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
- **Role**: Launches the central FastAPI REST & WebSocket backend service.
- **Execution Command**:
  ```bash
  backend\.venv\Scripts\python.exe run_server.py
  ```
- **Inputs**: Reads environment variables from `.env` (`OPENAI_API_KEY`, `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`).
- **Outputs**: Binds Uvicorn HTTP server to `http://127.0.0.1:8000`. Serves REST endpoints (`/api/chat`, `/api/livekit/token`, `/api/auth/google/callback`, `/api/history`) and WebSockets (`/ws/voice/{session_id}`).
- **End-to-End Use Case**: Serves as the primary API gateway for client frontends, orchestrates LLM chat turns, executes tool calling, handles Google OAuth callbacks, and issues LiveKit access tokens.

### 1.2 `run_livekit.py`
- **Path**: `run_livekit.py`
- **Role**: Starts the real-time LiveKit WebRTC Voice Pipeline Worker.
- **Execution Command**:
  ```bash
  backend\.venv\Scripts\python.exe run_livekit.py dev
  ```
- **Inputs**: LiveKit Cloud credentials (`LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`) and OpenAI API key (`OPENAI_API_KEY`).
- **Outputs**: Establishes a persistent worker connection to LiveKit Cloud (`wss://nexus-ai-assistant-awu0v1ts.livekit.cloud`).
- **End-to-End Use Case**: Subscribes to audio rooms created by web or Streamlit clients, streams bidirectional voice via WebRTC, runs local Silero VAD to detect pauses in speech, feeds transcribed audio to OpenAI, executes registered Python tools, and streams synthetic voice responses back with sub-400ms turnaround.

### 1.3 `streamlit_app.py`
- **Path**: `streamlit_app.py`
- **Role**: Production ChatGPT-style executive web interface with integrated LiveKit WebRTC Voice Studio.
- **Execution Command**:
  ```bash
  backend\.venv\Scripts\streamlit.exe run streamlit_app.py --server.port 8501
  ```
- **Inputs**: User text input via chat capsule, voice audio via embedded LiveKit WebRTC component, model engine selection (Cloud GPT-4o vs Local Ollama), Google 1-Click Login button, and optional email profile settings.
- **Outputs**: Renders modern dark-mode web application at `http://localhost:8501`. Renders ChatGPT-style conversational history, tool execution cards (Web Search, Math, Medicine Information, Application Opening), real-time WebRTC audio waveform visualizer, and hands-free microphone controls.
- **End-to-End Use Case**: The primary graphical desktop interface for end-users to interact with the assistant via text and voice, manage their Google OAuth connection, view structured tool results, and review chat history.

### 1.4 `run_voice.py`
- **Path**: `run_voice.py`
- **Role**: Standalone local microphone and speaker audio loop runner.
- **Execution Command**:
  ```bash
  backend\.venv\Scripts\python.exe run_voice.py
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
  backend\.venv\Scripts\python.exe -m agent.cli
  ```
- **End-to-End Use Case**: Allows developers to test multi-turn conversations and tool calling directly in PowerShell without starting web servers.

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
  backend\.venv\Scripts\python.exe -m rag.ingest
  ```

### 5.2 `rag/store.py`
- **Path**: `rag/store.py`
- **Role**: In-memory vector store with cosine similarity matching and top-k nearest neighbor retrieval.
- **End-to-End Use Case**: Powers domain-specific RAG knowledge retrieval for university syllabi, documentation, and reference manuals.

---

## 6. Master Evaluation Suite (`evals/`)

The evaluation suite implements a 4-pillar, 35-benchmark testing framework:

### 6.1 `evals/run_suite.py`
- **Path**: `evals/run_suite.py`
- **Role**: Master evaluation orchestrator. Runs all 35 modular benchmarks and produces a production promotion verdict.
- **Execution Command**:
  ```bash
  backend\.venv\Scripts\python.exe -m evals.run_suite
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

---

## 7. Pytest Unit Test Matrix (`tests/`)

All 79 unit tests can be executed with a single command:
```bash
backend\.venv\Scripts\python.exe -m pytest tests/ -v
```

### 7.1 Test Suites Overview
- `tests/test_agent.py` (7 tests): Tests LangGraph agent workflow, approval gating, and tool dispatching.
- `tests/test_auth_and_history.py` (6 tests): Validates user registration, bcrypt password hashing, token validation, and chat history ordering.
- `tests/test_calc_and_session.py` (16 tests): Tests all calculator operations (addition, percentages, square roots, division, modulo, negative numbers) and session isolation.
- `tests/test_email.py` (21 tests): Comprehensive email test matrix covering Google OAuth priority, SMTP fallback, bulk CSV dispatch, and AI composition.
- `tests/test_launcher.py` (10 tests): Verifies app targets (YouTube, WhatsApp, LinkedIn, Spotify, GitHub, Gmail) and browser search query extraction.
- `tests/test_livekit.py` (4 tests): Tests LiveKit status endpoints, token generation, and tool binding.
- `tests/test_medical.py` (7 tests): Validates the new medical search tool across curated lookups, topic filtering (uses, dosage, side effects), empty query handling, and intent detection.
- `tests/test_voice.py` (4 tests): Tests clean spoken text formatting, silent audio transcription, and push-to-talk stop events.
- `tests/test_whatsapp.py` (4 tests): Tests contact search, phone number parsing, and WhatsApp Web message URL formation.
- `tests/verify_all_features.py`: Standalone 24-feature live verification matrix with detailed tabular reporting.

---

## 8. Web Frontend (`web/`)

### 8.1 `web/index.html`
- **Path**: `web/index.html`
- **Role**: Executive web interface layout built with clean black and white aesthetics, responsive sidebar, and chat canvas.

### 8.2 `web/app.js`
- **Path**: `web/app.js`
- **Role**: Client-side JavaScript controller. Manages WebRTC connection to LiveKit Cloud, renders animated audio waveforms during speech, displays action notification toasts, and maintains local chat history.

---

## 9. End-to-End Operational Lifecycle

1. **System Startup**:
   - `run_server.py` starts on port 8000 (FastAPI backend).
   - `run_livekit.py` connects to LiveKit Cloud WebRTC room.
   - `streamlit_app.py` starts on port 8501 (Streamlit executive UI).

2. **User Interaction**:
   - The user opens `http://localhost:8501`.
   - The user clicks `Login with Google` to connect their Gmail account via 1-click OAuth.
   - The user clicks `Start LiveKit Voice` and speaks: *"What is Dolo 650 used for?"*.
   - LiveKit WebRTC captures the audio stream, Silero VAD detects the pause, OpenAI transcribes the speech, and invokes `medical_search(medicine_name="Dolo 650", topic="uses")`.
   - The medical search engine retrieves the pharmacology profile from the curated clinical database and OpenFDA.
   - LiveKit streams the verbal answer directly into the user's headphones in sub-400ms.
   - Streamlit displays a structured Medicine Information card on screen.
   - The conversational turn is logged into SQLite with `ORDER BY created_at DESC, rowid DESC`.
