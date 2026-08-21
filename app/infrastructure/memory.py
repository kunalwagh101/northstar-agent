from __future__ import annotations

import asyncio
import secrets
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

from app.domain.models import Channel, ConversationSession


class SessionNotFoundError(LookupError):
    pass


class SessionExpiredError(LookupError):
    pass


class SessionCapacityError(RuntimeError):
    pass


class InMemorySessionStore:
    """TTL-bound, session-isolated memory for the assignment demo.

    The interface keeps persistence behind one boundary, so Redis or PostgreSQL can
    replace this implementation without changing agent behaviour.
    """

    def __init__(
        self,
        *,
        ttl_minutes: int,
        max_sessions: int,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._ttl = timedelta(minutes=ttl_minutes)
        self._max_sessions = max_sessions
        self._clock = clock or (lambda: datetime.now(UTC))
        self._sessions: dict[str, ConversationSession] = {}
        self._session_locks: dict[str, asyncio.Lock] = {}
        self._index_lock = asyncio.Lock()

    def _expired(self, session: ConversationSession) -> bool:
        now = self._clock()
        updated_at = session.updated_at
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=UTC)
        return now - updated_at > self._ttl

    def _purge_expired_unlocked(self) -> None:
        expired = [
            session_id for session_id, session in self._sessions.items() if self._expired(session)
        ]
        for session_id in expired:
            self._sessions.pop(session_id, None)
            self._session_locks.pop(session_id, None)

    async def create(self, channel: Channel) -> ConversationSession:
        async with self._index_lock:
            self._purge_expired_unlocked()
            if len(self._sessions) >= self._max_sessions:
                raise SessionCapacityError("Session capacity reached")

            session_id = secrets.token_urlsafe(18)
            now = self._clock()
            session = ConversationSession(
                session_id=session_id,
                channel=channel,
                created_at=now,
                updated_at=now,
            )
            self._sessions[session_id] = session
            self._session_locks[session_id] = asyncio.Lock()
            return session.model_copy(deep=True)

    async def get(self, session_id: str) -> ConversationSession:
        async with self._index_lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise SessionNotFoundError(session_id)
            if self._expired(session):
                self._sessions.pop(session_id, None)
                self._session_locks.pop(session_id, None)
                raise SessionExpiredError(session_id)
            return session.model_copy(deep=True)

    @asynccontextmanager
    async def transaction(self, session_id: str) -> AsyncIterator[ConversationSession]:
        async with self._index_lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise SessionNotFoundError(session_id)
            if self._expired(session):
                self._sessions.pop(session_id, None)
                self._session_locks.pop(session_id, None)
                raise SessionExpiredError(session_id)
            lock = self._session_locks[session_id]

        async with lock:
            current = self._sessions.get(session_id)
            if current is None:
                raise SessionNotFoundError(session_id)
            working_copy = current.model_copy(deep=True)
            yield working_copy
            working_copy.updated_at = self._clock()
            self._sessions[session_id] = working_copy

    async def delete(self, session_id: str) -> bool:
        async with self._index_lock:
            existed = session_id in self._sessions
            self._sessions.pop(session_id, None)
            self._session_locks.pop(session_id, None)
            return existed

    async def count(self) -> int:
        async with self._index_lock:
            self._purge_expired_unlocked()
            return len(self._sessions)
