import React, { useState, useEffect } from 'react';
import {
  Bell,
  CheckCircle2,
  Clock,
  ListTodo,
  Plus,
  RefreshCw,
  Repeat,
  Sparkles,
  Trash2,
  TrendingUp,
} from 'lucide-react';
import {
  fetchTasks,
  createTask,
  completeTask,
  deleteTask,
  fetchDailySummary,
  fetchReminders,
  createReminder,
  dismissReminder,
  checkDueReminders,
  type TaskDto,
  type DailySummaryDto,
  type ReminderDto,
} from '../services/api';

export function TaskManager() {
  const [tasks, setTasks] = useState<TaskDto[]>([]);
  const [summary, setSummary] = useState<DailySummaryDto | null>(null);
  const [reminders, setReminders] = useState<ReminderDto[]>([]);
  const [loading, setLoading] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);

  // New task form state
  const [taskTitle, setTaskTitle] = useState('');
  const [taskPriority, setTaskPriority] = useState('medium');
  const [taskDueDate, setTaskDueDate] = useState('');

  // New reminder form state
  const [remTitle, setRemTitle] = useState('');
  const [remTime, setRemTime] = useState('');
  const [remRecurring, setRemRecurring] = useState(false);
  const [remRule, setRemRule] = useState('daily');

  const loadAllData = async () => {
    setLoading(true);
    try {
      const [tList, sData, rList] = await Promise.all([
        fetchTasks(),
        fetchDailySummary().catch(() => null),
        fetchReminders().catch(() => []),
      ]);
      setTasks(tList);
      if (sData) setSummary(sData);
      setReminders(rList);
    } catch (err: any) {
      console.error('Failed to load productivity data:', err);
      setFeedback(`Error loading data: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAllData();
  }, []);

  const handleCreateTask = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!taskTitle.trim()) return;

    try {
      await createTask({
        title: taskTitle.trim(),
        priority: taskPriority,
        due_date: taskDueDate ? new Date(taskDueDate).toISOString() : undefined,
      });
      setTaskTitle('');
      setTaskDueDate('');
      setFeedback('Task created successfully!');
      await loadAllData();
    } catch (err: any) {
      setFeedback(`Failed to create task: ${err.message}`);
    }
  };

  const handleCompleteTask = async (taskId: string) => {
    try {
      await completeTask(taskId);
      setFeedback('Task marked as completed!');
      await loadAllData();
    } catch (err: any) {
      setFeedback(`Failed to complete task: ${err.message}`);
    }
  };

  const handleDeleteTask = async (taskId: string) => {
    try {
      await deleteTask(taskId);
      setFeedback('Task deleted.');
      await loadAllData();
    } catch (err: any) {
      setFeedback(`Failed to delete task: ${err.message}`);
    }
  };

  const handleCreateReminder = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!remTitle.trim()) return;

    const scheduledDate = remTime
      ? new Date(remTime).toISOString()
      : new Date(Date.now() + 60000).toISOString();

    try {
      await createReminder({
        title: remTitle.trim(),
        scheduled_at: scheduledDate,
        is_recurring: remRecurring,
        recurrence_rule: remRecurring ? remRule : undefined,
      });
      setRemTitle('');
      setRemTime('');
      setFeedback('Reminder scheduled!');
      await loadAllData();
    } catch (err: any) {
      setFeedback(`Failed to create reminder: ${err.message}`);
    }
  };

  const handleDismissReminder = async (reminderId: string) => {
    try {
      await dismissReminder(reminderId);
      await loadAllData();
    } catch (err: any) {
      setFeedback(`Dismiss failed: ${err.message}`);
    }
  };

  const handleTriggerDueCheck = async () => {
    try {
      const res = await checkDueReminders();
      setFeedback(`Due check complete: ${res.triggered_count} reminder(s) triggered.`);
      await loadAllData();
    } catch (err: any) {
      setFeedback(`Check due failed: ${err.message}`);
    }
  };

  const pendingTasks = tasks.filter((t) => t.status === 'pending');
  const inProgressTasks = tasks.filter((t) => t.status === 'in_progress');
  const completedTasks = tasks.filter((t) => t.status === 'completed');

  const getPriorityBadge = (p: string) => {
    switch (p) {
      case 'urgent':
        return { bg: 'rgba(239, 68, 68, 0.15)', color: '#f87171', border: 'rgba(239, 68, 68, 0.3)' };
      case 'high':
        return { bg: 'rgba(245, 158, 11, 0.15)', color: '#fbbf24', border: 'rgba(245, 158, 11, 0.3)' };
      case 'medium':
        return { bg: 'rgba(99, 102, 241, 0.15)', color: '#a5b4fc', border: 'rgba(99, 102, 241, 0.3)' };
      default:
        return { bg: 'rgba(148, 163, 184, 0.15)', color: '#94a3b8', border: 'rgba(148, 163, 184, 0.3)' };
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {/* Daily Digest Summary Row */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
          gap: '16px',
        }}
      >
        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
            <span style={{ fontSize: '0.78rem', color: '#94a3b8', textTransform: 'uppercase', fontWeight: 600 }}>
              Total Tasks
            </span>
            <ListTodo size={16} color="#6366f1" />
          </div>
          <div style={{ fontSize: '1.6rem', fontWeight: 700, color: '#f8fafc' }}>
            {summary?.total_tasks ?? tasks.length}
          </div>
          <div style={{ fontSize: '0.75rem', color: '#94a3b8' }}>
            {summary?.pending_count ?? pendingTasks.length} pending • {summary?.completed_count ?? completedTasks.length} done
          </div>
        </div>

        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
            <span style={{ fontSize: '0.78rem', color: '#94a3b8', textTransform: 'uppercase', fontWeight: 600 }}>
              Completion Rate
            </span>
            <TrendingUp size={16} color="#10b981" />
          </div>
          <div style={{ fontSize: '1.6rem', fontWeight: 700, color: '#34d399' }}>
            {summary?.completion_rate ?? 0}%
          </div>
          <div style={{ fontSize: '0.75rem', color: '#94a3b8' }}>
            Sprint productivity score
          </div>
        </div>

        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
            <span style={{ fontSize: '0.78rem', color: '#94a3b8', textTransform: 'uppercase', fontWeight: 600 }}>
              Urgent Attention
            </span>
            <Clock size={16} color="#ef4444" />
          </div>
          <div style={{ fontSize: '1.6rem', fontWeight: 700, color: '#f87171' }}>
            {summary?.urgent_pending_count ?? 0}
          </div>
          <div style={{ fontSize: '0.75rem', color: '#94a3b8' }}>
            High & urgent priority pending
          </div>
        </div>

        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
            <span style={{ fontSize: '0.78rem', color: '#94a3b8', textTransform: 'uppercase', fontWeight: 600 }}>
              Active Reminders
            </span>
            <Bell size={16} color="#f59e0b" />
          </div>
          <div style={{ fontSize: '1.6rem', fontWeight: 700, color: '#fbbf24' }}>
            {reminders.filter((r) => r.status === 'scheduled').length}
          </div>
          <div style={{ fontSize: '0.75rem', color: '#94a3b8' }}>
            {reminders.filter((r) => r.status === 'triggered').length} triggered alerts
          </div>
        </div>
      </div>

      {/* Action feedback */}
      {feedback && (
        <div
          className="card"
          style={{
            padding: '10px 16px',
            fontSize: '0.85rem',
            background: 'rgba(99, 102, 241, 0.1)',
            border: '1px solid rgba(99, 102, 241, 0.3)',
            color: '#c7d2fe',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
          }}
        >
          <Sparkles size={16} color="#818cf8" /> {feedback}
        </div>
      )}

      {/* Main Row: 3-Column Kanban Board + Reminders Sidebar */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left: Kanban Tasks Board */}
        <div className="lg:col-span-8 flex flex-col gap-4">
          {/* Quick Add Task Form */}
          <div className="card !p-4">
            <form onSubmit={handleCreateTask} className="flex flex-col sm:flex-row gap-2.5 items-stretch sm:items-center">
              <input
                type="text"
                placeholder="Add a new task (e.g. 'Deploy Nexus to Vercel')..."
                value={taskTitle}
                onChange={(e) => setTaskTitle(e.target.value)}
                className="flex-1 bg-slate-950 border border-slate-800 rounded-xl px-4 py-2 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
              />
              <select
                value={taskPriority}
                onChange={(e) => setTaskPriority(e.target.value)}
                className="bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-xs text-slate-300 focus:outline-none"
              >
                <option value="low">Low Priority</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
                <option value="urgent">Urgent</option>
              </select>
              <button
                type="submit"
                disabled={!taskTitle.trim() || loading}
                className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded-xl px-4 py-2 text-xs font-bold transition flex items-center justify-center gap-1.5 shadow"
              >
                <Plus size={15} /> Add Task
              </button>
            </form>
          </div>

          {/* 3 Columns */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* Column 1: Pending */}
            <div
              style={{
                background: 'rgba(15, 23, 42, 0.6)',
                borderRadius: '12px',
                border: '1px solid rgba(255, 255, 255, 0.06)',
                padding: '16px',
                display: 'flex',
                flexDirection: 'column',
                gap: '12px',
                minHeight: '400px',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                <span style={{ fontSize: '0.85rem', fontWeight: 700, color: '#cbd5e1' }}>Pending</span>
                <span style={{ fontSize: '0.75rem', background: 'rgba(255, 255, 255, 0.08)', padding: '2px 8px', borderRadius: '4px' }}>
                  {pendingTasks.length}
                </span>
              </div>

              {pendingTasks.map((t) => {
                const p = getPriorityBadge(t.priority);
                return (
                  <div
                    key={t.id}
                    style={{
                      background: 'rgba(255, 255, 255, 0.04)',
                      borderRadius: '8px',
                      border: '1px solid rgba(255, 255, 255, 0.08)',
                      padding: '12px',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px' }}>
                      <span
                        style={{
                          fontSize: '0.68rem',
                          fontWeight: 700,
                          textTransform: 'uppercase',
                          background: p.bg,
                          color: p.color,
                          border: `1px solid ${p.border}`,
                          padding: '2px 6px',
                          borderRadius: '4px',
                        }}
                      >
                        {t.priority}
                      </span>
                      <div style={{ display: 'flex', gap: '4px' }}>
                        <button
                          onClick={() => handleCompleteTask(t.id)}
                          title="Mark complete"
                          style={{
                            background: 'transparent',
                            color: '#10b981',
                            padding: '4px',
                            border: 'none',
                          }}
                        >
                          <CheckCircle2 size={16} />
                        </button>
                        <button
                          onClick={() => handleDeleteTask(t.id)}
                          title="Delete task"
                          style={{
                            background: 'transparent',
                            color: '#64748b',
                            padding: '4px',
                            border: 'none',
                          }}
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </div>
                    <div style={{ fontSize: '0.88rem', fontWeight: 600, color: '#f8fafc', marginBottom: '4px' }}>
                      {t.title}
                    </div>
                    {t.description && (
                      <p style={{ fontSize: '0.78rem', color: '#94a3b8', lineHeight: 1.3 }}>{t.description}</p>
                    )}
                  </div>
                );
              })}
            </div>

            {/* Column 2: In Progress */}
            <div
              style={{
                background: 'rgba(15, 23, 42, 0.6)',
                borderRadius: '12px',
                border: '1px solid rgba(255, 255, 255, 0.06)',
                padding: '16px',
                display: 'flex',
                flexDirection: 'column',
                gap: '12px',
                minHeight: '400px',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                <span style={{ fontSize: '0.85rem', fontWeight: 700, color: '#38bdf8' }}>In Progress</span>
                <span style={{ fontSize: '0.75rem', background: 'rgba(56, 189, 248, 0.15)', color: '#38bdf8', padding: '2px 8px', borderRadius: '4px' }}>
                  {inProgressTasks.length}
                </span>
              </div>

              {inProgressTasks.map((t) => {
                const p = getPriorityBadge(t.priority);
                return (
                  <div
                    key={t.id}
                    style={{
                      background: 'rgba(255, 255, 255, 0.04)',
                      borderRadius: '8px',
                      border: '1px solid rgba(56, 189, 248, 0.25)',
                      padding: '12px',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px' }}>
                      <span
                        style={{
                          fontSize: '0.68rem',
                          fontWeight: 700,
                          textTransform: 'uppercase',
                          background: p.bg,
                          color: p.color,
                          border: `1px solid ${p.border}`,
                          padding: '2px 6px',
                          borderRadius: '4px',
                        }}
                      >
                        {t.priority}
                      </span>
                      <button
                        onClick={() => handleCompleteTask(t.id)}
                        title="Mark complete"
                        style={{
                          background: 'transparent',
                          color: '#10b981',
                          padding: '4px',
                          border: 'none',
                        }}
                      >
                        <CheckCircle2 size={16} />
                      </button>
                    </div>
                    <div style={{ fontSize: '0.88rem', fontWeight: 600, color: '#f8fafc' }}>{t.title}</div>
                  </div>
                );
              })}
            </div>

            {/* Column 3: Completed */}
            <div
              style={{
                background: 'rgba(15, 23, 42, 0.6)',
                borderRadius: '12px',
                border: '1px solid rgba(255, 255, 255, 0.06)',
                padding: '16px',
                display: 'flex',
                flexDirection: 'column',
                gap: '12px',
                minHeight: '400px',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                <span style={{ fontSize: '0.85rem', fontWeight: 700, color: '#34d399' }}>Completed</span>
                <span style={{ fontSize: '0.75rem', background: 'rgba(16, 185, 129, 0.15)', color: '#34d399', padding: '2px 8px', borderRadius: '4px' }}>
                  {completedTasks.length}
                </span>
              </div>

              {completedTasks.map((t) => (
                <div
                  key={t.id}
                  style={{
                    background: 'rgba(16, 185, 129, 0.05)',
                    borderRadius: '8px',
                    border: '1px solid rgba(16, 185, 129, 0.2)',
                    padding: '12px',
                    opacity: 0.85,
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                    <span style={{ fontSize: '0.88rem', fontWeight: 600, color: '#94a3b8', textDecoration: 'line-through' }}>
                      {t.title}
                    </span>
                    <button
                      onClick={() => handleDeleteTask(t.id)}
                      style={{ background: 'transparent', color: '#64748b', padding: '4px', border: 'none' }}
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Right: Reminders & Background Worker Widget */}
        <div className="lg:col-span-4 flex flex-col gap-4">
          <div className="card">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
              <div>
                <h3 style={{ fontSize: '0.95rem', fontWeight: 700, color: '#f8fafc', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Bell size={16} color="#f59e0b" /> Scheduled Reminders
                </h3>
                <p style={{ fontSize: '0.72rem', color: '#94a3b8' }}>
                  Background worker checks due items every 10s
                </p>
              </div>
              <button
                onClick={handleTriggerDueCheck}
                title="Force background scan now"
                style={{
                  padding: '4px 8px',
                  fontSize: '0.72rem',
                  background: 'rgba(255, 255, 255, 0.08)',
                  color: '#94a3b8',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px',
                }}
              >
                <RefreshCw size={12} /> Scan
              </button>
            </div>

            {/* Quick Reminder Form */}
            <form onSubmit={handleCreateReminder} style={{ marginBottom: '16px' }}>
              <input
                type="text"
                placeholder="Reminder title (e.g. 'Team Standup')..."
                value={remTitle}
                onChange={(e) => setRemTitle(e.target.value)}
                style={{
                  width: '100%',
                  padding: '8px 12px',
                  borderRadius: '6px',
                  background: 'rgba(255, 255, 255, 0.05)',
                  border: '1px solid rgba(255, 255, 255, 0.1)',
                  color: '#ffffff',
                  fontSize: '0.82rem',
                  marginBottom: '8px',
                }}
              />
              <div style={{ display: 'flex', gap: '8px', marginBottom: '8px' }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.75rem', color: '#cbd5e1' }}>
                  <input
                    type="checkbox"
                    checked={remRecurring}
                    onChange={(e) => setRemRecurring(e.target.checked)}
                  />
                  <Repeat size={12} /> Recurring
                </label>
                {remRecurring && (
                  <select
                    value={remRule}
                    onChange={(e) => setRemRule(e.target.value)}
                    style={{
                      background: '#1a2234',
                      border: '1px solid rgba(255, 255, 255, 0.15)',
                      color: '#ffffff',
                      fontSize: '0.72rem',
                      padding: '2px 6px',
                      borderRadius: '4px',
                    }}
                  >
                    <option value="daily">Daily</option>
                    <option value="weekly">Weekly</option>
                    <option value="monthly">Monthly</option>
                  </select>
                )}
              </div>
              <button
                type="submit"
                disabled={!remTitle.trim()}
                style={{
                  width: '100%',
                  background: '#f59e0b',
                  color: '#000000',
                  fontWeight: 700,
                  fontSize: '0.8rem',
                  padding: '6px 10px',
                }}
              >
                Schedule Reminder
              </button>
            </form>

            {/* List of Reminders */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', maxHeight: '360px', overflowY: 'auto' }}>
              {reminders.length === 0 ? (
                <div style={{ textAlign: 'center', color: '#64748b', fontSize: '0.8rem', padding: '20px 0' }}>
                  No active reminders scheduled.
                </div>
              ) : (
                reminders.map((r) => {
                  const isTriggered = r.status === 'triggered';
                  return (
                    <div
                      key={r.id}
                      style={{
                        padding: '10px 12px',
                        borderRadius: '8px',
                        background: isTriggered ? 'rgba(239, 68, 68, 0.12)' : 'rgba(255, 255, 255, 0.04)',
                        border: `1px solid ${isTriggered ? 'rgba(239, 68, 68, 0.35)' : 'rgba(255, 255, 255, 0.08)'}`,
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                        <span
                          style={{
                            fontSize: '0.68rem',
                            fontWeight: 700,
                            padding: '1px 6px',
                            borderRadius: '4px',
                            background: isTriggered ? '#ef4444' : 'rgba(245, 158, 11, 0.2)',
                            color: isTriggered ? '#ffffff' : '#fbbf24',
                          }}
                        >
                          {r.status.toUpperCase()}
                        </span>
                        {isTriggered && (
                          <button
                            onClick={() => handleDismissReminder(r.id)}
                            style={{
                              padding: '2px 6px',
                              fontSize: '0.68rem',
                              background: 'rgba(255, 255, 255, 0.1)',
                              color: '#f8fafc',
                            }}
                          >
                            Dismiss
                          </button>
                        )}
                      </div>
                      <div style={{ fontSize: '0.85rem', fontWeight: 600, color: '#f8fafc' }}>{r.title}</div>
                      <div style={{ fontSize: '0.72rem', color: '#94a3b8', marginTop: '2px', display: 'flex', alignItems: 'center' }}>
                        <span>Due: {new Date(r.scheduled_at).toLocaleTimeString()}</span>
                        {r.is_recurring && (
                          <span style={{ display: 'inline-flex', alignItems: 'center', marginLeft: '6px' }}>
                            • <Repeat size={11} style={{ margin: '0 4px' }} /> {r.recurrence_rule}
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
