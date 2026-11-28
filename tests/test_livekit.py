"""Unit and integration tests for LiveKit WebRTC endpoints and agent worker."""

import os
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from agent.main import app


def test_livekit_status_unconfigured():
    client = TestClient(app)
    with patch.dict(os.environ, {"LIVEKIT_URL": "", "LIVEKIT_API_KEY": "", "LIVEKIT_API_SECRET": ""}):
        res = client.get("/api/livekit/status")
        assert res.status_code == 200
        data = res.json()
        assert data["configured"] is False
        assert data["url"] is None


def test_livekit_token_unconfigured():
    client = TestClient(app)
    with patch.dict(os.environ, {"LIVEKIT_URL": "", "LIVEKIT_API_KEY": "", "LIVEKIT_API_SECRET": ""}):
        res = client.get("/api/livekit/token")
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is False
        assert "not configured" in data["error"].lower()


def test_livekit_status_and_token_configured():
    client = TestClient(app)
    with patch.dict(os.environ, {
        "LIVEKIT_URL": "wss://nexus-demo.livekit.cloud",
        "LIVEKIT_API_KEY": "API12345678901234567890",
        "LIVEKIT_API_SECRET": "secretsecretsecret12345678901234567890"
    }):
        # Status
        res_s = client.get("/api/livekit/status")
        assert res_s.status_code == 200
        assert res_s.json()["configured"] is True
        assert res_s.json()["url"] == "wss://nexus-demo.livekit.cloud"

        # Token
        res_t = client.get("/api/livekit/token?room=custom-room&name=Tester")
        assert res_t.status_code == 200
        data = res_t.json()
        assert data["success"] is True
        assert data["room"] == "custom-room"
        assert data["url"] == "wss://nexus-demo.livekit.cloud"
        assert isinstance(data["token"], str)
        assert len(data["token"]) > 50


def test_livekit_tools_instantiation():
    """Verify that all livekit tools import and wrap properly."""
    from agent.livekit_worker import LIVEKIT_TOOLS
    assert len(LIVEKIT_TOOLS) >= 7
    tool_names = [t.info.name for t in LIVEKIT_TOOLS]
    assert "web_search" in tool_names
    assert "calculator" in tool_names
    assert "send_email" in tool_names
    assert "open_app" in tool_names
    assert "send_whatsapp_message" in tool_names


@pytest.mark.asyncio
async def test_local_edge_tts_stream_adapter_real_streaming():
    """Verify that LocalEdgeTTS properly streams audio through LiveKit StreamAdapter without raising NotImplementedError."""
    from livekit.agents import tts
    from agent.local_voice import LocalEdgeTTS

    edge = LocalEdgeTTS()
    adapter = tts.StreamAdapter(tts=edge)
    stream = adapter.stream()
    assert stream is not None
    stream.push_text("Unit test audio synthesis.")
    stream.flush()
    stream.end_input()
    frames = []
    async for f in stream:
        frames.append(f)
    assert len(frames) > 0


@pytest.mark.asyncio
async def test_livekit_tool_pleasantry_guard():
    """Verify that conversational pleasantries do not trigger unconstrained web searches in LiveKit."""
    from agent.livekit_worker import web_search

    res = await web_search("hello")
    assert "listening" in res.lower()

    res2 = await web_search("let me take a look")
    assert "listening" in res2.lower()


@pytest.mark.asyncio
async def test_livekit_send_email_validation():
    """Verify that send_email rejects invalid/placeholder addresses and normalizes spoken emails."""
    from agent.livekit_worker import send_email
    from agent.tools.email import normalize_spoken_email

    res = await send_email("invalid-address", "test description")
    assert "valid" in res.lower()

    res_dummy = await send_email("recipient@example.com", "test description", recipient_name="John Doe")
    assert "valid email address" in res_dummy.lower()

    assert normalize_spoken_email("rohit at the red gmail dot com") == "rohit@gmail.com"


