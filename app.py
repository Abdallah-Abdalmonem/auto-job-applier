import os
import uuid
import threading
import time
import random
import smtplib
import ssl
from datetime import timedelta
from pathlib import Path
from email.mime.multipart import MIMEMultipart
from flask import Flask, request, jsonify, render_template, session
from werkzeug.utils import secure_filename

# Import helper functions from the original script
from send_applications import load_workbook_data, build_email, send_email, should_skip, attach_file

app = Flask(__name__, template_folder="templates", static_folder="static")

# Production safety: use a static secret key so session cookies remain valid across server reloads
app.secret_key = "auto-job-applier-saas-secure-key-9988"
app.permanent_session_lifetime = timedelta(days=30)

app.config['UPLOAD_FOLDER'] = os.path.dirname(os.path.abspath(__file__))
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB limit

# Shared application states, keyed by session_id
user_states = {}
user_states_lock = threading.Lock()

def get_user_state(session_id):
    with user_states_lock:
        if session_id not in user_states:
            user_states[session_id] = {
                "status": "idle",
                "total": 0,
                "sent": 0,
                "skipped": 0,
                "failed": 0,
                "logs": [],
                "records": [],
                "stop_requested": False
            }
        return user_states[session_id]

def add_user_log(session_id, msg):
    timestamp = time.strftime('%H:%M:%S')
    with user_states_lock:
        state = get_user_state(session_id)
        state["logs"].append(f"[{timestamp}] {msg}")

def update_user_status(session_id, status):
    with user_states_lock:
        state = get_user_state(session_id)
        state["status"] = status

@app.before_request
def ensure_session_id():
    session.permanent = True
    if "session_id" not in session:
        session["session_id"] = str(uuid.uuid4())
    if "config" not in session:
        session["config"] = {
            "sender_email": "",
            "sender_name": "",
            "app_password": "",
            "resume_path": "",
            "cover_letter_path": "",
            "xlsx_file": "",
            "min_delay": "30",
            "max_delay": "90",
            "default_position": "Software Engineer"
        }

