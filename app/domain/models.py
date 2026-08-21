from __future__ import annotations

from datetime import UTC, date, datetime, time
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

TrimmedText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Channel(StrEnum):
    CHAT = "chat"
    VOICE = "voice"


class Language(StrEnum):
    ENGLISH = "english"
    HINDI = "hindi"
    HINGLISH = "hinglish"


class Configuration(StrEnum):
    TWO_BHK = "2 BHK"
    THREE_BHK = "3 BHK"


class PurchasePurpose(StrEnum):
    SELF_USE = "self-use"
    INVESTMENT = "investment"
    UNKNOWN = "unknown"


class InterestLevel(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    DISQUALIFIED = "disqualified"
    UNKNOWN = "unknown"


class ConversationStatus(StrEnum):
    ACTIVE = "active"
    FOLLOW_UP_SCHEDULED = "follow_up_scheduled"
    ESCALATED = "escalated"
    COMPLETED = "completed"
    DO_NOT_CONTACT = "do_not_contact"


class EndReason(StrEnum):
    SITE_VISIT_BOOKED = "site_visit_booked"
    FOLLOW_UP_REQUESTED = "follow_up_requested"
    NOT_INTERESTED = "not_interested"
    DO_NOT_CONTACT = "do_not_contact"
    HUMAN_HANDOFF = "human_handoff"
    CUSTOMER_ENDED = "customer_ended"


class SiteVisitStatus(StrEnum):
    NOT_REQUESTED = "not_requested"
    REQUESTED = "requested"
    BOOKED = "booked"
    FAILED = "failed"


class BookingFailureReason(StrEnum):
    SLOT_UNAVAILABLE = "slot_unavailable"
    OUTSIDE_BUSINESS_HOURS = "outside_business_hours"
    CLOSED_DAY = "closed_day"
    PAST_SLOT = "past_slot"
    INVALID_SLOT = "invalid_slot"


class AgentActionType(StrEnum):
    NONE = "none"
    BOOK_SITE_VISIT = "book_site_visit"
    SCHEDULE_FOLLOW_UP = "schedule_follow_up"
    ESCALATE_TO_HUMAN = "escalate_to_human"
    END_CONVERSATION = "end_conversation"


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class ProjectFacts(StrictModel):
    company: str = "Northstar Homes"
    project: str = "Northstar One"
    location: str = "Sector 79, Gurugram"
    configurations: tuple[Configuration, ...] = (
        Configuration.TWO_BHK,
        Configuration.THREE_BHK,
    )
    two_bhk_starting_price: str = "₹1.35 crore onwards"
    three_bhk_starting_price: str = "₹1.75 crore onwards"
    confirmed_information_only: bool = True


PROJECT_FACTS = ProjectFacts()


class ConversationMessage(StrictModel):
    role: MessageRole
    content: str = Field(min_length=1, max_length=4000)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class LeadProfile(StrictModel):
    name: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=20, repr=False)
    language: Language = Language.ENGLISH
    configuration: Configuration | None = None
    budget_raw: str | None = Field(default=None, max_length=100)
    budget_crore: float | None = Field(default=None, ge=0, le=1000)
    purchase_purpose: PurchasePurpose = PurchasePurpose.UNKNOWN
    purchase_timeline: str | None = Field(default=None, max_length=100)
    preferred_location: str | None = Field(default=None, max_length=120)
    interest_level: InterestLevel = InterestLevel.UNKNOWN
    site_visit_status: SiteVisitStatus = SiteVisitStatus.NOT_REQUESTED
    site_visit_at: datetime | None = None
    booking_reference: str | None = Field(default=None, max_length=40)
    follow_up_required: bool = False
    follow_up_at: datetime | None = None
    do_not_contact: bool = False
    human_escalation_required: bool = False
    objections: list[str] = Field(default_factory=list, max_length=10)
    unknown_questions: list[str] = Field(default_factory=list, max_length=10)


class ConversationSession(StrictModel):
    session_id: str
    channel: Channel = Channel.CHAT
    status: ConversationStatus = ConversationStatus.ACTIVE
    end_reason: EndReason | None = None
    profile: LeadProfile = Field(default_factory=LeadProfile)
    messages: list[ConversationMessage] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class LeadUpdates(StrictModel):
    name: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=20, repr=False)
    language: Language | None = None
    configuration: Configuration | None = None
    budget_raw: str | None = Field(default=None, max_length=100)
    budget_crore: float | None = Field(default=None, ge=0, le=1000)
    purchase_purpose: PurchasePurpose | None = None
    purchase_timeline: str | None = Field(default=None, max_length=100)
    preferred_location: str | None = Field(default=None, max_length=120)
    objection: str | None = Field(default=None, max_length=160)


class AgentAction(StrictModel):
    type: AgentActionType = AgentActionType.NONE
    booking_date: date | None = None
    booking_time: time | None = None
    follow_up_at: datetime | None = None
    escalation_reason: str | None = Field(default=None, max_length=200)


class AgentTurn(StrictModel):
    reply: str = Field(min_length=1, max_length=1600)
    language: Language = Language.ENGLISH
    intent: str = Field(default="general_enquiry", max_length=80)
    lead_updates: LeadUpdates = Field(default_factory=LeadUpdates)
    action: AgentAction = Field(default_factory=AgentAction)
    should_end: bool = False
    end_reason: EndReason | None = None
    unknown_question: bool = False

    @field_validator("end_reason")
    @classmethod
    def validate_end_reason(cls, value: EndReason | None, info: object) -> EndReason | None:
        del info
        return value


class BookingResult(StrictModel):
    success: bool
    status: SiteVisitStatus
    requested_at: datetime | None = None
    confirmed_at: datetime | None = None
    booking_reference: str | None = None
    failure_reason: BookingFailureReason | None = None
    alternatives: list[datetime] = Field(default_factory=list, max_length=3)


class CreateSessionRequest(StrictModel):
    channel: Channel = Channel.CHAT


class CreateSessionResponse(StrictModel):
    session_id: str
    greeting: str
    expires_in_seconds: int
    provider_mode: str


class ChatRequest(StrictModel):
    session_id: TrimmedText = Field(max_length=128)
    message: TrimmedText = Field(max_length=2000)
    channel: Channel = Channel.CHAT


class ResponseMeta(StrictModel):
    provider: str
    fallback_used: bool = False
    latency_ms: float = Field(ge=0)
    request_id: str | None = None


class ChatResponse(StrictModel):
    session_id: str
    reply: str
    language: Language
    intent: str
    status: ConversationStatus
    profile: LeadProfile
    booking: BookingResult | None = None
    conversation_ended: bool
    meta: ResponseMeta


class LeadAnalytics(StrictModel):
    session_id: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    preferred_language: Language
    channel: Channel
    lead_name: str | None
    phone_provided: bool
    configuration: Configuration | None
    budget: str | None
    budget_crore: float | None
    purchase_purpose: PurchasePurpose
    purchase_timeline: str | None
    preferred_location: str | None
    interest_level: InterestLevel
    lead_score: int = Field(ge=0, le=100)
    qualification_completeness: int = Field(ge=0, le=100)
    site_visit_status: SiteVisitStatus
    site_visit_at: datetime | None
    booking_reference: str | None
    follow_up_required: bool
    follow_up_at: datetime | None
    do_not_contact: bool
    human_escalation_required: bool
    objections: list[str]
    unknown_questions: list[str]
    conversation_status: ConversationStatus
    end_reason: EndReason | None
    customer_message_count: int
    summary: str


class HealthResponse(StrictModel):
    status: Literal["ok"] = "ok"
    version: str
    provider: str
