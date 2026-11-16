# Nexus AI Voice Assistant — Benchmark & Evaluation Scorecard
**Timestamp:** `2026-11-16T11:07:24.922934+00:00` | **Overall Score:** `100.0% PASS`

---
## 1. Component Latency Profile
| Component / Tool | Average (ms) | Min (ms) | Max (ms) |
|---|---|---|---|
| `calculator` | **0.12 ms** | 0.03 ms | 0.28 ms |
| `clock_timezone` | **3.85 ms** | 0.01 ms | 11.53 ms |
| `app_launcher` | **68.96 ms** | 24.5 ms | 154.84 ms |
| `whatsapp_url` | **29.22 ms** | 24.67 ms | 31.65 ms |
| `python_sandbox` | **0.17 ms** | 0.09 ms | 0.3 ms |
| `web_search` | **1303.82 ms** | 1303.82 ms | 1303.82 ms |
| `rag_vector_search` | **564.79 ms** | 293.46 ms | 888.59 ms |
| `email_composer` | **1328.79 ms** | 1118.14 ms | 1726.16 ms |

## 2. Tool Execution Accuracy
**Score:** `100.0%` (6/6 Passed)

- ✅ **Math Percentage Calculation**: Result: 1150.0 (Expected: 1150.0)
- ✅ **Timezone Precision (UTC)**: Spoken: The current time is Monday, November 16, 2026 at 11:07 AM (UTC).
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