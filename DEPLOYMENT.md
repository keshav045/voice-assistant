# Nexus AI Voice Assistant — Production Deployment Guide

This document details the production deployment, containerization, environment configuration, and operational best practices for the **Nexus AI Personal Voice Assistant**.

---

## 1. System Architecture & Requirements

The Nexus Voice Assistant is an asynchronous FastAPI service providing:
- **Speech-to-Text & Text-to-Speech**: Browser Web Speech API & optional OpenAI Whisper/TTS with instant speech cancellation.
- **Agentic Tool Execution**: Web search, safe mathematical computation, Python REPL, Windows/Browser app launcher (`open_app`), and WhatsApp automation (`send_whatsapp_message`).
- **Data Persistence**: SQLite in Write-Ahead Logging (WAL) mode (`PRAGMA journal_mode=WAL;`, `PRAGMA foreign_keys=ON;`, `timeout=30.0`), persistent user sessions, and grouped conversation history.
- **Web Interface**: Lightweight vanilla HTML5/ES6 client served statically by FastAPI.

### System Prerequisites
- **Python**: 3.11+
- **Docker**: 20.10+ (for containerized deployments)
- **Docker Compose**: 2.0+ (optional, for local container orchestration)
- **Memory**: Minimum 512 MB RAM (1 GB recommended)
- **Disk**: 1 GB free space for database persistence and dependencies

---

## 2. Environment Configuration

Copy `.env.example` to `.env` in the project root:

```bash
cp .env.example .env
```

### Essential Environment Variables

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | *(required)* | OpenAI API key for conversational intelligence and function calling |
| `OPENAI_MODEL` | `gpt-4o` | Model identifier (`gpt-4o`, `gpt-4o-mini`) |
| `HOST` | `0.0.0.0` | Network binding interface |
| `PORT` | `8000` | Port for the HTTP and WebSocket server |
| `WORKERS` | `1` | Uvicorn worker count (keep at 1 for SQLite consistency or scale with distributed DB) |
| `DB_PATH` | `/app/data/voice_assistant.db` | Absolute or relative path to SQLite database file |
| `LOG_LEVEL` | `info` | Logging verbosity (`debug`, `info`, `warning`, `error`) |

---

## 3. Production Deployment Options

### Option A: Docker & Docker Compose (Recommended)

The repository provides a multi-stage, non-root `Dockerfile` and `docker-compose.yml` with health checks and persistent volume mounting.

#### 1. Build and Run with Docker Compose
```bash
# Start container in detached mode
docker-compose up -d --build

# Inspect running containers
docker-compose ps

# View live container logs
docker-compose logs -f
```

#### 2. Standalone Docker Run
```bash
# Build production image
docker build -t nexus-voice-assistant:latest .

# Run with persistent data volume and environment variables
docker run -d \
  --name nexus_voice_assistant \
  --restart unless-stopped \
  -p 8000:8000 \
  -e OPENAI_API_KEY="your-api-key-here" \
  -e OPENAI_MODEL="gpt-4o" \
  -v nexus_data:/app/data \
  nexus-voice-assistant:latest
```

#### 3. Verify Health Check
```bash
docker inspect --format='{{json .State.Health}}' nexus_voice_assistant
curl http://localhost:8000/health
```

---

### Option B: Cloud Platform Deployments

Nexus is fully containerized and automatically adheres to dynamic cloud port bindings (`${PORT:-8000}`).

