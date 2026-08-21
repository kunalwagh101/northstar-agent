"use strict";

const state = {
  sessionId: null,
  channel: "chat",
  busy: false,
  ended: false,
  profile: null,
};

const elements = {
  messages: document.querySelector("#messages"),
  welcome: document.querySelector("#welcome-state"),
  form: document.querySelector("#chat-form"),
  input: document.querySelector("#message-input"),
  send: document.querySelector("#send-button"),
  typing: document.querySelector("#typing-indicator"),
  quickReplies: document.querySelector("#quick-replies"),
  newChat: document.querySelector("#new-chat"),
  analyticsButton: document.querySelector("#view-analytics"),
  analyticsDialog: document.querySelector("#analytics-dialog"),
  analyticsGrid: document.querySelector("#analytics-grid"),
  analyticsSummary: document.querySelector("#analytics-summary"),
  closeAnalytics: document.querySelector("#close-analytics"),
  dialogNewChat: document.querySelector("#dialog-new-chat"),
  banner: document.querySelector("#connection-banner"),
  toast: document.querySelector("#toast"),
  channelButtons: document.querySelectorAll(".channel-button"),
  fields: {
    configuration: document.querySelector("#field-configuration"),
    budget: document.querySelector("#field-budget"),
    purpose: document.querySelector("#field-purpose"),
    timeline: document.querySelector("#field-timeline"),
    visit: document.querySelector("#field-visit"),
    language: document.querySelector("#field-language"),
    score: document.querySelector("#lead-score"),
  },
};

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  if (!response.ok) {
    let message = "Something went wrong. Please try again.";
    try {
      const payload = await response.json();
      message = payload.detail || message;
    } catch (_) {
      // The safe generic message is used when a non-JSON upstream error occurs.
    }
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }
  return response.status === 204 ? null : response.json();
}

function setBusy(value) {
  state.busy = value;
  elements.input.disabled = value || state.ended;
  elements.send.disabled = value || state.ended;
  elements.typing.hidden = !value;
}

function scrollMessages() {
  elements.messages.scrollTop = elements.messages.scrollHeight;
}

