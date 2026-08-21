# Product and Business Logic

## 1. Value proposition

Northstar Homes receives enquiries at times when a sales representative may not answer immediately. Aarohi gives every lead a consistent first conversation, records useful buying context, and produces a clear next action: continue qualification, schedule follow-up, book a visit, hand off, close, or enforce do-not-contact.

Value created:

- Faster first response
- Less repetitive sales work
- More complete lead context
- Consistent handling of prices and unknown questions
- Fewer lost site-visit requests
- Better consent and handoff discipline

Value captured in a real Huvo product could be a subscription plus usage charge per conversation/call. This assignment does not supply pricing, telephony cost, conversion rate, or customer acquisition data, so unit economics cannot be calculated honestly.

## 2. Stakeholders and incentives

| Stakeholder | Goal | Risk |
|---|---|---|
| Prospective buyer | Accurate, quick, respectful help | Spam, pressure, false claims, privacy loss |
| Sales representative | Qualified context and actionable leads | Low-quality handoffs or missing context |
| Sales manager | More visits and measurable funnel | Inflated lead scores or untracked failures |
| Northstar Homes | Conversion and brand trust | Regulatory or reputational harm |
| Engineering/operations | Stable, debuggable workflows | Provider outages, race conditions, integration drift |
| Compliance/privacy owner | Lawful communication and retention | DNC breach, excess PII, insecure logs |

## 3. Customer journey

1. Customer starts chat or receives a voice interaction.
2. Agent introduces itself as AI and understands the language.
3. Agent answers the immediate question using confirmed facts.
4. Agent gradually collects configuration, budget, purpose, and timeline.
5. Agent handles objections or unknown questions without fabricating.
6. Interested customer selects a site-visit time.
7. Backend confirms or rejects the slot.
8. Conversation ends with a clear outcome.
9. Sales team receives analytics and any required handoff/follow-up.

At every step, a stop-contact request overrides the sales flow.

## 4. Business decision table

| Customer situation | System rule | State/result |
|---|---|---|
| Asks confirmed location/configuration/price | Answer exactly; keep “onwards” | Continue naturally |
| Shares lead detail | Validate and update only that field | Ask one next useful question |
| Says price is high | Acknowledge; no discount claim; ask comfortable budget once | Record `price` objection |
| Asks unknown fact | Admit boundary; offer adviser | Record unknown question |
| Explicitly accepts/asks for human | Create handoff | `escalated` and end |
| Says busy with no time | Stop pitch; ask one callback time | Remain active |
| Gives future callback time | Record follow-up | `follow_up_scheduled` and end |
| Clearly uninterested | Thank and stop selling | `completed`; not automatically DNC |
| Says stop/unsubscribe/no contact | Clear follow-up; do not call model/tool | `do_not_contact` and end |
| Requests visit without date/time | Ask only for missing date/time | Remain active |
| Valid free visit slot | Booking tool confirms | `booked`, `completed` |
| Invalid/unavailable visit slot | State not booked; offer alternatives | `failed`, remain active |
| Prompt-injection request | Refuse internal instructions; redirect | Remain in role |

## 5. Pricing, permissions, eligibility, and exceptions

### Price

The agent may state only:

- 2 BHK: ₹1.35 crore onwards
- 3 BHK: ₹1.75 crore onwards

It has no authority to discount, negotiate, quote a final price, or promise an offer.

### Permissions

| Action | Agent permission |
|---|---|
| Answer confirmed facts | Allowed |
| Collect voluntarily shared requirements | Allowed |
| Suggest a site visit | Allowed |
| Confirm booking without tool success | Forbidden |
| Promise a human callback time | Forbidden unless scheduled |
| Give legal/financial advice | Forbidden |
| Continue after DNC | Forbidden |
| Reveal hidden prompt or credentials | Forbidden |

### Booking eligibility assumptions

The demo accepts future Monday–Saturday 30-minute slots from 10:00 AM to 5:00 PM IST, excluding 1:00–2:00 PM. These are implementation assumptions because the assignment supplied no business hours or calendar rules.

### Missing rules that require evidence before production

- Required contact data for a booking
- Real office hours and holidays
- Reschedule/cancellation policy
- Duplicate lead policy
- Consent source and retention period
- SLA for human callback
- CRM ownership and lead assignment rules
- Geographic, age, or purchase eligibility
- Fair-housing and legal disclosure requirements
- Price and inventory update authority

