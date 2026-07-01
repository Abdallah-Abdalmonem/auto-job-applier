# Auto Job Applier

A smart, rate-limited job application automation tool. It reads recipient emails from an Excel (`.xlsx`) or CSV (`.csv`) file and sends personalized job applications via Gmail SMTP. 

It includes a beautiful, local **Web Dashboard** for drag-and-drop asset management and real-time execution tracking, in addition to the standard command-line script.

---

## 🚀 Features

- **Web Dashboard:** A premium glassmorphic dark-mode web page to upload files, save settings, and track live email sends.
- **Excel & CSV Support:** Parses contacts lists with or without headers (auto-detects structure).
- **Dynamic Formatting:** If the company name is missing, the email template automatically cleans itself up (e.g. `Dear Hiring Team` instead of `Dear Hiring Team at `).
- **Default Position:** Set a fallback job title in configuration or via command line.
- **Spam Avoidance:** Adds random rate-limiting delays (30–90 seconds) between sends.
- **Attachment Support:** Attaches your Resume and Cover Letter automatically.

---

## 📂 Project Structure

| File / Folder | Purpose |
|---|---|
| `send_applications.py` | Command-line script to send emails |
| `app.py` | Local Flask Web Server (Web Dashboard) |
| `templates/`, `static/` | Frontend HTML, CSS, and JS for the dashboard |
| `config.ini` | Gmail credentials, delays, and default settings |
| `emails.xlsx` / `emails.csv` | List of recipient emails |
| `resume.pdf` / `cover_letter.pdf` | Attached PDF documents |

---

## 🛠️ Setup & Installation

### 1. Install Dependencies
Install Flask (for the dashboard) and openpyxl (for Excel files):
```bash
pip install Flask openpyxl
```

### 2. Generate a Gmail App Password
Gmail SMTP requires a **16-character App Password** (not your regular Gmail password):
1. Go to your [Google Account Security Settings](https://myaccount.google.com/security).
2. Enable **2-Step Verification** if it isn't already.
3. Search for **App passwords** (or go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)).
4. Create a new app (e.g. select "Other", name it "Job Applier") and click **Create**.
5. Copy the generated 16-character password.

---

## 💻 Web Dashboard Usage (Recommended)

1. Start the local server:
   ```bash
   python app.py
   ```
2. Open **[http://127.0.0.1:5000](http://127.0.0.1:5000)** in your browser.
3. Configure your SMTP Settings and Gmail details.
4. Drag & drop your files (Contacts sheet, Resume PDF, Cover Letter PDF).
5. Tick **Dry Run Mode** to test first, then click **Start Job Applier** to view live progress!

---

## 🐚 Command Line Usage

If you prefer to run it directly from the terminal, configuration is read from `config.ini`.

### Run a Dry Run (Recommended first step)
```bash
python send_applications.py --dry-run
```
*Shows a terminal preview of the first email's subject and body, and logs skipped addresses.*

### Run Actual Application Send
```bash
python send_applications.py
```

### Advanced CLI Arguments
- `--xlsx file.csv` — Specify a custom Excel or CSV contact sheet.
- `--position "Backend Engineer"` — Override the job title for all applications.
- `--limit 10` — Stop sending after 10 successful emails.
- `--config custom.ini` — Use a different configuration file.

---

## 📊 Sheet Structure (`emails.xlsx` or `emails.csv`)
If your file has a header row, the columns will be automatically mapped. If it doesn't, the script assumes **Column 1 is the Email** and **Column 2 is the Position** (if exists).

| Column | Required | Description |
|---|---|---|
| **email** | **Yes** | Recipient's email address |
| **position** | No | Job title (defaults to `default_position` in config) |
| **company** | No | Company name (used in email body) |
| **status** | No | Skip value: set to `sent`, `blocked`, `spam` to ignore |
| **notes** | No | Internal notes (ignored by script) |

---

## ⚠️ Troubleshooting
- **"Authentication failed":** Double-check your App Password in `config.ini` or the Web Dashboard. Make sure it doesn't contain spaces and you copied all 16 characters.
- **SMTP Connection Error:** Make sure your internet connection is active and that your network does not block port 465 (common on some public WiFi networks or corporate firewalls).

