/**
 * Nexus Personal Voice Assistant - Web Client
 * Features:
 * - Persistent left sidebar with search history per user
 * - Bottom-left user login & signup profile controls
 * - Live cricket scores, web search, calculator, Python runner, and reasoning
 * - Voice Speech Recognition & Spoken TTS output
 */

let audioOutputEnabled = true;
let currentAuthTab = "login";
let authToken = localStorage.getItem("nexus_auth_token") || "";
let currentUser = null;
let currentSessionId = "web-" + Math.random().toString(36).substring(2, 9);
let mobileSidebarOpen = false;
let currentAudio = null;
let isSpeaking = false;

// --- Initialization ---
document.addEventListener("DOMContentLoaded", () => {
  checkLiveKitStatus();
  checkAuthStatus();
  loadHistory();
  checkGmailStatus();
});

// --- User Authentication ---
async function checkAuthStatus() {
  if (!authToken) {
    updateAuthUI(null);
    return;
  }
  try {
    const res = await fetch("/api/auth/me", {
      headers: { "Authorization": `Bearer ${authToken}` }
    });
    const data = await res.json();
    if (data.authenticated && data.user) {
      currentUser = data.user;
      updateAuthUI(currentUser);
    } else {
      localStorage.removeItem("nexus_auth_token");
      authToken = "";
      currentUser = null;
      updateAuthUI(null);
    }
  } catch (err) {
    console.warn("Could not verify auth:", err);
    updateAuthUI(null);
  }
}

function updateAuthUI(user) {
  const loggedOutCard = document.getElementById("sidebar-auth-logged-out");
  const loggedInCard = document.getElementById("sidebar-auth-logged-in");
  const displayName = document.getElementById("user-display-name");
  const avatarInitial = document.getElementById("user-avatar-initial");

  if (user) {
    if (loggedOutCard) loggedOutCard.classList.add("hidden");
    if (loggedInCard) loggedInCard.classList.remove("hidden");
    if (displayName) displayName.innerText = user.username;
    if (avatarInitial) avatarInitial.innerText = (user.username || "U")[0].toUpperCase();
  } else {
    if (loggedOutCard) loggedOutCard.classList.remove("hidden");
    if (loggedInCard) loggedInCard.classList.add("hidden");
  }
  checkGmailStatus();
}

function openAuthModal(tab = "login") {
  const modal = document.getElementById("auth-modal");
  if (!modal) return;
  modal.classList.remove("hidden");
  switchAuthTab(tab);
  hideAuthError();
  // Focus username input
  setTimeout(() => {
    const uInput = document.getElementById("auth-username");
    if (uInput) uInput.focus();
  }, 100);
}

function closeAuthModal() {
  const modal = document.getElementById("auth-modal");
  if (modal) modal.classList.add("hidden");
  hideAuthError();
}

function switchAuthTab(tab) {
  currentAuthTab = tab;
  const loginTab = document.getElementById("tab-login-btn");
  const signupTab = document.getElementById("tab-signup-btn");
  const title = document.getElementById("auth-modal-title");
  const submitBtn = document.getElementById("auth-submit-btn");
  const emailGroup = document.getElementById("email-field-group");

  hideAuthError();

  if (tab === "signup") {
    if (signupTab) signupTab.className = "flex-1 py-1.5 rounded-lg text-xs font-semibold transition-all bg-surface-container-lowest text-on-surface shadow-xs";
    if (loginTab) loginTab.className = "flex-1 py-1.5 rounded-lg text-xs font-semibold transition-all text-on-surface-variant hover:text-on-surface";
    if (title) title.innerText = "Create Nexus Account";
    if (submitBtn) submitBtn.innerText = "Create Account";
    if (emailGroup) emailGroup.classList.remove("hidden");
  } else {
    if (loginTab) loginTab.className = "flex-1 py-1.5 rounded-lg text-xs font-semibold transition-all bg-surface-container-lowest text-on-surface shadow-xs";
    if (signupTab) signupTab.className = "flex-1 py-1.5 rounded-lg text-xs font-semibold transition-all text-on-surface-variant hover:text-on-surface";
    if (title) title.innerText = "Sign In to Nexus";
    if (submitBtn) submitBtn.innerText = "Sign In";
    if (emailGroup) emailGroup.classList.add("hidden");
  }
}

function showAuthError(msg) {
  const errBox = document.getElementById("auth-error-box");
  if (errBox) {
    errBox.innerText = msg;
    errBox.classList.remove("hidden");
  }
}

function hideAuthError() {
  const errBox = document.getElementById("auth-error-box");
  if (errBox) errBox.classList.add("hidden");
}

