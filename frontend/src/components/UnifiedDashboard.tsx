import React, { useState, useEffect } from 'react';
import {
  Zap,
  CheckSquare,
  Calendar,
  Mail,
  Monitor,
  Shield,
  Check,
  CheckCircle2,
  Mic,
  Bot,
  Brain,
  LayoutGrid,
} from 'lucide-react';
import {
  fetchTasks,
  fetchDailySummary,
  fetchEmailDrafts,
  fetchCalendarEvents,
  fetchDesktopStatus,
  fetchApprovals,
  submitApprovalDecision,
  completeTask,
  submitChatMessage,
  type TaskDto,
  type DailySummaryDto,
  type EmailDraftDto,
  type CalendarEventDto,
  type DesktopStatusDto,
  type ApprovalDto,
} from '../services/api';

interface UnifiedDashboardProps {
  onNavigateTab: (tab: any) => void;
}

export const UnifiedDashboard: React.FC<UnifiedDashboardProps> = ({ onNavigateTab }) => {
  const [summary, setSummary] = useState<DailySummaryDto | null>(null);
  const [tasks, setTasks] = useState<TaskDto[]>([]);
  const [drafts, setDrafts] = useState<EmailDraftDto[]>([]);
  const [events, setEvents] = useState<CalendarEventDto[]>([]);
  const [desktopStatus, setDesktopStatus] = useState<DesktopStatusDto | null>(null);
  const [approvals, setApprovals] = useState<ApprovalDto[]>([]);

  // Omni-bar state
  const [omniPrompt, setOmniPrompt] = useState('');
  const [submittingPrompt, setSubmittingPrompt] = useState(false);
  const [aiResponse, setAiResponse] = useState<string | null>(null);
  const [notification, setNotification] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  useEffect(() => {
    loadDashboardData();
    const interval = setInterval(loadDashboardData, 10000);
    return () => clearInterval(interval);
  }, []);

  const showNotification = (type: 'success' | 'error', text: string) => {
    setNotification({ type, text });
    setTimeout(() => setNotification(null), 4500);
  };

  const loadDashboardData = async () => {
    try {
      const [summaryData, tasksData, draftsData, eventsData, desktopData, approvalsData] =
        await Promise.all([
          fetchDailySummary().catch(() => null),
          fetchTasks().catch(() => []),
          fetchEmailDrafts().catch(() => []),
          fetchCalendarEvents().catch(() => []),
          fetchDesktopStatus().catch(() => null),
          fetchApprovals('pending').catch(() => []),
        ]);

      if (summaryData) setSummary(summaryData);
      setTasks(tasksData);
      setDrafts(draftsData);
      setEvents(eventsData);
      if (desktopData) setDesktopStatus(desktopData);
      setApprovals(approvalsData);
    } catch (err: any) {
      console.error('Failed to load dashboard data:', err);
    }
  };

  const handleOmniSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!omniPrompt.trim()) return;

    setSubmittingPrompt(true);
    setAiResponse(null);
    try {
      const res = await submitChatMessage(omniPrompt);
      setAiResponse(res.final_response);
      showNotification('success', `Agent completed turn (Status: ${res.workflow_status}).`);
      setOmniPrompt('');
      await loadDashboardData();
    } catch (err: any) {
      showNotification('error', err.message || 'Execution failed');
    } finally {
      setSubmittingPrompt(false);
    }
  };

  const handleApprovalAction = async (approvalId: string, decision: 'approved' | 'rejected') => {
    try {
      const res = await submitApprovalDecision(approvalId, decision);
      showNotification('success', res.message);
      await loadDashboardData();
    } catch (err: any) {
      showNotification('error', err.message || 'Approval decision failed');
    }
  };

  const handleQuickCompleteTask = async (taskId: string) => {
    try {
      await completeTask(taskId);
      showNotification('success', 'Task marked completed.');
      await loadDashboardData();
    } catch (err: any) {
      showNotification('error', err.message || 'Failed to complete task');
    }
  };

  return (
    <div className="space-y-6">
      {/* Omni-Command Bar */}
      <div className="bg-gradient-to-r from-slate-900 via-indigo-950/40 to-slate-900 border border-indigo-500/30 p-5 rounded-2xl shadow-2xl space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-indigo-400 animate-pulse" />
            <span className="text-xs font-mono font-bold text-indigo-300 uppercase tracking-wider">
              Nexus Agentic Omni-Command Bar
            </span>
          </div>
          <span className="text-[11px] font-mono text-slate-400 bg-black/40 px-2 py-0.5 rounded border border-slate-800">
            9-Node LangGraph Core Active
          </span>
        </div>

        <form onSubmit={handleOmniSubmit} className="flex gap-2">
          <input
            type="text"
            placeholder="Type any command (e.g. 'Create urgent task for security audit', 'Show my schedule', 'Summarize unread emails')..."
            value={omniPrompt}
            onChange={(e) => setOmniPrompt(e.target.value)}
            className="flex-1 bg-black/40 border border-slate-700 rounded-xl px-4 py-3 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 shadow-inner"
          />
          <button
            type="submit"
            disabled={submittingPrompt}
            className="px-6 py-3 bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 text-white rounded-xl text-sm font-bold transition shadow-lg flex items-center gap-2 disabled:opacity-50"
          >
            {submittingPrompt ? (
              <>
                <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                Dispatching...
              </>
            ) : (
              <>
                <Zap className="w-4 h-4 mr-1.5" />
                Dispatch
              </>
            )}
          </button>
        </form>

        {aiResponse && (
          <div className="bg-black/50 p-4 rounded-xl border border-indigo-800/40 text-xs text-slate-200 font-sans leading-relaxed whitespace-pre-wrap">
            <div className="text-[10px] font-mono text-indigo-400 uppercase tracking-widest mb-1">
              Nexus Agent Response:
            </div>
            {aiResponse}
          </div>
        )}
      </div>

      {notification && (
        <div
          className={`p-4 rounded-xl text-sm border flex items-center justify-between ${
            notification.type === 'success'
              ? 'bg-emerald-950/60 border-emerald-800 text-emerald-300'
              : 'bg-rose-950/60 border-rose-800 text-rose-300'
          }`}
        >
          <span>{notification.text}</span>
          <button onClick={() => setNotification(null)} className="text-xs hover:underline ml-4">
            Dismiss
          </button>
        </div>
      )}

      {/* Top Real-time Executive Metrics */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div
          onClick={() => onNavigateTab('tasks')}
          className="bg-slate-900 border border-slate-800 hover:border-emerald-500/40 p-4 rounded-2xl cursor-pointer transition shadow-md"
        >
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs text-slate-400">Tasks Pending</span>
            <CheckSquare className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="text-2xl font-bold text-white">
            {summary ? summary.pending_count : tasks.filter((t) => t.status !== 'completed').length}
          </div>
          <span className="text-[11px] text-emerald-400 font-mono">
            {summary?.urgent_pending_count || 0} urgent item(s)
          </span>
        </div>

        <div
          onClick={() => onNavigateTab('calendar')}
          className="bg-slate-900 border border-slate-800 hover:border-blue-500/40 p-4 rounded-2xl cursor-pointer transition shadow-md"
        >
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs text-slate-400">Calendar Agenda</span>
            <Calendar className="w-4 h-4 text-blue-400" />
          </div>
          <div className="text-2xl font-bold text-white">{events.length}</div>
          <span className="text-[11px] text-blue-400 font-mono">Synced with Google Cal</span>
        </div>

        <div
          onClick={() => onNavigateTab('emails')}
          className="bg-slate-900 border border-slate-800 hover:border-rose-500/40 p-4 rounded-2xl cursor-pointer transition shadow-md"
        >
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs text-slate-400">Email Drafts & Outbox</span>
            <Mail className="w-4 h-4 text-rose-400" />
          </div>
          <div className="text-2xl font-bold text-white">{drafts.length}</div>
          <span className="text-[11px] text-rose-400 font-mono">
            {drafts.filter((d) => d.status === 'draft').length} pending dispatch
          </span>
        </div>

        <div
          onClick={() => onNavigateTab('desktop')}
          className="bg-slate-900 border border-slate-800 hover:border-cyan-500/40 p-4 rounded-2xl cursor-pointer transition shadow-md"
        >
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs text-slate-400">Windows Companion</span>
            <Monitor className="w-4 h-4 text-cyan-400" />
          </div>
          <div className="text-2xl font-bold text-white">
            {desktopStatus?.is_connected ? 'Active' : 'Standby'}
          </div>
          <span className="text-[11px] text-cyan-400 font-mono">
            {desktopStatus?.hostname || 'Windows 11 Daemon'}
          </span>
        </div>
      </div>

      {/* Two Column Layout: Operational Modules */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Approvals Queue & Agenda */}
        <div className="lg:col-span-7 space-y-6">
          {/* Pending Approval Gate Queue */}
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div>
                <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
                  <Shield className="w-4 h-4 text-amber-400" /> Human-in-the-Loop Approval Queue
                  {approvals.length > 0 && (
                    <span className="text-[10px] bg-amber-500/20 text-amber-300 border border-amber-500/40 px-2 py-0.5 rounded-full font-mono">
                      {approvals.length} Action(s) Waiting
                    </span>
                  )}
                </h3>
                <p className="text-xs text-slate-400">
                  Sensitive tool actions (email send, task deletion, desktop exec) paused at policy gate.
                </p>
              </div>
            </div>

            {approvals.length === 0 ? (
              <div className="text-center py-6 text-xs text-slate-500 bg-slate-950/40 rounded-xl border border-slate-800 flex items-center justify-center gap-1.5">
                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                <span>No pending approval requests. Agent operations running normally.</span>
              </div>
            ) : (
              <div className="space-y-3">
                {approvals.map((req) => (
                  <div
                    key={req.id}
                    className="p-4 rounded-xl bg-amber-500/5 border border-amber-500/30 flex flex-col md:flex-row md:items-center justify-between gap-3"
                  >
                    <div>
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-xs font-mono font-bold text-amber-400">
                          {req.tool_name}
                        </span>
                        <span className="text-[10px] text-slate-400">
                          {new Date(req.created_at).toLocaleTimeString()}
                        </span>
                      </div>
                      <p className="text-xs text-slate-200 font-semibold">{req.action_summary}</p>
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      <button
                        onClick={() => handleApprovalAction(req.id, 'rejected')}
                        className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-xs font-medium transition"
                      >
                        Reject
                      </button>
                      <button
                        onClick={() => handleApprovalAction(req.id, 'approved')}
                        className="px-3.5 py-1.5 bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold rounded-lg text-xs transition shadow-sm"
                      >
                        Approve Action
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Today's Scheduled Agenda */}
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div>
                <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
                  <Calendar className="w-4 h-4 text-blue-400" /> Upcoming Agenda & Meetings
                </h3>
                <p className="text-xs text-slate-400">Synchronized meetings and focus time blocks.</p>
              </div>
              <button
                onClick={() => onNavigateTab('calendar')}
                className="text-xs text-blue-400 hover:underline"
              >
                View Calendar →
              </button>
            </div>

            {events.length === 0 ? (
              <div className="text-center py-8 text-xs text-slate-500">
                No events scheduled.
              </div>
            ) : (
              <div className="space-y-2">
                {events.slice(0, 4).map((evt) => (
                  <div
                    key={evt.id}
                    className="p-3 rounded-xl bg-slate-950/60 border border-slate-800 flex items-center justify-between text-xs"
                  >
                    <div>
                      <div className="font-bold text-slate-200">{evt.title}</div>
                      <div className="text-[11px] text-slate-400 font-mono">
                        {new Date(evt.start_time).toLocaleDateString([], { month: 'short', day: 'numeric' })}{' '}
                        • {new Date(evt.start_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} -{' '}
                        {new Date(evt.end_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </div>
                    </div>
                    {evt.location && (
                      <span className="text-[10px] text-slate-400 bg-slate-800 px-2 py-0.5 rounded border border-slate-700 truncate max-w-[150px]">
                        {evt.location}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Right Column: Urgent Tasks & Quick Launch */}
        <div className="lg:col-span-5 space-y-6">
          {/* Urgent Action Items */}
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div>
                <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
                  <Zap className="w-4 h-4 text-amber-400" /> Urgent Tasks & Action Items
                </h3>
                <p className="text-xs text-slate-400">High priority tasks requiring completion.</p>
              </div>
              <button
                onClick={() => onNavigateTab('tasks')}
                className="text-xs text-emerald-400 hover:underline"
              >
                Kanban View →
              </button>
            </div>

            <div className="space-y-2">
              {tasks
                .filter((t) => t.status !== 'completed')
                .slice(0, 5)
                .map((task) => (
                  <div
                    key={task.id}
                    className="p-3 rounded-xl bg-slate-950/60 border border-slate-800 flex items-center justify-between gap-3 text-xs hover:border-slate-700 transition"
                  >
                    <div className="truncate">
                      <span
                        className={`text-[10px] font-mono uppercase mr-2 px-1.5 py-0.5 rounded border ${
                          task.priority === 'urgent'
                            ? 'bg-rose-500/10 text-rose-400 border-rose-500/30'
                            : 'bg-amber-500/10 text-amber-400 border-amber-500/30'
                        }`}
                      >
                        {task.priority}
                      </span>
                      <span className="text-slate-200 font-medium">{task.title}</span>
                    </div>

                    <button
                      onClick={() => handleQuickCompleteTask(task.id)}
                      className="inline-flex items-center gap-1 px-2 py-1 rounded bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 text-[10px] font-semibold transition shrink-0"
                    >
                      <Check className="w-3 h-3" />
                      Done
                    </button>
                  </div>
                ))}
            </div>
          </div>

          {/* Assistant Navigation Hub */}
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-3">
            <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
              <LayoutGrid className="w-4 h-4 text-indigo-400" /> Direct Module Switcher
            </h3>
            <div className="grid grid-cols-2 gap-2 text-xs">
              <button
                onClick={() => onNavigateTab('voice')}
                className="p-3 rounded-xl bg-slate-800/60 hover:bg-slate-800 border border-slate-700/60 text-slate-200 text-left transition"
              >
                <div className="flex items-center gap-1.5 font-semibold">
                  <Mic className="w-3.5 h-3.5 text-indigo-400" /> Live Voice
                </div>
                <p className="text-[10px] text-slate-400 mt-0.5">Speech-to-speech engine</p>
              </button>
              <button
                onClick={() => onNavigateTab('agent')}
                className="p-3 rounded-xl bg-slate-800/60 hover:bg-slate-800 border border-slate-700/60 text-slate-200 text-left transition"
              >
                <div className="flex items-center gap-1.5 font-semibold">
                  <Bot className="w-3.5 h-3.5 text-indigo-400" /> Agent Core
                </div>
                <p className="text-[10px] text-slate-400 mt-0.5">LangGraph 9-node orchestrator</p>
              </button>
              <button
                onClick={() => onNavigateTab('emails')}
                className="p-3 rounded-xl bg-slate-800/60 hover:bg-slate-800 border border-slate-700/60 text-slate-200 text-left transition"
              >
                <div className="flex items-center gap-1.5 font-semibold">
                  <Mail className="w-3.5 h-3.5 text-rose-400" /> Gmail Hub
                </div>
                <p className="text-[10px] text-slate-400 mt-0.5">Summarization & drafts</p>
              </button>
              <button
                onClick={() => onNavigateTab('memory')}
                className="p-3 rounded-xl bg-slate-800/60 hover:bg-slate-800 border border-slate-700/60 text-slate-200 text-left transition"
              >
                <div className="flex items-center gap-1.5 font-semibold">
                  <Brain className="w-3.5 h-3.5 text-purple-400" /> Vector Memory
                </div>
                <p className="text-[10px] text-slate-400 mt-0.5">Semantic cosine search</p>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

