# 🤖 Resume Screening AI

An AI-powered resume screening workflow built with **n8n**, **Google Gemini**, **Google Drive**, **Notion**, and **Gmail**.

This project automates the recruitment screening process by comparing candidate resumes with a job description, generating ATS scores, identifying skill gaps, and storing structured evaluation results in Notion.

---

## 🚀 Features

- 📄 Job Application Form
- 📎 PDF Resume Upload
- ☁️ Google Drive Integration
- 📑 Resume Text Extraction
- 📋 Job Description Parsing
- 🤖 AI Resume Analysis with Google Gemini
- 🎯 ATS Score (0–100)
- ⭐ Overall Candidate Fit Rating (0–10)
- 💪 Strength & Weakness Analysis
- 📈 Risk & Reward Assessment
- 🧠 Matched & Missing Skills Detection
- 🎤 AI-Generated Interview Questions
- 📧 Automatic Confirmation Email
- 🗂️ Candidate Database in Notion

---

# 🏗 Workflow

```text
Candidate
    │
    ▼
Application Form
    │
    ▼
Upload Resume
    │
    ▼
Google Drive
    │
    ▼
Extract Resume Text
    │
    ▼
Extract Job Description
    │
    ▼
Google Gemini AI
    │
    ├── ATS Score
    ├── Skill Match
    ├── Missing Skills
    ├── Candidate Summary
    ├── Interview Questions
    ├── Hiring Recommendation
    └── Risk & Reward Analysis
    │
    ▼
Send Confirmation Email
    │
    ▼
Save Results to Notion
```

---

## 🛠 Tech Stack

| Technology | Purpose |
|------------|---------|
| n8n | Workflow Automation |
| Google Gemini | AI Resume Screening |
| Google Drive | Resume Storage |
| Gmail | Email Automation |
| Notion | Candidate Database |
| PDF Extract | Resume Parsing |

---

## 📂 Repository Structure

```text
Resume_Screening_AI/
│
├── README.md
└── Resume screening AI.json
```

---

## ⚙️ How It Works

1. Applicant submits the application form.
2. Resume is uploaded to Google Drive.
3. Resume text is extracted automatically.
4. Job description is extracted from a PDF.
5. Google Gemini compares the resume with the job description.
6. AI generates:
   - ATS Score
   - Candidate Summary
   - Matched Skills
   - Missing Skills
   - Strengths & Weaknesses
   - Risk & Reward Assessment
   - Interview Questions
   - Hiring Recommendation
7. Confirmation email is sent to the applicant.
8. Results are stored in a Notion database.

---

## 📊 AI Output

The workflow generates:

- ✅ ATS Score
- ✅ Overall Fit Rating
- ✅ Hiring Recommendation
- ✅ Candidate Summary
- ✅ Matched Skills
- ✅ Missing Skills
- ✅ Additional Skills
- ✅ Strengths & Weaknesses
- ✅ Risk Assessment
- ✅ Reward Assessment
- ✅ Interview Questions

---

## 📥 Getting Started

### Prerequisites

- n8n
- Google Gemini API
- Google Drive OAuth
- Gmail OAuth
- Notion Integration

### Import Workflow

1. Clone this repository:

```bash
git clone https://github.com/yourusername/Resume_Screening_AI.git
```

2. Open **n8n**.

3. Import:

```
Resume screening AI.json
```

4. Configure all required credentials.

5. Activate the workflow.

---

## 📸 Screenshots

<img width="1552" height="707" alt="image" src="https://github.com/user-attachments/assets/9aa3a3bf-a9c2-40ae-b74b-8239b40f079b" />

<img width="870" height="925" alt="image" src="https://github.com/user-attachments/assets/17f884d1-ba3c-4de2-9338-dd3db8c7995d" />

<img width="1267" height="742" alt="image" src="https://github.com/user-attachments/assets/46cb86ab-5317-471c-b1a4-599dfe29c985" />

<img width="1447" height="313" alt="image" src="https://github.com/user-attachments/assets/a4c952ff-5bde-4e33-93f7-6f2fb97b7408" />

<img width="1553" height="337" alt="image" src="https://github.com/user-attachments/assets/188ab651-2dec-4029-a71a-cdfedb18e87b" />




---

## 🔮 Future Improvements

- Multiple Job Description Support
- Resume Ranking Dashboard
- Duplicate Resume Detection
- Recruiter Email Notifications
- Slack Integration
- Interview Scheduling
- Support DOCX Resumes
- Candidate Analytics Dashboard

---

## 📄 License

This project is licensed under the **MIT License**.

---

## 👨‍💻 Author

**Vignesh Rao**

- GitHub: https://github.com/vigneshrao77

---

⭐ **If you found this project useful, consider giving it a star!**
