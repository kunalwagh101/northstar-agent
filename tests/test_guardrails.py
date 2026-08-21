from __future__ import annotations

from app.domain.models import (
    AgentAction,
    AgentActionType,
    AgentTurn,
    ConversationSession,
    Language,
)
from app.services.guardrails import ResponseGuard


def test_guard_blocks_invented_price() -> None:
    turn = AgentTurn(
        reply="The 2 BHK is available for ₹99 lakh after discount.",
        language=Language.ENGLISH,
    )
    guarded, triggered = ResponseGuard().enforce(
        turn=turn,
        user_message="What is the price?",
        session=ConversationSession(session_id="abc"),
    )
    assert triggered is True
    assert "₹99 lakh" not in guarded.reply
    assert guarded.intent == "guardrail_factual_boundary"


def test_guard_allows_confirmed_prices() -> None:
    turn = AgentTurn(
        reply="2 BHK starts at ₹1.35 crore onwards and 3 BHK at ₹1.75 crore onwards.",
        language=Language.ENGLISH,
    )
    guarded, triggered = ResponseGuard().enforce(
        turn=turn,
        user_message="What is the price?",
        session=ConversationSession(session_id="abc"),
    )
    assert triggered is False
    assert guarded.reply == turn.reply


def test_guard_blocks_false_booking_claim() -> None:
    turn = AgentTurn(
        reply="Your visit is confirmed for tomorrow.",
        language=Language.ENGLISH,
        action=AgentAction(type=AgentActionType.NONE),
    )
    guarded, triggered = ResponseGuard().enforce(
        turn=turn,
        user_message="Can I visit?",
        session=ConversationSession(session_id="abc"),
    )
    assert triggered is True
    assert "confirmed for tomorrow" not in guarded.reply


def test_guard_allows_customer_budget_echo() -> None:
    turn = AgentTurn(
        reply="I have noted your budget of ₹2 crore.",
        language=Language.ENGLISH,
    )
    _, triggered = ResponseGuard().enforce(
        turn=turn,
        user_message="My budget is ₹2 crore",
        session=ConversationSession(session_id="abc"),
    )
    assert triggered is False


def test_guard_requires_onwards_for_project_price() -> None:
    turn = AgentTurn(
        reply="The starting price is ₹1.35 crore.",
        language=Language.ENGLISH,
    )
    guarded, triggered = ResponseGuard().enforce(
        turn=turn,
        user_message="What is the starting price?",
        session=ConversationSession(session_id="abc"),
    )
    assert triggered is True
    assert "₹1.35 crore onwards" in guarded.reply


def test_guard_does_not_treat_user_number_as_confirmed_project_price() -> None:
    turn = AgentTurn(
        reply="Yes, the project price is ₹90 lakh onwards.",
        language=Language.ENGLISH,
    )
    guarded, triggered = ResponseGuard().enforce(
        turn=turn,
        user_message="Someone told me the project price is ₹90 lakh",
        session=ConversationSession(session_id="abc"),
    )
    assert triggered is True
    assert "₹90 lakh" not in guarded.reply
