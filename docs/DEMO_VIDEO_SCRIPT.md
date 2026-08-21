# Demo Video Script

Target length: 4–5 minutes.

## 0:00–0:30 — Introduction

“Hi, I’m Kunal. This is my Huvo AI Forward Deployed Engineer assignment: a multilingual sales agent for Northstar Homes. I focused on prompt quality and safe agent behaviour. The backend is FastAPI, and the interface is plain responsive HTML, CSS, and JavaScript.”

Show the repository root and the running interface.

## 0:30–1:15 — Prompt approach

Open `prompts/NORTHSTAR_AGENT_SYSTEM_PROMPT.md`.

“The prompt separates identity, confirmed facts, language matching, qualification, objections, consent, booking, escalation, and clean endings. It works for chat and voice-style turns. The model returns structured JSON, but it does not control irreversible actions.”

Briefly show the strict factual boundary and booking section.

## 1:15–2:15 — Successful Hinglish conversation

Send:

1. `Mujhe 3 BHK chahiye`
2. `Mera budget 2 crore hai`
3. `Self-use ke liye, within 3 months`
4. `Kal 11 am site visit book kar do`

Point out the live lead panel, language matching, retained context, exact ₹1.75 crore “onwards” price, booking reference, and analytics.

Say:

“The reference is generated only after the backend booking service confirms the slot. The model cannot create a booking by writing a convincing sentence.”

## 2:15–2:50 — Failed booking

Start a new conversation and send:

`Please book a site visit on Sunday at 11 am`

Show that it says **not booked** and offers Monday alternatives.

## 2:50–3:20 — Unknown information

Start a new conversation and send:

`Does it have a swimming pool and gym?`

Show that it admits the information is unavailable and offers human help instead of inventing amenities.

## 3:20–3:45 — Do-not-contact

Start a new conversation and send:

`Book tomorrow, but do not contact me again`

Show that DNC wins, booking is not attempted, the lead score becomes zero, and the conversation ends.

## 3:45–4:20 — Architecture and testing

Show the README architecture diagram, then run:

```bash
uv run pytest --cov=app --cov-report=term-missing
uv run python scripts/run_evaluation.py --check
```

Say:

“The build currently has 45 passing tests, 89% branch-aware coverage, and 9 out of 9 deterministic behavioural scenarios. I have not claimed live-model accuracy or cost because I did not use an external key for the measured report.”

## 4:20–4:40 — Closing

“For production, I would replace in-process memory with Redis and PostgreSQL, connect a real CRM and calendar through idempotent tools, add tenant authentication and a durable consent ledger, and run the prompt through a native-speaker multilingual evaluation set. Thank you.”

## Recording checklist

- Use 1080p if possible.
- Zoom browser and editor so text is readable.
- Hide API keys, notifications, bookmarks, and unrelated tabs.
- Keep the terminal at the repository root.
- Record one clean take; do not spend time adding animation.
- Upload as unlisted YouTube, Loom, or viewable Google Drive.
