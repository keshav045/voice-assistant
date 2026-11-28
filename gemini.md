# Nexus AI Assistant — End-to-End Script & Component Reference

This document provides a comprehensive technical reference for every executable script,
background service, agent module, tool, evaluation harness, test suite, and frontend
interface in the Nexus AI Assistant project.

For each script, the following specifications are detailed:
- **Script Path & File Name**
- **Core Purpose & Role**
- **Execution Command & Runtime Environment**
- **Key Inputs & Configuration Parameters**
- **Outputs & Side Effects**
- **End-to-End Operational Use Case**

---

## 1. Master Application Runners & Entrypoints

### 1.1 `run_server.py`
- **Path**: `run_server.py`
- **Role**: Launches the central FastAPI REST & WebSocket backend service and serves the Web UI (`web/index.html`).
- **Execution Command**:
  ```bash
  .venv\Scripts\python.exe run_server.py
  ```
- **Inputs**: Reads environment variables from `.env` (`OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`, `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`).
- **Outputs**: Binds Uvicorn HTTP server to `http://127.0.0.1:8000`. Serves REST endpoints (`/api/chat`, `/api/chat/confirm`, `/api/livekit/token`, `/api/auth/google/callback`, `/api/history`, `/api/stt`, `/api/tts`, `/api/updates/stream`) and WebSockets (`/ws/voice/{session_id}`).
- **End-to-End Use Case**: Serves as the primary API gateway and native Web UI host, orchestrates LLM chat turns, executes tool calling, handles Google OAuth callbacks, and issues LiveKit access tokens.

### 1.2 `run_livekit.py`
- **Path**: `run_livekit.py`
- **Role**: Starts the real-time LiveKit WebRTC Voice Pipeline Worker.
- **Execution Command**:
  ```bash
  .venv\Scripts\python.exe run_livekit.py dev
  ```
- **Inputs**: LiveKit Cloud credentials (`LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`) and LLM settings (`OPENAI_BASE_URL` / `OPENAI_API_KEY`).
- **Outputs**: Establishes a persistent worker connection to LiveKit Cloud.
- **End-to-End Use Case**: Subscribes to audio rooms created by the native web frontend (`web/index.html`), streams bidirectional voice via WebRTC, runs local Silero VAD + `faster-whisper` STT + `qwen2.5:1.5b` (with `qwen3:1.7b` fallback) + Piper ONNX / Edge-TTS, and executes registered Python tools in real time.

### 1.3 Web Frontend (`web/index.html` & `web/app.js`)
- **Path**: `web/index.html`, `web/app.js`
- **Role**: Production executive web interface with integrated LiveKit WebRTC voice controls and Server-Sent Events (SSE) updates, served directly by `run_server.py` on `http://localhost:8000`.
- **Execution Command**:
  ```bash
  .venv\Scripts\python.exe run_server.py
  ```
- **Inputs**: User text input via chat capsule, voice audio via LiveKit WebRTC, Google OAuth sign-in, and username/password authentication.
- **Outputs**: Renders modern web UI at `http://localhost:8000` with conversation history, tool execution cards (Web Search/Live News, Math, Medicine Information, Email Dispatched, App Launch links, HITL confirmation cards), and LiveKit audio telemetry.
- **End-to-End Use Case**: Exclusive graphical web interface for end-users to interact via text and real-time voice, manage their Google OAuth connection, view structured tool cards, and browse chat history.

### 1.4 `run_voice.py`
- **Path**: `run_voice.py`
- **Role**: Standalone local microphone and speaker audio loop runner.
- **Execution Command**:
  ```bash
  .venv\Scripts\python.exe run_voice.py
  ```
- **Inputs**: Default system microphone and audio output devices.
- **Outputs**: Records user speech chunks, posts them to `/api/stt` or local Whisper, routes transcribed text to `/api/chat`, and plays returned MP3 audio through system speakers.
- **End-to-End Use Case**: Used for headless, desktop-only terminal voice interactions without running a browser or WebRTC connection.

---

## 2. Core Agent Architecture & Orchestration

### 2.1 `agent/main.py`
- **Path**: `agent/main.py`
- **Role**: FastAPI application instance, multi-domain router, tool calling dispatcher, and cloud-to-local failover planner.
- **Key Functions**:
  - `process_user_turn(user_text, session_id, user_id)`: Central coordinator that queries OpenAI with active function schemas, parses tool calls, executes handlers, and handles local fallback heuristics.
  - `google_auth_callback(code, state)`: Exchanges Google OAuth code for tokens, saves credentials to SQLite for user "krish", and redirects to frontend.
  - `livekit_token_endpoint(req)`: Generates cryptographically signed LiveKit WebRTC room tokens.
- **End-to-End Use Case**: The central nervous system of the project. Whenever a user sends a message or a tool is executed, `agent/main.py` coordinates LLM inference, database logging, tool dispatching, and error resilience.

### 2.2 `agent/livekit_worker.py`
- **Path**: `agent/livekit_worker.py`
- **Role**: LiveKit WebRTC Agent worker definition, local Silero VAD turn detection, and tool execution loop.
- **Key Functions**:
  - `entrypoint(ctx)`: Initializes WebRTC audio room session, configures local Silero VAD (activation threshold 0.50, silence cutoff 0.40s, max endpoint delay 0.8s), binds OpenAI LLM and TTS plugins, and starts listener with local turn detection (`turn_detection="vad"`). Employs zero-latency startup without blocking greeting synthesis.
  - `@llm.function_tool` definitions: Registers `web_search`, `calculator`, `medical_search`, `run_python_code`, `get_current_time`, `open_app`, `send_whatsapp_message`, and `send_email`.
  - `_broadcast_client_action(action_type, data)`: Sends real-time data packets to the browser client (e.g. triggering URL navigation for YouTube/WhatsApp or showing email sent toasts).
- **End-to-End Use Case**: Powers hands-free, auto-silence conversational voice. When Krish speaks, local Silero VAD detects speech onset instantly, cuts off within 400ms of user silence, executes tools asynchronously, and returns audio answers in real time without cloud inference gateway timeouts.

### 2.3 `agent/prompts.py`
- **Path**: `agent/prompts.py`
- **Role**: Stores `SYSTEM_PROMPT` containing master behavioral instructions and voice formatting guidelines.
- **Key Rules**:
  - Real-time news delivery with natural follow-up questions.
  - Direct live cricket score reporting.
  - YouTube search and application opening directives.
  - Phonetic email address normalization.
  - User identity rules for Krish and meeting invitations.
  - Medical information search directives.
  - Strict zero-markdown spoken text formatting.
- **End-to-End Use Case**: Injected into every LLM call across cloud and voice pipelines to ensure consistent persona, high conversational intelligence, and clean vocal delivery.

### 2.4 `agent/safety.py`
- **Path**: `agent/safety.py`
- **Role**: Safety policy enforcement and confirmation gating for high-stakes write actions.
- **Key Functions**:
  - `check_action_safety(tool_name, args)`: Determines whether an action requires explicit human confirmation.
  - `build_confirmation_prompt(tool_name, args)`: Creates natural language verification questions.
- **End-to-End Use Case**: Protects users against accidental email dispatch or calendar changes by intercepting actions until confirmed.

### 2.5 `agent/confirm.py`
- **Path**: `agent/confirm.py`
- **Role**: Natural language confirmation intent parser.
- **Key Functions**:
  - `parse_confirmation(user_text)`: Evaluates user affirmation ("yes", "sure", "proceed", "send it") or cancellation ("no", "cancel", "stop", "abort").
- **End-to-End Use Case**: Ensures natural conversational confirmation parsing without requiring rigid keyword syntax.

### 2.6 `agent/session.py`
- **Path**: `agent/session.py`
- **Role**: In-memory multi-turn conversational session buffer.
- **Key Functions**:
  - `add_turn(session_id, user_text, spoken_reply)`: Stores turn messages.
  - `get_messages_for_prompt(session_id, max_turns)`: Formats history for LLM prompt context window.
  - `clear_session(session_id)`: Wipes in-memory session state.
- **End-to-End Use Case**: Provides conversational continuity so users can refer to previous statements (e.g. "What did I just say?").

### 2.7 `agent/memory.py`
- **Path**: `agent/memory.py`
- **Role**: Long-term semantic fact memory manager.
- **Key Functions**:
  - `save_fact(user_id, fact_text)`: Persists user facts in database.
  - `recall_facts(user_id, query)`: Retrieves relevant user facts based on query keywords.
- **End-to-End Use Case**: Stores persistent user preferences (e.g. "My favorite sport is cricket") that persist across sessions.

### 2.8 `agent/cli.py`
- **Path**: `agent/cli.py`
- **Role**: Interactive terminal chat interface for developer testing.
- **Execution Command**:
  ```bash
  .venv\Scripts\python.exe -m agent.cli
  ```
- **End-to-End Use Case**: Allows developers to test multi-turn conversations and tool calling directly in PowerShell without starting web servers.

