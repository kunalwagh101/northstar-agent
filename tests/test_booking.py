from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from app.services.booking import BookingService

IST = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 8, 21, 12, 0, tzinfo=IST)


@pytest.fixture
def service() -> BookingService:
    return BookingService(timezone_name="Asia/Kolkata", clock=lambda: NOW)


@pytest.mark.asyncio
async def test_booking_is_idempotent_for_same_session(service: BookingService) -> None:
    first = await service.book(
        session_id="session-a",
        booking_date=date(2026, 8, 22),
        booking_time=time(11, 0),
    )
    second = await service.book(
        session_id="session-a",
        booking_date=date(2026, 8, 22),
        booking_time=time(11, 0),
    )
    assert first.success is True
    assert second.success is True
    assert second.booking_reference == first.booking_reference


@pytest.mark.asyncio
async def test_double_booking_fails_for_another_session(service: BookingService) -> None:
    await service.book(
        session_id="session-a",
        booking_date=date(2026, 8, 22),
        booking_time=time(11, 0),
    )
    result = await service.book(
        session_id="session-b",
        booking_date=date(2026, 8, 22),
        booking_time=time(11, 0),
    )
    assert result.success is False
    assert result.failure_reason == "slot_unavailable"
    assert len(result.alternatives) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("booking_date", "booking_time", "expected"),
    [
        (date(2026, 8, 21), time(11, 0), "past_slot"),
        (date(2026, 8, 22), time(9, 30), "outside_business_hours"),
        (date(2026, 8, 22), time(13, 0), "slot_unavailable"),
        (date(2026, 8, 22), time(11, 15), "invalid_slot"),
        (date(2026, 8, 23), time(11, 0), "closed_day"),
    ],
)
async def test_booking_validation(
    service: BookingService,
    booking_date: date,
    booking_time: time,
    expected: str,
) -> None:
    result = await service.book(
        session_id="session",
        booking_date=booking_date,
        booking_time=booking_time,
    )
    assert result.success is False
    assert result.failure_reason == expected
