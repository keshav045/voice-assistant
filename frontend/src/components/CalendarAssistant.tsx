import React, { useState, useEffect } from 'react';
import {
  fetchCalendarEvents,
  createCalendarEvent,
  checkCalendarAvailability,
  fetchFreeSlots,
  deleteCalendarEvent,
  fetchGoogleAuthUrl,
  fetchGoogleAuthStatus,
  disconnectGoogleAuth,
  type CalendarEventDto,
  type AvailabilityDto,
  type FreeSlotDto,
  type GoogleAuthStatusDto,
} from '../services/api';

export const CalendarAssistant: React.FC = () => {
  const [events, setEvents] = useState<CalendarEventDto[]>([]);
  const [freeSlots, setFreeSlots] = useState<FreeSlotDto[]>([]);
  const [loading, setLoading] = useState(false);
  const [notification, setNotification] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [googleStatus, setGoogleStatus] = useState<GoogleAuthStatusDto | null>(null);

  // Availability checker state
  const [checkStart, setCheckStart] = useState(() => {
    const d = new Date();
    d.setHours(d.getHours() + 1, 0, 0, 0);
    return d.toISOString().slice(0, 16);
  });
  const [checkEnd, setCheckEnd] = useState(() => {
    const d = new Date();
    d.setHours(d.getHours() + 2, 0, 0, 0);
    return d.toISOString().slice(0, 16);
  });
  const [availabilityResult, setAvailabilityResult] = useState<AvailabilityDto | null>(null);
  const [checkingAvailability, setCheckingAvailability] = useState(false);

  // New Event Form State
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  const [newStart, setNewStart] = useState(() => {
    const d = new Date();
    d.setDate(d.getDate() + 1);
    d.setHours(14, 0, 0, 0);
    return d.toISOString().slice(0, 16);
  });
  const [newEnd, setNewEnd] = useState(() => {
    const d = new Date();
    d.setDate(d.getDate() + 1);
    d.setHours(15, 0, 0, 0);
    return d.toISOString().slice(0, 16);
  });
  const [newLocation, setNewLocation] = useState('Google Meet');
  const [newDescription, setNewDescription] = useState('');
  const [newAttendees, setNewAttendees] = useState('keshav@nexus.ai');

  useEffect(() => {
    loadEvents();
    loadFreeSlots();
    checkGoogleStatus();

    const handleMessage = (event: MessageEvent) => {
      if (event.data?.type === 'GOOGLE_CONNECTED') {
        showNotification('success', `Google Calendar connected (${event.data.email})!`);
        checkGoogleStatus();
        loadEvents();
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
    if (!window.confirm('Disconnect Google Calendar? Nexus will fall back to local offline mode.')) return;
    try {
      await disconnectGoogleAuth();
      showNotification('success', 'Google Workspace disconnected.');
      await checkGoogleStatus();
      await loadEvents();
    } catch (err: any) {
      showNotification('error', err.message || 'Disconnect failed');
    }
  };

  const showNotification = (type: 'success' | 'error', text: string) => {
    setNotification({ type, text });
    setTimeout(() => setNotification(null), 4500);
  };

  const loadEvents = async () => {
    setLoading(true);
    try {
      const data = await fetchCalendarEvents();
      setEvents(data);
    } catch (err: any) {
      showNotification('error', err.message || 'Failed to load calendar events');
    } finally {
      setLoading(false);
    }
  };

  const loadFreeSlots = async () => {
    try {
      const today = new Date().toISOString();
      const slots = await fetchFreeSlots(today, 30);
      setFreeSlots(slots);
    } catch (err: any) {
      console.error('Failed to load free slots:', err);
    }
  };

  const handleCheckAvailability = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    setCheckingAvailability(true);
    setAvailabilityResult(null);
    try {
      const startIso = new Date(checkStart).toISOString();
      const endIso = new Date(checkEnd).toISOString();
      const res = await checkCalendarAvailability(startIso, endIso);
      setAvailabilityResult(res);
    } catch (err: any) {
      showNotification('error', err.message || 'Failed to check availability');
    } finally {
      setCheckingAvailability(false);
    }
  };

  const handleCreateEvent = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle || !newStart || !newEnd) {
      showNotification('error', 'Title, start time, and end time are required.');
      return;
    }

    const startIso = new Date(newStart).toISOString();
    const endIso = new Date(newEnd).toISOString();

    const confirmed = window.confirm(
      `APPROVAL GATE: CONFIRM SCHEDULE\n\nTitle: ${newTitle}\nWhen: ${new Date(newStart).toLocaleString()} - ${new Date(newEnd).toLocaleTimeString()}\nLocation: ${newLocation}\n\nProceed with scheduling?`
    );
    if (!confirmed) return;

    try {
      const attendeesList = newAttendees
        .split(',')
        .map((a) => a.trim())
        .filter(Boolean);

      const created = await createCalendarEvent({
        title: newTitle,
        start_time: startIso,
        end_time: endIso,
        location: newLocation,
        description: newDescription,
        attendees: attendeesList,
      });

      showNotification('success', `Event "${created.title}" scheduled successfully.`);
      setShowCreateModal(false);
      setNewTitle('');
      setNewDescription('');
      await loadEvents();
      await loadFreeSlots();
    } catch (err: any) {
      showNotification('error', err.message || 'Failed to create event');
    }
  };

  const handleDeleteEvent = async (id: string, title: string) => {
    const confirmed = window.confirm(
      `APPROVAL GATE: CANCEL EVENT\n\nAre you sure you want to cancel the event "${title}"?`
    );
    if (!confirmed) return;

    try {
      await deleteCalendarEvent(id);
      showNotification('success', `Event "${title}" cancelled.`);
      await loadEvents();
      await loadFreeSlots();
    } catch (err: any) {
      showNotification('error', err.message || 'Failed to cancel event');
    }
  };

  return (
    <div className="space-y-6">
      {/* Header and Control Bar */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-slate-900 border border-slate-800 p-5 rounded-2xl shadow-lg">
        <div>
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-blue-500/10 border border-blue-500/30 flex items-center justify-center text-blue-400 font-bold">
              📅
            </div>
            <div>
              <h2 className="text-xl font-bold text-white tracking-tight flex items-center gap-2">
                Google Calendar & Scheduling
                <span className="text-xs bg-blue-500/20 text-blue-400 border border-blue-500/30 px-2 py-0.5 rounded-full font-mono">
                  Phase 6
                </span>
              </h2>
              <p className="text-sm text-slate-400">
                Agenda inspection, slot availability verification, conflict avoidance, and approval-gated scheduling.
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {googleStatus?.connected ? (
            <div className="px-3 py-1.5 rounded-xl border text-xs font-medium flex items-center gap-2 bg-emerald-500/10 text-emerald-400 border-emerald-500/30">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
              <span>Calendar Live ({googleStatus.email})</span>
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
              title="Connect Google account for live Calendar sync"
            >
              <span>🌐</span> Connect Google
            </button>
          )}

          <button
            onClick={() => loadEvents()}
            disabled={loading}
            className="px-3.5 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-xl text-sm font-medium transition flex items-center gap-1.5"
          >
            🔄 Refresh
          </button>
          <button
            onClick={() => setShowCreateModal(true)}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-xl text-sm font-semibold transition shadow-md flex items-center gap-1.5"
          >
            ➕ Schedule Event
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

      {/* Availability Checker & Free Slots Row */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Availability Checker Panel */}
        <div className="lg:col-span-7 bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <div>
              <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
                <span>🔍</span> Instant Availability & Conflict Inspector
              </h3>
              <p className="text-xs text-slate-400">
                Verify whether a requested window overlaps with existing commitments.
              </p>
            </div>
          </div>

          <form onSubmit={handleCheckAvailability} className="grid grid-cols-1 md:grid-cols-12 gap-3 items-end">
            <div className="md:col-span-5">
              <label className="block text-xs font-medium text-slate-400 mb-1">Proposed Start</label>
              <input
                type="datetime-local"
                value={checkStart}
                onChange={(e) => setCheckStart(e.target.value)}
                required
                className="w-full bg-slate-800/80 border border-slate-700 rounded-xl px-3 py-2 text-xs text-slate-100 focus:outline-none focus:border-blue-500"
              />
            </div>
            <div className="md:col-span-5">
              <label className="block text-xs font-medium text-slate-400 mb-1">Proposed End</label>
              <input
                type="datetime-local"
                value={checkEnd}
                onChange={(e) => setCheckEnd(e.target.value)}
                required
                className="w-full bg-slate-800/80 border border-slate-700 rounded-xl px-3 py-2 text-xs text-slate-100 focus:outline-none focus:border-blue-500"
              />
            </div>
            <div className="md:col-span-2">
              <button
                type="submit"
                disabled={checkingAvailability}
                className="w-full py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-xl text-xs font-semibold transition disabled:opacity-50"
              >
                {checkingAvailability ? 'Checking...' : 'Check Slot'}
              </button>
            </div>
          </form>

          {availabilityResult && (
            <div
              className={`p-4 rounded-xl border text-xs space-y-2 ${
                availabilityResult.is_free
                  ? 'bg-emerald-950/40 border-emerald-800/60 text-emerald-200'
                  : 'bg-rose-950/40 border-rose-800/60 text-rose-200'
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="font-bold flex items-center gap-1.5">
                  {availabilityResult.is_free ? '✓ SLOT AVAILABLE' : '⚠ CONFLICT DETECTED'}
                </span>
                <span className="text-[11px] font-mono opacity-80">
                  {availabilityResult.conflict_count} conflict(s)
                </span>
              </div>
              <p className="leading-relaxed">{availabilityResult.message}</p>
              {availabilityResult.conflicts.length > 0 && (
                <div className="space-y-1 pt-1 border-t border-rose-800/40">
                  {availabilityResult.conflicts.map((c) => (
                    <div key={c.id} className="text-[11px] text-rose-300 font-mono">
                      • {c.title} ({new Date(c.start_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} -{' '}
                      {new Date(c.end_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })})
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Free Open Slots Strip */}
        <div className="lg:col-span-5 bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-3">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <div>
              <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
                <span>⏱</span> Open Availability Gaps
              </h3>
              <p className="text-xs text-slate-400">Available free windows during workday (9am-6pm).</p>
            </div>
          </div>

          <div className="space-y-2 max-h-[170px] overflow-y-auto pr-1">
            {freeSlots.length === 0 ? (
              <div className="text-xs text-slate-500 py-6 text-center">
                No free slots remaining or schedule full.
              </div>
            ) : (
              freeSlots.map((slot, idx) => (
                <div
                  key={idx}
                  className="p-2.5 rounded-xl bg-slate-800/50 border border-slate-700/60 flex items-center justify-between text-xs"
                >
                  <span className="font-mono text-emerald-400 font-semibold">{slot.display}</span>
                  <button
                    onClick={() => {
                      setNewStart(slot.start_time.slice(0, 16));
                      setNewEnd(slot.end_time.slice(0, 16));
                      setShowCreateModal(true);
                    }}
                    className="text-[11px] px-2 py-0.5 rounded bg-blue-600/30 text-blue-300 hover:bg-blue-600/60 border border-blue-500/30 transition"
                  >
                    Book Slot
                  </button>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Events Agenda List */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-4">
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <div>
            <h3 className="text-lg font-bold text-white flex items-center gap-2">
              Upcoming Scheduled Meetings & Events
              <span className="text-xs bg-slate-800 text-slate-400 px-2 py-0.5 rounded-full font-mono border border-slate-700">
                {events.length}
              </span>
            </h3>
            <p className="text-xs text-slate-400">
              Meetings synced with local engine and Google Calendar workspace.
            </p>
          </div>
        </div>

        {events.length === 0 ? (
          <div className="text-center py-16 text-slate-500 text-sm">
            No upcoming events scheduled. Click &quot;Schedule Event&quot; to add one.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {events.map((evt) => {
              const startDate = new Date(evt.start_time);
              const endDate = new Date(evt.end_time);
              return (
                <div
                  key={evt.id}
                  className="bg-slate-950/60 border border-slate-800 rounded-xl p-4 flex flex-col justify-between hover:border-blue-500/40 transition space-y-3"
                >
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-blue-400 font-mono font-semibold">
                        {startDate.toLocaleDateString([], { month: 'short', day: 'numeric' })}
                      </span>
                      <span
                        className={`text-[10px] uppercase font-mono px-1.5 py-0.5 rounded border ${
                          evt.status === 'confirmed'
                            ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                            : 'bg-amber-500/10 text-amber-400 border-amber-500/30'
                        }`}
                      >
                        {evt.status}
                      </span>
                    </div>

                    <h4 className="text-sm font-bold text-white">{evt.title}</h4>

                    <div className="text-xs text-slate-400 font-mono">
                      {startDate.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} -{' '}
                      {endDate.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </div>

                    {evt.location && (
                      <div className="text-xs text-slate-300 flex items-center gap-1 truncate">
                        <span className="text-slate-500">📍</span> {evt.location}
                      </div>
                    )}

                    {evt.description && (
                      <p className="text-xs text-slate-400 line-clamp-2 leading-relaxed">
                        {evt.description}
                      </p>
                    )}

                    {evt.attendees && evt.attendees.length > 0 && (
                      <div className="flex flex-wrap gap-1 pt-1">
                        {evt.attendees.map((att, i) => (
                          <span
                            key={i}
                            className="text-[10px] bg-slate-800 text-slate-400 px-1.5 py-0.5 rounded border border-slate-700"
                          >
                            {att}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>

                  <div className="pt-2 border-t border-slate-800/80 flex items-center justify-end">
                    <button
                      onClick={() => handleDeleteEvent(evt.id, evt.title)}
                      className="text-xs text-rose-400 hover:text-rose-300 transition"
                    >
                      Cancel Event
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Schedule Event Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-lg w-full p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div>
                <h3 className="text-lg font-bold text-white">Schedule Calendar Event</h3>
                <p className="text-xs text-slate-400">
                  Adds appointment with deterministic approval safeguard.
                </p>
              </div>
              <button
                onClick={() => setShowCreateModal(false)}
                className="text-slate-400 hover:text-white text-sm"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleCreateEvent} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1">Event Title</label>
                <input
                  type="text"
                  placeholder="e.g. Technical Architecture Review"
                  value={newTitle}
                  onChange={(e) => setNewTitle(e.target.value)}
                  required
                  className="w-full bg-slate-800/80 border border-slate-700 rounded-xl px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-blue-500"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-slate-400 mb-1">Start Time</label>
                  <input
                    type="datetime-local"
                    value={newStart}
                    onChange={(e) => setNewStart(e.target.value)}
                    required
                    className="w-full bg-slate-800/80 border border-slate-700 rounded-xl px-3 py-2 text-xs text-slate-100 focus:outline-none focus:border-blue-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-400 mb-1">End Time</label>
                  <input
                    type="datetime-local"
                    value={newEnd}
                    onChange={(e) => setNewEnd(e.target.value)}
                    required
                    className="w-full bg-slate-800/80 border border-slate-700 rounded-xl px-3 py-2 text-xs text-slate-100 focus:outline-none focus:border-blue-500"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1">
                  Location / Conference Link
                </label>
                <input
                  type="text"
                  placeholder="https://meet.google.com/xyz or Room 301"
                  value={newLocation}
                  onChange={(e) => setNewLocation(e.target.value)}
                  className="w-full bg-slate-800/80 border border-slate-700 rounded-xl px-3 py-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-blue-500"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1">
                  Attendees (comma-separated emails)
                </label>
                <input
                  type="text"
                  placeholder="sarah@example.com, architect@nexus.ai"
                  value={newAttendees}
                  onChange={(e) => setNewAttendees(e.target.value)}
                  className="w-full bg-slate-800/80 border border-slate-700 rounded-xl px-3 py-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-blue-500"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1">Description / Notes</label>
                <textarea
                  rows={3}
                  placeholder="Meeting agenda items..."
                  value={newDescription}
                  onChange={(e) => setNewDescription(e.target.value)}
                  className="w-full bg-slate-800/80 border border-slate-700 rounded-xl px-3 py-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-blue-500"
                />
              </div>

              <div className="bg-amber-500/10 border border-amber-500/20 p-3 rounded-xl text-xs text-amber-300 flex items-start gap-2">
                <span>🛡</span>
                <span>
                  <strong>Approval Policy:</strong> Creating or modifying calendar appointments is an
                  external write operation. Confirming will create the event in the schedule.
                </span>
              </div>

              <div className="flex items-center justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-xl text-xs font-medium transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-5 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-xl text-xs font-bold transition shadow-md"
                >
                  Confirm & Schedule
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

