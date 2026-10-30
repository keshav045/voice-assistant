import React, { useState, useEffect } from 'react';
import {
  Activity,
  CheckCircle2,
  Database,
  ExternalLink,
  Flame,
  Key,
  Layers,
  RefreshCw,
  Server,
  ShieldAlert,
  Sparkles,
  User as UserIcon,
} from 'lucide-react';
import {
  fetchHealth,
  fetchSystemConfig,
  registerUser,
  loginUser,
} from './services/api';
import type { SystemHealth, SystemConfig, AuthResponse } from './types';

export function App() {
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [config, setConfig] = useState<SystemConfig | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'system' | 'auth' | 'roadmap'>('system');

  // Auth test state
  const [authEmail, setAuthEmail] = useState<string>('agent.user@nexus.ai');
  const [authPassword, setAuthPassword] = useState<string>('NexusSecure2026!');
  const [authName, setAuthName] = useState<string>('Nexus Operator');
  const [authResult, setAuthResult] = useState<AuthResponse | null>(null);
  const [authLoading, setAuthLoading] = useState<boolean>(false);
  const [authMessage, setAuthMessage] = useState<string | null>(null);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [healthData, configData] = await Promise.all([
        fetchHealth(),
        fetchSystemConfig().catch(() => null),
      ]);
      setHealth(healthData);
      if (configData) setConfig(configData);
    } catch (err: any) {
      console.error('Failed to load system data:', err);
      setError(err.message || 'Cannot reach Nexus backend server on http://localhost:8000');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 10000); // 10s auto refresh
    return () => clearInterval(interval);
  }, []);

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setAuthLoading(true);
    setAuthMessage(null);
    try {
      const res = await registerUser(authEmail, authPassword, authName);
      setAuthResult(res);
      setAuthMessage('Account registered successfully! JWT Token issued.');
    } catch (err: any) {
      setAuthMessage(`Error: ${err.message}`);
    } finally {
      setAuthLoading(false);
    }
  };

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setAuthLoading(true);
    setAuthMessage(null);
    try {
      const res = await loginUser(authEmail, authPassword);
      setAuthResult(res);
      setAuthMessage('Logged in successfully! Token verified.');
    } catch (err: any) {
      setAuthMessage(`Error: ${err.message}`);
    } finally {
      setAuthLoading(false);
    }
  };

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      {/* Top Navigation Bar */}
      <header
        style={{
          borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
          background: 'rgba(11, 15, 25, 0.85)',
          backdropFilter: 'blur(16px)',
          padding: '16px 32px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          position: 'sticky',
          top: 0,
          zIndex: 50,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
          <div
            style={{
              width: '42px',
              height: '42px',
              borderRadius: '10px',
              background: 'linear-gradient(135deg, #4f46e5 0%, #06b6d4 100%)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              boxShadow: '0 4px 20px rgba(99, 102, 241, 0.4)',
            }}
          >
            <Sparkles size={24} color="#ffffff" />
          </div>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <h1 style={{ fontSize: '1.25rem', fontWeight: 700, color: '#f8fafc', letterSpacing: '-0.02em' }}>
                NEXUS
              </h1>
              <span
                style={{
                  background: 'rgba(99, 102, 241, 0.15)',
                  color: '#a5b4fc',
                  border: '1px solid rgba(99, 102, 241, 0.3)',
                  padding: '2px 8px',
                  borderRadius: '6px',
                  fontSize: '0.72rem',
                  fontWeight: 600,
                }}
              >
                v{health?.version || '0.1.0'}
              </span>
            </div>
            <p style={{ fontSize: '0.78rem', color: '#94a3b8' }}>
              Agentic AI Productivity Assistant
            </p>
          </div>
        </div>

        {/* Status Indicators & External Links */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          {/* Health Pill */}
          {health?.status === 'healthy' ? (
            <div className="badge badge-success">
              <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#34d399' }} />
              API Online ({health.database.latency_ms ?? 1}ms)
            </div>
          ) : (
            <div className="badge badge-error">
              <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#f87171' }} />
              {loading ? 'Checking...' : 'API Disconnected'}
            </div>
          )}

          {/* Database Pill */}
          <div className="badge badge-info">
            <Database size={12} />
            {health?.database?.dialect?.toUpperCase() || 'DB'} : {health?.database?.status || 'Unknown'}
          </div>

          {/* Quick links */}
          <a
            href="http://localhost:8000/docs"
            target="_blank"
            rel="noreferrer"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              fontSize: '0.82rem',
              color: '#94a3b8',
              padding: '6px 12px',
              borderRadius: '6px',
              border: '1px solid rgba(255, 255, 255, 0.08)',
              background: 'rgba(255, 255, 255, 0.03)',
            }}
          >
            FastAPI Swagger <ExternalLink size={12} />
          </a>

          <button
            onClick={loadData}
            disabled={loading}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              background: '#4f46e5',
              color: '#ffffff',
            }}
          >
            <RefreshCw size={14} />
            Refresh
          </button>
        </div>
      </header>

      {/* Main Container */}
      <main style={{ maxWidth: '1280px', width: '100%', margin: '0 auto', padding: '32px 24px', flex: 1 }}>
        {/* Navigation Tabs */}
        <div
          style={{
            display: 'flex',
            gap: '8px',
            marginBottom: '28px',
            borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
            paddingBottom: '12px',
          }}
        >
          <button
            onClick={() => setActiveTab('system')}
            style={{
              background: activeTab === 'system' ? 'rgba(99, 102, 241, 0.2)' : 'transparent',
              color: activeTab === 'system' ? '#c7d2fe' : '#94a3b8',
              borderColor: activeTab === 'system' ? '#6366f1' : 'transparent',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
            }}
          >
            <Server size={16} /> Phase 1 Foundation & System Health
          </button>
          <button
            onClick={() => setActiveTab('auth')}
            style={{
              background: activeTab === 'auth' ? 'rgba(99, 102, 241, 0.2)' : 'transparent',
              color: activeTab === 'auth' ? '#c7d2fe' : '#94a3b8',
              borderColor: activeTab === 'auth' ? '#6366f1' : 'transparent',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
            }}
          >
            <Key size={16} /> Authentication & Identity
          </button>
          <button
            onClick={() => setActiveTab('roadmap')}
            style={{
              background: activeTab === 'roadmap' ? 'rgba(99, 102, 241, 0.2)' : 'transparent',
              color: activeTab === 'roadmap' ? '#c7d2fe' : '#94a3b8',
              borderColor: activeTab === 'roadmap' ? '#6366f1' : 'transparent',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
            }}
          >
            <Layers size={16} /> 10-Phase Roadmap Tracker
          </button>
        </div>

        {/* Error Notification */}
        {error && (
          <div
            className="card"
            style={{
              marginBottom: '24px',
              borderLeft: '4px solid #ef4444',
              display: 'flex',
              alignItems: 'center',
              gap: '12px',
              background: 'rgba(239, 68, 68, 0.08)',
            }}
          >
            <ShieldAlert size={22} color="#f87171" />
            <div>
              <div style={{ fontWeight: 600, color: '#f87171' }}>Backend Connection Notice</div>
              <div style={{ fontSize: '0.85rem', color: '#fca5a5' }}>{error}</div>
            </div>
          </div>
        )}

        {/* TAB 1: SYSTEM HEALTH & FOUNDATION */}
        {activeTab === 'system' && (
          <div>
            {/* Top Metrics Row */}
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
                gap: '20px',
                marginBottom: '28px',
              }}
            >
              {/* Card 1: Backend Server */}
              <div className="card">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                  <span style={{ fontSize: '0.82rem', color: '#94a3b8', textTransform: 'uppercase', fontWeight: 600 }}>
                    FastAPI Engine
                  </span>
                  <Activity size={18} color="#6366f1" />
                </div>
                <div style={{ fontSize: '1.4rem', fontWeight: 700, color: '#ffffff', marginBottom: '6px' }}>
                  {health?.status === 'healthy' ? 'Operational' : 'Waiting on Server'}
                </div>
                <div style={{ fontSize: '0.82rem', color: '#94a3b8' }}>
                  Port 8000 • Environment: <strong style={{ color: '#38bdf8' }}>{health?.environment || 'development'}</strong>
                </div>
              </div>

              {/* Card 2: Database Layer */}
              <div className="card">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                  <span style={{ fontSize: '0.82rem', color: '#94a3b8', textTransform: 'uppercase', fontWeight: 600 }}>
                    Storage Engine
                  </span>
                  <Database size={18} color="#10b981" />
                </div>
                <div style={{ fontSize: '1.4rem', fontWeight: 700, color: '#ffffff', marginBottom: '6px' }}>
                  {health?.database.dialect?.toUpperCase() || 'SQL'} Engine
                </div>
                <div style={{ fontSize: '0.82rem', color: '#94a3b8' }}>
                  Status: <span style={{ color: '#34d399', fontWeight: 600 }}>{health?.database.status}</span>
                  {health?.database.latency_ms !== undefined && ` (${health.database.latency_ms} ms ping)`}
                </div>
              </div>

              {/* Card 3: AI Configuration */}
              <div className="card">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                  <span style={{ fontSize: '0.82rem', color: '#94a3b8', textTransform: 'uppercase', fontWeight: 600 }}>
                    LLM & Voice Model
                  </span>
                  <Flame size={18} color="#f59e0b" />
                </div>
                <div style={{ fontSize: '1.4rem', fontWeight: 700, color: '#ffffff', marginBottom: '6px' }}>
                  {config?.ai.model || 'GPT-4o'}
                </div>
                <div style={{ fontSize: '0.82rem', color: '#94a3b8' }}>
                  Voice: {config?.ai.voice_model || 'gpt-4o-realtime-preview'}
                </div>
              </div>
            </div>

            {/* Checklist of Phase 1 Deliverables */}
            <div className="card" style={{ marginBottom: '28px' }}>
              <h2 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: '16px', color: '#f8fafc' }}>
                Phase 1 Acceptance Verification Checkpoint
              </h2>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '16px' }}>
                <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
                  <CheckCircle2 size={20} color="#10b981" style={{ flexShrink: 0, marginTop: '2px' }} />
                  <div>
                    <strong style={{ color: '#f1f5f9' }}>FastAPI Backend Started</strong>
                    <p style={{ fontSize: '0.82rem', color: '#94a3b8' }}>
                      Asynchronous application structure with Lifespan lifecycle and CORS enabled.
                    </p>
                  </div>
                </div>

                <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
                  <CheckCircle2 size={20} color="#10b981" style={{ flexShrink: 0, marginTop: '2px' }} />
                  <div>
                    <strong style={{ color: '#f1f5f9' }}>Database Models & Alembic</strong>
                    <p style={{ fontSize: '0.82rem', color: '#94a3b8' }}>
                      SQLAlchemy 2.0 models for User, OAuthAccount, Conversation, and Message with Alembic migration.
                    </p>
                  </div>
                </div>

                <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
                  <CheckCircle2 size={20} color="#10b981" style={{ flexShrink: 0, marginTop: '2px' }} />
                  <div>
                    <strong style={{ color: '#f1f5f9' }}>System Health & Config Endpoints</strong>
                    <p style={{ fontSize: '0.82rem', color: '#94a3b8' }}>
                      GET /health and GET /api/v1/system/config verified with automated tests.
                    </p>
                  </div>
                </div>

                <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
                  <CheckCircle2 size={20} color="#10b981" style={{ flexShrink: 0, marginTop: '2px' }} />
                  <div>
                    <strong style={{ color: '#f1f5f9' }}>JWT Authentication System</strong>
                    <p style={{ fontSize: '0.82rem', color: '#94a3b8' }}>
                      Bcrypt password hashing, Bearer JWT access tokens, and user registration endpoints.
                    </p>
                  </div>
                </div>

                <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
                  <CheckCircle2 size={20} color="#10b981" style={{ flexShrink: 0, marginTop: '2px' }} />
                  <div>
                    <strong style={{ color: '#f1f5f9' }}>Docker Compose Specifications</strong>
                    <p style={{ fontSize: '0.82rem', color: '#94a3b8' }}>
                      PostgreSQL with pgvector and Redis service definitions ready for container deployment.
                    </p>
                  </div>
                </div>

                <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
                  <CheckCircle2 size={20} color="#10b981" style={{ flexShrink: 0, marginTop: '2px' }} />
                  <div>
                    <strong style={{ color: '#f1f5f9' }}>React Dashboard Client</strong>
                    <p style={{ fontSize: '0.82rem', color: '#94a3b8' }}>
                      Vite + TypeScript dashboard connected to backend with live polling and health metrics.
                    </p>
                  </div>
                </div>
              </div>
            </div>

            {/* Live Response Payload Inspector */}
            <div className="card">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                <span style={{ fontSize: '0.9rem', fontWeight: 600, color: '#f8fafc' }}>
                  Live API Health Payload (/health)
                </span>
                <span style={{ fontSize: '0.78rem', color: '#64748b' }}>
                  Last response: {health?.timestamp || new Date().toISOString()}
                </span>
              </div>
              <pre>{JSON.stringify(health, null, 2)}</pre>
            </div>
          </div>
        )}

        {/* TAB 2: AUTHENTICATION */}
        {activeTab === 'auth' && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: '24px' }}>
            <div className="card">
              <h2 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: '14px', color: '#f8fafc' }}>
                User Registration & Token Generation
              </h2>
              <p style={{ fontSize: '0.82rem', color: '#94a3b8', marginBottom: '20px' }}>
                Test the JWT identity layer implemented for Phase 1. Tokens use bcrypt hashing and HS256 signatures.
              </p>

              <form onSubmit={handleRegister}>
                <div style={{ marginBottom: '14px' }}>
                  <label style={{ display: 'block', fontSize: '0.8rem', color: '#cbd5e1', marginBottom: '6px' }}>
                    Full Name
                  </label>
                  <input
                    type="text"
                    value={authName}
                    onChange={(e) => setAuthName(e.target.value)}
                    style={{
                      width: '100%',
                      padding: '10px 12px',
                      borderRadius: '8px',
                      background: 'rgba(255, 255, 255, 0.05)',
                      border: '1px solid rgba(255, 255, 255, 0.1)',
                      color: '#ffffff',
                    }}
                  />
                </div>

                <div style={{ marginBottom: '14px' }}>
                  <label style={{ display: 'block', fontSize: '0.8rem', color: '#cbd5e1', marginBottom: '6px' }}>
                    Email Address
                  </label>
                  <input
                    type="email"
                    value={authEmail}
                    onChange={(e) => setAuthEmail(e.target.value)}
                    style={{
                      width: '100%',
                      padding: '10px 12px',
                      borderRadius: '8px',
                      background: 'rgba(255, 255, 255, 0.05)',
                      border: '1px solid rgba(255, 255, 255, 0.1)',
                      color: '#ffffff',
                    }}
                  />
                </div>

                <div style={{ marginBottom: '20px' }}>
                  <label style={{ display: 'block', fontSize: '0.8rem', color: '#cbd5e1', marginBottom: '6px' }}>
                    Password
                  </label>
                  <input
                    type="password"
                    value={authPassword}
                    onChange={(e) => setAuthPassword(e.target.value)}
                    style={{
                      width: '100%',
                      padding: '10px 12px',
                      borderRadius: '8px',
                      background: 'rgba(255, 255, 255, 0.05)',
                      border: '1px solid rgba(255, 255, 255, 0.1)',
                      color: '#ffffff',
                    }}
                  />
                </div>

                <div style={{ display: 'flex', gap: '12px' }}>
                  <button
                    type="submit"
                    disabled={authLoading}
                    style={{ background: '#4f46e5', color: '#ffffff', flex: 1 }}
                  >
                    Register Account
                  </button>
                  <button
                    type="button"
                    onClick={handleLogin}
                    disabled={authLoading}
                    style={{
                      background: 'rgba(255, 255, 255, 0.08)',
                      color: '#f8fafc',
                      border: '1px solid rgba(255, 255, 255, 0.15)',
                      flex: 1,
                    }}
                  >
                    Login Existing
                  </button>
                </div>
              </form>

              {authMessage && (
                <div
                  style={{
                    marginTop: '16px',
                    padding: '10px 14px',
                    borderRadius: '8px',
                    fontSize: '0.82rem',
                    background: authMessage.startsWith('Error')
                      ? 'rgba(239, 68, 68, 0.15)'
                      : 'rgba(16, 185, 129, 0.15)',
                    color: authMessage.startsWith('Error') ? '#f87171' : '#34d399',
                    border: '1px solid currentColor',
                  }}
                >
                  {authMessage}
                </div>
              )}
            </div>

            <div className="card">
              <h2 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: '14px', color: '#f8fafc' }}>
                Active Token Payload
              </h2>
              {authResult ? (
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '14px' }}>
                    <UserIcon size={18} color="#60a5fa" />
                    <span style={{ fontSize: '0.9rem', color: '#e2e8f0', fontWeight: 600 }}>
                      {authResult.user.email} (UUID: {authResult.user.id})
                    </span>
                  </div>
                  <pre>{JSON.stringify(authResult, null, 2)}</pre>
                </div>
              ) : (
                <div
                  style={{
                    height: '240px',
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: '#64748b',
                    textAlign: 'center',
                  }}
                >
                  <Key size={36} style={{ marginBottom: '12px', opacity: 0.5 }} />
                  <p style={{ fontSize: '0.85rem' }}>
                    Submit registration or login to view the signed JWT and User session object.
                  </p>
                </div>
              )}
            </div>
          </div>
        )}

        {/* TAB 3: 10-PHASE ROADMAP TRACKER */}
        {activeTab === 'roadmap' && (
          <div className="card">
            <h2 style={{ fontSize: '1.2rem', fontWeight: 700, marginBottom: '6px', color: '#f8fafc' }}>
              Nexus 10-Milestone Implementation Plan
            </h2>
            <p style={{ fontSize: '0.85rem', color: '#94a3b8', marginBottom: '24px' }}>
              Execution strictly follows verified milestones. Each phase must be tested before advancing.
            </p>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              {[
                {
                  phase: 1,
                  title: 'Foundation & Infrastructure',
                  days: 'Days 1–3',
                  status: 'COMPLETE',
                  desc: 'FastAPI, SQLAlchemy, models, health checks, JWT auth, Alembic migrations, and React Vite dashboard.',
                  color: '#10b981',
                },
                {
                  phase: 2,
                  title: 'Voice Engine',
                  days: 'Days 4–8',
                  status: 'NEXT UP',
                  desc: 'Audio capture, OpenAI Realtime API speech-to-speech, interchangeable STT/TTS adapters, VAD, and interruption handling.',
                  color: '#6366f1',
                },
                {
                  phase: 3,
                  title: 'LLM & LangGraph Agentic Core',
                  days: 'Days 9–14',
                  status: 'PLANNED',
                  desc: 'Intent classification, planner, tool selection router, approval gate checkpoints, and recovery.',
                  color: '#64748b',
                },
                {
                  phase: 4,
                  title: 'Tasks & Reminders Engine',
                  days: 'Days 15–18',
                  status: 'PLANNED',
                  desc: 'Task CRUD, priority scoring, deadlines, Celery/Redis background worker, and scheduled notifications.',
                  color: '#64748b',
                },
                {
                  phase: 5,
                  title: 'Gmail Assistant',
                  days: 'Days 19–22',
                  status: 'PLANNED',
                  desc: 'OAuth 2.0 Google connection, Gmail search, AI email summarization, draft generation, approval-gated sending.',
                  color: '#64748b',
                },
                {
                  phase: 6,
                  title: 'Google Calendar Assistant',
                  days: 'Days 23–26',
                  status: 'PLANNED',
                  desc: 'Event inspection, free/busy availability check, conflict resolution, proposed schedules with user confirmation.',
                  color: '#64748b',
                },
                {
                  phase: 7,
                  title: 'Windows Desktop Companion Agent',
                  days: 'Days 27–32',
                  status: 'PLANNED',
                  desc: 'Local Python companion, outbound secure WebSocket, strict action allowlists, application control, and file search.',
                  color: '#64748b',
                },
                {
                  phase: 8,
                  title: 'Semantic Memory & pgvector',
                  days: 'Days 33–36',
                  status: 'PLANNED',
                  desc: 'Embedding generation, vector search, preference storage, conversation history, user memory deletion controls.',
                  color: '#64748b',
                },
                {
                  phase: 9,
                  title: 'Frontend UI & Voice Controls',
                  days: 'Days 37–41',
                  status: 'PLANNED',
                  desc: 'Full-featured productivity dashboard: overview, live voice wave, email drafts, task kanban, calendar view, approvals modal.',
                  color: '#64748b',
                },
                {
                  phase: 10,
                  title: 'Testing, Hardening & Deployment',
                  days: 'Days 42–46',
                  status: 'PLANNED',
                  desc: 'End-to-end evaluation suite, rate limiting, error tracking, Docker containerization, cloud deployment, and audit logging.',
                  color: '#64748b',
                },
              ].map((m) => (
                <div
                  key={m.phase}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '16px 20px',
                    borderRadius: '10px',
                    background: 'rgba(255, 255, 255, 0.03)',
                    border: `1px solid ${m.status === 'COMPLETE' ? 'rgba(16, 185, 129, 0.3)' : m.status === 'NEXT UP' ? 'rgba(99, 102, 241, 0.4)' : 'rgba(255, 255, 255, 0.06)'}`,
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                    <div
                      style={{
                        width: '36px',
                        height: '36px',
                        borderRadius: '50%',
                        background: `${m.color}20`,
                        color: m.color,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontWeight: 700,
                        fontSize: '0.85rem',
                        border: `1px solid ${m.color}40`,
                      }}
                    >
                      {m.phase}
                    </div>
                    <div>
                      <div style={{ fontWeight: 600, color: '#f8fafc', fontSize: '0.95rem' }}>
                        Phase {m.phase}: {m.title}
                      </div>
                      <div style={{ fontSize: '0.8rem', color: '#94a3b8' }}>
                        {m.desc} • <span style={{ color: '#cbd5e1' }}>{m.days}</span>
                      </div>
                    </div>
                  </div>

                  <span
                    style={{
                      padding: '4px 10px',
                      borderRadius: '6px',
                      fontSize: '0.72rem',
                      fontWeight: 700,
                      background: `${m.color}20`,
                      color: m.color,
                      border: `1px solid ${m.color}40`,
                    }}
                  >
                    {m.status}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </main>

      {/* Footer */}
      <footer
        style={{
          borderTop: '1px solid rgba(255, 255, 255, 0.08)',
          padding: '16px 32px',
          fontSize: '0.8rem',
          color: '#64748b',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          background: 'rgba(11, 15, 25, 0.9)',
        }}
      >
        <span>Nexus Agentic AI Assistant • Phase 1 Foundation Verified</span>
        <span>Python 3.11 • FastAPI • SQLite / PostgreSQL • Vite React TS</span>
      </footer>
    </div>
  );
}

export default App;
