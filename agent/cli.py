"""Interactive Desktop Voice Assistant CLI.

Allows speaking into your microphone and hearing the spoken response aloud,
with live LLM reasoning, web search, sports scores, calendar, and task management.

Modes:
  - Push-to-Talk (Default): Press Enter to start speaking, speak, press Enter to stop.
  - Hands-Free Auto (--auto): Continuously listens with Voice Activity Detection.
  - Text input: Type anytime at the prompt.
"""

import argparse
import asyncio
import os
import sys
import threading
import uuid
from typing import Optional

from agent.main import process_user_turn
from agent.voice import (
    clean_spoken_text,
    record_audio_push_to_talk,
    record_audio_vad,
    transcribe_audio,
    speak_text,
)


def record_push_to_talk() -> str:
    """Record speech via Push-to-Talk and transcribe using Whisper."""
    stop_event = threading.Event()
    recorded_holder = []

    def target():
        audio = record_audio_push_to_talk(stop_event)
        recorded_holder.append(audio)

    rec_thread = threading.Thread(target=target, daemon=True)
    rec_thread.start()

    print("\n[Listening] Recording started. Speak into your microphone now.")
    print("            Press [Enter] when finished speaking...")
    try:
        input()
    except (KeyboardInterrupt, EOFError):
        pass

    stop_event.set()
    rec_thread.join(timeout=3.0)

    if not recorded_holder or recorded_holder[0].size == 0:
        return ""

    print("[Transcribing speech with Whisper...]")
    text = transcribe_audio(recorded_holder[0])
    return text.strip()


def record_hands_free() -> str:
    """Record speech automatically via Voice Activity Detection."""
    print("\n[Listening] Speak into your microphone now...")
    audio = record_audio_vad(silence_timeout=1.3, max_duration=20.0)
    if audio.size == 0:
        return ""
    print("[Transcribing speech with Whisper...]")
    text = transcribe_audio(audio)
    return text.strip()


async def execute_turn(user_text: str, session_id: str, voice: str = "alloy", speak: bool = True) -> str:
    """Process user turn through agent pipeline, display logs, and speak aloud."""
    print(f"\n[You]: {user_text}")
    print("[Assistant is analyzing & querying live tools...]")

    result = await process_user_turn(user_text, session_id)
    spoken = result.get("spoken_reply", "")
    tools = result.get("tool_calls_executed", [])
    latency = result.get("latency_ms", 0)

    # Display tool reasoning in terminal
    if tools:
        print(f"\n--- Live Tool Reasoning ({latency}ms) ---")
        for t in tools:
            tool_name = t.get("tool", "").upper()
            args = t.get("args", {})
            res = t.get("result", {})
            print(f"[*] Tool Executed: {tool_name}")
            print(f"    Args: {args}")
            if "results" in res:
                print(f"    Results Count: {len(res['results'])}")
                for r in res["results"][:2]:
                    title = r.get("title", "")
                    snip = r.get("snippet", "")
                    src = r.get("source", "")
                    print(f"    - {title}")
                    if snip and snip != title:
                        print(f"      {snip[:120]}...")
                    if src:
                        print(f"      Source: {src}")
            elif "spoken" in res:
                print(f"    Result: {res['spoken']}")
        print("----------------------------------------\n")

    # Display spoken reply
    print(f"[Nexus Voice Assistant]: {spoken}\n")

    # Speak aloud through speaker/headphones
    if speak and spoken:
        print("[Speaking result aloud...]")
        speak_text(spoken, voice=voice, use_openai=True)

    # Prompt if action requires confirmation
    if result.get("requires_confirmation"):
        print("[!] Confirmation required. Speak or type 'yes' to proceed, or 'no' to cancel.")

    return spoken


async def main():
    parser = argparse.ArgumentParser(description="Nexus Personal Voice Assistant")
    parser.add_argument("--auto", action="store_true", help="Hands-free mode using Voice Activity Detection")
    parser.add_argument("--mute", action="store_true", help="Mute audio output (terminal text only)")
    parser.add_argument("--voice", type=str, default="alloy", help="OpenAI TTS voice (alloy, echo, fable, onyx, nova, shimmer)")
    args = parser.parse_args()

    session_id = f"cli-{uuid.uuid4().hex[:8]}"
    speak = not args.mute
    auto_mode = args.auto

    print("=" * 65)
    print("   NEXUS PERSONAL VOICE ASSISTANT")
    print("   Voice-first, LLM-powered with Live Web & Sports Search")
    print(f"   Audio Input Mode:  {'Hands-Free (Auto-VAD)' if auto_mode else 'Push-to-Talk (Press Enter to Speak)'}")
    print(f"   Audio Output Mode: {'ON (Speaker / Headphones)' if speak else 'MUTED'}")
    print(f"   TTS Voice:         {args.voice}")
    print("   Commands:          Type 'exit' to quit, 'mode' to switch input mode.")
    print("=" * 65)

    if not auto_mode:
        print("\nTip: Press [Enter] on an empty prompt to start speaking with your microphone,")
        print("     or type your question directly.")

    while True:
        try:
            if auto_mode:
                user_text = record_hands_free()
                if not user_text:
                    continue
            else:
                prompt_line = input("\nNexus [Press Enter to Speak, or type] > ").strip()
                if prompt_line.lower() in ["exit", "quit", "q"]:
                    print("Exiting Voice Assistant. Goodbye!")
                    break
                if prompt_line.lower() == "mode":
                    auto_mode = not auto_mode
                    mode_name = "Hands-Free Auto-VAD" if auto_mode else "Push-to-Talk"
                    print(f"[Switched input mode to: {mode_name}]")
                    continue

                if not prompt_line:
                    # User pressed Enter -> Record voice
                    user_text = record_push_to_talk()
                    if not user_text:
                        print("[No clear speech detected. Please speak into your microphone and try again.]")
                        continue
                else:
                    user_text = prompt_line

            await execute_turn(user_text, session_id, voice=args.voice, speak=speak)

        except (KeyboardInterrupt, EOFError):
            print("\nExiting Voice Assistant. Goodbye!")
            break


if __name__ == "__main__":
    asyncio.run(main())
