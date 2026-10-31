# Nexus — Agentic AI Productivity Assistant

> A production-style hybrid voice + agentic AI platform powered by LangGraph, FastAPI, and an authenticated Windows 11 desktop companion.

---

## System Architecture

```
React Dashboard + Voice Client (Port 5173)
           │
           ▼
FastAPI Backend (Port 8000)
  ├── Lifespan & Config Management
  ├── JWT Auth & Role Security
  ├── Health & System Endpoints (/health, /api/v1/system/config)
  ├── SQLAlchemy 2.0 Async ORM (SQLite / PostgreSQL with pgvector)
  └── Alembic Migrations
```

---

## Repository Structure

```
nexus-ai-assistant/
├── backend/
│   ├── alembic/                # Async DB schema migrations
│   ├── app/
│   │   ├── api/                # REST & WebSocket route handlers
│   │   │   └── v1/endpoints/   # health, system, auth
│   │   ├── agents/             # Specialist agents (task, email, calendar, etc.)
│   │   ├── core/               # App config (Pydantic Settings), security (JWT/bcrypt)
│   │   ├── database/           # Base, async engine, session dependency
│   │   ├── models/             # SQLAlchemy 2.0 models (User, OAuthAccount, Conversation, Message)
│   │   ├── services/           # OpenAI, Google Workspace adapters
│   │   └── workflows/          # LangGraph state and orchestration graphs
│   ├── tests/                  # Pytest async integration & unit test suite
│   ├── requirements.txt        # Backend dependencies
│   ├── pytest.ini              # Pytest configuration
│   └── .env.example            # Backend environment template
├── frontend/
│   ├── src/
│   │   ├── components/         # Reusable UI widgets
│   │   ├── services/api.ts     # Health, config, and auth API clients
│   │   ├── types/index.ts      # TypeScript interfaces
│   │   ├── App.tsx             # Interactive dashboard & roadmap tracker
│   │   └── index.css           # Glassmorphism dark mode styles
│   ├── package.json            # Vite, React 19, Lucide
│   └── vite.config.ts          # Vite proxy to backend
├── desktop-agent/              # Windows 11 local companion agent (Phase 7)
├── database/
│   └── init/01-init.sql        # PostgreSQL pgvector & UUID extension initialization
├── docker-compose.yml          # Container configuration for PostgreSQL + pgvector and Redis
├── .env.example                # Root environment template
├── .gitignore
└── README.md
```

---

## Quickstart Guide

### 1. Backend Setup

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

- **Health check**: `http://localhost:8000/health`
- **Interactive Swagger UI**: `http://localhost:8000/docs`
- **System config**: `http://localhost:8000/api/v1/system/config`

### 2. Frontend Setup

```powershell
cd frontend
npm install
npm run dev
```

- **Dashboard**: `http://localhost:5173`

### 3. Run Backend Automated Tests

```powershell
cd backend
.\.venv\Scripts\pytest.exe -v
```

---

## 10-Milestone Roadmap

- [x] **Phase 1 — Foundation & Infrastructure** (Completed)
- [ ] **Phase 2 — Voice Engine** (OpenAI Realtime API, STT/TTS adapters, VAD)
- [ ] **Phase 3 — LLM & LangGraph Core** (Orchestrator, intent router, approval gates)
- [ ] **Phase 4 — Tasks & Reminders** (CRUD, Redis queue, background scheduling)
- [ ] **Phase 5 — Gmail Integration** (OAuth, summarization, draft generation)
- [ ] **Phase 6 — Google Calendar** (Free/busy, conflict detection, scheduling)
- [ ] **Phase 7 — Windows Desktop Agent** (Authenticated outbound WS, command allowlists)
- [ ] **Phase 8 — Semantic Memory** (pgvector embeddings, preference retrieval)
- [ ] **Phase 9 — Dashboard & Voice UI** (Wave visualizer, kanban, approvals modal)
- [ ] **Phase 10 — Hardening & Production** (Rate limiting, audit logging, packaging)