async function handleAuthSubmit(event) {
  event.preventDefault();
  const username = document.getElementById("auth-username").value.trim();
  const password = document.getElementById("auth-password").value;
  const email = document.getElementById("auth-email").value.trim();

  const url = currentAuthTab === "signup" ? "/api/auth/signup" : "/api/auth/login";
  const payload = { username, password };
  if (currentAuthTab === "signup" && email) payload.email = email;

  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();

    if (!res.ok || !data.success) {
      showAuthError(data.detail || "Authentication failed. Please check your credentials.");
      return;
    }

    // Success
    authToken = data.token;
    currentUser = data.user;
    localStorage.setItem("nexus_auth_token", authToken);
    updateAuthUI(currentUser);
    closeAuthModal();

    // Reload search history for this newly signed-in user
    loadHistory();

  } catch (err) {
    showAuthError("Network error. Please try again.");
  }
}

async function logoutUser() {
  try {
    if (authToken) {
      await fetch("/api/auth/logout", {
        method: "POST",
        headers: { "Authorization": `Bearer ${authToken}` }
      });
    }
  } catch (e) {
    // Continue
  }
  authToken = "";
  currentUser = null;
  localStorage.removeItem("nexus_auth_token");
  updateAuthUI(null);
  loadHistory();
}

// --- History Management (Left Sidebar: Grouped by Conversation Session) ---
async function loadHistory() {
  try {
    const headers = {};
    if (authToken) headers["Authorization"] = `Bearer ${authToken}`;
    const res = await fetch("/api/history", { headers });
    const data = await res.json();
    if (data.success) {
      const sessions = data.sessions || [];
      renderHistory(sessions);
      updateHistoryCountBadge(sessions.length);
    }
  } catch (e) {
    console.warn("Could not load history:", e);
  }
}

function updateHistoryCountBadge(count) {
  const badge = document.getElementById("history-count-badge");
  if (!badge) return;
  badge.innerText = count > 99 ? "99+" : count;
}

function renderHistory(sessions) {
  const container = document.getElementById("history-items-container");
  if (!container) return;

  if (sessions.length === 0) {
    container.innerHTML = `
      <div class="flex flex-col items-center justify-center py-12 text-center text-on-surface-variant">
        <span class="material-symbols-outlined text-[36px] text-surface-container-high mb-2">history_toggle_off</span>
        <p class="text-xs font-semibold">No chat history yet</p>
        <p class="text-[11px] text-on-surface-variant/70 mt-1 max-w-[200px]">
          Ask questions or speak to see your conversations saved here.
        </p>
      </div>
    `;
    return;
  }

  container.innerHTML = sessions.map(session => {
    const timeAgo = formatTimeAgo(session.last_active);
    const isActive = session.session_id === currentSessionId;
    const msgCount = session.turn_count || 1;
    const countLabel = msgCount === 1 ? "1 message" : `${msgCount} messages`;

    const activeClasses = isActive
      ? "bg-primary/10 border-primary shadow-xs ring-1 ring-primary/20"
      : "bg-surface-container-low/70 hover:bg-surface-container-low border-surface-container hover:border-surface-container-high";

    return `
      <div class="group relative flex items-center justify-between p-2.5 rounded-xl border transition-all cursor-pointer ${activeClasses}" onclick="openChatSession('${session.session_id}')">
        <div class="flex items-start gap-2.5 min-w-0 flex-1 pr-1">
          <span class="material-symbols-outlined text-primary text-[18px] shrink-0 mt-0.5">chat_bubble_outline</span>
          <div class="flex flex-col min-w-0 flex-1">
            <span class="text-xs font-semibold text-on-surface truncate group-hover:text-primary transition-colors">
              ${escapeHtml(session.title)}
            </span>
            <div class="flex items-center gap-1.5 text-[10px] text-on-surface-variant/70 mt-0.5">
              <span>${countLabel}</span>
              <span>•</span>
              <span>${timeAgo}</span>
            </div>
          </div>
        </div>

        <button onclick="deleteChatSession('${session.session_id}', event)" class="opacity-0 group-hover:opacity-100 p-1 text-on-surface-variant hover:text-red-600 rounded-lg hover:bg-red-50 transition-all shrink-0" title="Delete conversation">
          <span class="material-symbols-outlined text-[15px]">delete</span>
        </button>
      </div>
    `;
  }).join("");
}

