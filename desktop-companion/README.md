# Nexus Windows Desktop Companion Agent (Phase 7)

The **Nexus Windows Desktop Companion** is a local Python daemon running on the user's Windows machine. It connects to the Nexus backend via an outbound secure WebSocket channel (`/ws/desktop/companion`) to perform desktop automations under strict safety guardrails.

---

## Key Features & Security Guarantees

1. **Strict Application Allowlist**:
   Only pre-approved applications can be launched:
   - `notepad` (`notepad.exe`)
   - `calculator` (`calc.exe`)
   - `explorer` (`explorer.exe`)
   - `taskmgr` (`taskmgr.exe`)
   - `terminal` (`wt.exe`)
   - `browser` (`msedge.exe`)
   - `code` (`code.cmd`)

2. **No Arbitrary Shell Execution**:
   - `subprocess.Popen(..., shell=False)` is used exclusively with pre-validated executable paths.
   - Prohibited actions (e.g. `arbitrary_shell_exec`, `format_disk`, `bypass_auth`) are deterministically blocked by the backend `PolicyEngine`.

3. **Human Approval Gates**:
   - Destructive operations, file deletions, or script executions require explicit human consent in the Nexus dashboard or voice assistant before dispatch.

4. **Active Window & Telemetry**:
   - Safely queries active foreground window titles and system resource metrics using Win32 API bindings.

5. **Scoped Safe File Search**:
   - Only reads within user documents/project folders matching safe extensions (`.txt`, `.md`, `.json`, `.pdf`, `.png`, etc.).

---

## Running the Companion

```powershell
# From the project root
python desktop-companion/main.py ws://localhost:8000/ws/desktop/companion
```

