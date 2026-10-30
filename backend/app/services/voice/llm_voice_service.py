"""Conversational LLM response generator for Voice."""

import logging
from typing import Dict, List, Optional
from openai import AsyncOpenAI
from app.core.config import settings
from app.services.voice.base import BaseLLMVoiceService

logger = logging.getLogger("nexus.voice.llm")

DEFAULT_VOICE_SYSTEM_PROMPT = """You are Nexus, an intelligent, helpful agentic productivity assistant.
You are communicating via natural voice.
- Keep your answers concise, direct, and conversational (typically 1 to 3 sentences unless asked for details).
- Do not use markdown syntax, code blocks, bullet points, or complex symbols in your voice response, as this will be read aloud by Text-to-Speech.
- Speak naturally and warmly.
"""


class OpenAILLMVoiceService(BaseLLMVoiceService):
    """OpenAI Chat Completion provider for voice interaction."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.OPENAI_API_KEY
        self.client = AsyncOpenAI(api_key=self.api_key) if self.api_key else None

    async def generate_response(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
    ) -> str:
        if not self.client:
            logger.warning("OpenAI API key not set, falling back to mock LLM")
            return await MockLLMVoiceService().generate_response(messages, system_prompt)

        prompt = system_prompt or DEFAULT_VOICE_SYSTEM_PROMPT
        formatted_messages = [{"role": "system", "content": prompt}]
        formatted_messages.extend(messages)

        try:
            response = await self.client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=formatted_messages,
                temperature=0.7,
                max_tokens=300,
            )
            reply = response.choices[0].message.content or ""
            return reply.strip()
        except Exception as e:
            logger.error(f"LLM voice generation failed: {e}")
            raise


class MockLLMVoiceService(BaseLLMVoiceService):
    """Mock LLM response generator for testing."""

    async def generate_response(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
    ) -> str:
        last_message = messages[-1]["content"] if messages else ""
        return f"I received your message: '{last_message}'. I am ready to help you with your tasks, calendar, and email."


def get_llm_voice_service() -> BaseLLMVoiceService:
    """Factory to retrieve configured LLM service."""
    if settings.OPENAI_API_KEY:
        return OpenAILLMVoiceService()
    return MockLLMVoiceService()