async function openChatSession(sessionId) {
  if (sessionId === currentSessionId && document.getElementById("chat-messages").children.length > 1) {
    // Already in this session
    if (window.innerWidth < 768 && mobileSidebarOpen) {
      toggleMobileSidebar();
    }
    return;
  }

  stopSpeaking();
  currentSessionId = sessionId;

  try {
    const headers = {};
    if (authToken) headers["Authorization"] = `Bearer ${authToken}`;
    const res = await fetch(`/api/history/${sessionId}`, { headers });
    const data = await res.json();

    const container = document.getElementById("chat-messages");
    if (container && data.success && data.turns) {
      container.innerHTML = "";
      if (data.turns.length === 0) {
        container.innerHTML = `
          <div class="flex items-start gap-3 max-w-[85%] self-start">
            <div class="w-8 h-8 rounded-full bg-primary flex items-center justify-center text-white text-xs font-bold shrink-0 mt-0.5 shadow-sm">
              AI
            </div>
            <div class="flex flex-col gap-1">
              <span class="text-[10px] text-on-surface-variant font-medium">Nexus Assistant</span>
              <div class="px-4 py-3 rounded-2xl rounded-tl-sm bg-surface-container-low text-on-surface text-sm leading-relaxed shadow-sm">
                Conversation loaded. Ask a question or use mic to continue!
              </div>
            </div>
          </div>
        `;
      } else {
        data.turns.forEach(turn => {
          appendUserBubble(turn.user_message);
          appendAssistantBubble(turn.spoken_reply, turn.tool_calls);
        });
      }
      container.scrollTop = container.scrollHeight;
    }
  } catch (err) {
    console.warn("Could not load session turns:", err);
  }

  loadHistory();

  if (window.innerWidth < 768 && mobileSidebarOpen) {
    toggleMobileSidebar();
  }
}

async function deleteChatSession(sessionId, event) {
  if (event) event.stopPropagation();
  if (!confirm("Are you sure you want to delete this conversation?")) return;

  try {
    const headers = {};
    if (authToken) headers["Authorization"] = `Bearer ${authToken}`;
    await fetch(`/api/history/${sessionId}`, { method: "DELETE", headers });

    if (sessionId === currentSessionId) {
      startNewChat();
    }
    loadHistory();
  } catch (e) {
    console.warn("Error deleting chat session:", e);
  }
}

async function clearHistory() {
  if (!confirm("Are you sure you want to clear all conversations?")) return;
  try {
    const headers = {};
    if (authToken) headers["Authorization"] = `Bearer ${authToken}`;
    await fetch("/api/history", { method: "DELETE", headers });
    startNewChat();
    loadHistory();
  } catch (e) {
    console.warn("Error clearing history:", e);
  }
}

function startNewChat() {
  stopSpeaking();
  currentSessionId = "web-" + Math.random().toString(36).substring(2, 9);
  const container = document.getElementById("chat-messages");
  if (container) {
    container.innerHTML = `
      <div class="flex items-start gap-3 max-w-[85%] self-start">
        <div class="w-8 h-8 rounded-full bg-primary flex items-center justify-center text-white text-xs font-bold shrink-0 mt-0.5 shadow-sm">
          AI
        </div>
        <div class="flex flex-col gap-1">
          <span class="text-[10px] text-on-surface-variant font-medium">Nexus Assistant</span>
          <div class="px-4 py-3 rounded-2xl rounded-tl-sm bg-surface-container-low text-on-surface text-sm leading-relaxed shadow-sm">
            Started a new chat session! You can type your request or click the mic button below to talk.
          </div>
        </div>
      </div>
    `;
  }
  const input = document.getElementById("chat-input");
  if (input) {
    input.value = "";
    input.focus();
  }
  loadHistory();
  if (window.innerWidth < 768 && mobileSidebarOpen) {
    toggleMobileSidebar();
  }
}

function toggleMobileSidebar() {
  const sidebar = document.getElementById("sidebar");
  const backdrop = document.getElementById("sidebar-backdrop");
  if (!sidebar) return;

  mobileSidebarOpen = !mobileSidebarOpen;
  if (mobileSidebarOpen) {
    sidebar.classList.remove("-translate-x-full");
    if (backdrop) backdrop.classList.remove("hidden");
  } else {
    sidebar.classList.add("-translate-x-full");
    if (backdrop) backdrop.classList.add("hidden");
  }
}

function quickFill(text) {
  const input = document.getElementById("chat-input");
  if (input) {
    input.value = text;
    input.focus();
  }
}

function formatTimeAgo(isoStr) {
  if (!isoStr) return "";
  try {
    const date = new Date(isoStr);
    const now = new Date();
    const diffSec = Math.floor((now - date) / 1000);
    if (diffSec < 60) return "Just now";
    if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
    if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
    return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  } catch (e) {
    return "";
  }
}

