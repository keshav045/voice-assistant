import React, { useState, useEffect } from 'react';
import {
  Brain,
  Calendar,
  CheckCircle2,
  Clock,
  LayoutDashboard,
  Mail,
  Mic,
  Monitor,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  X,
  Bell,
  MessageSquare,
  BarChart3,
  Settings as SettingsIcon,
} from 'lucide-react';
import {
  fetchHealth,
  fetchSystemConfig,
  fetchApprovals,
  fetchGoogleAuthStatus,
  submitChatMessage,
  type GoogleAuthStatusDto,
} from './services/api';
import type { SystemHealth, SystemConfig } from './types';
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
  | 'calendar'
  | 'emails'
  | 'reminders'
  | 'desktop'
  | 'memory'
  | 'approvals'
  | 'analytics'
  | 'settings';

interface SidebarItem {
  id: TabKey;
  label: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  badge?: string | number | null;
  badgeStyle?: 'live' | 'count';
}

export function App() {
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [config, setConfig] = useState<SystemConfig | null>(null);
  const [, setLoading] = useState<boolean>(true);
  const [activeTab, setActiveTab] = useState<TabKey>('dashboard');
  const [pendingApprovalsCount, setPendingApprovalsCount] = useState<number>(3);
  const [googleStatus, setGoogleStatus] = useState<GoogleAuthStatusDto | null>(null);

  // Command Palette State (Ctrl+K)
  const [isCommandPaletteOpen, setIsCommandPaletteOpen] = useState<boolean>(false);
  const [commandQuery, setCommandQuery] = useState<string>('');
  const [commandExecuting, setCommandExecuting] = useState<boolean>(false);
  const [commandResult, setCommandResult] = useState<string | null>(null);

  // Notifications drawer state
  const [notificationsCount, setNotificationsCount] = useState<number>(4);
  const [showNotifications, setShowNotifications] = useState<boolean>(false);

  const loadData = async () => {
    setLoading(true);
    try {
      const [healthData, configData, approvalsData, googleData] = await Promise.all([
        fetchHealth().catch(() => null),
        fetchSystemConfig().catch(() => null),
        fetchApprovals('pending').catch(() => []),
        fetchGoogleAuthStatus().catch(() => null),
      ]);
      if (healthData) setHealth(healthData);
      if (configData) setConfig(configData);
      if (approvalsData) setPendingApprovalsCount(approvalsData.length || 3);
      if (googleData) setGoogleStatus(googleData);
    } catch (err: any) {
      console.warn('System telemetry check error:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 15000);

    // Global keyboard shortcut: Ctrl+K / Cmd+K
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setIsCommandPaletteOpen((prev) => !prev);
      }
      if (e.key === 'Escape') {
        setIsCommandPaletteOpen(false);
        setShowNotifications(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);

    return () => {
      clearInterval(interval);
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, []);

  const handleExecuteCommandPrompt = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!commandQuery.trim()) return;
    setCommandExecuting(true);
    setCommandResult(null);
    try {
      const res = await submitChatMessage(commandQuery.trim());
      setCommandResult(res.final_response || 'Execution finished successfully.');
      await loadData();
    } catch (err: any) {
      setCommandResult(`Error: ${err.message}`);
    } finally {
      setCommandExecuting(false);
    }
  };

  // 12 Sidebar Navigation Items matching Nexus OS v2.4 mockups exactly
  const sidebarItems: SidebarItem[] = [
    { id: 'dashboard', label: 'Overview', icon: LayoutDashboard },
    { id: 'voice', label: 'AI Voice Assistant', icon: Mic, badge: 'LIVE', badgeStyle: 'live' },
    { id: 'agent', label: 'AI Chat', icon: MessageSquare },
    { id: 'tasks', label: 'Tasks', icon: CheckCircle2 },
    { id: 'calendar', label: 'Calendar', icon: Calendar },
    { id: 'emails', label: 'Emails', icon: Mail },
    { id: 'reminders', label: 'Reminders', icon: Clock },
    { id: 'desktop', label: 'Desktop Agent', icon: Monitor },
    { id: 'memory', label: 'AI Memory', icon: Brain },
    { id: 'approvals', label: 'Approvals', icon: ShieldCheck, badge: pendingApprovalsCount, badgeStyle: 'count' },
    { id: 'analytics', label: 'Analytics', icon: BarChart3 },
    { id: 'settings', label: 'Settings', icon: SettingsIcon },
  ];

  return (
    <div className="min-h-screen bg-[#000000] text-[#f4f4f5] flex font-sans selection:bg-white selection:text-black">
      {/* Nexus Left Sidebar (Fixed 240px width) */}
      <aside className="w-60 bg-[#09090b] border-r border-[#222226] flex flex-col justify-between flex-shrink-0 sticky top-0 h-screen z-30">
        <div>
          {/* Logo & Version Header */}
          <div className="p-4 border-b border-[#1e1e24] flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-white text-black flex items-center justify-center font-bold shadow-md">
                <Sparkles size={16} />
              </div>
              <div className="flex items-baseline gap-1.5">
                <span className="font-bold text-base tracking-tight text-white">Nexus</span>
                <span className="text-[10px] font-mono text-[#a1a1aa] bg-[#18181b] border border-[#27272a] px-1.5 py-0.5 rounded">
                  OS v2.4
                </span>
              </div>
            </div>
          </div>

          {/* 12 Nav Items */}
          <nav className="p-2 space-y-1 overflow-y-auto max-h-[calc(100vh-140px)]">
            {sidebarItems.map((item) => {
              const Icon = item.icon;
              const isActive = activeTab === item.id;
              return (
                <button
                  key={item.id}
                  onClick={() => setActiveTab(item.id)}
                  className={`w-full flex items-center justify-between px-3 py-2 rounded-xl text-xs font-medium transition-all cursor-pointer ${
                    isActive
                      ? 'bg-[#18181b] text-white border border-[#38383e]'
                      : 'text-[#a1a1aa] hover:text-white hover:bg-[#121215] border border-transparent'
                  }`}
                >
                  <div className="flex items-center gap-2.5">
                    <Icon size={16} className={isActive ? 'text-white' : 'text-[#71717a]'} />
                    <span>{item.label}</span>
                  </div>

                  {item.badge && (
                    <>
                      {item.badgeStyle === 'live' ? (
                        <span className="flex items-center gap-1 text-[9px] font-mono font-bold bg-[#18181b] border border-[#3f3f46] text-white px-1.5 py-0.5 rounded-full">
                          <span className="w-1.5 h-1.5 rounded-full bg-white animate-mono-pulse" />
                          <span>{item.badge}</span>
                        </span>
                      ) : (
                        <span className="w-4 h-4 rounded-full bg-[#18181b] border border-[#3f3f46] text-white text-[10px] font-bold flex items-center justify-center">
                          {item.badge}
                        </span>
                      )}
                    </>
                  )}
                </button>
              );
            })}
          </nav>
        </div>

        {/* Bottom User Profile Card: Alex Vance */}
        <div className="p-3 border-t border-[#1e1e24] bg-[#0c0c0e]">
          <div className="flex items-center justify-between p-2 rounded-xl bg-[#121215] border border-[#222226]">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-full bg-[#18181b] border border-[#3f3f46] flex items-center justify-center font-bold text-xs text-white">
                AV
              </div>
              <div className="overflow-hidden">
                <div className="font-semibold text-xs text-white truncate">Alex Vance</div>
                <div className="text-[10px] text-[#71717a] truncate">VP of Product</div>
              </div>
            </div>
            <button
              onClick={() => setActiveTab('settings')}
              title="User Settings"
              className="text-[#71717a] hover:text-white transition-colors cursor-pointer p-1"
            >
              <SlidersHorizontal size={14} />
            </button>
          </div>
        </div>
      </aside>

      {/* Main App Content Area */}
      <div className="flex-1 flex flex-col min-w-0 bg-[#000000] overflow-y-auto h-screen">
        {/* Top Header Bar matching Nexus OS v2.4 mockups */}
        <header className="h-14 px-6 border-b border-[#222226] bg-[#09090b]/90 backdrop-blur-md flex items-center justify-between sticky top-0 z-20">
          {/* Left: Breadcrumbs */}
          <div className="flex items-center gap-2 text-xs font-mono text-[#a1a1aa]">
            <span className="hover:text-white cursor-pointer" onClick={() => setActiveTab('dashboard')}>
              Nexus
            </span>
            <span className="text-[#3f3f46]">&gt;</span>
            <span className="text-white font-medium capitalize">
              {activeTab === 'dashboard' ? 'Workspace' : activeTab}
            </span>
          </div>

          {/* Center: Search Bar with Ctrl+K */}
          <div
            onClick={() => setIsCommandPaletteOpen(true)}
            className="flex items-center gap-2.5 bg-[#121215] border border-[#27272a] hover:border-[#3f3f46] px-3.5 py-1.5 rounded-xl cursor-pointer w-72 md:w-88 transition-all"
          >
            <Search size={14} className="text-[#71717a]" />
            <span className="text-xs text-[#71717a] flex-1">Command or search...</span>
            <span className="font-mono text-[10px] text-[#a1a1aa] bg-[#18181b] border border-[#27272a] px-1.5 py-0.5 rounded">
              Ctrl+K
            </span>
          </div>

          {/* Right Controls: Mesh Status Pills, Notifications, Voice Session Button & Avatar */}
          <div className="flex items-center gap-3">
            {/* Status Pills */}
            <div className="hidden lg:flex items-center gap-2 text-xs text-[#a1a1aa] mr-1">
              <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-[#121215] border border-[#222226] text-[11px]">
                <span className="w-1.5 h-1.5 rounded-full bg-white" />
                Gmail
              </span>
              <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-[#121215] border border-[#222226] text-[11px]">
                <span className="w-1.5 h-1.5 rounded-full bg-white" />
                G-Cal
              </span>
              <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-[#121215] border border-[#222226] text-[11px]">
                <span className="w-1.5 h-1.5 rounded-full bg-white" />
                Win11 Agent
              </span>
            </div>

            {/* Notifications Bell */}
            <button
              onClick={() => setShowNotifications(!showNotifications)}
              className="relative w-8 h-8 rounded-lg bg-[#121215] border border-[#27272a] hover:border-[#3f3f46] text-[#a1a1aa] hover:text-white flex items-center justify-center cursor-pointer transition-colors"
            >
              <Bell size={14} />
              {notificationsCount > 0 && (
                <span className="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-white text-black text-[9px] font-bold flex items-center justify-center">
                  {notificationsCount}
                </span>
              )}
            </button>

            {/* Voice Session Launch Button */}
            <button
              onClick={() => setActiveTab('voice')}
              className="btn-secondary-mono !px-3 !py-1.5 !text-xs !rounded-xl flex items-center gap-1.5 cursor-pointer"
            >
              <Mic size={13} />
              <span>Voice Session</span>
            </button>

            {/* Profile Circle with Pro badge */}
            <div className="flex items-center gap-1.5 pl-1">
              <div className="w-8 h-8 rounded-full bg-white text-black font-bold flex items-center justify-center text-xs">
                A
              </div>
              <span className="text-[10px] font-mono text-[#a1a1aa] font-semibold">Pro</span>
            </div>
          </div>
        </header>

        {/* Notifications Drawer */}
        {showNotifications && (
          <div className="absolute right-6 top-16 w-80 bg-[#0c0c0e] border border-[#27272a] rounded-2xl shadow-2xl p-4 z-40 space-y-3">
            <div className="flex items-center justify-between pb-2 border-b border-[#222226]">
              <span className="text-xs font-bold text-white">System Notifications</span>
              <button
                onClick={() => setNotificationsCount(0)}
                className="text-[10px] text-[#a1a1aa] hover:text-white"
              >
                Clear all
              </button>
            </div>
            <div className="space-y-2 text-xs">
              <div className="p-2.5 rounded-lg bg-[#18181b] border border-[#27272a]">
                <div className="font-medium text-white">Autonomous Agent Consensus</div>
                <div className="text-[11px] text-[#a1a1aa]">3 tasks awaiting human signoff in approvals queue.</div>
              </div>
              <div className="p-2.5 rounded-lg bg-[#18181b] border border-[#27272a]">
                <div className="font-medium text-white">Google Workspace Sync</div>
                <div className="text-[11px] text-[#a1a1aa]">Calendar collision detected for 14:00 tomorrow.</div>
              </div>
            </div>
          </div>
        )}

        {/* Main Content Workspace */}
        <main className="p-6 flex-1">
          {activeTab === 'dashboard' && <UnifiedDashboard onNavigateTab={setActiveTab} />}
          {activeTab === 'voice' && <VoiceAssistant />}
          {activeTab === 'agent' && <AgentOrchestrator />}
          {activeTab === 'tasks' && <TaskManager />}
          {activeTab === 'calendar' && <CalendarAssistant />}
          {activeTab === 'emails' && <EmailAssistant />}
          {activeTab === 'reminders' && <TaskManager />}
          {activeTab === 'desktop' && <DesktopCompanion />}
          {activeTab === 'memory' && <SemanticMemory />}
          {activeTab === 'approvals' && <AgentOrchestrator />}
          {activeTab === 'analytics' && <UnifiedDashboard onNavigateTab={setActiveTab} />}
          {activeTab === 'settings' && (
            <div className="max-w-4xl mx-auto space-y-6">
              <div className="card-mono p-6 bg-[#0c0c0e] border border-[#27272a]">
                <h2 className="text-base font-bold text-white mb-2">Nexus System Settings & Telemetry</h2>
                <p className="text-xs text-[#a1a1aa] mb-4">
                  Autonomous runtime parameters, model orchestration keys, and daemon connections.
                </p>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                  <div className="p-3.5 rounded-xl bg-[#18181b] border border-[#27272a]">
                    <div className="font-bold text-white mb-1">Backend Engine</div>
                    <div className="text-[#a1a1aa]">FastAPI + LangGraph + Uvicorn</div>
                    <div className="font-mono text-[10px] text-white mt-1">
                      Status: {health?.status || 'Online'} (Port 8000) • DB: {health?.database.status || 'connected'}
                    </div>
                  </div>
                  <div className="p-3.5 rounded-xl bg-[#18181b] border border-[#27272a]">
                    <div className="font-bold text-white mb-1">Theme Architecture</div>
                    <div className="text-[#a1a1aa]">Nexus Monochrome Obsidian v2.4</div>
                    <div className="font-mono text-[10px] text-white mt-1">
                      Google Workspace: {googleStatus?.connected ? 'Connected' : 'Ready'} • Config: {config ? 'Loaded' : 'Default'}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}
        </main>
      </div>

      {/* Ctrl+K Command Palette Modal */}
      {isCommandPaletteOpen && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-[#0c0c0e] border border-[#27272a] rounded-2xl w-full max-w-xl shadow-2xl overflow-hidden">
            <div className="p-4 border-b border-[#222226] flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Search size={16} className="text-[#a1a1aa]" />
                <span className="text-xs font-semibold text-white">Nexus Command Palette</span>
              </div>
              <button
                onClick={() => setIsCommandPaletteOpen(false)}
                className="text-[#71717a] hover:text-white cursor-pointer"
              >
                <X size={16} />
              </button>
            </div>

            <form onSubmit={handleExecuteCommandPrompt} className="p-4 border-b border-[#222226]">
              <input
                type="text"
                autoFocus
                placeholder="Type an autonomous command or search (e.g. 'Summarize inbox', 'Find free slots tomorrow')..."
                value={commandQuery}
                onChange={(e) => setCommandQuery(e.target.value)}
                className="w-full bg-[#18181b] border border-[#27272a] rounded-xl px-3.5 py-2.5 text-xs text-white placeholder-[#71717a] focus:outline-none focus:border-white"
              />
              <div className="flex justify-end gap-2 mt-3">
                <button
                  type="button"
                  onClick={() => setIsCommandPaletteOpen(false)}
                  className="btn-secondary-mono !py-1 !px-3 !text-xs cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={commandExecuting || !commandQuery.trim()}
                  className="btn-primary-mono !py-1 !px-3 !text-xs cursor-pointer disabled:opacity-40"
                >
                  {commandExecuting ? 'Executing...' : 'Run Command'}
                </button>
              </div>
            </form>

            {commandResult && (
              <div className="p-4 bg-[#121215] text-xs space-y-1">
                <div className="text-[10px] uppercase font-bold text-[#a1a1aa]">Execution Output</div>
                <div className="text-white font-normal leading-relaxed">{commandResult}</div>
              </div>
            )}

            <div className="p-3 bg-[#09090b] text-[10px] text-[#71717a] flex justify-between items-center">
              <span>Press ESC to close</span>
              <span>Nexus OS v2.4 Global Sentinel</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
export default App;
