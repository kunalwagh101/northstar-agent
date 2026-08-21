from __future__ import annotations

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import ValidationError

from app.domain.models import AgentTurn, ConversationMessage, ConversationSession

logger = logging.getLogger(__name__)


class LLMProviderError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ProviderResult:
    turn: AgentTurn
    provider: str
    input_tokens: int | None = None
    output_tokens: int | None = None


class AgentProvider(ABC):
    name: str

    @abstractmethod
    async def generate_turn(
        self,
        *,
        system_prompt: str,
        session: ConversationSession,
        user_message: str,
    ) -> ProviderResult:
        raise NotImplementedError


class OpenAICompatibleProvider(AgentProvider):
    name = "openai"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: int,
        max_retries: int,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("OPENAI_API_KEY is required when AI_PROVIDER=openai")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._max_retries = max_retries
        self._client = client or httpx.AsyncClient(timeout=timeout_seconds)
        self._owns_client = client is None

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    @staticmethod
    def _message_payload(messages: list[ConversationMessage]) -> list[dict[str, str]]:
        return [{"role": message.role.value, "content": message.content} for message in messages]

    async def generate_turn(
        self,
        *,
        system_prompt: str,
        session: ConversationSession,
        user_message: str,
    ) -> ProviderResult:
        messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        messages.extend(self._message_payload(session.messages[-30:]))
        messages.append({"role": "user", "content": user_message})

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": 600,
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        response: httpx.Response | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = await self._client.post(
                    f"{self._base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
            except httpx.HTTPError as exc:
                if attempt >= self._max_retries:
                    raise LLMProviderError("AI provider request failed") from exc
                await asyncio.sleep(0.25 * (2**attempt))
                continue

            if response.status_code < 400:
                break
            if response.status_code not in {408, 429, 500, 502, 503, 504}:
                raise LLMProviderError(f"AI provider returned HTTP {response.status_code}")
            if attempt >= self._max_retries:
                raise LLMProviderError(
                    f"AI provider unavailable after retries: {response.status_code}"
                )
            await asyncio.sleep(0.25 * (2**attempt))

        if response is None:  # pragma: no cover - defensive guard
            raise LLMProviderError("AI provider returned no response")

        try:
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            raw_turn = json.loads(content)
            turn = AgentTurn.model_validate(raw_turn)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError, ValidationError) as exc:
            logger.warning("invalid_provider_output", extra={"provider": self.name})
            raise LLMProviderError("AI provider returned an invalid structured response") from exc

        usage = body.get("usage", {})
        return ProviderResult(
            turn=turn,
            provider=f"openai:{self._model}",
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
        )
