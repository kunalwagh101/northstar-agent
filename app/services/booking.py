from __future__ import annotations

import asyncio
import secrets
from collections.abc import Callable
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.domain.models import BookingFailureReason, BookingResult, SiteVisitStatus


class BookingService:
    """Safe, deterministic simulation of an external calendar booking tool."""

    OPENING_TIME = time(10, 0)
    CLOSING_TIME = time(17, 0)
    LUNCH_START = time(13, 0)
    LUNCH_END = time(14, 0)
    SLOT_MINUTES = 30

    def __init__(
        self,
        *,
        timezone_name: str,
        clock: Callable[[], datetime] | None = None,
        unavailable_slots: set[str] | None = None,
    ) -> None:
        self.timezone = ZoneInfo(timezone_name)
        self._clock = clock or (lambda: datetime.now(self.timezone))
        self._unavailable_slots = unavailable_slots or set()
        self._booked: dict[str, tuple[str, str]] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def _slot_key(value: datetime) -> str:
        return value.isoformat(timespec="minutes")

    def _failure_reason(self, requested_at: datetime) -> BookingFailureReason | None:
        now = self._clock()
        if requested_at <= now:
            return BookingFailureReason.PAST_SLOT
        if requested_at.weekday() == 6:
            return BookingFailureReason.CLOSED_DAY
        local_time = requested_at.timetz().replace(tzinfo=None)
        if requested_at.minute not in {0, 30} or requested_at.second != 0:
            return BookingFailureReason.INVALID_SLOT
        if local_time < self.OPENING_TIME or local_time >= self.CLOSING_TIME:
            return BookingFailureReason.OUTSIDE_BUSINESS_HOURS
        if self.LUNCH_START <= local_time < self.LUNCH_END:
            return BookingFailureReason.SLOT_UNAVAILABLE
        key = self._slot_key(requested_at)
        if key in self._unavailable_slots or key in self._booked:
            return BookingFailureReason.SLOT_UNAVAILABLE
        return None

    def _alternatives(self, requested_at: datetime) -> list[datetime]:
        alternatives: list[datetime] = []
        candidate = requested_at + timedelta(minutes=self.SLOT_MINUTES)
        deadline = requested_at + timedelta(days=14)
        while candidate <= deadline and len(alternatives) < 3:
            if self._failure_reason(candidate) is None:
                alternatives.append(candidate)
            candidate += timedelta(minutes=self.SLOT_MINUTES)
            if candidate.timetz().replace(tzinfo=None) >= self.CLOSING_TIME:
                candidate = (candidate + timedelta(days=1)).replace(
                    hour=self.OPENING_TIME.hour,
                    minute=self.OPENING_TIME.minute,
                    second=0,
                    microsecond=0,
                )
        return alternatives

    async def book(
        self,
        *,
        session_id: str,
        booking_date: object,
        booking_time: object,
    ) -> BookingResult:
        if not hasattr(booking_date, "year") or not isinstance(booking_time, time):
            return BookingResult(
                success=False,
                status=SiteVisitStatus.FAILED,
                failure_reason=BookingFailureReason.INVALID_SLOT,
            )

        requested_at = datetime.combine(booking_date, booking_time, tzinfo=self.timezone)
        async with self._lock:
            key = self._slot_key(requested_at)
            existing = self._booked.get(key)
            if existing and existing[0] == session_id:
                return BookingResult(
                    success=True,
                    status=SiteVisitStatus.BOOKED,
                    requested_at=requested_at,
                    confirmed_at=requested_at,
                    booking_reference=existing[1],
                )

            failure = self._failure_reason(requested_at)
            if failure is not None:
                return BookingResult(
                    success=False,
                    status=SiteVisitStatus.FAILED,
                    requested_at=requested_at,
                    failure_reason=failure,
                    alternatives=self._alternatives(requested_at),
                )

            reference = f"NS-{requested_at:%Y%m%d}-{secrets.token_hex(2).upper()}"
            self._booked[key] = (session_id, reference)
            return BookingResult(
                success=True,
                status=SiteVisitStatus.BOOKED,
                requested_at=requested_at,
                confirmed_at=requested_at,
                booking_reference=reference,
            )
