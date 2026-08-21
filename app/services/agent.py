from __future__ import annotations

import logging
import re
import time as monotonic_time
from collections.abc import Callable
from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.metrics import MetricsRegistry
from app.domain.models import (
    AgentActionType,
    BookingFailureReason,
    BookingResult,
    Channel,
    ChatResponse,
    Configuration,
    ConversationMessage,
    ConversationSession,
    ConversationStatus,
    CreateSessionResponse,
    EndReason,
    Language,
    LeadAnalytics,
    LeadUpdates,
    MessageRole,
    PurchasePurpose,
    ResponseMeta,
    SiteVisitStatus,
)
from app.domain.safety import is_do_not_contact, redact_phone_numbers
from app.infrastructure.demo_provider import DemoAgentProvider, detect_language
from app.infrastructure.llm import AgentProvider, LLMProviderError, ProviderResult
from app.infrastructure.memory import InMemorySessionStore
from app.services.analytics import AnalyticsService
from app.services.booking import BookingService
from app.services.guardrails import ResponseGuard
from app.services.prompt import PromptBuilder

logger = logging.getLogger(__name__)


class AgentUnavailableError(RuntimeError):
    pass


def _say(language: Language, *, en: str, hi: str, hinglish: str) -> str:
    if language == Language.HINDI:
        return hi
    if language == Language.HINGLISH:
        return hinglish
    return en


