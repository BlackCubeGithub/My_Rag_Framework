"""
Generator Module
Handles LLM-based text generation
"""
import json
import time
from typing import Optional, AsyncIterator
import structlog
from openai import AsyncOpenAI
from backend.config import settings

logger = structlog.get_logger()


class Generator:
    """LLM text generator using OpenAI-compatible API"""

    def __init__(
        self,
        model: str = "gpt-4-turbo",
        api_key: str = "",
        base_url: str = "https://api.openai.com/v1",
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

        self.client = AsyncOpenAI(
            api_key=api_key or settings.LLM_API_KEY or "dummy",
            base_url=base_url or settings.LLM_BASE_URL,
        )

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> str:
        """Generate text from prompt"""
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": prompt})

        start_time = time.time()

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature or self.temperature,
                max_tokens=max_tokens or self.max_tokens,
                **kwargs,
            )

            latency = (time.time() - start_time) * 1000

            logger.info(
                "generation_completed",
                model=self.model,
                latency_ms=latency,
                tokens=response.usage.total_tokens if response.usage else 0,
            )

            return response.choices[0].message.content or ""

        except Exception as e:
            logger.error("generation_failed", error=str(e))
            raise

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        **kwargs,
    ) -> AsyncIterator[str]:
        """Generate text with streaming"""
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": prompt})

        try:
            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature or self.temperature,
                max_tokens=self.max_tokens,
                stream=True,
                **kwargs,
            )

            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

        except Exception as e:
            logger.error("stream_generation_failed", error=str(e))
            raise

    async def batch_generate(
        self,
        prompts: list[str],
        system_prompt: Optional[str] = None,
    ) -> list[str]:
        """Generate multiple responses in parallel"""
        import asyncio

        tasks = [
            self.generate(prompt, system_prompt=system_prompt)
            for prompt in prompts
        ]

        return await asyncio.gather(*tasks)

    async def generate_structured(
        self,
        prompt: str,
        response_format: type,
        system_prompt: Optional[str] = None,
    ) -> dict:
        """Generate structured JSON response"""
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": prompt})

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )

            content = response.choices[0].message.content or "{}"
            return json.loads(content)

        except Exception as e:
            logger.error("structured_generation_failed", error=str(e))
            raise
