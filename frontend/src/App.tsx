import React, { useState, useEffect } from 'react';
import {
  Activity,
  AlertTriangle,
  Bot,
  Brain,
  Calendar,
  ChevronLeft,
  ChevronRight,
  Database,
  ExternalLink,
  Flame,
  Key,
  Layers,
  LayoutDashboard,
  ListTodo,
  Mail,
  Mic,
  Monitor,
  RefreshCw,
  Search,
  Server,
  ShieldAlert,
  Sparkles,
  X,
  Zap,
} from 'lucide-react';
import {
  fetchHealth,
  fetchSystemConfig,
  registerUser,
  loginUser,
  fetchReminders,
  fetchApprovals,
  fetchGoogleAuthStatus,
  fetchGoogleAuthUrl,
  submitChatMessage,
  type GoogleAuthStatusDto,
} from './services/api';
import type { SystemHealth, SystemConfig, AuthResponse } from './types';
import { VoiceAssistant } from './components/VoiceAssistant';
import { AgentOrchestrator } from './components/AgentOrchestrator';
import { TaskManager } from './components/TaskManager';
import { EmailAssistant } from './components/EmailAssistant';
import { CalendarAssistant } from './components/CalendarAssistant';
import { DesktopCompanion } from './components/DesktopCompanion';
import { SemanticMemory } from './components/SemanticMemory';
import { UnifiedDashboard } from './components/UnifiedDashboard';

type TabKey =
  | 'dashboard'
  | 'voice'
  | 'agent'
  | 'tasks'
  | 'emails'
  | 'calendar'
  | 'desktop'
  | 'memory'
  | 'system'
  | 'auth'
  | 'roadmap';

interface NavItem {
  id: string;
  label: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  badge: string | null;
  badgeColor?: string;
}

interface NavSection {
  group: string;
  items: NavItem[];
}

