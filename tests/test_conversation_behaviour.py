from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import send


def test_successful_site_visit_booking(client: TestClient, session_id: str) -> None:
    payload = send(client, session_id, "Book a site visit tomorrow at 11 am")
    assert payload["booking"]["success"] is True
    assert payload["profile"]["site_visit_status"] == "booked"
    assert payload["profile"]["booking_reference"].startswith("NS-20260822-")
    assert "confirmed" in payload["reply"].lower()
    assert "Saturday, 22 August" in payload["reply"]
    assert payload["status"] == "completed"
    assert payload["conversation_ended"] is True


def test_failed_sunday_booking_offers_alternatives(client: TestClient, session_id: str) -> None:
    payload = send(client, session_id, "Please book a site visit on Sunday at 11 am")
    assert payload["booking"]["success"] is False
    assert payload["booking"]["failure_reason"] == "closed_day"
    assert payload["profile"]["site_visit_status"] == "failed"
    assert "not booked" in payload["reply"].lower()
    assert "Monday, 24 August" in payload["reply"]
    assert payload["status"] == "active"
    assert payload["conversation_ended"] is False


def test_booking_needs_date_and_time(client: TestClient, session_id: str) -> None:
    payload = send(client, session_id, "I want to book a site visit")
    assert payload["intent"] == "site_visit_details_needed"
    assert "date and time" in payload["reply"]
    assert payload["profile"]["site_visit_status"] == "not_requested"
    assert payload["booking"] is None


def test_busy_customer_callback(client: TestClient, session_id: str) -> None:
    payload = send(client, session_id, "I am busy. Call me tomorrow at 4 pm")
    assert payload["status"] == "follow_up_scheduled"
    assert payload["profile"]["follow_up_required"] is True
    assert payload["profile"]["follow_up_at"].startswith("2026-08-22T16:00:00")
    assert payload["conversation_ended"] is True


def test_busy_customer_without_time_is_not_pressured(client: TestClient, session_id: str) -> None:
    payload = send(client, session_id, "I am busy right now")
    assert payload["intent"] == "customer_busy"
    assert "callback" in payload["reply"].lower()
    assert payload["conversation_ended"] is False


def test_uninterested_customer_ends_without_dnc(client: TestClient, session_id: str) -> None:
    payload = send(client, session_id, "I am not interested")
    assert payload["status"] == "completed"
    assert payload["profile"]["do_not_contact"] is False
    assert payload["conversation_ended"] is True
    analytics = client.get(f"/api/sessions/{session_id}/analytics").json()
    assert analytics["interest_level"] == "disqualified"
    assert analytics["lead_score"] == 5


def test_do_not_contact_has_highest_priority(client: TestClient, session_id: str) -> None:
    payload = send(
        client,
        session_id,
        "I want a 3 BHK but do not contact me again and book tomorrow at 11 am",
    )
    assert payload["meta"]["provider"] == "policy:do-not-contact"
    assert payload["status"] == "do_not_contact"
    assert payload["profile"]["do_not_contact"] is True
    assert payload["profile"]["site_visit_status"] == "not_requested"
    assert payload["booking"] is None
    assert "stop further sales communication" in payload["reply"]

    later = send(client, session_id, "Actually, show me the price")
    assert later["intent"] == "conversation_already_ended"
    assert "do-not-contact preference remains recorded" in later["reply"]


def test_human_handoff(client: TestClient, session_id: str) -> None:
    payload = send(client, session_id, "I want to speak to a human sales advisor")
    assert payload["status"] == "escalated"
    assert payload["profile"]["human_escalation_required"] is True
    assert payload["conversation_ended"] is True


def test_voice_channel_stays_concise(client: TestClient, session_id: str) -> None:
    payload = send(client, session_id, "What is the price?", channel="voice")
    assert payload["profile"]["language"] == "english"
    assert len(payload["reply"].split()) < 55