class AgentService:
    def __init__(
        self,
        *,
        store: InMemorySessionStore,
        provider: AgentProvider,
        fallback_provider: DemoAgentProvider,
        prompt_builder: PromptBuilder,
        booking_service: BookingService,
        analytics_service: AnalyticsService,
        guard: ResponseGuard,
        metrics: MetricsRegistry,
        max_messages_per_session: int,
        session_ttl_seconds: int,
        fallback_enabled: bool,
        timezone_name: str,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.store = store
        self.provider = provider
        self.fallback_provider = fallback_provider
        self.prompt_builder = prompt_builder
        self.booking_service = booking_service
        self.analytics_service = analytics_service
        self.guard = guard
        self.metrics = metrics
        self.max_messages_per_session = max_messages_per_session
        self.session_ttl_seconds = session_ttl_seconds
        self.fallback_enabled = fallback_enabled
        self.timezone = ZoneInfo(timezone_name)
        self._clock = clock or (lambda: datetime.now(self.timezone))

    async def create_session(self, channel: Channel) -> CreateSessionResponse:
        session = await self.store.create(channel)
        self.metrics.increment("sessions_created_total")
        greeting = _say(
            session.profile.language,
            en="Hello, I’m Aarohi, Northstar Homes’ AI sales assistant. Are you looking for a 2 BHK or 3 BHK?",
            hi="नमस्ते, मैं Aarohi हूँ, Northstar Homes की AI सेल्स असिस्टेंट। आप 2 BHK देख रहे हैं या 3 BHK?",
            hinglish="Hi, main Aarohi hoon, Northstar Homes ki AI sales assistant. Aap 2 BHK dekh rahe hain ya 3 BHK?",
        )
        async with self.store.transaction(session.session_id) as active:
            active.messages.append(
                ConversationMessage(role=MessageRole.ASSISTANT, content=greeting)
            )
        return CreateSessionResponse(
            session_id=session.session_id,
            greeting=greeting,
            expires_in_seconds=self.session_ttl_seconds,
            provider_mode=self.provider.name,
        )

    @staticmethod
    def _dnc_reply(language: Language) -> str:
        return _say(
            language,
            en="Understood. I’m sorry for the disturbance. We will stop further sales communication.",
            hi="समझ गया। असुविधा के लिए क्षमा कीजिए। आगे कोई बिक्री संबंधी संपर्क नहीं किया जाएगा।",
            hinglish="Samajh gaya. Disturbance ke liye sorry. Aage se sales communication stop kar diya jayega.",
        )

    @staticmethod
    def _closed_reply(session: ConversationSession) -> str:
        if session.status == ConversationStatus.DO_NOT_CONTACT:
            return _say(
                session.profile.language,
                en="This conversation is closed and the do-not-contact preference remains recorded.",
                hi="यह बातचीत बंद है और संपर्क न करने का अनुरोध दर्ज है।",
                hinglish="Yeh conversation closed hai aur do-not-contact preference recorded hai.",
            )
        return _say(
            session.profile.language,
            en="This conversation has ended. Please start a new conversation if you need further help.",
            hi="यह बातचीत समाप्त हो चुकी है। अधिक सहायता के लिए नई बातचीत शुरू करें।",
            hinglish="Yeh conversation end ho chuki hai. Further help ke liye new conversation start karein.",
        )

    @staticmethod
    def _safe_updates(
        updates: LeadUpdates,
        *,
        message: str,
        session: ConversationSession,
    ) -> LeadUpdates:
        safe = updates.model_copy(deep=True)
        digits = re.sub(r"\D", "", message)
        if safe.phone and safe.phone not in digits and safe.phone != session.profile.phone:
            safe.phone = None

        if safe.configuration and safe.configuration != session.profile.configuration:
            number = "2" if safe.configuration == Configuration.TWO_BHK else "3"
            if not re.search(rf"\b{number}\s*[- ]?\s*bhk\b", message, re.IGNORECASE):
                safe.configuration = None

        if safe.budget_crore is not None and safe.budget_crore != session.profile.budget_crore:
            numeric_tokens = [float(value) for value in re.findall(r"\d+(?:\.\d+)?", message)]
            crore_match = any(abs(value - safe.budget_crore) < 0.001 for value in numeric_tokens)
            lakh_match = any(
                abs(value / 100 - safe.budget_crore) < 0.001 for value in numeric_tokens
            )
            if not crore_match and not lakh_match:
                safe.budget_crore = None
                safe.budget_raw = None
        return safe

    @staticmethod
    def _apply_updates(
        session: ConversationSession,
        updates: LeadUpdates,
        *,
        unknown_question: bool,
        user_message: str,
    ) -> None:
        profile = session.profile
        if updates.name:
            profile.name = updates.name
        if updates.phone:
            profile.phone = updates.phone
        if updates.language:
            profile.language = updates.language
        if updates.configuration:
            profile.configuration = updates.configuration
        if updates.budget_raw:
            profile.budget_raw = updates.budget_raw
        if updates.budget_crore is not None:
            profile.budget_crore = updates.budget_crore
        if updates.purchase_purpose and updates.purchase_purpose != PurchasePurpose.UNKNOWN:
            profile.purchase_purpose = updates.purchase_purpose
        if updates.purchase_timeline:
            profile.purchase_timeline = updates.purchase_timeline
        if updates.preferred_location:
            profile.preferred_location = updates.preferred_location
        if updates.objection and updates.objection not in profile.objections:
            profile.objections.append(updates.objection)
            profile.objections = profile.objections[-10:]
        if unknown_question:
            question = redact_phone_numbers(user_message)[:160]
            if question not in profile.unknown_questions:
                profile.unknown_questions.append(question)
                profile.unknown_questions = profile.unknown_questions[-10:]

    async def _provider_turn(
        self,
        *,
        session: ConversationSession,
        message: str,
    ) -> tuple[ProviderResult, bool]:
        system_prompt = self.prompt_builder.build(session)
        try:
            return (
                await self.provider.generate_turn(
                    system_prompt=system_prompt,
                    session=session,
                    user_message=message,
                ),
                False,
            )
        except LLMProviderError:
            self.metrics.increment("provider_errors_total")
            logger.warning("provider_fallback", extra={"provider": self.provider.name})
            if not self.fallback_enabled or self.provider is self.fallback_provider:
                raise AgentUnavailableError("The AI service is temporarily unavailable") from None
            result = await self.fallback_provider.generate_turn(
                system_prompt=system_prompt,
                session=session,
                user_message=message,
            )
            self.metrics.increment("provider_fallbacks_total")
            return result, True

    async def _execute_booking(
        self,
        *,
        session: ConversationSession,
        result: ProviderResult,
    ) -> BookingResult:
        action = result.turn.action
        session.profile.site_visit_status = SiteVisitStatus.REQUESTED
        booking = await self.booking_service.book(
            session_id=session.session_id,
            booking_date=action.booking_date,
            booking_time=action.booking_time,
        )
        if booking.success:
            session.profile.site_visit_status = SiteVisitStatus.BOOKED
            session.profile.site_visit_at = booking.confirmed_at
            session.profile.booking_reference = booking.booking_reference
            session.status = ConversationStatus.COMPLETED
            session.end_reason = EndReason.SITE_VISIT_BOOKED
            self.metrics.increment("bookings_succeeded_total")
            when = booking.confirmed_at.astimezone(self.timezone) if booking.confirmed_at else None
            formatted = when.strftime("%A, %d %B at %I:%M %p") if when else "the selected time"
            result.turn.reply = _say(
                result.turn.language,
                en=f"Your Northstar One site visit is confirmed for {formatted} IST. Reference: {booking.booking_reference}. Thank you.",
                hi=f"आपकी Northstar One साइट विज़िट {formatted} IST के लिए कन्फर्म है। रेफरेंस: {booking.booking_reference}। धन्यवाद।",
                hinglish=f"Aapki Northstar One site visit {formatted} IST ke liye confirmed hai. Reference: {booking.booking_reference}. Thank you.",
            )
            result.turn.should_end = True
            result.turn.end_reason = EndReason.SITE_VISIT_BOOKED
            return booking

        session.profile.site_visit_status = SiteVisitStatus.FAILED
        self.metrics.increment("bookings_failed_total")
        reason_text = {
            BookingFailureReason.SLOT_UNAVAILABLE: "that slot is unavailable",
            BookingFailureReason.OUTSIDE_BUSINESS_HOURS: "that time is outside visiting hours",
            BookingFailureReason.CLOSED_DAY: "site visits are closed that day",
            BookingFailureReason.PAST_SLOT: "that time has already passed",
            BookingFailureReason.INVALID_SLOT: "that is not a valid 30-minute visit slot",
        }.get(booking.failure_reason, "the slot could not be confirmed")
        alternatives = ", ".join(
            value.astimezone(self.timezone).strftime("%A, %d %B at %I:%M %p")
            for value in booking.alternatives
        )
        alternative_sentence = (
            f" Available alternatives are {alternatives} IST. Which one works for you?"
            if alternatives
            else " Would you like help from a sales adviser?"
        )
        result.turn.reply = _say(
            result.turn.language,
            en=f"The visit was not booked because {reason_text}.{alternative_sentence}",
            hi=f"साइट विज़िट बुक नहीं हुई क्योंकि चुना गया स्लॉट उपलब्ध नहीं है। विकल्प: {alternatives} IST। आप कौन-सा समय पसंद करेंगे?",
            hinglish=f"Site visit book nahi hui because selected slot available nahi hai. Alternatives: {alternatives} IST. Aapka preferred slot kaunsa hai?",
        )
        result.turn.should_end = False
        result.turn.end_reason = None
        return booking

    async def chat(
        self,
        *,
        session_id: str,
        message: str,
        channel: Channel,
        request_id: str | None = None,
    ) -> ChatResponse:
        started = monotonic_time.perf_counter()
        booking: BookingResult | None = None
        fallback_used = False

        async with self.store.transaction(session_id) as session:
            if session.status != ConversationStatus.ACTIVE:
                latency_ms = (monotonic_time.perf_counter() - started) * 1000
                return ChatResponse(
                    session_id=session.session_id,
                    reply=self._closed_reply(session),
                    language=session.profile.language,
                    intent="conversation_already_ended",
                    status=session.status,
                    profile=session.profile,
                    conversation_ended=True,
                    meta=ResponseMeta(
                        provider="policy:closed-session",
                        latency_ms=latency_ms,
                        request_id=request_id,
                    ),
                )

            session.channel = channel
            detected_language = detect_language(message, session.profile.language)

            if is_do_not_contact(message):
                session.profile.language = detected_language
                session.profile.do_not_contact = True
                session.profile.follow_up_required = False
                session.profile.follow_up_at = None
                session.status = ConversationStatus.DO_NOT_CONTACT
                session.end_reason = EndReason.DO_NOT_CONTACT
                reply = self._dnc_reply(detected_language)
                provider_name = "policy:do-not-contact"
                intent = "do_not_contact"
                self.metrics.increment("do_not_contact_total")
            else:
                provider_result, fallback_used = await self._provider_turn(
                    session=session,
                    message=message,
                )
                guarded_turn, guard_triggered = self.guard.enforce(
                    turn=provider_result.turn,
                    user_message=message,
                    session=session,
                )
                provider_result = ProviderResult(
                    turn=guarded_turn,
                    provider=provider_result.provider,
                    input_tokens=provider_result.input_tokens,
                    output_tokens=provider_result.output_tokens,
                )
                if guard_triggered:
                    self.metrics.increment("guardrail_interventions_total")

                safe_updates = self._safe_updates(
                    provider_result.turn.lead_updates,
                    message=message,
                    session=session,
                )
                self._apply_updates(
                    session,
                    safe_updates,
                    unknown_question=provider_result.turn.unknown_question,
                    user_message=message,
                )
                session.profile.language = provider_result.turn.language

                action = provider_result.turn.action
                if action.type == AgentActionType.BOOK_SITE_VISIT:
                    booking = await self._execute_booking(
                        session=session,
                        result=provider_result,
                    )
                elif action.type == AgentActionType.SCHEDULE_FOLLOW_UP:
                    if action.follow_up_at and action.follow_up_at > self._clock():
                        session.profile.follow_up_required = True
                        session.profile.follow_up_at = action.follow_up_at
                        session.status = ConversationStatus.FOLLOW_UP_SCHEDULED
                        session.end_reason = EndReason.FOLLOW_UP_REQUESTED
                        self.metrics.increment("followups_scheduled_total")
                    else:
                        provider_result.turn.reply = _say(
                            provider_result.turn.language,
                            en="Please share a future date and time for the callback.",
                            hi="कृपया कॉल-बैक के लिए भविष्य की तारीख और समय बताइए।",
                            hinglish="Please callback ke liye future date aur time share karein.",
                        )
                        provider_result.turn.should_end = False
                        provider_result.turn.end_reason = None
                elif action.type == AgentActionType.ESCALATE_TO_HUMAN:
                    session.profile.human_escalation_required = True
                    session.status = ConversationStatus.ESCALATED
                    session.end_reason = EndReason.HUMAN_HANDOFF
                    self.metrics.increment("human_handoffs_total")
                elif (
                    action.type == AgentActionType.END_CONVERSATION
                    or provider_result.turn.should_end
                ):
                    end_reason = provider_result.turn.end_reason or EndReason.CUSTOMER_ENDED
                    session.end_reason = end_reason
                    if end_reason == EndReason.DO_NOT_CONTACT:
                        session.profile.do_not_contact = True
                        session.status = ConversationStatus.DO_NOT_CONTACT
                    else:
                        session.status = ConversationStatus.COMPLETED

                reply = provider_result.turn.reply
                provider_name = provider_result.provider
                intent = provider_result.turn.intent

            session.messages.extend(
                [
                    ConversationMessage(role=MessageRole.USER, content=message),
                    ConversationMessage(role=MessageRole.ASSISTANT, content=reply),
                ]
            )
            session.messages = session.messages[-self.max_messages_per_session :]
            analytics = self.analytics_service.generate(session)
            session.profile.interest_level = analytics.interest_level

            latency_ms = (monotonic_time.perf_counter() - started) * 1000
            self.metrics.increment("chat_turns_total")
            return ChatResponse(
                session_id=session.session_id,
                reply=reply,
                language=session.profile.language,
                intent=intent,
                status=session.status,
                profile=session.profile,
                booking=booking,
                conversation_ended=session.status != ConversationStatus.ACTIVE,
                meta=ResponseMeta(
                    provider=provider_name,
                    fallback_used=fallback_used,
                    latency_ms=round(latency_ms, 2),
                    request_id=request_id,
                ),
            )

    async def analytics(self, session_id: str) -> LeadAnalytics:
        session = await self.store.get(session_id)
        return self.analytics_service.generate(session)

    async def delete_session(self, session_id: str) -> bool:
        return await self.store.delete(session_id)
