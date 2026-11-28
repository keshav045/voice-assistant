# Voice Pipeline Latency & Accuracy Diagnosis Report v2

Branch: `voice-latency-diagnosis` (`main` untouched at `fc002ed`)  
Date: 2026-11-28  
Scope: Follow-up evidence audit correcting prior report flaws, evaluating interleaved controls, endpoint silence cutoffs, production streaming alignment, host memory footprint, env-gated startup prewarm, and held-out prompt leakage. Zero code defaults were changed (`base.en`, `en`, `beam=1`, `cpu`, `int8`, `turn_detection="vad"`, `preemptive_generation=False`, Silero VAD `0.55 / 0.08 / 0.65`, `cpu_threads=4`, `vad_filter=True`).

> Synthetic Audio Disclosure: Repository contained `0` human recordings (`REPO_AUDIO_CLIPS: []`). All audio benchmarks (`15` original prompts in [bench_clips/synthetic/manifest.jsonl](file:///c:/Users/krish/OneDrive/Desktop/keshav/bench_clips/synthetic/manifest.jsonl), `12` held-out prompts in [bench_clips/heldout_synthetic/manifest.jsonl](file:///c:/Users/krish/OneDrive/Desktop/keshav/bench_clips/heldout_synthetic/manifest.jsonl), `4` duration clips in [bench_clips/durations/manifest.jsonl](file:///c:/Users/krish/OneDrive/Desktop/keshav/bench_clips/durations/manifest.jsonl), and pause clips) were generated with offline Piper TTS (`en_US-lessac-medium`, marked `synthetic: true`). Human confirmation via [record_voice_clips.py](file:///c:/Users/krish/OneDrive/Desktop/keshav/evals/record_voice_clips.py) is still required.

---

## Environment & Hardware Table

| Component | Measured Value |
| :--- | :--- |
| OS | `Windows-11-10.0.26300-SP0` |
| Python | `3.13.7` |
| CPU | `AMD Ryzen 5 5600H with Radeon Graphics` (`AMD64 Family 25 Model 80 Stepping 0`) |
| Physical / Logical Cores | `6` physical cores / `12` logical processors |
| System RAM | `7.342 GB` (`7,698,540 KB`; Tier `C_MODEST_CPU_8GB`) |
| Commit / Virtual Limit | `25.174 GB` (`26,396,748 KB`) |
| GPU (`nvidia-smi`) | `NVIDIA GeForce RTX 3050 Laptop GPU`, `4096 MiB` VRAM (`Driver 610.91`, `CUDA UMD 13.3`) |
| Inference Packages | `faster-whisper 1.2.1`, `ctranslate2 4.9.1`, `livekit-agents 1.9.0`, `livekit-plugins-silero 1.9.0`, `piper-tts 1.8.0`, `edge-tts 7.3.1` |
| Optional Packages | `livekit-plugins-turn-detector`: NOT INSTALLED; `sherpa-onnx`: NOT INSTALLED |
| Ollama Local Models | `qwen2.5:1.5b` (`986 MB`, `Q4_K_M`), `qwen3:1.7b` (`1.4 GB`, `Q4_K_M`), `llama3.2:3b` (`2.0 GB`, `Q4_K_M`) |

---

## Task 0: Corrections to Previous Results (`REPORT.md`)

### 0a. Rescored Previous Runs (`task0_rescored_summary.json`)
All saved transcripts from Task 1 and Task 2 were rescored with the final `compute_entity_accuracy` normalizer so every configuration uses identical scoring rules:

| Raw File | Config | Clips (Syn) | WER (All 15) | WER (Excl. Hinglish `P11`/`P12`, 13 clips) | Entity Acc (All 15) | Entity Acc (Excl. Hinglish) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `task1b_ollama_stopped.json` | `base.en`, `t=4`, `vad=on`, `stopped` | 15 (`true`) | `0.2382` | `0.1477` | `0.8333` (`25/30`) | `0.8276` (`24/29`) |
| `task1b_ollama_idle.json` | `base.en`, `t=4`, `vad=on`, `idle` | 15 (`true`) | `0.2382` | `0.1477` | `0.8333` (`25/30`) | `0.8276` (`24/29`) |
| `task1b_ollama_generating.json` | `base.en`, `t=4`, `vad=on`, `gen` | 15 (`true`) | `0.2382` | `0.1477` | `0.8333` (`25/30`) | `0.8276` (`24/29`) |
| `task1d_threads_3.json` | `base.en`, `t=3`, `vad=on`, `stopped` | 15 (`true`) | `0.2382` | `0.1477` | `0.8333` (`25/30`) | `0.8276` (`24/29`) |
| `task1d_threads_6.json` | `base.en`, `t=6`, `vad=on`, `stopped` | 15 (`true`) | `0.2382` | `0.1477` | `0.8333` (`25/30`) | `0.8276` (`24/29`) |
| `task1d_threads_12.json` | `base.en`, `t=12`, `vad=on`, `stopped` | 15 (`true`) | `0.2382` | `0.1477` | `0.8333` (`25/30`) | `0.8276` (`24/29`) |
| `task1e_vad_off.json` | `base.en`, `t=4`, `vad=off`, `stopped` | 15 (`true`) | `0.2382` | `0.1477` | `0.8333` (`25/30`) | `0.8276` (`24/29`) |
| `task2a_tiny_b1_default.json` | `tiny.en`, `b=1`, default prompt | 15 (`true`) | `0.2875` | `0.1875` | `0.8000` (`24/30`) | `0.8276` (`24/29`) |
| `task2a_tiny_b1_prompt.json` | `tiny.en`, `b=1`, short prompt | 15 (`true`) | `0.2752` | `0.1905` | `0.7667` (`23/30`) | `0.7931` (`23/29`) |
| `task2a_tiny_b3_prompt.json` | `tiny.en`, `b=3`, short prompt | 15 (`true`) | `0.2724` | `0.1701` | `0.8000` (`24/30`) | `0.8276` (`24/29`) |
| `task2c_base_b1_prompt.json` | `base.en`, `b=1`, short prompt | 15 (`true`) | `0.2751` | `0.1999` | `0.8000` (`24/30`) | `0.7931` (`23/29`) |

### 0b. Per-Category WER & Entity Accuracy Breakdown (`15` synthetic clips)

| Category (Clip Count) | `base.en` Default Prompt WER / Entity Acc | `base.en` Short Prompt WER / Entity Acc | `tiny.en` `b=1` Default WER / Entity Acc | `tiny.en` `b=1` Short Prompt WER / Entity Acc | `tiny.en` `b=3` Short Prompt WER / Entity Acc |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `clean_english` (`3`) | `0.1111` / `1.0` (`5/5`) | `0.1111` / `1.0` (`5/5`) | `0.2434` / `0.8` (`4/5`) | `0.1898` / `0.8` (`4/5`) | `0.1898` / `0.8` (`4/5`) |
| `indian_english_accent` (`2`) | `0.1875` / `1.0` (`3/3`) | `0.1875` / `1.0` (`3/3`) | `0.1875` / `1.0` (`3/3`) | `0.1875` / `1.0` (`3/3`) | `0.1875` / `1.0` (`3/3`) |
| `numbers_amounts_emails` (`3`) | `0.1595` / `0.8` (`8/10`) | `0.2155` / `0.8` (`8/10`) | `0.2071` / `0.7` (`7/10`) | `0.2364` / `0.7` (`7/10`) | `0.1852` / `0.8` (`8/10`) |
| `names` (`2`) | `0.2666` / `0.5` (`3/6`) | `0.3222` / `0.3333` (`2/6`) | `0.0556` / `0.8333` (`5/6`) | `0.1111` / `0.6667` (`4/6`) | `0.0556` / `0.6667` (`4/6`) |
| `hinglish` (`2`, `P11`/`P12`) | `0.8264` / `1.0` (`1/1`) | `0.7639` / `1.0` (`1/1`) | `0.9375` / `0.0` (`0/1`) | `0.8264` / `0.0` (`0/1`) | `0.9375` / `0.0` (`0/1`) |
| `noisy_far_mic` (`2`, note*) | `0.0` / `1.0` (`1/1`) | `0.2` / `1.0` (`1/1`) | `0.2` / `1.0` (`1/1`) | `0.2` / `1.0` (`1/1`) | `0.2` / `1.0` (`1/1`) |
| `pauses_corrections` (`1`) | `0.2` / `1.0` (`4/4`) | `0.2` / `1.0` (`4/4`) | `0.2` / `1.0` (`4/4`) | `0.2` / `1.0` (`4/4`) | `0.2` / `1.0` (`4/4`) |
| **Overall Excl. Hinglish (`13`)** | **`0.1477` / `0.8276`** | `0.1999` / `0.7931` | `0.1875` / `0.8276` | `0.1905` / `0.7931` | `0.1701` / `0.8276` |

*\*Synthetic `noisy_far_mic` clips have prompt text only without real acoustic room noise or far-field attenuation.*

### 0c. Explicit Errata Corrected From `REPORT.md`
1. **VAD cold-load claim**: `REPORT.md` attributed `906.0 ms` cold load on `vad=off` to removing Silero VAD (`1329.0 -> 906.0 ms`), ignoring that across `vad=on` runs `cold_load_ms` already varied from **`920.9 ms` to `1329.0 ms`** (`threads=12: 920.9`, `threads=3: 1124.2`, `threads=6: 1280.5`, `threads=4: 1329.0`). Cold load difference is therefore NOT attributable to `vad_filter`.
2. **Task 5 `~320 ms` gap note**: On `task5_e2e_summary.json` (`5` turns), sum of stage averages (`595.8 + 1555.6 + 729.8 + 500.9 = 3382.1 ms`) vs `server_ttfa_ms` average (`3745.8 ms`) is **`363.7 ms`**; sum of stage P50s (`602.6 + 1626.6 + 470.9 + 328.8 = 3028.9 ms`) vs `server_ttfa_ms` P50 (`3500.5 ms`) is **`471.6 ms`** (per-turn gaps: `[423.4, 319.0, 343.1, 566.5, 166.4] ms`).
3. **Longest-clip label**: `REPORT.md` named `synth_P10`/`synth_P15` (`3.3901 s`) as longest right after stating `3.6456 s`. Verified longest clip in `task1b_ollama_stopped.json` is **`synth_P08.wav` (`4.7601 s`, warm P50 `1069.3 ms`, RTF `0.2246`)**.
4. **Shortest-clip cold vs warm label**: `synth_P14.wav` (`1.8228 s`, warm P50 `1000.5 ms`, warm RTF `0.5489`) was **warm** (fixed per-call encoder work), NOT cold; **`synth_P01.wav` (`2.5426 s`)** was the cold 1st call (`1301.6 ms` cold, `1005.4 ms` warm P50, warm RTF `0.3954`).

---

## Task 1: GPU Proposal (`nvidia-cublas-cu12`, `nvidia-cudnn-cu12`) & Duration Scaling (`1, 2, 4, 8 s`)

### 1a. Proposed Packages & Exact PyPI `win_amd64` Sizes (Zero Packages Installed)

| Package | Version | `win_amd64` Wheel | Exact Size | Notes |
| :--- | :--- | :--- | :--- | :--- |
| `nvidia-cublas-cu12` | `12.9.2.10` | `nvidia_cublas_cu12-12.9.2.10-py3-none-win_amd64.whl` | `553.2 MB` | Provides `cublas64_12.dll` & `cublasLt64_12.dll` (Note: `12.9.3.13` only published Linux wheels) |
| `nvidia-cudnn-cu12` | `9.28.1.4` | `nvidia_cudnn_cu12-9.28.1.4-py3-none-win_amd64.whl` | `664.04 MB` (`696,300,805 B`) | Provides `cudnn_ops64_9.dll` & cuDNN 9 kernels |
| `nvidia-cuda-nvrtc-cu12` | `12.9.86` | `nvidia_cuda_nvrtc_cu12-12.9.86-py3-none-win_amd64.whl` | `72.87 MB` (`76,408,187 B`) | Transitive dependency pulled by `nvidia-cublas-cu12` |
| **Total Download** | — | — | **`~1,290.1 MB`** (`~1.26 GiB`) | Installs into `.venv` only; ~2.5+ GB unpacked |

Guarded code added in [agent/local_voice.py](file:///c:/Users/krish/OneDrive/Desktop/keshav/agent/local_voice.py): `_register_cuda_dll_paths()` invokes `os.add_dll_directory()` on `.venv/Lib/site-packages/nvidia/*/bin` **only when `device == "cuda"`** (`STT_DEVICE=cpu` remains default, automatic CPU INT8 fallback preserved).

### 1b. GPU vs CPU Benchmark Matrix (`base.en`, `small.en`, `tiny.en` on `cuda int8_float16` / `float16`)
- **Status**: **`NOT RUN`** — awaiting user approval to install the ~`1.29 GB` CUDA 12 / cuDNN 9 wheels listed in Table 1a (and `small.en` is not cached locally).

### 1c. Duration Scaling (`1.0 s`, `2.0 s`, `4.0 s`, `8.0 s` Synthetic Clips; `repeats=5`)
Tested on `cpu/int8`, `beam=1`, `threads=4`, `vad_filter=on`, Ollama `stopped` (`task1c_duration_scaling_cpu.json`). **GPU column = `NOT RUN`**.

| Model | Clip (`synthetic: true`) | Exact Duration (s) | Cold 1st Call (ms) | Warm P50 (ms) | Warm P95 (ms) | Min / Max (ms) | Warm RTF (P50) | GPU Latency |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `base.en` | `dur_1s.wav` | `1.0` | `1108.5` | `968.9` | `992.8` | `921.2 / 992.8` | `0.9689` | `NOT RUN` |
| `base.en` | `dur_2s.wav` | `2.0` | — | `981.5` | `1013.0` | `918.1 / 1013.0` | `0.4908` | `NOT RUN` |
| `base.en` | `dur_4s.wav` | `4.0` | — | `1017.9` | `1049.2` | `997.8 / 1049.2` | `0.2545` | `NOT RUN` |
| `base.en` | `dur_8s.wav` | `8.0` | — | `1219.4` | `1311.9` | `1155.0 / 1311.9` | `0.1524` | `NOT RUN` |
| `tiny.en` | `dur_1s.wav` | `1.0` | `445.4` | `454.4` | `681.7` | `438.1 / 681.7` | `0.4544` | `NOT RUN` |
| `tiny.en` | `dur_2s.wav` | `2.0` | — | `471.4` | `579.0` | `433.7 / 579.0` | `0.2357` | `NOT RUN` |
| `tiny.en` | `dur_4s.wav` | `4.0` | — | `488.4` | `523.3` | `438.5 / 523.3` | `0.1221` | `NOT RUN` |
| `tiny.en` | `dur_8s.wav` | `8.0` | — | `502.4` | `524.4` | `489.3 / 524.4` | `0.0628` | `NOT RUN` |

Observation: Going from `1.0 s` to **`8.0 s` (8x more audio)** added only **`+48.0 ms`** on `tiny.en` (`454.4 -> 502.4 ms`) and **`+250.5 ms`** on `base.en` (`968.9 -> 1219.4 ms`), confirming that ~`950 ms` (`base.en`) and ~`450 ms` (`tiny.en`) is fixed per-call 30-second-window encoder work on CPU.

---

## Task 2: Interleaved A/B/A/B Threads & VAD Results (`>= 5` Repeats / Block)

Each arm ran `2` interleaved blocks x `5` repeats x `15` clips = `150` warm decodes per arm (`task2_interleaved_threads_4_vs_6.json`, `task2_interleaved_vad_on_vs_off.json`), `base.en`, `beam=1`, `cpu/int8`, Ollama `stopped`.

| Experiment (`A/B/A/B`) | Config | Warm Decodes | Block Medians (ms) | Pooled Median (ms) | Min / Max (ms) | Pooled P95 (ms) | WER / Entity Acc | Peak RSS (MB) | Delta % & Verdict |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Threads Sweep | `threads=4` (`A`) | `150` (`15` syn) | `1068.9`, `1138.2` | `1111.9` | `898.1 / 2522.0` | `1571.7` | `0.2382` / `0.8333` | `545.5` | — |
| Threads Sweep | `threads=6` (`B`) | `150` (`15` syn) | `1148.4`, `1317.8` | `1207.0` | `869.8 / 2821.4` | `1825.0` | `0.2382` / `0.8333` | `545.5` | **`+8.55%` -> no significant difference** |
| VAD Filter Sweep | `vad_filter=on` (`A`) | `150` (`15` syn) | `1090.8`, `1307.7` | `1216.8` | `899.3 / 2810.6` | `1852.9` | `0.2382` / `0.8333` | `547.0` | — |
| VAD Filter Sweep | `vad_filter=off` (`B`) | `150` (`15` syn) | `1076.4`, `1119.8` | `1097.3` | `904.5 / 1462.3` | `1288.7` | `0.2382` / `0.8333` | `547.0` | **`-9.82%` -> no significant difference in median** (P95 `1852.9 -> 1288.7 ms` tighter) |

---

## Task 3: Silero `min_silence` Endpoint Tuning (`synthetic: true`)

Measured on `6` trailing-silence runs (`2` clean synthetic phrases x `3` repeats) + `3` synthetic mid-sentence pause clips (`0.45 s`, `0.55 s`, `0.60 s` digital silence gaps) per threshold (`activation_threshold=0.55`, `min_speech_duration=0.08`, `task3_endpoint_sweep.json`):

| Silero `min_silence_duration` | Synthetic? | Clean Trials | `endpoint_ms` P50 (ms) | `endpoint_ms` P95 (ms) | Min / Max (ms) | Paused Clips | Premature Cutoffs | Clips Cut Prematurely |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **`0.65` (current default)** | **Yes (`synthetic: true`)** | `6` | `547.0` | `609.4` | `531.7 / 609.4` | `3` | **`1 / 3`** | `pause_600ms` only (`pause_450ms` & `pause_550ms` held) |
| `0.50` | **Yes (`synthetic: true`)** | `6` | `391.2` | `455.2` | `374.2 / 455.2` | `3` | **`3 / 3`** | `pause_450ms`, `pause_550ms`, `pause_600ms` |
| `0.40` | **Yes (`synthetic: true`)** | `6` | `281.5` | `363.3` | `267.1 / 363.3` | `3` | **`3 / 3`** | `pause_450ms`, `pause_550ms`, `pause_600ms` |

*Confirmation Notice: All pause gaps are digital `0`-PCM gaps between Piper clips and MUST be confirmed on real human microphone speech with breath/hesitation cadence before altering defaults.*

---

## Task 4: Production Path Audit & `22`-Turn E2E Telemetry

### 4a & 4b. Production (`livekit_worker.py`) vs Benchmark Harness (`benchmark_voice.py`)
1. **Does `livekit_worker.py` stream LLM output to Piper sentence-by-sentence?** **Yes.**
   - In [agent/livekit_worker.py](file:///c:/Users/krish/OneDrive/Desktop/keshav/agent/livekit_worker.py) lines `878–892`, `_build_resilient_engines()` wraps `LocalPiperTTS()` (`capabilities=TTSCapabilities(streaming=False)`) inside `tts.FallbackAdapter([local_piper, local_edge])` and then wraps that in `tts.StreamAdapter(tts=local_tts_chunked)`.
   - Inspected `livekit.agents.tts.StreamAdapter` / `StreamAdapterWrapper._run` in `.venv` (`livekit-agents 1.9.0`): it attaches `tokenize.blingfire.SentenceTokenizer(retain_format=True)` (`_forward_input()` pushes streaming LLM chunks, `_synthesize()` iterates `async for ev in sent_stream:` and calls `self._tts._wrapped_tts.synthesize(text)` **for each sentence token immediately upon completion**).
2. **Does `run_local_e2e_telemetry_turns()` reuse `AgentSession`?** **No — it is a separate scripted harness.** Exact differences:
   - Reuses `TurnTimer` ([voice_telemetry.py](file:///c:/Users/krish/OneDrive/Desktop/keshav/agent/voice_telemetry.py)), `silero.VAD.load(...)` thresholds (`0.55 / 0.08 / 0.65`), `LocalWhisperSTT`, Ollama `qwen2.5:1.5b` (`num_ctx=4096`, `keep_alive=30m`), and `PiperVoice`.
   - Differs in: (a) awaiting the full Ollama response (`full_reply = "".join(llm_reply_parts)`) before calling `piper_voice.synthesize(full_reply)` instead of streaming sentence-by-sentence via `tts.StreamAdapter`; (b) running without `AgentSession` / `stt.StreamAdapter` / `min_endpointing_delay=0.55` turn detector state; and (c) sending a minimal 1-line system prompt without `22` `@llm.function_tool` JSON schemas.

### 4c & 4d. `22`-Turn Telemetry With Memory Pressure (`task4_e2e_22turns.jsonl`)
Executed `22` synthetic turns including `2` explicitly unloaded cold-LLM turns (Turn `#1` and Turn `#12` via `keep_alive=0`), logging `ram_available_gb` (`0.663–0.85 GB`) and `commit_used_gb` (`16.823–17.197 GB`) on every row:

| Subset (`synthetic_input: true`) | Turns | `endpoint_ms` P50 / P95 | `stt_final_ms` P50 / P95 | `llm_ttft_ms` P50 / P95 | `llm_total_ms` P50 / P95 | `tts_ttfb_ms` P50 / P95 | `server_ttfa_ms` P50 / P95 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Excluding Cold LLM** | `20` | `594.7` / `652.4` | **`1199.7` / `1362.7`** | `374.8` / `448.0` | `671.1` / `983.9` | `279.1` / `428.4` | **`2739.8` / `3060.5`** |
| **Cold LLM Only (`#1`, `#12`)** | `2` | `541.9` / `593.7` | `1156.9` / `1271.2` | **`4787.9` / `6834.6`** | `4952.6` / `6979.9` | `158.8` / `193.1` | **`6810.2` / `9037.9`** |
| **Including Cold LLM (All)** | `22` | `580.3` / `652.4` | `1197.6` / `1362.7` | `374.8` / `4787.9` | `671.1` / `4952.6` | `256.8` / `428.4` | **`2739.8` / `6810.2`** |

Memory-pressure check across the `22` turns: `ram_available_gb` stayed tight (`0.663–0.850 GB`, `89–90%` RAM used), commit `16.823–17.197 GB`; slowest warm STT turns (`Turn 7: 1403.8 ms @ 0.741 GB`, `Turn 22: 1362.7 ms @ 0.779 GB`, `Turn 8: 1327.0 ms @ 0.761 GB`) reflected clip complexity plus ~90% RAM saturation, while cold TTFA spikes (`Turn 1: 9037.9 ms @ 0.663 GB`, `Turn 12: 6810.2 ms @ 0.702 GB`) were dominated by `qwen2.5:1.5b` cold loading (`4.79–6.83 s`).

---

## Task 5: Host Memory & Ollama Footprint

| Timing | OS Free RAM / Commit | Top Host Consumers (Working Set RAM / Private Commit) | Ollama + `llama-server` Total Footprint |
| :--- | :--- | :--- | :--- |
| **Baseline (Ollama Stopped)** | `793.6 MB` free (`812,628 KB`), Commit `16.44 / 25.17 GB` | 1. `Memory Compression` (`1133.5` / `8.0 MB`), 2. `chrome` PID `5328` (`307.7` / `338.1`), 3. `agy` (`268.4` / `330.9`), 4. `Code` `18052` (`262.0` / `355.7`), 5. `Code` `14340` (`241.4` / `395.4`), 6. `chrome` `23380` (`237.4` / `368.6`), 7. `MsMpEng` (`158.7` / `410.9`), 8. `chrome` `1680` (`143.2` / `205.6`), 9. `explorer` (`103.9` / `178.1`), 10. `powershell` (`86.4` / `66.5`) | `0 MB` (`ollama` not running) |
| **Ollama Idle (`qwen2.5:1.5b` loaded)** | `931.6 MB` free (`954,000 KB`), Commit `16.02 / 25.17 GB` | Top processes include `Memory Compression` (`646.0 MB`), `llama-server` (`634.1` / `1997.9 MB`), `Code` x3 (`672.0 MB`), `agy` (`304.5 MB`), `MsMpEng` (`186.6 MB`) | **`ollama.exe` (`46.5` / `71.3 MB`) + `llama-server.exe` (`634.1` / `1997.9 MB`) = `680.6 MB` RAM Working Set (`2,069.2 MB` Private commit) + `1.2 GB` (`1,169,382,440 B`) `100% GPU` VRAM** |

Justification for keeping `qwen2.5:1.5b`: Baseline desktop apps (Chrome + VS Code + Antigravity + Defender + Memory Compression) consume ~`6.55 GB` of the laptop's `7.34 GB` RAM *before* Ollama even starts, while `qwen2.5:1.5b` (`1.5B` `Q4_K_M`) runs `100% GPU` on the RTX 3050 (`1.12 GiB` / `4096 MiB` VRAM) with `374.8 ms` P50 warm TTFT. Swapping to a smaller LLM (`0.5B`) is therefore NOT supported by the memory data cleanly and risks tool-calling degradation.

---

## Task 6: Opt-In Prewarm Implementation & Cold Turn 1 Before vs After

Implemented in [agent/livekit_worker.py](file:///c:/Users/krish/OneDrive/Desktop/keshav/agent/livekit_worker.py) behind env flags (both default **`"false"`** so behavior is unchanged unless enabled):
- `PREWARM_OLLAMA=true` -> `prewarm_ollama()` (tiny `/api/generate` `num_predict=1` using `OLLAMA_KEEP_ALIVE=30m` & `OLLAMA_NUM_CTX=4096`).
- `PREWARM_STT_DECODE=true` -> `prewarm_stt_decode()` (~`1.0 s` non-silent `16 kHz` warmup decode).

Measured across `3` clean isolated child processes per arm on `synth_P01.wav` (`task6_prewarm_before_after.json`):

| Arm (`3` subprocess trials each) | Prewarm Boot Time (ms) | Turn 1 STT P50 / P95 (ms) | Turn 1 LLM TTFT P50 / P95 (ms) | Turn 1 TTS TTFB P50 / P95 (ms) | Total Turn 1 Compute P50 / P95 (ms) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Before (`PREWARM=false`)** | `0.0` | `1126.6` / `1289.6` | **`5580.4` / `6125.2`** | `226.3` / `333.1` | **`7225.5` / `7754.8`** |
| **After (`PREWARM=true`)** | `7746.8–8545.3` (`8111.6` P50) | `1163.5` / `1197.9` | **`438.5` / `453.8`** (`-5141.9 ms`) | `179.1` / `192.8` | **`1904.8` / `1938.0`** (**`-73.6%` Turn 1 latency**) |

Evidence verdict: `PREWARM_OLLAMA=true` eliminates the `5.6 s` Turn 1 cold-LLM stall at startup; `PREWARM_STT_DECODE` produced no P50 speedup (`1126.6 -> 1163.5 ms`) once `LocalWhisperSTT.__init__` already loaded the model.

---

## Task 7: Prompt Leakage Test (`original_15` vs Held-Out `heldout_12`)

Built [bench_clips/heldout_prompts.json](file:///c:/Users/krish/OneDrive/Desktop/keshav/bench_clips/heldout_prompts.json) (`12` prompts verified with `verify_heldout_prompt_isolation() == []`, zero shared tokens with `STT_INITIAL_PROMPT` / `GST` / `rupees` / `calendar`, `repeats=3`, `cpu/int8`, `beam=1`, `threads=4`, `vad=on`, `task7_prompt_leakage.json`):

| Dataset (`synthetic: true`) | Model | Prompt Config | Clips | WER | CER | Entity Acc (`matched/expected`) | Warm P50 / P95 (ms) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `original_15` | `base.en` | `prompt_on` (`_DEFAULT_STT_PROMPT`) | `15` | `0.2382` | `0.1009` | `0.8333` (`25/30`) | `1339.5` / `1472.4` |
| `original_15` | `base.en` | `prompt_off` (`None`) | `15` | `0.2765` | `0.1083` | `0.7667` (`23/30`) | `1266.6` / `1522.9` |
| `original_15` | `tiny.en` | `prompt_on` (`_DEFAULT_STT_PROMPT`) | `15` | `0.2875` | `0.1131` | `0.8000` (`24/30`) | `660.2` / `767.6` |
| `original_15` | `tiny.en` | `prompt_off` (`None`) | `15` | `0.3186` | `0.1284` | `0.7000` (`21/30`) | `675.7` / `755.3` |
| `heldout_12` | `base.en` | `prompt_on` (`_DEFAULT_STT_PROMPT`) | `12` | **`0.1421`** | `0.1265` | `0.3333` (`4/12`) | `1335.0` / `1455.7` |
| `heldout_12` | `base.en` | `prompt_off` (`None`) | `12` | **`0.1421`** | `0.1265` | `0.3333` (`4/12`) | `1312.8` / `1466.5` |
| `heldout_12` | `tiny.en` | `prompt_on` (`_DEFAULT_STT_PROMPT`) | `12` | **`0.1495`** | `0.1277` | `0.3333` (`4/12`) | `671.0` / `733.5` |
| `heldout_12` | `tiny.en` | `prompt_off` (`None`) | `12` | **`0.1495`** | `0.1260` | `0.4167` (`5/12`) | `820.9` / `1115.2` |

Finding: `STT_INITIAL_PROMPT` gains (`-0.0383` WER / `+2` entities on `base.en`; `-0.0311` WER / `+3` entities on `tiny.en`) occurred **only on the overlapping `original_15` set** and gave **zero WER improvement on `heldout_12`** (`0.1421 == 0.1421` on `base.en`; `0.1495 == 0.1495` on `tiny.en`).

---

## Findings & What the Data Does Not Show

1. **Main E2E Latency Causes**: On warm turns (`N=20`), **`base.en` CPU INT8 decode (`1199.7 ms` P50, `~44%` of `2739.8 ms` P50 TTFA)** is the largest consistent contributor due to fixed 30s-window encoder work (`~950 ms` fixed floor from `1–8 s` scaling test). On Turn 1 without prewarm, cold `qwen2.5:1.5b` loading (`4.79–6.83 s`) dominates (`7225.5 ms` -> `1904.8 ms` when `PREWARM_OLLAMA=true`).
2. **Thread & VAD Conclusions**: Neither `threads 4 vs 6` (`+8.55%`, overlapping) nor `vad_filter on vs off` (`-9.82%`, overlapping) showed a significant median latency difference in interleaved `A/B/A/B` runs (`150` decodes/arm), though `vad_filter=off` tightened P95 (`1852.9 -> 1288.7 ms`) on clean trimmed synthetic clips.
3. **What the Data Does Not Show**:
   - Real human microphone performance (Indian English accents, spontaneous disfluencies, background TV/fan noise, microphone AEC artifacts).
   - How `vad_filter=off` performs when background noise slips past Silero VAD, or how `0.65 s` vs `0.50 s` `min_silence` handles human breath pauses.
   - True GPU speedup (`cuda` `int8_float16` / `float16`) and GPU contention with `qwen2.5:1.5b` on the RTX 3050.
   - Real `AgentSession` + `tts.StreamAdapter` sentence-streaming E2E TTFA vs the full-reply scripted harness.

---

## NOT RUN / Unverified List

| Item | Reason |
| :--- | :--- |
| Task 1b & Task 1c GPU (`base.en`, `small.en`, `tiny.en` on CUDA `int8_float16` / `float16`) | **NOT RUN** — Awaiting approval to install `nvidia-cublas-cu12`, `nvidia-cudnn-cu12`, and `nvidia-cuda-nvrtc-cu12` (`~1.29 GB` total); `cublas64_12.dll` missing locally. |
| Task 2b `distil-small.en` / `distil-medium.en` | **NOT RUN** — Not in local HuggingFace cache (`local_files_only=True` fails without downloading). |
| Human Microphone Clip Set (`bench_clips/human/`) | **NOT RUN** — Awaiting human recording session (`python -m evals.record_voice_clips`). |
| Smaller Ollama Model RAM Benchmark (`qwen2.5:0.5b`) | **NOT RUN** — Not pulled locally, and memory breakdown showed host apps (`~6.55 GB`) rather than GPU-offloaded `qwen2.5:1.5b` (`680.6 MB` host RAM) were primary RAM consumers. |

---

## Git Diff Summary & Test Output Verification

Branch: `* voice-latency-diagnosis` (`main` untouched at `fc002ed`).

Phase 2 voice diagnosis files added/modified on `voice-latency-diagnosis`:
- Added: [REPORT_v2.md](file:///c:/Users/krish/OneDrive/Desktop/keshav/REPORT_v2.md), [evals/record_voice_clips.py](file:///c:/Users/krish/OneDrive/Desktop/keshav/evals/record_voice_clips.py), [bench_clips/prompts.json](file:///c:/Users/krish/OneDrive/Desktop/keshav/bench_clips/prompts.json), [bench_clips/heldout_prompts.json](file:///c:/Users/krish/OneDrive/Desktop/keshav/bench_clips/heldout_prompts.json), `bench_clips/synthetic/*`, `bench_clips/heldout_synthetic/*`, `bench_clips/durations/*`, `./bench_results/*` (`26` raw artifacts including `task0_rescored_summary.json`, `task1c_duration_scaling_cpu.json`, `task2_interleaved_*.json`, `task3_endpoint_sweep.json`, `task4_e2e_22turns*`, `task5_memory_ollama_idle.json`, `task6_prewarm_before_after.json`, `task7_prompt_leakage.json`).
- Modified on this branch for diagnosis/hooks (defaults unchanged): [agent/local_voice.py](file:///c:/Users/krish/OneDrive/Desktop/keshav/agent/local_voice.py), [agent/voice_telemetry.py](file:///c:/Users/krish/OneDrive/Desktop/keshav/agent/voice_telemetry.py), [agent/livekit_worker.py](file:///c:/Users/krish/OneDrive/Desktop/keshav/agent/livekit_worker.py), [evals/benchmark_voice.py](file:///c:/Users/krish/OneDrive/Desktop/keshav/evals/benchmark_voice.py), [.env.example](file:///c:/Users/krish/OneDrive/Desktop/keshav/.env.example), [tests/test_livekit.py](file:///c:/Users/krish/OneDrive/Desktop/keshav/tests/test_livekit.py), [GEMINI.md](file:///c:/Users/krish/OneDrive/Desktop/keshav/GEMINI.md), [history.txt](file:///c:/Users/krish/OneDrive/Desktop/keshav/history.txt). *(Full working-tree diff from `fc002ed` spans `49` modified files in `git diff --stat`, including prior bug-fix and upgrade work carried cleanly from working tree onto `voice-latency-diagnosis`.)*

Pre-doc pytest run observed (`.\.venv\Scripts\python.exe -m pytest -v --tb=short`):
```text
collected 128 items
...
======================= 128 passed in 112.88s (0:01:52) =======================
```
*(Final post-doc pytest & `evals.run_suite` verification executed immediately after finalizing `REPORT_v2.md`, `GEMINI.md`, and `history.txt`.)*
