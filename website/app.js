/**
 * Nexus OS v2.4 - Static Showcase Website Scripts
 * Strictly ZERO emojis. Pure SVG & text.
 */

document.addEventListener('DOMContentLoaded', () => {
  // 1. Workspace Showcase Viewport Tabs Switcher
  const tabButtons = document.querySelectorAll('.tab-btn');
  const showcaseViews = document.querySelectorAll('.showcase-view');
  const frameAddressPath = document.getElementById('frame-address-path');

  const pathMap = {
    overview: 'nexus://workspace/overview',
    voice: 'nexus://workspace/voice-studio',
    kanban: 'nexus://workspace/autonomous-tasks',
    chat: 'nexus://workspace/agentic-orchestration',
  };

  tabButtons.forEach((btn) => {
    btn.addEventListener('click', () => {
      const targetView = btn.getAttribute('data-view');

      // Update button active state
      tabButtons.forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');

      // Update view display
      showcaseViews.forEach((view) => {
        if (view.id === `view-${targetView}`) {
          view.classList.add('active');
        } else {
          view.classList.remove('active');
        }
      });

      // Update address bar text
      if (frameAddressPath && pathMap[targetView]) {
        frameAddressPath.textContent = pathMap[targetView];
      }
    });
  });

  // 2. Terminal Code Snippets Switcher
  const snippetTabs = document.querySelectorAll('.snippet-tab');
  const terminalCmdText = document.getElementById('terminal-cmd-text');

  const snippets = {
    local: `# 1. Clone Nexus repository
git clone https://github.com/nexus-org/nexus-os.git
cd "voice assistant"

# 2. Automated One-Click Windows Daemon Startup
start-nexus.bat

# System will initialize FastAPI (:8000) and Vite Monochrome UI (:5173)`,

    docker: `# Run fully containerized production stack with Docker Compose
docker compose -f docker-compose.prod.yml up -d --build

# Inspect running cluster containers
docker compose ps
# Nexus backend, Redis queue, SQLite / Postgres, and Nginx frontend live`,

    api: `# Dispatch natural language agentic workflow via cURL
curl -X POST "http://127.0.0.1:8000/api/v1/chat" \\
  -H "Content-Type: application/json" \\
  -d '{"message": "Check calendar collisions and summarize launch blockers email"}'

# Output returns LangGraph deterministic state & human approval gates`,
  };

  snippetTabs.forEach((tab) => {
    tab.addEventListener('click', () => {
      const snippetKey = tab.getAttribute('data-snippet');
      snippetTabs.forEach((t) => t.classList.remove('active'));
      tab.classList.add('active');

      if (terminalCmdText && snippets[snippetKey]) {
        terminalCmdText.textContent = snippets[snippetKey];
      }
    });
  });

  // 3. Copy Snippet Button
  const copyBtn = document.getElementById('copy-snippet-btn');
  if (copyBtn && terminalCmdText) {
    copyBtn.addEventListener('click', () => {
      const textToCopy = terminalCmdText.textContent;
      navigator.clipboard.writeText(textToCopy).then(() => {
        const originalText = copyBtn.querySelector('.copy-text').textContent;
        copyBtn.querySelector('.copy-text').textContent = 'Copied!';
        setTimeout(() => {
          copyBtn.querySelector('.copy-text').textContent = originalText;
        }, 2000);
      });
    });
  }

  // 4. Live Health Check Poller
  const liveStatusPill = document.getElementById('live-mesh-status');
  const liveLatencyEl = document.getElementById('live-latency-val');

  async function checkLiveMesh() {
    try {
      const startTime = performance.now();
      const res = await fetch('http://127.0.0.1:8000/api/v1/health');
      const endTime = performance.now();
      const latency = Math.round(endTime - startTime);

      if (res.ok) {
        if (liveStatusPill) {
          liveStatusPill.innerHTML = `
            <span class="pulse-dot"></span>
            <span>Mesh Online &bull; ${latency}ms</span>
          `;
        }
        if (liveLatencyEl) {
          liveLatencyEl.textContent = `${latency}ms`;
        }
      }
    } catch (e) {
      // Backend not reached locally - keep default static indicator
      if (liveStatusPill) {
        liveStatusPill.innerHTML = `
          <span class="pulse-dot"></span>
          <span>Mesh Fabric Ready &bull; 38ms</span>
        `;
      }
    }
  }

  checkLiveMesh();
  setInterval(checkLiveMesh, 15000);

  // 5. Interactive Voice Visualizer Waveform Heights
  const waveBars = document.querySelectorAll('.wave-bar');
  const orbCore = document.querySelector('.orb-core');
  let isOrbActive = true;

  if (orbCore) {
    orbCore.addEventListener('click', () => {
      isOrbActive = !isOrbActive;
      waveBars.forEach((bar) => {
        bar.style.animationPlayState = isOrbActive ? 'running' : 'paused';
        bar.style.opacity = isOrbActive ? '1' : '0.25';
      });
    });
  }
});
