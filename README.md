# Nexus AI — Production Voice Assistant

An asynchronous, voice-first intelligent assistant featuring real-time conversational intelligence, desktop & browser application automation, automated WhatsApp messaging, web search, AST-safe calculation, Python execution, interruptible speech synthesis, and session-grouped personal chat history.

Built with Python 3.11+, FastAPI, SQLite (WAL mode), and a vanilla HTML5/ES6 web interface (zero Node.js/npm dependencies).

---

## Key Features

- **Voice-First & Instant Speech Cancellation**:
  - Live microphone streaming via Web Speech API with the mic integrated directly inside the input bar.
  - Floating **"Stop Speaking"** button with immediate audio cancellation on click, `Escape` key, or new user interaction.
- **App & Website Launcher (`open_app`)**:
  - Launches desktop applications (e.g., Notepad, Calculator, Explorer).
  - Automatically launches web services (YouTube, WhatsApp Web, LinkedIn, Gmail, Spotify, GitHub) with intelligent search queries (e.g., *"open youtube and play lo-fi hip hop"*).
  - Explicit browser targeting (`Chrome`, `Microsoft Edge`) and automatic fallback to default browser if native apps are not installed.
- **WhatsApp Contact Automation (`send_whatsapp_message`)**:
  - Search contact names in WhatsApp desktop or web (`web.whatsapp.com`).
  - Automated message typing via clipboard buffer and background thread execution to prevent UI latency.
  - Configurable `auto_send` flag to review before sending or dispatch immediately.
- **Real-Time Web Search & Computation**:
  - Live DuckDuckGo web search for current events, facts, and live information.
  - AST-safe arithmetic calculator and sandboxed Python REPL for complex computational logic.
- **Session-Grouped Personal Chat History & Authentication**:
  - User registration and login with salted SHA-256 password hashing and secure token sessions.
  - Left-sidebar conversation manager grouping interactions by session ID, displaying original query titles, turn counts, and relative timestamps.
  - One-click historical conversation resumption and session deletion.
- **Production Hardened & Containerized**:
  - SQLite with Write-Ahead Logging (`WAL`), `foreign_keys=ON`, and `30.0s` busy timeout.
  - Non-root multi-stage `Dockerfile` with automated `HEALTHCHECK` and persistent volume mounts.
  - Production launcher `run_server.py` supporting dynamic port binding (`$PORT`) for cloud providers (Render, Railway, Fly.io, Cloud Run).

---

## System Architecture

```
voice-assistant/
├── agent/
│   ├── main.py              # FastAPI server, REST routes, static file serving, and agent turn processing
│   ├── cli.py               # Interactive terminal voice assistant
│   ├── voice.py             # Microphone capture and TTS engine
│   ├── session.py           # Multi-turn conversation buffer with auto-summarization
│   ├── safety.py            # Gated confirmation, prompt-injection defenses, argument validation
│   ├── prompts.py           # System prompts and tool usage instructions
│   └── tools/
│       ├── launcher.py      # App & browser launcher (YouTube, LinkedIn, Gmail, Spotify, etc.)
│       ├── whatsapp.py      # WhatsApp contact search and automated messaging
│       ├── search.py        # Live DuckDuckGo web search
│       ├── calc.py          # AST-safe mathematical calculator
│       ├── python_repl.py   # Sandboxed Python code execution
│       ├── calendar.py      # Calendar event tools
│       ├── email.py         # Email drafting tools
│       ├── tasks.py         # Task management tools
│       └── memory_tools.py  # User fact retention and recall
├── db/
│   ├── schema.sql           # SQLite schema definitions
│   └── models.py            # WAL mode connection manager, auth, and session-grouped history CRUD
├── web/
│   ├── index.html           # Modern voice interface with left sidebar and integrated mic
│   ├── app.js               # Web Speech API, session history loader, and speech cancellation
│   └── style.css            # Dark theme responsive design
├── tests/
│   ├── test_agent.py        # Pipeline & tool execution tests
│   ├── test_auth_and_history.py # Auth, health check probes, and session grouping tests
│   ├── test_launcher.py     # App launcher and browser fallback tests
│   ├── test_whatsapp.py     # WhatsApp messaging automation tests
│   ├── test_voice.py        # Voice pipeline and audio transcription tests
│   └── test_phase1.py       # Math calculator and session tests
├── Dockerfile               # Production multi-platform container image (appuser, curl healthcheck)
├── docker-compose.yml       # Production container orchestration with persistent volume
├── run_server.py            # Production server launcher with dynamic port binding
├── run_voice.py             # Terminal voice assistant launcher
├── requirements.txt         # Production Python dependencies
├── DEPLOYMENT.md            # Comprehensive cloud and on-premise deployment guide
└── .env.example             # Documented configuration template
```