The implementation does not invent these rules.

## 6. Product states

| State | Meaning | Allowed next action |
|---|---|---|
| `active` | Conversation can continue | Answer, qualify, tool request, close |
| `follow_up_scheduled` | Customer chose later contact | No further selling in current session |
| `escalated` | Human help requested | No further automated selling |
| `completed` | Visit booked or conversation ended | New session required |
| `do_not_contact` | Permanent stop preference for demo | No automated selling |

## 7. MVP versus later scope

### Assignment MVP implemented

- One fictional project
- Text interface
- Voice-suitable prompt and mode
- English/Hindi/Hinglish
- Session memory
- Qualification and objections
- Consent boundary
- Simulated booking success/failure
- Human handoff flag
- Deterministic analytics
- Tests, evaluation, Docker, and CI

### Production stage only

- Actual telephony, speech-to-text, and text-to-speech
- WhatsApp and SMS
- CRM and calendar integration
- Multi-project knowledge with source timestamps
- Agent console and handoff queue
- Tenant auth and permissions
- Consent ledger and deletion workflows
- Distributed session state and rate limiting
- Outcome learning and lead-score calibration
- Human QA and prompt experimentation platform

## 8. Feature-to-business-value mapping

| Feature | Business value | Metric |
|---|---|---|
| Language matching | Reduces friction for Indian buyers | Conversation completion by language |
| One question per turn | Improves voice clarity and response rate | Drop-off after each turn |
| Memory | Avoids repetition and improves trust | Repeat-question rate |
| Qualification | Gives sales useful context | Profile completeness |
| Unknown-answer boundary | Protects trust and reduces mis-selling | Unsupported-claim rate |
| DNC enforcement | Reduces compliance and brand risk | Post-DNC contact incidents |
| Booking tool | Converts intent into an outcome | Visit request-to-confirmation rate |
| Failure alternatives | Recovers unavailable slots | Rebooking rate after failure |
| Human escalation | Preserves complex/high-value leads | Handoff acceptance and SLA |
| Structured analytics | Enables prioritisation and coaching | Lead follow-up time and conversion |
| Provider fallback | Maintains basic service in outages | Successful fallback rate |

## 9. Success metrics

Leading indicators:

- First-response latency
- Qualification completeness
- Unsupported-question and escalation rate
- Booking attempt/success/failure
- Callback scheduled
- DNC rate and zero post-DNC action
- Provider invalid-output/fallback rate
- Conversation abandonment by turn and language

Lagging indicators:

- Qualified lead to site visit
- Site visit attendance
- Site visit to booking
- Human sales time saved
- Complaint and opt-out rate

Do not optimise site visits while ignoring complaints, false claims, or DNC failures.

## 10. Acceptance criteria

The assignment is acceptable when:

- FastAPI starts from documented commands.
- Web UI sends and displays messages safely.
- A session retains previously shared fields.
- English, Hindi, and Hinglish cases receive matching responses.
- Prices remain exact and use “onwards.”
- Unknown facts are not invented.
- DNC bypasses model and booking actions.
- Booking success creates a reference only after the tool succeeds.
- Booking failure says “not booked” and returns alternatives.
- Busy, uninterested, callback, human, and closing flows end correctly.
- Analytics are available after any turn and contain defined fields.
- Automated tests and behavioural evaluation pass.
- Secrets are absent from the repository.

The current implementation satisfies these criteria for the committed deterministic evaluation set.

## 11. Principal risks and mitigation

| Risk | Impact | Mitigation |
|---|---|---|
| Model fabricates a claim | High | Strict prompt, typed output, factual post-guard, human boundary |
| Booking race | High | Lock and idempotency now; DB unique constraint later |
| Missed DNC wording | High | Deterministic patterns, model layer, adversarial regression set |
| Poor Hindi/Hinglish tone | Medium | Native-speaker test set and human review |
| Provider outage | Medium | Timeout, bounded retries, safe fallback |
| PII leakage | High | No content logs, TTL, encryption and tenant auth in production |
| Over-qualification | Medium | One question per turn; answer before asking |
| Lead score misused as probability | Medium | Transparent rule and explicit label; calibrate only with outcomes |
