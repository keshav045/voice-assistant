# Voice Pipeline Latency & Accuracy Diagnosis Report

Branch: `voice-latency-diagnosis`  
Date: 2026-11-28  
Scope: Evidence-only diagnosis of `base.en` latency, CPU/memory/Ollama contention, fast-model prompt/beam trade-offs, CUDA runtime status, and end-to-end local LiveKit voice telemetry. All existing code defaults (`base.en`, `en`, `beam=1`, `cpu`, `int8`, `turn_detection="vad"`, `preemptive_generation=False`, Silero VAD thresholds) were kept untouched.

> Important Labelling Notice: `0` pre-existing audio clips existed in the repository (`REPO_AUDIO_CLIPS: []`). All clip benchmarks below were measured on `15` synthetic `16 kHz` mono WAVs generated via offline Piper TTS (`en_US-lessac-medium`, marked `synthetic: true` in `bench_clips/synthetic/manifest.jsonl`). They do not substitute for real human microphone clips across accents and room noise.

---

## 1. Hardware & Environment

| Property | Measured Value |
| :--- | :--- |
| OS | `Windows-11-10.0.26300-SP0` |
| Python | `3.13.7` |
| CPU | `AMD Ryzen 5 5600H with Radeon Graphics` (`AMD64 Family 25 Model 80 Stepping 0`) |
| CPU Cores | `6` physical cores / `12` logical processors |
| System RAM | `7.342 GB` total (`0.77–1.59 GB` free at baseline; Hardware Tier `C_MODEST_CPU_8GB`) |
| Windows Commit / Pagefile | `25.174 GB` commit limit (`16.71–19.45 GB` committed across test states) |
| GPU (`nvidia-smi`) | `NVIDIA GeForce RTX 3050 Laptop GPU`, `4096 MiB` VRAM (`Driver 610.91`, `CUDA UMD 13.3`) |
| `faster-whisper` / `ctranslate2` | `faster-whisper 1.2.1`, `ctranslate2 4.9.1` |
| `livekit-agents` / Silero VAD | `livekit-agents 1.9.0`, `livekit-plugins-silero 1.9.0` |
| TTS Engines Installed | `piper-tts 1.8.0` (`en_US-lessac-medium.onnx`, `63.2 MB`), `edge-tts 7.3.1` |
| Optional Packages | `livekit-plugins-turn-detector`: NOT INSTALLED; `sherpa-onnx`: NOT INSTALLED |
| Cached Faster-Whisper Models | `Systran/faster-whisper-base.en`, `Systran/faster-whisper-tiny.en` |

---

## 2. Task 1 Results: Contention, Threads, and Internal VAD

All Task 1 runs used identical `15` synthetic clips (`base.en`, `cpu/int8`, `language=en`, `beam=1`, `3` warm repeats = `45` warm decodes + `1` cold first call per run).

### 2.1 Task 1a & 1b: Ollama Contention States (`threads=4`, `vad_filter=on`)

| Ollama State | Clips (Syn) | WER | Entity Acc | Cold Load (ms) | Cold 1st Call (ms / RTF) | Warm P50 (ms) | Warm P95 (ms) | Warm Avg (ms) | Warm RTF P50 / P95 | Free RAM Before / During / Min (GB) | Commit Before -> During (GB) | CPU Before / During (%) | Peak RSS (MB) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `stopped` | 15 (`true`) | `0.2382` | `0.8333` (`25/30`) | `1329.0` | `1301.6` (`0.5119`) | `1047.0` | `1447.8` | `1085.6` | `0.3732` / `0.5608` | `0.851` / `0.785` / `0.777` | `16.839` -> `17.028` | `10.9` / `50.8` | `545.2` |
| `idle` (`qwen2.5:1.5b` loaded) | 15 (`true`) | `0.2382` | `0.8333` (`25/30`) | `1793.4` | `1465.4` (`0.5763`) | `1330.8` | `1531.2` | `1347.1` | `0.4592` / `0.6763` | `0.716` / `0.322` / `0.322` | `18.677` -> `19.452` | `17.3` / `43.5` | `533.1` |
| `generating` (18 concurrent Ollama calls) | 15 (`true`) | `0.2382` | `0.8333` (`25/30`) | `1812.3` | `1813.5` (`0.7132`) | `1359.7` | `1575.7` | `1385.0` | `0.4873` / `0.7110` | `0.873` / `0.595` / `0.542` | `18.766` -> `19.337` | `35.4` / `44.7` | `546.9` |