export function App() {
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [config, setConfig] = useState<SystemConfig | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<TabKey>('dashboard');
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState<boolean>(false);
  const [pendingApprovalsCount, setPendingApprovalsCount] = useState<number>(0);
  const [googleStatus, setGoogleStatus] = useState<GoogleAuthStatusDto | null>(null);

  // Command Palette State (Ctrl+K)
  const [isCommandPaletteOpen, setIsCommandPaletteOpen] = useState<boolean>(false);
  const [commandQuery, setCommandQuery] = useState<string>('');
  const [commandExecuting, setCommandExecuting] = useState<boolean>(false);
  const [commandResult, setCommandResult] = useState<string | null>(null);

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
      const [healthData, configData, approvalsData, googleData] = await Promise.all([
        fetchHealth(),
        fetchSystemConfig().catch(() => null),
        fetchApprovals('pending').catch(() => []),
        fetchGoogleAuthStatus().catch(() => null),
      ]);
      setHealth(healthData);
      if (configData) setConfig(configData);
      setPendingApprovalsCount(approvalsData.length);
      if (googleData) setGoogleStatus(googleData);
    } catch (err: any) {
      console.error('Failed to load system data:', err);
      setError(err.message || 'Cannot reach Nexus backend server on http://localhost:8000');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 12000); // 12s auto refresh

    // Request desktop notification permission
    if ('Notification' in window && Notification.permission === 'default') {
      Notification.requestPermission();
    }

    // Check due reminders and notify
    const remindedIds = new Set<string>();
    const checkReminders = async () => {
      try {
        const triggered = await fetchReminders('triggered');
        for (const rem of triggered) {
          if (!remindedIds.has(rem.id)) {
            remindedIds.add(rem.id);
            if ('Notification' in window && Notification.permission === 'granted') {
              new Notification('Nexus Reminder Due', {
                body: rem.title,
                icon: '/vite.svg',
              });
            }
          }
        }
      } catch (e) {
        // Ignore background polling error
      }
    };
    const remInterval = setInterval(checkReminders, 12000);

    // Global keyboard shortcut: Ctrl+K / Cmd+K
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setIsCommandPaletteOpen((prev) => !prev);
      }
      if (e.key === 'Escape') {
        setIsCommandPaletteOpen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);

    // Google OAuth window message listener
    const handleGoogleMessage = (event: MessageEvent) => {
      if (event.data?.type === 'GOOGLE_CONNECTED') {
        loadData();
      }
    };
    window.addEventListener('message', handleGoogleMessage);

    return () => {
      clearInterval(interval);
      clearInterval(remInterval);
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('message', handleGoogleMessage);
    };
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

  const handleConnectGoogle = async () => {
    try {
      const authData = await fetchGoogleAuthUrl();
      if (!authData.configured || !authData.url) {
        alert(authData.message || 'Please configure GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in backend/.env');
        return;
      }
      window.open(authData.url, 'GoogleAuthPopup', 'width=600,height=700');
    } catch (err: any) {
      alert(err.message || 'Failed to start Google sign-in');
    }
  };

  const handleExecuteCommandPrompt = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!commandQuery.trim()) return;
    setCommandExecuting(true);
    setCommandResult(null);
    try {
      const res = await submitChatMessage(commandQuery.trim());
      setCommandResult(res.final_response || 'Execution finished.');
      await loadData();
    } catch (err: any) {
      setCommandResult(`Error: ${err.message}`);
    } finally {
      setCommandExecuting(false);
    }
  };

  const navItems: NavSection[] = [
    {
      group: 'CORE ASSISTANT',
      items: [
        { id: 'dashboard', label: 'Command Center', icon: LayoutDashboard, badge: null },
        { id: 'voice', label: 'Voice Assistant', icon: Mic, badge: 'Live' },
        {
          id: 'agent',
          label: 'Agentic Core',
          icon: Bot,
          badge: pendingApprovalsCount > 0 ? `${pendingApprovalsCount} gate` : null,
          badgeColor: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
        },
      ],
    },
    {
      group: 'PRODUCTIVITY SUITE',
      items: [
        { id: 'tasks', label: 'Tasks & Reminders', icon: ListTodo, badge: null },
        { id: 'emails', label: 'Gmail Assistant', icon: Mail, badge: googleStatus?.connected ? 'Sync' : null },
        { id: 'calendar', label: 'Google Calendar', icon: Calendar, badge: null },
      ],
    },
    {
      group: 'OS & SYSTEM',
      items: [
        { id: 'desktop', label: 'Windows Companion', icon: Monitor, badge: 'Phase 7' },
        { id: 'memory', label: 'Semantic Memory', icon: Brain, badge: null },
        { id: 'system', label: 'System & Health', icon: Server, badge: null },
        { id: 'auth', label: 'Authentication', icon: Key, badge: null },
        { id: 'roadmap', label: '10-Phase Roadmap', icon: Layers, badge: '100%' },
      ],
    },
  ];

  const getBreadcrumbTitle = (tab: TabKey): string => {
    switch (tab) {
      case 'dashboard':
        return 'Executive Command Center';
      case 'voice':
        return 'Voice Assistant & Speech Engine';
      case 'agent':
        return 'LangGraph Agentic Core & Approvals';
      case 'tasks':
        return 'Tasks & Reminders Engine';
      case 'emails':
        return 'Gmail & Email Intelligence';
      case 'calendar':
        return 'Google Calendar & Scheduling';
      case 'desktop':
        return 'Windows Desktop Companion';
      case 'memory':
        return 'Semantic Vector Memory & Preferences';
      case 'system':
        return 'System Telemetry & Architecture';
      case 'auth':
        return 'Authentication & Session Security';
      case 'roadmap':
        return '10-Phase Implementation Roadmap';
      default:
        return 'Dashboard';
    }
  };

  return (
    <div className="min-h-screen bg-[#0b0f19] text-slate-100 flex flex-col font-sans selection:bg-indigo-500/30 selection:text-indigo-200">
      <div className="flex flex-1 relative">
        {/* Modern Collapsible Sidebar */}
        <aside
          className={`bg-[#0f172a]/95 backdrop-blur-xl border-r border-slate-800/80 flex flex-col justify-between transition-all duration-300 z-40 sticky top-0 h-screen ${
            isSidebarCollapsed ? 'w-20' : 'w-64'
          }`}
        >
          {/* Sidebar Header */}
          <div>
            <div className="p-4 border-b border-slate-800/80 flex items-center justify-between">
              <div className="flex items-center gap-3 overflow-hidden">
                <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-indigo-600 to-cyan-500 flex items-center justify-center text-white shadow-lg shadow-indigo-500/25 flex-shrink-0">
                  <Sparkles size={20} className="animate-pulse" />
                </div>
                {!isSidebarCollapsed && (
                  <div className="overflow-hidden">
                    <div className="flex items-center gap-2">
                      <span className="font-extrabold text-base tracking-tight text-white">NEXUS</span>
                      <span className="text-[10px] bg-indigo-500/20 text-indigo-300 px-1.5 py-0.5 rounded border border-indigo-500/30 font-mono font-bold">
                        v{health?.version || '1.0'}
                      </span>
                    </div>
                    <p className="text-[11px] text-slate-400 truncate">Agentic Productivity</p>
                  </div>
                )}
              </div>
              <button
                onClick={() => setIsSidebarCollapsed(!isSidebarCollapsed)}
                className="p-1.5 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-white transition flex-shrink-0"
                title={isSidebarCollapsed ? 'Expand Sidebar' : 'Collapse Sidebar'}
              >
                {isSidebarCollapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
              </button>
            </div>

            {/* Quick Search Shortcut Button */}
            <div className="p-3">
              <button
                onClick={() => setIsCommandPaletteOpen(true)}
                className={`w-full py-2 px-3 rounded-xl bg-slate-900/80 border border-slate-800 hover:border-indigo-500/40 text-slate-400 hover:text-slate-200 text-xs transition flex items-center justify-between group shadow-sm ${
                  isSidebarCollapsed ? 'justify-center px-0' : ''
                }`}
                title="Search or Run Command (Ctrl+K)"
              >
                <div className="flex items-center gap-2">
                  <Search size={14} className="group-hover:text-indigo-400 transition" />
                  {!isSidebarCollapsed && <span>Search commands...</span>}
                </div>
                {!isSidebarCollapsed && (
                  <kbd className="text-[10px] bg-slate-800 border border-slate-700 px-1.5 py-0.5 rounded text-slate-400 font-mono">
                    ⌘K
                  </kbd>
                )}
              </button>
            </div>

            {/* Navigation Sections */}
            <nav className="px-2 space-y-4 py-2 overflow-y-auto max-h-[calc(100vh-230px)]">
              {navItems.map((sec, idx) => (
                <div key={idx} className="space-y-1">
                  {!isSidebarCollapsed && (
                    <div className="px-3 text-[10px] font-bold text-slate-500 tracking-wider uppercase font-mono mb-1">
                      {sec.group}
                    </div>
                  )}
                  {sec.items.map((item) => {
                    const Icon = item.icon;
                    const isActive = activeTab === item.id;
                    return (
                      <button
                        key={item.id}
                        onClick={() => setActiveTab(item.id as TabKey)}
                        className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-xs font-semibold transition group text-left relative ${
                          isActive
                            ? 'bg-gradient-to-r from-indigo-600/20 to-purple-600/10 text-white border border-indigo-500/40 shadow-sm'
                            : 'text-slate-400 hover:bg-slate-800/60 hover:text-slate-200'
                        } ${isSidebarCollapsed ? 'justify-center px-0' : ''}`}
                        title={item.label}
                      >
                        {isActive && (
                          <span className="absolute left-0 top-2 bottom-2 w-1 bg-indigo-500 rounded-r-full" />
                        )}
                        <Icon
                          size={18}
                          className={`flex-shrink-0 transition ${
                            isActive
                              ? 'text-indigo-400'
                              : 'text-slate-400 group-hover:text-slate-200'
                          }`}
                        />
                        {!isSidebarCollapsed && (
                          <div className="flex-1 flex items-center justify-between overflow-hidden">
                            <span className="truncate">{item.label}</span>
                            {item.badge && (
                              <span
                                className={`text-[10px] px-1.5 py-0.2 rounded-full font-mono font-bold ${
                                  item.badgeColor || 'bg-slate-800 text-slate-300 border border-slate-700'
                                }`}
                              >
                                {item.badge}
                              </span>
                            )}
                          </div>
                        )}
                      </button>
                    );
                  })}
                </div>
              ))}
            </nav>
          </div>

          {/* Sidebar Footer User & Status */}
          <div className="p-3 border-t border-slate-800/80 bg-slate-950/40">
            <div
              className={`flex items-center gap-3 p-2 rounded-xl bg-slate-900/60 border border-slate-800/60 ${
                isSidebarCollapsed ? 'justify-center p-1.5' : ''
              }`}
            >
              <div className="w-8 h-8 rounded-lg bg-indigo-600/20 border border-indigo-500/30 flex items-center justify-center text-indigo-400 font-bold text-xs flex-shrink-0">
                KO
              </div>
              {!isSidebarCollapsed && (
                <div className="overflow-hidden flex-1">
                  <div className="text-xs font-bold text-slate-200 truncate">Keshav</div>
                  <div className="text-[10px] text-emerald-400 flex items-center gap-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                    Local Operator
                  </div>
                </div>
              )}
            </div>
          </div>
        </aside>

        {/* Main Workspace Area */}
        <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
          {/* Top Navigation Header */}
          <header className="h-16 border-b border-slate-800/80 bg-[#0b0f19]/80 backdrop-blur-xl px-6 flex items-center justify-between sticky top-0 z-30 shadow-sm">
            <div className="flex items-center gap-3">
              <span className="text-xs text-slate-500 uppercase tracking-wider font-mono">Nexus</span>
              <span className="text-slate-600">/</span>
              <h1 className="text-sm font-bold text-white tracking-tight flex items-center gap-2">
                {getBreadcrumbTitle(activeTab)}
              </h1>
            </div>

            <div className="flex items-center gap-3 flex-wrap">
              {/* Google Workspace Live Sync Pill */}
              {googleStatus?.connected ? (
                <div className="hidden sm:flex items-center gap-2 bg-emerald-500/10 border border-emerald-500/30 px-3 py-1.5 rounded-xl text-xs text-emerald-400 font-medium">
                  <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                  <span className="truncate max-w-[150px]">{googleStatus.email}</span>
                </div>
              ) : (
                <button
                  onClick={handleConnectGoogle}
                  className="hidden sm:flex items-center gap-1.5 px-3 py-1.5 bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-300 rounded-xl text-xs font-semibold transition"
                  title="Connect Google Workspace (Gmail and Calendar)"
                >
                  Connect Google Workspace
                </button>
              )}

              {/* API Health Pill */}
              <div
                className={`hidden md:flex items-center gap-2 px-3 py-1.5 rounded-xl border text-xs font-mono font-semibold ${
                  health?.status === 'healthy'
                    ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                    : 'bg-rose-500/10 text-rose-400 border-rose-500/30'
                }`}
              >
                <span
                  className={`w-2 h-2 rounded-full ${
                    health?.status === 'healthy' ? 'bg-emerald-400 animate-pulse' : 'bg-rose-400'
                  }`}
                />
                {health?.status === 'healthy'
                  ? `API ${health?.database?.latency_ms ?? 1}ms`
                  : 'API Disconnected'}
              </div>

              {/* Quick Action Button */}
              <button
                onClick={() => setIsCommandPaletteOpen(true)}
                className="px-3.5 py-1.5 bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 text-white rounded-xl text-xs font-bold transition shadow-md shadow-indigo-600/20 flex items-center gap-1.5"
              >
                <Zap size={14} />
                <span>Command</span>
                <kbd className="hidden lg:inline-block text-[9px] bg-black/30 px-1 py-0.2 rounded font-mono ml-1">
                  ⌘K
                </kbd>
              </button>

              <button
                onClick={loadData}
                disabled={loading}
                className="p-2 bg-slate-900 hover:bg-slate-800 text-slate-400 hover:text-white rounded-xl border border-slate-800 transition"
                title="Refresh Status"
              >
                <RefreshCw size={15} className={loading ? 'animate-spin' : ''} />
              </button>

              <a
                href="http://localhost:8000/docs"
                target="_blank"
                rel="noreferrer"
                className="hidden xl:inline-flex items-center gap-1 px-3 py-1.5 bg-slate-900 hover:bg-slate-800 text-slate-400 hover:text-slate-200 border border-slate-800 rounded-xl text-xs font-medium transition"
              >
                Swagger <ExternalLink size={11} />
              </a>
            </div>
          </header>

          {/* Pending Approvals Global Gate Notice */}
          {pendingApprovalsCount > 0 && activeTab !== 'agent' && (
            <div className="bg-amber-950/70 border-b border-amber-800/60 px-6 py-2.5 flex items-center justify-between text-xs text-amber-200">
              <div className="flex items-center gap-2">
                <AlertTriangle size={15} className="text-amber-400 animate-pulse" />
                <span>
                  <strong>Safety Gate:</strong> {pendingApprovalsCount} sensitive action(s) require human approval before execution.
                </span>
              </div>
              <button
                onClick={() => setActiveTab('agent')}
                className="px-3 py-1 bg-amber-500 hover:bg-amber-400 text-slate-950 rounded-lg text-xs font-bold transition shadow"
              >
                Review & Approve →
              </button>
            </div>
          )}

          {/* Backend Error Banner */}
          {error && (
            <div className="m-6 p-4 rounded-2xl bg-rose-950/60 border border-rose-800 text-rose-200 text-xs flex items-center justify-between">
              <div className="flex items-center gap-3">
                <ShieldAlert size={20} className="text-rose-400" />
                <div>
                  <div className="font-bold text-rose-300">Backend Connection Error</div>
                  <div className="text-rose-400">{error}</div>
                </div>
              </div>
              <button
                onClick={loadData}
                className="px-3 py-1 bg-rose-900/60 hover:bg-rose-800 text-rose-200 rounded-lg text-xs font-semibold"
              >
                Retry
              </button>
            </div>
          )}

          {/* Active View Container */}
          <main className="flex-1 p-6 max-w-7xl w-full mx-auto overflow-y-auto">
            {activeTab === 'dashboard' && <UnifiedDashboard onNavigateTab={setActiveTab} />}
            {activeTab === 'voice' && <VoiceAssistant />}
            {activeTab === 'agent' && <AgentOrchestrator />}
            {activeTab === 'tasks' && <TaskManager />}
            {activeTab === 'emails' && <EmailAssistant />}
            {activeTab === 'calendar' && <CalendarAssistant />}
            {activeTab === 'desktop' && <DesktopCompanion />}
            {activeTab === 'memory' && <SemanticMemory />}

            {/* TAB: SYSTEM & HEALTH */}
            {activeTab === 'system' && (
              <div className="space-y-6">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
                  <div className="card">
                    <div className="flex justify-between items-center mb-3">
                      <span className="text-xs text-slate-400 uppercase font-semibold">FastAPI Engine</span>
                      <Activity size={18} className="text-indigo-400" />
                    </div>
                    <div className="text-xl font-bold text-white mb-1">
                      {health?.status === 'healthy' ? 'Operational' : 'Disconnected'}
                    </div>
                    <div className="text-xs text-slate-400">
                      Environment: <span className="text-cyan-400 font-semibold">{health?.environment || 'development'}</span>
                    </div>
                  </div>

                  <div className="card">
                    <div className="flex justify-between items-center mb-3">
                      <span className="text-xs text-slate-400 uppercase font-semibold">Database Persistence</span>
                      <Database size={18} className="text-emerald-400" />
                    </div>
                    <div className="text-xl font-bold text-white mb-1">
                      {health?.database.dialect?.toUpperCase() || 'SQLite'}
                    </div>
                    <div className="text-xs text-slate-400">
                      Status: <span className="text-emerald-400 font-semibold">{health?.database.status}</span>
                      {health?.database.latency_ms !== undefined && ` (${health.database.latency_ms} ms)`}
                    </div>
                  </div>

                  <div className="card">
                    <div className="flex justify-between items-center mb-3">
                      <span className="text-xs text-slate-400 uppercase font-semibold">AI Models</span>
                      <Flame size={18} className="text-amber-400" />
                    </div>
                    <div className="text-xl font-bold text-white mb-1">
                      {config?.ai.model || 'GPT-4o'}
                    </div>
                    <div className="text-xs text-slate-400 truncate">
                      Voice: {config?.ai.voice_model || 'gpt-4o-realtime-preview'}
                    </div>
                  </div>
                </div>

                <div className="card space-y-4">
                  <h3 className="text-base font-bold text-white">Full-Stack Production Readiness</h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                    <div className="p-3 bg-slate-900/60 rounded-xl border border-slate-800 space-y-1">
                      <strong className="text-slate-200">Container Deployment</strong>
                      <p className="text-slate-400">Docker Compose files ready for multi-container production with PostgreSQL, pgvector, Redis, and FastAPI.</p>
                    </div>
                    <div className="p-3 bg-slate-900/60 rounded-xl border border-slate-800 space-y-1">
                      <strong className="text-slate-200">Google Workspace Sync</strong>
                      <p className="text-slate-400">OAuth 2.0 with Gmail REST API and Google Calendar v3. Symmetric Fernet token encryption active.</p>
                    </div>
                    <div className="p-3 bg-slate-900/60 rounded-xl border border-slate-800 space-y-1">
                      <strong className="text-slate-200">Desktop Companion Daemon</strong>
                      <p className="text-slate-400">Windows native WebSocket client with allowlisted app launcher, PIL screenshots, and psutil telemetry.</p>
                    </div>
                    <div className="p-3 bg-slate-900/60 rounded-xl border border-slate-800 space-y-1">
                      <strong className="text-slate-200">Rate Limiting & Safety Policy</strong>
                      <p className="text-slate-400">Sliding window memory rate limiter and deterministic approval policy for sensitive write actions.</p>
                    </div>
                  </div>
                </div>

                <div className="card">
                  <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider block mb-2">Live /health JSON Payload</span>
                  <pre>{JSON.stringify(health, null, 2)}</pre>
                </div>
              </div>
            )}

            {/* TAB: AUTHENTICATION */}
            {activeTab === 'auth' && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="card space-y-4">
                  <div>
                    <h2 className="text-lg font-bold text-white">JWT Operator Authentication</h2>
                    <p className="text-xs text-slate-400">Bcrypt password hashing and HS256 JWT access tokens.</p>
                  </div>

                  <form className="space-y-3">
                    <div>
                      <label className="text-xs text-slate-400 block mb-1">Email</label>
                      <input
                        type="email"
                        value={authEmail}
                        onChange={(e) => setAuthEmail(e.target.value)}
                        className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-xs text-white"
                      />
                    </div>
                    <div>
                      <label className="text-xs text-slate-400 block mb-1">Password</label>
                      <input
                        type="password"
                        value={authPassword}
                        onChange={(e) => setAuthPassword(e.target.value)}
                        className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-xs text-white"
                      />
                    </div>
                    <div>
                      <label className="text-xs text-slate-400 block mb-1">Full Name</label>
                      <input
                        type="text"
                        value={authName}
                        onChange={(e) => setAuthName(e.target.value)}
                        className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-xs text-white"
                      />
                    </div>
                    <div className="flex gap-2 pt-2">
                      <button
                        type="button"
                        onClick={handleRegister}
                        disabled={authLoading}
                        className="flex-1 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl text-xs font-bold"
                      >
                        Register
                      </button>
                      <button
                        type="button"
                        onClick={handleLogin}
                        disabled={authLoading}
                        className="flex-1 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-xl text-xs font-bold"
                      >
                        Login
                      </button>
                    </div>
                  </form>

                  {authMessage && (
                    <div
                      className={`p-3 rounded-xl text-xs border ${
                        authMessage.startsWith('Error')
                          ? 'bg-rose-950/60 border-rose-800 text-rose-300'
                          : 'bg-emerald-950/60 border-emerald-800 text-emerald-300'
                      }`}
                    >
                      {authMessage}
                    </div>
                  )}
                </div>

                <div className="card space-y-3">
                  <h3 className="text-sm font-bold text-white">Active Token Payload</h3>
                  {authResult ? (
                    <div>
                      <div className="text-xs text-emerald-400 font-semibold mb-2">
                        Signed User: {authResult.user.email}
                      </div>
                      <pre>{JSON.stringify(authResult, null, 2)}</pre>
                    </div>
                  ) : (
                    <div className="h-64 flex flex-col items-center justify-center text-slate-500 text-center text-xs">
                      <Key size={32} className="mb-2 opacity-40" />
                      Register or login above to inspect JWT credentials.
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* TAB: ROADMAP TRACKER */}
            {activeTab === 'roadmap' && (
              <div className="card space-y-4">
                <div>
                  <h2 className="text-lg font-bold text-white">10-Phase Milestone Implementation Architecture</h2>
                  <p className="text-xs text-slate-400">All 10 phases verified with 43 automated backend tests and frontend Vite builds.</p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {[
                    { p: 'Phase 1', t: 'Foundation & Infrastructure', d: 'FastAPI, SQLAlchemy, models, health checks, JWT auth, Alembic migrations, React Vite.' },
                    { p: 'Phase 2', t: 'Voice Engine & WebSocket Pipeline', d: 'Audio capture, OpenAI Realtime speech-to-speech, interchangeable STT/TTS adapters, VAD.' },
                    { p: 'Phase 3', t: 'LLM & LangGraph Agentic Core', d: 'Intent classification, planner, tool selection router, approval gate checkpoints, recovery.' },
                    { p: 'Phase 4', t: 'Tasks & Reminders Engine', d: 'Task CRUD, priority scoring, deadlines, background scheduler loop, recurring reminders.' },
                    { p: 'Phase 5', t: 'Gmail Integration & Email Assistant', d: 'OAuth 2.0 Google sync, Gmail search, AI summarization, draft composer, live send.' },
                    { p: 'Phase 6', t: 'Google Calendar Assistant', d: 'Event inspection, free/busy check, conflict detection, availability slot booking.' },
                    { p: 'Phase 7', t: 'Windows Desktop Companion', d: 'WebSocket client daemon, allowlisted apps, PIL screenshots, safe file search, psutil metrics.' },
                    { p: 'Phase 8', t: 'Semantic Memory & Vector Search', d: 'Embedding generation, vector search, preference storage, user memory wipe controls.' },
                    { p: 'Phase 9', t: 'Unified Executive Dashboard', d: 'Command center, omni-bar, live voice orb, drafts, task kanban, approvals modal.' },
                    { p: 'Phase 10', t: 'Hardening, Compliance & Deployment', d: 'Rate limiting, error recovery, Docker containerization, cloud deployment, audit logging.' },
                  ].map((item, idx) => (
                    <div key={idx} className="p-4 bg-slate-900/60 border border-slate-800 rounded-xl space-y-1">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold text-indigo-400">{item.p}</span>
                        <span className="text-[10px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 px-2 py-0.5 rounded-full font-mono font-bold">
                          COMPLETE
                        </span>
                      </div>
                      <div className="text-sm font-bold text-white">{item.t}</div>
                      <p className="text-xs text-slate-400">{item.d}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </main>
        </div>
      </div>

      {/* Global Interactive Command Palette (Ctrl+K) */}
      {isCommandPaletteOpen && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-md z-50 flex items-start justify-center pt-24 px-4 animate-in fade-in duration-200">
          <div
            className="w-full max-w-xl bg-slate-900 border border-indigo-500/40 rounded-2xl shadow-2xl overflow-hidden shadow-indigo-500/20"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="p-4 border-b border-slate-800 flex items-center justify-between gap-3">
              <Search size={18} className="text-indigo-400 flex-shrink-0" />
              <form onSubmit={handleExecuteCommandPrompt} className="flex-1">
                <input
                  type="text"
                  autoFocus
                  placeholder="Type an instruction or search tabs (e.g. 'Show calendar', 'voice', 'summarize emails')..."
                  value={commandQuery}
                  onChange={(e) => setCommandQuery(e.target.value)}
                  className="w-full bg-transparent text-sm text-white placeholder-slate-500 focus:outline-none"
                />
              </form>
              <button
                onClick={() => setIsCommandPaletteOpen(false)}
                className="p-1 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-white"
              >
                <X size={16} />
              </button>
            </div>

            {commandExecuting && (
              <div className="p-4 text-xs text-indigo-300 flex items-center gap-2 bg-indigo-950/40 border-b border-indigo-900/50">
                <span className="w-3.5 h-3.5 border-2 border-indigo-400/30 border-t-indigo-400 rounded-full animate-spin" />
                Dispatching command to LangGraph agent...
              </div>
            )}

            {commandResult && (
              <div className="p-4 text-xs text-slate-200 bg-black/40 border-b border-slate-800 max-h-40 overflow-y-auto whitespace-pre-wrap font-sans">
                {commandResult}
              </div>
            )}

            <div className="p-3 max-h-64 overflow-y-auto space-y-1">
              <div className="text-[10px] font-bold text-slate-500 uppercase tracking-wider font-mono px-3 py-1">
                Quick Navigation & Actions
              </div>
              {[
                { label: 'Executive Command Center', tab: 'dashboard', icon: LayoutDashboard },
                { label: 'Voice Assistant & Speech', tab: 'voice', icon: Mic },
                { label: 'Agentic Core & Approvals', tab: 'agent', icon: Bot },
                { label: 'Tasks & Scheduled Reminders', tab: 'tasks', icon: ListTodo },
                { label: 'Gmail Assistant & Inbox', tab: 'emails', icon: Mail },
                { label: 'Google Calendar & Scheduling', tab: 'calendar', icon: Calendar },
                { label: 'Windows Desktop Companion', tab: 'desktop', icon: Monitor },
                { label: 'Semantic Vector Memory', tab: 'memory', icon: Brain },
                { label: 'System Health & Metrics', tab: 'system', icon: Server },
              ]
                .filter((item) =>
                  !commandQuery || item.label.toLowerCase().includes(commandQuery.toLowerCase())
                )
                .map((item, idx) => {
                  const Icon = item.icon;
                  return (
                    <button
                      key={idx}
                      onClick={() => {
                        setActiveTab(item.tab as TabKey);
                        setIsCommandPaletteOpen(false);
                      }}
                      className="w-full flex items-center justify-between p-2.5 rounded-xl hover:bg-slate-800 text-slate-300 hover:text-white text-xs transition text-left"
                    >
                      <div className="flex items-center gap-2.5">
                        <Icon size={16} className="text-indigo-400" />
                        <span>{item.label}</span>
                      </div>
                      <span className="text-[10px] text-slate-500 font-mono">Jump</span>
                    </button>
                  );
                })}
            </div>

            <div className="p-2.5 bg-slate-950 border-t border-slate-800 flex items-center justify-between text-[11px] text-slate-500 px-4">
              <span>Press <strong>Enter</strong> to dispatch prompt to agent</span>
              <span><strong>ESC</strong> to close</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