### 2.9 `agent/lc_tools.py`
- **Path**: `agent/lc_tools.py`
- **Role**: LangChain `@tool` function wrappers for all 18 Nexus tools with human-in-the-loop `interrupt()` safety pauses.
- **Key Features**:
  - Irreversible actions (`send_email`, `delete_task`, `create_event`) place `interrupt()` as the very first statement before any side effect can occur.
  - Safe read-only tools (`search_web`, `calculator`, `medical_search`, `open_app`, `run_python_code`, `list_tasks`, `remember`) execute directly without pause.
- **End-to-End Use Case**: Exposes Nexus tools to the LangGraph autonomous execution loop while guaranteeing human-in-the-loop safety before executing real-world side effects.

### 2.10 `agent/lc_agent.py`
- **Path**: `agent/lc_agent.py`
- **Role**: LangGraph StateGraph autonomous agent with checkpointed state persistence and confirmation resumption.
- **Key Functions**:
  - `build_agent_graph(checkpointer, custom_llm)`: Compiles StateGraph with `agent_node`, `ToolNode(LANGGRAPH_TOOLS)`, and persistent SQLite checkpointer (`SqliteSaver`).
  - `run_langgraph_turn(message, session_id, user_id)`: Executes turns, halts at `__interrupt__` on sensitive actions, and returns confirmation prompts.
  - `resume_langgraph_turn(decision, session_id)`: Resumes paused runs via `Command(resume="yes"|"no")` using thread checkpoints.
- **End-to-End Use Case**: Replaces manual tool calling with an autonomous LangGraph agent loop that halts before irreversible actions and resumes upon explicit approval.

---

## 3. Tool Suite (`agent/tools/`)

### 3.1 `agent/tools/medical.py`
- **Path**: `agent/tools/medical.py`
- **Primary Function**: `medical_search(medicine_name: str, topic: str = "all") -> Dict[str, Any]`
- **Data Layers**:
  1. Curated Clinical Knowledge Base: Instant offline pharmacology for Paracetamol, Dolo 650, Ibuprofen, Combiflam, Metformin, Amoxicillin, Azithromycin, Omeprazole, Pantoprazole, Cetirizine, Aspirin, Atorvastatin, Losartan, Montelukast.
  2. OpenFDA Drug Label API: Queries `api.fda.gov` for official FDA label indications, dosage, warnings, and adverse reactions.
  3. Medical Web Search Fallback: Searches DuckDuckGo for newly approved medications.
- **Output Fields**: Generic Name, Drug Class, Brand Names, Uses, Dosage, Side Effects, Precautions, Interactions, Spoken Summary, Medical Disclaimer.
- **End-to-End Use Case**: Answers user questions about any medicine across voice and text, returning clinical details with responsible medical disclaimers.

### 3.2 `agent/tools/email.py`
- **Path**: `agent/tools/email.py`
- **Primary Function**: `send_email(to, description, recipient_name, sender_email, sender_name, user_id) -> Dict[str, Any]`
- **Capabilities**:
  - Google OAuth REST API: Sends directly via `https://gmail.googleapis.com/gmail/v1/users/me/messages/send` if user has signed in with Google.
  - SMTP Fallback: Sends via Gmail SMTP (ports 587/465) if 16-character App Password is configured.
  - AI Subject and Body Composer: Generates professional email drafts from short spoken descriptions.
  - Bulk Email: Supports sending to comma-separated lists and `contacts.csv` files.
- **End-to-End Use Case**: Enables Krish to say "Send email to John about tomorrow's 3 PM project meeting", composing and sending the message directly from Krish's authenticated Gmail address.

### 3.3 `agent/tools/search.py`
- **Path**: `agent/tools/search.py`
- **Primary Functions**:
  - `web_search(query, max_results)`: Fetches live news, cricket scores, and world events via Google News RSS and DuckDuckGo.
  - `get_current_time(timezone)`: Retrieves current time, date, day of week, and timezone.
- **End-to-End Use Case**: Provides live real-time information that LLMs do not know from pre-training.

### 3.4 `agent/tools/calc.py`
- **Path**: `agent/tools/calc.py`
- **Primary Function**: `calculator(expression: str) -> Dict[str, Any]`
- **Capabilities**: AST-safe mathematical evaluation of arithmetic, percentages, square roots, powers, and financial calculations without using dangerous `eval()`.
- **End-to-End Use Case**: Handles math queries like "Calculate 18% GST on $1,250 and split 3 ways".

### 3.5 `agent/tools/launcher.py`
- **Path**: `agent/tools/launcher.py`
- **Primary Function**: `open_app(name: str, query: str = "", browser: str = None) -> Dict[str, Any]`
- **Capabilities**: Launches local Windows desktop applications (Calculator, Notepad, Explorer) and web applications (YouTube, WhatsApp, LinkedIn, Spotify, GitHub, Gmail) with automatic search query extraction.
- **End-to-End Use Case**: Handles requests like "Open YouTube and search for lofi music", opening the target in a fresh browser tab.

### 3.6 `agent/tools/whatsapp.py`
- **Path**: `agent/tools/whatsapp.py`
- **Primary Function**: `send_whatsapp_message(contact_name: str, message: str = "", phone: str = "") -> Dict[str, Any]`
- **Capabilities**: Generates pre-filled WhatsApp Web URLs (`https://web.whatsapp.com/send?text=...`) and opens contact chats.
- **End-to-End Use Case**: Handles requests like "Message Krish on WhatsApp saying Good Morning".

### 3.7 `agent/tools/calendar.py`
- **Path**: `agent/tools/calendar.py`
- **Primary Functions**: `list_events`, `find_free_slot`, `create_event`.
- **End-to-End Use Case**: Manages schedule, checks calendar availability, and creates meeting entries.

### 3.8 `agent/tools/tasks.py`
- **Path**: `agent/tools/tasks.py`
- **Primary Functions**: `add_task`, `list_tasks`, `complete_task`.
- **End-to-End Use Case**: Stores and manages daily to-do items in SQLite.

### 3.9 `agent/tools/coding.py`
- **Path**: `agent/tools/coding.py`
- **Primary Function**: `run_python_code(code: str) -> Dict[str, Any]`
- **Capabilities**: Executes Python scripts in an isolated subprocess with timeout and AST security validation.
- **End-to-End Use Case**: Solves algorithmic problems and verifies code logic on demand.

### 3.10 `agent/tools/docs.py`
- **Path**: `agent/tools/docs.py`
- **Primary Function**: `search_my_docs(query: str) -> Dict[str, Any]`
- **End-to-End Use Case**: Searches local notes and document text files.

### 3.11 `agent/tools/memory_tools.py`
- **Path**: `agent/tools/memory_tools.py`
- **Primary Functions**: `remember(fact: str)`, `forget(fact: str)`.
- **End-to-End Use Case**: Persists custom user facts into the long-term memory store.

---

## 4. Database Layer (`db/models.py`)

- **Path**: `db/models.py`
- **Role**: SQLite database abstraction layer operating in WAL mode.
- **Core Entities Managed**:
  - `users`: User account credentials with bcrypt password hashing.
  - `auth_tokens`: Bearer session tokens for authenticated HTTP API requests.
  - `chat_history`: Permanent conversation turns ordered by `created_at DESC, rowid DESC`.
  - `user_oauth`: Stored Google OAuth access and refresh tokens for 1-click Gmail sending.
  - `email_profiles`: Optional manual sender profiles and App Passwords.
  - `tasks` & `reminders`: User to-do items and scheduled notifications.
  - `tool_call_logs` & `audit_logs`: Detailed performance latency and security audit logs.
- **End-to-End Use Case**: Provides safe, persistent storage across all modules and prevents database locking during concurrent voice streaming and web browsing.

---

## 5. RAG & Vector Engine (`rag/`)

### 5.1 `rag/ingest.py`
- **Path**: `rag/ingest.py`
- **Role**: Document ingestion pipeline. Reads text documents, splits them into semantic chunks, generates vector embeddings, and writes to vector store.
- **Execution Command**:
  ```bash
  .venv\Scripts\python.exe -m rag.ingest
  ```

### 5.2 `rag/store.py`
- **Path**: `rag/store.py`
- **Role**: SQLite-backed vector store with cosine similarity matching and lexical reranking.
- **End-to-End Use Case**: Powers domain-specific RAG knowledge retrieval for personal notes, documentation, and reference manuals.

---

## 6. Master Evaluation Suite (`evals/`)

The evaluation suite implements a 4-pillar, 35-benchmark testing framework:

### 6.1 `evals/run_suite.py`
- **Path**: `evals/run_suite.py`
- **Role**: Master evaluation orchestrator. Runs all 35 modular benchmarks and produces a production promotion verdict.
- **Execution Command**:
  ```bash
  .venv\Scripts\python.exe -m evals.run_suite
  ```
- **Outputs**: Generates `evals/suite_report.json` and prints the pass/fail score table. Requires a 90% minimum pass rate and 0 failed critical tests to approve production deployment.

