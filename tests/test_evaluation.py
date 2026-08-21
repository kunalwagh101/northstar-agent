from __future__ import annotations

from scripts.run_evaluation import run_cases


def test_all_behavioural_evaluation_cases_pass() -> None:
    results = run_cases()
    failures = {result.case_id: result.failures for result in results if not result.passed}
    assert not failures, failures