@pytest.mark.asyncio
async def test_livekit_local_whisper_no_metadata_errors():
    """Verify LocalWhisperSTT handles 48kHz stereo AudioFrame without PyAV metadata_errors."""
    import numpy as np
    import livekit.rtc as rtc
    from agent.local_voice import LocalWhisperSTT, transcribe_audio_local

    stt_engine = LocalWhisperSTT("tiny.en")
    pcm = np.zeros(48000 * 2, dtype=np.int16)
    frame = rtc.AudioFrame(
        data=pcm.tobytes(),
        sample_rate=48000,
        num_channels=2,
        samples_per_channel=48000,
    )
    ev = await stt_engine._recognize_impl(frame)
    assert ev.alternatives[0].text == ""
    assert transcribe_audio_local(frame.to_wav_bytes(), "tiny.en") == ""


@pytest.mark.asyncio
async def test_livekit_workshop_agents_and_consent_tasks():
    """Verify FallbackAdapter builder, AgentTask consent tasks, and specialized handoff agents."""
    from livekit.plugins import silero
    from agent.livekit_worker import (
        ActionConsentTask,
        CollectConsentTask,
        EscalationSpecialistAgent,
        LIVEKIT_TOOLS,
        NewsBriefingAgent,
        NexusVoiceAgent,
        _build_resilient_engines,
    )

    tool_names = [t.info.name for t in LIVEKIT_TOOLS]
    assert "get_live_news" in tool_names

    vad = silero.VAD.load()
    stt_e, llm_e, tts_e = _build_resilient_engines(vad)
    assert stt_e is not None and llm_e is not None and tts_e is not None

    assert NexusVoiceAgent() is not None
    assert NewsBriefingAgent(topic="technology") is not None
    assert EscalationSpecialistAgent(reason="test") is not None
    assert CollectConsentTask() is not None
    assert ActionConsentTask("send email") is not None


def test_realtime_news_and_updates_endpoints():
    """Verify /api/news, /api/updates/publish, and /api/metrics/livekit endpoints."""
    client = TestClient(app)
    pub = client.post("/api/updates/publish", json={
        "event_type": "METRICS_UPDATE",
        "data": {"turn_latency_ms": 312.5, "eou_ms": 120.0, "llm_ttft_ms": 110.0, "tts_ttfb_ms": 82.5},
    })
    assert pub.status_code == 200
    assert pub.json()["success"] is True

    m = client.get("/api/metrics/livekit")
    assert m.status_code == 200
    assert m.json()["count"] >= 1
    assert m.json()["avg_turn_latency_ms"] is not None

    with patch("agent.tools.search._fetch_google_news_rss", return_value=[{
        "title": "Sample Live Headline",
        "snippet": "Sample Live Headline details",
        "source": "https://example.com/news",
        "publisher": "Example News",
        "published_at": "Fri, 27 Nov 2026 15:00:00 GMT",
        "relative_time": "5m ago",
    }]):
        news_res = client.get("/api/news?topic=technology&limit=3")
        assert news_res.status_code == 200
        data = news_res.json()
        assert data["success"] is True
        assert data["news_items"][0]["publisher"] == "Example News"


def test_ollama_nested_tool_args_unwrapping():
    """Verify nested Ollama tool-call parameter wrappers and stringified ints are normalized cleanly."""
    from agent.main import _filter_handler_kwargs, _parse_tool_call_args
    from agent.tools.search import get_live_news

    raw = '{"type": "function", "function": "get_live_news", "parameters": {"topic": "technology", "extra": 1}}'
    parsed = _parse_tool_call_args(raw)
    assert parsed == {"topic": "technology", "extra": 1}
    filtered = _filter_handler_kwargs(get_live_news, parsed)
    assert filtered == {"topic": "technology"}

    with patch("agent.tools.search._fetch_google_news_rss", return_value=[{
        "title": "Tech Headline",
        "snippet": "Tech Headline",
        "source": "https://example.com",
        "publisher": "TechSite",
        "published_at": "",
        "relative_time": "2m ago",
    }]):
        res = get_live_news(topic="technology", max_results="4")
        assert res["success"] is True
        assert res["count"] == 1


