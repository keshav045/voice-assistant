-- Personal Voice Assistant Database Schema
-- Matches PDF specification for core tables

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'guest',
    title TEXT NOT NULL,
    priority TEXT NOT NULL DEFAULT 'medium',
    due_at TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS memory_facts (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'guest',
    fact TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'general',
    created_at TEXT NOT NULL,
    last_used_at TEXT
);

CREATE TABLE IF NOT EXISTS tool_calls (
    id TEXT PRIMARY KEY,
    session_id TEXT,
    tool TEXT NOT NULL,
    args_json TEXT,
    result_size INTEGER,
    latency_ms REAL,
    error TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    stt_seconds REAL DEFAULT 0.0,
    tts_chars INTEGER DEFAULT 0,
    llm_tokens INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS doc_chunks (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'guest',
    file TEXT NOT NULL,
    section TEXT,
    text TEXT NOT NULL,
    embedding TEXT,
    modified_at TEXT NOT NULL
);

-- PDF Plan Data Model Additions
CREATE TABLE IF NOT EXISTS papers (
    id TEXT PRIMARY KEY,
    source_url TEXT,
    title TEXT NOT NULL,
    authors TEXT,
    file_path TEXT,
    parsed_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS paper_chunks (
    id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL,
    section TEXT,
    chunk_index INTEGER DEFAULT 0,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(paper_id) REFERENCES papers(id)
);

CREATE TABLE IF NOT EXISTS reports (
    id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL,
    depth TEXT NOT NULL DEFAULT 'standard',
    markdown TEXT NOT NULL,
    pdf_path TEXT,
    verified INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY(paper_id) REFERENCES papers(id)
);

CREATE TABLE IF NOT EXISTS reminders (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'guest',
    text TEXT NOT NULL,
    due_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notes (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'guest',
    text TEXT NOT NULL,
    tags TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    title TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    tool_calls TEXT,
    created_at TEXT NOT NULL
);

-- User Authentication & Personal History
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_tokens (
    token TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS chat_history (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    user_message TEXT NOT NULL,
    spoken_reply TEXT NOT NULL,
    tool_calls TEXT,
    latency_ms REAL,
    created_at TEXT NOT NULL
);

-- Google OAuth & Third-party Integrations
CREATE TABLE IF NOT EXISTS user_oauth_tokens (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT 'google',
    email TEXT,
    access_token TEXT,
    refresh_token TEXT,
    token_expiry TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Execution Tracing & Observability (LangSmith & Local SQLite Traces)
CREATE TABLE IF NOT EXISTS execution_traces (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    user_id TEXT NOT NULL DEFAULT 'guest',
    name TEXT NOT NULL,
    run_type TEXT NOT NULL DEFAULT 'chain',
    start_time REAL NOT NULL,
    end_time REAL,
    latency_ms REAL,
    status TEXT NOT NULL DEFAULT 'running',
    inputs_json TEXT,
    outputs_json TEXT,
    metadata_json TEXT,
    created_at TEXT NOT NULL
);

-- Custom Email Sender Profiles
CREATE TABLE IF NOT EXISTS user_email_profiles (
    user_id TEXT PRIMARY KEY,
    sender_name TEXT NOT NULL,
    sender_email TEXT NOT NULL,
    sender_password TEXT,
    smtp_host TEXT DEFAULT 'smtp.gmail.com',
    smtp_port INTEGER DEFAULT 587,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Persistent Calendar Events
CREATE TABLE IF NOT EXISTS calendar_events (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'guest',
    title TEXT NOT NULL,
    start TEXT NOT NULL,
    end TEXT NOT NULL,
    attendees_json TEXT NOT NULL DEFAULT '[]',
    calendar_id TEXT NOT NULL DEFAULT 'primary',
    status TEXT NOT NULL DEFAULT 'confirmed',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chat_history_user_session ON chat_history(user_id, session_id);