function escapeJs(str) {
  if (!str) return "";
  return String(str).replace(/'/g, "\\'").replace(/"/g, '\\"');
}

// --- LiveKit WebRTC Voice Controls ---
function toggleMicrophone() {
  toggleLiveKitConnection();
}

function updateMicUI(state) {
  // state: "idle" | "connecting" | "connected"
  const micBtn = document.getElementById("mic-btn");
  const micIcon = document.getElementById("mic-icon");
  const chatInput = document.getElementById("chat-input");

  if (!micBtn) return;

  if (state === "connected") {
    micBtn.className = "w-10 h-10 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white flex items-center justify-center transition-all shadow-md animate-pulse shrink-0";
    if (micIcon) {
      micIcon.innerText = "mic";
      micIcon.className = "material-symbols-outlined text-[20px] text-white";
    }
    micBtn.title = "Disconnect LiveKit Voice Stream";
    if (chatInput) chatInput.placeholder = "LiveKit Voice active... Speak now";
  } else if (state === "connecting") {
    micBtn.className = "w-10 h-10 rounded-xl bg-amber-500 text-white flex items-center justify-center transition-all shadow-md animate-spin shrink-0";
    if (micIcon) {
      micIcon.innerText = "sync";
      micIcon.className = "material-symbols-outlined text-[20px] text-white";
    }
    micBtn.title = "Connecting LiveKit...";
    if (chatInput) chatInput.placeholder = "Connecting LiveKit WebRTC...";
  } else {
    micBtn.className = "w-10 h-10 rounded-xl bg-surface-container-low hover:bg-surface-container text-on-surface flex items-center justify-center transition-all shrink-0 border border-surface-container/60";
    if (micIcon) {
      micIcon.innerText = "mic";
      micIcon.className = "material-symbols-outlined text-[20px] text-primary";
    }
    micBtn.title = "Connect LiveKit Voice Stream";
    if (chatInput) chatInput.placeholder = "Ask anything or speak with LiveKit...";
  }
}

// --- Audio Spoken Output Toggle ---
function toggleAudioOutput() {
  audioOutputEnabled = !audioOutputEnabled;
  if (!audioOutputEnabled) {
    stopSpeaking();
  }
  const label = document.getElementById("audio-toggle-label");
  const icon = document.getElementById("audio-toggle-icon");
  if (label) label.innerText = audioOutputEnabled ? "Voice: ON" : "Voice: OFF";
  if (icon) icon.innerText = audioOutputEnabled ? "volume_up" : "volume_off";
}

// --- Chat Input & Execution ---
function handleChatInput(event) {
  if (event.key === "Escape") {
    stopSpeaking();
    return;
  }
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    submitChatTurn();
  }
}

// Global Escape key listener to stop speaking immediately
window.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && isSpeaking) {
    stopSpeaking();
  }
});

// --- URL / Application Auto-Launcher ---
function triggerOpenUrl(url) {
  if (!url) return;
  let opened = false;
  try {
    const w = window.open(url, "_blank");
    if (w && !w.closed && typeof w.closed !== "undefined") {
      opened = true;
    }
  } catch (e) {
    opened = false;
  }
  // If the browser's popup blocker blocked the new tab, navigate directly so the app or website opens
  if (!opened) {
    window.location.href = url;
  }
}

