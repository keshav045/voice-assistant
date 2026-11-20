# Deploying Nexus Voice Assistant to Streamlit Cloud

This guide walks you through deploying your **Nexus AI Voice Assistant** to **Streamlit Community Cloud** (free, fast, and globally accessible).

---

## 1. Test Locally First

You can run and test the Streamlit app locally at any time:

```powershell
backend\.venv\Scripts\streamlit.exe run streamlit_app.py
```

This will launch the app in your browser at:
`http://localhost:8501`

### What You Can Do in the Streamlit UI:
- **Voice Input**: Click the microphone icon under **Voice Input**, speak your command, and click stop. The audio is automatically transcribed using OpenAI Whisper.
- **Chat Input**: Type messages, math expressions, and tool requests.
- **Auto-Speech**: The assistant speaks back using OpenAI TTS-1 with your selected voice.
- **Tool Launcher**: YouTube, WhatsApp, calculations, email composer, and web search execute with visual status badges and links to open in a new tab.
- **Conversation Sessions**: Create new conversations, switch between previous chats, and clear history.

---

## 2. Deploy to Streamlit Community Cloud (Step-by-Step)

### Step 1: Sign in to Streamlit
1. Go to [share.streamlit.io](https://share.streamlit.io/).
2. Sign in with your GitHub account (`keshav045`).

### Step 2: Create a New App
1. Click the **"New app"** button.
2. Select:
   - **Repository**: `keshav045/voice-assistant`
   - **Branch**: `main`
   - **Main file path**: `streamlit_app.py`
   - **App URL**: Choose a custom subdomain (e.g., `nexus-voice-assistant.streamlit.app`).

---

### Step 3: Configure Cloud Secrets (Environment Variables)

Before clicking Deploy, click **"Advanced settings"** (or go to **App Settings > Secrets** after deploying):

Add your environment variables into the **Secrets** text box in TOML format:

```toml
OPENAI_API_KEY = "sk-proj-your-openai-api-key-here"
OPENAI_MODEL = "gpt-4o"
OPENAI_TTS_VOICE = "alloy"

# Google Cloud OAuth 2.0 (for connected Gmail sending)
GOOGLE_CLIENT_ID = "your-client-id.apps.googleusercontent.com"
GOOGLE_CLIENT_SECRET = "your-google-client-secret"

# Fallback SMTP Email (Optional)
SENDER_EMAIL = "your-email@gmail.com"
SENDER_APP_PASSWORD = "xxxx xxxx xxxx xxxx"

# LiveKit Cloud (Optional, for WebRTC streaming)
LIVEKIT_URL = "wss://your-project.livekit.cloud"
LIVEKIT_API_KEY = "your-key"
LIVEKIT_API_SECRET = "your-secret"
```

---

### Step 4: Click "Deploy!"
1. Click **Deploy!**.
2. Streamlit Cloud will read `requirements.txt`, install dependencies, and launch your voice assistant app.
3. Your app will be live at:
   `https://nexus-voice-assistant.streamlit.app`

---

## 3. When You Are Ready to Push to Git

*(As requested, no git push will be made until you decide).*

When you are ready to upload this to GitHub for Streamlit Cloud deployment, simply tell me or run:

```powershell
git add streamlit_app.py .streamlit/ requirements.txt DEPLOY_STREAMLIT.md
git commit -m "feat(streamlit): add Streamlit Cloud deployment app and configuration"
git push origin main
```