def email_sender_worker(session_id, user_config, xlsx_path, dry_run, limit, position_override):
    # Reset and configure user state
    with user_states_lock:
        state = get_user_state(session_id)
        state["status"] = "running"
        state["logs"] = []
        state["sent"] = 0
        state["skipped"] = 0
        state["failed"] = 0
        state["stop_requested"] = False
        state["records"] = []
        state["total"] = 0

    try:
        add_user_log(session_id, "Starting background sender task...")
        
        # Load configuration passed from route context
        sender_email = user_config.get("sender_email", "").strip()
        app_password = user_config.get("app_password", "").strip()
        sender_name = user_config.get("sender_name", "").strip()
        resume_name = user_config.get("resume_path", "").strip()
        cover_letter_name = user_config.get("cover_letter_path", "").strip()
        min_delay = float(user_config.get("min_delay", 30))
        max_delay = float(user_config.get("max_delay", 90))
        default_position = user_config.get("default_position", "").strip()

        add_user_log(session_id, f"Loading recipient data...")
        records = load_workbook_data(xlsx_path)
        total = len(records)
        
        with user_states_lock:
            state = get_user_state(session_id)
            state["total"] = total
            state["records"] = [
                {**r, "send_status": "pending", "error": ""} for r in records
            ]

        add_user_log(session_id, f"Successfully loaded {total} contacts.")

        body_template = """{salutation},

I am writing to express my interest in the {position} position{company_at}. I believe my skills and experience make me a strong candidate for this role.

I have attached my resume and cover letter for your review. I would welcome the opportunity to discuss how I can contribute to your team.

Thank you for your time and consideration.

Best regards,
{sender_name}
""".replace("{sender_name}", sender_name)

        smtp_server = None
        if not dry_run:
            add_user_log(session_id, "Connecting to Gmail SMTP server (smtp.gmail.com:465)...")
            context = ssl.create_default_context()
            try:
                smtp_server = smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context)
                smtp_server.login(sender_email, app_password)
                add_user_log(session_id, "SMTP authenticated successfully. Ready to send.")
            except Exception as e:
                add_user_log(session_id, f"SMTP CONNECTION ERROR: {str(e)}")
                add_user_log(session_id, "Please check your email and App Password configuration.")
                update_user_status(session_id, "completed")
                return

        for i, record in enumerate(records):
            # Check stop requested
            with user_states_lock:
                state = get_user_state(session_id)
                stop_requested = state["stop_requested"]

            if stop_requested:
                add_user_log(session_id, "STOP SIGN RECEIVED: Terminating execution early.")
                break

            email = record.get("email", "")
            company = record.get("company", "")
            position = record.get("position", "") or position_override or default_position or "open position"
            
            comp_display = company if company else "(no company)"
            add_user_log(session_id, f"[{i+1}/{total}] Processing email to '{email}' for position '{position}' at {comp_display}...")

            with user_states_lock:
                state = get_user_state(session_id)
                state["records"][i]["send_status"] = "processing"

            if should_skip(record):
                reason = record.get("status", "")
                if not reason:
                    if not email or "@" not in email:
                        reason = "missing or invalid email"
                    else:
                        reason = "skipped"
                add_user_log(session_id, f"  SKIPPED: {reason}")
                with user_states_lock:
                    state = get_user_state(session_id)
                    state["skipped"] += 1
                    state["records"][i]["send_status"] = "skipped"
                    state["records"][i]["error"] = reason
                continue

            # Build email message
            msg = build_email(sender_email, sender_name, email, company, position, body_template)

            # Resolve attachments inside user-specific directory
            user_dir = os.path.join(app.config['UPLOAD_FOLDER'], "uploads", session_id)
            if resume_name:
                resume_abs = os.path.join(user_dir, resume_name)
                if os.path.exists(resume_abs):
                    attach_file(msg, resume_abs)
                else:
                    add_user_log(session_id, f"  WARNING: Resume PDF not found on server.")

            if cover_letter_name:
                cover_abs = os.path.join(user_dir, cover_letter_name)
                if os.path.exists(cover_abs):
                    attach_file(msg, cover_abs)
                else:
                    add_user_log(session_id, f"  WARNING: Cover letter PDF not found on server.")

            with user_states_lock:
                state = get_user_state(session_id)
                sent_count = state["sent"]

            if dry_run:
                if sent_count == 0:
                    add_user_log(session_id, "--- DRY RUN PREVIEW (FIRST EMAIL) ---")
                    add_user_log(session_id, f"Subject: {msg['Subject']}")
                    body_text = ""
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain":
                            body_text = part.get_payload()
                            break
                    add_user_log(session_id, "Body:")
                    for line in body_text.splitlines():
                        add_user_log(session_id, f"  {line}")
                    attachments_list = [Path(p).name for p in [resume_name, cover_letter_name] if p]
                    add_user_log(session_id, f"Attachments: {attachments_list}")
                    add_user_log(session_id, "-------------------------------------")
                
                add_user_log(session_id, f"  [DRY RUN] Simulating email sent to {email}")
                with user_states_lock:
                    state = get_user_state(session_id)
                    state["sent"] += 1
                    state["records"][i]["send_status"] = "sent"
                continue

            # Actual send
            success = send_email(smtp_server, sender_email, email, msg)
            if success:
                add_user_log(session_id, f"  SUCCESS: Email sent to {email}")
                with user_states_lock:
                    state = get_user_state(session_id)
                    state["sent"] += 1
                    state["records"][i]["send_status"] = "sent"
            else:
                add_user_log(session_id, f"  FAILED to send to {email}")
                with user_states_lock:
                    state = get_user_state(session_id)
                    state["failed"] += 1
                    state["records"][i]["send_status"] = "failed"
                    state["records"][i]["error"] = "SMTP Error"

            # Get fresh sent counter
            with user_states_lock:
                state = get_user_state(session_id)
                sent_count = state["sent"]

            # Rate limit delay
            if i < total - 1 and (limit == 0 or sent_count < limit):
                delay = random.uniform(min_delay, max_delay)
                add_user_log(session_id, f"  Rate Limiting: waiting {delay:.1f}s before next email...")
                sleep_start = time.time()
                while time.time() - sleep_start < delay:
                    with user_states_lock:
                        state = get_user_state(session_id)
                        stop_requested = state["stop_requested"]
                    if stop_requested:
                        break
                    time.sleep(0.25)

            if limit > 0 and sent_count >= limit:
                add_user_log(session_id, f"Reached execution limit of {limit} sent emails. Stopping.")
                break

        if smtp_server:
            try:
                smtp_server.quit()
                add_user_log(session_id, "SMTP server connection closed.")
            except:
                pass

        add_user_log(session_id, "Background sender execution finished.")
        update_user_status(session_id, "completed")

    except Exception as e:
        add_user_log(session_id, f"CRITICAL WORKER ERROR: {str(e)}")
        update_user_status(session_id, "completed")

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/config", methods=["GET"])
def get_config():
    return jsonify(session.get("config", {}))