@pytest.mark.asyncio
async def test_piper_offline_tts_and_fallback_adapter():
    """Verify offline Piper TTS produces WAV and streams PCM frames inside LiveKit FallbackAdapter."""
    from livekit.agents import tts
    from agent.local_voice import LocalPiperTTS, LocalEdgeTTS, synthesize_speech_local_with_format_async

    piper_tts = LocalPiperTTS()
    if piper_tts.is_available:
        audio_bytes, fmt = await synthesize_speech_local_with_format_async("Hello Krish.")
        assert fmt == "wav"
        assert audio_bytes[:4] == b"RIFF"

        edge_tts = LocalEdgeTTS()
        fb = tts.FallbackAdapter([piper_tts, edge_tts], max_retry_per_tts=1, sample_rate=piper_tts.sample_rate)
        sa = tts.StreamAdapter(tts=fb)
        frames = []
        async with sa.synthesize("Testing offline synthesis.") as stream:
            async for ev in stream:
                frames.append(ev.frame)
        await sa.aclose()
        await fb.aclose()
        assert len(frames) >= 1
        assert frames[0].sample_rate == piper_tts.sample_rate


def test_uncalled_email_recipient_extraction():
    """Ensure fallback email parser extracts target recipient rather than 'email to'."""
    from agent.main import _dispatch_uncalled_tool_intent

    out = _dispatch_uncalled_tool_intent("send an email to john")
    assert out is not None
    assert out["tool"] == "send_email"
    assert out["args"].get("to") == "john"


@pytest.mark.asyncio
async def test_livekit_calculator_time_and_qwen3_fallback_config(monkeypatch):
    """Verify LiveKit calculator/time tools and ensure qwen3 fallback keeps think=False."""
    from livekit.plugins import silero
    from agent.livekit_worker import calculator, get_current_time, _build_resilient_engines

    calc_out = await calculator("18% gst on 1250")
    assert "225" in calc_out

    time_out = await get_current_time("Asia/Kolkata")
    assert "Asia/Kolkata" in time_out

    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "ollama")
    monkeypatch.setenv("OPENAI_MODEL", "qwen2.5:1.5b")
    monkeypatch.setenv("FALLBACK_LLM_MODEL", "qwen3:1.7b")

    vad = silero.VAD.load()
    _, llm_engine, _ = _build_resilient_engines(vad)
    # FallbackAdapter holds primary and fallback LLM instances
    fallback_llms = getattr(llm_engine, "_llm_instances", None) or getattr(llm_engine, "llms", [])
    qwen3_llms = [m for m in fallback_llms if getattr(m, "model", "") == "qwen3:1.7b"]
    if qwen3_llms:
        extra_opts = getattr(qwen3_llms[0], "_opts", None)
        extra_body = getattr(extra_opts, "extra_body", None) or {}
        assert extra_body.get("think") is False


