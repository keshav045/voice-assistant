import React, { useState, useEffect, useRef } from 'react';
import {
  CheckCircle2,
  Layers,
  Shield,
  Plus,
  MessageSquare,
  Terminal,
  Calendar as CalendarIcon,
  Mail,
  Monitor,
  Sparkles,
  ChevronDown,
  Mic,
  ArrowUp,
  FileText,
  AlertTriangle,
  Folder,
  Zap,
} from 'lucide-react';
import {
  submitChatMessage,
  fetchApprovals,
} from '../services/api';

interface ChatItem {
  id: string;
  sender: 'user' | 'orchestrator' | 'agent';
  agentName?: string;
  actionName?: string;
  timestamp: string;
  content?: string;
  cardType?: 'calendar_collision' | 'gmail_drafts' | 'desktop_audit' | 'standard';
  data?: any;
}

export function AgentOrchestrator() {
  const [inputMessage, setInputMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const [, setPendingApprovals] = useState<any[]>([]);
  const [actionFeedback, setActionFeedback] = useState<string | null>(null);
  const [selectedThread, setSelectedThread] = useState<string>('q3_financial');
  const [selectedModel, setSelectedModel] = useState<string>('Nexus Ultra Reasoning');

  // Messages stream initialized to match Image 4 mockup state
  const [messages, setMessages] = useState<ChatItem[]>([
    {
      id: 'msg-1',
      sender: 'orchestrator',
      agentName: 'Calendar Sentinel',
      actionName: 'conflict_scan()',
      timestamp: '14:02',
      cardType: 'calendar_collision',
      content:
        'Checked availability for 8 core leads for tomorrow (Thursday, Nov 14). Found 1 meeting collision for Marcus Vance & Priya Sen at 14:00. Nexus recommends adjusting slot to 15:30 - 16:15 EST.',
    },
    {
      id: 'msg-2',
      sender: 'agent',
      agentName: 'Gmail Agent',
      actionName: 'generate_executive_replies()',
      timestamp: '14:05',
      cardType: 'gmail_drafts',
      data: {
        draft1: {
          id: '1084',
          type: 'Concise',
          to: 'Sarah Jenkins (VP Eng)',
          body: 'Sarah, specs for Q3 mobile integration have been locked and validated locally. We anticipate clean rollout with 0 schema rollbacks.',
          status: 'staged',
        },
        draft2: {
          id: '1085',
          type: 'Strategic',
          to: 'David Chen (VP Strategy)',
          body: 'David, noted on the board deck milestones. We have incorporated automated agent failovers to mitigate all third-party drift.',
          status: 'staged',
        },
      },
    },
    {
      id: 'msg-3',
      sender: 'agent',
      agentName: 'Desktop Agent (Win11 Daemon)',
      actionName: 'sha256_audit_file()',
      timestamp: '14:07',
      cardType: 'desktop_audit',
      data: {
        path: 'C:\\Projects\\Nexus\\specs.pdf',
        size: '4.2 MB',
        checksum: '8f4c2e11a90b4d... [Synced with Git Tag v2.4-preview]',
      },
    },
    {
      id: 'msg-4',
      sender: 'orchestrator',
      timestamp: '14:08',
      cardType: 'standard',
      content:
        'Would you like me to dispatch both approved emails and lock 15:30 on Google Calendar simultaneously?',
    },
  ]);

  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  const loadApprovals = async () => {
    try {
      const data = await fetchApprovals('pending');
      setPendingApprovals(data);
    } catch (err) {
      console.error('Failed to fetch approvals:', err);
    }
  };

  useEffect(() => {
    loadApprovals();
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSubmit = async (e?: React.FormEvent, customPrompt?: string) => {
    if (e) e.preventDefault();
    const promptToSend = customPrompt || inputMessage.trim();
    if (!promptToSend || loading) return;

    const userMsg: ChatItem = {
      id: `user-${Date.now()}`,
      sender: 'user',
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      cardType: 'standard',
      content: promptToSend,
    };
    setMessages((prev) => [...prev, userMsg]);
    setInputMessage('');
    setLoading(true);
    setActionFeedback(null);

    try {
      const res = await submitChatMessage(promptToSend);

      const agentMsg: ChatItem = {
        id: `agent-${Date.now()}`,
        sender: 'orchestrator',
        agentName: 'Nexus Orchestrator',
        actionName: (res as any).intent || res.workflow_status || 'execute_pipeline()',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        cardType: 'standard',
        content: res.final_response || 'Workflow executed successfully across nodes.',
      };
      setMessages((prev) => [...prev, agentMsg]);

      if (res.approval_required) {
        await loadApprovals();
      }
    } catch (err: any) {
      setActionFeedback(`Error: ${err.message}`);
      setMessages((prev) => [
        ...prev,
        {
          id: `err-${Date.now()}`,
          sender: 'orchestrator',
          agentName: 'System Error Handler',
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          cardType: 'standard',
          content: `Failed to execute: ${err.message || 'Unknown network error'}.`,
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleApproveDraft = async (draftId: string) => {
    setActionFeedback(`Draft #${draftId} approved and staged for immediate SMTP dispatch.`);
    setMessages((prev) => [
      ...prev,
      {
        id: `ack-${Date.now()}`,
        sender: 'agent',
        agentName: 'Gmail Agent',
        actionName: 'send_draft()',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        cardType: 'standard',
        content: `Approval confirmed for Draft #${draftId}. Email queued for high-priority dispatch with TLS encryption.`,
      },
    ]);
  };

  const handleHoldCalendarSlot = () => {
    setActionFeedback('Slot 15:30 - 16:15 EST held on Google Calendar. Calendar invites created.');
    setMessages((prev) => [
      ...prev,
      {
        id: `cal-${Date.now()}`,
        sender: 'agent',
        agentName: 'Calendar Sentinel',
        actionName: 'resolve_collision()',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        cardType: 'standard',
        content:
          'Calendar collision resolved. 15:30 - 16:15 EST blocked and invites dispatched to Marcus Vance & Priya Sen.',
      },
    ]);
  };

  return (
    <div className="flex flex-col gap-5 text-white max-w-[1600px] mx-auto pb-10">
      {/* 2-Column Orchestration Workspace */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
        {/* Left Sub-Panel: Conversations, Active Intelligence & Threads (col-span-3) */}
        <div className="lg:col-span-3 card-mono p-4 flex flex-col justify-between h-[820px] bg-[#0c0c0e] border border-[#27272a]">
          <div className="space-y-4">
            {/* New Conversation Button */}
            <button
              onClick={() => {
                setMessages([]);
                setActionFeedback('Started fresh orchestration conversation.');
              }}
              className="btn-primary-mono !w-full !py-2.5 flex items-center justify-between text-xs font-semibold cursor-pointer"
            >
              <div className="flex items-center gap-2">
                <Plus size={15} />
                <span>New Conversation</span>
              </div>
              <span className="font-mono text-[10px] bg-black text-white px-2 py-0.5 rounded">Ctrl+N</span>
            </button>

            {/* Active Intelligence Box */}
            <div className="p-3 rounded-xl bg-[#18181b] border border-[#27272a] space-y-2">
              <div className="flex items-center justify-between text-[11px]">
                <div className="flex items-center gap-1.5 text-[#a1a1aa] font-bold uppercase tracking-wider text-[10px]">
                  <span className="w-2 h-2 rounded-full bg-white animate-mono-pulse" />
                  <span>Active Intelligence</span>
                </div>
              </div>
              <div
                onClick={() =>
                  setSelectedModel((prev) =>
                    prev === 'Nexus Ultra Reasoning'
                      ? 'Gemini 1.5 Pro (Google)'
                      : prev === 'Gemini 1.5 Pro (Google)'
                      ? 'Claude 3.5 Sonnet'
                      : 'Nexus Ultra Reasoning'
                  )
                }
                className="flex items-center justify-between px-3 py-2 rounded-lg bg-[#121215] border border-[#27272a] hover:border-white text-xs cursor-pointer transition-colors"
              >
                <span className="font-semibold text-white">{selectedModel}</span>
                <ChevronDown size={13} className="text-[#a1a1aa]" />
              </div>
              <p className="text-[10px] text-[#71717a]">Fallbacks: Sonnet 3.5 • GPT-4o</p>
            </div>

            {/* Thread History Groups */}
            <div className="space-y-4 overflow-y-auto max-h-[500px] pr-1">
              {/* Group: TODAY */}
              <div>
                <div className="flex items-center justify-between text-[10px] uppercase font-bold text-[#71717a] mb-2">
                  <span>Today</span>
                  <span>2 threads</span>
                </div>
                <div className="space-y-1.5">
                  <div
                    onClick={() => setSelectedThread('q3_financial')}
                    className={`p-2.5 rounded-lg border text-xs cursor-pointer transition-colors ${
                      selectedThread === 'q3_financial'
                        ? 'bg-[#18181b] border-white text-white'
                        : 'bg-transparent border-transparent hover:bg-[#121215] text-[#a1a1aa]'
                    }`}
                  >
                    <div className="flex items-center justify-between font-medium text-[11px] mb-1">
                      <div className="flex items-center gap-2 truncate">
                        <MessageSquare size={13} className="flex-shrink-0" />
                        <span className="truncate">Q3 Financial Strategy Synthe...</span>
                      </div>
                      <span className="w-1.5 h-1.5 rounded-full bg-white flex-shrink-0" />
                    </div>
                    <div className="text-[10px] text-[#71717a] ml-5">4 agents • 18 tool executions</div>
                  </div>

                  <div
                    onClick={() => setSelectedThread('desktop_auto')}
                    className={`p-2.5 rounded-lg border text-xs cursor-pointer transition-colors ${
                      selectedThread === 'desktop_auto'
                        ? 'bg-[#18181b] border-white text-white'
                        : 'bg-transparent border-transparent hover:bg-[#121215] text-[#a1a1aa]'
                    }`}
                  >
                    <div className="flex items-center justify-between font-medium text-[11px] mb-1">
                      <div className="flex items-center gap-2 truncate">
                        <Terminal size={13} className="flex-shrink-0" />
                        <span className="truncate">Desktop automation script review</span>
                      </div>
                    </div>
                    <div className="text-[10px] text-[#71717a] ml-5">Active Win11 subprocess</div>
                  </div>
                </div>
              </div>

              {/* Group: YESTERDAY */}
              <div>
                <div className="flex items-center justify-between text-[10px] uppercase font-bold text-[#71717a] mb-2">
                  <span>Yesterday</span>
                  <span>1 thread</span>
                </div>
                <div
                  onClick={() => setSelectedThread('product_spec')}
                  className={`p-2.5 rounded-lg border text-xs cursor-pointer transition-colors ${
                    selectedThread === 'product_spec'
                      ? 'bg-[#18181b] border-white text-white'
                      : 'bg-transparent border-transparent hover:bg-[#121215] text-[#a1a1aa]'
                  }`}
                >
                  <div className="flex items-center justify-between font-medium text-[11px] mb-1">
                    <div className="flex items-center gap-2 truncate">
                      <FileText size={13} className="flex-shrink-0" />
                      <span className="truncate">Product spec generation for Mo...</span>
                    </div>
                  </div>
                  <div className="text-[10px] text-[#71717a] ml-5">Completed • 2 drafts</div>
                </div>
              </div>

              {/* Group: PREVIOUS 7 DAYS */}
              <div>
                <div className="flex items-center justify-between text-[10px] uppercase font-bold text-[#71717a] mb-2">
                  <span>Previous 7 Days</span>
                  <span>3 threads</span>
                </div>
                <div className="space-y-1.5">
                  <div className="p-2.5 rounded-lg hover:bg-[#121215] text-[#a1a1aa] text-xs cursor-pointer">
                    <div className="flex items-center gap-2 font-medium text-[11px] mb-1 truncate">
                      <Mail size={13} className="flex-shrink-0" />
                      <span className="truncate">Customer escalate resolution log</span>
                    </div>
                    <div className="text-[10px] text-[#71717a] ml-5">3 emails auto-dispatched</div>
                  </div>

                  <div className="p-2.5 rounded-lg hover:bg-[#121215] text-[#a1a1aa] text-xs cursor-pointer">
                    <div className="flex items-center gap-2 font-medium text-[11px] mb-1 truncate">
                      <Layers size={13} className="flex-shrink-0" />
                      <span className="truncate">Board Deck metrics cross-check</span>
                    </div>
                    <div className="text-[10px] text-[#71717a] ml-5">Verified via Snowflake API</div>
                  </div>

                  <div className="p-2.5 rounded-lg hover:bg-[#121215] text-[#a1a1aa] text-xs cursor-pointer">
                    <div className="flex items-center gap-2 font-medium text-[11px] mb-1 truncate">
                      <Shield size={13} className="flex-shrink-0" />
                      <span className="truncate">Security perimeter permission s...</span>
                    </div>
                    <div className="text-[10px] text-[#71717a] ml-5">Desktop Agent signed</div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Bottom Autonomous Mode READY badge */}
          <div className="pt-3 border-t border-[#222226] flex items-center justify-between text-xs">
            <div className="flex items-center gap-2 text-white font-medium">
              <Zap size={14} />
              <span>Autonomous Mode</span>
            </div>
            <span className="bg-[#18181b] border border-[#3f3f46] text-white px-2.5 py-0.5 rounded-full text-[10px] font-mono font-bold tracking-wider">
              READY
            </span>
          </div>
        </div>

        {/* Right Column: Active Multi-Agent Orchestration Canvas (col-span-9) */}
        <div className="lg:col-span-9 card-mono p-5 flex flex-col justify-between h-[820px] bg-[#0c0c0e] border border-[#27272a] relative">
          <div>
            {/* Header: Topic, Active Orchestration pill, Agent Tags */}
            <div className="flex flex-wrap items-center justify-between gap-3 pb-4 border-b border-[#222226] mb-4">
              <div>
                <div className="flex items-center gap-2.5">
                  <div className="w-7 h-7 rounded-lg bg-[#18181b] border border-[#27272a] flex items-center justify-center text-white">
                    <Sparkles size={15} />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <h2 className="text-base font-bold text-white tracking-wide">
                        Strategic Roadmap & Executive Gmail Triage
                      </h2>
                      <span className="text-[10px] font-mono uppercase bg-[#18181b] text-white border border-[#3f3f46] px-2 py-0.5 rounded-full font-bold">
                        • ACTIVE ORCHESTRATION
                      </span>
                    </div>
                    <p className="text-[11px] text-[#71717a] font-mono mt-0.5">
                      Session #NX-9402 • Context Window: 48.2k / 128k Tokens
                    </p>
                  </div>
                </div>
              </div>

              {/* Agent Membership Badges */}
              <div className="flex items-center gap-2 flex-wrap">
                <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-[#18181b] border border-[#27272a] text-[11px] font-medium text-white">
                  <span className="w-1.5 h-1.5 rounded-full bg-white" />
                  Orchestrator Agent
                </span>
                <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-[#18181b] border border-[#27272a] text-[11px] font-medium text-white">
                  <span className="w-1.5 h-1.5 rounded-full bg-white" />
                  Gmail Agent
                </span>
                <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-[#18181b] border border-[#27272a] text-[11px] font-medium text-white">
                  <span className="w-1.5 h-1.5 rounded-full bg-white" />
                  Desktop Agent
                </span>
                <button
                  title="Add Agent"
                  className="w-7 h-7 rounded-full bg-[#18181b] border border-[#27272a] hover:border-white text-white flex items-center justify-center text-xs cursor-pointer transition-colors"
                >
                  <Plus size={13} />
                </button>
              </div>
            </div>

            {actionFeedback && (
              <div className="mb-3 px-3 py-2 rounded-lg bg-[#18181b] border border-[#3f3f46] text-xs text-white flex items-center justify-between">
                <span>{actionFeedback}</span>
                <button onClick={() => setActionFeedback(null)} className="text-[#a1a1aa] hover:text-white text-xs">
                  ✕
                </button>
              </div>
            )}

            {/* Conversation Stream */}
            <div className="overflow-y-auto max-h-[540px] pr-2 space-y-4">
              {messages.map((item) => {
                if (item.cardType === 'calendar_collision') {
                  return (
                    <div
                      key={item.id}
                      className="p-4 rounded-xl bg-[#141416] border border-[#2e2e33] space-y-3"
                    >
                      <div className="flex items-center justify-between text-xs">
                        <div className="flex items-center gap-2">
                          <span className="text-white font-bold tracking-wide flex items-center gap-1.5">
                            <AlertTriangle size={15} />
                            Collision Detected (14:00)
                          </span>
                          <span className="text-[#71717a]">• 7 Soon Impact</span>
                        </div>
                        <span className="text-[#71717a] font-mono text-[10px]">{item.timestamp}</span>
                      </div>

                      <p className="text-xs text-[#d4d4d8] leading-relaxed">{item.content}</p>

                      <div className="flex flex-wrap gap-2.5 pt-1">
                        <button
                          onClick={handleHoldCalendarSlot}
                          className="btn-primary-mono !text-xs !py-1.5 cursor-pointer"
                        >
                          <CalendarIcon size={13} />
                          <span>Hold 15:30 Slot & Dispatch Invites</span>
                        </button>
                        <button className="btn-secondary-mono !text-xs !py-1.5 cursor-pointer">
                          <span>Adjust Window</span>
                        </button>
                      </div>
                    </div>
                  );
                }

                if (item.cardType === 'gmail_drafts') {
                  const drafts = item.data;
                  return (
                    <div
                      key={item.id}
                      className="p-4 rounded-xl bg-[#141416] border border-[#2e2e33] space-y-3"
                    >
                      <div className="flex items-center justify-between text-xs">
                        <div className="flex items-center gap-2">
                          <Mail size={15} className="text-white" />
                          <span className="font-bold text-white">Gmail Agent</span>
                          <span className="font-mono text-[#a1a1aa] text-[11px]">
                            generate_executive_replies()
                          </span>
                        </div>
                        <span className="text-[10px] font-mono bg-[#1f1f23] text-white border border-[#38383e] px-2.5 py-0.5 rounded-full font-bold">
                          • 2 Drafts Staged
                        </span>
                      </div>

                      {/* Side-by-side draft cards */}
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1">
                        {/* Draft 1 */}
                        <div className="p-3.5 rounded-lg bg-[#18181b] border border-[#27272a] space-y-2.5 text-xs">
                          <div className="flex items-center justify-between text-[11px]">
                            <span className="font-bold text-white">Draft #1084 (Concise)</span>
                            <span className="text-[#a1a1aa]">To: Sarah Jenkins (VP Eng)</span>
                          </div>
                          <p className="text-[11px] text-[#a1a1aa] italic leading-relaxed">
                            "{drafts.draft1.body}"
                          </p>
                          <div className="flex gap-2 pt-1">
                            <button className="btn-secondary-mono !w-full !py-1 !text-[11px]">
                              Preview Full
                            </button>
                            <button
                              onClick={() => handleApproveDraft(drafts.draft1.id)}
                              className="btn-primary-mono !w-full !py-1 !text-[11px] cursor-pointer"
                            >
                              <CheckCircle2 size={12} />
                              <span>Approve</span>
                            </button>
                          </div>
                        </div>

                        {/* Draft 2 */}
                        <div className="p-3.5 rounded-lg bg-[#18181b] border border-[#27272a] space-y-2.5 text-xs">
                          <div className="flex items-center justify-between text-[11px]">
                            <span className="font-bold text-white">Draft #1085 (Strategic)</span>
                            <span className="text-[#a1a1aa]">To: David Chen (VP Strategy)</span>
                          </div>
                          <p className="text-[11px] text-[#a1a1aa] italic leading-relaxed">
                            "{drafts.draft2.body}"
                          </p>
                          <div className="flex gap-2 pt-1">
                            <button className="btn-secondary-mono !w-full !py-1 !text-[11px]">
                              Preview Full
                            </button>
                            <button
                              onClick={() => handleApproveDraft(drafts.draft2.id)}
                              className="btn-primary-mono !w-full !py-1 !text-[11px] cursor-pointer"
                            >
                              <CheckCircle2 size={12} />
                              <span>Approve</span>
                            </button>
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                }

                if (item.cardType === 'desktop_audit') {
                  return (
                    <div
                      key={item.id}
                      className="p-4 rounded-xl bg-[#141416] border border-[#2e2e33] space-y-3"
                    >
                      <div className="flex items-center justify-between text-xs">
                        <div className="flex items-center gap-2">
                          <Monitor size={15} className="text-white" />
                          <span className="font-bold text-white">Desktop Agent (Win11 Daemon)</span>
                          <span className="font-mono text-[#a1a1aa] text-[11px]">
                            sha256_audit_file()
                          </span>
                        </div>
                        <span className="text-[10px] font-mono bg-[#1f1f23] text-white border border-[#38383e] px-2.5 py-0.5 rounded-full font-bold flex items-center gap-1.5">
                          <CheckCircle2 size={12} />
                          VERIFIED INTACT
                        </span>
                      </div>

                      <div className="flex flex-wrap items-center justify-between gap-3 p-3 rounded-lg bg-[#18181b] border border-[#27272a] text-xs">
                        <div>
                          <div className="font-mono text-white font-medium flex items-center gap-2">
                            <span>{item.data.path}</span>
                            <span className="text-[10px] text-[#71717a] font-normal">{item.data.size}</span>
                          </div>
                          <div className="font-mono text-[10px] text-[#a1a1aa] mt-0.5">
                            Checksum: {item.data.checksum}
                          </div>
                        </div>

                        <button className="btn-secondary-mono !py-1.5 !px-3 !text-xs flex items-center gap-1.5 cursor-pointer">
                          <Folder size={13} />
                          <span>Show in Explorer</span>
                        </button>
                      </div>
                    </div>
                  );
                }

                // Standard turn
                return (
                  <div
                    key={item.id}
                    className={`p-3.5 rounded-xl border text-xs leading-relaxed ${
                      item.sender === 'user'
                        ? 'bg-[#18181b] border-[#38383e] text-white max-w-[85%] ml-auto'
                        : 'bg-[#121215] border-[#222226] text-[#e4e4e7] max-w-[92%]'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1.5 text-[11px] text-[#71717a]">
                      <div className="flex items-center gap-1.5">
                        <span
                          className={`w-1.5 h-1.5 rounded-full ${
                            item.sender === 'user' ? 'bg-white' : 'bg-[#71717a]'
                          }`}
                        />
                        <span className="font-semibold text-white">
                          {item.sender === 'user' ? 'Alex Vance' : item.agentName || 'Nexus Orchestrator'}
                        </span>
                      </div>
                      <span className="font-mono text-[10px]">{item.timestamp}</span>
                    </div>
                    <p className="font-normal">{item.content}</p>
                  </div>
                );
              })}
              <div ref={messagesEndRef} />
            </div>
          </div>

          {/* Bottom Prompt Dock & Quick Dispatches */}
          <div className="w-full pt-3 border-t border-[#222226] space-y-2.5">
            {/* Quick Dispatch Pills */}
            <div className="flex flex-wrap items-center gap-2 text-xs text-[#a1a1aa]">
              <span className="text-[10px] font-bold uppercase tracking-wider text-[#71717a]">
                Quick Dispatch:
              </span>
              {[
                { label: '/ summarize-threads', prompt: 'Summarize all high priority email and slack threads.' },
                { label: '/ schedule-sync', prompt: 'Find the earliest open 30 min slot for tomorrow and draft invite.' },
                { label: '/ draft-email', prompt: 'Draft executive update email to leadership regarding sprint milestones.' },
                { label: '/ verify-desktop-files', prompt: 'Run sha256 checksum audit on all staged deliverables.' },
              ].map((pill, idx) => (
                <button
                  key={idx}
                  onClick={() => handleSubmit(undefined, pill.prompt)}
                  className="px-2.5 py-1 rounded-full bg-[#18181b] border border-[#27272a] hover:border-[#3f3f46] text-white text-[11px] font-mono cursor-pointer transition-colors"
                >
                  {pill.label}
                </button>
              ))}
            </div>

            {/* Input Form with Command Bar */}
            <form onSubmit={handleSubmit} className="p-3 rounded-2xl bg-[#121215] border border-[#27272a] space-y-3">
              <input
                type="text"
                placeholder="Ask Nexus or type / to invoke specialized agents (e.g. /email, /calendar, /desktop)..."
                value={inputMessage}
                onChange={(e) => setInputMessage(e.target.value)}
                disabled={loading}
                className="w-full bg-transparent text-sm text-white placeholder-[#71717a] focus:outline-none"
              />

              <div className="flex flex-wrap items-center justify-between gap-2 pt-1 border-t border-[#1e1e24]">
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    className="w-8 h-8 rounded-lg bg-[#18181b] border border-[#27272a] text-[#a1a1aa] hover:text-white flex items-center justify-center cursor-pointer"
                  >
                    <Plus size={14} />
                  </button>

                  <div className="flex items-center gap-1.5 px-3 py-1 rounded-lg bg-[#18181b] border border-[#27272a] text-xs text-white">
                    <span className="w-1.5 h-1.5 rounded-full bg-white" />
                    <span>Orchestrator Ensembles</span>
                    <ChevronDown size={12} className="text-[#a1a1aa]" />
                  </div>

                  <span className="text-[11px] font-medium bg-[#18181b] border border-[#27272a] text-[#a1a1aa] px-2.5 py-1 rounded-lg flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 rounded-full bg-white" />
                    Context: High Priority
                  </span>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    title="Voice dictation"
                    className="w-8 h-8 rounded-lg bg-[#18181b] border border-[#27272a] text-[#a1a1aa] hover:text-white flex items-center justify-center cursor-pointer"
                  >
                    <Mic size={15} />
                  </button>

                  <button
                    type="submit"
                    disabled={loading || !inputMessage.trim()}
                    className="btn-primary-mono !py-1.5 !px-3.5 !text-xs flex items-center gap-1.5 disabled:opacity-40 cursor-pointer"
                  >
                    <span>{loading ? 'Thinking...' : 'Dispatch'}</span>
                    <ArrowUp size={14} />
                  </button>
                </div>
              </div>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}
