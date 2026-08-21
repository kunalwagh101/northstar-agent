from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.domain.models import (
    AgentTurn,
    ConversationSession,
    Language,
    LeadUpdates,
)
from app.infrastructure.llm import (
    AgentProvider,
    LLMProviderError,
    OpenAICompatibleProvider,
    ProviderResult,
)
from app.main import create_app
from tests.conftest import send


def _response(content: str, status_code: int = 200) -> httpx.Response:
    return httpx.Response(
        status_code,
        json={
            "choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 25},
        },
    )


@pytest.mark.asyncio
async def test_openai_compatible_provider_parses_structured_turn() -> None:
    raw_turn = AgentTurn(
        reply="Northstar One is in Sector 79, Gurugram.",
        language=Language.ENGLISH,
        lead_updates=LeadUpdates(language=Language.ENGLISH),
    ).model_dump(mode="json")
    transport = httpx.MockTransport(lambda _: _response(json.dumps(raw_turn)))
    async with httpx.AsyncClient(transport=transport) as client:
        provider = OpenAICompatibleProvider(
            api_key="test-key",
            base_url="https://example.test/v1",
            model="test-model",
            timeout_seconds=2,
            max_retries=0,
            client=client,
        )
        result = await provider.generate_turn(
            system_prompt="system",
            session=ConversationSession(session_id="abc"),
            user_message="Where is it?",
        )
    assert result.turn.reply.endswith("Gurugram.")
    assert result.provider == "openai:test-model"
    assert result.input_tokens == 100
    assert result.output_tokens == 25


@pytest.mark.asyncio
async def test_openai_compatible_provider_rejects_invalid_output() -> None:
    transport = httpx.MockTransport(lambda _: _response("not-json"))
    async with httpx.AsyncClient(transport=transport) as client:
        provider = OpenAICompatibleProvider(
            api_key="test-key",
            base_url="https://example.test/v1",
            model="test-model",
            timeout_seconds=2,
            max_retries=0,
            client=client,
        )
        with pytest.raises(LLMProviderError, match="invalid structured response"):
            await provider.generate_turn(
                system_prompt="system",
                session=ConversationSession(session_id="abc"),
                user_message="hello",
            )


@pytest.mark.asyncio
async def test_openai_compatible_provider_rejects_non_retryable_http_error() -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(401, json={"error": "bad key"}))
    async with httpx.AsyncClient(transport=transport) as client:
        provider = OpenAICompatibleProvider(
            api_key="test-key",
            base_url="https://example.test/v1",
            model="test-model",
            timeout_seconds=2,
            max_retries=0,
            client=client,
        )
        with pytest.raises(LLMProviderError, match="HTTP 401"):
            await provider.generate_turn(
                system_prompt="system",
                session=ConversationSession(session_id="abc"),
                user_message="hello",
            )


class FailingProvider(AgentProvider):
    name = "failing-test-provider"

    async def generate_turn(
        self,
        *,
        system_prompt: str,
        session: ConversationSession,
        user_message: str,
    ) -> ProviderResult:
        del system_prompt, session, user_message
        raise LLMProviderError("simulated outage")


class UnsafeProvider(AgentProvider):
    name = "unsafe-test-provider"

    def __init__(self) -> None:
        self.calls = 0

    async def generate_turn(
        self,
        *,
        system_prompt: str,
        session: ConversationSession,
        user_message: str,
    ) -> ProviderResult:
        del system_prompt, session, user_message
        self.calls += 1
        return ProviderResult(
            turn=AgentTurn(
                reply="A special 2 BHK is confirmed at ₹90 lakh with discount.",
                language=Language.ENGLISH,
            ),
            provider=self.name,
        )


def test_provider_outage_uses_safe_fallback(
    settings: Settings,
    fixed_clock: Callable[[], datetime],
) -> None:
    app = create_app(settings, provider=FailingProvider(), clock=fixed_clock)
    with TestClient(app) as client:
        session_id = client.post("/api/sessions", json={"channel": "chat"}).json()["session_id"]
        payload = send(client, session_id, "What is the location?")
    assert payload["meta"]["fallback_used"] is True
    assert payload["meta"]["provider"] == "demo:deterministic-v1"
    assert "Sector 79, Gurugram" in payload["reply"]


def test_post_model_guard_blocks_unsafe_provider_output(
    settings: Settings,
    fixed_clock: Callable[[], datetime],
) -> None:
    provider = UnsafeProvider()
    app = create_app(settings, provider=provider, clock=fixed_clock)
    with TestClient(app) as client:
        session_id = client.post("/api/sessions", json={"channel": "chat"}).json()["session_id"]
        payload = send(client, session_id, "What is the price?")
    assert provider.calls == 1
    assert payload["intent"] == "guardrail_factual_boundary"
    assert "₹90 lakh" not in payload["reply"]


def test_do_not_contact_bypasses_even_unsafe_provider(
    settings: Settings,
    fixed_clock: Callable[[], datetime],
) -> None:
    provider = UnsafeProvider()
    app = create_app(settings, provider=provider, clock=fixed_clock)
    with TestClient(app) as client:
        session_id = client.post("/api/sessions", json={"channel": "chat"}).json()["session_id"]
        payload = send(client, session_id, "Do not contact me again")
    assert provider.calls == 0
    assert payload["status"] == "do_not_contact"
