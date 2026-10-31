import React, { useState, useEffect } from 'react';
import {
  searchEmails,
  summarizeEmails,
  fetchEmailDrafts,
  createEmailDraft,
  sendEmail,
  fetchGoogleAuthUrl,
  fetchGoogleAuthStatus,
  disconnectGoogleAuth,
  type EmailMessageDto,
  type EmailDraftDto,
  type GoogleAuthStatusDto,
} from '../services/api';

export const EmailAssistant: React.FC = () => {
  const [messages, setMessages] = useState<EmailMessageDto[]>([]);
  const [drafts, setDrafts] = useState<EmailDraftDto[]>([]);
  const [selectedMessage, setSelectedMessage] = useState<EmailMessageDto | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [aiSummary, setAiSummary] = useState<string | null>(null);
  const [notification, setNotification] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [googleStatus, setGoogleStatus] = useState<GoogleAuthStatusDto | null>(null);

  // Composer state
  const [recipient, setRecipient] = useState('');
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const [activeTab, setActiveTab] = useState<'inbox' | 'drafts' | 'compose'>('inbox');

  useEffect(() => {
    loadInbox();
    loadDrafts();
    checkGoogleStatus();

    const handleMessage = (event: MessageEvent) => {
      if (event.data?.type === 'GOOGLE_CONNECTED') {
        showNotification('success', `Google Workspace account connected (${event.data.email})!`);
        checkGoogleStatus();
        loadInbox();
      }
    };
    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, []);

  const checkGoogleStatus = async () => {
    try {
      const st = await fetchGoogleAuthStatus();
      setGoogleStatus(st);
    } catch (e) {
      console.warn('Could not check Google status:', e);
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
      showNotification('error', err.message || 'Failed to start Google sign-in');
    }
  };

  const handleDisconnectGoogle = async () => {
    if (!window.confirm('Disconnect Google Workspace? Nexus will fall back to local offline mode.')) return;
    try {
      await disconnectGoogleAuth();
      showNotification('success', 'Google Workspace disconnected.');
      await checkGoogleStatus();
      await loadInbox();
    } catch (err: any) {
      showNotification('error', err.message || 'Disconnect failed');
    }
  };

  const showNotification = (type: 'success' | 'error', text: string) => {
    setNotification({ type, text });
    setTimeout(() => setNotification(null), 4500);
  };

  const loadInbox = async (query = '') => {
    setLoading(true);
    try {
      const data = await searchEmails(query);
      setMessages(data.messages);
      if (data.messages.length > 0 && !selectedMessage) {
        setSelectedMessage(data.messages[0]);
      }
    } catch (err: any) {
      showNotification('error', err.message || 'Failed to load inbox');
    } finally {
      setLoading(false);
    }
  };

  const loadDrafts = async () => {
    try {
      const data = await fetchEmailDrafts();
      setDrafts(data);
    } catch (err: any) {
      console.error('Failed to load drafts:', err);
    }
  };

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    loadInbox(searchQuery);
  };

  const handleGenerateSummary = async () => {
    setSummaryLoading(true);
    setAiSummary(null);
    try {
      const res = await summarizeEmails(searchQuery);
      setAiSummary(res.summary);
      showNotification('success', `Analyzed ${res.emails_analyzed} messages.`);
    } catch (err: any) {
      showNotification('error', err.message || 'Failed to summarize emails');
    } finally {
      setSummaryLoading(false);
    }
  };

  const handleSaveDraft = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!recipient || !subject || !body) {
      showNotification('error', 'Recipient, subject, and body are required.');
      return;
    }

    try {
      const draft = await createEmailDraft({ recipient, subject, body });
      showNotification('success', `Draft saved successfully (ID: ${draft.id.slice(0, 8)}).`);
      setDrafts([draft, ...drafts]);
      setRecipient('');
      setSubject('');
      setBody('');
      setActiveTab('drafts');
    } catch (err: any) {
      showNotification('error', err.message || 'Failed to create draft');
    }
  };

  const handleDirectSend = async (draftId?: string) => {
    const toSendRecipient = draftId ? drafts.find((d) => d.id === draftId)?.recipient || recipient : recipient;
    const toSendSubject = draftId ? drafts.find((d) => d.id === draftId)?.subject || subject : subject;
    const toSendBody = draftId ? drafts.find((d) => d.id === draftId)?.body || body : body;

    if (!toSendRecipient || !toSendSubject || !toSendBody) {
      showNotification('error', 'Cannot send email: missing fields.');
      return;
    }

    const confirmed = window.confirm(
      `APPROVAL GATE CONFIRMATION\n\nAre you sure you want to dispatch an email to "${toSendRecipient}" with subject "${toSendSubject}"?`
    );
    if (!confirmed) return;

    try {
      const res = await sendEmail({
        recipient: toSendRecipient,
        subject: toSendSubject,
        body: toSendBody,
        draft_id: draftId,
      });
      showNotification('success', res.message);
      await loadDrafts();
      if (!draftId) {
        setRecipient('');
        setSubject('');
        setBody('');
        setActiveTab('inbox');
      }
    } catch (err: any) {
      showNotification('error', err.message || 'Failed to dispatch email');
    }
  };

  const handleReplyToMessage = (msg: EmailMessageDto) => {
    setRecipient(msg.sender);
    setSubject(msg.subject.startsWith('Re:') ? msg.subject : `Re: ${msg.subject}`);
    setBody(`\n\n--- On ${new Date(msg.date).toLocaleDateString()}, ${msg.sender} wrote:\n> ${msg.body.replace(/\n/g, '\n> ')}`);
    setActiveTab('compose');
  };

  return (
    <div className="space-y-6">
      {/* Header and Control Bar */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-slate-900 border border-slate-800 p-5 rounded-2xl shadow-lg">
        <div>
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-rose-500/10 border border-rose-500/30 flex items-center justify-center text-rose-400 font-bold">
              ✉
            </div>
            <div>
              <h2 className="text-xl font-bold text-white tracking-tight flex items-center gap-2">
                Gmail & Email Intelligence
                <span className="text-xs bg-rose-500/20 text-rose-400 border border-rose-500/30 px-2 py-0.5 rounded-full font-mono">
                  Phase 5
                </span>
              </h2>
              <p className="text-sm text-slate-400">
                Inbox search, AI thread summarization, and human-in-the-loop email dispatch.
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {/* Google Workspace Connection Pill */}
          {googleStatus?.connected ? (
            <div className="px-3 py-1.5 rounded-xl border text-xs font-medium flex items-center gap-2 bg-emerald-500/10 text-emerald-400 border-emerald-500/30">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
              <span>Gmail Live ({googleStatus.email})</span>
              <button
                onClick={handleDisconnectGoogle}
                className="text-slate-400 hover:text-rose-400 ml-1 text-xs"
                title="Disconnect Google Account"
              >
                ✕
              </button>
            </div>
          ) : (
            <button
              onClick={handleConnectGoogle}
              className="px-3 py-1.5 bg-slate-800 hover:bg-slate-750 text-slate-200 border border-slate-700 hover:border-slate-600 rounded-xl text-xs font-medium transition flex items-center gap-1.5"
              title="Connect Google account for live Gmail & Google Calendar sync"
            >
              <span>🌐</span> Connect Google
            </button>
          )}

          <button
            onClick={handleGenerateSummary}
            disabled={summaryLoading}
            className="px-4 py-2 bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white rounded-xl text-sm font-medium transition shadow-md flex items-center gap-2 disabled:opacity-50"
          >
            {summaryLoading ? (
              <>
                <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                Analyzing...
              </>
            ) : (
              <>✨ Generate AI Summary</>
            )}
          </button>
          <button
            onClick={() => setActiveTab('compose')}
            className="px-4 py-2 bg-rose-600 hover:bg-rose-500 text-white rounded-xl text-sm font-medium transition shadow-md flex items-center gap-1.5"
          >
            ✏ Compose
          </button>
        </div>
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

      {/* AI Summary Banner if generated */}
      {aiSummary && (
        <div className="bg-gradient-to-r from-purple-950/40 to-slate-900 border border-purple-800/40 p-5 rounded-2xl shadow-xl">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-purple-300 flex items-center gap-2">
              <span className="text-base">✦</span> AI Inbox Intelligence Brief
            </h3>
            <button
              onClick={() => setAiSummary(null)}
              className="text-xs text-slate-400 hover:text-white"
            >
              ✕ Close
            </button>
          </div>
          <div className="text-sm text-slate-200 whitespace-pre-line leading-relaxed bg-black/30 p-4 rounded-xl border border-purple-900/30 font-mono">
            {aiSummary}
          </div>
        </div>
      )}

      {/* Navigation Tabs */}
      <div className="flex border-b border-slate-800 gap-2">
        <button
          onClick={() => setActiveTab('inbox')}
          className={`px-4 py-2.5 text-sm font-medium border-b-2 transition ${
            activeTab === 'inbox'
              ? 'border-rose-500 text-rose-400'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          Inbox ({messages.length})
        </button>
        <button
          onClick={() => setActiveTab('drafts')}
          className={`px-4 py-2.5 text-sm font-medium border-b-2 transition ${
            activeTab === 'drafts'
              ? 'border-rose-500 text-rose-400'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          Drafts & Outbox ({drafts.length})
        </button>
        <button
          onClick={() => setActiveTab('compose')}
          className={`px-4 py-2.5 text-sm font-medium border-b-2 transition ${
            activeTab === 'compose'
              ? 'border-rose-500 text-rose-400'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          New Message
        </button>
      </div>

      {/* Main Content Areas */}
      {activeTab === 'inbox' && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Inbox List */}
          <div className="lg:col-span-5 space-y-3">
            <form onSubmit={handleSearchSubmit} className="flex gap-2">
              <input
                type="text"
                placeholder="Search subject, sender, or content..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="flex-1 bg-slate-900 border border-slate-800 rounded-xl px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-rose-500"
              />
              <button
                type="submit"
                disabled={loading}
                className="px-3.5 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-xl text-sm font-medium transition"
              >
                Search
              </button>
            </form>

            <div className="space-y-2 max-h-[620px] overflow-y-auto pr-1">
              {loading ? (
                <div className="text-center py-10 text-slate-500 text-sm">Loading emails...</div>
              ) : messages.length === 0 ? (
                <div className="text-center py-10 text-slate-500 text-sm bg-slate-900/50 rounded-xl border border-slate-800">
                  No emails match your search.
                </div>
              ) : (
                messages.map((msg) => {
                  const isSelected = selectedMessage?.id === msg.id;
                  return (
                    <div
                      key={msg.id}
                      onClick={() => setSelectedMessage(msg)}
                      className={`p-4 rounded-xl border cursor-pointer transition text-left ${
                        isSelected
                          ? 'bg-rose-500/10 border-rose-500/40 shadow-sm'
                          : 'bg-slate-900/60 border-slate-800/80 hover:bg-slate-800/50'
                      }`}
                    >
                      <div className="flex items-center justify-between text-xs text-slate-400 mb-1">
                        <span className="font-semibold text-slate-300 truncate max-w-[200px]">
                          {msg.sender}
                        </span>
                        <span>{new Date(msg.date).toLocaleDateString()}</span>
                      </div>
                      <h4
                        className={`text-sm font-medium mb-1 truncate ${
                          msg.is_read ? 'text-slate-300' : 'text-white font-bold'
                        }`}
                      >
                        {msg.subject}
                      </h4>
                      <p className="text-xs text-slate-400 line-clamp-2 leading-relaxed">
                        {msg.snippet}
                      </p>
                      <div className="flex gap-1 mt-2">
                        {msg.labels.map((l) => (
                          <span
                            key={l}
                            className="text-[10px] bg-slate-800 text-slate-400 px-1.5 py-0.5 rounded border border-slate-700 font-mono"
                          >
                            {l}
                          </span>
                        ))}
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>

          {/* Email Reader View */}
          <div className="lg:col-span-7 bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl flex flex-col justify-between min-h-[500px]">
            {selectedMessage ? (
              <div className="space-y-4">
                <div className="border-b border-slate-800 pb-4">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-mono text-slate-400">ID: {selectedMessage.id}</span>
                    <span className="text-xs text-slate-400">
                      {new Date(selectedMessage.date).toLocaleString()}
                    </span>
                  </div>
                  <h3 className="text-xl font-bold text-white mb-2">{selectedMessage.subject}</h3>
                  <div className="text-xs text-slate-300 space-y-1">
                    <div>
                      <span className="text-slate-500">From:</span> {selectedMessage.sender}
                    </div>
                    <div>
                      <span className="text-slate-500">To:</span> {selectedMessage.recipient}
                    </div>
                  </div>
                </div>

                <div className="text-sm text-slate-200 whitespace-pre-wrap leading-relaxed py-2 font-sans">
                  {selectedMessage.body}
                </div>

                <div className="pt-4 border-t border-slate-800 flex items-center justify-between">
                  <button
                    onClick={() => handleReplyToMessage(selectedMessage)}
                    className="px-4 py-2 bg-rose-600 hover:bg-rose-500 text-white rounded-xl text-sm font-medium transition flex items-center gap-2"
                  >
                    ↩ Reply with Nexus
                  </button>
                  <span className="text-xs text-slate-500">
                    Drafted replies require human confirmation before sending.
                  </span>
                </div>
              </div>
            ) : (
              <div className="text-center py-20 text-slate-500 text-sm">
                Select an email from the inbox list to read details.
              </div>
            )}
          </div>
        </div>
      )}

      {/* Compose Tab */}
      {activeTab === 'compose' && (
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl max-w-3xl mx-auto space-y-6">
          <div className="border-b border-slate-800 pb-3 flex items-center justify-between">
            <div>
              <h3 className="text-lg font-bold text-white">Compose Email Message</h3>
              <p className="text-xs text-slate-400">
                Prepare drafts or dispatch emails with deterministic approval safeguards.
              </p>
            </div>
            <div className="text-xs bg-amber-500/10 text-amber-400 border border-amber-500/30 px-3 py-1 rounded-lg">
              🛡 Policy Protected
            </div>
          </div>

          <form onSubmit={handleSaveDraft} className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1">Recipient</label>
              <input
                type="email"
                placeholder="recipient@example.com"
                value={recipient}
                onChange={(e) => setRecipient(e.target.value)}
                required
                className="w-full bg-slate-800/80 border border-slate-700 rounded-xl px-4 py-2.5 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-rose-500"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1">Subject</label>
              <input
                type="text"
                placeholder="Discussion notes / Proposal reply"
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                required
                className="w-full bg-slate-800/80 border border-slate-700 rounded-xl px-4 py-2.5 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-rose-500"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1">Email Body</label>
              <textarea
                rows={8}
                placeholder="Write your email message here..."
                value={body}
                onChange={(e) => setBody(e.target.value)}
                required
                className="w-full bg-slate-800/80 border border-slate-700 rounded-xl px-4 py-3 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-rose-500 font-sans"
              />
            </div>

            <div className="bg-slate-950/60 p-4 rounded-xl border border-slate-800 text-xs text-slate-400 flex items-start gap-3">
              <span className="text-amber-400 text-base">ℹ</span>
              <div>
                <strong className="text-slate-300">Approval Policy:</strong> Sending emails is
                classified as an external sensitive action. Clicking &quot;Send Email&quot; invokes the
                human-in-the-loop approval confirmation dialog before message transmission.
              </div>
            </div>

            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                type="submit"
                className="px-5 py-2.5 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-xl text-sm font-medium transition"
              >
                💾 Save as Draft
              </button>
              <button
                type="button"
                onClick={() => handleDirectSend()}
                className="px-5 py-2.5 bg-rose-600 hover:bg-rose-500 text-white rounded-xl text-sm font-semibold transition shadow-md flex items-center gap-2"
              >
                🚀 Send Email (Approval Gate)
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Drafts & Outbox Tab */}
      {activeTab === 'drafts' && (
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <div>
              <h3 className="text-lg font-bold text-white">Drafts & Sent Dispatches</h3>
              <p className="text-xs text-slate-400">All prepared and sent email records.</p>
            </div>
            <button
              onClick={loadDrafts}
              className="text-xs text-slate-400 hover:text-white px-3 py-1.5 rounded-lg border border-slate-800 bg-slate-800/40"
            >
              🔄 Refresh
            </button>
          </div>

          {drafts.length === 0 ? (
            <div className="text-center py-12 text-slate-500 text-sm">
              No drafts or sent records found.
            </div>
          ) : (
            <div className="divide-y divide-slate-800">
              {drafts.map((d) => (
                <div key={d.id} className="py-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span
                        className={`text-xs px-2 py-0.5 rounded font-mono uppercase font-semibold ${
                          d.status === 'sent'
                            ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30'
                            : 'bg-amber-500/10 text-amber-400 border border-amber-500/30'
                        }`}
                      >
                        {d.status}
                      </span>
                      <span className="text-sm font-bold text-slate-200">{d.subject}</span>
                    </div>
                    <div className="text-xs text-slate-400">
                      To: <span className="text-slate-300">{d.recipient}</span> • Created:{' '}
                      {new Date(d.created_at).toLocaleString()}
                      {d.sent_at && (
                        <span> • Sent: {new Date(d.sent_at).toLocaleString()}</span>
                      )}
                    </div>
                    <p className="text-xs text-slate-400 line-clamp-2 max-w-2xl bg-black/20 p-2 rounded border border-slate-800/60 font-mono mt-1">
                      {d.body}
                    </p>
                  </div>

                  {d.status === 'draft' && (
                    <button
                      onClick={() => handleDirectSend(d.id)}
                      className="px-4 py-2 bg-rose-600/90 hover:bg-rose-500 text-white rounded-xl text-xs font-semibold transition shrink-0"
                    >
                      Approve & Send
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