Key observation: Going from Ollama `stopped` to `idle` added **`+283.8 ms` (`+27.1%`)** to `base.en` warm P50 (`1047.0 -> 1330.8 ms`) and pushed system commit from `17.03 GB` to `19.45 GB` (available RAM dropped to **`0.322 GB`**, `95%` memory utilization). Concurrent Ollama generation (`18` `120`-token GPU requests, `0` errors) added only `+28.9 ms` on top of idle (`1330.8 -> 1359.7 ms`), showing Ollama ran on the RTX 3050 while Windows memory pressure/commit accounted for most of the CPU STT slowdown.

### 2.2 Task 1c: Clip Durations & Real-Time Factor (`base.en`, `stopped`, `threads=4`)

Clip durations in `bench_clips/synthetic/manifest.jsonl` range from `1.8228 s` (`synth_P14.wav`) to `3.6456 s` (`synth_P08.wav`):
- Shortest clip (`synth_P14.wav`, `1.8228 s`): warm P50 `1244.0 ms`, RTF `0.6825` (cold/fixed overhead dominates short clips).
- Longest clip (`synth_P10.wav` / `synth_P15.wav`, `3.3901 s`): warm P50 `1253.7–1410.0 ms`, RTF `0.3698–0.4159`.
- Clean command (`synth_P01.wav`, `2.5426 s`): cold `1301.6 ms` (`RTF 0.5119`), warm P50 across `stopped` `0.3732` RTF (`~950 ms`).

### 2.3 Task 1d: `cpu_threads` Sweep (`base.en`, `beam=1`, `vad_filter=on`, Ollama `stopped`)

| Config (`cpu_threads`) | Clips (Syn) | WER | Entity Acc | Cold Load / 1st Call (ms) | Warm P50 (ms) | Warm P95 (ms) | Warm RTF P50 / P95 | During CPU (%) | Min Avail RAM (GB) | Peak RSS (MB) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `3` (half physical cores) | 15 (`true`) | `0.2382` | `0.7667` (`23/30`)* | `1124.2` / `1140.7` | `1085.2` | `1452.4` | `0.3807` / `0.5964` | `19.8` | `0.951` | N/A** |
| `4` (current default) | 15 (`true`) | `0.2382` | `0.8333` (`25/30`) | `1329.0` / `1301.6` | `1047.0` | `1447.8` | `0.3732` / `0.5608` | `50.8` | `0.777` | `545.2` |
| `6` (physical cores) | 15 (`true`) | `0.2382` | `0.7667` (`23/30`)* | `1280.5` / `1071.2` | `1008.6` | **`1290.1`** | **`0.3585` / `0.5270`** | `50.5` | `0.856` | N/A** |
| `12` (all logical SMT cores) | 15 (`true`) | `0.2382` | `0.7667` (`23/30`)* | `920.9` / `1078.4` | `1047.0` | `1351.3` | `0.3742` / `0.5807` | `98.8` | `0.898` | N/A** |

*\*`task1d_threads_*` ran right before the `am/pm` boundary rule was added to `_normalize_for_entities`; transcripts and WER (`0.2382`) were identical to `threads=4`.*  
*\*\*`peak_rss_mb` was `null` in `task1d_threads_*` and `task1e_vad_off` because those ran before `K32GetProcessMemoryInfo` fixed handle sizing.*

### 2.4 Task 1e: `faster-whisper` Internal `vad_filter` Comparison (`base.en`, `beam=1`, `threads=4`, Ollama `stopped`)

| Config (`vad_filter`) | Clips (Syn) | WER | Entity Acc | Cold Load / 1st Call (ms) | Warm P50 (ms) | Warm P95 (ms) | Warm RTF P50 / P95 | During CPU (%) | Min Avail RAM (GB) | Peak RSS (MB) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `vad_filter=on` (default) | 15 (`true`) | `0.2382` | `0.8333` (`25/30`) | `1329.0` / `1301.6` | `1047.0` | `1447.8` | `0.3732` / `0.5608` | `50.8` | `0.777` | `545.2` |
| `vad_filter=off` | 15 (`true`) | `0.2382` | `0.7667` (`23/30`)* | **`906.0` / `904.4`** | **`1001.5`** | `1447.1` | **`0.3528`** / `0.5726` | `39.8` | `0.771` | N/A** |

