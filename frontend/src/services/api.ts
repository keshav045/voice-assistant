import type { AuthResponse, SystemConfig, SystemHealth, User } from '../types';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export async function fetchHealth(): Promise<SystemHealth> {
  const res = await fetch(`${API_BASE}/health`, {
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) {
    throw new Error(`Health check failed with status: ${res.status}`);
  }
  return res.json();
}

export async function fetchSystemConfig(): Promise<SystemConfig> {
  const res = await fetch(`${API_BASE}/api/v1/system/config`, {
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) {
    throw new Error(`Config fetch failed with status: ${res.status}`);
  }
  return res.json();
}

export async function registerUser(
  email: string,
  password: string,
  fullName?: string
): Promise<AuthResponse> {
  const res = await fetch(`${API_BASE}/api/v1/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      email,
      password,
      full_name: fullName,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Registration failed' }));
    throw new Error(err.detail || 'Registration failed');
  }
  return res.json();
}

export async function loginUser(
  email: string,
  password: string
): Promise<AuthResponse> {
  const formData = new URLSearchParams();
  formData.append('username', email);
  formData.append('password', password);

  const res = await fetch(`${API_BASE}/api/v1/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: formData.toString(),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Login failed' }));
    throw new Error(err.detail || 'Login failed');
  }
  return res.json();
}

export async function fetchCurrentUser(token: string): Promise<User> {
  const res = await fetch(`${API_BASE}/api/v1/auth/me`, {
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
  });
  if (!res.ok) {
    throw new Error('Authentication failed');
  }
  return res.json();
}

export interface VoiceSessionDto {
  session_id: string;
  status: string;
  provider_mode: string;
  ws_url: string;
  started_at: string;
  metrics: Record<string, any>;
}

export async function createVoiceSession(
  providerMode: 'modular' | 'realtime' = 'modular'
): Promise<VoiceSessionDto> {
  const res = await fetch(`${API_BASE}/api/v1/voice/session`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ provider_mode: providerMode }),
  });
  if (!res.ok) {
    throw new Error(`Failed to create voice session: ${res.statusText}`);
  }
  return res.json();
}

export interface ChatResponseDto {
  request_id: string;
  user_message: string;
  normalized_intent?: string;
  plan?: Record<string, any>;
  current_agent?: string;
  tool_results: Array<{
    tool: string;
    args: Record<string, any>;
    output: Record<string, any>;
  }>;
  approval_required: boolean;
  approval_status: string;
  approval_payload?: {
    approval_id: string;
    tool_name: string;
    action_summary: string;
    tool_payload: Record<string, any>;
  };
  workflow_status: string;
  final_response: string;
}

export interface ApprovalDto {
  id: string;
  agent_run_id: string;
  tool_name: string;
  action_summary: string;
  tool_payload?: Record<string, any>;
  status: string;
  created_at: string;
  decided_at?: string;
}