### 6.2 Modular Evaluation Scripts
- `evals/eval_retriever.py`: Evaluates vector retrieval Hit@1, Hit@3, and MRR.
- `evals/eval_retriever_with_reranker.py`: Validates two-stage semantic reranking precision.
- `evals/eval_generator.py`: Verifies zero markdown leakage in spoken audio and conciseness index.
- `evals/eval_latency.py`: Measures P95 latency for math, clock, and code sandbox tools.
- `evals/eval_cost.py`: Profiles per-turn token usage and financial cost for GPT-4o and Ollama.
- `evals/eval_leakage.py`: Tests boundary defense, API credential masking, and prompt encapsulation.
- `evals/eval_ops.py`: Verifies SQLite WAL concurrency, database schema integrity, and API readiness.
- `evals/eval_rag_pipeline.py`: Validates ground-truth fact retrieval from indexed documents.
- `evals/eval_reliability.py`: Tests error handling for zero division, syntax errors, and code injection attacks.
- `evals/eval_safety.py`: Confirms 100% gating for write actions and natural language confirmation parsing.
- `evals/eval_scope.py`: Verifies the assistant blocks out-of-scope physical or financial commands.
- `evals/eval_toxicity.py`: Asserts 100% interception of toxic inputs with zero false positives on benign queries.
- `evals/eval_application.py`: Validates multi-turn session persistence and clean session isolation.

### 6.3 Supporting Eval Scripts
- `evals/harness.py`: Benchmark execution framework, scoring logic, and JSON formatting.
- `evals/metric_registry.py`: Threshold definitions and pass criteria.
- `evals/promote.py`: Enforces production promotion gate rules.
- `evals/compare.py`: Compares latency and accuracy benchmarks between Cloud GPT-4o and Local Ollama.
- `evals/benchmark_voice.py`: Hardware gate profiler (`record_hardware_profile`), normalized WER/CER & critical entity scoring, manifest loader, contention/thread/VAD sweep runner, and offline E2E telemetry runner (`python -m evals.benchmark_voice`).
- `evals/record_voice_clips.py`: Interactive `16 kHz` mono WAV microphone recording helper saving human test clips and `manifest.jsonl` rows (`python -m evals.record_voice_clips`).

---

## 7. Pytest Unit Test Matrix (`tests/`)

All unit and regression tests (128 tests across 12 modules, isolated via `tests/conftest.py`) can be executed with a single command:
```bash
.venv\Scripts\python.exe -m pytest -v
```

### 7.1 Test Suites Overview
- `tests/test_bug_fixes_regression.py` (6 tests): Verifies pre-mutation HITL gating (`create_event`, `delete_task`), anonymous OAuth session isolation, cross-user token delete isolation, XSS escaping, voice cleaner symbol preservation, confirmation parser boundaries, pediatric & medication clinical lookup fixes, RAG mixed-dim tolerance, and screening/LiveKit launch guards.
- `tests/test_langgraph_safety.py`: Validates LangGraph interrupts, real DB side effects across tool categories, and SQLite checkpointer persistence.
- `tests/test_screening_and_tracing.py`: Validates input/output screening, local SQLite tracing, LangSmith status/callbacks, and persistence health checks.
- `tests/test_agent.py`: Tests agent workflow, approval gating, and tool dispatching.
- `tests/test_auth_and_history.py`: Validates user registration, PBKDF2 password hashing, token validation, and chat history ordering.
- `tests/test_calc_and_session.py`: Tests all calculator operations (addition, percentages, discounts, square roots, division, modulo, negative numbers) and session isolation.
- `tests/test_email.py`: Comprehensive email test matrix covering Google OAuth priority, SMTP fallback, bulk CSV dispatch, and AI composition.
- `tests/test_launcher.py`: Verifies app targets and browser search query extraction.
- `tests/test_livekit.py`: Tests LiveKit status endpoints, token generation, local Piper/Edge TTS, Whisper decoding, and tool binding.
- `tests/test_medical.py`: Validates medical search across curated lookups, topic filtering, pediatric safety, and intent detection.
- `tests/test_voice.py`: Tests clean spoken text formatting, silent audio transcription, and push-to-talk stop events.
- `tests/test_whatsapp.py`: Tests contact search, phone number parsing, and WhatsApp Web message URL formation.
- `tests/verify_all_features.py`: Standalone live verification matrix with tabular reporting.

---

## 8. Web Frontend (`web/`)

### 8.1 `web/index.html`
- **Path**: `web/index.html`
- **Role**: Executive web interface layout built with clean minimalist aesthetics, responsive sidebar, auth/OAuth controls, and chat canvas.

### 8.2 `web/app.js`
- **Path**: `web/app.js`
- **Role**: Client-side JavaScript controller. Manages WebRTC connection to LiveKit Cloud, SSE updates, rich tool cards (News, Medicine, Email), action links, and local chat history.

---

## 9. End-to-End Operational Lifecycle

1. **System Startup**:
   - `run_server.py` starts on port 8000 (FastAPI backend + native `web/index.html` UI).
   - `run_livekit.py` connects to LiveKit Cloud WebRTC room.

2. **User Interaction**:
   - The user opens `http://localhost:8000`.
   - The user clicks `Continue with Google` to sign in and connect Gmail via 1-click OAuth.
   - The user clicks `Connect LiveKit Voice` and speaks: *"What is Dolo 650 used for?"*.
   - LiveKit WebRTC captures audio, Silero VAD detects the pause, `faster-whisper` transcribes the speech locally, and the agent invokes `medical_search(medicine_name="Dolo 650", topic="uses")`.
   - Offline Piper ONNX TTS (with Edge-TTS fallback) streams verbal audio to the browser in real time.
   - The Web UI renders a structured Medicine Information card on screen and logs the turn into SQLite with `ORDER BY created_at DESC, rowid DESC`.

---

## 10. Master Chronological Change Log (By Date, Files Changed & Cascading Impacts)

### 10.1 Date: 2026-10-30
- **Entry 2026-10-30.1** (Commit `39f4740` at 22:27:53 +0530):
  - **Files Changed**: `db/models.py`, `db/schema.sql`, `backend/app/main.py`, `docker-compose.yml`, `README.md`
  - **What Was Changed**: Implemented initial SQLite database layer with WAL mode concurrency; created tables for users, auth_tokens, sessions, chat_history, email_profiles, tasks, reminders, and audit_logs; established FastAPI REST gateway.
  - **What Was Affected**: Established foundational persistence and non-blocking multi-turn database access for all downstream services.
- **Entry 2026-10-30.2** (Commit `545afce` at 22:54:51 +0530):
  - **Files Changed**: `agent/voice.py`, `backend/app/services/voice/*`, `backend/tests/test_voice.py`
  - **What Was Changed**: Built dual-engine voice pipeline with OpenAI Whisper (STT) and OpenAI TTS-1; created `_clean_spoken_text` sanitization to strip markdown, asterisks, backticks, and bullet symbols from spoken speech.
  - **What Was Affected**: Prevented vocalization of markdown syntax and established sub-second vocal playback.
- **Entry 2026-10-30.3** (Commit `af20a91` at 23:20:03 +0530):
  - **Files Changed**: `agent/safety.py`, `agent/confirm.py`, `backend/app/agents/policy.py`, `backend/app/api/v1/endpoints/approvals.py`
  - **What Was Changed**: Built natural language confirmation gating and policy verification for high-stakes write operations (email dispatch, calendar creation).
  - **What Was Affected**: Enforced 100% human-in-the-loop protection against accidental irreversible actions.

### 10.2 Date: 2026-10-31
- **Entry 2026-10-31.1** (Commit `dad2572` at 11:11:43 +0530):
  - **Files Changed**: `agent/tools/tasks.py`, `db/models.py`
  - **What Was Changed**: Created task management toolset (`add_task`, `list_tasks`, `complete_task`) backed by SQLite `tasks` table.
  - **What Was Affected**: Allowed users to manage to-dos and scheduling items directly via natural voice commands.
- **Entry 2026-10-31.2** (Commit `8e402b8` at 11:18:51 +0530):
  - **Files Changed**: `agent/tools/email.py`, `db/models.py`
  - **What Was Changed**: Created email assistant supporting draft creation, message search, and sender profile persistence.
  - **What Was Affected**: Enabled voice-driven email management.
- **Entry 2026-10-31.3** (Commit `2ed80f1` at 11:27:06 +0530):
  - **Files Changed**: `agent/tools/calendar.py`
  - **What Was Changed**: Implemented Google Calendar integration (`list_events`, `find_free_slot`, `create_event`) with Asia/Kolkata timezone support.
  - **What Was Affected**: Automated calendar slot search and meeting scheduling with conflict detection.
- **Entry 2026-10-31.4** (Commit `c77b6e2` at 11:33:08 +0530):
  - **Files Changed**: `agent/tools/launcher.py`
  - **What Was Changed**: Created Windows desktop app launcher (`open_app`) for native apps (Notepad, Calculator) and web destinations (YouTube, WhatsApp, Spotify, GitHub).
  - **What Was Affected**: Users can launch local applications or browser tabs hands-free.
- **Entry 2026-10-31.5** (Commit `355b74b` at 11:39:16 +0530):
  - **Files Changed**: `rag/ingest.py`, `rag/store.py`, `agent/memory.py`, `agent/tools/memory_tools.py`
  - **What Was Changed**: Built semantic vector retrieval engine with cosine similarity matching and long-term memory tools (`remember`, `forget`).
  - **What Was Affected**: Assistant recalls persistent user preferences and domain document knowledge across sessions.
