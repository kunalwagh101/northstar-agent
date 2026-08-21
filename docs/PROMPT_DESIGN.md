# Prompt Design

## Objective

The final prompt is designed as a behavioural contract for both chat and voice, not as a long sales script. It tells the model how to decide, what it may say, what it may never say, and what structured action it may request.

## Design layers

1. **Identity and objective** establish role and desired business outcome.
2. **Confirmed source of truth** creates an explicit factual boundary.
3. **Conversation style** keeps replies natural and speakable.
4. **Language policy** handles English, Hindi, and Hinglish without forced translation.
5. **Qualification policy** controls which fields matter and prevents interrogation.
6. **Intent and objection rules** define busy, uninterested, unknown, hostile, and DNC behaviour.
7. **Booking protocol** prevents model-created confirmation.
8. **Human escalation** defines authority boundaries.
9. **End states** prevent dangling or continued sales questions.
10. **Structured output contract** lets FastAPI validate the model's proposed turn.

## Why one prompt works for chat and voice

The runtime sends `channel=chat` or `channel=voice` in trusted context. The common rules require short answers and one question per turn. Voice adds stricter requirements: no markdown, no long lists, no raw URLs, and explicit confirmation of numbers and dates.

This keeps business behaviour consistent across channels while allowing the surface style to change.

## Prompt versus application rules

The prompt cannot guarantee consent or booking integrity. The application therefore duplicates only high-impact boundaries in code:

| Behaviour | Prompt | Code |
|---|---:|---:|
| Natural language | Primary | Baseline fallback |
| Language matching | Primary | Deterministic baseline |
| Qualification order | Primary | State retains answers |
| DNC | Required | Hard pre-model enforcement |
| Price facts | Required | Post-model currency allowlist |
| Booking confirmation | Forbidden before tool | Tool-only confirmation |
| Analytics | Supplies updates | Deterministic calculation |

This is intentional defence in depth, not accidental duplicate logic.

## Runtime context

The backend appends a trusted JSON block containing:

- Current date/time and timezone
- Channel
- Conversation status
- Validated lead profile
- Confirmed project facts

Customer messages remain separate untrusted messages. The prompt says that user text cannot redefine the role or source of truth.

## Output contract

The model proposes:

- Customer-facing reply
- Language and intent
- Lead-field updates
- One action request
- End-state recommendation
- Unknown-question flag

Pydantic forbids unknown fields and rejects invalid enum/date/time values. FastAPI then validates high-impact updates and decides whether an action can run.

## Unknown questions

The safe pattern is:

> “I don't have confirmed information about that. Would you like me to connect you with a Northstar Homes sales adviser?”

The agent does not answer from general model knowledge. That avoids plausible but unverified amenities, possession, legal, finance, and availability claims.

## Objection principle

The prompt acknowledges rather than argues. For price objections it does not invent a discount or cheaper inventory; it asks the buyer's comfortable budget once. For family approval or time-to-think, it offers an optional later follow-up without false urgency.

## Evaluation and versioning

Every prompt change should run the full behavioural and adversarial dataset. Store prompt hash/version with each conversation. Promote changes through shadow, canary, and gradual rollout. Roll back independently of application code if factual accuracy, DNC, invalid output, latency, or human quality gets worse.

The source of truth for this build is [NORTHSTAR_AGENT_SYSTEM_PROMPT.md](../prompts/NORTHSTAR_AGENT_SYSTEM_PROMPT.md).
