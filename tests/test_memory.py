from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.domain.models import Channel
from app.infrastructure.memory import (
    InMemorySessionStore,
    SessionCapacityError,
    SessionExpiredError,
    SessionNotFoundError,
)


@pytest.mark.asyncio
async def test_store_transaction_isolated_copy() -> None:
    store = InMemorySessionStore(ttl_minutes=10, max_sessions=2)
    created = await store.create(Channel.CHAT)
    async with store.transaction(created.session_id) as session:
        session.profile.budget_raw = "₹2 crore"
    loaded = await store.get(created.session_id)
    assert loaded.profile.budget_raw == "₹2 crore"
    loaded.profile.budget_raw = "changed outside store"
    assert (await store.get(created.session_id)).profile.budget_raw == "₹2 crore"


@pytest.mark.asyncio
async def test_store_expiry_and_capacity() -> None:
    now = [datetime(2026, 8, 21, 10, 0, tzinfo=UTC)]
    store = InMemorySessionStore(
        ttl_minutes=1,
        max_sessions=1,
        clock=lambda: now[0],
    )
    created = await store.create(Channel.CHAT)
    with pytest.raises(SessionCapacityError):
        await store.create(Channel.CHAT)

    now[0] += timedelta(minutes=2)
    with pytest.raises(SessionExpiredError):
        await store.get(created.session_id)

    replacement = await store.create(Channel.CHAT)
    assert replacement.session_id != created.session_id
    with pytest.raises(SessionNotFoundError):
        await store.get("missing")


@pytest.mark.asyncio
async def test_delete_is_idempotent() -> None:
    store = InMemorySessionStore(ttl_minutes=10, max_sessions=2)
    created = await store.create(Channel.CHAT)
    assert await store.delete(created.session_id) is True
    assert await store.delete(created.session_id) is False