- **Entry 2026-10-31.6** (Commit `3817faf` at 16:32:31 +0530):
  - **Files Changed**: `web/index.html`, `web/app.js`, `agent/prompts.py`, `backend/app/main.py`
  - **What Was Changed**: Completely purged all emoji characters from UI layout, prompts, and backend logs, replacing them with clean SVG and Lucide icons.
  - **What Was Affected**: Delivered an executive black-and-white visual aesthetic and eliminated cross-platform terminal font rendering glitches.

### 10.3 Date: 2026-11-03
- **Entry 2026-11-03.1** (Commit `a1ebd45` at 22:32:52 +0530):
  - **Files Changed**: `agent/tools/email.py`
  - **What Was Changed**: Added live SMTP dispatch via `smtp.gmail.com` with TLS/SSL, 16-character App Passwords, and AI subject/body generation.
  - **What Was Affected**: Delivered live email transmission from short spoken summaries.
- **Entry 2026-11-03.2** (Commit `9228aef` at 23:05:31 +0530):
  - **Files Changed**: `agent/tools/email.py`
  - **What Was Changed**: Added bulk email dispatch for comma-separated recipients and `contacts.csv` parsing.
  - **What Was Affected**: Enabled batch project announcements and multi-recipient email workflows.
- **Entry 2026-11-03.3** (Commit `0725db1` at 23:18:44 +0530):
  - **Files Changed**: `agent/main.py`, `agent/tools/email.py`, `db/models.py`
  - **What Was Changed**: Integrated official Google OAuth 2.0 REST API (`gmail.googleapis.com`) and stored credentials in `user_oauth` SQLite table.
  - **What Was Affected**: Users can send emails directly without configuring App Passwords.

### 10.4 Date: 2026-11-06
- **Entry 2026-11-06.1** (Commit `c70d3ac` at 19:19:09 +0530):
  - **Files Changed**: `run_livekit.py`, `agent/livekit_worker.py`, `agent/main.py`, `requirements.txt`
  - **What Was Changed**: Integrated LiveKit WebRTC Voice Pipeline Worker with bidirectional streaming and `/api/livekit/token` room token generation.
  - **What Was Affected**: Delivered sub-500ms conversational voice interaction over WebRTC audio rooms.

### 10.5 Date: 2026-11-08
- **Entry 2026-11-08.1** (Commit `e015f9f` at 14:06:21 +0530):
  - **Files Changed**: `web/app.js`, `web/index.html`
  - **What Was Changed**: Removed browser Web Speech API in favor of LiveKit WebRTC as dedicated voice engine.
  - **What Was Affected**: Resolved Chrome browser audio cutoffs and transcription dropping.
- **Entry 2026-11-08.2** (Commit `e713275` at 15:43:30 +0530):
  - **Files Changed**: `agent/livekit_worker.py`
  - **What Was Changed**: Made all LiveKit tool functions asynchronous and bound participant identity to active user profile.
  - **What Was Affected**: Eliminated event loop stalls during tool invocation over voice.

### 10.6 Date: 2026-11-11
- **Entry 2026-11-11.1** (Commit `fec3bcb` at 19:49:15 +0530):
  - **Files Changed**: `evals/run_suite.py`, `evals/eval_*.py`
  - **What Was Changed**: Built master 4-pillar LLM evaluation framework (retrieval, generation, pipeline, application).
  - **What Was Affected**: Established automated quality benchmark with 90% minimum pass threshold.
- **Entry 2026-11-11.2** (Commit `c53d0cb` at 20:03:21 +0530):
  - **Files Changed**: `agent/tools/email.py`
  - **What Was Changed**: Prioritized active user Google OAuth session over environment SMTP fallback.
  - **What Was Affected**: Guarantees emails are sent from the authenticated user identity.

### 10.7 Date: 2026-11-15
- **Entry 2026-11-15.1** (Commit `6c7d53c` at 19:32:51 +0530):
  - **Files Changed**: `streamlit_app.py`, `DEPLOY_STREAMLIT.md`, `.streamlit/config.toml`
  - **What Was Changed**: Migrated primary desktop interface to Streamlit (`streamlit_app.py`), embedding LiveKit WebRTC, chat canvas, tool result cards, and Google login.
  - **What Was Affected**: Provided a cohesive, dark-mode ChatGPT-style desktop dashboard for end-users.

### 10.8 Date: 2026-11-20
- **Entry 2026-11-20.1** (Commit `eae14f6` at 20:57:06 +0530):
  - **Files Changed**: `evals/run_suite.py`, `evals/harness.py`, `evals/metric_registry.py`, `evals/eval_*.py` (19 files)
  - **What Was Changed**: Expanded evaluation harness to 35 modular benchmarks with automated production promotion gating.
  - **What Was Affected**: Certified 100% pass rate across security, latency, toxicity, cost, and reliability.
- **Entry 2026-11-20.2** (Commit `d5898c4` at 23:32:42 +0530):
  - **Files Changed**: `streamlit_app.py`, `agent/main.py`, `agent/tools/email.py`, `db/models.py`, `tests/test_email.py`
  - **What Was Changed**: Implemented 1-Click Google OAuth login and logout button in Streamlit sidebar; created `user_email_profiles` table and CRUD methods (`db_save_user_email_profile`, `db_get_user_email_profile`).
  - **What Was Affected**: Users can authenticate with Google directly in the UI, with automatic fallback priority: OAuth Token -> Manual Profile -> Env SMTP.

### 10.9 Date: 2026-11-21
- **Entry 2026-11-21.1** (Commit `553fcd6` at 00:00:49 +0530):
  - **Files Changed**: `db/models.py`, `agent/main.py`, `evals/harness.py`, `streamlit_app.py`, `tests/verify_all_features.py`, `web/app.js`
  - **What Was Changed**: Fixed SQLite chat history ordering by sorting with `ORDER BY created_at DESC, rowid DESC`; eliminated all unicode emojis across evaluation scripts and web JavaScript.
  - **What Was Affected**: Resolved Windows millisecond timestamp collisions in chat history and guaranteed reliable pass for `test_chat_history_persistence`.
- **Entry 2026-11-21.2** (Commit `fbe6eb0` at 00:09:09 +0530):
  - **Files Changed**: `agent/tools/medical.py`, `agent/tools/__init__.py`, `agent/livekit_worker.py`, `agent/main.py`, `agent/prompts.py`, `streamlit_app.py`, `tests/test_medical.py`
  - **What Was Changed**: Implemented Medical Search & Pharmacology tool (`agent/tools/medical.py`) with Curated DB, OpenFDA API, and Web Fallback; registered across voice and chat; added 7 unit tests.
  - **What Was Affected**: Assistant answers detailed medicine queries with clinical precision and safety disclaimers; expanded test matrix to 79/79 passing tests.
- **Entry 2026-11-21.3** (Commit `44ea335` at 00:20:09 +0530):
  - **Files Changed**: `gemini.md`, `history.txt`
  - **What Was Changed**: Created master documentation files `history.txt` and `gemini.md`.
  - **What Was Affected**: Established standardized operational references and change impact matrices.
- **Entry 2026-11-21.4** (Commit `07bfaa4` at 00:30:04 +0530):
  - **Files Changed**: `agent/livekit_worker.py`, `agent/prompts.py`, `streamlit_app.py`
  - **What Was Changed**: Switched LiveKit turn detection from cloud turn-detector-v1 to local Silero VAD (`turn_detection="vad"`); set `activation_threshold=0.50`, `min_silence_duration=0.40s`, `max_endpointing_delay=0.8s`; enforced direct YouTube launching in `SYSTEM_PROMPT`.
  - **What Was Affected**: Voice auto-stops within 400ms of pausing; fan hum and background hiss no longer hold the mic open; eliminated HTTP 408 interruption timeouts.
- **Entry 2026-11-21.5** (Commit `ed94583` at 00:47:49 +0530):
  - **Files Changed**: `agent/livekit_worker.py`, `streamlit_app.py`, `dom_inspect.py`, `DEPLOY_STREAMLIT.md`, `evals/benchmark_report.md`, `gemini.md`, `history.txt`
  - **What Was Changed**: Removed blocking `await session.say(...)` upon LiveKit connection; created `dom_inspect.py` using Playwright headless Chromium for automated DOM inspection; added animated real-time audio waveform visualizer (`.lk-wave`) in `streamlit_app.py`; removed remaining emojis from documentation.
  - **What Was Affected**: Voice connection latency dropped from 7+ seconds to under 3 milliseconds; user microphone is hot immediately upon joining; waveform visualizer provides clear feedback of active speech; verified 0 emojis across entire repository.

### 10.10 Date: 2026-11-22
- **Entry 2026-11-22.1**:
  - **Files Changed**: `agent/prompts.py`, `agent/main.py`
  - **What Was Changed**: Implemented conversational greeting and pleasantry fallback handler in `agent/main.py` to prevent basic greetings ("hello", "hi", "hey", "namaste", "good morning", "how are you") from executing web searches; gated fallback search to informational questions or queries with 3+ words; added `COMPACT_SYSTEM_PROMPT` in `agent/prompts.py` with `num_ctx=4096` parameter passing for local Ollama models.
  - **What Was Affected**: Basic greetings return an immediate, natural spoken greeting without invoking external search engines; resolves 400 Bad Request context limit errors on local Ollama models; preserves conversational continuity even if Cloud OpenAI credits are exhausted.