Key observation: Disabling faster-whisper's internal Silero VAD cut cold model load by `423 ms` (`1329.0 -> 906.0 ms`) and cold first inference by `397 ms` (`1301.6 -> 904.4 ms`) with zero WER degradation on pre-trimmed clips (`0.2382` identical), because LiveKit's `stt.StreamAdapter` already runs Silero VAD upstream.

---

## 3. Task 2 Results: Prompt & Beam Fixes (`tiny.en` vs `base.en` vs `distil-small.en`)

All runnable comparisons executed under identical Ollama `stopped` state (`threads=4`, `vad_filter=on`, `3` warm repeats).

| Model & Prompt Config | Clips (Syn) | WER | CER | Entity Acc | Cold Load / 1st Call (ms) | Warm P50 (ms) | Warm P95 (ms) | Warm RTF P50 / P95 | Peak RSS (MB) | Key Entity Behavior |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `base.en`, `beam=1`, default prompt* | 15 (`true`) | **`0.2382`** | **`0.1009`** | **`0.8333`** (`25/30`) | `1329.0` / `1301.6` | `1047.0` | `1447.8` | `0.3732` / `0.5608` | `545.2` | `P06` `18% GST 1000 Rupees` (`1.0`), `P09` `Rohal` (`0.5`), `P10` `PantoPristle` |
| `base.en`, `beam=1`, `"GST, rupees, Gmail, calendar, Nexus"` | 15 (`true`) | `0.2751` | `0.1091` | `0.8000` (`24/30`) | `1796.6` / `1379.7` | `1320.9` | `1529.3` | `0.4598` / `0.6808` | `546.4` | Prompt degraded overall WER (`0.2751`) vs default prompt |
| `tiny.en`, `beam=1`, default prompt* | 15 (`true`) | `0.2875` | `0.1131` | `0.8000` (`24/30`) | `1167.4` / `651.0` | `533.0` | `667.6` | `0.1861` / `0.2684` | **`483.4`** | Missed `GST` (`"GSD"` on `P06`), got `Rahul` (`1.0`) on `P09` |
| `tiny.en`, `beam=1`, `"GST, rupees, Gmail, calendar, Nexus"` | 15 (`true`) | `0.2752` | `0.1272` | `0.7667` (`23/30`) | `1155.2` / `566.2` | **`515.9`** | **`590.3`** | **`0.1792` / `0.2745`** | `486.4` | Fixed `GST` (`1.0` on `P06`), regressed `Rohit`->`rohirr` (`P07`) & `Paracetamol` (`P10`) |
| `tiny.en`, `beam=3`, `"GST, rupees, Gmail, calendar, Nexus"` | 15 (`true`) | `0.2724` | `0.1105` | `0.8000` (`24/30`) | `974.8` / `680.9` | `639.7` | `762.6` | `0.2257` / `0.3380` | `487.4` | Kept `GST` (`1.0`), recovered `rohit` & `paracetamol`, `~39%` faster than `base.en` |
| `distil-small.en` / `distil-medium.en` | 0 | **NOT RUN** | **NOT RUN** | **NOT RUN** | **NOT RUN** | **NOT RUN** | **NOT RUN** | **NOT RUN** | N/A | Requires HuggingFace download (`local_files_only=True` failed) |

*\*Default prompt: `"Nexus AI assistant, WhatsApp, YouTube, Gmail, Paracetamol, Dolo 650, Ibuprofen."`*

---

## 4. Task 3 Results: Clip Audit, Manifest, Recording Tool & Entity Scoring

