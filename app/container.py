from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from app.core.config import Settings
from app.core.metrics import MetricsRegistry
from app.infrastructure.demo_provider import DemoAgentProvider
from app.infrastructure.llm import AgentProvider, OpenAICompatibleProvider
from app.infrastructure.memory import InMemorySessionStore
from app.services.agent import AgentService
from app.services.analytics import AnalyticsService
from app.services.booking import BookingService
from app.services.guardrails import ResponseGuard
from app.services.prompt import PromptBuilder


@dataclass(slots=True)
class AppContainer:
    settings: Settings
    metrics: MetricsRegistry
    store: InMemorySessionStore
    provider: AgentProvider
    fallback_provider: DemoAgentProvider
    booking: BookingService
    analytics: AnalyticsService
    agent: AgentService

    async def close(self) -> None:
        close = getattr(self.provider, "close", None)
        if close is not None:
            await close()


def build_container(
    settings: Settings,
    *,
    provider: AgentProvider | None = None,
    clock: Callable[[], datetime] | None = None,
    unavailable_slots: set[str] | None = None,
) -> AppContainer:
    metrics = MetricsRegistry()
    store = InMemorySessionStore(
        ttl_minutes=settings.session_ttl_minutes,
        max_sessions=settings.max_sessions,
        clock=clock,
    )
    fallback_provider = DemoAgentProvider(
        timezone_name=settings.booking_timezone,
        clock=clock,
    )
    if provider is None:
        if settings.ai_provider == "openai":
            provider = OpenAICompatibleProvider(
                api_key=settings.openai_api_key or "",
                base_url=settings.openai_base_url,
                model=settings.openai_model,
                timeout_seconds=settings.ai_timeout_seconds,
                max_retries=settings.ai_max_retries,
            )
        else:
            provider = fallback_provider

    booking = BookingService(
        timezone_name=settings.booking_timezone,
        clock=clock,
        unavailable_slots=unavailable_slots,
    )
    analytics = AnalyticsService()
    prompt_builder = PromptBuilder(settings.prompt_path, settings.booking_timezone)
    agent = AgentService(
        store=store,
        provider=provider,
        fallback_provider=fallback_provider,
        prompt_builder=prompt_builder,
        booking_service=booking,
        analytics_service=analytics,
        guard=ResponseGuard(),
        metrics=metrics,
        max_messages_per_session=settings.max_messages_per_session,
        session_ttl_seconds=settings.session_ttl_minutes * 60,
        fallback_enabled=settings.fallback_to_demo,
        timezone_name=settings.booking_timezone,
        clock=clock,
    )
    return AppContainer(
        settings=settings,
        metrics=metrics,
        store=store,
        provider=provider,
        fallback_provider=fallback_provider,
        booking=booking,
        analytics=analytics,
        agent=agent,
    )
