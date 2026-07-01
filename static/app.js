// ==========================================================================
// Auto Job Applier JavaScript Control Logic (Redesigned)
// ==========================================================================

let activeFileNames = {
    xlsx: "",
    resume: "",
    cover_letter: ""
};

let pollingInterval = null;
let lastLogLength = 0;

document.addEventListener("DOMContentLoaded", () => {
    // 1. Initial Load of Config
    loadConfig();

    // 2. Form Submit Intercept
    const configForm = document.getElementById("config-form");
    configForm.addEventListener("submit", (e) => {
        e.preventDefault();
        saveConfig();
    });

    // 3. Initialize Drag & Drop Events for Upload Card Wrapper Zones
    setupDragAndDrop("xlsx-zone", "xlsx");
    setupDragAndDrop("resume-zone", "resume");
    setupDragAndDrop("cover-zone", "cover_letter");

    // 4. Start checking status right away to resume UI if task is already running on server
    checkServerStatus();
    pollingInterval = setInterval(checkServerStatus, 1200);
});

// Helper: Show custom visual toast message
function showToast(message, type = "info") {
    const container = document.getElementById("toast-container");
    if (!container) return;

    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;
    
    let iconClass = "fa-solid fa-circle-info";
    if (type === "success") iconClass = "fa-solid fa-circle-check";
    if (type === "error") iconClass = "fa-solid fa-circle-exclamation";
    
    toast.innerHTML = `
        <i class="${iconClass}"></i>
        <span>${message}</span>
    `;

    container.appendChild(toast);

    // Auto fadeout and remove
    setTimeout(() => {
        toast.classList.add("fade-out");
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

// Helper: Toggle app password visibility
function togglePasswordVisibility() {
    const passwordInput = document.getElementById("app_password");
    const eyeIcon = document.getElementById("toggle-eye");
    if (passwordInput.type === "password") {
        passwordInput.type = "text";
        eyeIcon.classList.remove("fa-eye");
        eyeIcon.classList.add("fa-eye-slash");
    } else {
        passwordInput.type = "password";
        eyeIcon.classList.remove("fa-eye-slash");
        eyeIcon.classList.add("fa-eye");
    }
}

// ── 1. CONFIGURATION APIs ──────────────────────────────────────────────────

async function loadConfig() {
    try {
        const response = await fetch("/api/config");
        if (!response.ok) throw new Error("Could not fetch configurations.");
        const data = await response.json();
        
        document.getElementById("sender_email").value = data.sender_email || "";
        document.getElementById("sender_name").value = data.sender_name || "";
        document.getElementById("app_password").value = data.app_password || "";
        document.getElementById("min_delay").value = data.min_delay || "30";
        document.getElementById("max_delay").value = data.max_delay || "90";
        document.getElementById("default_position").value = data.default_position || "";

        // Update filenames UI labels if loaded from config
        if (data.resume_path) {
            activeFileNames.resume = data.resume_path;
            document.getElementById("resume-filename").innerHTML = `<span class="uploaded-badge"><i class="fa-solid fa-check"></i> ${data.resume_path}</span>`;
        }
        if (data.cover_letter_path) {
            activeFileNames.cover_letter = data.cover_letter_path;
            document.getElementById("cover-filename").innerHTML = `<span class="uploaded-badge"><i class="fa-solid fa-check"></i> ${data.cover_letter_path}</span>`;
        }
    } catch (err) {
        console.error("Config load error:", err);
    }
}

async function saveConfig() {
    const saveBtn = document.getElementById("save-config-btn");
    const originalContent = saveBtn.innerHTML;

    const payload = {
        sender_email: document.getElementById("sender_email").value.trim(),
        sender_name: document.getElementById("sender_name").value.trim(),
        app_password: document.getElementById("app_password").value.trim(),
        min_delay: parseInt(document.getElementById("min_delay").value) || 30,
        max_delay: parseInt(document.getElementById("max_delay").value) || 90,
        default_position: document.getElementById("default_position").value.trim(),
        resume_path: activeFileNames.resume,
        cover_letter_path: activeFileNames.cover_letter
    };

    try {
        saveBtn.disabled = true;
        saveBtn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Saving Settings...`;

        const response = await fetch("/api/config", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        if (!response.ok) throw new Error("Could not save settings.");
        
        showToast("SMTP settings saved successfully!", "success");
        saveBtn.innerHTML = `<i class="fa-solid fa-check"></i> Settings Saved!`;
        
        setTimeout(() => {
            saveBtn.innerHTML = originalContent;
            saveBtn.disabled = false;
        }, 1500);
    } catch (err) {
        saveBtn.innerHTML = originalContent;
        saveBtn.disabled = false;
        showToast("Failed to save settings: " + err.message, "error");
    }
}

// ── 2. DRAG AND DROP UPLOADS ────────────────────────────────────────────────

function setupDragAndDrop(zoneId, fileType) {
    const zone = document.getElementById(zoneId);
    if (!zone) return;
    
    // Prevent defaults
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        zone.addEventListener(eventName, preventDefaults, false);
    });

    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    // Add drag effects
    ['dragenter', 'dragover'].forEach(eventName => {
        zone.addEventListener(eventName, () => zone.classList.add('dragover'), false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        zone.addEventListener(eventName, () => zone.classList.remove('dragover'), false);
    });

    // Handle dropped files
    zone.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        const files = dt.files;
        if (files.length) {
            uploadFile(files[0], fileType);
        }
    });
}

function uploadSelectedFile(inputElement, fileType) {
    if (inputElement.files && inputElement.files.length > 0) {
        uploadFile(inputElement.files[0], fileType);
    }
}

async function uploadFile(file, type) {
    const zoneLabels = {
        xlsx: "xlsx-filename",
        resume: "resume-filename",
        cover_letter: "cover-filename"
    };
    const labelId = zoneLabels[type];
    const labelElement = document.getElementById(labelId);
    if (!labelElement) return;

    const originalText = labelElement.innerText;
    labelElement.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Uploading ${file.name}...`;

    const formData = new FormData();
    formData.append("file", file);
    formData.append("type", type);

    try {
        const response = await fetch("/api/upload", {
            method: "POST",
            body: formData
        });
        const result = await response.json();

        if (!response.ok) throw new Error(result.error || "Upload failed.");

        activeFileNames[type] = result.filename;
        labelElement.innerHTML = `<span class="uploaded-badge"><i class="fa-solid fa-check"></i> ${result.filename}</span>`;
        showToast(`Uploaded ${result.filename} successfully!`, "success");
    } catch (err) {
        labelElement.innerText = originalText;
        showToast("Upload Error: " + err.message, "error");
    }
}

// ── 3. JOB CONTROLLER ACTIONS ──────────────────────────────────────────────

async function startExecution() {
    const startBtn = document.getElementById("start-btn");
    const dryRun = document.getElementById("dry_run_check").checked;
    const limit = parseInt(document.getElementById("email_limit").value) || 0;
    const position = document.getElementById("default_position").value.trim();

    const payload = {
        xlsx_file: activeFileNames.xlsx,
        dry_run: dryRun,
        limit: limit,
        position: position
    };

    try {
        startBtn.disabled = true;
        const response = await fetch("/api/start", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        const result = await response.json();
        
        if (!response.ok) throw new Error(result.error);

        showToast("Job application process initiated!", "info");

        // Reveal the tracking panel
        document.getElementById("progress-section").classList.remove("hidden");
        document.getElementById("start-btn").classList.add("hidden");
        document.getElementById("stop-btn").classList.remove("hidden");
        document.getElementById("stop-btn").disabled = false;
        document.getElementById("stop-btn").innerHTML = `<i class="fa-solid fa-circle-stop"></i> Stop Sending`;

        lastLogLength = 0;
        checkServerStatus();
    } catch (err) {
        startBtn.disabled = false;
        showToast("Could not start job: " + err.message, "error");
    }
}

async function stopExecution() {
    const stopBtn = document.getElementById("stop-btn");
    stopBtn.disabled = true;
    stopBtn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Stopping...`;

    try {
        await fetch("/api/stop", { method: "POST" });
        showToast("Stop signal sent. Terminating...", "warning");
    } catch (err) {
        console.error("Stop error:", err);
    }
}

// ── 4. STATUS POLLING AND UI UPDATES ──────────────────────────────────────

async function checkServerStatus() {
    try {
        const response = await fetch("/api/status");
        if (!response.ok) return;
        const state = await response.json();

        updateProgressUI(state);
    } catch (err) {
        console.error("Status polling failed:", err);
        document.getElementById("server-status-badge").innerHTML = `<span class="pulse-dot" style="background-color: var(--danger);"></span> Server Offline`;
    }
}

function updateProgressUI(state) {
    const startBtn = document.getElementById("start-btn");
    const stopBtn = document.getElementById("stop-btn");
    const progressSection = document.getElementById("progress-section");
    const statusBadge = document.getElementById("task-status-text");

    document.getElementById("server-status-badge").innerHTML = `<span class="pulse-dot"></span> Server Connected`;

    if (state.status !== "idle") {
        progressSection.classList.remove("hidden");
    }

    if (state.status === "running") {
        statusBadge.innerText = "RUNNING";
        statusBadge.style.background = "var(--primary-glow)";
        startBtn.classList.add("hidden");
        stopBtn.classList.remove("hidden");
        if (state.stop_requested) {
            stopBtn.disabled = true;
            stopBtn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Stopping...`;
        }
    } else if (state.status === "completed") {
        statusBadge.innerText = "FINISHED";
        statusBadge.style.background = "var(--success)";
        startBtn.classList.remove("hidden");
        startBtn.disabled = false;
        stopBtn.classList.add("hidden");
    } else {
        statusBadge.innerText = "IDLE";
        statusBadge.style.background = "var(--text-muted)";
        startBtn.classList.remove("hidden");
        startBtn.disabled = false;
        stopBtn.classList.add("hidden");
    }

    // Counters
    document.getElementById("stat-total").innerText = state.total;
    document.getElementById("stat-sent").innerText = state.sent;
    document.getElementById("stat-skipped").innerText = state.skipped;
    document.getElementById("stat-failed").innerText = state.failed;

    // Progress percentage
    const completedCount = state.sent + state.skipped + state.failed;
    const percent = state.total > 0 ? Math.round((completedCount / state.total) * 100) : 0;
    
    document.getElementById("progress-bar-fill").style.width = `${percent}%`;
    document.getElementById("progress-percent-lbl").innerText = `${percent}%`;

    // Console logs rendering
    const consoleBox = document.getElementById("console-logs");
    if (state.logs && state.logs.length !== lastLogLength) {
        consoleBox.innerHTML = state.logs.map(logLine => {
            if (logLine.includes("SUCCESS:") || logLine.includes("successfully")) {
                return `<span style="color: var(--success); font-weight: 500;">${logLine}</span>`;
            } else if (logLine.includes("FAILED") || logLine.includes("ERROR:")) {
                return `<span style="color: var(--danger); font-weight: 500;">${logLine}</span>`;
            } else if (logLine.includes("SKIPPED") || logLine.includes("WARNING:")) {
                return `<span style="color: var(--warning); font-weight: 500;">${logLine}</span>`;
            }
            return logLine;
        }).join("\n");
        
        consoleBox.scrollTop = consoleBox.scrollHeight;
        lastLogLength = state.logs.length;
    }

    // Recipients datagrid
    const tbody = document.getElementById("recipients-tbody");
    if (state.records && state.records.length > 0) {
        tbody.innerHTML = state.records.map(record => {
            const statusClass = record.send_status || "pending";
            const badgeLabel = record.send_status ? record.send_status.toUpperCase() : "PENDING";
            const errTooltip = record.error ? ` title="${record.error}" style="cursor:help; border-bottom: 1px dotted var(--danger);"` : "";
            
            return `
                <tr>
                    <td>${record.email}</td>
                    <td>${record.company || '<span style="color:var(--text-muted);">—</span>'}</td>
                    <td>${record.position || '<span style="color:var(--text-muted);">—</span>'}</td>
                    <td>
                        <span class="status-badge ${statusClass}"${errTooltip}>
                            ${badgeLabel}
                        </span>
                    </td>
                </tr>
            `;
        }).join("");
    } else {
        tbody.innerHTML = `<tr><td colspan="4" style="text-align:center; color:var(--text-muted); padding:2rem 0;">No recipients loaded yet.</td></tr>`;
    }
}