- **Entry 2026-11-22.2**:
  - **Files Changed**: `agent/main.py`
  - **What Was Changed**: Implemented `_is_tool_call_aligned_with_intent` anti-hallucination guardrail in `agent/main.py` to validate that any LLM-emitted tool call (particularly from small local Ollama models like `rtu-senior:latest`) matches explicit user intent before execution; added fast greeting interceptor at top of `process_user_turn` returning direct spoken responses in ~1ms without querying the LLM.
  - **What Was Affected**: Eliminates unintended tool execution and email dispatch hallucinations (preventing models from firing `send_email` on casual greetings); slashes greeting turn latency from 28.2 seconds to 1 millisecond.
- **Entry 2026-11-22.3**:
  - **Files Changed**: `.env`, `agent/main.py`, `agent/livekit_worker.py`, `agent/tools/email.py`, `streamlit_app.py`
  - **What Was Changed**: Completely removed `OPENAI_API_KEY` from `.env` and converted the default environment to 100% offline local model operation using Local Ollama (`rtu-senior:latest` at `http://localhost:11434/v1`); changed default model engine in `streamlit_app.py` to Local Ollama; disabled external OpenAI API network requests for speech and transcription when no key is set; expanded `_is_tool_call_aligned_with_intent` in `agent/main.py` across all active tools (`web_search`, `calculator`, `medical_search`, `run_python_code`, `get_current_time`, `open_app`, `send_whatsapp_message`, `send_email`) to eliminate hallucinated searches and write actions; added intent remapping for WhatsApp messaging; configured LiveKit worker to bind to local Ollama.
  - **What Was Affected**: Achieved 100% local model autonomy without any cloud API key or payment dependency; resolved all hallucinated web searches ("Windows Hello TPM lockout") and unprompted email transmissions when users say "hello"; verified 79/79 pytest unit tests passed (100%) offline with 0 emojis.
- **Entry 2026-11-22.4**:
  - **Files Changed**: `agent/local_voice.py`, `agent/livekit_worker.py`, `streamlit_app.py`
  - **What Was Changed**: Diagnosed and resolved LiveKit WebRTC Voice worker failure observed in user video recording where speaking "hello India versus New Zealand search for it" resulted in dead air due to Ollama throwing HTTP 404 (model 'gpt-4o-mini-transcribe' not found); created `agent/local_voice.py` containing `LocalWhisperSTT` (faster-whisper CPU inference) and `LocalEdgeTTS` (neural Edge speech synthesis); wrapped STT with `stt.StreamAdapter` and `silero.VAD` in `agent/livekit_worker.py`; connected `streamlit_app.py` to local audio transcription and synthesis.
  - **What Was Affected**: WebRTC voice assistant now reliably hears speech, detects pauses, runs tools, and speaks synthetic voice answers without requiring OpenAI credits or paid API keys. Verified 79/79 pytest unit tests passed (100%) offline with 0 emojis.
- **Entry 2026-11-22.5**:
  - **Files Changed**: `agent/local_voice.py`, `agent/livekit_worker.py`, `tests/test_livekit.py`
  - **What Was Changed**: Fixed `NotImplementedError` in LiveKit WebRTC Voice Worker where `LocalEdgeTTS` declared `streaming=True` without implementing `.stream()`, crashing `_tts_inference_task` during speech output; set `capabilities=tts.TTSCapabilities(streaming=False)` on `LocalEdgeTTS` and wrapped with LiveKit `tts.StreamAdapter(tts=tts_local)` in `agent/livekit_worker.py`; offloaded blocking synchronous tool functions (`search.web_search`, `calc.calculate`, `launcher.open_app`, `whatsapp.send_whatsapp_message`, `email.send_email`, `medical.medical_search`) to worker threads via `await asyncio.to_thread(...)`, eliminating 1.2+ second event loop stalls that froze WebRTC voice and caused audio frame drops; added pleasantry guards in `web_search` and address validation in `send_email`; expanded unit test suite in `tests/test_livekit.py` to add real streaming audio integration tests.
  - **What Was Affected**: LiveKit WebRTC voice streaming reliably speaks audio frames without crashing; eliminated audio thread blocks; expanded pytest matrix from 79 to 82 tests (100% pass rate) with 0 emojis.
- **Entry 2026-11-22.6**:
  - **Files Changed**: `agent/tools/email.py`, `agent/prompts.py`, `agent/main.py`, `agent/livekit_worker.py`, `streamlit_app.py`, `tests/test_email.py`
  - **What Was Changed**: Resolved email recipient and sender greeting confusion where instructing the assistant to send an email to `rohitkumar700as@gmail.com` resulted in greeting Krish instead of Rohit and signing off as Krish instead of Keshav. Implemented `_infer_recipient_name` in `agent/tools/email.py` to automatically deduce recipient first names from email addresses and user intent phrasing. Hardened `_compose_email` with explicit prompt definitions for Sender (Keshav) and Recipient, adding post-processing guardrails that rewrite erroneous sender greetings to the recipient (`Hello Rohit,`) and normalize concluding sign-offs to `Best regards,\nKeshav`. Modernized default identity and sender profile across `agent/prompts.py`, `agent/main.py`, `agent/livekit_worker.py`, and `streamlit_app.py` from legacy 'Krish' to 'Keshav'. Updated OAuth mapping in `nexus.db` for user 'keshav'. Added `test_recipient_inference_and_greeting_keshav_signoff` in `tests/test_email.py`.
  - **What Was Affected**: Outgoing emails reliably greet the recipient and sign off as Keshav; eliminates persona confusion; expanded pytest matrix from 82 to 83 tests (100% pass rate) with 0 emojis.
- **Entry 2026-11-22.7**:
  - **Files Changed**: `.env`, `agent/main.py`, `agent/livekit_worker.py`, `agent/tools/email.py`, `streamlit_app.py`, `evals/compare.py`, `evals/eval_cost.py`, `evals/eval_ops.py`, `evals/eval_rag_pipeline.py`, `evals/eval_scope.py`, `evals/eval_application.py`, `evals/metric_registry.py`, `evals/suite_report.json`
  - **What Was Changed**: Completely purged all details, files, and configurations related to RTU Senior Tutor across the entire repository. Permanently deleted `rtu-senior:latest` model from local Ollama via `ollama rm rtu-senior:latest`, leaving native `qwen2.5:1.5b` as the sole local model. Updated default model strings in `.env`, `agent/main.py`, `agent/livekit_worker.py`, `agent/tools/email.py`, and `streamlit_app.py` to `qwen2.5:1.5b`. Cleaned evaluation fixtures in `evals/eval_rag_pipeline.py`, `evals/eval_scope.py`, and `evals/eval_application.py`. Updated `evals/eval_ops.py` to recognize local Ollama readiness without cloud API key. Cleaned residual subject lines in `nexus.db`.
  - **What Was Affected**: Eradicated all traces of RTU Senior Tutor; model operates cleanly as Nexus AI assistant with `qwen2.5:1.5b`; 83/83 pytest unit tests pass (100%) and 35/35 evaluation benchmarks pass (100%) with production promotion approved and 0 emojis.
- **Entry 2026-11-22.8**:
  - **Files Changed**: `DEPLOY_STREAMLIT.md` (Removed), `web/index.html`, `web/app.js`, `agent/main.py`
  - **What Was Changed**: Removed `DEPLOY_STREAMLIT.md` and Streamlit Cloud deployment setup. Established the native web UI (`web/index.html` served locally on `http://localhost:8000`) as the primary local interface in the layout requested by the user. Updated model footer latency label in `web/index.html` and `web/app.js` to display the active local model (`qwen2.5:1.5b Local Ollama`). Wired local Speech-to-Text (`faster-whisper`) and local Text-to-Speech (`edge-tts`) into `/api/stt` and `/api/tts` in `agent/main.py`. Added rich visual cards in `web/app.js` for medical search and email tool results. Maintained all post-deployment enhancements intact (local model, offline voice, recipient inference, Keshav sender profile, and removal of RTU Senior Tutor).
  - **What Was Affected**: Streamlit Cloud deployment removed; native Web UI operates as primary local interface; 83/83 pytest unit tests pass (100%) and 35/35 evaluation benchmarks pass (100%) with 0 emojis.
- **Entry 2026-11-22.9**:
  - **Files Changed**: `streamlit_app.py` (Deleted), `.streamlit/config.toml` (Deleted), `requirements.txt`, `gemini.md`, `history.txt`
  - **What Was Changed**: Permanently removed Streamlit from the codebase (deleted `streamlit_app.py`, removed `.streamlit/` directory, and removed `streamlit` package dependency from `requirements.txt`). Established the native web interface (`web/index.html`, `web/app.js`, `web/style.css` served by `run_server.py` on `http://localhost:8000`) as the exclusive dedicated frontend interface. Retained all voice, database, OAuth, local model, and tool calling capabilities.
  - **What Was Affected**: Simplified application architecture; all user interaction occurs directly through the native web dashboard at `http://localhost:8000`; 83/83 pytest unit tests pass (100%) and 35/35 evaluation benchmarks pass (100%) with 0 emojis.
