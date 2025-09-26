import os
import sys
import random
import sqlite3
import string
import smtplib
import traceback  # For detailed error logging
import time      # For polling the file upload status
from email.mime.text import MIMEText
from flask import Flask, request, redirect, url_for, render_template, session, flash
import google.generativeai as genai

# REMOVED: All pyresparser and nltk and pdfplumber imports are gone.
# We only need the core libraries.

# ---------------------------
# Configuration and Setup
# ---------------------------
app = Flask(__name__)
app.secret_key = 'your_secret_key_here'
DATABASE = 'database.db'
UPLOAD_FOLDER = os.path.join('static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Gemini API key
GEMINI_API_KEY = "AIzaSyABGNvp0TMDQEtVbRM26s253rHsv8VesmQ"
genai.configure(api_key=GEMINI_API_KEY)

generation_config = {
    "temperature": 1,
    "top_p": 0.95,
    "top_k": 40,
    "max_output_tokens": 8192,
    "response_mime_type": "text/plain",
}

# IMPORTANT: We need a model that supports file inputs. 
# 'gemini-2.0-flash-exp' might be text-only depending on API version.
# 'gemini-1.5-flash' or 'gemini-pro' are guaranteed to work with files.
# Let's target a known multimodal-capable model.
# NOTE: If 'gemini-1.5-flash' gives an error, change it back, but this is the correct family.
model = genai.GenerativeModel(
    model_name="gemini-2.0-flash-exp",  # Change to "gemini-1.5-flash" or "gemini-pro" if needed
    generation_config=generation_config,
)


# ---------------------------
# Database helper functions (Unchanged)
# ---------------------------
def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            user_type TEXT NOT NULL,
            skills TEXT
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS companies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            teacher_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            address TEXT,
            contact TEXT,
            image TEXT,
            skills TEXT,
            FOREIGN KEY (teacher_id) REFERENCES users (id)
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            company_id INTEGER NOT NULL,
            score INTEGER,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (student_id) REFERENCES users (id),
            FOREIGN KEY (company_id) REFERENCES companies (id)
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# ---------------------------
# Helper functions
# ---------------------------
def send_email(to_email, subject, message):
    """Send email using Gmail SMTP. (Unchanged)"""
    smtp_server = "smtp.gmail.com"
    smtp_port = 587
    sender_email = "logithkumar188@gmail.com"
    password = "nwqk nbup vlsr qpqq"
    msg = MIMEText(message)
    msg["Subject"] = subject
    msg["From"] = sender_email
    msg["To"] = to_email

    try:
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(sender_email, password)
        server.sendmail(sender_email, [to_email], msg.as_string())
        server.quit()
    except Exception as e:
        print("Error sending email:", e)

def generate_questions(company_skills):
    """Generate 10 multiple-choice questions using Gemini (Unchanged)."""
    skills_prompt = company_skills.strip() if company_skills.strip() else "General Knowledge"
    prompt = (
        f"Generate 10 multiple choice questions based on the following skills: {skills_prompt}. "
        "Each question must include exactly four options formatted as follows:\n"
        "Question: <Your question here>\n"
        "Options:\n"
        "A. <Option A>\n"
        "B. <Option B>\n"
        "C. <Option C>\n"
        "D. <Option D>\n"
        "Answer: <Letter of correct answer>\n"
        "Do not include any extra text." \
        "Al the skills must get equal no of questions"
    )

    try:
        # Use generate_content for reliability, not start_chat
        response = model.generate_content(prompt)
        response_text = response.text
    except Exception as e:
        print("Gemini API error:", e)
        return []

    # Parse the response (Unchanged)
    questions = []
    question_blocks = response_text.split("Question:")
    for block in question_blocks[1:]:
        try:
            question_part, rest = block.split("Options:", 1)
            options_str, answer_str = rest.split("Answer:", 1)
            options_lines = options_str.strip().splitlines()
            options = {
                line.split('.')[0].strip(): line.split('.', 1)[1].strip()
                for line in options_lines if '.' in line
            }
            questions.append({
                'question': question_part.strip(),
                'options': options,
                'correct': answer_str.strip()[0]
            })
        except Exception as e:
            print("Error parsing question:", e)
            continue
    return questions

def skills_match(student_skills, company_skills):
    """Return True if at least one skill (case-insensitive) matches. (Unchanged)"""
    student_list = [s.strip().lower() for s in student_skills.split(',') if s.strip()]
    company_list = [s.strip().lower() for s in company_skills.split(',') if s.strip()]
    return bool(set(student_list) & set(company_list))

# -----------------------------------------------
# NEW ALL-IN-ONE SKILL EXTRACTOR FUNCTION
# This replaces both pdfplumber and the old gemini text function.
# It works on BOTH digital and scanned image PDFs.
# -----------------------------------------------
def extract_skills_from_pdf_with_gemini(pdf_path):
    """Uploads PDF to Gemini, performs OCR if needed, and extracts skills."""
    resume_file = None
    try:
        print(f"🚀 Uploading {pdf_path} to Gemini API for multimodal extraction...")
        
        # 1. Upload the file to the Gemini API
        resume_file = genai.upload_file(path=pdf_path, display_name="Uploaded Resume")
        
        print(f"File uploaded, waiting for processing... (Name: {resume_file.name})")
        
        # 2. Wait for the file to be processed
        while resume_file.state.name == "PROCESSING":
             time.sleep(2) # Poll every 2 seconds
             resume_file = genai.get_file(resume_file.name)
        
        if resume_file.state.name != "ACTIVE":
            print(f"❌ File upload failed with state: {resume_file.state.name}")
            return ""

        print("✅ File active. Sending extraction prompt.")
        
        # 3. Create the prompt, including the file reference
        prompt = (
            "Based on the attached resume PDF (which may be a scanned image or digital text), "
            "please perform OCR if necessary and extract a comprehensive list of all technical skills, "
            "programming languages, frameworks, libraries, tools, and important soft skills mentioned. "
            "Return ONLY a single comma-separated list (e.g., Python, Java, React, Team Leadership, SQL, Git, Data Analysis). "
            "Do not add any preamble, titles, explanations, or labels like 'Skills:'. Just the comma-separated list."
        )
        
        # 4. Send the prompt AND the file to the model
        response = model.generate_content([prompt, resume_file])
        
        # 5. Clean and return the extracted text
        skills_text = response.text.strip().replace('*', '').replace('\n', ', ').strip()
        
        # Remove any "Here is the list:" preamble
        if ":" in skills_text:
            skills_text = skills_text.split(":")[-1].strip()
        
        skills_list = [skill.strip() for skill in skills_text.split(',') if skill.strip()]
        cleaned_skills = ", ".join(skills_list)
        
        print(f"🎯 Skills extracted by Gemini (from PDF): {cleaned_skills}")
        return cleaned_skills

    except Exception as e:
        print(f"❌ Gemini API file processing error: {e}")
        traceback.print_exc()
        return ""
        
    finally:
        # 6. Delete the file from Google's storage to clean up
        if resume_file:
            try:
                genai.delete_file(resume_file.name)
                print(f"🗑️ Deleted remote file: {resume_file.name}")
            except Exception as del_e:
                print(f"⚠️ Could not delete remote file: {del_e}") # Non-fatal error

# ---------------------------
# All Routes below are unchanged EXCEPT /upload_resume
# ---------------------------
@app.route('/')
def index():
    return render_template("index.html")

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username  = request.form['username']
        email     = request.form['email']
        password  = request.form['password']
        user_type = request.form['user_type']
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute("INSERT INTO users (username, email, password, user_type) VALUES (?, ?, ?, ?)",
                        (username, email, password, user_type))
            conn.commit()
            flash("Registration successful. Please log in.", "success")
        except sqlite3.IntegrityError:
            flash("User with this email already exists.", "error")
            conn.close()
            return redirect(url_for('register'))
        conn.close()
        return redirect(url_for('login'))
    return render_template("register.html")

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email    = request.form['email']
        password = request.form['password']
        conn = get_db_connection()
        user = conn.execute("SELECT * FROM users WHERE email = ? AND password = ?", (email, password)).fetchone()
        conn.close()
        if user:
            session['user_id'] = user['id']
            session['user_type'] = user['user_type']
            if user['user_type'] == 'teacher':
                return redirect(url_for('upload'))
            else:
                return redirect(url_for('resume'))
        else:
            flash("Invalid credentials", "error")
            return redirect(url_for('login'))
    return render_template("login.html")

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if 'user_id' not in session or session.get('user_type') != 'teacher':
        flash("Access denied", "error")
        return redirect(url_for('login'))
    if request.method == 'POST':
        name    = request.form['name']
        address = request.form['address']
        contact = request.form['contact']
        skills  = request.form['skills']
        image_file = request.files['image']
        image_filename = None
        if image_file:
            image_filename = ''.join(random.choices(string.ascii_letters + string.digits, k=8)) + "_" + image_file.filename
            image_path = os.path.join(UPLOAD_FOLDER, image_filename)
            image_file.save(image_path)
        conn = get_db_connection()
        conn.execute("INSERT INTO companies (teacher_id, name, address, contact, image, skills) VALUES (?, ?, ?, ?, ?, ?)",
                       (session['user_id'], name, address, contact, image_filename, skills))
        conn.commit()
        conn.close()
        flash("Company uploaded successfully.", "success")
        return redirect(url_for('upload'))
    conn = get_db_connection()
    companies = conn.execute("SELECT * FROM companies WHERE teacher_id = ?", (session['user_id'],)).fetchall()
    conn.close()
    return render_template("upload.html", companies=companies)

@app.route('/company/<int:company_id>')
def company_details(company_id):
    if 'user_id' not in session or session.get('user_type') != 'teacher':
        flash("Access denied", "error")
        return redirect(url_for('login'))
    conn = get_db_connection()
    company = conn.execute("SELECT * FROM companies WHERE id = ?", (company_id,)).fetchone()
    conn.close()
    return render_template("company_details.html", company=company)

@app.route('/results')
def results():
    if 'user_id' not in session:
        flash("Please log in", "error")
        return redirect(url_for('login'))
    conn = get_db_connection()
    if session.get('user_type') == 'teacher':
        res = conn.execute("""
            SELECT r.*, u.username as student_name, c.name as company_name
            FROM results r 
            JOIN users u ON r.student_id = u.id 
            JOIN companies c ON r.company_id = c.id
            ORDER BY r.timestamp DESC
        """).fetchall()
    else:
        res = conn.execute("""
            SELECT r.*, c.name as company_name
            FROM results r 
            JOIN companies c ON r.company_id = c.id
            WHERE r.student_id = ?
            ORDER BY r.timestamp DESC
        """, (session['user_id'],)).fetchall()
    conn.close()
    return render_template("results.html", res=res, user_type=session.get('user_type'))

# ---------------------------
# Resume Routes
# ---------------------------
@app.route('/resume', methods=['GET', 'POST'])
def resume():
    # Only for students
    if 'user_id' not in session or session.get('user_type') != 'student':
        flash("Access denied", "error")
        return redirect(url_for('login'))

    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (session['user_id'],)).fetchone()
    companies = []

    # This route now handles manual skill entry (unchanged)
    if request.method == 'POST' and "skills" in request.form:
        skills = request.form['skills']
        conn.execute("UPDATE users SET skills = ? WHERE id = ?", (skills, session['user_id']))
        conn.commit()
        user = conn.execute("SELECT * FROM users WHERE id = ?", (session['user_id'],)).fetchone()

        if skills:
            all_companies = conn.execute("SELECT * FROM companies").fetchall()
            for comp in all_companies:
                if comp['skills'] and skills_match(skills, comp['skills']):
                    companies.append(comp)

    conn.close()
    return render_template("resume.html", user=user, companies=companies)


