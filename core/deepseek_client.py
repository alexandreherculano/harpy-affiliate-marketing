"""DeepSeek API client for LLM-powered skill execution."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from core.config import Config
from core.logger import get_logger

logger = get_logger()


@dataclass
class ChatMessage:
    role: str
    content: str


@dataclass
class ChatResponse:
    content: str
    usage: Usage
    model: str
    finish_reason: str = "stop"


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class DeepSeekClient:
    config: Config
    _http: httpx.Client = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self._http is None:
            self._http = httpx.Client(
                base_url=self.config.deepseek_base_url,
                headers={
                    "Authorization": f"Bearer {self.config.deepseek_api_key}",
                    "Content-Type": "application/json",
                },
                timeout=120.0,
            )

    def chat(
        self,
        messages: list[dict[str, str]],
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        retries: int = 3,
    ) -> ChatResponse:
        payload: dict[str, Any] = {
            "model": self.config.deepseek_model,
            "messages": self._build_messages(messages, system_prompt),
            "temperature": temperature or self.config.deepseek_temperature,
            "max_tokens": max_tokens or self.config.deepseek_max_tokens,
        }

        for attempt in range(retries):
            try:
                response = self._http.post("/chat/completions", json=payload)
                response.raise_for_status()
                data = response.json()
                return self._parse_response(data)
            except httpx.HTTPStatusError as e:
                logger.warning(
                    "DeepSeek API error (attempt %d/%d): %s",
                    attempt + 1,
                    retries,
                    e,
                )
                if attempt == retries - 1:
                    raise
                time.sleep(2 ** attempt)
            except httpx.RequestError as e:
                logger.warning(
                    "DeepSeek request error (attempt %d/%d): %s",
                    attempt + 1,
                    retries,
                    e,
                )
                if attempt == retries - 1:
                    raise
                time.sleep(2 ** attempt)

        raise RuntimeError("Unexpected: exhausted retries")

    def chat_with_structured_output(
        self,
        messages: list[dict[str, str]],
        system_prompt: str | None = None,
        temperature: float | None = None,
    ) -> ChatResponse:
        response = self.chat(messages, system_prompt=system_prompt, temperature=temperature)

        content = response.content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            content = "\n".join(lines)

        return ChatResponse(
            content=content,
            usage=response.usage,
            model=response.model,
            finish_reason=response.finish_reason,
        )

    @staticmethod
    def _build_messages(
        messages: list[dict[str, str]],
        system_prompt: str | None = None,
    ) -> list[dict[str, str]]:
        result: list[dict[str, str]] = []
        if system_prompt:
            result.append({"role": "system", "content": system_prompt})
        result.extend(messages)
        return result

    @staticmethod
    def _parse_response(data: dict[str, Any]) -> ChatResponse:
        choice = data["choices"][0]
        usage_data = data.get("usage", {})
        return ChatResponse(
            content=choice["message"]["content"],
            usage=Usage(
                prompt_tokens=usage_data.get("prompt_tokens", 0),
                completion_tokens=usage_data.get("completion_tokens", 0),
                total_tokens=usage_data.get("total_tokens", 0),
            ),
            model=data.get("model", "deepseek-chat"),
            finish_reason=choice.get("finish_reason", "stop"),
        )

    def close(self) -> None:
        self._http.close()