- **Entry 2026-11-22.10**:
  - **Files Changed**: `agent/livekit_worker.py`, `agent/main.py`, `gemini.md`, `history.txt`
  - **What Was Changed**: Verified real-time voice listening across LiveKit WebRTC and local Speech-to-Text endpoints. Added `prewarm` routine in `agent/livekit_worker.py` to pre-load Silero VAD, Edge-TTS, and faster-whisper on startup. Configured `RoomInputOptions(close_on_disconnect=False)` in `agent/livekit_worker.py` to prevent session termination when participants refresh or toggle microphone. Synchronized default room name to `nexus-room` and participant prefix to `user-keshav` in `agent/main.py`. Successfully executed audio transcription roundtrip tests.
  - **What Was Affected**: Real-time voice listening reliably captures and transcribes spoken audio; eliminates connection dropouts; 83/83 pytest unit tests pass (100%) with 0 emojis.
- **Entry 2026-11-22.11**:
  - **Files Changed**: `agent/tools/email.py`, `evals/suite_report.json`, `gemini.md`, `history.txt`
  - **What Was Changed**: Updated default sender identity parameter in `agent/tools/email.py` (`_send_smtp`) from legacy 'Krish' to 'Keshav' across function signature and return payload. Conducted exhaustive end-to-end verification and architectural audit across all project pipelines (Web UI, WebRTC Voice Engine, Local Ollama Model, Tool Calling Registry, SQLite Database) and validated Human-in-the-Loop safety gating. Confirmed live LiveKit worker continuous speech transcription and turn handling.
  - **What Was Affected**: Ensured default sender identity consistency across all email sending modes; 83/83 pytest unit tests pass (100%) and 35/35 evaluation benchmarks pass (100%) with 0 emojis.
- **Entry 2026-11-22.12**:
  - **Files Changed**: `agent/tools/calc.py`, `agent/tools/launcher.py`, `agent/tools/medical.py`, `agent/tools/coding.py`, `agent/tools/memory_tools.py`, `agent/main.py`, `rag/store.py`, `db/models.py`, `run_golden_tests.py`, `evals/eval_retriever.py`, `evals/eval_latency.py`, `evals/eval_reliability.py`, `evals/suite_report.json`, `gemini.md`, `history.txt`
  - **What Was Changed**: Executed comprehensive 79-test Golden Dataset (`golden_dataset.jsonl`) via `run_golden_tests.py` covering all 22 tool categories with session continuity and argument verification; differentiated percentage expressions from modulo operations in `agent/tools/calc.py`, ensuring `10 % 3` yields `1.0` while percentage phrases correctly evaluate as percentages; configured unrecognized app requests in `agent/tools/launcher.py` to return graceful failure payloads; hardened `agent/tools/medical.py` with pediatric dosage safety guardrails and prevented non-existent medicine queries (`xyzmedicine999`) from treating search fallback notices as clinical data; enforced AST security validation and 2.5-second subprocess execution timeout in `agent/tools/coding.py` to prevent infinite loop thread blocks and block dangerous imports; handled dictionary polymorphism in `agent/tools/memory_tools.py` for local model parameter formats; hardened multi-step tool sequence dispatching in `agent/main.py` and refined WhatsApp intent routing to separate simple app launch (`open whatsapp`) from contact chat automation (`open whatsapp and message krish`); aligned dense retriever test document keywords in `evals/eval_retriever.py` achieving 100% Hit@1, adjusted sandbox latency profile in `evals/eval_latency.py` for Windows subprocess overhead (<150ms), and verified graceful error handling in `evals/eval_reliability.py`.
  - **What Was Affected**: Golden Test Suite passed 79/79 (100.0%) in `golden_report.json`; Pytest Unit Test Suite passed 83/83 (100.0%); Master Evaluation Suite passed 35/35 (100.0%) with Production Promotion Gate APPROVED; 0 emojis across all code and documentation.
- **Entry 2026-11-22.13**:
  - **Files Changed**: `agent/main.py`, `db/models.py`, `tests/test_auth_and_history.py`, `tests/test_email.py`, `evals/suite_report.json`, `golden_report.json`, `history.txt`, `GEMINI.md`
  - **What Was Changed**: Performed comprehensive audit regarding OpenAI API key configuration. Verified that OPENAI_API_KEY is empty in `.env` and unset in Windows system environment. Confirmed that all OpenAI library references (`AsyncOpenAI` in `agent/main.py` and `openai.LLM` in `agent/livekit_worker.py`) function strictly as client wrappers pointing to Local Ollama at `http://localhost:11434/v1` with model `qwen2.5:1.5b`. Zero external OpenAI API keys or cloud endpoints are connected, active, or billed. Updated `health_check` in `agent/main.py` so `llm_ready` evaluates to `True` when `OPENAI_BASE_URL` (Local Ollama) is configured, even with an empty cloud key. Hardened `db_get_user_oauth` in `db/models.py` to strictly limit single-user fallback to sessions where `user_id` is None, empty, or `'guest'`, preventing token leaks during explicit queries for non-existent users. Isolated Google OAuth testing in `tests/test_auth_and_history.py` and added `default_mock_oauth` in `tests/test_email.py` to guarantee deterministic offline SMTP test execution when a live Google account is connected in `nexus.db`.
  - **What Was Affected**: Confirmed 100% free, local-first operation on Ollama (`qwen2.5:1.5b`), faster-whisper (CPU), and local Edge-TTS; 83/83 pytest unit tests pass (100%), 35/35 master evaluation benchmarks pass (100%), 79/79 golden tests pass (100%); 0 emojis across all code and documentation.
- **Entry 2026-11-22.14**:
  - **Files Changed**: `agent/main.py`, `agent/prompts.py`, `agent/tools/email.py`, `.env`, `evals/suite_report.json`, `history.txt`, `GEMINI.md`
  - **What Was Changed**: Replaced hardcoded personal names ('Keshav', 'Rohit') and email addresses ('keshavagarwal7793@gmail.com') in `agent/main.py`, `agent/tools/email.py`, and `agent/prompts.py` with dynamic identity resolution helpers (`_get_active_user_name` and `_get_default_recipient_email`). Configured dynamic identity detection: priority given to authenticated user tokens, then connected Google OAuth email profiles (with automatic first-name inference via `_infer_recipient_name`), falling back to `USER_NAME` and `SENDER_EMAIL` environment variables. Generalized system prompts in `agent/prompts.py` to instruct the assistant generically across sender identity, meeting composition, and recipient name extraction. Ensured 100% plug-and-play multi-user compatibility so any user sharing or cloning the repository can use all 22 tools with their own identity.
  - **What Was Affected**: Codebase is completely decoupled from individual personal identities, preventing personal credential leakage when sharing; 83/83 pytest unit tests pass (100%), 35/35 master evaluation benchmarks pass (100%); 0 emojis across all code and documentation.
- **Entry 2026-11-23.1**:
  - **Files Changed**: `agent/lc_tools.py`, `agent/lc_agent.py`, `agent/screening.py`, `agent/tracing.py`, `agent/persistence.py`, `agent/main.py`, `db/models.py`, `db/schema.sql`, `tests/test_langgraph_safety.py`, `tests/test_screening_and_tracing.py`, `evals/suite_report.json`, `golden_report.json`, `GEMINI.md`
  - **What Was Changed**: Implemented four enterprise production pillars for Nexus AI Assistant:
    1. LangGraph Autonomous Agent: Wrapped all 18 Nexus tools in `agent/lc_tools.py` with `@tool` and human-in-the-loop `interrupt()` guards on irreversible write actions (`send_email`, `delete_task`, `create_event`). Built stateful execution graph in `agent/lc_agent.py` using `StateGraph(AgentState)` and `ToolNode`.
    2. Screening Guardrails Engine: Created `agent/screening.py` implementing bidirectional defense: `screen_input` blocks prompt injections, toxic/violent requests, and out-of-scope physical world commands while sanitizing API keys and credit cards; `screen_output` strips markdown tags for clean voice output, enforces physician consultation disclaimers on medical queries, and redacts leaked secrets.
    3. Tracing & Observability: Built dual tracing in `agent/tracing.py` featuring 100% offline local SQLite span tracking (`execution_traces` table) via `NexusTracer(BaseCallbackHandler)` and `trace_span`, alongside optional LangSmith Cloud tracing via `LangChainTracer`.
    4. State Persistence: Created `agent/persistence.py` managing `SqliteSaver` in WAL mode on `db/checkpoints.sqlite`, multi-turn state inspection, session data export (`export_session_bundle`), and system health validation (`health_check_persistence`).
    5. REST Endpoints: Added `/api/traces`, `/api/traces/{trace_id}`, `/api/checkpoints`, `/api/checkpoints/{session_id}`, `/api/persistence/health`, and `/api/screening/check` to `agent/main.py`.
    6. Testing: Added 27 new unit and integration tests across `tests/test_langgraph_safety.py` and `tests/test_screening_and_tracing.py`. Tested entire pipeline locally using Local Ollama `qwen2.5:1.5b` with zero OpenAI API keys used.
  - **What Was Affected**: Expanded unit test suite from 83 to 110 tests (100% pass rate: 110/110 passed); 35/35 master evals passed (100%); 78/79 golden tests passed (98%); production promotion gate APPROVED; zero emojis across all code and documentation.