@pytest.mark.asyncio
async def test_voice_upgrade_v2_config_telemetry_and_strict_local(monkeypatch, tmp_path):
    """Verify v2 env-driven STT config, strict local mode, per-turn TurnTimer isolation, and WER/CER."""
    from agent.local_voice import (
        LocalPiperTTS,
        _stt_beam,
        _stt_device,
        _stt_initial_prompt,
        _stt_language,
        _stt_model_size,
        is_strict_local_mode,
        synthesize_speech_local_with_format_async,
    )
    from agent.voice_telemetry import TurnTimer, compute_latency_percentiles
    from evals.benchmark_voice import compute_cer, compute_wer, record_hardware_profile

    # Default profile preserves base.en, en, beam=1, cpu and removes personal names from default prompt
    assert _stt_model_size() == "base.en"
    assert _stt_language() == "en"
    assert _stt_beam() == 1
    assert _stt_device() == "cpu"
    default_prompt = _stt_initial_prompt() or ""
    assert "keshav" not in default_prompt.lower()
    assert "rohit" not in default_prompt.lower()

    # Env-driven overrides work dynamically
    monkeypatch.setenv("STT_LANGUAGE", "auto")
    monkeypatch.setenv("WHISPER_MODEL_SIZE", "small")
    monkeypatch.setenv("WHISPER_BEAM_SIZE", "3")
    monkeypatch.setenv("STT_INITIAL_PROMPT", "none")
    assert _stt_language() is None
    assert _stt_model_size() == "small"
    assert _stt_beam() == 3
    assert _stt_initial_prompt() is None

    # STRICT_LOCAL_MODE blocks networked Edge-TTS fallback when Piper returns empty
    monkeypatch.setenv("STRICT_LOCAL_MODE", "true")
    assert is_strict_local_mode() is True
    with patch("agent.local_voice.synthesize_speech_piper_wav", return_value=b""), \
         patch("agent.local_voice.synthesize_speech_local_async") as mock_edge:
        audio_b, fmt = await synthesize_speech_local_with_format_async("hello world")
        assert audio_b == b""
        assert fmt == "wav"
        mock_edge.assert_not_called()

    # TurnTimer keeps each turn isolated and records JSONL cleanly
    log_file = tmp_path / "turns.jsonl"
    t1 = TurnTimer(speech_id="speech-1111")
    t1.set_stage_ms("eou_ms", 420.0)
    t1.set_stage_ms("stt_ms", 680.0)
    t1.set_stage_ms("llm_ttft_ms", 310.0)
    t1.set_stage_ms("tts_ttfb_ms", 190.0)
    row1 = t1.record(path=log_file)
    assert row1["server_ttfa_ms"] == 920.0

    t2 = TurnTimer(speech_id="speech-2222")
    t2.set_stage_ms("eou_ms", 500.0)
    snap2 = t2.snapshot()
    assert snap2["llm_ttft_ms"] == 0.0
    assert snap2["tts_ttfb_ms"] == 0.0
    assert log_file.exists() and len(log_file.read_text(encoding="utf-8").strip().splitlines()) == 1

    # Percentiles and /api/metrics/livekit P50/P95
    stats = compute_latency_percentiles([100.0, 200.0, 300.0, 400.0, 500.0])
    assert stats["p50_ms"] == 300.0
    assert stats["p95_ms"] == 500.0

    client = TestClient(app)
    res = client.get("/api/metrics/livekit")
    assert res.status_code == 200
    body = res.json()
    assert "p50_turn_latency_ms" in body and "p95_turn_latency_ms" in body

    # Hardware profile + WER/CER helpers
    hw = record_hardware_profile()
    assert hw["hardware_tier"] in {"A_GPU_READY", "B_MODERN_CPU_16GB", "C_MODEST_CPU_8GB", "D_LOW_MEMORY"}
    assert compute_wer("Hello, world!", "hello world") == 0.0
    assert compute_cer("open gmail", "open gmal") > 0.0
    assert isinstance(LocalPiperTTS(), LocalPiperTTS)