#### 1. Deploy on Render
1. Connect your GitHub repository to [Render](https://render.com).
2. Create a new **Web Service**.
3. Select **Docker** as the Runtime environment.
4. Set the following Environment Variables in the Render dashboard:
   - `OPENAI_API_KEY`: `sk-...`
   - `OPENAI_MODEL`: `gpt-4o`
   - `DB_PATH`: `/app/data/voice_assistant.db`
5. Under **Disks**, add a persistent disk mounted to `/app/data` (size: 1 GB).
6. Set Health Check Path to: `/health`.
7. Click **Create Web Service**.

#### 2. Deploy on Railway
1. Install Railway CLI or connect via the [Railway Dashboard](https://railway.app).
2. Click **New Project** → **Deploy from GitHub Repo**.
3. Add a **Volume** mounted to `/app/data` to ensure SQLite history persists across redeploys.
4. Set environment variable `OPENAI_API_KEY`.
5. Railway automatically builds the included `Dockerfile` and exposes the service.

#### 3. Deploy on Fly.io
1. Install `flyctl` and log in:
   ```bash
   fly auth login
   ```
2. Initialize app:
   ```bash
   fly launch --no-deploy
   ```
3. Create a persistent volume for the SQLite database:
   ```bash
   fly volumes create nexus_data --size 1
   ```
4. Attach the volume in `fly.toml`:
   ```toml
   [mounts]
     source = "nexus_data"
     destination = "/app/data"

   [http_service]
     internal_port = 8000
     force_https = true
     auto_stop_machines = false
     auto_start_machines = true
   ```
5. Set secret and deploy:
   ```bash
   fly secrets set OPENAI_API_KEY="your-key"
   fly deploy
   ```

#### 4. Deploy on Google Cloud Run
```bash
gcloud run deploy nexus-assistant \
  --source . \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars OPENAI_API_KEY="your-key"
```

---

### Option C: Bare-Metal / Linux VPS (Ubuntu/Debian)

For deployment on dedicated servers, AWS EC2, or DigitalOcean Droplets using **systemd** and **Nginx**.

#### 1. Setup User and Repository
```bash
sudo useradd -m -s /bin/bash nexusapp
sudo usermod -aG sudo nexusapp
sudo su - nexusapp

git clone <your-repository-url> /home/nexusapp/voice-assistant
cd /home/nexusapp/voice-assistant

python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
nano .env
```

#### 2. Configure Systemd Service
Create `/etc/systemd/system/nexus-assistant.service`:
```ini
[Unit]
Description=Nexus AI Voice Assistant Service
After=network.target

[Service]
Type=simple
User=nexusapp
WorkingDirectory=/home/nexusapp/voice-assistant
EnvironmentFile=/home/nexusapp/voice-assistant/.env
ExecStart=/home/nexusapp/voice-assistant/.venv/bin/python run_server.py
Restart=always
RestartSec=5s

[Install]
WantedBy=multi-user.target
```

Enable and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable nexus-assistant
sudo systemctl start nexus-assistant
sudo systemctl status nexus-assistant
```

#### 3. Nginx Reverse Proxy with SSL (Certbot)
Create `/etc/nginx/sites-available/nexus-assistant`:
```nginx
server {
    server_name yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400;
    }
}
```

Enable site and acquire free SSL certificate:
```bash
sudo ln -s /etc/nginx/sites-available/nexus-assistant /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
sudo certbot --nginx -d yourdomain.com
```

---

## 4. Production Health Probes & Monitoring

The application includes two dedicated monitoring endpoints:
- `GET /health`: Used by load balancers, container orchestrators (Docker, Kubernetes), and uptime monitors.
- `GET /api/health`: Provides diagnostic status on database responsiveness and model availability.

Example payload:
```json
{
  "status": "healthy",
  "database": "ok",
  "model": "gpt-4o",
  "llm_ready": true,
  "service": "Nexus Personal Voice Assistant",
  "version": "1.0.0",
  "timestamp": "2026-11-02T18:47:47.294019+00:00"
}
```

---

## 5. Security & Maintenance Checklist

- [x] **Non-Root Container**: Container runs under dedicated user `appuser` (UID 1000).
- [x] **Database Concurrency**: SQLite configured with Write-Ahead Logging (`WAL`), `foreign_keys=ON`, and `timeout=30.0` to eliminate database locking under concurrent traffic.
- [x] **Credential Protection**: Passwords hashed using salted SHA-256 (`db/models.py`). Session tokens are cryptographically random 256-bit hexadecimal strings.
- [x] **Dynamic Port Binding**: Application responds dynamically to `$PORT` passed by cloud container providers.
- [x] **Graceful Fallbacks**: Web-based launcher and clipboard messaging fallback gracefully when desktop applications or GUI displays are unavailable.
