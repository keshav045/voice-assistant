# Nexus Agentic AI Productivity Assistant — Complete Deployment Guide

This guide details how to deploy the **Nexus Executive Dashboard** and backend services across cloud hosting providers (Vercel, Netlify, Railway, Render), Docker container infrastructure, or as a standalone local Windows workstation application.

---

## 🌐 Option 1: Cloud Deployment (Vercel / Netlify + Railway / Render)

Deploying Nexus in the cloud gives you a persistent, shareable URL accessible from any desktop, tablet, or browser.

### 1.1 Backend Cloud Deployment (Railway or Render)
1. Push your repository to **GitHub** (private or public).
2. Create an account on [Railway.app](https://railway.app) or [Render.com](https://render.com).
3. Click **New Project** -> **Deploy from GitHub repo**.
4. Set the Root Directory to: `backend`
5. Configure Environment Variables:
   ```env
   ENVIRONMENT="production"
   DEBUG="false"
   OPENAI_API_KEY="sk-proj-your-key-here"
   SECRET_KEY="your-random-32-character-secret-key"
   DATABASE_URL="sqlite+aiosqlite:///./nexus.db"  # Or connect to a managed Postgres instance
   GOOGLE_CLIENT_ID="your-google-client-id.apps.googleusercontent.com"
   GOOGLE_CLIENT_SECRET="your-google-client-secret"
   GOOGLE_REDIRECT_URI="https://your-backend-url.railway.app/api/v1/auth/google/callback"
   FRONTEND_URL="https://your-nexus-frontend.vercel.app"
   ```
6. Start Command:
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```
7. Note down your public backend URL (e.g. `https://nexus-api.railway.app`).

---

### 1.2 Frontend Cloud Deployment (Vercel)
Nexus includes a pre-configured [frontend/vercel.json](file:///c:/Users/kesha/OneDrive/Desktop/voice%20assistant/frontend/vercel.json) that automatically handles single-page application (SPA) routing.

1. Navigate to [Vercel](https://vercel.com) and click **Add New Project**.
2. Select your repository.
3. In **Build & Development Settings**:
   * **Framework Preset**: `Vite`
   * **Root Directory**: `frontend`
   * **Build Command**: `npm run build`
   * **Output Directory**: `dist`
4. Add Environment Variable:
   ```env
   VITE_API_BASE_URL="https://your-backend-url.railway.app"
   ```
5. Click **Deploy**. Vercel will build and assign you a fast, global CDN URL (e.g. `https://nexus-assistant.vercel.app`).

---

### 1.3 Frontend Cloud Deployment (Netlify)
Nexus includes [frontend/netlify.toml](file:///c:/Users/kesha/OneDrive/Desktop/voice%20assistant/frontend/netlify.toml) with SPA fallback routing.

1. Navigate to [Netlify](https://netlify.com) -> **Add new site** -> **Import an existing project**.
2. Base directory: `frontend`
3. Build command: `npm run build`
4. Publish directory: `frontend/dist`
5. Add Environment Variable in Netlify UI:
   ```env
   VITE_API_BASE_URL="https://your-backend-url.railway.app"
   ```
6. Click **Deploy Site**.

---

## 🐳 Option 2: Full-Stack Docker Compose Deployment

If you want to host both backend, frontend, PostgreSQL (with pgvector), and Redis on a cloud VPS (Ubuntu, Debian, AWS EC2, DigitalOcean, Hetzner), use the included production Docker Compose file:

### Step 1: Clone and Configure
```bash
git clone <your-repo-url>
cd "voice assistant"
cp .env.example .env
```
Fill in your `OPENAI_API_KEY` and `SECRET_KEY` in `.env`.

### Step 2: Build and Launch Containers
```bash
docker compose -f docker-compose.prod.yml up -d --build
```

### What this starts:
* **`nexus-frontend-prod`**: Nginx Alpine serving the production React bundle on Port `80` (HTTP).
* **`nexus-backend-prod`**: FastAPI Uvicorn engine on Port `8000`.
* **`nexus-postgres-prod`**: PostgreSQL 16 with `pgvector` extension for 1536-dimensional semantic memory on Port `5432`.
* **`nexus-redis-prod`**: Redis 7 Alpine cache & message broker on Port `6379`.

### View Logs:
```bash
docker compose -f docker-compose.prod.yml logs -f
```

---

## 💻 Option 3: Local Windows 11 Native Run

For everyday personal usage on your local Windows workstation:

1. **Launch**:
   Double-click:
   ```bat
   start-nexus.bat
   ```
   * Automatically initializes the backend, Vite dev server, desktop companion daemon, and opens `http://localhost:5173`.
2. **Stop**:
   Double-click:
   ```bat
   stop-nexus.bat
   ```
   * Terminates all processes cleanly.

---

## 🔐 Environment Variables Reference Table

| Variable | Required | Default | Purpose |
| :--- | :--- | :--- | :--- |
| `OPENAI_API_KEY` | **Yes** | `""` | Powers LangGraph agent routing, speech recognition, and semantic memory |
| `SECRET_KEY` | **Yes** | Dev Key | Key used for JWT signatures and Fernet token encryption |
| `DATABASE_URL` | No | SQLite local | Async database URL (`sqlite+aiosqlite:///./nexus.db` or PostgreSQL) |
| `GOOGLE_CLIENT_ID` | Optional | `""` | Google Cloud OAuth Client ID for Gmail & Calendar sync |
| `GOOGLE_CLIENT_SECRET` | Optional | `""` | Google Cloud OAuth Client Secret |
| `GOOGLE_REDIRECT_URI` | Optional | `http://localhost:8000/api/v1/auth/google/callback` | OAuth redirect URI |
| `VITE_API_BASE_URL` | Cloud only | Auto-detected | Public backend API URL consumed by the React dashboard |

---

## 🧪 Production Health & Status Verification

Once deployed, verify your deployment:
* **Frontend Dashboard**: Visit your assigned URL (e.g. `https://nexus.vercel.app` or `http://localhost:5173`).
* **API Health Check**: `GET /health` returns `{ "status": "healthy", "database": { "status": "connected" } }`.
* **FastAPI Interactive Docs**: Visit `http://your-backend-domain/docs`.
