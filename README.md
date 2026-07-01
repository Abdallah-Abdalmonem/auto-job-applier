# Job Application Email Sender

Reads an Excel sheet of recipient emails and sends job application emails via Gmail SMTP. Automatically skips addresses marked as blocked, spam, bounced, or already sent. Includes rate limiting to avoid triggering spam filters.

## Files

| File | Purpose |
|---|---|
| `send_applications.py` | Main script — reads Excel, sends emails |
| `create_sample_excel.py` | Generates `emails.xlsx` with sample data |
| `emails.xlsx` | Your email list (edit this with real data) |
| `config.ini` | Your Gmail credentials and settings |
| `resume.pdf` | Your resume (place in this folder) |
| `cover_letter.pdf` | Your cover letter (place in this folder) |

## Setup

### 1. Install Python dependencies

```bash
pip install openpyxl
```

### 2. Generate a Gmail App Password

Gmail requires an App Password (not your regular password) for SMTP access:

1. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
2. Sign in if needed
3. Select app: **Mail**, Select device: **Other** → name it "Job Script"
4. Click **Generate** — copy the 16-character password

> If you don't see the App Password option, you need to enable 2-Step Verification first (under Security → 2-Step Verification).

### 3. Configure `config.ini`

Open `config.ini` and fill in:

- `sender_email` — your Gmail address
- `app_password` — the 16-character App Password (spaces are fine)
- `sender_name` — your full name as you want recipients to see it
- `resume_path` — path to your resume file (e.g., `resume.pdf`)
- `cover_letter_path` — path to your cover letter (leave empty `""` if none)
- `min_delay` / `max_delay` — random delay range in seconds between emails

### 4. Prepare your Excel sheet

Open `emails.xlsx` and fill in your data. The columns are:

| Column | Required | Description |
|---|---|---|
| **email** | Yes | Recipient's email address |
| **company** | Yes | Company name (used in the email body) |
| **position** | Yes | Job title (used in subject and body) |
| **status** | No | Leave blank to send, or set to: `spam`, `blocked`, `sent`, `replied`, `skip` |
| **notes** | No | Your personal notes (not sent) |

Rows with a status of `spam`, `blocked`, `sent`, `replied`, or `skip` are automatically skipped. This is how you prevent sending to addresses that blocked you or marked you as spam.

### 5. Place your files

Put your `resume.pdf` and `cover_letter.pdf` in this folder (or update the paths in `config.ini`).

## Usage

### Preview first (dry run — no emails sent)

```bash
python send_applications.py --dry-run
```

This shows you exactly which emails would be sent and which would be skipped, without actually sending anything.

### Send emails

```bash
python send_applications.py
```

### Use a different Excel file or config

```bash
python send_applications.py --xlsx my_list.csv --config my_config.ini
```

### Limit the number of emails sent

```bash
python send_applications.py --limit 5
```

Useful for testing — sends only the first 5 eligible emails and stops.

## How spam avoidance works

- **Rate limiting**: A random delay (30–90 seconds by default) is added between each email. This mimics human behaviour and avoids Gmail's rate limits.
- **Status tracking**: Any address that blocks you or marks you as spam should be marked with `blocked` or `spam` in the Excel sheet. The script will skip them on subsequent runs.
- **Recipient refusal detection**: If Gmail refuses a recipient (e.g., the address is invalid or has blocked you), the script catches the error and reports it without crashing.

## Typical workflow

1. Add new recipients to `emails.xlsx` with an empty status
2. Run `--dry-run` to verify the list
3. Run the script to send
4. After a few days, update statuses for bounced/blocked/spam addresses
5. Run again for new batches

## Troubleshooting

| Problem | Solution |
|---|---|
| "Authentication failed" | Double-check your App Password in `config.ini`. Make sure you're using an App Password, not your regular Gmail password. |
| "openpyxl is required" | Run `pip install openpyxl` |
| Emails going to recipient's spam | Make sure your email body looks natural. Customise the template in `send_applications.py`. Also ensure your Gmail account is warmed up (has been sending normal emails). |
| "Connection refused" | Check your internet connection. Some networks block port 465 — try a different network or VPN. |