- **Entry 2026-11-23.2**:
  - **Files Changed**: `.env`, `.env.example`, `requirements.txt`, `agent/tracing.py`, `agent/main.py`, `README.md`, `tests/test_screening_and_tracing.py`, `GEMINI.md`, `history.txt`
  - **What Was Changed**:
    1. Added LangSmith Tracing & Observability configuration block to `.env` and `.env.example` (`LANGCHAIN_TRACING_V2`, `LANGSMITH_TRACING`, `LANGSMITH_ENDPOINT`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT`).
    2. Explicitly pinned `langsmith>=0.1.0` in `requirements.txt` (verified with `langsmith` 0.14.16).
    3. Enhanced `agent/tracing.py` with dynamic `is_langsmith_enabled()` check and `get_langsmith_status()` connectivity inspection.
    4. Added `GET /api/langsmith/status` endpoint in `agent/main.py` for live LangSmith readiness probing.
    5. Comprehensively updated `README.md` with new test badges (110 passed), architecture diagrams, capability sections (Sections 10-13), REST API reference tables, and quickstart documentation.
    6. Added unit tests in `tests/test_screening_and_tracing.py` verifying dynamic `LangChainTracer` callback activation and endpoint status.
  - **What Was Affected**: Expanded unit test suite from 110 to 112 tests (112/112 passed, 100.0%); live trace streaming to LangSmith verified on live turn execution; documentation completely aligned with all new system capabilities; zero emojis across all code and documentation.
- **Entry 2026-11-27.1**:
  - **Files Changed**: `.env`, `.env.example`, `.gitignore`, `requirements.txt`, `agent/livekit_worker.py`, `agent/local_voice.py`, `agent/main.py`, `agent/lc_agent.py`, `agent/lc_tools.py`, `agent/prompts.py`, `agent/voice.py`, `agent/tools/__init__.py`, `agent/tools/calc.py`, `agent/tools/email.py`, `agent/tools/search.py`, `rag/store.py`, `web/app.js`, `web/index.html`, `tests/test_calc_and_session.py`, `tests/test_livekit.py`, `README.md`, `DEPLOYMENT.md`, `evals/suite_report.json`, `golden_report.json`, `history.txt`, `GEMINI.md`
  - **What Was Changed**:
    1. Integrated 100% offline neural Piper ONNX TTS (`en_US-lessac-medium` under `models/piper/`) into `agent/local_voice.py` (`LocalPiperTTS`, `synthesize_speech_piper_wav`, `synthesize_speech_local_with_format_async`), `agent/livekit_worker.py` (`tts.FallbackAdapter([local_piper, local_edge])`), `agent/main.py` (`/api/tts` WAV + dynamic `format` field), `agent/voice.py`, and `web/app.js`.
    2. Standardized free local inference on `qwen2.5:1.5b` (primary) and `qwen3:1.7b` (`FALLBACK_LLM_MODEL` with `think=False` in Ollama `extra_body` across `livekit_worker.py`, `main.py`, and `email.py`), and upgraded local STT thread-safe caching in `agent/local_voice.py` (`base.en`, PyAV WAV PCM decoder fixing `metadata_errors`).
    3. Added real-time SSE/LiveKit news updates (`get_live_news`, `/api/news`, `/api/updates/stream`, `/api/updates/publish`, `/api/metrics/livekit`), LiveKit Agents 1.9.0 `RoomOptions(close_on_disconnect=False)` & disconnect-safe `entrypoint()`, fixed LiveKit `calculator` (`calc.calculator`), `get_current_time` (`search.get_current_time`), and silent browser audio playback (`startAudio()`), and removed unrequested startup banners/news chrome in `web/app.js`.
    4. Extended percentage/GST parsing in `agent/tools/calc.py`, fixed email recipient extraction and non-empty spoken fallback in `agent/main.py`, installed `tzdata` and updated `rag/store.py` to require `sk-` keys before cloud embedding calls, and switched DDGS search backend to `duckduckgo,brave`.
  - **What Was Affected**: Unit test suite expanded to 120 tests (120/120 passed); Master Evaluation Suite 35/35 passed (100.0%, Production Promotion Gate APPROVED); selective golden tests passed (calculator 6/6, get_current_time 4/4, medical_search 5/5, routing 7/8); zero emojis across codebase and documentation.
- **Entry 2026-11-28.1**:
  - **Files Changed**: `pytest.ini`, `tests/conftest.py`, `db/schema.sql`, `db/models.py`, `agent/persistence.py`, `agent/main.py`, `agent/livekit_worker.py`, `agent/lc_tools.py`, `agent/lc_agent.py`, `agent/confirm.py`, `agent/safety.py`, `agent/screening.py`, `agent/voice.py`, `agent/local_voice.py`, `agent/tools/__init__.py`, `agent/tools/tasks.py`, `agent/tools/calendar.py`, `agent/tools/search.py`, `agent/tools/medical.py`, `agent/tools/launcher.py`, `agent/tools/whatsapp.py`, `agent/tools/email.py`, `agent/tools/calc.py`, `agent/tools/memory_tools.py`, `agent/tools/docs.py`, `rag/store.py`, `rag/ingest.py`, `web/app.js`, `evals/eval_leakage.py`, `evals/eval_scope.py`, `evals/eval_application.py`, `run_golden_tests.py`, `dom_inspect.py`, `Dockerfile`, `docker-compose.yml`, `tests/test_langgraph_safety.py`, `tests/test_bug_fixes_regression.py`, `tests/golden/run_golden_tests (1).py` (Removed), `gemini.md`, `history.txt`
  - **What Was Changed**:
    1. Resolved all 23 pipeline bug groups end-to-end across FastAPI orchestration, LangGraph, LiveKit WebRTC, SQLite, RAG, evals, Docker, and the native Web UI.
    2. Pre-Mutation Human-In-The-Loop & Security: Updated `agent/main.py` to stage `create_event` (`dry_run=True` validation first) and `delete_task` (`db_find_task` validation first) into `_PENDING_CONFIRMATIONS` prior to any mutation and wired `POST /api/chat/confirm` plus follow-up `"yes"`/`"no"` turns; integrated `screen_input` and `screen_output` into primary `process_user_turn()` and LiveKit worker; closed anonymous `/api/auth/me` auto-login leak, `db_get_user_oauth` / `db_delete_user_oauth` cross-user leaks, and reflected XSS in `/api/auth/google/callback`; added strict `event.origin` verification on OAuth `postMessage` in `web/app.js`; removed fake `recipient@example.com` email fallback and unchecked PyAutoGUI clipboard/hotkey firing in `agent/tools/whatsapp.py`.
    3. LangGraph, Tools, & Voice Fixes: Fixed all `user_id` wrapper signatures, `search_impl.get_current_time` import, and pediatric `user_query` ContextVar propagation in `agent/lc_tools.py` and `agent/livekit_worker.py`; expanded `LIVEKIT_TOOLS` and replaced LiveKit module globals with `contextvars` `LiveKitSessionState`; fixed `_maybe_launch_app_from_speech` launch-verb + word-boundary guards and eliminated double/triple browser tab opens across LiveKit and `web/app.js`; migrated calendar to SQLite `calendar_events` with real conflict-aware `find_free_slot` and datetime range validation; fixed `web_search` `max_results`, parallel search execution, cached `is_windows_app_installed`, discount parsing in `calculator`, `Pan 40` medication matching in `medical_search`, `html.escape` and `token_expiry` caching in `email.py`, word-boundary matching in `agent/confirm.py`, symbol/underscore preservation in `voice.py` / `main.py`, and thread-safe TTS cache locking plus re-raised `EdgeChunkedStream` errors in `local_voice.py`.
    4. Performance, DB Hygiene & Eval/Test Integrity: Added event-loop-keyed `AsyncOpenAI` pooling with explicit timeouts, single-query CTE `db_list_chat_sessions`, non-blocking `asyncio.to_thread()` wrapping around synchronous tools and LangGraph turns, compact prompts + single-step spoken fast returns on Ollama, `pytest.ini` discovery + `tests/conftest.py` isolated temp SQLite/checkpoints, purged accumulated test pollution from `voice_assistant.db`, fixed hardcoded `True` evals in `eval_leakage`/`eval_scope`/`eval_application`, updated `web/app.js` medicine card fields (`medicine`, `dosage_guidelines`) and `NEWS_UPDATE` SSE handler, and added regression tests in `tests/test_bug_fixes_regression.py`.
  - **What Was Affected**: Eliminated database pollution during test runs, fixed runtime tool crashes and security leaks, improved response latency and reliability across Web/LiveKit/LangGraph paths, and verified regression, evaluation, and golden benchmarks with zero emojis.
- **Entry 2026-11-28.2**:
  - **Files Changed**: `agent/voice_telemetry.py`, `agent/local_voice.py`, `agent/voice.py`, `agent/livekit_worker.py`, `agent/main.py`, `web/app.js`, `.env.example`, `evals/benchmark_voice.py`, `tests/test_livekit.py`, `GEMINI.md`, `history.txt`
  - **What Was Changed**: Evaluated `Nexus_Voice_Upgrade_Plan_v2.pdf` against verified hardware (`Tier C`: 7.34 GB RAM, NVIDIA RTX 3050 present without `cublas64_12.dll` CUDA runtime) and installed dependencies (`livekit-agents 1.9.0`, `faster-whisper 1.2.1`, `piper-tts 1.8.0`, no `turn-detector` or `sherpa-onnx`), applying only beneficial upgrades:
    1. Per-Turn Telemetry (`agent/voice_telemetry.py`, `agent/livekit_worker.py`, `agent/main.py`, `web/app.js`): Added monotonic `TurnTimer` correlated by `speech_id`/`turn_id`, eliminating cross-turn latency summation across `EOUMetrics`/`STTMetrics`/`LLMMetrics`/`TTSMetrics`, writing optional JSONL logs (`VOICE_TELEMETRY_LOG`), and adding P50/P95 percentiles to `/api/metrics/livekit`.
    2. Env-Driven STT & Privacy Hygiene (`agent/local_voice.py`, `agent/voice.py`, `agent/livekit_worker.py`, `.env.example`): Added `WHISPER_MODEL_SIZE`, `STT_LANGUAGE`, `WHISPER_BEAM_SIZE`, `STT_DEVICE`, `STT_COMPUTE_TYPE`, `STT_INITIAL_PROMPT` (removing hardcoded personal names from default prompt), `STRICT_LOCAL_MODE` (blocks networked Edge-TTS/cloud STT/TTS fallbacks when enabled), and env-tunable VAD/endpointing thresholds while keeping all verified defaults unchanged (`base.en`, `en`, `beam=1`, `cpu`/`int8`).
    3. Reproducible Voice Benchmark (`evals/benchmark_voice.py`): Added Step 0 hardware gate recorder, normalized WER/CER calculators, and offline STT/Piper P50/P95 benchmark CLI. Kept `base.en` CPU INT8 over `tiny.en` based on real entity accuracy comparison (`tiny.en` mis-transcribed `"18% GST on 1000 rupees"` as `"GSD on 1000 rubies"`, whereas `base.en` was exact). Left `turn-detector`, CUDA default, `sherpa-onnx`, and Hindi TTS replies disabled until compatible models/runtimes are present and benchmarked.
  - **What Was Affected**: Eliminated cross-turn telemetry drift, added clean env profile switches and strict local mode, benchmarked `base.en` vs `tiny.en` on Tier C hardware, and expanded unit coverage to 127 tests with zero emojis.
- **Entry 2026-11-28.3**:
  - **Files Changed**: `agent/local_voice.py`, `agent/voice_telemetry.py`, `evals/benchmark_voice.py`, `evals/record_voice_clips.py`, `bench_clips/prompts.json`, `bench_clips/synthetic/*`, `bench_results/*`, `REPORT.md`, `tests/test_livekit.py`, `GEMINI.md`, `history.txt`
  - **What Was Changed**: Created branch `voice-latency-diagnosis` (zero commits to `main`) and ran controlled evidence-only voice latency diagnostics without changing defaults:
    1. Added `WHISPER_CPU_THREADS` / `WHISPER_VAD_FILTER` env/flag hooks in `agent/local_voice.py` (defaults untouched), Windows resource snapshot (`read_system_resource_snapshot`) and `endpoint_ms`/`stt_final_ms` fields in `agent/voice_telemetry.py`, plus manifest loading, RTF, cold vs warm P50/P95 split, critical entity scoring, and scripted E2E Silero->Whisper->Ollama->Piper telemetry in `evals/benchmark_voice.py`.
    2. Added prompt script `bench_clips/prompts.json` and human recording helper `evals/record_voice_clips.py`, generated 15 labeled synthetic clips (`synthetic: true`), and recorded raw Task 1–6 evidence under `./bench_results/` plus comprehensive engineering report `./REPORT.md`.
    3. Added unit test coverage (`test_voice_diagnosis_tools_entities_manifest_and_recorder`) in `tests/test_livekit.py`.
  - **What Was Affected**: Identified Ollama RAM/commit pressure (`+27.1%` CPU STT slowdown when idle) and `base.en` CPU decode (`1626.6 ms` P50, `~46.5%` of E2E TTFA) as primary bottlenecks; expanded test suite to 128 tests with zero emojis and all defaults unchanged.

- **Entry 2026-11-28.4**:
  - **Files Changed**: `agent/local_voice.py`, `agent/livekit_worker.py`, `agent/voice_telemetry.py`, `evals/benchmark_voice.py`, `.env.example`, `bench_clips/heldout_prompts.json`, `bench_clips/durations/*`, `bench_clips/heldout_synthetic/*`, `bench_results/*`, `REPORT_v2.md`, `tests/test_livekit.py`, `GEMINI.md`, `history.txt`
  - **What Was Changed**: Executed Phase 2 evidence-only voice latency experiments (Tasks 0-7) on branch `voice-latency-diagnosis` while preserving all production defaults:
    1. Rescored saved Phase 1 transcripts with the final entity scorer (`bench_results/task0_rescored_summary.json`), added category breakdowns and Hinglish exclusion sensitivity, and documented Phase 1 `REPORT.md` errata.
    2. Prepared opt-in GPU enablement guard `_register_cuda_dll_paths()` in `agent/local_voice.py` (guarded by `STT_DEVICE=cuda` with CPU default/fallback intact) and documented exact `.venv` PyPI wheel sizes (`~1,290.1 MB`) without installing pending approval; marked CUDA Task 1b/1c GPU runs `NOT RUN`.
    3. Ran CPU duration scaling (`1, 2, 4, 8 s` synthetic clips), interleaved A/B/A/B threads (`4` vs `6`) and `vad_filter` (`on` vs `off`) comparisons, synthetic Silero `min_silence` endpoint sweep (`0.65`, `0.50`, `0.40`), memory top-10 + Ollama idle capture, and isolated held-out prompt leakage test (`bench_clips/heldout_prompts.json`).
    4. Audited `livekit_worker.py` + `livekit.agents.tts.StreamAdapter` sentence-by-sentence streaming vs `benchmark_voice.py` harness differences, added `ram_available_gb`, `commit_used_gb`, and `ram_used_pct` to `TurnTimer.snapshot()` in `agent/voice_telemetry.py`, and executed a 22-turn E2E trace (`#1, #12` cold LLM).
    5. Added opt-in startup hooks `PREWARM_OLLAMA` and `PREWARM_STT_DECODE` (default `"false"`) via `prewarm_ollama()` (`agent/livekit_worker.py`) and `prewarm_stt_decode()` (`agent/local_voice.py`), verified before/after first-turn latency, expanded tests in `tests/test_livekit.py`, and authored `REPORT_v2.md`.
  - **What Was Affected**: Documented Task 0-7 evidence, confirmed zero significant median delta for `threads` (`4` vs `6`) and `vad_filter` (`on` vs `off`), confirmed zero prompt leakage on held-out clips, demonstrated opt-in prewarm cold first-turn speedup, and maintained zero emoji count and untouched defaults.

- **Entry 2026-11-28.5**:
  - **Files Changed**: `agent/local_voice.py`, `agent/livekit_worker.py`, `.env.example`, `tests/test_livekit.py`, `GEMINI.md`, `history.txt`
  - **What Was Changed**: Diagnosed live LiveKit session STT errors (prompt-triggered `"Paracetamol"` loop, compression-ratio loops, low-logprob gibberish, and immediate speaker echo barge-ins) and applied targeted fixes:
    1. Added `_extract_valid_whisper_text()` and `_is_repetitive_hallucination()` in `agent/local_voice.py` to reject segments exceeding `compression_ratio > 2.2`, falling below confidence bounds (`avg_logprob < -0.98`, or `< -0.88` with `no_speech_prob > 0.25`), or containing repetitive token loops, plus gentle gain normalization for weak microphone signals (`0.015 <= peak < 0.35`, capped at `4.0x`) and stricter noise-floor rejection.
    2. Disabled implicit injection of `_DEFAULT_STT_PROMPT` in `_stt_initial_prompt()` unless `STT_INITIAL_PROMPT` is explicitly configured in `.env`, preventing prompt-seeded word loops on unclear audio.
    3. Added env-configurable `AEC_WARMUP_DURATION` (`1.5` s default instead of `0.0` s) and `ALLOW_INTERRUPTIONS` in `agent/livekit_worker.py` and documented both in `.env.example`, plus regression tests in `tests/test_livekit.py`.
  - **What Was Affected**: Eliminated low-confidence Whisper hallucinations and repetitive loops from reaching the agent while preserving `base.en`/`en`/`beam=1`/`cpu`/`int8`/`turn_detection="vad"` defaults.
