from __future__ import annotations

import argparse
import json
import statistics
import sys
import warnings
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from starlette.exceptions import StarletteDeprecationWarning

from app.core.config import Settings
from app.main import create_app

warnings.filterwarnings("ignore", category=StarletteDeprecationWarning)

ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = ROOT / "evaluation" / "cases.json"
DEFAULT_OUTPUT = ROOT / "evaluation" / "results.md"
FIXED_NOW = datetime(2026, 8, 21, 12, 0, tzinfo=ZoneInfo("Asia/Kolkata"))


@dataclass(slots=True)
class CaseResult:
    case_id: str
    description: str
    passed: bool
    failures: list[str]
    messages: list[str]
    turns: list[dict[str, Any]]
    analytics: dict[str, Any]


def _contains(text: str, expected: list[str]) -> list[str]:
    lower = text.lower()
    return [needle for needle in expected if needle.lower() not in lower]


def _present(text: str, forbidden: list[str]) -> list[str]:
    lower = text.lower()
    return [needle for needle in forbidden if needle.lower() in lower]


def _evaluate_expectations(
    expected: dict[str, Any],
    final: dict[str, Any],
    analytics: dict[str, Any],
) -> list[str]:
    failures: list[str] = []
    profile = final["profile"]
    booking = final.get("booking")

    mappings = {
        "status": final.get("status"),
        "language": final.get("language"),
        "intent": final.get("intent"),
        "configuration": profile.get("configuration"),
        "budget_crore": profile.get("budget_crore"),
        "purchase_purpose": profile.get("purchase_purpose"),
        "site_visit_status": profile.get("site_visit_status"),
        "follow_up_required": profile.get("follow_up_required"),
        "do_not_contact": profile.get("do_not_contact"),
        "human_escalation_required": profile.get("human_escalation_required"),
        "booking_success": booking.get("success") if booking else None,
        "booking_failure_reason": booking.get("failure_reason") if booking else None,
        "unknown_question_count": len(profile.get("unknown_questions", [])),
    }
    for field, actual in mappings.items():
        if field in expected and actual != expected[field]:
            failures.append(f"{field}: expected {expected[field]!r}, got {actual!r}")

    if "objection" in expected and expected["objection"] not in profile.get("objections", []):
        failures.append(f"objection {expected['objection']!r} was not recorded")

    missing = _contains(final["reply"], expected.get("reply_contains", []))
    if missing:
        failures.append(f"reply missing: {missing}")
    present = _present(final["reply"], expected.get("reply_excludes", []))
    if present:
        failures.append(f"reply included forbidden text: {present}")

    word_count = len(final["reply"].split())
    if word_count > expected.get("maximum_reply_words", 10_000):
        failures.append(f"reply had {word_count} words")

    lead_score = analytics["lead_score"]
    if lead_score < expected.get("minimum_lead_score", 0):
        failures.append(f"lead score {lead_score} was below minimum")
    if lead_score > expected.get("maximum_lead_score", 100):
        failures.append(f"lead score {lead_score} exceeded maximum")
    return failures


def run_cases() -> list[CaseResult]:
    from fastapi.testclient import TestClient

    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    settings = Settings(
        app_env="evaluation",
        ai_provider="demo",
        rate_limit_requests=1000,
        allowed_hosts=("testserver",),
        project_root=ROOT,
    )
    app = create_app(settings, clock=lambda: FIXED_NOW)
    results: list[CaseResult] = []

    with TestClient(app) as client:
        for case in cases:
            created = client.post("/api/sessions", json={"channel": case["channel"]})
            created.raise_for_status()
            session_id = created.json()["session_id"]
            turns: list[dict[str, Any]] = []
            for message in case["messages"]:
                response = client.post(
                    "/api/chat",
                    json={
                        "session_id": session_id,
                        "message": message,
                        "channel": case["channel"],
                    },
                )
                response.raise_for_status()
                turns.append(response.json())
            analytics_response = client.get(f"/api/sessions/{session_id}/analytics")
            analytics_response.raise_for_status()
            analytics = analytics_response.json()
            failures = _evaluate_expectations(case["expect"], turns[-1], analytics)
            results.append(
                CaseResult(
                    case_id=case["id"],
                    description=case["description"],
                    passed=not failures,
                    failures=failures,
                    messages=case["messages"],
                    turns=turns,
                    analytics=analytics,
                )
            )
    return results


def _clean_reply(reply: str, booking_reference: str | None) -> str:
    return reply.replace(booking_reference, "<generated-reference>") if booking_reference else reply


def markdown_report(results: list[CaseResult]) -> str:
    passed = sum(result.passed for result in results)
    latencies = [turn["meta"]["latency_ms"] for result in results for turn in result.turns]
    p95_index = max(0, round((len(latencies) - 1) * 0.95))
    p95 = sorted(latencies)[p95_index] if latencies else 0
    lines = [
        "# Behavioural Evaluation Results",
        "",
        f"Generated with deterministic clock: `{FIXED_NOW.isoformat()}`.",
        "",
        "## Verified result",
        "",
        f"- Scenarios passed: **{passed}/{len(results)} ({passed / len(results) * 100:.1f}%)**",
        f"- Agent-turn latency: **p50 {statistics.median(latencies):.2f} ms; p95 {p95:.2f} ms**",
        "- External LLM calls: **0** (offline deterministic baseline)",
        "- Live-model accuracy/cost/latency: **not measured; an API key was not used**",
        "",
        "> This report proves the deterministic fallback and application rules passed the listed cases. "
        "It does not claim that every possible customer message or external LLM response will pass.",
        "",
        "## Scenario summary",
        "",
        "| Scenario | Expected behaviour | Result |",
        "|---|---|---|",
    ]
    for result in results:
        expected = result.description
        outcome = "PASS" if result.passed else "FAIL: " + "; ".join(result.failures)
        lines.append(f"| `{result.case_id}` | {expected} | **{outcome}** |")

    for result in results:
        final = result.turns[-1]
        reference = final["profile"].get("booking_reference")
        lines.extend(
            [
                "",
                f"## {result.case_id}",
                "",
                f"**Input:** {' → '.join(result.messages)}",
                "",
                f"**Expected:** {result.description}",
                "",
                f"**Actual response:** {_clean_reply(final['reply'], reference)}",
                "",
                f"**Actual state:** intent `{final['intent']}`, status `{final['status']}`, "
                f"language `{final['language']}`, site visit `{final['profile']['site_visit_status']}`, "
                f"lead score `{result.analytics['lead_score']}`.",
                "",
                f"**Result:** {'PASS' if result.passed else 'FAIL'}",
            ]
        )
        if result.failures:
            lines.append(f"\nFailures: {'; '.join(result.failures)}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deterministic conversation evaluations")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--check", action="store_true", help="Do not write; exit non-zero on failure"
    )
    args = parser.parse_args()

    results = run_cases()
    report = markdown_report(results)
    if not args.check:
        args.output.write_text(report, encoding="utf-8")
        print(f"Wrote {args.output.relative_to(ROOT)}")
    failed = [result for result in results if not result.passed]
    if failed:
        for result in failed:
            print(f"FAIL {result.case_id}: {'; '.join(result.failures)}", file=sys.stderr)
        return 1
    print(f"PASS {len(results)}/{len(results)} scenarios")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