async function submitChatTurn(textOverride) {
  stopSpeaking();
  const inputEl = document.getElementById("chat-input");
  const userText = (textOverride || (inputEl ? inputEl.value : "")).trim();
  if (!userText) return;

  if (inputEl) inputEl.value = "";

  appendUserBubble(userText);

  // Synchronously capture window handle during the user's keystroke/click event
  // This prevents Google Chrome and Microsoft Edge from blocking the tab as an unprompted popup
  let pendingWindow = null;
  const cleanLower = userText.toLowerCase().trim();
  const isOpenIntent = /(?:^|\b)(?:open|launch|start|play|goto|visit)\b/i.test(cleanLower) ||
                       /(?:youtube|whatsapp|linkedin|gmail|mail|spotify|github)/i.test(cleanLower);

  if (isOpenIntent) {
    try {
      pendingWindow = window.open("about:blank", "_blank");
    } catch (e) {
      pendingWindow = null;
    }
  }

  const thinkingId = appendThinkingBubble();

  try {
    const headers = { "Content-Type": "application/json" };
    if (authToken) headers["Authorization"] = `Bearer ${authToken}`;

    const resp = await fetch("/api/chat", {
      method: "POST",
      headers: headers,
      body: JSON.stringify({ message: userText, session_id: currentSessionId })
    });

    const data = await resp.json();
    removeMessage(thinkingId);

    // Check if tools yielded a URL to open
    let targetUrlToOpen = null;
    if (data.tool_calls_executed && data.tool_calls_executed.length > 0) {
      for (const tc of data.tool_calls_executed) {
        if ((tc.tool === "open_app" || tc.tool === "send_whatsapp_message") && tc.result && tc.result.url) {
          targetUrlToOpen = tc.result.url;
          break;
        }
      }
    }

    if (targetUrlToOpen) {
      if (pendingWindow && !pendingWindow.closed) {
        pendingWindow.location.href = targetUrlToOpen;
        pendingWindow = null;
      } else {
        triggerOpenUrl(targetUrlToOpen);
      }
    } else if (pendingWindow && !pendingWindow.closed) {
      pendingWindow.close();
      pendingWindow = null;
    }

    appendAssistantBubble(data.spoken_reply, data.tool_calls_executed);

    const latLabel = document.getElementById("turn-latency-label");
    if (latLabel && data.latency_ms) {
      latLabel.innerText = `Turn: ${data.latency_ms}ms • Model: GPT-4o`;
    }

    if (audioOutputEnabled && data.spoken_reply) {
      playSpokenAudio(data.spoken_reply);
    }

    // Refresh history in left sidebar
    loadHistory();

  } catch (err) {
    if (pendingWindow && !pendingWindow.closed) {
      pendingWindow.close();
      pendingWindow = null;
    }
    console.error("Chat turn error:", err);
    removeMessage(thinkingId);
    appendAssistantBubble("I encountered an error processing your request. Please try again.");
  }
}

// --- Spoken Audio Controls & Playback ---
function setSpeakingState(speaking) {
  isSpeaking = speaking;
  const stopPill = document.getElementById("stop-speaking-pill");
  if (stopPill) {
    if (speaking) {
      stopPill.classList.remove("hidden");
    } else {
      stopPill.classList.add("hidden");
    }
  }
}

function stopSpeaking() {
  if (currentAudio) {
    try {
      currentAudio.pause();
      currentAudio.currentTime = 0;
    } catch (e) {}
    currentAudio = null;
  }
  setSpeakingState(false);
}

async function playSpokenAudio(text) {
  if (!text || !audioOutputEnabled) return;

  stopSpeaking();

  // Try server TTS (OpenAI TTS endpoint)
  try {
    const res = await fetch("/api/tts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: text, voice: "alloy" })
    });
    const data = await res.json();
    if (data.success && data.audio_base64) {
      const audio = new Audio("data:audio/mp3;base64," + data.audio_base64);
      currentAudio = audio;

      audio.onplay = () => {
        setSpeakingState(true);
      };

      audio.onended = () => {
        if (currentAudio === audio) {
          currentAudio = null;
          setSpeakingState(false);
        }
      };

      audio.onerror = () => {
        if (currentAudio === audio) {
          currentAudio = null;
          setSpeakingState(false);
        }
      };

      audio.onpause = () => {
        if (currentAudio === audio && audio.ended) {
          setSpeakingState(false);
        }
      };

      setSpeakingState(true);
      await audio.play();
    }
  } catch (e) {
    console.warn("TTS playback error:", e);
    setSpeakingState(false);
  }
}

// --- DOM Chat Bubbles ---
function appendUserBubble(text) {
  const container = document.getElementById("chat-messages");
  if (!container) return;

  const bubble = document.createElement("div");
  bubble.className = "flex items-start gap-3 max-w-[85%] self-end flex-row-reverse";
  bubble.innerHTML = `
    <div class="w-8 h-8 rounded-full bg-surface-container flex items-center justify-center text-on-surface text-xs font-bold shrink-0 mt-0.5 border border-surface-container-high">
      You
    </div>
    <div class="flex flex-col gap-1 items-end">
      <span class="text-[10px] text-on-surface-variant font-medium">You</span>
      <div class="px-4 py-2.5 rounded-2xl rounded-tr-sm bg-primary text-white text-sm leading-relaxed shadow-sm">
        ${escapeHtml(text)}
      </div>
    </div>
  `;
  container.appendChild(bubble);
  container.scrollTop = container.scrollHeight;
}

