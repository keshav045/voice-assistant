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
  ShieldAlert,
  Sparkles,
  Terminal,
  Trash2,
  Zap,
} from 'lucide-react';
import {
  fetchTasks,
  createTask,
  completeTask,
  deleteTask,
  fetchDailySummary,
  fetchApprovals,
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
  const [loading, setLoading] = useState<boolean>(false);
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

      {/* Top Metric Cards (Image 1 Exact Layout) */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {/* Card 1: Total Active Load */}
        <div className="bg-[#0b0b0d] border border-zinc-800 rounded-2xl p-5 shadow-lg relative overflow-hidden">
          <div className="flex items-center justify-between text-xs font-mono text-zinc-400 uppercase tracking-wider mb-2">
            <span>Total Active Load</span>
            <Layers size={16} className="text-white" />
          </div>
          <div className="text-3xl font-black text-white">48 <span className="text-xs font-normal text-zinc-400">orchestrated</span></div>
          <div className="mt-2 text-[11px] text-zinc-400 font-mono flex items-center gap-1.5">
            <span className="text-white">&uarr; 4 new</span> syncing across 6 hubs
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
          <div className="text-3xl font-black text-white">18 <span className="text-xs font-normal text-zinc-400">running</span></div>
          <div className="mt-2 text-[11px] text-zinc-400 font-mono">
            37.5% of total workflow fully delegated
          </div>
        </div>

        {/* Card 3: Approval Gates */}
        <div className="bg-[#0b0b0d] border border-zinc-800 rounded-2xl p-5 shadow-lg relative overflow-hidden">
          <div className="flex items-center justify-between text-xs font-mono text-zinc-400 uppercase tracking-wider mb-2">
            <span>Approval Gates</span>
            <ShieldAlert size={16} className="text-white" />
          </div>
          <div className="text-3xl font-black text-white">{approvals.length || 6} <span className="text-xs font-normal text-zinc-400">items locked</span></div>
          <div className="mt-2 text-[11px] text-zinc-400 font-mono flex items-center gap-1.5">
            <span className="text-white font-bold">! 2 urgent</span> require exec token
          </div>
        </div>

        {/* Card 4: Completed Wk 42 */}
        <div className="bg-[#0b0b0d] border border-zinc-800 rounded-2xl p-5 shadow-lg relative overflow-hidden">
          <div className="flex items-center justify-between text-xs font-mono text-zinc-400 uppercase tracking-wider mb-2">
            <span>Completed Wk 42</span>
            <CheckCircle2 size={16} className="text-white" />
          </div>
          <div className="text-3xl font-black text-white">124 <span className="text-xs font-mono text-zinc-400 font-normal">+18% vel</span></div>
          <div className="mt-2 text-[11px] text-zinc-400 font-mono flex items-center gap-1">
            <Zap size={11} className="text-white" />
            Saved approx 34.2 hrs dev/exec time
          </div>
        </div>
      </div>

      {/* Subheader Controls & Filters */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pt-1">
        <div className="flex items-center gap-3 flex-wrap">
          {/* View Switcher */}
          <div className="flex items-center bg-zinc-950 border border-zinc-800 p-1 rounded-xl">
            <button
              onClick={() => setActiveView('kanban')}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition flex items-center gap-1.5 ${
                activeView === 'kanban' ? 'bg-zinc-800 text-white font-bold' : 'text-zinc-400 hover:text-white'
              }`}
            >
              <Layers size={13} />
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
          <button className="btn-secondary-mono text-xs py-2 px-3">
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

      {/* 4-Column Kanban View (Image 1 Exact Columns) */}
      {activeView === 'kanban' ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {/* Column 1: Backlog & Suggestions */}
          <div className="bg-[#0b0b0d] border border-zinc-800/80 rounded-2xl p-4 flex flex-col space-y-3.5">
            <div className="flex items-center justify-between pb-2 border-b border-zinc-800/80 text-xs font-bold text-white">
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-zinc-400" />
                <span>Backlog &amp; Suggestions</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="text-[11px] font-mono px-2 py-0.5 rounded-full bg-zinc-900 border border-zinc-800 text-zinc-300">
                  5
                </span>
                <MoreHorizontal size={14} className="text-zinc-500" />
              </div>
            </div>

            <div className="space-y-3 flex-1 overflow-y-auto max-h-[700px] pr-1">
              {/* Card 1: Continuous Inference */}
              <div className="p-3.5 rounded-xl bg-zinc-950 border border-zinc-800 space-y-2">
                <div className="flex items-center gap-1.5 text-[10px] font-mono text-zinc-400">
                  <Activity size={12} className="text-zinc-400" />
                  <span>Autonomous Inference</span>
                </div>
                <p className="text-xs text-zinc-300 leading-relaxed">
                  Continuous inference scanning unread Slack threads, calendar conflicts, and Gmail threads.
                </p>
              </div>

              {/* Card 2: Urgent Inferred from Gmail */}
              <div className="p-3.5 rounded-xl bg-zinc-950 border border-zinc-800 space-y-2.5 hover:border-zinc-700 transition">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-[10px] font-mono font-bold uppercase px-2 py-0.5 rounded bg-white text-black">
                    Urgent
                  </span>
                  <span className="text-[10px] font-mono text-zinc-400">Inferred from Gmail</span>
                </div>
                <h4 className="text-xs font-bold text-white leading-snug">
                  Prepare Q4 Executive Briefing from 14 raw investor memos
                </h4>
                <div className="text-[11px] text-zinc-400">Collated thread across Board of Directors...</div>
                <div className="flex items-center gap-2 text-[10px] font-mono text-zinc-400">
                  <span className="bg-zinc-900 px-2 py-0.5 rounded border border-zinc-800">Finance Docs</span>
                  <span>Due Tomorrow</span>
                </div>
                <div className="flex items-center gap-2 pt-1 border-t border-zinc-850">
                  <button className="btn-secondary-mono py-1 px-2.5 text-[11px]">Manual Queue</button>
                  <button className="btn-primary-mono py-1 px-2.5 text-[11px]">Delegate</button>
                </div>
              </div>

              {/* Card 3: Normal G-Calendar */}
              <div className="p-3.5 rounded-xl bg-zinc-950 border border-zinc-800 space-y-2.5 hover:border-zinc-700 transition">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-zinc-900 text-zinc-300 border border-zinc-800">
                    Normal
                  </span>
                  <span className="text-[10px] font-mono text-zinc-400">G-Calendar</span>
                </div>
                <h4 className="text-xs font-bold text-white leading-snug">
                  Reschedule overlap between Team Sprint &amp; VP sync
                </h4>
                <div className="flex items-center justify-between text-[11px] text-zinc-400 pt-1">
                  <span>Assignee: Unassigned</span>
                  <button className="btn-secondary-mono py-1 px-2 text-[10px]">Delegate to Agent</button>
                </div>
              </div>

              {/* Card 4: Repo Audit Ingest */}
              <div className="p-3.5 rounded-xl bg-zinc-950 border border-zinc-800 space-y-2">
                <div className="text-[10px] font-mono text-zinc-400">Repo Audit Ingest</div>
                <h4 className="text-xs font-bold text-white">Synthesize 40 Customer Interviews from Gong</h4>
                <div className="flex items-center justify-between pt-1 text-xs">
                  <span className="text-[10px] text-zinc-500 font-mono">Voice Transcripts</span>
                  <button className="btn-secondary-mono py-1 px-2 text-[10px]">Trigger Run</button>
                </div>
              </div>
            </div>
          </div>

          {/* Column 2: Autonomous In Progress */}
          <div className="bg-[#0b0b0d] border border-zinc-800/80 rounded-2xl p-4 flex flex-col space-y-3.5">
            <div className="flex items-center justify-between pb-2 border-b border-zinc-800/80 text-xs font-bold text-white">
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-white animate-mono-pulse" />
                <span>Autonomous In Progress</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="text-[11px] font-mono px-2 py-0.5 rounded-full bg-zinc-900 border border-zinc-800 text-zinc-300">
                  18
                </span>
                <RefreshCw size={12} className="text-zinc-500 animate-spin" />
              </div>
            </div>

            <div className="space-y-3 flex-1 overflow-y-auto max-h-[700px] pr-1">
              {/* Card 1 */}
              <div className="p-3.5 rounded-xl bg-zinc-950 border border-zinc-800 space-y-2.5">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-zinc-900 text-zinc-300 border border-zinc-800">
                    Research Agent v4
                  </span>
                  <span className="text-[10px] font-mono font-bold uppercase px-1.5 py-0.5 rounded bg-white text-black">
                    High
                  </span>
                </div>
                <h4 className="text-xs font-bold text-white">Synthesize 40 customer interviews into JTBD Matrix</h4>
                <div className="space-y-1">
                  <div className="flex items-center justify-between text-[10px] font-mono text-zinc-400">
                    <span>chunk [29/40]: extracting...</span>
                    <span className="text-white font-bold">72%</span>
                  </div>
                  <div className="w-full bg-zinc-900 h-1.5 rounded-full overflow-hidden">
                    <div className="bg-white h-full rounded-full" style={{ width: '72%' }} />
                  </div>
                </div>
                <div className="flex items-center justify-between text-[10px] font-mono text-zinc-500 pt-1">
                  <span>1.4k Tokens/s</span>
                  <span>Context: 128k</span>
                </div>
              </div>

              {/* Card 2 */}
              <div className="p-3.5 rounded-xl bg-zinc-950 border border-zinc-800 space-y-2.5">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-zinc-900 text-zinc-300 border border-zinc-800">
                    Desktop Agent Win11
                  </span>
                  <span className="text-[10px] font-mono text-zinc-400">Normal</span>
                </div>
                <h4 className="text-xs font-bold text-white">Batch reconciliation: SAP invoice balance mismatch</h4>
                <div className="text-[11px] text-zinc-400 font-mono">Throughput: 410 entries parsed</div>
                <div className="flex items-center justify-between text-[11px] font-mono text-zinc-300 pt-1">
                  <span>ETA 4m</span>
                  <span className="font-bold text-white">88% Complete</span>
                </div>
              </div>

              {/* Card 3 */}
              <div className="p-3.5 rounded-xl bg-zinc-950 border border-zinc-800 space-y-2.5">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-zinc-900 text-zinc-300 border border-zinc-800">
                    Gmail Agent
                  </span>
                  <span className="text-[10px] font-mono text-zinc-400">Normal</span>
                </div>
                <h4 className="text-xs font-bold text-white">Drafting 18 personalized outbound partner follow-ups</h4>
                <div className="w-full bg-zinc-900 h-1.5 rounded-full overflow-hidden">
                  <div className="bg-white h-full rounded-full" style={{ width: '64%' }} />
                </div>
                <div className="text-[10px] font-mono text-zinc-400">Drafting email #12 via Context &bull; 64%</div>
              </div>
            </div>
          </div>

          {/* Column 3: Awaiting Approval */}
          <div className="bg-[#0b0b0d] border border-zinc-800/80 rounded-2xl p-4 flex flex-col space-y-3.5">
            <div className="flex items-center justify-between pb-2 border-b border-zinc-800/80 text-xs font-bold text-white">
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-white" />
                <span>Awaiting Approval</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="text-[11px] font-mono px-2 py-0.5 rounded-full bg-white text-black font-extrabold">
                  {approvals.length || 6}
                </span>
                <Shield size={13} className="text-zinc-400" />
              </div>
            </div>

            <div className="space-y-3 flex-1 overflow-y-auto max-h-[700px] pr-1">
              {/* Card 1: High Privilege Action */}
              <div className="p-3.5 rounded-xl bg-zinc-950 border border-zinc-800 space-y-2.5">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-[10px] font-mono font-bold uppercase px-2 py-0.5 rounded bg-white text-black">
                    High Privilege Action
                  </span>
                  <span className="text-[10px] font-mono text-zinc-500">12m ago</span>
                </div>
                <h4 className="text-xs font-bold text-white leading-snug">
                  Disburse $12,450 to AWS Cloud Services (Monthly Reserve)
                </h4>
                <div className="text-[10px] font-mono text-zinc-400 space-y-0.5">
                  <div>Trigger Agent: Autonomous Controller</div>
                  <div>Confidence: 99.4% (Pre-verified)</div>
                </div>
                <div className="flex items-center gap-2 pt-1">
                  <button className="btn-primary-mono py-1 px-3 text-[11px] font-bold">Approve</button>
                  <button className="btn-secondary-mono py-1 px-3 text-[11px]">Inspect</button>
                </div>
              </div>

              {/* Card 2: Communication CRM */}
              <div className="p-3.5 rounded-xl bg-zinc-950 border border-zinc-800 space-y-2.5">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-zinc-900 text-zinc-300 border border-zinc-800">
                    Communication
                  </span>
                  <span className="text-[10px] font-mono text-zinc-500">CRM Sync</span>
                </div>
                <h4 className="text-xs font-bold text-white leading-snug">
                  Send Product Roadmap Release Update to Tier-1 Enterprise Clients
                </h4>
                <p className="text-[11px] text-zinc-400">Targeting 14 accounts. Tailored change-log...</p>
                <div className="flex items-center gap-2 pt-1">
                  <button className="btn-primary-mono py-1 px-3 text-[11px]">Dispatch</button>
                  <button className="btn-secondary-mono py-1 px-3 text-[11px]">Diff View</button>
                </div>
              </div>

              {/* Card 3: Cloud Infra */}
              <div className="p-3.5 rounded-xl bg-zinc-950 border border-zinc-800 space-y-2.5">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-[10px] font-mono font-bold uppercase px-2 py-0.5 rounded bg-zinc-800 text-zinc-200">
                    System Critical
                  </span>
                  <span className="text-[10px] font-mono text-zinc-500">Cloud Infra</span>
                </div>
                <h4 className="text-xs font-bold text-white leading-snug">
                  Promote Staging Microservices v3.8.1 to Production Region US-East
                </h4>
                <button className="w-full btn-secondary-mono py-1.5 text-xs font-semibold justify-center">
                  Review Pull Request
                </button>
              </div>
            </div>
          </div>

          {/* Column 4: Completed */}
          <div className="bg-[#0b0b0d] border border-zinc-800/80 rounded-2xl p-4 flex flex-col space-y-3.5">
            <div className="flex items-center justify-between pb-2 border-b border-zinc-800/80 text-xs font-bold text-white">
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-white" />
                <span>Completed</span>
              </div>
              <span className="text-[11px] font-mono px-2 py-0.5 rounded-full bg-zinc-900 border border-zinc-800 text-zinc-300">
                124
              </span>
            </div>

            {/* Top Autonomous Efficiency Ring Gauge Card */}
            <div className="p-3.5 rounded-xl bg-zinc-950 border border-zinc-800 flex items-center justify-between">
              <div>
                <div className="text-[10px] font-mono uppercase text-zinc-400">Autonomous Efficiency</div>
                <div className="text-sm font-bold text-white mt-0.5">4.2 hrs Saved Today</div>
                <div className="text-[10px] text-zinc-500 mt-0.5">Zero intervention errors</div>
              </div>
              <div className="relative w-11 h-11 flex items-center justify-center">
                <svg className="w-11 h-11 transform -rotate-90" viewBox="0 0 36 36">
                  <path
                    className="text-zinc-800"
                    strokeWidth="3.5"
                    stroke="currentColor"
                    fill="none"
                    d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                  />
                  <path
                    className="text-white"
                    strokeDasharray="87, 100"
                    strokeWidth="3.5"
                    strokeLinecap="round"
                    stroke="currentColor"
                    fill="none"
                    d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                  />
                </svg>
                <div className="absolute text-[9px] font-bold text-white font-mono">87%</div>
              </div>
            </div>

            <div className="space-y-3 flex-1 overflow-y-auto max-h-[600px] pr-1">
              {/* Card 1 */}
              <div className="p-3.5 rounded-xl bg-zinc-950 border border-zinc-800 space-y-1.5">
                <div className="flex items-center gap-1.5 text-[10px] font-mono text-zinc-400">
                  <Check size={11} className="text-white" />
                  <span>Completed &bull; Saved 45 mins</span>
                </div>
                <h4 className="text-xs font-bold text-white">Ingest &amp; Categorize 120 Zendesk support escalations</h4>
                <div className="text-[10px] font-mono text-zinc-500">DeskAgent Automator &bull; All 120 routed to Jira</div>
              </div>

              {/* Card 2 */}
              <div className="p-3.5 rounded-xl bg-zinc-950 border border-zinc-800 space-y-1.5">
                <div className="flex items-center gap-1.5 text-[10px] font-mono text-zinc-400">
                  <Check size={11} className="text-white" />
                  <span>Completed &bull; Saved 1.2 hrs</span>
                </div>
                <h4 className="text-xs font-bold text-white">Generate competitor feature-matrix report vs Vercel v0</h4>
                <div className="text-[10px] font-mono text-zinc-500">WebCrawler &amp; LLM v3 &bull; Exported to Notion</div>
              </div>

              {/* Card 3 */}
              <div className="p-3.5 rounded-xl bg-zinc-950 border border-zinc-800 space-y-1.5">
                <div className="flex items-center gap-1.5 text-[10px] font-mono text-zinc-400">
                  <Check size={11} className="text-white" />
                  <span>Completed &bull; Saved 20 mins</span>
                </div>
                <h4 className="text-xs font-bold text-white">Sync Calendar with Tokyo partner timezone daylight shift</h4>
                <div className="text-[10px] font-mono text-zinc-500">Calendar Agent &bull; 8 Invites Shifted</div>
              </div>
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
                    <span className={`font-semibold ${task.status === 'completed' ? 'line-through text-zinc-500' : 'text-white'}`}>
                      {task.title}
                    </span>
                    <div className="text-[10px] font-mono text-zinc-500 mt-0.5">
                      Priority: {task.priority} &bull; Created: {new Date(task.created_at).toLocaleTimeString()}
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
        </div>
      )}

      {/* Bottom Runtime Cluster Status Strip (Image 1 Exact Bottom Bar) */}
      <div className="p-4 rounded-xl bg-zinc-950 border border-zinc-800 flex flex-col md:flex-row md:items-center justify-between gap-3 text-xs font-mono text-zinc-400">
        <div className="flex items-center gap-2 truncate">
          <Terminal size={14} className="text-white shrink-0" />
          <span className="text-white font-bold">Autonomous Cluster Orchestration NOMINAL</span>
          <span className="text-zinc-600">//</span>
          <span className="truncate">Active node thread #8492</span>
          <span className="text-zinc-600">//</span>
          <span className="truncate">Running model: nexus-deep-reason-3.5-flash</span>
          <span className="text-zinc-600">//</span>
          <span>Core temp: 38&deg;C</span>
        </div>
        <button className="btn-secondary-mono py-1 px-3 text-[11px] shrink-0">
          View Full Runtime Logs
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
                  placeholder="e.g. Ingest customer survey data into analytical breakdown"
                  required
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
              <div className="flex items-center justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="btn-secondary-mono py-1.5 px-3 text-xs"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={loading}
                  className="btn-primary-mono py-1.5 px-4 text-xs font-bold"
                >
                  {loading ? 'Orchestrating...' : 'Dispatch Task'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
