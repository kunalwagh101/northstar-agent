from __future__ import annotations

import re

from app.domain.models import AgentActionType, AgentTurn, ConversationSession, Language

_MONEY = re.compile(r"(?:₹\s*)?(\d+(?:\.\d+)?)\s*(crore|cr\b|lakh|lac\b)", re.IGNORECASE)
_BOOKING_CLAIM = re.compile(
    r"(?:\b(?:visit|slot|booking)\b.{0,40}\b(?:booked|confirmed|reserved)\b)|"
    r"(?:\b(?:booked|confirmed|reserved)\b.{0,40}\b(?:visit|slot|booking)\b)",
    re.IGNORECASE,
)
_UNSUPPORTED_CLAIM = re.compile(
    r"\b(?:possession is|rera (?:number|is)|amenities include|units? (?:are )?available|"
    r"discount of|carpet area is|builder has delivered)\b",
    re.IGNORECASE,
)
_BUDGET_CONTEXT = re.compile(
    r"\b(?:your|stated|comfortable|noted|approximate|aapka|budget|बजट)\b", re.IGNORECASE
)
_PRICE_CONTEXT = re.compile(r"\b(?:price|cost|starts?|starting|कीमत)\b", re.IGNORECASE)


def _safe_boundary_reply(language: Language) -> str:
    if language == Language.HINDI:
        return "मैं केवल पुष्ट जानकारी साझा कर सकता हूँ: 2 BHK ₹1.35 करोड़ onwards और 3 BHK ₹1.75 करोड़ onwards है। अन्य जानकारी के लिए मैं सेल्स सलाहकार से जोड़ सकता हूँ।"
    if language == Language.HINGLISH:
        return "Main sirf confirmed information share kar sakta hoon: 2 BHK ₹1.35 crore onwards aur 3 BHK ₹1.75 crore onwards hai. Baaki details ke liye sales advisor se connect kar sakta hoon."
    return "I can only confirm that 2 BHK starts at ₹1.35 crore onwards and 3 BHK at ₹1.75 crore onwards. I can connect you with a sales adviser for other details."


class ResponseGuard:
    """Post-model boundary for high-impact claims; it does not rely on prompt obedience."""

    @staticmethod
    def _money_allowed(
        *,
        value: float,
        unit: str,
        reply: str,
        user_message: str,
        session: ConversationSession,
    ) -> bool:
        normalized = value if unit.lower().startswith(("crore", "cr")) else value / 100
        if round(normalized, 4) in {1.35, 1.75}:
            return True

        allowed_budgets: set[float] = set()
        if session.profile.budget_crore is not None:
            allowed_budgets.add(round(session.profile.budget_crore, 4))
        for match in _MONEY.finditer(user_message):
            raw_value = float(match.group(1))
            raw_unit = match.group(2).lower()
            user_value = raw_value if raw_unit.startswith(("crore", "cr")) else raw_value / 100
            allowed_budgets.add(round(user_value, 4))
        return round(normalized, 4) in allowed_budgets and bool(_BUDGET_CONTEXT.search(reply))

    def enforce(
        self,
        *,
        turn: AgentTurn,
        user_message: str,
        session: ConversationSession,
    ) -> tuple[AgentTurn, bool]:
        violation = _UNSUPPORTED_CLAIM.search(turn.reply) is not None
        if (
            _BOOKING_CLAIM.search(turn.reply)
            and turn.action.type != AgentActionType.BOOK_SITE_VISIT
        ):
            violation = True

        for match in _MONEY.finditer(turn.reply):
            if not self._money_allowed(
                value=float(match.group(1)),
                unit=match.group(2),
                reply=turn.reply,
                user_message=user_message,
                session=session,
            ):
                violation = True
                break

        if (
            _PRICE_CONTEXT.search(turn.reply)
            and _MONEY.search(turn.reply)
            and "onwards" not in turn.reply.lower()
        ):
            violation = True

        if not violation:
            return turn, False

        safe_turn = turn.model_copy(deep=True)
        safe_turn.reply = _safe_boundary_reply(turn.language)
        safe_turn.unknown_question = True
        safe_turn.action.type = AgentActionType.NONE
        safe_turn.should_end = False
        safe_turn.end_reason = None
        safe_turn.intent = "guardrail_factual_boundary"
        return safe_turn, True