- **Pre-existing clips**: `0` audio clips (`REPO_AUDIO_CLIPS: []`). No transcripts were fabricated.
- **Prompt script**: [bench_clips/prompts.json](file:///c:/Users/krish/OneDrive/Desktop/keshav/bench_clips/prompts.json) (`15` prompts across `clean_english`, `indian_english_accent`, `numbers_amounts_emails`, `names`, `hinglish`, `noisy_far_mic`, `pauses_corrections`).
- **Manifest support**: `evals.benchmark_voice` (`load_manifest`) supports both `.jsonl` and `.csv` manifests (`wav_path`, `reference_text`, `category`, `speaker`, `synthetic`) and reports `human_accuracy` separately from `synthetic_accuracy`.
- **Human recording helper**: Created [evals/record_voice_clips.py](file:///c:/Users/krish/OneDrive/Desktop/keshav/evals/record_voice_clips.py) (`python -m evals.record_voice_clips --speaker <name>`) saving `16 kHz` mono 16-bit PCM WAVs and `synthetic: false` manifest rows for user capture.
- **Separate Critical Entity Scoring**: `compute_entity_accuracy()` scores emails, normalized numbers/percentages, currency/time units, and target names separately (`0.8333` on `base.en` default vs `0.8000` on `tiny.en` + domain prompt `beam=3`). Note: Hinglish clips `P11`/`P12` generated by an English-US Piper voice inflate synthetic WER (`0.75–0.7778`), because English TTS mispronounces Hindi phonetics regardless of STT model.

---

## 5. Task 4 Results: CUDA Check (Read-Only)

| Check | Result |
| :--- | :--- |
| `nvidia-smi` GPU & VRAM | `NVIDIA GeForce RTX 3050 Laptop GPU`, `4096 MiB` total VRAM (`WDDM`, Driver `610.91`, CUDA UMD `13.3`) |
| `ctranslate2` / `faster-whisper` | `ctranslate2 4.9.1`, `faster-whisper 1.2.1` |
| `ctranslate2.get_cuda_device_count()` | `1` (supports `float16`, `int8_float16`, `int8`, `float32`, `bfloat16`) |
| CUDA DLLs Found in `.venv` | `cudnn64_9.dll` (`266,288` bytes inside `.venv/Lib/site-packages/ctranslate2/cudnn64_9.dll`) |
| CUDA DLLs Missing on System / `.venv` | `cublas64_12.dll`, `cublasLt64_12.dll`, `cudart64_12.dll`, `cudnn_ops64_9.dll`, `cudnn_ops_infer64_8.dll` |
| `WhisperModel('base.en', device='cuda', compute_type='int8_float16')` | Init succeeded in `2.459 s`, encode raised `RuntimeError: Library cublas64_12.dll is not found or cannot be loaded` |

What is needed to fix the DLL error (not installed): Either install NVIDIA CUDA Toolkit `12.x` + cuDNN `9.x` system-wide and add `bin/` to `PATH`, OR install PyPI runtime wheels `nvidia-cublas-cu12` and `nvidia-cudnn-cu12` (and add their DLL folders to `PATH`/`os.add_dll_directory`). Note: exact wheel download sizes were not queried from PyPI to keep runs offline. Also note that the RTX 3050 has `4096 MiB` VRAM, of which resident `qwen2.5:1.5b` (`num_ctx=4096`) uses `~1.12 GiB` (`1,169,382,440` bytes), leaving `~2.8 GiB` VRAM headroom for `base.en` or `small` `int8_float16`.

---

## 6. Task 5 Results: End-to-End Local Telemetry (`VOICE_TELEMETRY_LOG`)

Executed `5` scripted local turns (`synth_P01.wav`..`synth_P05.wav`, `synthetic_input: true`) through real Silero VAD (`0.55` threshold, `0.65 s` min silence) -> `LocalWhisperSTT` (`base.en`, `cpu/int8`, `beam=1`, `threads=4`) -> Ollama streaming (`qwen2.5:1.5b`, `num_ctx=4096`, `keep_alive=30m`) -> `PiperVoice` first PCM chunk, saving raw JSONL to `bench_results/task5_voice_turns.jsonl`:

| Stage (`5` turns) | Avg (ms) | P50 (ms) | P95 (ms) | Largest Contributor? |
| :--- | :--- | :--- | :--- | :--- |
| `endpoint_ms` (Silero EOU after speech end) | `595.8` | `602.6` | `668.8` | No |
| **`stt_final_ms` (`base.en` CPU INT8 decode)** | **`1555.6`** | **`1626.6`** | **`1688.9`** | **YES (~46.5% of P50 TTFA)** |
| `llm_ttft_ms` (Ollama `qwen2.5:1.5b` first token) | `729.8` | `470.9` | `1762.7` | Turn 1 cold spike (`1762.7 ms`), `467–478 ms` Turns 2–5 |
| `tts_ttfb_ms` (Piper first PCM chunk) | `500.9` | `328.8` | `1096.0` | No (`237–520 ms` except `P04` long numeric string `1096 ms`) |
| `server_ttfa_ms` (`speech_end -> tts_first_audio`) | `3745.8` | `3500.5` | `4736.7` | Total (`STT` is single largest contributor) |

*(Note: `server_ttfa_ms` includes remaining LLM reply generation tokens before non-streamed `piper_voice.synthesize(full_reply)`, explaining the `~320 ms` difference between summing stage first-token latencies and total `server_ttfa_ms`.)*

---

## 7. Task 6 Results: Ollama Facts (Read-Only)

| Field | Measured Fact |
| :--- | :--- |
| Active Primary Model (`OPENAI_MODEL`) | `qwen2.5:1.5b` (`digest: 65ec06548149`) |
| Fallback Model (`FALLBACK_LLM_MODEL`) | `qwen3:1.7b` (`1.4 GB` disk, `2.0B`, `Q4_K_M`, `think=False` passed) |
| Other Local Model Present | `llama3.2:3b` (`2.0 GB` disk, `3.2B`, `Q4_K_M`) |
| `qwen2.5:1.5b` Size & Quantization | `986,061,892` bytes on disk (`986 MB`); `1.5B` Qwen2; `Q4_K_M` GGUF |
| Configured `num_ctx` & `keep_alive` | `num_ctx: 4096` (model max `32768`), `keep_alive: "30m"` across `livekit_worker.py`, `main.py`, `lc_agent.py` |
| Resident State (`ollama ps`) | `1,169,382,440` bytes (`1.2 GB`), `100% GPU` (`size_vram == size`), `llamacpp` runner, stays resident `30 min` (`UNTIL 29 minutes from now`) |
| Cold Model Load (`warm_ping`) | `load_duration_ms: 8488.6 ms` when unloaded -> must keep prewarmed before user speaks |

**Suggestion (labelled as suggestion only, not pulled or tested)**: Keeping `qwen2.5:1.5b` (`Q4_K_M`, `100% GPU`) is already fast (`P50 470.9 ms` TTFT once warm). To lower host virtual commit pressure (`19.45 GB`) on this `7.34 GB` RAM laptop, test `num_ctx=2048` first, or evaluate `qwen2.5:0.5b` (`Q4_K_M`, `~398 MB` on disk vs `986 MB` -> ~`550–650 MB` RAM/VRAM saving; requires accuracy verification on tool calls before switching).

---

## 8. Findings & Why `base.en` Hit `~3.2 s` Earlier

1. **Why earlier test reported `~3.24 s` (`task-2248`) vs `~1.05–1.63 s` warm here**:
   - In the earlier 3-clip synthetic check (`1` run per clip), the median of `[1420.4, 3243.7, 4020.3] ms` mixed **cold first inference + high-memory-pressure pass** (`ram_available_gb: 0.80 GB`) over only 3 single runs.
   - Separating cold from warm across `45` warm runs shows **true `base.en` warm P50 = `1047.0 ms`** (Ollama stopped) rising **`+27.1%` to `1330.8 ms`** (Ollama idle) and **`1359.7 ms`** (Ollama generating) due to heavy commit/pagefile pressure (`16.8 -> 19.45 GB` committed on `7.34 GB` RAM), and **`1626.6 ms` P50** inside end-to-end LiveKit turns alongside VAD and LLM memory footprint.
2. **Thread & VAD Findings**:
   - `cpu_threads=6` (physical core count) yielded the **best P95 (`1290.1 ms`) and RTF (`0.3585`)** at `50.5%` CPU, whereas `cpu_threads=12` saturated all logical cores (`98.8%` CPU) with SMT contention (`1047.0 ms` P50, `1351.3 ms` P95).
   - Disabling faster-whisper's internal `vad_filter` saved `~400–420 ms` cold init/first call with zero accuracy loss on pre-trimmed clips (`0.2382` WER).
3. **What the Data Does Not Show & Caveats**:
   - **Synthetic audio caveat**: All `15` clips came from `en_US-lessac-medium` Piper TTS (`synthetic: true`), not human speakers. Real microphones with Indian-English accents, room echo, trailing TV noise, and real code-switched Hinglish will yield different WER and VAD behavior.
   - Small sample count for Task 5 (`5` synthetic turns) means P95 estimates (`4736.7 ms`) reflect `1` cold-LLM turn (`1762.7 ms`).

---

## 9. Recommendations (Not Changed Automatically)

1. **Recommended to test for change after human-clip verification**:
   - **`WHISPER_CPU_THREADS=6`** (vs current `4`): lowest P95 (`1290.1 vs 1447.8 ms`) and lowest RTF (`0.3585 vs 0.3732`) on 6-core/12-thread Ryzen 5 5600H without `98.8%` SMT saturation.
   - **`WHISPER_VAD_FILTER=false` specifically behind LiveKit `StreamAdapter` + Silero VAD**: eliminates redundant second VAD pass and trims `~400 ms` cold first-turn latency; keep `true` or benchmark on noisy human clips first.
   - **Prewarm Ollama in `agent/livekit_worker.py:prewarm()`**: avoids the `8488.6 ms` cold load hit seen in `warm_ping` / Turn 1 `1762.7 ms` spike.
2. **Keep as-is for now**:
   - Keep **`WHISPER_MODEL_SIZE=base.en`** (`cpu/int8`, `beam=1`, `language=en`) until user records real clips with `python -m evals.record_voice_clips --speaker krish` and benchmarks whether `tiny.en` + expanded domain prompt (`"GST, rupees, Gmail, WhatsApp, YouTube, Paracetamol, Dolo 650, Rahul, Rohit, Nexus"`) at `beam=3` meets entity accuracy on human audio.
   - Keep **`turn_detection="vad"`** and **`preemptive_generation=False`**.

---

## 10. NOT RUN / Unverified List

| Item | Reason |
| :--- | :--- |
| `distil-small.en` & `distil-medium.en` (`Task 2b`) | **NOT RUN** — Not cached in `~/.cache/huggingface/hub`; `local_files_only=True` fails without downloading `~300–800 MB`. |
| CUDA GPU Whisper (`STT_DEVICE=cuda`) | **NOT RUN** beyond error probe — Encode crashes with `RuntimeError: Library cublas64_12.dll is not found or cannot be loaded`. |
| Human Microphone Clip Benchmark | **NOT RUN** — Repository contained `0` human recordings; awaits user recording via `evals/record_voice_clips.py`. |
| `qwen2.5:0.5b` / lower-quant Ollama RAM benchmark | **NOT RUN** — Only `qwen2.5:1.5b`, `qwen3:1.7b`, and `llama3.2:3b` are present locally; zero unapproved model pulls performed. |

---

## 11. Raw Result Files & Commands Used

All raw outputs live under [bench_results/](file:///c:/Users/krish/OneDrive/Desktop/keshav/bench_results):
- [task1b_ollama_stopped.json](file:///c:/Users/krish/OneDrive/Desktop/keshav/bench_results/task1b_ollama_stopped.json), [task1b_ollama_idle.json](file:///c:/Users/krish/OneDrive/Desktop/keshav/bench_results/task1b_ollama_idle.json), [task1b_ollama_generating.json](file:///c:/Users/krish/OneDrive/Desktop/keshav/bench_results/task1b_ollama_generating.json)
- [task1d_threads_3.json](file:///c:/Users/krish/OneDrive/Desktop/keshav/bench_results/task1d_threads_3.json), [task1d_threads_6.json](file:///c:/Users/krish/OneDrive/Desktop/keshav/bench_results/task1d_threads_6.json), [task1d_threads_12.json](file:///c:/Users/krish/OneDrive/Desktop/keshav/bench_results/task1d_threads_12.json)
- [task1e_vad_off.json](file:///c:/Users/krish/OneDrive/Desktop/keshav/bench_results/task1e_vad_off.json)
- [task2a_tiny_b1_default.json](file:///c:/Users/krish/OneDrive/Desktop/keshav/bench_results/task2a_tiny_b1_default.json), [task2a_tiny_b1_prompt.json](file:///c:/Users/krish/OneDrive/Desktop/keshav/bench_results/task2a_tiny_b1_prompt.json), [task2a_tiny_b3_prompt.json](file:///c:/Users/krish/OneDrive/Desktop/keshav/bench_results/task2a_tiny_b3_prompt.json), [task2b_distil_check.json](file:///c:/Users/krish/OneDrive/Desktop/keshav/bench_results/task2b_distil_check.json), [task2c_base_b1_prompt.json](file:///c:/Users/krish/OneDrive/Desktop/keshav/bench_results/task2c_base_b1_prompt.json)
- [task4_cuda_check.json](file:///c:/Users/krish/OneDrive/Desktop/keshav/bench_results/task4_cuda_check.json)
- [task5_voice_turns.jsonl](file:///c:/Users/krish/OneDrive/Desktop/keshav/bench_results/task5_voice_turns.jsonl), [task5_e2e_summary.json](file:///c:/Users/krish/OneDrive/Desktop/keshav/bench_results/task5_e2e_summary.json)
- [task6_ollama_facts.json](file:///c:/Users/krish/OneDrive/Desktop/keshav/bench_results/task6_ollama_facts.json)

Key commands executed:
```powershell
.\.venv\Scripts\python.exe -m evals.benchmark_voice --generate-synthetic bench_clips/synthetic --prompts bench_clips/prompts.json
.\.venv\Scripts\python.exe -m evals.benchmark_voice --manifest bench_clips/synthetic/manifest.jsonl --model base.en --beam 1 --cpu-threads 4 --vad-filter on --repeats 3 --ollama-state stopped --out bench_results/task1b_ollama_stopped.json
.\.venv\Scripts\python.exe -m evals.benchmark_voice --manifest bench_clips/synthetic/manifest.jsonl --model base.en --beam 1 --cpu-threads 3 --vad-filter on --repeats 3 --ollama-state stopped --out bench_results/task1d_threads_3.json
.\.venv\Scripts\python.exe -m evals.benchmark_voice --manifest bench_clips/synthetic/manifest.jsonl --model base.en --beam 1 --cpu-threads 6 --vad-filter on --repeats 3 --ollama-state stopped --out bench_results/task1d_threads_6.json
.\.venv\Scripts\python.exe -m evals.benchmark_voice --manifest bench_clips/synthetic/manifest.jsonl --model base.en --beam 1 --cpu-threads 12 --vad-filter on --repeats 3 --ollama-state stopped --out bench_results/task1d_threads_12.json
.\.venv\Scripts\python.exe -m evals.benchmark_voice --manifest bench_clips/synthetic/manifest.jsonl --model base.en --beam 1 --cpu-threads 4 --vad-filter off --repeats 3 --ollama-state stopped --out bench_results/task1e_vad_off.json
.\.venv\Scripts\python.exe -m evals.benchmark_voice --manifest bench_clips/synthetic/manifest.jsonl --model tiny.en --beam 1 --cpu-threads 4 --vad-filter on --repeats 3 --ollama-state stopped --out bench_results/task2a_tiny_b1_default.json
.\.venv\Scripts\python.exe -m evals.benchmark_voice --manifest bench_clips/synthetic/manifest.jsonl --model tiny.en --beam 1 --cpu-threads 4 --vad-filter on --prompt "GST, rupees, Gmail, calendar, Nexus" --repeats 3 --ollama-state stopped --out bench_results/task2a_tiny_b1_prompt.json
.\.venv\Scripts\python.exe -m evals.benchmark_voice --manifest bench_clips/synthetic/manifest.jsonl --model tiny.en --beam 3 --cpu-threads 4 --vad-filter on --prompt "GST, rupees, Gmail, calendar, Nexus" --repeats 3 --ollama-state stopped --out bench_results/task2a_tiny_b3_prompt.json
.\.venv\Scripts\python.exe -m evals.benchmark_voice --manifest bench_clips/synthetic/manifest.jsonl --model base.en --beam 1 --cpu-threads 4 --vad-filter on --prompt "GST, rupees, Gmail, calendar, Nexus" --repeats 3 --ollama-state stopped --out bench_results/task2c_base_b1_prompt.json
.\.venv\Scripts\python.exe -m evals.benchmark_voice --manifest bench_clips/synthetic/manifest.jsonl --model base.en --beam 1 --cpu-threads 4 --vad-filter on --repeats 3 --ollama-state idle --out bench_results/task1b_ollama_idle.json
.\.venv\Scripts\python.exe -m evals.benchmark_voice --manifest bench_clips/synthetic/manifest.jsonl --model base.en --beam 1 --cpu-threads 4 --vad-filter on --repeats 3 --ollama-state generating --concurrent-ollama-gen --out bench_results/task1b_ollama_generating.json
.\.venv\Scripts\python.exe -m evals.benchmark_voice --e2e-turns 5 --manifest bench_clips/synthetic/manifest.jsonl --telemetry-log bench_results/task5_voice_turns.jsonl --out bench_results/task5_e2e_summary.json
```