function appendAssistantBubble(text, toolCalls) {
  const container = document.getElementById("chat-messages");
  if (!container) return;

  const bubble = document.createElement("div");
  bubble.className = "flex items-start gap-3 max-w-[85%] self-start";

  let toolBadgeHtml = "";
  if (toolCalls && toolCalls.length > 0) {
    const names = toolCalls.map(tc => {
      if (tc.tool === "send_whatsapp_message") {
        const cName = tc.result?.contact || (tc.args && tc.args.contact_name) || "Contact";
        return `WhatsApp: ${cName}`;
      }
      if (tc.tool === "open_app") {
        const tgt = tc.result?.target || (tc.args && tc.args.name) || "App";
        return `Launched: ${tgt}`;
      }
      if (tc.tool === "web_search") return "Live Cricket & Web Search";
      if (tc.tool === "calculator") return "Math Calculator";
      if (tc.tool === "run_python_code") return "Python Code Runner";
      if (tc.tool === "get_current_time") return "Current Time";
      return tc.tool;
    }).join(", ");
    toolBadgeHtml = `
      <div class="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-surface-container text-[11px] text-on-surface-variant font-medium mt-1 w-fit border border-surface-container-high">
        <span class="material-symbols-outlined text-[14px] text-primary">bolt</span>
        <span>Called: ${escapeHtml(names)}</span>
      </div>
    `;
  }

  let actionLinkHtml = "";
  if (toolCalls && toolCalls.length > 0) {
    for (const tc of toolCalls) {
      if ((tc.tool === "open_app" || tc.tool === "send_whatsapp_message") && tc.result && tc.result.url) {
        const label = tc.tool === "open_app" ? `Open ${(tc.result.target || "App")}` : "Open WhatsApp Chat";
        actionLinkHtml += `
          <a href="${escapeHtml(tc.result.url)}" target="_blank" rel="noopener noreferrer" class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary text-white text-xs font-semibold hover:bg-primary-container transition-all shadow-xs mt-1 w-fit">
            <span>${escapeHtml(label)}</span>
            <span class="material-symbols-outlined text-[14px]">open_in_new</span>
          </a>
        `;
        triggerOpenUrl(tc.result.url);
      }
    }
  }

  bubble.innerHTML = `
    <div class="w-8 h-8 rounded-full bg-primary flex items-center justify-center text-white text-xs font-bold shrink-0 mt-0.5 shadow-sm">
      AI
    </div>
    <div class="flex flex-col gap-1">
      <span class="text-[10px] text-on-surface-variant font-medium">Nexus Assistant</span>
      <div class="px-4 py-3 rounded-2xl rounded-tl-sm bg-surface-container-low text-on-surface text-sm leading-relaxed shadow-sm">
        ${escapeHtml(text)}
      </div>
      ${toolBadgeHtml}
      ${actionLinkHtml}
    </div>
  `;
  container.appendChild(bubble);
  container.scrollTop = container.scrollHeight;
}

function appendThinkingBubble() {
  const container = document.getElementById("chat-messages");
  if (!container) return null;

  const id = "thinking-" + Math.random().toString(36).substring(2, 7);
  const bubble = document.createElement("div");
  bubble.id = id;
  bubble.className = "flex items-start gap-3 max-w-[85%] self-start";
  bubble.innerHTML = `
    <div class="w-8 h-8 rounded-full bg-primary/20 flex items-center justify-center text-primary text-xs font-bold shrink-0 mt-0.5">
      AI
    </div>
    <div class="flex items-center gap-2 px-4 py-3 rounded-2xl rounded-tl-sm bg-surface-container-low text-on-surface-variant text-sm">
      <span class="w-2 h-2 rounded-full bg-primary animate-ping"></span>
      <span class="text-xs font-medium">Searching & processing...</span>
    </div>
  `;
  container.appendChild(bubble);
  container.scrollTop = container.scrollHeight;
  return id;
}

