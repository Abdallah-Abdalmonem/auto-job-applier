# Deployment Guide: PythonAnywhere (Multi-User)

This guide explains how to deploy your Auto-Job-Applier web dashboard on **PythonAnywhere** so that it is accessible online for any user.

---

## 🛠️ Step-by-Step Deployment

### 1. Create a PythonAnywhere Account
- Register for a free account at [pythonanywhere.com](https://www.pythonanywhere.com).

### 2. Clone your Repository
- On your PythonAnywhere dashboard, go to the **Consoles** tab and open a new **Bash Console**.
- Run the following command to clone your GitHub repository:
  ```bash
  git clone https://github.com/Abdallah-Abdalmonem/auto-job-applier.git
  ```

### 3. Create a Virtual Environment & Install Dependencies
- Inside the Bash Console, navigate to the project directory and set up a Python virtual environment:
  ```bash
  cd auto-job-applier
  mkvirtualenv --python=/usr/bin/python3.10 auto-applier-env
  ```
- Install the required packages listed in `requirements.txt`:
  ```bash
  pip install -r requirements.txt
  ```

### 4. Configure the PythonAnywhere Web App
- Go to the **Web** tab on the PythonAnywhere dashboard.
- Click **Add a new web app**.
- Choose **Manual Configuration** (Do NOT choose "Flask" here; manual configuration lets you link your existing virtualenv and files).
- Select **Python 3.10** as the version.
- Under the **Virtualenv** section of the Web tab, enter the path:
  `/home/<your_username>/.virtualenvs/auto-applier-env`
- Under **Code** section, set:
  - **Source code:** `/home/<your_username>/auto-job-applier`
  - **Working directory:** `/home/<your_username>/auto-job-applier`
- Under the **WSGI configuration file** section, click the link to edit the file.
- Delete all default contents of the file and paste the following:
  ```python
  import sys
  import os

  # Add project path to sys.path
  project_home = '/home/<your_username>/auto-job-applier'
  if project_home not in sys.path:
      sys.path = [project_home] + sys.path

  os.chdir(project_home)

  # Import Flask app and rename to 'application' for WSGI compatibility
  from app import app as application
  ```
  *(Remember to replace `<your_username>` with your actual PythonAnywhere username!)*
- Click **Save**.

### 5. Reload and Visit
- Go back to the **Web** tab.
- Click the green **Reload** button at the top.
- Click your web app URL (e.g., `http://<your_username>.pythonanywhere.com`) to launch your live dashboard!
- **Done!** Any user can now visit your link, type in their own email details, and drag-and-drop their own contacts sheet, resume, and cover letter directly from their browser.