function addMessage(role, text) {
  if (elements.welcome) {
    elements.welcome.remove();
    elements.welcome = null;
  }

  const row = document.createElement("div");
  row.className = `message-row ${role}`;

  const bubble = document.createElement("div");
  bubble.className = "message-bubble";
  bubble.textContent = text;

  const time = document.createElement("span");
  time.className = "message-time";
  time.textContent = new Intl.DateTimeFormat("en-IN", {
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date());

  bubble.appendChild(time);
  row.appendChild(bubble);
  elements.messages.appendChild(row);
  scrollMessages();
}

function humanize(value) {
  if (value === null || value === undefined || value === "unknown") return "Not shared";
  return String(value)
    .replaceAll("_", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function updateProfile(profile) {
  if (!profile) return;
  state.profile = profile;
  elements.fields.configuration.textContent = profile.configuration || "Not shared";
  elements.fields.budget.textContent = profile.budget_raw || "Not shared";
  elements.fields.purpose.textContent = humanize(profile.purchase_purpose);
  elements.fields.timeline.textContent = profile.purchase_timeline || "Not shared";
  elements.fields.visit.textContent = humanize(profile.site_visit_status || "not_requested");
  elements.fields.language.textContent = humanize(profile.language);

  const interest = profile.interest_level || "unknown";
  elements.fields.score.textContent = interest === "unknown" ? "New lead" : `${humanize(interest)} interest`;
  elements.fields.score.className = `score-pill ${interest}`;
}

function showBanner(message) {
  elements.banner.textContent = message;
  elements.banner.hidden = false;
}

function clearBanner() {
  elements.banner.hidden = true;
  elements.banner.textContent = "";
}

function showToast(message) {
  elements.toast.textContent = message;
  elements.toast.hidden = false;
  window.setTimeout(() => {
    elements.toast.hidden = true;
  }, 3200);
}

async function startSession({ deleteExisting = false } = {}) {
  if (state.busy) return;
  setBusy(true);
  clearBanner();

  if (deleteExisting && state.sessionId) {
    try {
      await api(`/api/sessions/${encodeURIComponent(state.sessionId)}`, { method: "DELETE" });
    } catch (_) {
      // A missing or expired old session does not block a fresh conversation.
    }
  }

  try {
    const payload = await api("/api/sessions", {
      method: "POST",
      body: JSON.stringify({ channel: state.channel }),
    });
    state.sessionId = payload.session_id;
    state.ended = false;
    state.profile = null;
    elements.messages.replaceChildren();
    elements.quickReplies.hidden = false;
    elements.analyticsButton.disabled = true;
    updateProfile({
      configuration: null,
      budget_raw: null,
      purchase_purpose: "unknown",
      purchase_timeline: null,
      site_visit_status: "not_requested",
      language: "english",
      interest_level: "unknown",
    });
    addMessage("assistant", payload.greeting);
    elements.input.placeholder = state.channel === "voice" ? "Type as you would speak…" : "Write a message…";
  } catch (error) {
    showBanner(error.message);
  } finally {
    setBusy(false);
    elements.input.focus();
  }
}

async function sendMessage(text) {
  const message = text.trim();
  if (!message || state.busy || state.ended) return;
  if (!state.sessionId) {
    await startSession();
    if (!state.sessionId) return;
  }

  clearBanner();
  elements.quickReplies.hidden = true;
  addMessage("user", message);
  elements.input.value = "";
  resizeInput();
  setBusy(true);
  scrollMessages();

  try {
    const payload = await api("/api/chat", {
      method: "POST",
      body: JSON.stringify({
        session_id: state.sessionId,
        message,
        channel: state.channel,
      }),
    });
    addMessage("assistant", payload.reply);
    updateProfile(payload.profile);
    state.ended = payload.conversation_ended;
    elements.analyticsButton.disabled = false;

    if (payload.meta.fallback_used) {
      showToast("AI provider was unavailable. Safe demo mode answered this turn.");
    }
    if (state.ended) {
      elements.input.placeholder = "Conversation ended";
      showToast("Conversation completed. Lead analytics are ready.");
    }
  } catch (error) {
    addMessage("assistant", "I’m sorry, I couldn’t process that message. Please try again.");
    showBanner(error.message);
    if (error.status === 404 || error.status === 410) {
      state.sessionId = null;
      showToast("The session expired. Start a new conversation.");
    }
  } finally {
    setBusy(false);
    if (!state.ended) elements.input.focus();
  }
}

function analyticsItem(label, value) {
  const item = document.createElement("div");
  item.className = "analytics-item";
  const key = document.createElement("span");
  key.textContent = label;
  const content = document.createElement("strong");
  content.textContent = value === null || value === undefined || value === "" ? "Not shared" : humanize(value);
  item.append(key, content);
  return item;
}

async function openAnalytics() {
  if (!state.sessionId) return;
  try {
    const data = await api(`/api/sessions/${encodeURIComponent(state.sessionId)}/analytics`);
    elements.analyticsSummary.textContent = data.summary;
    elements.analyticsGrid.replaceChildren(
      analyticsItem("Lead score", `${data.lead_score} / 100`),
      analyticsItem("Completeness", `${data.qualification_completeness}%`),
      analyticsItem("Interest", data.interest_level),
      analyticsItem("Configuration", data.configuration),
      analyticsItem("Budget", data.budget),
      analyticsItem("Purpose", data.purchase_purpose),
      analyticsItem("Timeline", data.purchase_timeline),
      analyticsItem("Site visit", data.site_visit_status),
      analyticsItem("Follow-up", data.follow_up_required ? "Required" : "Not required"),
      analyticsItem("Human handoff", data.human_escalation_required ? "Required" : "Not required"),
      analyticsItem("Do not contact", data.do_not_contact ? "Yes" : "No"),
      analyticsItem("Status", data.conversation_status),
    );
    elements.analyticsDialog.showModal();
  } catch (error) {
    showBanner(error.message);
  }
}

function resizeInput() {
  elements.input.style.height = "auto";
  elements.input.style.height = `${Math.min(elements.input.scrollHeight, 120)}px`;
}

elements.form.addEventListener("submit", (event) => {
  event.preventDefault();
  sendMessage(elements.input.value);
});

elements.input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    elements.form.requestSubmit();
  }
});

elements.input.addEventListener("input", resizeInput);

elements.quickReplies.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-message]");
  if (button) sendMessage(button.dataset.message);
});

elements.newChat.addEventListener("click", () => startSession({ deleteExisting: true }));
elements.dialogNewChat.addEventListener("click", () => {
  elements.analyticsDialog.close();
  startSession({ deleteExisting: true });
});
elements.analyticsButton.addEventListener("click", openAnalytics);
elements.closeAnalytics.addEventListener("click", () => elements.analyticsDialog.close());

elements.analyticsDialog.addEventListener("click", (event) => {
  if (event.target === elements.analyticsDialog) elements.analyticsDialog.close();
});

elements.channelButtons.forEach((button) => {
  button.addEventListener("click", () => {
    state.channel = button.dataset.channel;
    elements.channelButtons.forEach((candidate) => {
      const active = candidate === button;
      candidate.classList.toggle("active", active);
      candidate.setAttribute("aria-pressed", String(active));
    });
    elements.input.placeholder = state.channel === "voice" ? "Type as you would speak…" : "Write a message…";
    showToast(state.channel === "voice" ? "Voice-style replies enabled." : "Chat-style replies enabled.");
  });
});

startSession();
