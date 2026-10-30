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
