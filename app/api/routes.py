from __future__ import annotations

from fastapi import APIRouter, Request, Response, status

from app.container import AppContainer
from app.domain.models import (
    PROJECT_FACTS,
    ChatRequest,
    ChatResponse,
    CreateSessionRequest,
    CreateSessionResponse,
    HealthResponse,
    LeadAnalytics,
    ProjectFacts,
)

router = APIRouter()


def _container(request: Request) -> AppContainer:
    return request.app.state.container


@router.get("/healthz", response_model=HealthResponse, tags=["operations"])
async def health(request: Request) -> HealthResponse:
    container = _container(request)
    return HealthResponse(
        version=container.settings.app_version,
        provider=container.provider.name,
    )


@router.get("/readyz", response_model=HealthResponse, tags=["operations"])
async def readiness(request: Request) -> HealthResponse:
    container = _container(request)
    return HealthResponse(
        version=container.settings.app_version,
        provider=container.provider.name,
    )


@router.get("/api/project", response_model=ProjectFacts, tags=["project"])
async def project_facts() -> ProjectFacts:
    return PROJECT_FACTS


@router.post(
    "/api/sessions",
    response_model=CreateSessionResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["conversation"],
)
async def create_session(
    payload: CreateSessionRequest,
    request: Request,
) -> CreateSessionResponse:
    return await _container(request).agent.create_session(payload.channel)


@router.post("/api/chat", response_model=ChatResponse, tags=["conversation"])
async def chat(payload: ChatRequest, request: Request) -> ChatResponse:
    return await _container(request).agent.chat(
        session_id=payload.session_id,
        message=payload.message,
        channel=payload.channel,
        request_id=getattr(request.state, "request_id", None),
    )


@router.get(
    "/api/sessions/{session_id}/analytics",
    response_model=LeadAnalytics,
    tags=["analytics"],
)
async def analytics(session_id: str, request: Request) -> LeadAnalytics:
    return await _container(request).agent.analytics(session_id)


@router.delete(
    "/api/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["conversation"],
)
async def delete_session(session_id: str, request: Request) -> Response:
    await _container(request).agent.delete_session(session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/api/metrics", tags=["operations"])
async def metrics(request: Request) -> dict[str, object]:
    container = _container(request)
    snapshot = container.metrics.snapshot()
    snapshot["active_sessions"] = await container.store.count()
    return snapshot
