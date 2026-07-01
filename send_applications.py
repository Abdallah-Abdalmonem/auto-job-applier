"""
Job Application Email Sender
Reads an Excel sheet of recipient emails and sends personalized job application
emails via Gmail SMTP. Skips any addresses that have been marked as blocked or
detected as spam. Includes rate limiting to avoid triggering spam filters.
"""

import smtplib
import ssl
import time
import random
import configparser
import argparse
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path

try:
    import openpyxl
except ImportError:
    print("openpyxl is required. Install it with: pip install openpyxl")
    sys.exit(1)


# ── helpers ──────────────────────────────────────────────────────────────────

def load_config(config_path: str) -> dict:
    """Read settings from an INI-style config file."""
    cfg = configparser.ConfigParser()
    cfg.read(config_path)
    if "gmail" not in cfg:
        raise ValueError(f"[gmail] section not found in {config_path}")
    g = cfg["gmail"]
    required = ["sender_email", "app_password"]
    for key in required:
        if key not in g:
            raise ValueError(f"Missing required key '{key}' in [gmail] section")
    return {
        "sender_email": g["sender_email"],
        "app_password": g["app_password"],
        "sender_name": g.get("sender_name", g["sender_email"]),
        "resume_path": g.get("resume_path", ""),
        "cover_letter_path": g.get("cover_letter_path", ""),
        "min_delay": float(g.get("min_delay", 30)),
        "max_delay": float(g.get("max_delay", 90)),
    }


def load_workbook_data(xlsx_path: str) -> list[dict]:
    """Load rows from the first sheet of the Excel workbook."""
    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        raise ValueError("Excel file is empty.")

    headers = [str(h).strip().lower() if h else f"col_{i}" for i, h in enumerate(rows[0])]
    records = []
    for row in rows[1:]:
        record = dict(zip(headers, row))
        # normalise key fields
        for key in ("email", "company", "position", "status", "notes"):
            if key in record and record[key] is not None:
                record[key] = str(record[key]).strip()
        records.append(record)
    wb.close()
    return records


def should_skip(record: dict) -> bool:
    """Return True if this recipient should be skipped."""
    status = record.get("status", "").lower()
    skip_values = {"blocked", "spam", "bounced", "skip", "sent", "replied", "ignore"}
    if status in skip_values:
        return True
    email = record.get("email", "")
    if not email or "@" not in email:
        return True
    return False


def build_email(
    sender_email: str,
    sender_name: str,
    recipient_email: str,
    company: str,
    position: str,
    body_template: str,
) -> MIMEMultipart:
    """Compose a MIME email with the given template filled in."""
    msg = MIMEMultipart()
    msg["From"] = f"{sender_name} <{sender_email}>"
    msg["To"] = recipient_email
    msg["Subject"] = f"Application for {position} at {company}"

    body = body_template.format(
        company=company,
        position=position,
        recipient_email=recipient_email,
    )
    msg.attach(MIMEText(body, "plain"))
    return msg


def attach_file(msg: MIMEMultipart, file_path: str):
    """Attach a file to the MIME message."""
    path = Path(file_path)
    if not path.exists():
        print(f"  WARNING: attachment not found — {file_path}")
        return
    with open(path, "rb") as f:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(f.read())
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", f"attachment; filename={path.name}")
    msg.attach(part)


def send_email(
    smtp_server: smtplib.SMTP_SSL,
    sender_email: str,
    recipient_email: str,
    msg: MIMEMultipart,
) -> bool:
    """Send a single email. Returns True on success."""
    try:
        smtp_server.sendmail(sender_email, recipient_email, msg.as_string())
        return True
    except smtplib.SMTPRecipientsRefused:
        print(f"  RECIPIENT REFUSED (likely blocked/spam): {recipient_email}")
        return False
    except smtplib.SMTPException as exc:
        print(f"  SMTP error sending to {recipient_email}: {exc}")
        return False


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Send job application emails from an Excel list.")
    parser.add_argument("--xlsx", default="emails.xlsx", help="Path to the Excel file (default: emails.xlsx)")
    parser.add_argument("--config", default="config.ini", help="Path to the config file (default: config.ini)")
    parser.add_argument("--dry-run", action="store_true", help="Preview emails without sending")
    parser.add_argument("--limit", type=int, default=0, help="Max number of emails to send (0 = no limit)")
    args = parser.parse_args()

    # load config
    config = load_config(args.config)
    sender_email = config["sender_email"]
    app_password = config["app_password"]
    sender_name = config["sender_name"]
    resume_path = config["resume_path"]
    cover_letter_path = config["cover_letter_path"]
    min_delay = config["min_delay"]
    max_delay = config["max_delay"]

    # load recipients
    records = load_workbook_data(args.xlsx)
    total = len(records)
    print(f"Loaded {total} rows from {args.xlsx}")

    # email body template — edit this to match your style
    body_template = """Dear Hiring Team at {company},

I am writing to express my interest in the {position} position at {company}. I believe my skills and experience make me a strong candidate for this role.

I have attached my resume and cover letter for your review. I would welcome the opportunity to discuss how I can contribute to your team.

Thank you for your time and consideration.

Best regards,
{sender_name}
""".replace("{sender_name}", sender_name)

    # connect to Gmail SMTP
    if not args.dry_run:
        context = ssl.create_default_context()
        print("Connecting to Gmail SMTP server...")
        try:
            smtp_server = smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context)
            smtp_server.login(sender_email, app_password)
        except smtplib.SMTPAuthenticationError:
            print("Authentication failed. Check your email and App Password in config.ini")
            sys.exit(1)
        except Exception as exc:
            print(f"Could not connect to Gmail: {exc}")
            sys.exit(1)
        print("Connected and authenticated.\n")

    sent = 0
    skipped = 0
    failed = 0

    for i, record in enumerate(records, start=1):
        email = record.get("email", "")
        company = record.get("company", "your company")
        position = record.get("position", "the open role")

        print(f"[{i}/{total}] {email} — {company} ({position})")

        if should_skip(record):
            reason = record.get("status", "missing email")
            print(f"  SKIPPED (status: {reason})")
            skipped += 1
            continue

        # build message
        msg = build_email(sender_email, sender_name, email, company, position, body_template)

        if resume_path:
            attach_file(msg, resume_path)
        if cover_letter_path:
            attach_file(msg, cover_letter_path)

        if args.dry_run:
            print(f"  DRY RUN — would send to {email}")
            sent += 1
            continue

        # send
        success = send_email(smtp_server, sender_email, email, msg)
        if success:
            print(f"  SENT successfully")
            sent += 1
        else:
            print(f"  FAILED — will need to retry or mark as blocked")
            failed += 1

        # rate limiting delay (skip after the last email)
        if i < total and (args.limit == 0 or sent < args.limit):
            delay = random.uniform(min_delay, max_delay)
            print(f"  Waiting {delay:.0f}s before next email...")
            time.sleep(delay)

        # honour --limit
        if args.limit and sent >= args.limit:
            print(f"\nReached limit of {args.limit} emails. Stopping.")
            break

    if not args.dry_run:
        smtp_server.quit()

    print(f"\n{'='*50}")
    print(f"Summary: {sent} sent, {skipped} skipped, {failed} failed (out of {total} total)")


if __name__ == "__main__":
    main()