@app.route("/api/config", methods=["POST"])
def save_config():
    try:
        data = request.json or {}
        config = session.get("config", {})
        
        config["sender_email"] = data.get("sender_email", "").strip()
        config["sender_name"] = data.get("sender_name", "").strip()
        config["app_password"] = data.get("app_password", "").strip()
        config["min_delay"] = str(data.get("min_delay", 30))
        config["max_delay"] = str(data.get("max_delay", 90))
        config["default_position"] = data.get("default_position", "").strip()
        
        # Preserve or update file paths from payload if present
        if "resume_path" in data:
            config["resume_path"] = data.get("resume_path", "").strip()
        if "cover_letter_path" in data:
            config["cover_letter_path"] = data.get("cover_letter_path", "").strip()
        if "xlsx_file" in data:
            config["xlsx_file"] = data.get("xlsx_file", "").strip()
            
        session["config"] = config
        session.modified = True
        return jsonify({"message": "Configuration saved to browser session successfully."})
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

    filename = secure_filename(file.filename)
    session_id = session["session_id"]
    
    # Establish isolated upload folder
    user_dir = os.path.join(app.config['UPLOAD_FOLDER'], "uploads", session_id)
    os.makedirs(user_dir, exist_ok=True)
    
    # Clean checks depending on type
    if file_type == "xlsx":
        if not (filename.endswith(".xlsx") or filename.endswith(".csv")):
            return jsonify({"error": "Only .xlsx and .csv files are supported"}), 400
        save_path = os.path.join(user_dir, filename)
        file.save(save_path)
        
        # Save filename in user's session
        config = session.get("config", {})
        config["xlsx_file"] = filename
        session["config"] = config
        session.modified = True
        
        return jsonify({"message": f"Sheet '{filename}' uploaded successfully.", "filename": filename})

    elif file_type in ("resume", "cover_letter"):
        if not filename.endswith(".pdf"):
            return jsonify({"error": "Only PDF files are supported"}), 400
        save_path = os.path.join(user_dir, filename)
        file.save(save_path)

        # Update session
        config = session.get("config", {})
        config_key = "resume_path" if file_type == "resume" else "cover_letter_path"
        config[config_key] = filename
        session["config"] = config
        session.modified = True

        return jsonify({"message": f"Document '{filename}' uploaded successfully.", "filename": filename})

    return jsonify({"error": "Invalid upload type"}), 400

@app.route("/api/start", methods=["POST"])
def start_sending():
    session_id = session["session_id"]
    user_config = session.get("config", {})
    
    # Check if this user already has an active sender thread
    user_state = get_user_state(session_id)
    if user_state["status"] == "running":
        return jsonify({"error": "An application run is already in progress for this session."}), 400

    xlsx_file = user_config.get("xlsx_file", "")
    if not xlsx_file:
        return jsonify({"error": "No contacts file found. Please upload an Excel or CSV file first."}), 400

    user_dir = os.path.join(app.config['UPLOAD_FOLDER'], "uploads", session_id)
    xlsx_path = os.path.join(user_dir, xlsx_file)
    if not os.path.exists(xlsx_path):
        return jsonify({"error": "Contacts file not found. Please upload it again."}), 400

    data = request.json or {}
    dry_run = data.get("dry_run", False)
    limit = int(data.get("limit", 0))
    position = data.get("position", "")

    # Reset worker state safely
    with user_states_lock:
        state = get_user_state(session_id)
        state["status"] = "running"
        state["total"] = 0
        state["sent"] = 0
        state["skipped"] = 0
        state["failed"] = 0
        state["logs"] = []
        state["records"] = []
        state["stop_requested"] = False

    # Spawn thread passing copy of user configuration (safe context)
    t = threading.Thread(
        target=email_sender_worker, 
        args=(session_id, dict(user_config), xlsx_path, dry_run, limit, position),
        daemon=True
    )
    t.start()

    return jsonify({"message": "Background job started successfully."})

@app.route("/api/stop", methods=["POST"])
def stop_sending():
    session_id = session["session_id"]
    with user_states_lock:
        state = get_user_state(session_id)
        state["stop_requested"] = True
    add_user_log(session_id, "Stop signal triggered by user. Halting...")
    return jsonify({"message": "Stop signal sent to background task."})

@app.route("/api/status", methods=["GET"])
def get_status():
    session_id = session["session_id"]
    return jsonify(get_user_state(session_id))

if __name__ == "__main__":
    # Create the global uploads folder if missing
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], "uploads"), exist_ok=True)
    print("Starting Multi-User Auto-Job-Applier Web Application on http://127.0.0.1:5000")
    app.run(debug=True, host="127.0.0.1", port=5000)
