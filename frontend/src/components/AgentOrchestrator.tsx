import React, { useState, useEffect } from 'react';
import {
  Bot,
  CheckCircle,
  CheckCircle2,
  Layers,
  Send,
  Shield,
  XCircle,
} from 'lucide-react';
import {
  submitChatMessage,
  fetchApprovals,
  submitApprovalDecision,
  type ChatResponseDto,
  type ApprovalDto,
} from '../services/api';

const PIPELINE_NODES = [
  { id: 'understand_request', name: '1. Understand', desc: 'Normalize input & context' },
  { id: 'classify_intent', name: '2. Classify', desc: 'Domain intent recognition' },
  { id: 'plan_actions', name: '3. Plan', desc: 'Action planning & tool selection' },
  { id: 'route_agent', name: '4. Route', desc: 'Specialist agent assignment' },
  { id: 'approval_gate', name: '5. Approval Gate', desc: 'Deterministic policy check' },
  { id: 'execute_tool', name: '6. Execute', desc: 'Narrowly scoped tool run' },
  { id: 'validate_result', name: '7. Validate', desc: 'Output verification & recovery' },
  { id: 'save_memory', name: '8. Memory', desc: 'Context & audit logging' },
  { id: 'generate_response', name: '9. Response', desc: 'Natural language outcome' },
];