---

## Quickstart Guide

### 1. Installation

Clone the repository and install dependencies:

```bash
git clone <repository-url>
cd voice-assistant

# Create virtual environment
python -m venv .venv

# Activate environment (Windows)
.venv\Scripts\activate
# Or on Linux/macOS:
source .venv/bin/activate

# Install requirements
pip install -r requirements.txt
```

### 2. Configure Environment

Copy `.env.example` to `.env` and configure your OpenAI API key:

```bash
cp .env.example .env
```

Edit `.env`:
```ini
OPENAI_API_KEY=sk-your-openai-api-key
OPENAI_MODEL=gpt-4o
PORT=8000
HOST=0.0.0.0
DB_PATH=voice_assistant.db
```

### 3. Launch Web Assistant

```bash
python run_server.py
```

Open **`http://localhost:8000`** in your browser.
- Click the microphone inside the input bar to speak.
- Use the **"Stop Speaking"** button to immediately interrupt playback.
- Sign up or log in via the left sidebar to save and organize chat sessions.

### 4. Run Terminal Voice Assistant (Optional)

```bash
python run_voice.py
```
- Press and hold **Spacebar** to speak, release to submit.

---

## Verification & Testing

Execute the automated test suite across all subsystems:

```bash
pytest tests/ -v
```

All 45+ unit and integration tests run in under 30 seconds, testing:
- Application launcher and browser fallback (`test_launcher.py`)
- WhatsApp contact search and automated dispatch (`test_whatsapp.py`)
- Authentication, health checks, and session-grouped history (`test_auth_and_history.py`)
- Tool execution and agentic reasoning (`test_agent.py`)
- Voice synthesis and transcription cleanup (`test_voice.py`)
- Calculator and memory persistence (`test_phase1.py`)

---

## Production Deployment

### Docker Compose
```bash
docker-compose up -d --build
```

### Cloud Providers
Refer to [DEPLOYMENT.md](DEPLOYMENT.md) for step-by-step instructions for:
- **Docker & Docker Compose**
- **Render** (Web Service via Dockerfile)
- **Railway** (Automated GitHub Deployment)
- **Fly.io** (`fly launch` with persistent volume)
- **Linux VPS (Ubuntu/Debian)** with Systemd + Nginx SSL Reverse Proxy

---

## API Endpoints Summary

| Endpoint | Method | Description |
|---|---|---|
| `/health` | `GET` | Container & orchestrator health check probe |
| `/api/health` | `GET` | Diagnostic status (database, model readiness) |
| `/api/chat` | `POST` | Process conversation turn with active tools |
| `/api/history` | `GET` | List grouped chat sessions or turns |
| `/api/history/{id}` | `GET` | Get all turns for a specific chat session |
| `/api/history/{id}` | `DELETE` | Delete a single turn or an entire session |
| `/api/auth/signup` | `POST` | Register a new user account |
| `/api/auth/login` | `POST` | Authenticate and obtain session token |
| `/api/auth/logout` | `POST` | Invalidate current session token |
| `/api/tts` | `POST` | Synthesize text to speech audio |
| `/` | `GET` | Serve the web interface |

---

## License

MIT License. Designed and maintained for production environments.
