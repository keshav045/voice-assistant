"""Audio recording, speech-to-text (Whisper), and text-to-speech (TTS) engine."""

import io
import logging
import os
import re
import subprocess
import threading
import time
from typing import Optional, Tuple

import numpy as np
import scipy.io.wavfile as wavfile
import sounddevice as sd
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("voice_assistant.voice")

DEFAULT_SAMPLERATE = 16000
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")


def clean_spoken_text(text: str) -> str:
    """Clean text for natural speech synthesis by removing markdown and formatting artifacts."""
    if not text:
        return ""
    # Remove markdown headers, bold, italics, links, backticks
    clean = re.sub(r"#+\s*", "", text)
    clean = re.sub(r"\*\*([^*]+)\*\*", r"\1", clean)
    clean = re.sub(r"\*([^*]+)\*", r"\1", clean)
    clean = re.sub(r"`([^`]+)`", r"\1", clean)
    clean = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", clean)
    clean = re.sub(r"https?://\S+", "", clean)
    clean = re.sub(r"[-*]\s+", "", clean)
    # Remove emojis and special symbols (preserve standard punctuation: .,!?'":-)
    clean = re.sub(r"[^\w\s.,!?'\":-]", "", clean)
    # Normalize spaces
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def record_audio_push_to_talk(stop_event: threading.Event, samplerate: int = DEFAULT_SAMPLERATE) -> np.ndarray:
    """Record audio from the default microphone until stop_event is set."""
    audio_frames = []

    def callback(indata, frames, time_info, status):
        if status:
            logger.debug(f"Input stream status: {status}")
        audio_frames.append(indata.copy())

    with sd.InputStream(samplerate=samplerate, channels=1, dtype="int16", callback=callback):
        while not stop_event.is_set():
            time.sleep(0.05)

    if not audio_frames:
        return np.zeros((0, 1), dtype=np.int16)

    return np.concatenate(audio_frames, axis=0)


def calibrate_ambient_noise(duration: float = 0.5, samplerate: int = DEFAULT_SAMPLERATE) -> float:
    """Measure the background ambient noise level in RMS amplitude."""
    samples = int(duration * samplerate)
    rec = sd.rec(samples, samplerate=samplerate, channels=1, dtype="int16")
    sd.wait()
    rms = np.sqrt(np.mean(rec.astype(np.float32) ** 2))
    return float(rms)


def record_audio_vad(
    silence_timeout: float = 1.3,
    samplerate: int = DEFAULT_SAMPLERATE,
    max_duration: float = 20.0,
    stop_event: Optional[threading.Event] = None
) -> np.ndarray:
    """Record audio automatically using Voice Activity Detection (silence detection).
    
    Begins recording when speech is detected and stops after silence_timeout seconds of silence.
    """
    chunk_duration = 0.1  # 100ms chunks
    chunk_samples = int(chunk_duration * samplerate)
    
    # Calibrate ambient noise
    ambient_rms = calibrate_ambient_noise(0.4, samplerate=samplerate)
    threshold = max(600.0, ambient_rms * 2.2)

    audio_frames = []
    is_speaking = False
    silence_elapsed = 0.0
    start_time = time.time()

    with sd.InputStream(samplerate=samplerate, channels=1, dtype="int16") as stream:
        while True:
            if stop_event and stop_event.is_set():
                break
            if time.time() - start_time > max_duration:
                break

            chunk, _ = stream.read(chunk_samples)
            chunk_rms = np.sqrt(np.mean(chunk.astype(np.float32) ** 2))

            if chunk_rms > threshold:
                is_speaking = True
                silence_elapsed = 0.0
                audio_frames.append(chunk)
            elif is_speaking:
                audio_frames.append(chunk)
                silence_elapsed += chunk_duration
                if silence_elapsed >= silence_timeout:
                    # User finished speaking
                    break
            else:
                # Still waiting for speech to begin
                time.sleep(0.01)

    if not audio_frames:
        return np.zeros((0, 1), dtype=np.int16)

    return np.concatenate(audio_frames, axis=0)


def transcribe_audio(audio_data: np.ndarray, samplerate: int = DEFAULT_SAMPLERATE) -> str:
    """Transcribe audio numpy array into text using OpenAI Whisper."""
    if audio_data.size == 0:
        return ""

    # Check for empty audio / silence
    max_amp = np.max(np.abs(audio_data))
    if max_amp < 300:
        return ""

    # Convert PCM to in-memory WAV
    buf = io.BytesIO()
    wavfile.write(buf, samplerate, audio_data)
    buf.name = "input_speech.wav"
    buf.seek(0)

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key or api_key.startswith("your-"):
        logger.warning("No valid OpenAI API key found for Whisper.")
        return ""

    try:
        client = OpenAI(api_key=api_key)
        transcription = client.audio.transcriptions.create(
            model="whisper-1",
            file=buf,
            language="en"
        )
        return transcription.text.strip()
    except Exception as e:
        logger.error(f"Whisper transcription error: {e}")
        return ""


def speak_text(text: str, voice: str = "alloy", use_openai: bool = True) -> None:
    """Speak text aloud through speaker/headphones.
    
    Uses OpenAI high-fidelity TTS-1 with PCM direct playback, or falls back to
    Windows native speech synthesis.
    """
    clean = clean_spoken_text(text)
    if not clean:
        return

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if use_openai and api_key and not api_key.startswith("your-"):
        try:
            client = OpenAI(api_key=api_key)
            response = client.audio.speech.create(
                model="tts-1",
                voice=voice,
                input=clean,
                response_format="pcm"
            )
            pcm_bytes = response.content
            audio_array = np.frombuffer(pcm_bytes, dtype=np.int16)
            sd.play(audio_array, samplerate=24000)
            sd.wait()
            return
        except Exception as e:
            logger.warning(f"OpenAI TTS playback failed: {e}. Falling back to Windows native speech.")

    # Fallback: Windows Speech Synthesis (.NET System.Speech / SAPI)
    try:
        escaped = clean.replace("'", "''").replace('"', '')
        cmd = [
            "powershell",
            "-NoProfile",
            "-Command",
            f"Add-Type -AssemblyName System.Speech; (New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak('{escaped}')"
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        logger.error(f"Windows TTS fallback error: {e}")
