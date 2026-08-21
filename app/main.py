from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.routes import router
from app.container import build_container
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.core.middleware import (
    BodySizeLimitMiddleware,
    RequestContextMiddleware,
    SlidingWindowRateLimitMiddleware,
)
from app.infrastructure.llm import AgentProvider
from app.infrastructure.memory import (
    SessionCapacityError,
    SessionExpiredError,
    SessionNotFoundError,
)
from app.services.agent import AgentUnavailableError

logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    *,
    provider: AgentProvider | None = None,
    clock: Callable[[], datetime] | None = None,
    unavailable_slots: set[str] | None = None,
) -> FastAPI:
    active_settings = settings or get_settings()
    configure_logging(active_settings.log_level)
    container = build_container(
        active_settings,
        provider=provider,
        clock=clock,
        unavailable_slots=unavailable_slots,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        logger.info(
            "application_started",
            extra={
                "version": active_settings.app_version,
                "environment": active_settings.app_env,
                "provider": container.provider.name,
            },
        )
        yield
        await container.close()
        logger.info("application_stopped")

    application = FastAPI(
        title=active_settings.app_name,
        version=active_settings.app_version,
        description="Multilingual AI sales agent for the Northstar One real-estate project.",
        docs_url="/docs" if active_settings.app_env != "production" else None,
        redoc_url=None,
        lifespan=lifespan,
    )
    application.state.container = container

    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(active_settings.allowed_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type", "X-Request-ID"],
    )
    application.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=list(active_settings.allowed_hosts),
    )
    application.add_middleware(
        SlidingWindowRateLimitMiddleware,
        requests=active_settings.rate_limit_requests,
        window_seconds=active_settings.rate_limit_window_seconds,
    )
    application.add_middleware(
        BodySizeLimitMiddleware,
        max_body_bytes=active_settings.max_body_bytes,
    )
    application.add_middleware(
        RequestContextMiddleware,
        metrics=container.metrics,
    )

    @application.exception_handler(SessionNotFoundError)
    async def session_not_found(_: Request, __: SessionNotFoundError) -> JSONResponse:
        return JSONResponse({"detail": "Conversation session was not found"}, status_code=404)

    @application.exception_handler(SessionExpiredError)
    async def session_expired(_: Request, __: SessionExpiredError) -> JSONResponse:
        return JSONResponse(
            {"detail": "Conversation session expired. Please start a new conversation."},
            status_code=410,
        )

    @application.exception_handler(SessionCapacityError)
    async def session_capacity(_: Request, __: SessionCapacityError) -> JSONResponse:
        return JSONResponse(
            {"detail": "The service is temporarily at capacity"},
            status_code=503,
        )

    @application.exception_handler(AgentUnavailableError)
    async def agent_unavailable(_: Request, __: AgentUnavailableError) -> JSONResponse:
        return JSONResponse(
            {"detail": "The AI service is temporarily unavailable. Please try again."},
            status_code=503,
        )

    @application.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        safe_errors = [
            {"location": list(error["loc"]), "message": error["msg"], "type": error["type"]}
            for error in exc.errors()
        ]
        return JSONResponse({"detail": "Invalid request", "errors": safe_errors}, status_code=422)

    application.include_router(router)

    static_path = Path(active_settings.static_path)
    application.mount("/assets", StaticFiles(directory=static_path), name="assets")

    @application.get("/", include_in_schema=False)
    async def web_app() -> FileResponse:
        return FileResponse(static_path / "index.html")

    return application


app = create_app()
