from __future__ import annotations

from pathlib import Path

from app.domain.models import ConversationSession
from app.services.prompt import PromptBuilder


def test_final_prompt_contains_assignment_requirements() -> None:
    path = Path(__file__).resolve().parents[1] / "prompts" / "NORTHSTAR_AGENT_SYSTEM_PROMPT.md"
    prompt = path.read_text(encoding="utf-8")
    required_phrases = (
        "English, Hindi",
        "do-not-contact",
        "Site-visit workflow",
        "Human escalation",
        "Never invent",
        "voice mode",
        "₹1.35 crore onwards",
        "₹1.75 crore onwards",
        "Return exactly one valid JSON object",
    )
    for phrase in required_phrases:
        assert phrase.lower() in prompt.lower()


def test_prompt_builder_injects_trusted_state() -> None:
    path = Path(__file__).resolve().parents[1] / "prompts" / "NORTHSTAR_AGENT_SYSTEM_PROMPT.md"
    builder = PromptBuilder(path, "Asia/Kolkata")
    session = ConversationSession(session_id="abc")
    session.profile.budget_raw = "₹2 crore"
    built = builder.build(session)
    assert "<trusted_runtime_context>" in built
    assert '"budget_raw": "₹2 crore"' in built
    assert '"timezone": "Asia/Kolkata"' in built
