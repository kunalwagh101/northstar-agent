# Submission Email

**To:** aditi@huvo.ai
**CC:** nikhil@huvo.ai, vaibhav@huvo.ai, rohit@huvo.ai
**Subject:** Forward Deployed Engineer Assignment — Kunal Wagh

Hi Aditi,

Please find my completed Forward Deployed Engineer assignment below.

GitHub repository: https://github.com/kunalwagh101/northstar-agent

Demo video: `<LOOM_OR_VIDEO_LINK>`

I built the application with a FastAPI backend and a responsive text interface. The agent supports English, Hindi, and Hinglish, maintains conversation context, qualifies leads, handles objections and consent, simulates successful and failed site-visit bookings, supports human handoff, and generates structured lead analytics.

My main design decision was to separate conversational judgement from business actions. The AI can request a booking, but only the backend booking service can confirm it. Stop-contact requests are also enforced before any model call.

The repository includes the final system prompt, source code, setup instructions, assumptions, limitations, Docker configuration, tests, and actual behavioural evaluation outputs.

Thank you for reviewing the assignment. I would be happy to walk through any part of the prompt or implementation.

Best,
Kunal Wagh