function removeMessage(id) {
  if (!id) return;
  const el = document.getElementById(id);
  if (el) el.remove();
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// --- Google OAuth (Connect Gmail) Client Handlers ---
async function checkGmailStatus() {
  const pill = document.getElementById("gmail-status-pill");
  const unlinkedBox = document.getElementById("gmail-unlinked-state");
  const linkedBox = document.getElementById("gmail-linked-state");
  const emailSpan = document.getElementById("gmail-linked-email");

  try {
    const res = await fetch("/api/auth/google/status", {
      headers: authToken ? { "Authorization": `Bearer ${authToken}` } : {},
    });
    const data = await res.json();

    if (data.connected && data.email) {
      if (pill) {
        pill.innerText = "Linked";
        pill.className = "text-[9px] px-2 py-0.5 rounded-full font-semibold bg-emerald-100 text-emerald-800";
      }
      if (unlinkedBox) unlinkedBox.classList.add("hidden");
      if (linkedBox) linkedBox.classList.remove("hidden");
      if (emailSpan) emailSpan.innerText = data.email;
    } else {
      if (pill) {
        pill.innerText = data.oauth_configured ? "Not Linked" : "Ready";
        pill.className = "text-[9px] px-2 py-0.5 rounded-full font-semibold bg-surface-container text-on-surface-variant";
      }
      if (unlinkedBox) unlinkedBox.classList.remove("hidden");
      if (linkedBox) linkedBox.classList.add("hidden");
    }
  } catch (err) {
    console.warn("Could not check Gmail status:", err);
  }
}

async function connectGmailAccount() {
  try {
    const res = await fetch("/api/auth/google/url", {
      headers: authToken ? { "Authorization": `Bearer ${authToken}` } : {},
    });
    const data = await res.json();
    if (!data.configured) {
      alert("Google OAuth 2.0 Credentials Setup:\n\nTo enable production 1-click Google sign-in:\n1. Open Google Cloud Console (console.cloud.google.com)\n2. Create an OAuth 2.0 Client ID (Web Application)\n3. Set Redirect URI: http://localhost:8000/api/auth/google/callback\n4. Add GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET to your .env file.\n\n(In the meantime, the assistant will seamlessly use the fallback Gmail SMTP configured in .env!)");
      return;
    }
    // Open Google OAuth consent popup
    const width = 500;
    const height = 650;
    const left = window.screen.width / 2 - width / 2;
    const top = window.screen.height / 2 - height / 2;
    window.open(
      data.url,
      "google_oauth_popup",
      `width=${width},height=${height},top=${top},left=${left},status=no,resizable=yes`
    );
  } catch (err) {
    alert("Could not start Google connection: " + err.message);
  }
}

async function disconnectGmailAccount() {
  if (!confirm("Are you sure you want to disconnect your Gmail account?")) return;
  try {
    const res = await fetch("/api/auth/google/disconnect", {
      method: "POST",
      headers: authToken ? { "Authorization": `Bearer ${authToken}` } : {},
    });
    await res.json();
    checkGmailStatus();
  } catch (err) {
    alert("Could not disconnect Gmail: " + err.message);
  }
}

// Window listener for OAuth popup completion
window.addEventListener("message", (event) => {
  if (event.data && event.data.type === "GMAIL_CONNECTED") {
    checkGmailStatus();
  }
});

// ============================================================================
// LiveKit WebRTC Voice Engine (Dedicated Real-Time Audio)
// ============================================================================
let livekitRoom = null;
let isLiveKitConnecting = false;

async function checkLiveKitStatus() {
  try {
    const res = await fetch("/api/livekit/status");
    const data = await res.json();
    const pill = document.getElementById("livekit-status-pill");
    if (pill) {
      if (data.configured) {
        pill.innerText = "LiveKit Ready";
        pill.className = "text-[9px] px-2 py-0.5 rounded-full font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200";
      } else {
        pill.innerText = "Setup Required";
        pill.className = "text-[9px] px-2 py-0.5 rounded-full font-semibold bg-amber-50 text-amber-700 border border-amber-200";
      }
    }
  } catch (e) {
    console.warn("Could not check LiveKit status:", e);
  }
}

async function toggleLiveKitConnection() {
  if (livekitRoom) {
    await disconnectLiveKit();
  } else {
    await connectLiveKit();
  }
}

async function connectLiveKit() {
  if (isLiveKitConnecting) return;
  if (typeof LivekitClient === "undefined") {
    alert("LiveKit client library is loading. Please check your internet connection and try again.");
    return;
  }

  const btn = document.getElementById("livekit-connect-btn");
  const btnLabel = document.getElementById("livekit-connect-btn-label");
  const pill = document.getElementById("livekit-status-pill");
  const latency = document.getElementById("livekit-latency-indicator");

  try {
    isLiveKitConnecting = true;
    updateMicUI("connecting");
    if (btn) btn.className = "w-full flex items-center justify-center gap-2 py-2 px-3 rounded-xl bg-amber-500 hover:bg-amber-600 text-white text-xs font-semibold transition-all shadow-sm";
    if (btnLabel) btnLabel.innerText = "Connecting WebRTC...";
    if (pill) {
      pill.innerText = "Connecting...";
      pill.className = "text-[9px] px-2 py-0.5 rounded-full font-semibold bg-amber-100 text-amber-800 border border-amber-200";
    }

    // 1. Fetch room token from backend
    const res = await fetch("/api/livekit/token", {
      headers: authToken ? { "Authorization": `Bearer ${authToken}` } : {},
    });
    const data = await res.json();

    if (!data.success) {
      alert("LiveKit WebRTC Configuration Required:\n\n" + (data.message || "Please configure LIVEKIT_URL, LIVEKIT_API_KEY, and LIVEKIT_API_SECRET in your .env file.\n\nThen start the LiveKit Agent worker with:\npython run_livekit.py dev"));
      resetLiveKitUI();
      return;
    }

    // 2. Initialize LiveKit Room
    livekitRoom = new LivekitClient.Room({
      adaptiveStream: true,
      dynacast: true,
      audioCaptureDefaults: {
        autoGainControl: true,
        echoCancellation: true,
        noiseSuppression: true,
      },
    });

    // Handle remote assistant audio tracks
    livekitRoom.on(LivekitClient.RoomEvent.TrackSubscribed, (track, publication, participant) => {
      if (track.kind === LivekitClient.Track.Kind.Audio) {
        const existingAudio = document.getElementById(`audio-${participant.identity}`);
        if (existingAudio) existingAudio.remove();
        const audioElement = track.attach();
        audioElement.id = `audio-${participant.identity}`;
        audioElement.autoplay = true;
        document.body.appendChild(audioElement);
        audioElement.play().catch(e => console.warn("LiveKit audio playback notice:", e));
      }
    });

    // Listen for data packets from worker (e.g. auto-launch app or open URL)
    livekitRoom.on(LivekitClient.RoomEvent.DataReceived, (payload, participant) => {
      try {
        const text = new TextDecoder().decode(payload);
        const dataPacket = JSON.parse(text);
        if (dataPacket.type === "OPEN_URL" && dataPacket.url) {
          triggerOpenUrl(dataPacket.url);
        }
      } catch (e) {
        console.warn("Could not process LiveKit data packet:", e);
      }
    });

    // Handle disconnect event
    livekitRoom.on(LivekitClient.RoomEvent.Disconnected, () => {
      resetLiveKitUI();
    });

    // 3. Connect to room & publish local microphone
    await livekitRoom.connect(data.url, data.token);
    try {
      await livekitRoom.localParticipant.setMicrophoneEnabled(true);
    } catch (micErr) {
      console.warn("Microphone access error:", micErr);
      alert("Microphone Access Required:\nPlease allow microphone access in your browser address bar to speak with LiveKit.");
    }

    // Update UI to Connected State
    if (btn) {
      btn.className = "w-full flex items-center justify-center gap-2 py-2 px-3 rounded-xl bg-red-600 hover:bg-red-700 text-white text-xs font-semibold transition-all shadow-sm";
    }
    if (btnLabel) btnLabel.innerText = "Disconnect LiveKit Voice";
    if (pill) {
      pill.innerText = "Connected";
      pill.className = "text-[9px] px-2 py-0.5 rounded-full font-semibold bg-emerald-100 text-emerald-800 border border-emerald-300";
    }
    if (latency) latency.classList.remove("hidden");
    updateMicUI("connected");

    appendAssistantBubble(
      "LiveKit WebRTC audio stream connected! Speak into your microphone for real-time full-duplex voice response.",
      [{ tool: "livekit_webrtc", result: { status: "connected", room: data.room } }]
    );
  } catch (err) {
    console.error("LiveKit connection error:", err);
    alert("Could not connect to LiveKit WebRTC room: " + err.message);
    resetLiveKitUI();
  } finally {
    isLiveKitConnecting = false;
  }
}

async function disconnectLiveKit() {
  if (livekitRoom) {
    try {
      await livekitRoom.disconnect();
    } catch (e) {}
    livekitRoom = null;
  }
  resetLiveKitUI();
}

function resetLiveKitUI() {
  livekitRoom = null;
  isLiveKitConnecting = false;
  const btn = document.getElementById("livekit-connect-btn");
  const btnLabel = document.getElementById("livekit-connect-btn-label");
  const pill = document.getElementById("livekit-status-pill");
  const latency = document.getElementById("livekit-latency-indicator");

  if (btn) {
    btn.className = "w-full flex items-center justify-center gap-2 py-2 px-3 rounded-xl bg-primary hover:bg-primary-container text-white text-xs font-semibold transition-all shadow-sm group";
  }
  if (btnLabel) btnLabel.innerText = "Connect LiveKit Voice";
  if (pill) {
    pill.innerText = "LiveKit Ready";
    pill.className = "text-[9px] px-2 py-0.5 rounded-full font-semibold bg-primary/10 text-primary border border-primary/20";
  }
  if (latency) latency.classList.add("hidden");
  updateMicUI("idle");
}
