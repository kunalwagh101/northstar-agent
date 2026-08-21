from __future__ import annotations

from app.domain.models import (
    ConversationSession,
    ConversationStatus,
    InterestLevel,
    LeadAnalytics,
    MessageRole,
    PurchasePurpose,
    SiteVisitStatus,
)


class AnalyticsService:
    """Deterministic analytics avoid a second model call and make evaluation repeatable."""

    @staticmethod
    def _completeness(session: ConversationSession) -> int:
        profile = session.profile
        present = (
            profile.configuration is not None,
            profile.budget_raw is not None,
            profile.purchase_purpose != PurchasePurpose.UNKNOWN,
            profile.purchase_timeline is not None,
            profile.preferred_location is not None,
        )
        return round(sum(present) / len(present) * 100)

    @staticmethod
    def _lead_score(session: ConversationSession) -> int:
        profile = session.profile
        if profile.do_not_contact or session.status == ConversationStatus.DO_NOT_CONTACT:
            return 0
        if session.end_reason and session.end_reason.value == "not_interested":
            return 5

        score = 5
        score += 10 if profile.configuration else 0
        score += 15 if profile.budget_raw else 0
        score += 10 if profile.purchase_purpose != PurchasePurpose.UNKNOWN else 0
        score += 15 if profile.purchase_timeline else 0
        score += 5 if profile.preferred_location else 0
        score += 30 if profile.site_visit_status == SiteVisitStatus.BOOKED else 0
        score += 12 if profile.site_visit_status == SiteVisitStatus.REQUESTED else 0
        score += 10 if profile.follow_up_required else 0
        score += 5 if profile.human_escalation_required else 0
        score -= min(10, len(profile.objections) * 3)
        return max(0, min(score, 100))

    @staticmethod
    def _interest(score: int, session: ConversationSession) -> InterestLevel:
        if session.profile.do_not_contact or (
            session.end_reason and session.end_reason.value == "not_interested"
        ):
            return InterestLevel.DISQUALIFIED
        if score >= 70:
            return InterestLevel.HIGH
        if score >= 40:
            return InterestLevel.MEDIUM
        if score > 5:
            return InterestLevel.LOW
        return InterestLevel.UNKNOWN

    @staticmethod
    def _summary(session: ConversationSession, interest: InterestLevel) -> str:
        profile = session.profile
        pieces = [f"{interest.value.capitalize()}-interest lead"]
        if profile.configuration:
            pieces.append(f"seeking {profile.configuration.value}")
        if profile.budget_raw:
            pieces.append(f"with a stated budget of {profile.budget_raw}")
        if profile.purchase_purpose != PurchasePurpose.UNKNOWN:
            pieces.append(f"for {profile.purchase_purpose.value}")
        if profile.purchase_timeline:
            pieces.append(f"on a {profile.purchase_timeline} timeline")
        if profile.site_visit_status == SiteVisitStatus.BOOKED:
            pieces.append("site visit booked")
        elif profile.follow_up_required:
            pieces.append("follow-up requested")
        elif profile.human_escalation_required:
            pieces.append("human handoff requested")
        if profile.do_not_contact:
            pieces.append("do-not-contact enforced")
        return "; ".join(pieces) + "."

    def generate(self, session: ConversationSession) -> LeadAnalytics:
        score = self._lead_score(session)
        interest = self._interest(score, session)
        session.profile.interest_level = interest
        customer_messages = sum(message.role == MessageRole.USER for message in session.messages)
        return LeadAnalytics(
            session_id=session.session_id,
            preferred_language=session.profile.language,
            channel=session.channel,
            lead_name=session.profile.name,
            phone_provided=bool(session.profile.phone),
            configuration=session.profile.configuration,
            budget=session.profile.budget_raw,
            budget_crore=session.profile.budget_crore,
            purchase_purpose=session.profile.purchase_purpose,
            purchase_timeline=session.profile.purchase_timeline,
            preferred_location=session.profile.preferred_location,
            interest_level=interest,
            lead_score=score,
            qualification_completeness=self._completeness(session),
            site_visit_status=session.profile.site_visit_status,
            site_visit_at=session.profile.site_visit_at,
            booking_reference=session.profile.booking_reference,
            follow_up_required=session.profile.follow_up_required,
            follow_up_at=session.profile.follow_up_at,
            do_not_contact=session.profile.do_not_contact,
            human_escalation_required=session.profile.human_escalation_required,
            objections=list(session.profile.objections),
            unknown_questions=list(session.profile.unknown_questions),
            conversation_status=session.status,
            end_reason=session.end_reason,
            customer_message_count=customer_messages,
            summary=self._summary(session, interest),
        )
