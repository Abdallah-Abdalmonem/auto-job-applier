import os
import threading
import time
import random
import smtplib
import ssl
import configparser
from pathlib import Path
from email.mime.multipart import MIMEMultipart
from flask import Flask, request, jsonify, render_template, send_from_directory
from werkzeug.utils import secure_filename

# Import helper functions from the original script
from send_applications import load_config, load_workbook_data, build_email, send_email, should_skip, attach_file

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config['UPLOAD_FOLDER'] = os.path.dirname(os.path.abspath(__file__))
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB limit

# Shared application state
state = {
    "status": "idle",  # "idle", "running", "completed"
    "total": 0,
    "sent": 0,
    "skipped": 0,
    "failed": 0,
    "logs": [],
    "records": [],
    "stop_requested": False
}

state_lock = threading.Lock()
config_path = os.path.join(app.config['UPLOAD_FOLDER'], "config.ini")

def add_log(msg):
    timestamp = time.strftime('%H:%M:%S')
    with state_lock:
        state["logs"].append(f"[{timestamp}] {msg}")

def email_sender_worker(xlsx_path, dry_run, limit, position_override):
    global state
    
    with state_lock:
        state["status"] = "running"
        state["logs"] = []
        state["sent"] = 0
        state["skipped"] = 0
        state["failed"] = 0
        state["stop_requested"] = False

    try:
        add_log("Starting background sender task...")
        # Reload fresh config
        config = load_config(config_path)
        sender_email = config["sender_email"]
        app_password = config["app_password"]
        sender_name = config["sender_name"]
        resume_path = config["resume_path"]
        cover_letter_path = config["cover_letter_path"]
        min_delay = config["min_delay"]
        max_delay = config["max_delay"]
        default_position = config.get("default_position", "")

        add_log(f"Loading recipient data from {xlsx_path}...")
        records = load_workbook_data(xlsx_path)
        total = len(records)
        
        with state_lock:
            state["total"] = total
            state["records"] = [
                {**r, "send_status": "pending", "error": ""} for r in records
            ]

        add_log(f"Successfully loaded {total} contacts.")

        body_template = """{salutation},

I am writing to express my interest in the {position} position{company_at}. I believe my skills and experience make me a strong candidate for this role.

I have attached my resume and cover letter for your review. I would welcome the opportunity to discuss how I can contribute to your team.

Thank you for your time and consideration.

Best regards,
{sender_name}
""".replace("{sender_name}", sender_name)

        smtp_server = None
        if not dry_run:
            add_log("Connecting to Gmail SMTP server (smtp.gmail.com:465)...")
            context = ssl.create_default_context()
            try:
                smtp_server = smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context)
                smtp_server.login(sender_email, app_password)
                add_log("SMTP authenticated successfully. Ready to send.")
            except Exception as e:
                add_log(f"SMTP CONNECTION ERROR: {str(e)}")
                add_log("Please check your email and App Password configuration.")
                with state_lock:
                    state["status"] = "completed"
                return

        for i, record in enumerate(records):
            if state["stop_requested"]:
                add_log("STOP SIGN RECEIVED: Terminating early.")
                break

            email = record.get("email", "")
            company = record.get("company", "")
            position = record.get("position", "") or position_override or default_position or "open position"
            
            comp_display = company if company else "(no company)"
            add_log(f"[{i+1}/{total}] Processing email to '{email}' for position '{position}' at {comp_display}...")

            with state_lock:
                state["records"][i]["send_status"] = "processing"

            if should_skip(record):
                reason = record.get("status", "")
                if not reason:
                    if not email or "@" not in email:
                        reason = "missing or invalid email"
                    else:
                        reason = "skipped"
                add_log(f"  SKIPPED: {reason}")
                with state_lock:
                    state["skipped"] += 1
                    state["records"][i]["send_status"] = "skipped"
                    state["records"][i]["error"] = reason
                continue

            # Build message
            msg = build_email(sender_email, sender_name, email, company, position, body_template)

            # File attachments
            if resume_path:
                resume_abs = os.path.join(app.config['UPLOAD_FOLDER'], resume_path)
                if os.path.exists(resume_abs):
                    attach_file(msg, resume_abs)
                else:
                    add_log(f"  WARNING: Resume not found at path: {resume_path}")

            if cover_letter_path:
                cover_abs = os.path.join(app.config['UPLOAD_FOLDER'], cover_letter_path)
                if os.path.exists(cover_abs):
                    attach_file(msg, cover_abs)
                else:
                    add_log(f"  WARNING: Cover letter not found at path: {cover_letter_path}")

            if dry_run:
                if state["sent"] == 0:
                    add_log("--- DRY RUN PREVIEW (FIRST EMAIL) ---")
                    add_log(f"Subject: {msg['Subject']}")
                    body_text = ""
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain":
                            body_text = part.get_payload()
                            break
                    add_log("Body:")
                    for line in body_text.splitlines():
                        add_log(f"  {line}")
                    attachments_list = [Path(p).name for p in [resume_path, cover_letter_path] if p]
                    add_log(f"Attachments: {attachments_list}")
                    add_log("-------------------------------------")
                
                add_log(f"  [DRY RUN] Simulating email sent to {email}")
                with state_lock:
                    state["sent"] += 1
                    state["records"][i]["send_status"] = "sent"
                continue

            # Actual send
            success = send_email(smtp_server, sender_email, email, msg)
            if success:
                add_log(f"  SUCCESS: Email sent to {email}")
                with state_lock:
                    state["sent"] += 1
                    state["records"][i]["send_status"] = "sent"
            else:
                add_log(f"  FAILED to send to {email}")
                with state_lock:
                    state["failed"] += 1
                    state["records"][i]["send_status"] = "failed"
                    state["records"][i]["error"] = "SMTP Error"

            # Rate limit delay
            if i < total - 1 and (limit == 0 or state["sent"] < limit):
                delay = random.uniform(min_delay, max_delay)
                add_log(f"  Rate Limiting: waiting {delay:.1f}s before next email...")
                sleep_start = time.time()
                while time.time() - sleep_start < delay:
                    if state["stop_requested"]:
                        break
                    time.sleep(0.2)

            if limit > 0 and state["sent"] >= limit:
                add_log(f"Reached execution limit of {limit} sent emails. Stopping.")
                break

        if smtp_server:
            try:
                smtp_server.quit()
                add_log("SMTP server connection closed.")
            except:
                pass

        add_log("Background sender execution finished.")
        with state_lock:
            state["status"] = "completed"

    except Exception as e:
        add_log(f"CRITICAL WORKER ERROR: {str(e)}")
        with state_lock:
            state["status"] = "completed"

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/config", methods=["GET"])
def get_config():
    try:
        cfg = configparser.ConfigParser()
        cfg.read(config_path)
        g = cfg["gmail"] if "gmail" in cfg else {}
        
        def clean_val(key):
            val = g.get(key, "")
            return val.strip().strip("'\"").strip()

        return jsonify({
            "sender_email": clean_val("sender_email"),
            "sender_name": clean_val("sender_name"),
            "app_password": clean_val("app_password"),
            "resume_path": clean_val("resume_path"),
            "cover_letter_path": clean_val("cover_letter_path"),
            "min_delay": clean_val("min_delay") or "30",
            "max_delay": clean_val("max_delay") or "90",
            "default_position": clean_val("default_position")
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/config", methods=["POST"])
def save_config():
    try:
        data = request.json
        cfg = configparser.ConfigParser()
        cfg.read(config_path)
        if "gmail" not in cfg:
            cfg["gmail"] = {}
        
        cfg["gmail"]["sender_email"] = data.get("sender_email", "")
        cfg["gmail"]["sender_name"] = data.get("sender_name", "")
        cfg["gmail"]["app_password"] = data.get("app_password", "")
        cfg["gmail"]["resume_path"] = data.get("resume_path", "")
        cfg["gmail"]["cover_letter_path"] = data.get("cover_letter_path", "")
        cfg["gmail"]["min_delay"] = str(data.get("min_delay", 30))
        cfg["gmail"]["max_delay"] = str(data.get("max_delay", 90))
        cfg["gmail"]["default_position"] = data.get("default_position", "")

        with open(config_path, "w") as f:
            cfg.write(f)

        return jsonify({"message": "Configuration saved successfully."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/upload", methods=["POST"])
def upload_file():
    file_type = request.form.get("type")
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    filename = file.filename
    
    # Restrict filenames depending on type
    if file_type == "xlsx":
        if not (filename.endswith(".xlsx") or filename.endswith(".csv")):
            return jsonify({"error": "Only .xlsx and .csv files are supported"}), 400
        # Save as original or custom name, let's keep it safe
        filename = secure_filename(filename)
        save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(save_path)
        return jsonify({"message": f"Data file '{filename}' uploaded successfully.", "filename": filename})

    elif file_type in ("resume", "cover_letter"):
        if not filename.endswith(".pdf"):
            return jsonify({"error": "Only PDF files are supported"}), 400
        filename = secure_filename(filename)
        save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(save_path)

        # Automatically update config.ini
        cfg = configparser.ConfigParser()
        cfg.read(config_path)
        if "gmail" not in cfg:
            cfg["gmail"] = {}
        
        config_key = "resume_path" if file_type == "resume" else "cover_letter_path"
        cfg["gmail"][config_key] = filename
        with open(config_path, "w") as f:
            cfg.write(f)

        return jsonify({"message": f"Document '{filename}' uploaded and configured.", "filename": filename})

    return jsonify({"error": "Invalid upload type"}), 400

@app.route("/api/start", methods=["POST"])
def start_sending():
    global state
    if state["status"] == "running":
        return jsonify({"error": "An application run is already in progress."}), 400

    data = request.json or {}
    xlsx_file = data.get("xlsx_file", "")
    
    # Resolve absolute path for emails file
    if not xlsx_file:
        # Scan folder for a default emails.xlsx or emails.csv
        if os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], "emails.csv")):
            xlsx_file = "emails.csv"
        elif os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], "emails.xlsx")):
            xlsx_file = "emails.xlsx"
        else:
            return jsonify({"error": "No recipient file found. Please upload one first."}), 400

    xlsx_path = os.path.join(app.config['UPLOAD_FOLDER'], xlsx_file)
    if not os.path.exists(xlsx_path):
        return jsonify({"error": f"File '{xlsx_file}' does not exist on server."}), 400

    dry_run = data.get("dry_run", False)
    limit = int(data.get("limit", 0))
    position = data.get("position", "")

    # Reset and start the thread
    with state_lock:
        state["status"] = "running"
        state["total"] = 0
        state["sent"] = 0
        state["skipped"] = 0
        state["failed"] = 0
        state["logs"] = []
        state["records"] = []
        state["stop_requested"] = False

    t = threading.Thread(
        target=email_sender_worker, 
        args=(xlsx_path, dry_run, limit, position),
        daemon=True
    )
    t.start()

    return jsonify({"message": "Background job started successfully."})

@app.route("/api/stop", methods=["POST"])
def stop_sending():
    global state
    with state_lock:
        state["stop_requested"] = True
    add_log("Stop requested by user. Waiting for current operation to finish...")
    return jsonify({"message": "Stop signal sent to background task."})

@app.route("/api/status", methods=["GET"])
def get_status():
    with state_lock:
        return jsonify(state)

if __name__ == "__main__":
    print("Starting Auto-Job-Applier Web Application on http://127.0.0.1:5000")
    app.run(debug=True, host="127.0.0.1", port=5000)