# ---------------------------
# MODIFIED UPLOAD_RESUME ROUTE (now uses direct Gemini PDF upload)
# ---------------------------
@app.route('/upload_resume', methods=['POST'])
def upload_resume():
    if 'user_id' not in session or session.get('user_type') != 'student':
        flash("Access denied", "error")
        return redirect(url_for("login"))
        
    if "resume" not in request.files:
        flash("No file part", "error")
        return redirect(url_for("resume"))

    file = request.files["resume"]
    if file.filename == "":
        flash("No selected file", "error")
        return redirect(url_for("resume"))

    extracted_skills = ""
    file_path = ""
    matching_companies = []
    user = None
    conn = None # Ensure conn is defined for the finally block

    if file:
        try:
            # Save the file locally first
            file_path = os.path.join(UPLOAD_FOLDER, file.filename)
            file.save(file_path)
            print(f"📁 Resume uploaded locally: {file_path}")

            # --- NEW LOGIC: Send file directly to Gemini ---
            # This one function handles OCR, text extraction, and skill extraction
            extracted_skills = extract_skills_from_pdf_with_gemini(file_path)
            
            if not extracted_skills:
                flash("AI could not identify or extract any skills from the uploaded PDF.", "warning")
                # We still continue, just with an empty skill list

        except Exception as e:
            print(f"🚨 Unexpected error during resume processing: {e}")
            traceback.print_exc()
            flash(f"An unexpected error occurred processing the file: {e}", "error")
            return redirect(url_for("resume"))

    # --- Database logic remains the same ---
    # Save extracted skills to DB and get matching companies
    try:
        conn = get_db_connection()
        conn.execute("UPDATE users SET skills = ? WHERE id = ?", (extracted_skills, session['user_id']))
        conn.commit()

        user = conn.execute("SELECT * FROM users WHERE id = ?", (session['user_id'],)).fetchone()

        if extracted_skills:
            all_companies = conn.execute("SELECT * FROM companies").fetchall()
            print(f"🏢 Checking {len(all_companies)} companies for skill matches...")
            for comp in all_companies:
                if comp['skills'] and skills_match(extracted_skills, comp['skills']):
                    print(f"✅ Match found: {comp['name']}")
                    matching_companies.append(comp)
        else:
            print("⚠️ No skills extracted or found, skipping company matching.")
            
    except Exception as e:
        print(f"❌ Database error after extraction: {e}")
        flash("Skills extracted, but failed to save to database.", "error")
    finally:
        if conn:
            conn.close()

    print(f"🏁 Total matching companies: {len(matching_companies)}")
    flash("Resume uploaded and skills extracted successfully using AI!", "success")
    return render_template("resume.html", 
                           extracted_skills=extracted_skills, 
                           companies=matching_companies, 
                           user=user)