export function AgentOrchestrator() {
  const [inputMessage, setInputMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const [lastResponse, setLastResponse] = useState<ChatResponseDto | null>(null);
  const [pendingApprovals, setPendingApprovals] = useState<ApprovalDto[]>([]);
  const [approvalsLoading, setApprovalsLoading] = useState(false);
  const [actionFeedback, setActionFeedback] = useState<string | null>(null);

  // Load pending approvals
  const loadApprovals = async () => {
    setApprovalsLoading(true);
    try {
      const data = await fetchApprovals('pending');
      setPendingApprovals(data);
    } catch (err) {
      console.error('Failed to fetch approvals:', err);
    } finally {
      setApprovalsLoading(false);
    }
  };

  useEffect(() => {
    loadApprovals();
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputMessage.trim() || loading) return;

    setLoading(true);
    setActionFeedback(null);
    try {
      const res = await submitChatMessage(inputMessage.trim());
      setLastResponse(res);
      setInputMessage('');
      if (res.approval_required) {
        await loadApprovals();
      }
    } catch (err: any) {
      setActionFeedback(`Error: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleDecision = async (approvalId: string, decision: 'approved' | 'rejected') => {
    try {
      const res = await submitApprovalDecision(approvalId, decision);
      setActionFeedback(res.message);
      await loadApprovals();
    } catch (err: any) {
      setActionFeedback(`Decision error: ${err.message}`);
    }
  };

  const isNodeActive = (nodeId: string): boolean => {
    if (!lastResponse) return false;
    if (lastResponse.approval_required && lastResponse.approval_status === 'pending') {
      // Paused at approval gate
      return ['understand_request', 'classify_intent', 'plan_actions', 'route_agent', 'approval_gate'].includes(nodeId);
    }
    return true;
  };

  const isApprovalPaused = lastResponse?.approval_required && lastResponse?.approval_status === 'pending';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {/* Visual LangGraph 9-Node Pipeline Tracker */}
      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <div>
            <h2 style={{ fontSize: '1.1rem', fontWeight: 700, color: '#f8fafc', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Layers size={18} color="#6366f1" /> LangGraph 9-Node Orchestration Graph
            </h2>
            <p style={{ fontSize: '0.8rem', color: '#94a3b8' }}>
              Deterministic state graph with human-in-the-loop approval gate checkpointing
            </p>
          </div>

          <div className="badge badge-info">
            Status: {lastResponse ? lastResponse.workflow_status.toUpperCase() : 'READY'}
          </div>
        </div>

        {/* Horizontal Node Flow */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(115px, 1fr))',
            gap: '8px',
            alignItems: 'center',
          }}
        >
          {PIPELINE_NODES.map((node) => {
            const active = isNodeActive(node.id);
            const isGate = node.id === 'approval_gate';

            let bgColor = 'rgba(255, 255, 255, 0.03)';
            let borderColor = 'rgba(255, 255, 255, 0.08)';
            let textColor = '#64748b';

            if (isGate && isApprovalPaused) {
              bgColor = 'rgba(245, 158, 11, 0.18)';
              borderColor = '#f59e0b';
              textColor = '#fbbf24';
            } else if (active) {
              bgColor = 'rgba(99, 102, 241, 0.12)';
              borderColor = 'rgba(99, 102, 241, 0.35)';
              textColor = '#c7d2fe';
            }

            return (
              <div
                key={node.id}
                style={{
                  background: bgColor,
                  border: `1px solid ${borderColor}`,
                  borderRadius: '8px',
                  padding: '10px 8px',
                  textAlign: 'center',
                  transition: 'all 0.3s ease',
                  position: 'relative',
                }}
              >
                <div style={{ fontSize: '0.75rem', fontWeight: 700, color: textColor, marginBottom: '2px' }}>
                  {node.name}
                </div>
                <div style={{ fontSize: '0.65rem', color: '#94a3b8', lineHeight: 1.2 }}>
                  {node.desc}
                </div>
                {isGate && isApprovalPaused && (
                  <span
                    style={{
                      position: 'absolute',
                      top: '-6px',
                      right: '-6px',
                      background: '#f59e0b',
                      color: '#000000',
                      borderRadius: '50%',
                      width: '14px',
                      height: '14px',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      fontSize: '9px',
                      fontWeight: 900,
                    }}
                  >
                    !
                  </span>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Main Grid: Query Interface & Pending Approvals */}
      <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr', gap: '24px' }}>
        {/* Left Column: Chat Request & Execution Output */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {/* Query Form Card */}
          <div className="card">
            <h3 style={{ fontSize: '0.95rem', fontWeight: 700, color: '#f8fafc', marginBottom: '12px' }}>
              Execute Agentic Workflow
            </h3>

            <form onSubmit={handleSubmit}>
              <div style={{ display: 'flex', gap: '10px', marginBottom: '14px' }}>
                <input
                  type="text"
                  value={inputMessage}
                  onChange={(e) => setInputMessage(e.target.value)}
                  placeholder="e.g. 'Show all tasks', 'Create task: Deploy App', 'Delete task task-sample-1'..."
                  style={{
                    flex: 1,
                    padding: '10px 14px',
                    borderRadius: '8px',
                    background: 'rgba(255, 255, 255, 0.05)',
                    border: '1px solid rgba(255, 255, 255, 0.1)',
                    color: '#ffffff',
                    fontSize: '0.88rem',
                  }}
                />
                <button
                  type="submit"
                  disabled={loading || !inputMessage.trim()}
                  style={{
                    background: 'linear-gradient(135deg, #4f46e5 0%, #06b6d4 100%)',
                    color: '#ffffff',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                  }}
                >
                  <Send size={15} /> Execute
                </button>
              </div>
            </form>

            {/* Quick Test Prompt Pills */}
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
              <span style={{ fontSize: '0.72rem', color: '#94a3b8', alignSelf: 'center', marginRight: '4px' }}>
                Quick Test Scenarios:
              </span>
              <button
                type="button"
                onClick={() => setInputMessage('Show all my tasks')}
                style={{
                  fontSize: '0.75rem',
                  padding: '4px 10px',
                  background: 'rgba(16, 185, 129, 0.12)',
                  color: '#34d399',
                  border: '1px solid rgba(16, 185, 129, 0.25)',
                }}
              >
                Safe Read: "Show all my tasks"
              </button>
              <button
                type="button"
                onClick={() => setInputMessage('create task Review Database Schemas')}
                style={{
                  fontSize: '0.75rem',
                  padding: '4px 10px',
                  background: 'rgba(99, 102, 241, 0.12)',
                  color: '#a5b4fc',
                  border: '1px solid rgba(99, 102, 241, 0.25)',
                }}
              >
                Safe Write: "Create task..."
              </button>
              <button
                type="button"
                onClick={() => setInputMessage('delete task task-sample-1')}
                style={{
                  fontSize: '0.75rem',
                  padding: '4px 10px',
                  background: 'rgba(245, 158, 11, 0.12)',
                  color: '#fbbf24',
                  border: '1px solid rgba(245, 158, 11, 0.25)',
                }}
              >
                Sensitive: "Delete task..." (Approval Gate)
              </button>
            </div>
          </div>

          {/* Feedback banner */}
          {actionFeedback && (
            <div
              className="card"
              style={{
                background: 'rgba(59, 130, 246, 0.1)',
                border: '1px solid rgba(59, 130, 246, 0.3)',
                padding: '12px 16px',
                display: 'flex',
                alignItems: 'center',
                gap: '10px',
                fontSize: '0.85rem',
                color: '#93c5fd',
              }}
            >
              <CheckCircle2 size={18} color="#60a5fa" />
              {actionFeedback}
            </div>
          )}

          {/* Execution Result Card */}
          {lastResponse ? (
            <div className="card">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
                <span style={{ fontSize: '0.82rem', color: '#94a3b8', textTransform: 'uppercase', fontWeight: 600 }}>
                  Orchestrator Result ({lastResponse.request_id})
                </span>
                <span
                  style={{
                    fontSize: '0.75rem',
                    fontWeight: 700,
                    padding: '2px 8px',
                    borderRadius: '4px',
                    background:
                      lastResponse.workflow_status === 'completed'
                        ? 'rgba(16, 185, 129, 0.15)'
                        : lastResponse.workflow_status === 'pending_approval'
                        ? 'rgba(245, 158, 11, 0.15)'
                        : 'rgba(239, 68, 68, 0.15)',
                    color:
                      lastResponse.workflow_status === 'completed'
                        ? '#34d399'
                        : lastResponse.workflow_status === 'pending_approval'
                        ? '#fbbf24'
                        : '#f87171',
                  }}
                >
                  {lastResponse.workflow_status.toUpperCase()}
                </span>
              </div>

              {/* Natural Language Response */}
              <div
                style={{
                  background: 'rgba(255, 255, 255, 0.04)',
                  padding: '14px',
                  borderRadius: '8px',
                  borderLeft: `4px solid ${
                    lastResponse.approval_required ? '#f59e0b' : '#10b981'
                  }`,
                  marginBottom: '16px',
                }}
              >
                <div style={{ fontSize: '0.75rem', fontWeight: 600, color: '#94a3b8', marginBottom: '4px' }}>
                  FINAL ASSISTANT RESPONSE
                </div>
                <div style={{ fontSize: '0.92rem', color: '#f8fafc', lineHeight: 1.45 }}>
                  {lastResponse.final_response}
                </div>
              </div>

              {/* State Metadata Chips */}
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px', marginBottom: '16px' }}>
                <div style={{ fontSize: '0.75rem', background: 'rgba(255, 255, 255, 0.05)', padding: '4px 10px', borderRadius: '6px' }}>
                  Intent: <strong style={{ color: '#38bdf8' }}>{lastResponse.normalized_intent}</strong>
                </div>
                <div style={{ fontSize: '0.75rem', background: 'rgba(255, 255, 255, 0.05)', padding: '4px 10px', borderRadius: '6px' }}>
                  Specialist: <strong style={{ color: '#a78bfa' }}>{lastResponse.current_agent}</strong>
                </div>
                <div style={{ fontSize: '0.75rem', background: 'rgba(255, 255, 255, 0.05)', padding: '4px 10px', borderRadius: '6px' }}>
                  Tools Run: <strong style={{ color: '#34d399' }}>{lastResponse.tool_results.length}</strong>
                </div>
              </div>

              {/* Tool Execution Details */}
              {lastResponse.tool_results.length > 0 && (
                <div>
                  <div style={{ fontSize: '0.8rem', fontWeight: 600, color: '#cbd5e1', marginBottom: '8px' }}>
                    Tool Execution Payloads:
                  </div>
                  <pre>{JSON.stringify(lastResponse.tool_results, null, 2)}</pre>
                </div>
              )}
            </div>
          ) : (
            <div
              className="card"
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
              <Bot size={36} style={{ marginBottom: '12px', opacity: 0.4 }} />
              <p style={{ fontSize: '0.9rem', fontWeight: 500 }}>No active orchestration run.</p>
              <p style={{ fontSize: '0.78rem', color: '#64748b', maxWidth: '320px', marginTop: '4px' }}>
                Type an instruction above or click a test scenario to trigger the LangGraph state workflow.
              </p>
            </div>
          )}
        </div>

        {/* Right Column: Pending Approvals (Human-in-the-Loop) */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <div className="card" style={{ flex: 1 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <div>
                <h3 style={{ fontSize: '1rem', fontWeight: 700, color: '#f8fafc', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Shield size={18} color="#f59e0b" /> Approval Gate Queue
                </h3>
                <p style={{ fontSize: '0.75rem', color: '#94a3b8' }}>
                  Actions requiring explicit user consent before execution
                </p>
              </div>

              <button
                onClick={loadApprovals}
                disabled={approvalsLoading}
                style={{
                  padding: '4px 8px',
                  fontSize: '0.75rem',
                  background: 'rgba(255, 255, 255, 0.08)',
                  color: '#94a3b8',
                }}
              >
                Refresh
              </button>
            </div>

            {pendingApprovals.length === 0 ? (
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
                <CheckCircle size={36} style={{ marginBottom: '12px', opacity: 0.4, color: '#10b981' }} />
                <p style={{ fontSize: '0.9rem', fontWeight: 500, color: '#94a3b8' }}>No Pending Approvals</p>
                <p style={{ fontSize: '0.78rem', color: '#64748b', maxWidth: '280px', marginTop: '4px' }}>
                  All actions are cleared. Try requesting "Delete task task-sample-1" to test the approval gate.
                </p>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                {pendingApprovals.map((appr) => (
                  <div
                    key={appr.id}
                    style={{
                      background: 'rgba(245, 158, 11, 0.08)',
                      border: '1px solid rgba(245, 158, 11, 0.3)',
                      borderRadius: '10px',
                      padding: '16px',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px' }}>
                      <span
                        style={{
                          fontSize: '0.72rem',
                          fontWeight: 700,
                          color: '#fbbf24',
                          background: 'rgba(245, 158, 11, 0.2)',
                          padding: '2px 8px',
                          borderRadius: '4px',
                        }}
                      >
                        {appr.tool_name.toUpperCase()}
                      </span>
                      <span style={{ fontSize: '0.7rem', color: '#94a3b8' }}>
                        {new Date(appr.created_at).toLocaleTimeString()}
                      </span>
                    </div>

                    <div style={{ fontWeight: 600, color: '#f8fafc', fontSize: '0.92rem', marginBottom: '6px' }}>
                      {appr.action_summary}
                    </div>

                    {appr.tool_payload && (
                      <div style={{ marginBottom: '12px' }}>
                        <div style={{ fontSize: '0.72rem', color: '#94a3b8', marginBottom: '2px' }}>Arguments:</div>
                        <pre style={{ fontSize: '0.75rem', padding: '8px' }}>
                          {JSON.stringify(appr.tool_payload, null, 2)}
                        </pre>
                      </div>
                    )}

                    {/* Action buttons */}
                    <div style={{ display: 'flex', gap: '10px', marginTop: '8px' }}>
                      <button
                        onClick={() => handleDecision(appr.id, 'approved')}
                        style={{
                          flex: 1,
                          background: '#10b981',
                          color: '#ffffff',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          gap: '6px',
                          fontSize: '0.8rem',
                          padding: '8px 12px',
                        }}
                      >
                        <CheckCircle2 size={15} /> Approve & Execute
                      </button>
                      <button
                        onClick={() => handleDecision(appr.id, 'rejected')}
                        style={{
                          flex: 1,
                          background: 'rgba(239, 68, 68, 0.2)',
                          color: '#f87171',
                          border: '1px solid rgba(239, 68, 68, 0.4)',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          gap: '6px',
                          fontSize: '0.8rem',
                          padding: '8px 12px',
                        }}
                      >
                        <XCircle size={15} /> Reject
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
