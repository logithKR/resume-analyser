# AI-Powered Placement Monitoring System

This is a Python Flask-based web application designed to connect students with matching companies based on their resume skills. It leverages the **Google Gemini AI API** to automatically parse uploaded resumes (PDFs) and extract skills, and also to dynamically generate assessment quizzes for students.

## Features
- **Role-Based Access:** Separate dashboards for Teachers and Students.
- **AI Skill Extraction:** Students upload a PDF resume, and Gemini AI extracts technical and soft skills automatically. It can even perform OCR on scanned PDFs.
- **Smart Matching:** The system matches a student's extracted skills with the specific skill requirements of uploaded companies.
- **AI Assessments:** Gemini AI dynamically generates a 10-question multiple-choice quiz based on the specific skills a company requires.
- **Automated Emailing:** Assessment scores are automatically emailed to students upon completion.

## Prerequisites
- Python 3.8 or higher installed on your machine.

## Setup Instructions

### 1. Create a Virtual Environment (Recommended)
Creating a virtual environment ensures that the project dependencies don't interfere with your system-wide Python packages.
```bash
python -m venv venv

# To activate on Windows:
venv\Scripts\activate

# To activate on Mac/Linux:
source venv/bin/activate
```

### 2. Install Dependencies
Install all required third-party libraries using the provided requirements file:
```bash
pip install -r requirements.txt
```

### 3. Set Up API Keys
This project requires a Google Gemini API Key to function.
1. Go to [Google AI Studio](https://aistudio.google.com/app/apikey) and create a free API key.
2. In the root directory of this project, create a new file named `.env`.
3. Add your API key to the `.env` file exactly like this:
   ```env
   GEMINI_API_KEY=AIzaSy...your_actual_key_here
   ```

*(Note: The `.env` file is safely ignored by Git so your key won't be pushed to public repositories).*

### 4. Run the Application
Start the Flask development server:
```bash
python app.py
```
Open your web browser and go to `http://127.0.0.1:5000/`.

## Usage Workflow
1. **Teacher:** Register a new account as a `teacher`. Navigate to the "Upload Company" section to add companies, specify required skills (e.g., "Python, SQL, React"), and upload a company logo.
2. **Student:** Register a new account as a `student`. Navigate to your "Resume" dashboard. Upload a PDF resume. The AI will extract your skills and instantly show you companies that require those skills.
3. **Assessment:** As a student, click on a matching company to take an AI-generated quiz tailored to those skills. Once submitted, your score is logged and emailed to you.