# ---------------------------
# Other Routes (Unchanged)
# ---------------------------
@app.route('/company_student/<int:company_id>')
def company_details_student(company_id):
    if 'user_id' not in session or session.get('user_type') != 'student':
        flash("Access denied", "error")
        return redirect(url_for('login'))
    conn = get_db_connection()
    company = conn.execute("SELECT * FROM companies WHERE id = ?", (company_id,)).fetchone()
    conn.close()
    return render_template("company_details_student.html", company=company)

@app.route('/assessment/<int:company_id>', methods=['GET', 'POST'])
def assessment(company_id):
    if 'user_id' not in session or session.get('user_type') != 'student':
        flash("Access denied", "error")
        return redirect(url_for('login'))
    conn = get_db_connection()
    company = conn.execute("SELECT * FROM companies WHERE id = ?", (company_id,)).fetchone()
    conn.close()
    if request.method == 'POST':
        questions = session.get('questions')
        if not questions:
            flash("Session expired. Please try again.", "error")
            return redirect(url_for('resume'))
        score = 0
        for i, q in enumerate(questions):
            answer = request.form.get(f"q{i}")
            if answer == q['correct']:
                score += 1
        conn = get_db_connection()
        conn.execute("INSERT INTO results (student_id, company_id, score) VALUES (?, ?, ?)",
                       (session['user_id'], company_id, score))
        conn.commit()
        user = conn.execute("SELECT * FROM users WHERE id = ?", (session['user_id'],)).fetchone()
        conn.close()
        email_body = (f"Dear {user['username']},\n\nYou have completed the assessment for {company['name']} "
                      f"with a score of {score}/10.\n\nRegards,\nPlacement Monitoring System")
        send_email(user['email'], "Assessment Result", email_body)
        flash(f"Assessment submitted. Your score is {score}/10. An email has been sent to you.", "success")
        return redirect(url_for('student_results'))
    else:
        questions = generate_questions(company['skills'] if company['skills'] else "")
        session['questions'] = questions
        return render_template("assessment.html", company=company, questions=questions)

@app.route('/student_results')
def student_results():
    if 'user_id' not in session or session.get('user_type') != 'student':
        flash("Access denied", "error")
        return redirect(url_for('login'))
    conn = get_db_connection()
    res = conn.execute("""
            SELECT r.*, c.name as company_name
            FROM results r 
            JOIN companies c ON r.company_id = c.id
            WHERE r.student_id = ?
            ORDER BY r.timestamp DESC
        """, (session['user_id'],)).fetchall()
    conn.close()
    return render_template("student_results.html", res=res)

# ---------------------------
# Run the app
# ---------------------------
if __name__ == '__main__':
    # Make sure you are in your (resume_env_final) environment
    # Then just run: python app.py
    app.run(debug=True)