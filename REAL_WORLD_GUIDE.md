# Nexus Agentic AI Productivity Assistant — Real-World Daily Driver Guide

Welcome to **Nexus**, your personal, autonomous executive assistant designed specifically for real-world daily productivity on Windows 11.

Nexus is built to run locally on your workstation as a true daily driver—managing your tasks, inspecting your inbox, scheduling calendar events, capturing desktop screenshots, and speaking back to you in real-time.

---

## 🚀 1. One-Click Quick Start (Windows)

Nexus includes native one-click batch scripts so you never have to open multiple terminals:

### To Start Nexus:
Double-click:
```bat
start-nexus.bat
```
* **What happens automatically:**
  1. Starts the FastAPI Backend on `http://localhost:8000`
  2. Starts the Vite Web Executive Dashboard on `http://localhost:5173`
  3. Launches the Windows Desktop Companion daemon in the background
  4. Automatically opens your default web browser directly to `http://localhost:5173`

### To Stop Nexus:
Double-click:
```bat
stop-nexus.bat
```
* Safely halts all background daemons and frees ports `8000` and `5173`.

---

## 🔑 2. Setting Up Real Google Workspace Sync (Gmail & Calendar)

Nexus works **100% offline with curated local data** by default. To connect your actual personal or work **Gmail** and **Google Calendar**, follow this 5-minute setup:

### Step 1: Open Google Cloud Console
1. Navigate to [Google Cloud Console Credentials](https://console.cloud.google.com/apis/credentials).
2. Click **Create Project** and name it **"Nexus Assistant"**.

### Step 2: Enable the APIs
1. In the search bar at the top, search for **"Gmail API"** and click **Enable**.
2. Search for **"Google Calendar API"** and click **Enable**.

### Step 3: Configure the OAuth Consent Screen
1. In the left navigation, click **OAuth consent screen**.
2. Select **External** and click **Create**.
3. Fill in:
   * **App name**: `Nexus Assistant`
   * **User support email**: Your email
   * **Developer contact email**: Your email
4. Click **Save and Continue** through Scopes.
5. Under **Test users**, click **Add Users** and enter your personal Google email address.
6. Click **Save and Continue**.

### Step 4: Create OAuth 2.0 Credentials
1. Click **Credentials** in the left sidebar -> **Create Credentials** -> **OAuth client ID**.
2. Application type: **Web application**.
3. Name: `Nexus Desktop Client`.
4. Under **Authorized redirect URIs**, click **Add URI** and enter:
   ```text
   http://localhost:8000/api/v1/auth/google/callback
   ```
5. Click **Create**.
6. Copy your **Client ID** and **Client Secret**.

### Step 5: Add to `backend/.env`
Open `backend/.env` and paste your keys:
```env
GOOGLE_CLIENT_ID="your-client-id.apps.googleusercontent.com"
GOOGLE_CLIENT_SECRET="your-client-secret"
GOOGLE_REDIRECT_URI="http://localhost:8000/api/v1/auth/google/callback"
```

### Step 6: Connect in Nexus Dashboard
1. Launch Nexus with `start-nexus.bat`.
2. Go to the **Gmail** or **Calendar** tab and click **"Connect Google"**.
3. A secure Google sign-in window will open. Click **Allow**.
4. Nexus will display **🟢 Gmail Live / Calendar Live** and begin synchronizing your actual inbox and schedule!

> [!NOTE]
> All OAuth access and refresh tokens are encrypted on disk with Fernet AES-128-CBC encryption derived from your secret key. Nexus automatically refreshes expired tokens in the background.

---

## 🤖 3. OpenAI API Configuration

In `backend/.env`:
```env
OPENAI_API_KEY="sk-proj-your-key-here"
OPENAI_MODEL="gpt-4o"
OPENAI_VOICE_MODEL="gpt-4o-realtime-preview"
```
* With your OpenAI key, Nexus orchestrates multi-agent tasks, generates intelligent email summaries, drafts responses, and computes semantic vector embeddings.

---

## 🎙️ 4. Daily Operations & Real-World Features

### 1. Hands-Free Voice Conversation
* Navigate to the **Voice Assistant** tab.
* Click the glowing **Voice Orb** or press your microphone.
* Speak naturally: *"What's on my schedule tomorrow?", "Summarize my unread emails", "Create a task to finish the presentation by 5 PM"*.
* **Live Speech Output (TTS)**: Nexus speaks its answer aloud using your system's natural browser speech engine. You can toggle audio voice feedback on or off at any time using the **TTS Voice: ON / MUTED** button.

### 2. Omni-Command Center (`Ctrl+K` or Command Bar)
* From any tab, switch to the **Command Center** to see your consolidated executive dashboard:
  * Overdue and high-priority tasks
  * Today's agenda and calendar timeline
  * Email inbox preview and draft composer
  * Live Windows hardware telemetry (CPU, RAM, and Disk)
  * System health and audit activity feed

### 3. Windows Desktop Companion
* **Application Launcher**: Safely launch daily tools (*Chrome, VS Code, Windows Terminal, File Explorer, Notepad, Calculator, Task Manager*) with approval guardrails.
* **Instant Screenshots**: Click **"📸 Screenshot"** to capture your active desktop screen. The companion saves high-res PNG files to `desktop-companion/screenshots/` and displays a thumbnail preview immediately in your dashboard.
* **Smart File Search**: Quickly locate documents, PDFs, code files, and spreadsheets across your `Documents`, `Downloads`, `Desktop`, and project workspace.
* **Live Hardware Telemetry**: Monitored via native `psutil` (accurate CPU %, RAM %, and Disk capacity).

### 4. Background Scheduler & Desktop Notifications
* When you set a reminder (e.g. *"Remind me to call Alex at 4:30 PM"*), the Nexus background scheduler evaluates it every 10 seconds.
* When the reminder is due, Nexus triggers a native **Windows Notification Toast** directly on your desktop, accompanied by an in-app alert banner.

### 5. Approval Gates for High-Risk Actions
Nexus follows an uncompromising **Safety First** philosophy:
* Safe read operations (searching emails, viewing calendar, reading files, checking hardware metrics) run instantly.
* Sensitive actions (**sending an email**, **deleting a task**, **scheduling or deleting a calendar meeting**, **launching an app**) pause and present an explicit approval gate before execution.

---

## 🛠️ 5. Troubleshooting & Health Verification

| Issue | Resolution |
| :--- | :--- |
| **Port 8000 or 5173 already in use** | Run `stop-nexus.bat` to forcefully terminate lingering processes, then re-run `start-nexus.bat`. |
| **Microphone not working** | Ensure your browser has permission to access microphone on `http://localhost:5173`. Check browser site settings. |
| **Google Sign-In shows "Access Blocked: App has not completed verification"** | Since your Google Cloud Project is in Testing mode, ensure your Google email address is added under **OAuth consent screen > Test users**. |
| **Database migration status** | The SQLite database `nexus.db` is initialized and auto-migrates all tables on launch. |

---

## 🔒 6. Security Guarantees
* **Zero Arbitrary Execution**: Nexus cannot run raw bash/powershell strings or destructive disk commands. All desktop actions are strictly restricted to an approved whitelist.
* **Encrypted Credentials**: Stored OAuth tokens are symmetrically encrypted before persistence.
* **Local-First Architecture**: Your tasks, notes, semantic memory, and logs reside on your local machine.
