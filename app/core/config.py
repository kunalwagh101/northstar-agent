from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _as_int(name: str, default: int, *, minimum: int = 1) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        parsed = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if parsed < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return parsed


def _as_csv(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.getenv(name)
    if raw is None:
        return default
    values = tuple(item.strip() for item in raw.split(",") if item.strip())
    return values or default


@dataclass(frozen=True, slots=True)
class Settings:
    app_name: str = "Northstar Homes AI Sales Agent"
    app_version: str = "1.0.1"
    app_env: str = "development"
    log_level: str = "INFO"

    ai_provider: str = "demo"
    openai_api_key: str | None = field(default=None, repr=False)
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4.1-mini"
    ai_timeout_seconds: int = 20
    ai_max_retries: int = 2
    fallback_to_demo: bool = True

    session_ttl_minutes: int = 60
    max_sessions: int = 1000
    max_messages_per_session: int = 80
    max_message_chars: int = 2000

    rate_limit_requests: int = 30
    rate_limit_window_seconds: int = 60
    max_body_bytes: int = 16_384

    booking_timezone: str = "Asia/Kolkata"
    allowed_origins: tuple[str, ...] = (
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    )
    allowed_hosts: tuple[str, ...] = ("localhost", "127.0.0.1", "testserver")

    project_root: Path = field(
        default_factory=lambda: Path(__file__).resolve().parents[2], repr=False
    )

    @property
    def prompt_path(self) -> Path:
        return self.project_root / "prompts" / "NORTHSTAR_AGENT_SYSTEM_PROMPT.md"

    @property
    def static_path(self) -> Path:
        return self.project_root / "app" / "static"

    @classmethod
    def from_env(cls) -> Settings:
        provider = os.getenv("AI_PROVIDER", "demo").strip().lower()
        if provider not in {"demo", "openai"}:
            raise ValueError("AI_PROVIDER must be either 'demo' or 'openai'")

        return cls(
            app_env=os.getenv("APP_ENV", "development").strip().lower(),
            log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper(),
            ai_provider=provider,
            openai_api_key=os.getenv("OPENAI_API_KEY") or None,
            openai_base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
            openai_model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            ai_timeout_seconds=_as_int("AI_TIMEOUT_SECONDS", 20),
            ai_max_retries=_as_int("AI_MAX_RETRIES", 2, minimum=0),
            fallback_to_demo=_as_bool(os.getenv("FALLBACK_TO_DEMO"), True),
            session_ttl_minutes=_as_int("SESSION_TTL_MINUTES", 60),
            max_sessions=_as_int("MAX_SESSIONS", 1000),
            max_messages_per_session=_as_int("MAX_MESSAGES_PER_SESSION", 80),
            rate_limit_requests=_as_int("RATE_LIMIT_REQUESTS", 30),
            rate_limit_window_seconds=_as_int("RATE_LIMIT_WINDOW_SECONDS", 60),
            booking_timezone=os.getenv("BOOKING_TIMEZONE", "Asia/Kolkata"),
            allowed_origins=_as_csv(
                "ALLOWED_ORIGINS",
                ("http://localhost:8000", "http://127.0.0.1:8000"),
            ),
            allowed_hosts=_as_csv(
                "ALLOWED_HOSTS",
                ("localhost", "127.0.0.1", "testserver"),
            ),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()
