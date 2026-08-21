from __future__ import annotations

import re

DO_NOT_CONTACT_PATTERN = re.compile(
    r"(?:do\s+not|don['’]?t|never)\s+(?:call|contact|message|text)|"
    r"stop\s+(?:calling|contacting|messaging)|unsubscribe|remove\s+(?:my\s+)?(?:number|contact)|"
    r"(?:mujhe|mereko)\s+(?:call|contact|message)\s+mat|"
    r"(?:call|contact|message)\s+mat\s+kar|"
    r"(?:संपर्क|कॉल|फोन|मैसेज)\s+मत|बात\s+नहीं\s+करनी",
    re.IGNORECASE,
)

PROMPT_INJECTION_PATTERN = re.compile(
    r"ignore\s+(?:all\s+)?(?:previous|prior|system)|system\s+prompt|developer\s+message|"
    r"reveal\s+(?:your\s+)?(?:instructions|prompt)|jailbreak|chain\s+of\s+thought",
    re.IGNORECASE,
)


def is_do_not_contact(message: str) -> bool:
    return bool(DO_NOT_CONTACT_PATTERN.search(message))


def is_prompt_injection(message: str) -> bool:
    return bool(PROMPT_INJECTION_PATTERN.search(message))


def redact_phone_numbers(text: str) -> str:
    return re.sub(r"(?<!\d)(?:\+91[- ]?)?[6-9]\d{9}(?!\d)", "[phone redacted]", text)
