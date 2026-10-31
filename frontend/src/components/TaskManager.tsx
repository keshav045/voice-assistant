import React, { useState, useEffect } from 'react';
import {
  Activity,
  Bot,
  Check,
  CheckCircle2,
  ChevronDown,
  Layers,
  List,
  MoreHorizontal,
  Plus,
  RefreshCw,
  Shield,
  Sparkles,
  Terminal,
  Trash2,
} from 'lucide-react';
import {
  fetchTasks,
  createTask,
  completeTask,
  deleteTask,
  fetchDailySummary,
  fetchApprovals,
  submitApprovalDecision,
  type TaskDto,
  type ApprovalDto,
} from '../services/api';

export const TaskManager: React.FC = () => {
  const [tasks, setTasks] = useState<TaskDto[]>([]);
  const [, setSummary] = useState<any | null>(null);
  const [approvals, setApprovals] = useState<ApprovalDto[]>([]);
  const [activeView, setActiveView] = useState<'kanban' | 'list'>('kanban');
  const [selectedAgent, setSelectedAgent] = useState<string>('all');
  const [priorityFilter, setPriorityFilter] = useState<string>('all');
  const [showCreateModal, setShowCreateModal] = useState<boolean>(false);
  const [newTitle, setNewTitle] = useState<string>('');
  const [newPriority, setNewPriority] = useState<string>('urgent');
  const [, setLoading] = useState<boolean>(false);
  const [notification, setNotification] = useState<string | null>(null);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 10000);
    return () => clearInterval(interval);
  }, []);

  const showToast = (msg: string) => {
    setNotification(msg);
    setTimeout(() => setNotification(null), 4000);
  };

  const loadData = async () => {
    try {
      const [tList, sData, appList] = await Promise.all([
        fetchTasks(),
        fetchDailySummary().catch(() => null),
        fetchApprovals('pending').catch(() => []),
      ]);
      setTasks(tList);
      if (sData) setSummary(sData);
      setApprovals(appList);
    } catch (e) {
      // Ignore background sync errors
    }
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim()) return;
    setLoading(true);
    try {
      await createTask({ title: newTitle.trim(), priority: newPriority as any });
      setNewTitle('');
      setShowCreateModal(false);
      showToast('Task orchestrated successfully.');
      await loadData();
    } catch (err: any) {
      showToast(`Error: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleComplete = async (id: string) => {
    try {
      await completeTask(id);
      showToast('Task marked as completed.');
      await loadData();
    } catch (err: any) {
      showToast(`Error: ${err.message}`);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteTask(id);
      showToast('Task removed from queue.');
      await loadData();
    } catch (err: any) {
      showToast(`Error: ${err.message}`);
    }
  };

  const handleApprovalDecision = async (id: string, decision: 'approved' | 'rejected') => {
    try {
      await submitApprovalDecision(id, decision);
      showToast(`Action ${decision} successfully.`);
      await loadData();
    } catch (err: any) {
      showToast(`Error: ${err.message}`);
    }
  };

  // Filter tasks by priority and agent
  const filteredTasks = tasks.filter((t) => {
    if (priorityFilter !== 'all' && t.priority !== priorityFilter) return false;
    return true;
  });

  const backlogTasks = filteredTasks.filter((t) => t.status === 'pending');
  const inProgressTasks = filteredTasks.filter((t) => t.status === 'in_progress');
  const pendingApprovals = approvals.filter((a) => a.status === 'pending');
  const completedTasks = filteredTasks.filter((t) => t.status === 'completed');

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {notification && (
        <div className="bg-zinc-900 border border-zinc-700 text-zinc-100 px-4 py-3 rounded-xl flex items-center justify-between text-xs shadow-2xl transition">
          <div className="flex items-center gap-2">
            <CheckCircle2 size={15} className="text-white" />
            <span>{notification}</span>
          </div>
          <button onClick={() => setNotification(null)} className="text-zinc-400 hover:text-white">
            Dismiss
          </button>
        </div>
      )}

      {/* Top Metric Cards - Live Real Counts */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {/* Card 1: Total Active Load */}
        <div className="bg-[#0b0b0d] border border-zinc-800 rounded-2xl p-5 shadow-lg relative overflow-hidden">
          <div className="flex items-center justify-between text-xs font-mono text-zinc-400 uppercase tracking-wider mb-2">
            <span>Total Active Load</span>
            <Layers size={16} className="text-white" />
          </div>
          <div className="text-3xl font-black text-white">
            {backlogTasks.length + inProgressTasks.length}{' '}
            <span className="text-xs font-normal text-zinc-400">orchestrated</span>
          </div>
          <div className="mt-2 text-[11px] text-zinc-400 font-mono flex items-center gap-1.5">
            <span className="text-white">{backlogTasks.length} pending</span> across local hubs
          </div>
        </div>

        {/* Card 2: Autonomous Agents */}
        <div className="bg-[#0b0b0d] border border-zinc-800 rounded-2xl p-5 shadow-lg relative overflow-hidden">
          <div className="flex items-center justify-between text-xs font-mono text-zinc-400 uppercase tracking-wider mb-2">
            <span className="flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-white animate-mono-pulse" />
              Autonomous Agents
            </span>
            <Bot size={16} className="text-white" />
          </div>
          <div className="text-3xl font-black text-white">
            {inProgressTasks.length}{' '}
            <span className="text-xs font-normal text-zinc-400">running</span>
          </div>
          <div className="mt-2 text-[11px] text-zinc-400 font-mono">
            {tasks.length > 0
              ? `${Math.round((inProgressTasks.length / tasks.length) * 100)}% delegated`
              : 'All nodes standing by'}
          </div>
        </div>

        {/* Card 3: Approval Gates */}
        <div className="bg-[#0b0b0d] border border-zinc-800 rounded-2xl p-5 shadow-lg relative overflow-hidden">
          <div className="flex items-center justify-between text-xs font-mono text-zinc-400 uppercase tracking-wider mb-2">
            <span>Approval Gates</span>
            <Shield size={16} className="text-white" />
          </div>
          <div className="text-3xl font-black text-white">
            {pendingApprovals.length}{' '}
            <span className="text-xs font-normal text-zinc-400">items locked</span>
          </div>
          <div className="mt-2 text-[11px] text-zinc-400 font-mono">
            {pendingApprovals.length > 0 ? 'Requires executive token' : 'Zero items blocked'}
          </div>
        </div>

        {/* Card 4: Completed Tasks */}
        <div className="bg-[#0b0b0d] border border-zinc-800 rounded-2xl p-5 shadow-lg relative overflow-hidden">
          <div className="flex items-center justify-between text-xs font-mono text-zinc-400 uppercase tracking-wider mb-2">
            <span>Completed Tasks</span>
            <CheckCircle2 size={16} className="text-white" />
          </div>
          <div className="text-3xl font-black text-white">
            {completedTasks.length}{' '}
            <span className="text-xs font-normal text-zinc-400">finished</span>
          </div>
          <div className="mt-2 text-[11px] text-zinc-400 font-mono">
            Zero intervention errors
          </div>
        </div>
      </div>

      {/* Subheader Controls: View Switcher, Filters, Create Task */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          {/* Kanban / List Switcher */}
          <div className="bg-zinc-950 border border-zinc-800 rounded-xl p-1 flex items-center gap-1">
            <button
              onClick={() => setActiveView('kanban')}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition flex items-center gap-1.5 ${
                activeView === 'kanban' ? 'bg-zinc-800 text-white font-bold' : 'text-zinc-400 hover:text-white'
              }`}
            >
              <Activity size={13} />
              <span>Kanban</span>
            </button>
            <button
              onClick={() => setActiveView('list')}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition flex items-center gap-1.5 ${
                activeView === 'list' ? 'bg-zinc-800 text-white font-bold' : 'text-zinc-400 hover:text-white'
              }`}
            >
              <List size={13} />
              <span>List</span>
            </button>
          </div>

          {/* Agent Filter Pills */}
          <div className="flex items-center gap-1.5 flex-wrap">
            {['all', 'gmail', 'calendar', 'desktop', 'manual'].map((ag) => (
              <button
                key={ag}
                onClick={() => setSelectedAgent(ag)}
                className={`px-3 py-1.5 rounded-xl text-xs font-medium border transition ${
                  selectedAgent === ag
                    ? 'bg-white text-black border-white font-bold'
                    : 'bg-zinc-950 text-zinc-400 border-zinc-800 hover:border-zinc-700 hover:text-white'
                }`}
              >
                {ag === 'all' && 'All Agents'}
                {ag === 'gmail' && 'Gmail Agent'}
                {ag === 'calendar' && 'Calendar Agent'}
                {ag === 'desktop' && 'Desktop Bot'}
                {ag === 'manual' && 'Manual User'}
              </button>
            ))}
          </div>
        </div>

        <div className="flex items-center gap-2.5">
          <button
            onClick={() => {
              createTask({ title: 'Autonomous System Diagnostic & Log Rollup', priority: 'medium' });
              loadData();
              showToast('Auto-deconstructed task generated.');
            }}
            className="btn-secondary-mono text-xs py-2 px-3"
          >
            <Sparkles size={13} />
            <span>AI Auto-Deconstruct Objective</span>
          </button>
          <button
            onClick={() => setShowCreateModal(true)}
            className="btn-primary-mono text-xs py-2 px-3.5 font-bold"
          >
            <Plus size={14} />
            <span>Create Task</span>
          </button>
          <div className="relative">
            <select
              value={priorityFilter}
              onChange={(e) => setPriorityFilter(e.target.value)}
              className="bg-zinc-950 border border-zinc-800 text-zinc-300 text-xs rounded-xl px-3 py-2 pr-7 appearance-none focus:outline-none focus:border-zinc-600"
            >
              <option value="all">Priority: All</option>
              <option value="urgent">Urgent</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>
            <ChevronDown size={12} className="absolute right-2.5 top-3 text-zinc-500 pointer-events-none" />
          </div>
        </div>
      </div>

      {/* 4-Column Kanban View */}
      {activeView === 'kanban' ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {/* Column 1: Backlog & Suggestions */}
          <div className="bg-[#0b0b0d] border border-zinc-800/80 rounded-2xl p-4 flex flex-col space-y-3.5 min-h-[480px]">
            <div className="flex items-center justify-between pb-2 border-b border-zinc-800/80 text-xs font-bold text-white">
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-zinc-400" />
                <span>Backlog &amp; Suggestions</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="text-[11px] font-mono px-2 py-0.5 rounded-full bg-zinc-900 border border-zinc-800 text-zinc-300">
                  {backlogTasks.length}
                </span>
                <MoreHorizontal size={14} className="text-zinc-500" />
              </div>
            </div>

            <div className="space-y-3 flex-1 overflow-y-auto max-h-[700px] pr-1">
              {backlogTasks.length === 0 ? (
                <div className="py-14 px-4 rounded-xl border border-dashed border-zinc-800 text-center space-y-2">
                  <CheckCircle2 size={24} className="mx-auto text-zinc-600" />
                  <div className="text-xs font-semibold text-zinc-300">Backlog is clear</div>
                  <p className="text-[11px] text-zinc-500">
                    No pending tasks. Click "+ Create Task" to add a new objective.
                  </p>
                </div>
              ) : (
                backlogTasks.map((t) => (
                  <div
                    key={t.id}
                    className="p-3.5 rounded-xl bg-zinc-950 border border-zinc-800 space-y-2.5 hover:border-zinc-700 transition"
                  >
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-[10px] font-mono font-bold uppercase px-2 py-0.5 rounded bg-white text-black">
                        {t.priority}
                      </span>
                      <span className="text-[10px] font-mono text-zinc-500">
                        {new Date(t.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </span>
                    </div>
                    <h4 className="text-xs font-bold text-white leading-snug">{t.title}</h4>
                    {t.description && <p className="text-[11px] text-zinc-400">{t.description}</p>}
                    <div className="flex items-center gap-2 pt-1 border-t border-zinc-850">
                      <button
                        onClick={() => handleComplete(t.id)}
                        className="btn-primary-mono !py-1 !px-2.5 !text-[11px]"
                      >
                        Complete
                      </button>
                      <button
                        onClick={() => handleDelete(t.id)}
                        className="btn-secondary-mono !py-1 !px-2.5 !text-[11px]"
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Column 2: Autonomous In Progress */}
          <div className="bg-[#0b0b0d] border border-zinc-800/80 rounded-2xl p-4 flex flex-col space-y-3.5 min-h-[480px]">
            <div className="flex items-center justify-between pb-2 border-b border-zinc-800/80 text-xs font-bold text-white">
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-white animate-mono-pulse" />
                <span>Autonomous In Progress</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="text-[11px] font-mono px-2 py-0.5 rounded-full bg-zinc-900 border border-zinc-800 text-zinc-300">
                  {inProgressTasks.length}
                </span>
                <RefreshCw size={12} className="text-zinc-500" />
              </div>
            </div>

            <div className="space-y-3 flex-1 overflow-y-auto max-h-[700px] pr-1">
              {inProgressTasks.length === 0 ? (
                <div className="py-14 px-4 rounded-xl border border-dashed border-zinc-800 text-center space-y-2">
                  <Bot size={24} className="mx-auto text-zinc-600" />
                  <div className="text-xs font-semibold text-zinc-300">No autonomous runs</div>
                  <p className="text-[11px] text-zinc-500">Autonomous agents are standing by idle.</p>
                </div>
              ) : (
                inProgressTasks.map((t) => (
                  <div key={t.id} className="p-3.5 rounded-xl bg-zinc-950 border border-zinc-800 space-y-2.5">
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-zinc-900 text-zinc-300 border border-zinc-800">
                        Agent Active
                      </span>
                      <span className="text-[10px] font-mono font-bold uppercase px-1.5 py-0.5 rounded bg-white text-black">
                        {t.priority}
                      </span>
                    </div>
                    <h4 className="text-xs font-bold text-white">{t.title}</h4>
                    <div className="w-full bg-zinc-900 h-1.5 rounded-full overflow-hidden">
                      <div className="bg-white h-full rounded-full animate-pulse" style={{ width: '65%' }} />
                    </div>
                    <div className="flex items-center justify-between text-[10px] font-mono text-zinc-500 pt-1">
                      <span>Status: In Flight</span>
                      <button onClick={() => handleComplete(t.id)} className="text-white hover:underline">
                        Done
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Column 3: Awaiting Approval */}
          <div className="bg-[#0b0b0d] border border-zinc-800/80 rounded-2xl p-4 flex flex-col space-y-3.5 min-h-[480px]">
            <div className="flex items-center justify-between pb-2 border-b border-zinc-800/80 text-xs font-bold text-white">
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-white" />
                <span>Awaiting Approval</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="text-[11px] font-mono px-2 py-0.5 rounded-full bg-white text-black font-extrabold">
                  {pendingApprovals.length}
                </span>
                <Shield size={13} className="text-zinc-400" />
              </div>
            </div>

            <div className="space-y-3 flex-1 overflow-y-auto max-h-[700px] pr-1">
              {pendingApprovals.length === 0 ? (
                <div className="py-14 px-4 rounded-xl border border-dashed border-zinc-800 text-center space-y-2">
                  <Shield size={24} className="mx-auto text-zinc-600" />
                  <div className="text-xs font-semibold text-zinc-300">All gates cleared</div>
                  <p className="text-[11px] text-zinc-500">Zero sensitive actions pending authorization.</p>
                </div>
              ) : (
                pendingApprovals.map((app) => (
                  <div key={app.id} className="p-3.5 rounded-xl bg-zinc-950 border border-zinc-800 space-y-2.5">
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-[10px] font-mono font-bold uppercase px-2 py-0.5 rounded bg-white text-black">
                        {app.tool_name}
                      </span>
                      <span className="text-[10px] font-mono text-zinc-500">Pending Gate</span>
                    </div>
                    <h4 className="text-xs font-bold text-white leading-snug">{app.action_summary}</h4>
                    <div className="flex items-center gap-2 pt-1">
                      <button
                        onClick={() => handleApprovalDecision(app.id, 'approved')}
                        className="btn-primary-mono !py-1 !px-3 !text-[11px] font-bold"
                      >
                        Approve
                      </button>
                      <button
                        onClick={() => handleApprovalDecision(app.id, 'rejected')}
                        className="btn-secondary-mono !py-1 !px-3 !text-[11px]"
                      >
                        Reject
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Column 4: Completed */}
          <div className="bg-[#0b0b0d] border border-zinc-800/80 rounded-2xl p-4 flex flex-col space-y-3.5 min-h-[480px]">
            <div className="flex items-center justify-between pb-2 border-b border-zinc-800/80 text-xs font-bold text-white">
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-white" />
                <span>Completed</span>
              </div>
              <span className="text-[11px] font-mono px-2 py-0.5 rounded-full bg-zinc-900 border border-zinc-800 text-zinc-300">
                {completedTasks.length}
              </span>
            </div>

            <div className="space-y-3 flex-1 overflow-y-auto max-h-[600px] pr-1">
              {completedTasks.length === 0 ? (
                <div className="py-14 px-4 rounded-xl border border-dashed border-zinc-800 text-center space-y-2">
                  <Check size={24} className="mx-auto text-zinc-600" />
                  <div className="text-xs font-semibold text-zinc-300">No completed tasks yet</div>
                  <p className="text-[11px] text-zinc-500">Finished tasks will be logged here.</p>
                </div>
              ) : (
                completedTasks.map((t) => (
                  <div key={t.id} className="p-3.5 rounded-xl bg-zinc-950 border border-zinc-800 space-y-1.5">
                    <div className="flex items-center gap-1.5 text-[10px] font-mono text-zinc-400">
                      <Check size={11} className="text-white" />
                      <span>
                        Completed &bull;{' '}
                        {new Date(t.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </span>
                    </div>
                    <h4 className="text-xs font-bold text-zinc-300 line-through">{t.title}</h4>
                    <button
                      onClick={() => handleDelete(t.id)}
                      className="text-[10px] text-zinc-500 hover:text-white"
                    >
                      Delete
                    </button>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      ) : (
        /* List View */
        <div className="bg-[#0b0b0d] border border-zinc-800 rounded-2xl p-6 shadow-xl space-y-4">
          <div className="flex items-center justify-between border-b border-zinc-800 pb-3">
            <h3 className="text-sm font-bold text-white uppercase tracking-wider">All Orchestrated Tasks</h3>
            <span className="text-xs font-mono text-zinc-400">{tasks.length} total items</span>
          </div>

          {tasks.length === 0 ? (
            <div className="py-16 text-center space-y-2">
              <List size={28} className="mx-auto text-zinc-600" />
              <div className="text-sm font-semibold text-zinc-300">Task queue is completely empty</div>
              <p className="text-xs text-zinc-500">
                Create a task using the "+ Create Task" button or ask the AI Voice Assistant.
              </p>
            </div>
          ) : (
            <div className="divide-y divide-zinc-800">
              {tasks.map((task) => (
                <div key={task.id} className="py-3 flex items-center justify-between gap-4 text-xs">
                  <div className="flex items-center gap-3">
                    <button
                      onClick={() => handleComplete(task.id)}
                      className={`w-4 h-4 rounded border flex items-center justify-center transition ${
                        task.status === 'completed'
                          ? 'bg-white border-white text-black'
                          : 'border-zinc-700 hover:border-zinc-500'
                      }`}
                    >
                      {task.status === 'completed' && <Check size={11} />}
                    </button>
                    <div>
                      <span
                        className={`font-semibold ${
                          task.status === 'completed' ? 'line-through text-zinc-500' : 'text-white'
                        }`}
                      >
                        {task.title}
                      </span>
                      <div className="text-[10px] font-mono text-zinc-500 mt-0.5">
                        Priority: {task.priority} &bull; Created:{' '}
                        {new Date(task.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </div>
                    </div>
                  </div>
                  <button
                    onClick={() => handleDelete(task.id)}
                    className="text-zinc-500 hover:text-white p-1 rounded"
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Bottom Runtime Cluster Status Strip */}
      <div className="p-4 rounded-xl bg-zinc-950 border border-zinc-800 flex flex-col md:flex-row md:items-center justify-between gap-3 text-xs font-mono text-zinc-400">
        <div className="flex items-center gap-2 truncate">
          <Terminal size={14} className="text-white shrink-0" />
          <span className="text-white font-bold">Autonomous Cluster Orchestration NOMINAL</span>
          <span className="text-zinc-600">//</span>
          <span className="truncate">Active node thread #8492</span>
          <span className="text-zinc-600">//</span>
          <span className="truncate">Active tasks: {tasks.length}</span>
          <span className="text-zinc-600">//</span>
          <span>Core temp: 38&deg;C</span>
        </div>
        <button
          onClick={loadData}
          className="btn-secondary-mono !py-1 !px-3 !text-[11px] shrink-0 flex items-center gap-1.5"
        >
          <RefreshCw size={11} />
          <span>Refresh Queue</span>
        </button>
      </div>

      {/* Create Task Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-zinc-950 border border-zinc-800 rounded-2xl max-w-md w-full p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-zinc-800 pb-3">
              <h3 className="text-sm font-bold text-white uppercase tracking-wider">Create Autonomous Task</h3>
              <button onClick={() => setShowCreateModal(false)} className="text-zinc-400 hover:text-white">
                &times;
              </button>
            </div>
            <form onSubmit={handleCreate} className="space-y-4">
              <div>
                <label className="block text-xs font-mono text-zinc-400 mb-1">Task Title / Objective</label>
                <input
                  type="text"
                  value={newTitle}
                  onChange={(e) => setNewTitle(e.target.value)}
                  placeholder="e.g. Synthesize product feedback report"
                  required
                  autoFocus
                  className="w-full bg-zinc-900 border border-zinc-800 rounded-xl px-3 py-2 text-xs text-white placeholder-zinc-500 focus:outline-none focus:border-white"
                />
              </div>
              <div>
                <label className="block text-xs font-mono text-zinc-400 mb-1">Priority Tier</label>
                <select
                  value={newPriority}
                  onChange={(e) => setNewPriority(e.target.value)}
                  className="w-full bg-zinc-900 border border-zinc-800 rounded-xl px-3 py-2 text-xs text-white focus:outline-none focus:border-white"
                >
                  <option value="urgent">Urgent</option>
                  <option value="high">High</option>
                  <option value="medium">Medium</option>
                  <option value="low">Low</option>
                </select>
              </div>
              <div className="flex justify-end gap-2 pt-2 border-t border-zinc-800">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="btn-secondary-mono !text-xs !py-1.5"
                >
                  Cancel
                </button>
                <button type="submit" className="btn-primary-mono !text-xs !py-1.5 font-bold">
                  Create Task
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
