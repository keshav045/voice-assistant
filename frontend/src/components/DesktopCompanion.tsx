import React, { useState, useEffect } from 'react';
import {
  fetchDesktopStatus,
  executeDesktopCommand,
  type DesktopStatusDto,
} from '../services/api';

export const DesktopCompanion: React.FC = () => {
  const [status, setStatus] = useState<DesktopStatusDto | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [activeWindow, setActiveWindow] = useState<string | null>(null);
  const [systemMetrics, setSystemMetrics] = useState<any | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [fileResults, setFileResults] = useState<any[]>([]);
  const [latestScreenshot, setLatestScreenshot] = useState<{ path: string; fileName: string; thumbnail?: string; time: string } | null>(null);
  const [commandLogs, setCommandLogs] = useState<Array<{ time: string; action: string; message: string; success: boolean }>>([]);
  const [notification, setNotification] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  useEffect(() => {
    loadStatus();
    const interval = setInterval(loadStatus, 5000);
    return () => clearInterval(interval);
  }, []);

  const showNotification = (type: 'success' | 'error', text: string) => {
    setNotification({ type, text });
    setTimeout(() => setNotification(null), 4500);
  };

  const addLog = (action: string, message: string, success: boolean) => {
    const time = new Date().toLocaleTimeString();
    setCommandLogs((prev) => [{ time, action, message, success }, ...prev.slice(0, 19)]);
  };

  const loadStatus = async () => {
    try {
      const data = await fetchDesktopStatus();
      setStatus(data);
    } catch (err: any) {
      console.error('Failed to fetch companion status:', err);
    }
  };

  const handleInspectActiveWindow = async () => {
    setActionLoading('window');
    try {
      const res = await executeDesktopCommand({ action: 'get_active_window' });
      if (res.success) {
        setActiveWindow(res.window_title || res.title || 'Foreground Desktop');
        addLog('get_active_window', `Active: ${res.window_title || res.title}`, true);
        showNotification('success', 'Active foreground window inspected.');
      } else {
        showNotification('error', res.error || 'Failed to inspect window');
        addLog('get_active_window', res.error || 'Failed', false);
      }
    } catch (err: any) {
      showNotification('error', err.message);
    } finally {
      setActionLoading(null);
    }
  };

  const handleInspectMetrics = async () => {
    setActionLoading('metrics');
    try {
      const res = await executeDesktopCommand({ action: 'get_system_metrics' });
      if (res.success) {
        setSystemMetrics(res);
        addLog('get_system_metrics', 'Retrieved host telemetry', true);
        showNotification('success', 'Host system metrics refreshed.');
      }
    } catch (err: any) {
      showNotification('error', err.message);
    } finally {
      setActionLoading(null);
    }
  };

  const handleTakeScreenshot = async () => {
    setActionLoading('screenshot');
    try {
      const res = await executeDesktopCommand({ action: 'take_screenshot' });
      if (res.success) {
        setLatestScreenshot({
          path: res.file_path || res.path || '',
          fileName: res.file_name || 'screenshot.png',
          thumbnail: res.thumbnail_base64,
          time: new Date().toLocaleTimeString(),
        });
        addLog('take_screenshot', `Captured ${res.file_name || 'screen'}`, true);
        showNotification('success', 'Desktop screenshot captured successfully.');
      } else {
        showNotification('error', res.error || 'Failed to capture screenshot');
        addLog('take_screenshot', res.error || 'Failed', false);
      }
    } catch (err: any) {
      showNotification('error', err.message);
    } finally {
      setActionLoading(null);
    }
  };

  const handleLaunchApp = async (appName: string) => {
    const confirmed = window.confirm(
      `APPROVAL GATE: LAUNCH APPLICATION\n\nAre you sure you want to launch the desktop application "${appName}"?`
    );
    if (!confirmed) return;

    setActionLoading(appName);
    try {
      const res = await executeDesktopCommand({
        action: 'open_application',
        params: { app_name: appName },
        approval_granted: true,
      });

      if (res.success) {
        showNotification('success', res.message);
        addLog('open_application', res.message, true);
      } else {
        showNotification('error', res.error || 'Command rejected');
        addLog('open_application', res.error || 'Blocked', false);
      }
    } catch (err: any) {
      showNotification('error', err.message);
      addLog('open_application', err.message, false);
    } finally {
      setActionLoading(null);
    }
  };

  const handleSearchFiles = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchQuery) return;
    setActionLoading('search');
    try {
      const res = await executeDesktopCommand({
        action: 'search_files',
        params: { query: searchQuery },
      });
      if (res.success) {
        setFileResults(res.matches || []);
        addLog('search_files', `Found ${res.count || (res.matches ? res.matches.length : 0)} files for '${searchQuery}'`, true);
      } else {
        showNotification('error', res.error || 'File search failed');
      }
    } catch (err: any) {
      showNotification('error', err.message);
    } finally {
      setActionLoading(null);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header and Connection Status Bar */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-slate-900 border border-slate-800 p-5 rounded-2xl shadow-lg">
        <div>
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center text-cyan-400 font-bold">
              💻
            </div>
            <div>
              <h2 className="text-xl font-bold text-white tracking-tight flex items-center gap-2">
                Windows Desktop Companion
                <span className="text-xs bg-cyan-500/20 text-cyan-400 border border-cyan-500/30 px-2 py-0.5 rounded-full font-mono">
                  Phase 7
                </span>
              </h2>
              <p className="text-sm text-slate-400">
                Outbound secure WebSocket daemon executing allowlisted desktop automations with approval gates.
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div
            className={`px-3 py-1.5 rounded-xl border text-xs font-mono font-semibold flex items-center gap-2 ${
              status?.is_connected
                ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                : 'bg-amber-500/10 text-amber-400 border-amber-500/30'
            }`}
          >
            <span
              className={`w-2 h-2 rounded-full ${
                status?.is_connected ? 'bg-emerald-400 animate-pulse' : 'bg-amber-400'
              }`}
            />
            {status?.is_connected ? 'COMPANION CONNECTED' : 'DAEMON STANDBY (SIMULATION READY)'}
          </div>
          <button
            onClick={loadStatus}
            className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-xl text-xs font-medium transition"
          >
            🔄 Refresh
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

      {/* Companion Telemetry Banner */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl">
          <span className="text-xs text-slate-400 block mb-1">Target Host / OS</span>
          <div className="text-sm font-bold text-slate-200 truncate">
            {status?.hostname || 'WINDOWS-HOST'} • {status?.os || 'Windows 11'}
          </div>
          {systemMetrics?.cpu_count && (
            <div className="text-[11px] text-cyan-400 font-mono mt-1">
              Cores: {systemMetrics.cpu_count} • Telemetry Active
            </div>
          )}
        </div>
        <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl">
          <span className="text-xs text-slate-400 block mb-1">Active Foreground Window</span>
          <div className="text-sm font-mono text-cyan-300 truncate">
            {activeWindow || 'Click Inspect to read active window'}
          </div>
        </div>
        <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl">
          <span className="text-xs text-slate-400 block mb-1">Security Model</span>
          <div className="text-xs font-semibold text-emerald-400 flex items-center gap-1.5">
            <span>🛡</span> Strict Allowlist • Zero Shell Exec • Approval Gated
          </div>
        </div>
      </div>


      {/* Quick Launch & Host Inspection Row */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Approved App Launcher */}
        <div className="lg:col-span-7 bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <div>
              <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
                <span>🚀</span> Approved Application Launcher
              </h3>
              <p className="text-xs text-slate-400">
                Safe pre-validated executables launched with strict parameters without arbitrary shell invocation.
              </p>
            </div>
            <span className="text-[11px] font-mono bg-blue-500/10 text-blue-400 border border-blue-500/30 px-2 py-0.5 rounded">
              Requires Approval
            </span>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            {[
              { id: 'notepad', name: 'Notepad', icon: '📝', exe: 'notepad.exe' },
              { id: 'calculator', name: 'Calculator', icon: '🧮', exe: 'calc.exe' },
              { id: 'browser', name: 'Edge Browser', icon: '🌐', exe: 'msedge.exe' },
              { id: 'explorer', name: 'File Explorer', icon: '📁', exe: 'explorer.exe' },
              { id: 'terminal', name: 'Windows Terminal', icon: '💻', exe: 'wt.exe' },
              { id: 'code', name: 'VS Code', icon: '⚡', exe: 'code.cmd' },
            ].map((app) => (
              <button
                key={app.id}
                onClick={() => handleLaunchApp(app.id)}
                disabled={actionLoading === app.id}
                className="p-3.5 rounded-xl bg-slate-950/60 border border-slate-800 hover:border-cyan-500/40 hover:bg-slate-800/40 transition flex flex-col items-center justify-center text-center gap-1.5 group disabled:opacity-50"
              >
                <span className="text-2xl group-hover:scale-110 transition">{app.icon}</span>
                <span className="text-xs font-semibold text-slate-200">{app.name}</span>
                <span className="text-[10px] text-slate-500 font-mono">{app.exe}</span>
              </button>
            ))}
          </div>

          {/* Quick Reader Actions */}
          <div className="pt-2 border-t border-slate-800 flex flex-wrap gap-2">
            <button
              onClick={handleInspectActiveWindow}
              disabled={actionLoading === 'window'}
              className="flex-1 min-w-[120px] py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-xl text-xs font-semibold transition"
            >
              {actionLoading === 'window' ? 'Reading...' : '🔍 Inspect Window'}
            </button>
            <button
              onClick={handleInspectMetrics}
              disabled={actionLoading === 'metrics'}
              className="flex-1 min-w-[120px] py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-xl text-xs font-semibold transition"
            >
              {actionLoading === 'metrics' ? 'Querying...' : '📊 Telemetry'}
            </button>
            <button
              onClick={handleTakeScreenshot}
              disabled={actionLoading === 'screenshot'}
              className="flex-1 min-w-[120px] py-2 bg-cyan-600/30 hover:bg-cyan-600/40 border border-cyan-500/40 text-cyan-300 rounded-xl text-xs font-semibold transition"
            >
              {actionLoading === 'screenshot' ? 'Capturing...' : '📸 Screenshot'}
            </button>
          </div>

          {/* Screenshot Preview Card if taken */}
          {latestScreenshot && (
            <div className="p-3 bg-slate-950/80 border border-cyan-500/30 rounded-xl mt-3 flex items-center gap-4">
              {latestScreenshot.thumbnail ? (
                <img
                  src={`data:image/jpeg;base64,${latestScreenshot.thumbnail}`}
                  alt="Desktop Preview"
                  className="w-24 h-14 object-cover rounded-lg border border-slate-700 shadow"
                />
              ) : (
                <div className="w-24 h-14 bg-slate-800 rounded-lg flex items-center justify-center text-xs text-slate-400">
                  📸 PNG
                </div>
              )}
              <div className="overflow-hidden">
                <div className="text-xs font-semibold text-white truncate">{latestScreenshot.fileName}</div>
                <div className="text-[11px] text-slate-400 font-mono truncate" title={latestScreenshot.path}>
                  {latestScreenshot.path}
                </div>
                <div className="text-[10px] text-cyan-400 mt-0.5">Captured at {latestScreenshot.time}</div>
              </div>
            </div>
          )}
        </div>

        {/* Safe File Search Widget */}
        <div className="lg:col-span-5 bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-4 flex flex-col justify-between">
          <div className="space-y-3">
            <div className="border-b border-slate-800 pb-3">
              <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
                <span>🔎</span> Safe Scoped File Search
              </h3>
              <p className="text-xs text-slate-400">
                Search local workspace or documents folder for matching documents.
              </p>
            </div>

            <form onSubmit={handleSearchFiles} className="flex gap-2">
              <input
                type="text"
                placeholder="Search file name (e.g. plan, pdf, test)..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="flex-1 bg-slate-800/80 border border-slate-700 rounded-xl px-3 py-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-cyan-500"
              />
              <button
                type="submit"
                disabled={actionLoading === 'search'}
                className="px-4 py-2 bg-cyan-600 hover:bg-cyan-500 text-white rounded-xl text-xs font-bold transition"
              >
                Search
              </button>
            </form>

            <div className="space-y-1.5 max-h-[160px] overflow-y-auto pr-1">
              {fileResults.length === 0 ? (
                <div className="text-xs text-slate-500 py-6 text-center">
                  Enter a keyword to search safe workspace files.
                </div>
              ) : (
                fileResults.map((f, i) => (
                  <div
                    key={i}
                    className="p-2 rounded-lg bg-slate-800/40 border border-slate-800 flex items-center justify-between text-xs"
                  >
                    <span className="font-mono text-slate-200 truncate max-w-[200px]">{f.name}</span>
                    <span className="text-[10px] text-slate-500 font-mono">
                      {f.size_kb ? `${f.size_kb} KB` : `${Math.round((f.size_bytes || 0) / 1024)} KB`}
                    </span>
                  </div>
                ))
              )}
            </div>
          </div>

          <div className="text-[11px] text-slate-500 bg-black/20 p-2.5 rounded-xl border border-slate-800/60 font-mono">
            Daemon command: <code className="text-cyan-400">python desktop-companion/main.py</code>
          </div>
        </div>
      </div>

      {/* Command Telemetry Log Terminal */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-3">
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
            <span>📟</span> Live Action Telemetry & Policy Audit Log
          </h3>
          <span className="text-xs text-slate-400 font-mono">
            {commandLogs.length} events logged
          </span>
        </div>

        <div className="bg-black/40 border border-slate-800 rounded-xl p-4 font-mono text-xs max-h-48 overflow-y-auto space-y-1.5">
          {commandLogs.length === 0 ? (
            <div className="text-slate-500 italic">No desktop commands dispatched in this session.</div>
          ) : (
            commandLogs.map((log, idx) => (
              <div key={idx} className="flex items-start gap-2">
                <span className="text-slate-500">[{log.time}]</span>
                <span
                  className={log.success ? 'text-emerald-400' : 'text-rose-400'}
                >
                  {log.action}:
                </span>
                <span className="text-slate-300">{log.message}</span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
};
