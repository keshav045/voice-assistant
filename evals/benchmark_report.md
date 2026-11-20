# Nexus AI Voice Assistant — Benchmark & Evaluation Scorecard
**Timestamp:** `2026-11-20T13:53:52.394259+00:00` | **Overall Score:** `100.0% PASS`

---
## 1. Component Latency Profile
| Component / Tool | Average (ms) | Min (ms) | Max (ms) |
|---|---|---|---|
| `calculator` | **0.13 ms** | 0.04 ms | 0.3 ms |
| `clock_timezone` | **6.55 ms** | 0.01 ms | 19.63 ms |
| `app_launcher` | **54.52 ms** | 19.1 ms | 125.31 ms |
| `whatsapp_url` | **35.84 ms** | 25.81 ms | 52.41 ms |
| `python_sandbox` | **0.16 ms** | 0.08 ms | 0.3 ms |
| `web_search` | **1956.16 ms** | 1956.16 ms | 1956.16 ms |
| `rag_vector_search` | **1421.34 ms** | 284.98 ms | 3259.46 ms |
| `email_composer` | **2081.71 ms** | 1629.32 ms | 2949.34 ms |

## 2. Tool Execution Accuracy
**Score:** `100.0%` (6/6 Passed)

- ✅ **Math Percentage Calculation**: Result: 1150.0 (Expected: 1150.0)
- ✅ **Timezone Precision (UTC)**: Spoken: The current time is Friday, November 20, 2026 at 01:53 PM (UTC).
- ✅ **App Launcher Query Resolution**: URL: https://www.youtube.com/results?search_query=jazz+music
- ✅ **WhatsApp Click-to-Chat Link Generation**: Target: Alice
- ✅ **Python Code Execution Sandbox**: Output: [0, 1, 2, 3]
- ✅ **AI Email Generation Quality**: Subject: 'Rescheduling Project Status Meeting'

## 3. Error Detection & Resilience Testing
**Score:** `100.0%` (6/6 Gracefully Handled)

- 🛡️ **Division by Zero in Math**: Caught error: 'Division by zero'
- 🛡️ **Syntax Error in Math Expression**: Caught error: ''(' was never closed (<unknown>, line 1)'
- 🛡️ **Malicious Code Injection Blocking (os.system)**: Blocked with: 'Security restriction: 'os.system' is blocked.'
- 🛡️ **Unknown App Launcher Graceful Fallback**: Fallback search URL: 'https://www.google.com/search?q=quantum_hyper_nonexistent_tool_123'
- 🛡️ **Invalid Timezone Fallback Handling**: Resolved timezone: 'UTC'
- 🛡️ **Zero Markdown Leakage in Spoken Voice Stream**: Cleaned speech: 'Spoken Update Task 1: Finished with status 200! Check Docs.'

## 4. Safety Confirmation Gating
- **Write-action protection:** `PASS`
- **Read-action unblocking:** `PASS`
- **Precision:** `100.0%`
- **Natural Language Affirm/Deny Parser:** `PASS`

## 5. System Health & Infrastructure
- SQLite WAL Concurrency: `ENABLED`
- Database Tables Integrity: `INTACT`
- OpenAI LLM Status: `READY`
- Google OAuth Status: `READY`
- LiveKit Cloud WebRTC Status: `READY`