export async function submitChatMessage(message: string, conversationId?: string): Promise<ChatResponseDto> {
  const res = await fetch(`${API_BASE}/api/v1/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message,
      conversation_id: conversationId,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Chat request failed' }));
    throw new Error(err.detail || 'Chat request failed');
  }
  return res.json();
}

export async function fetchApprovals(statusFilter: string = 'pending'): Promise<ApprovalDto[]> {
  const res = await fetch(`${API_BASE}/api/v1/approvals?status_filter=${statusFilter}`, {
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) {
    throw new Error('Failed to fetch approvals');
  }
  return res.json();
}

export async function submitApprovalDecision(
  approvalId: string,
  decision: 'approved' | 'rejected',
  reason?: string
): Promise<{ approval_id: string; status: string; message: string; execution_result?: any }> {
  const res = await fetch(`${API_BASE}/api/v1/approvals/${approvalId}/decision`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      decision,
      reason: reason || 'Decision submitted from dashboard',
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Decision failed' }));
    throw new Error(err.detail || 'Decision failed');
  }
  return res.json();
}

// --- Phase 4 Tasks & Reminders DTOs & API Calls ---
export interface TaskDto {
  id: string;
  title: string;
  description?: string;
  priority: 'low' | 'medium' | 'high' | 'urgent';
  status: 'pending' | 'in_progress' | 'completed' | 'cancelled';
  due_date?: string;
  completed_at?: string;
  tags?: string[];
  created_at: string;
}

export interface TaskCreatePayload {
  title: string;
  description?: string;
  priority?: string;
  due_date?: string;
  tags?: string[];
}

export interface DailySummaryDto {
  summary_date: string;
  total_tasks: number;
  completed_count: number;
  pending_count: number;
  urgent_pending_count: number;
  urgent_tasks: Array<{ id: string; title: string; priority: string }>;
  completion_rate: number;
}

export interface ReminderDto {
  id: string;
  title: string;
  scheduled_at: string;
  is_recurring: boolean;
  recurrence_rule?: string;
  status: 'scheduled' | 'triggered' | 'dismissed' | 'cancelled';
  triggered_at?: string;
  notification_channel: string;
  created_at: string;
}

export interface ReminderCreatePayload {
  title: string;
  scheduled_at: string;
  is_recurring?: boolean;
  recurrence_rule?: string;
  channel?: string;
}

export async function fetchTasks(status?: string, priority?: string): Promise<TaskDto[]> {
  const params = new URLSearchParams();
  if (status) params.append('status', status);
  if (priority) params.append('priority', priority);
  const query = params.toString() ? `?${params.toString()}` : '';

  const res = await fetch(`${API_BASE}/api/v1/tasks${query}`, {
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) throw new Error('Failed to fetch tasks');
  return res.json();
}

export async function createTask(payload: TaskCreatePayload): Promise<TaskDto> {
  const res = await fetch(`${API_BASE}/api/v1/tasks`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error('Failed to create task');
  return res.json();
}

export async function completeTask(taskId: string): Promise<TaskDto> {
  const res = await fetch(`${API_BASE}/api/v1/tasks/${taskId}/complete`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) throw new Error('Failed to complete task');
  return res.json();
}

export async function deleteTask(taskId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/v1/tasks/${taskId}`, {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) throw new Error('Failed to delete task');
}

export async function fetchDailySummary(): Promise<DailySummaryDto> {
  const res = await fetch(`${API_BASE}/api/v1/tasks/summary/daily`, {
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) throw new Error('Failed to fetch daily summary');
  return res.json();
}

export async function fetchReminders(status?: string): Promise<ReminderDto[]> {
  const query = status ? `?status=${status}` : '';
  const res = await fetch(`${API_BASE}/api/v1/reminders${query}`, {
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) throw new Error('Failed to fetch reminders');
  return res.json();
}

export async function createReminder(payload: ReminderCreatePayload): Promise<ReminderDto> {
  const res = await fetch(`${API_BASE}/api/v1/reminders`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error('Failed to create reminder');
  return res.json();
}

export async function dismissReminder(reminderId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/v1/reminders/${reminderId}/dismiss`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) throw new Error('Failed to dismiss reminder');
}

export async function checkDueReminders(): Promise<any> {
  const res = await fetch(`${API_BASE}/api/v1/reminders/check-due`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) throw new Error('Failed to trigger reminder check');
  return res.json();
}

// --- Phase 5 Gmail Integration DTOs & API Calls ---
export interface EmailMessageDto {
  id: string;
  sender: string;
  recipient: string;
  subject: string;
  date: string;
  snippet: string;
  body: string;
  is_read: boolean;
  labels: string[];
}

export interface EmailDraftDto {
  id: string;
  user_id?: string;
  recipient: string;
  subject: string;
  body: string;
  status: 'draft' | 'pending_approval' | 'sent' | 'discarded';
  gmail_draft_id?: string;
  sent_at?: string;
  created_at: string;
  updated_at: string;
}

export interface EmailDraftCreatePayload {
  recipient: string;
  subject: string;
  body: string;
}

export interface EmailSendPayload {
  recipient: string;
  subject: string;
  body: string;
  draft_id?: string;
}

export async function searchEmails(query: string = '', limit: number = 10): Promise<{ success: boolean; count: number; messages: EmailMessageDto[]; query: string }> {
  const params = new URLSearchParams();
  if (query) params.append('q', query);
  params.append('limit', limit.toString());
  const res = await fetch(`${API_BASE}/api/v1/emails/search?${params.toString()}`, {
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) throw new Error('Failed to search emails');
  return res.json();
}

export async function summarizeEmails(query: string = ''): Promise<{ success: boolean; summary: string; emails_analyzed: number; query?: string }> {
  const res = await fetch(`${API_BASE}/api/v1/emails/summarize`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query }),
  });
  if (!res.ok) throw new Error('Failed to summarize emails');
  return res.json();
}

export async function fetchEmailDrafts(status?: string): Promise<EmailDraftDto[]> {
  const query = status ? `?status=${status}` : '';
  const res = await fetch(`${API_BASE}/api/v1/emails/drafts${query}`, {
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) throw new Error('Failed to fetch drafts');
  return res.json();
}

export async function createEmailDraft(payload: EmailDraftCreatePayload): Promise<EmailDraftDto> {
  const res = await fetch(`${API_BASE}/api/v1/emails/drafts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error('Failed to create draft');
  return res.json();
}

export async function sendEmail(payload: EmailSendPayload): Promise<{ success: boolean; message: string; sent_at: string; recipient: string }> {
  const res = await fetch(`${API_BASE}/api/v1/emails/send`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error('Failed to send email');
  return res.json();
}

// --- Phase 6 Google Calendar DTOs & API Calls ---
export interface CalendarEventDto {
  id: string;
  user_id?: string;
  title: string;
  description?: string;
  location?: string;
  start_time: string;
  end_time: string;
  is_all_day: boolean;
  status: 'confirmed' | 'tentative' | 'cancelled';
  google_event_id?: string;
  attendees?: string[];
  created_at: string;
  updated_at: string;
}

export interface CalendarEventCreatePayload {
  title: string;
  start_time: string;
  end_time: string;
  description?: string;
  location?: string;
  attendees?: string[];
}

export interface AvailabilityDto {
  is_free: boolean;
  start_time: string;
  end_time: string;
  conflict_count: number;
  conflicts: Array<{
    id: string;
    title: string;
    start_time: string;
    end_time: string;
    location?: string;
  }>;
  message: string;
}

export interface FreeSlotDto {
  start_time: string;
  end_time: string;
  duration_minutes: number;
  display: string;
}

export async function fetchCalendarEvents(start?: string, end?: string): Promise<CalendarEventDto[]> {
  const params = new URLSearchParams();
  if (start) params.append('start', start);
  if (end) params.append('end', end);
  const query = params.toString() ? `?${params.toString()}` : '';

  const res = await fetch(`${API_BASE}/api/v1/calendar/events${query}`, {
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) throw new Error('Failed to fetch calendar events');
  return res.json();
}

export async function createCalendarEvent(payload: CalendarEventCreatePayload): Promise<CalendarEventDto> {
  const res = await fetch(`${API_BASE}/api/v1/calendar/events`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to create calendar event' }));
    throw new Error(err.detail || 'Failed to create calendar event');
  }
  return res.json();
}

export async function checkCalendarAvailability(startTime: string, endTime: string): Promise<AvailabilityDto> {
  const params = new URLSearchParams({
    start_time: startTime,
    end_time: endTime,
  });
  const res = await fetch(`${API_BASE}/api/v1/calendar/availability?${params.toString()}`, {
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Availability check failed' }));
    throw new Error(err.detail || 'Availability check failed');
  }
  return res.json();
}

export async function fetchFreeSlots(date?: string, duration: number = 30): Promise<FreeSlotDto[]> {
  const params = new URLSearchParams({ duration: duration.toString() });
  if (date) params.append('date', date);
  const res = await fetch(`${API_BASE}/api/v1/calendar/free-slots?${params.toString()}`, {
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) throw new Error('Failed to fetch free slots');
  return res.json();
}

export async function deleteCalendarEvent(eventId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/v1/calendar/events/${eventId}`, {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) throw new Error('Failed to delete calendar event');
}