def test_voice_diagnosis_tools_entities_manifest_and_recorder(monkeypatch, tmp_path):
    """Verify new cpu_threads/vad_filter knobs, resource snapshot, entity scoring, manifest loader, and recorder."""
    import numpy as np
    from agent.local_voice import _stt_cpu_threads, _stt_vad_filter
    from agent.voice_telemetry import TurnTimer, read_system_resource_snapshot
    from evals.benchmark_voice import (
        compute_entity_accuracy,
        get_wav_duration_s,
        load_manifest,
    )
    from evals.record_voice_clips import (
        append_manifest_row,
        run_recording_session,
        save_pcm_mono_16k_wav,
    )

    # Defaults untouched
    assert _stt_vad_filter() is True
    default_threads = _stt_cpu_threads()
    assert default_threads >= 2

    monkeypatch.setenv("WHISPER_CPU_THREADS", "6")
    monkeypatch.setenv("WHISPER_VAD_FILTER", "off")
    assert _stt_cpu_threads() == 6
    assert _stt_vad_filter() is False

    # TurnTimer exposes endpoint_ms / stt_final_ms aliases alongside eou_ms / stt_ms
    t = TurnTimer(speech_id="diag123456")
    t.set_stage_ms("eou_ms", 600.0)
    t.set_stage_ms("stt_ms", 950.0)
    snap = t.snapshot()
    assert snap["endpoint_ms"] == 600.0
    assert snap["stt_final_ms"] == 950.0

    # Resource snapshot returns RAM / commit / RSS metrics on Windows without error
    res_snap = read_system_resource_snapshot()
    assert "ram_total_gb" in res_snap
    assert res_snap.get("process_peak_rss_mb", 0) > 0

    # Entity accuracy scores numbers, percentages, amounts, emails, and names separately from WER
    ent_ok = compute_entity_accuracy(
        "Calculate 18 percent GST on 1000 rupees.",
        "Calculate 18% GST on 1000 Rupees.",
    )
    assert ent_ok["entity_accuracy"] == 1.0

    ent_miss = compute_entity_accuracy(
        "Send an email to rohit at gmail dot com.",
        "sent an email to someone at example.",
    )
    assert ent_miss["entity_accuracy"] == 0.0

    # Manifest loading (JSONL & CSV) and WAV duration calculation
    wav_file = tmp_path / "sample.wav"
    dur = save_pcm_mono_16k_wav(wav_file, np.zeros(16000, dtype=np.int16), sample_rate=16000)
    assert dur == 1.0
    assert get_wav_duration_s(wav_file.read_bytes()) == 1.0

    jsonl_m = tmp_path / "manifest.jsonl"
    append_manifest_row(jsonl_m, wav_file, "Open Gmail", "clean_english", "tester", synthetic=False)
    loaded = load_manifest(jsonl_m)
    assert len(loaded) == 1
    assert loaded[0]["synthetic"] is False
    assert loaded[0]["speaker"] == "tester"

    csv_m = tmp_path / "manifest.csv"
    csv_m.write_text("wav_path,reference_text,category,speaker,synthetic\nsample.wav,Open Gmail,clean,piper,yes\n", encoding="utf-8")
    loaded_csv = load_manifest(csv_m)
    assert loaded_csv[0]["synthetic"] is True

    # Interactive recording helper creates 16 kHz mono WAVs and manifest rows using mocked input/audio
    prompts_json = tmp_path / "prompts.json"
    prompts_json.write_text('[{"id": "T1", "category": "clean", "text": "Hello Nexus"}]', encoding="utf-8")
    answers = iter(["", ""])
    written = run_recording_session(
        prompts_path=prompts_json,
        out_dir=tmp_path / "human",
        speaker="krish_test",
        record_fn=lambda stop_ev, sr: np.ones((8000, 1), dtype=np.int16) * 500,
        input_fn=lambda _p: next(answers),
    )
    assert len(written) == 1
    assert written[0]["synthetic"] is False
    assert (tmp_path / "human" / "krish_test_T1.wav").exists()

    # TurnTimer records memory pressure fields (ram_available_gb / commit_used_gb)
    assert "ram_available_gb" in snap and "commit_used_gb" in snap

    # Held-out prompts have zero token overlap with STT_INITIAL_PROMPT vocabulary
    from pathlib import Path
    from evals.benchmark_voice import verify_heldout_prompt_isolation
    assert verify_heldout_prompt_isolation(Path("bench_clips/heldout_prompts.json")) == []

    # Prewarm helpers & guarded CUDA DLL helper stay opt-in without altering defaults
    from types import SimpleNamespace
    from agent.local_voice import (
        _extract_valid_whisper_text,
        _is_repetitive_hallucination,
        _register_cuda_dll_paths,
        _stt_initial_prompt,
        prewarm_stt_decode,
    )
    from agent.livekit_worker import _env_flag, _env_float
    assert _env_flag("PREWARM_OLLAMA", default=False) is False
    assert _env_flag("PREWARM_STT_DECODE", default=False) is False
    assert _env_float("AEC_WARMUP_DURATION", 1.5) == 1.5
    assert _stt_initial_prompt() is None
    assert isinstance(_register_cuda_dll_paths(), list)
    assert prewarm_stt_decode("tiny.en", duration_s=0.6) >= 0.0

    # Whisper hallucination & repetition filters drop compression loops and low-logprob gibberish
    assert _is_repetitive_hallucination("Paracetamol, Paracetamol, Paracetamol, Paracetamol") is True
    assert _is_repetitive_hallucination("8-8-1-2-2-2-2-2-2-2") is True
    assert _is_repetitive_hallucination("Open Gmail and check emails") is False

    filtered = _extract_valid_whisper_text([
        SimpleNamespace(text="Mother of the Lord.", avg_logprob=-1.50, compression_ratio=0.95, no_speech_prob=0.10),
        SimpleNamespace(text="Paracetamol, Paracetamol, Paracetamol, Paracetamol", avg_logprob=-0.45, compression_ratio=20.8, no_speech_prob=0.05),
        SimpleNamespace(text="What time is it in London?", avg_logprob=-0.12, compression_ratio=0.92, no_speech_prob=0.01),
    ])
    assert filtered == "What time is it in London?"

