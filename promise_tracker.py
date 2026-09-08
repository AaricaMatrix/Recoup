"""
promise_tracker.py

Implements the "promise-to-pay tracker" direction: instead of diagnosing
once and blasting a nudge on a fixed schedule, this treats a recovery
contact as the START of a conversation. If the customer's reply contains a
commitment ("I'll pay Friday", "give me 3 days"), the agent tracks THAT
promise and only escalates if it's broken — not on a generic timer that
doesn't know a promise was ever made.

This is a genuinely different control flow, not a UI skin on the same
pipeline:
  fixed-timer model:   contact -> wait N days -> re-contact regardless
  promise-tracking:    contact -> reply -> (if promise) wait until THAT
                        date -> only re-contact (escalate) if broken

Three stages, each independently testable and each with a safety net:
  1. simulate_customer_reply()  — stands in for a real inbound SMS/WhatsApp/
     email reply or call transcript (there's no real two-way channel wired
     up yet, see README "what's simulated vs real")
  2. extract_commitment()       — turns free text into a structured
     {has_promise, promised_by, confidence} record. Tries a real LLM call
     first, falls back to a deterministic keyword+date parser so this
     stage NEVER silently does nothing just because an API call failed.
  3. resolve_commitment()       — simulates, at the promised date, whether
     the customer actually paid, and returns the next action: nothing
     further (kept) or an escalation with a broken-promise reason (broken)
"""

import random
import re
from datetime import datetime, timedelta

# ---------------------------------------------------------------------------
# Stage 1: simulate a customer reply
# ---------------------------------------------------------------------------

# Only interventions that represent an actual message to a human make sense
# to track a reply for. auto_retry/retry_alternate are silent technical
# actions (nobody replies to a card retry), and write_off means we decided
# NOT to contact anyone at all.
TRACKABLE_INTERVENTIONS = {
    "sms_nudge",
    "whatsapp_nudge",
    "email_reminder",
    "hinglish_voice_call",
    "human_collections_handoff",
}

# Reply templates grouped by what they represent. Weights below are
# per-category probabilities, not per-template — a template is chosen
# uniformly at random WITHIN whichever category gets picked.
PROMISE_REPLIES = [
    "I'll pay by Friday, just waiting on my salary.",
    "give me 3 more days and I'll clear it",
    "will pay this by next Monday, sorry for the delay",
    "I can clear this in a week, cash flow is tight right now",
    "paying tomorrow, had a family emergency this week",
    "I'll settle it by the 1st of next month",
    "yes will pay in 2 days",
]
IMMEDIATE_PAYMENT_REPLIES = [
    "already paid this just now, check again",
    "paying right now, one sec",
]
NO_PROMISE_REPLIES = [
    "who is this",
    "I don't think I owe this, please check",
    "not able to pay right now, no idea when",
    "stop messaging me",
]

# Reply-category probabilities by intervention — a human collections call is
# far more likely to produce an explicit verbal promise than a one-way SMS,
# which is far more likely to get no reply at all.
REPLY_PROFILE = {
    "human_collections_handoff": {"promise": 0.55, "immediate": 0.10, "no_promise": 0.15, "silence": 0.20},
    "hinglish_voice_call": {"promise": 0.45, "immediate": 0.08, "no_promise": 0.12, "silence": 0.35},
    "whatsapp_nudge": {"promise": 0.30, "immediate": 0.10, "no_promise": 0.10, "silence": 0.50},
    "sms_nudge": {"promise": 0.20, "immediate": 0.08, "no_promise": 0.07, "silence": 0.65},
    "email_reminder": {"promise": 0.12, "immediate": 0.05, "no_promise": 0.03, "silence": 0.80},
}


def simulate_customer_reply(intervention):
    """Returns (reply_text_or_None, category) where category is one of
    "promise" / "immediate" / "no_promise" / "silence". Stands in for a real
    inbound message — see the module docstring for what's simulated here vs
    what's real elsewhere in this project (the Razorpay Payment Link
    creation and webhook confirmation ARE real, this reply is not).
    """
    profile = REPLY_PROFILE.get(
        intervention,
        {"promise": 0.15, "immediate": 0.05, "no_promise": 0.10, "silence": 0.70},
    )
    roll = random.random()
    cumulative = 0.0
    for category, prob in profile.items():
        cumulative += prob
        if roll < cumulative:
            if category == "silence":
                return None, "silence"
            if category == "promise":
                return random.choice(PROMISE_REPLIES), "promise"
            if category == "immediate":
                return random.choice(IMMEDIATE_PAYMENT_REPLIES), "immediate"
            return random.choice(NO_PROMISE_REPLIES), "no_promise"
    return None, "silence"  # floating point safety net, should be unreachable


# ---------------------------------------------------------------------------
# Stage 2: extract a structured commitment from the reply text
# ---------------------------------------------------------------------------

# Deterministic fallback parser. Covers every phrasing used in
# PROMISE_REPLIES above by construction, which matters: it means the
# fallback path is fully exercised and testable WITHOUT ever calling an
# API, not just a vague "best effort" stub.
_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def _fallback_extract(reply_text, now):
    text = reply_text.lower()

    match = re.search(r"in (\d+) days?", text)
    if match:
        return now + timedelta(days=int(match.group(1))), 0.7

    match = re.search(r"(\d+) more days?", text)
    if match:
        return now + timedelta(days=int(match.group(1))), 0.7

    if "tomorrow" in text:
        return now + timedelta(days=1), 0.75

    if "next week" in text or "a week" in text or "1 week" in text:
        return now + timedelta(days=7), 0.6

    for i, day in enumerate(_WEEKDAYS):
        if day in text:
            # Days until the NEXT occurrence of that weekday (0 means today,
            # bump to next week so "pay by Friday" said ON a Friday means
            # next Friday, not "immediately").
            days_ahead = (i - now.weekday()) % 7
            days_ahead = days_ahead or 7
            return now + timedelta(days=days_ahead), 0.65

    match = re.search(r"(?:by|on) the (\d{1,2})(?:st|nd|rd|th)?", text)
    if match:
        day_of_month = int(match.group(1))
        candidate = now.replace(day=1) + timedelta(days=32)  # jump into next month
        candidate = candidate.replace(day=min(day_of_month, 28))  # 28 keeps this safe for Feb
        return candidate, 0.55

    if "next month" in text:
        return now + timedelta(days=30), 0.5

    # No parseable date phrase, even though the caller thought this reply
    # was a promise category. Being honest about that rather than guessing
    # a date is the point of returning None here — the caller treats a
    # None promised_by as "not confidently a promise", matching how the
    # AI path's own confidence threshold works.
    return None, 0.2


def extract_commitment(reply_text, event, client=None, now=None):
    """Returns a dict: {has_promise, promised_by (ISO date str or None),
    confidence, extraction_method, raw_reply}. `now` is injectable for
    testing; defaults to real UTC now.
    """
    now = now or datetime.utcnow()

    if client is not None:
        try:
            promised_by, confidence = _ai_extract(reply_text, event, now, client)
            method = "ai_llm"
        except Exception:
            promised_by, confidence = _fallback_extract(reply_text, now)
            method = "regex_fallback"
    else:
        promised_by, confidence = _fallback_extract(reply_text, now)
        method = "regex_fallback"

    return {
        "has_promise": promised_by is not None,
        "promised_by": promised_by.date().isoformat() if promised_by else None,
        "confidence": round(confidence, 2),
        "extraction_method": method,
        "raw_reply": reply_text,
    }


def _ai_extract(reply_text, event, now, client):
    """Real LLM call: asks the model to read the reply and return a promised
    payment date as an ISO date string, or null if there isn't a real
    commitment in there. Raises on anything unparseable so the caller falls
    back to the regex parser — same "never trust an unvalidated model
    output" posture as ai_diagnosis.py.
    """
    import json

    from ai_diagnosis import DEFAULT_MODEL, _throttle  # reuse the same throttle clock as diagnosis calls

    prompt = (
        "A customer replied to a payment reminder. Extract whether they made "
        "a commitment to pay by a specific date.\n\n"
        f"Today's date: {now.date().isoformat()}\n"
        f'Customer reply: "{reply_text}"\n\n'
        "Respond with ONLY a JSON object, no markdown fences:\n"
        '{"has_promise": true/false, "promised_by": "<YYYY-MM-DD or null>", '
        '"confidence": <0 to 1>}'
    )
    _throttle()
    response = client.chat.completions.create(
        model=DEFAULT_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=100,
        response_format={"type": "json_object"},
    )
    parsed = json.loads(response.choices[0].message.content.strip().strip("`"))
    if not parsed.get("has_promise"):
        return None, float(parsed.get("confidence", 0.5))
    promised_by = datetime.fromisoformat(parsed["promised_by"])
    confidence = float(parsed["confidence"])
    if not (0 <= confidence <= 1):
        raise ValueError(f"invalid confidence {confidence!r}")
    return promised_by, confidence


# ---------------------------------------------------------------------------
# Stage 3: resolve whether the promise was kept
# ---------------------------------------------------------------------------

# How much a root cause's TRUE recovery odds improve when given more time,
# versus how much of that is just delay dressed up as a promise. Funds-gap
# and cash-flow-delay genuinely resolve with time; chronic delinquency and
# price sensitivity mostly don't — a longer runway doesn't fix a customer
# who was never going to pay.
TIME_SENSITIVITY = {
    "customer_funds_gap": 0.035,
    "cash_flow_delay": 0.03,
    "auth_friction": 0.01,
    "decision_paralysis": 0.015,
    "session_drop": 0.01,
    "instrument_invalid": 0.015,
    "transient_infra_failure": 0.01,
    "risk_flagged_decline": 0.005,
    "price_sensitivity": 0.008,
    "chronic_delinquency": 0.004,
}
MAX_TIME_BONUS = 0.30  # even a very long promise window can't manufacture certainty


def resolve_commitment(event, root_cause, commitment, intervention=None, now=None):
    """Simulates the outcome AT the promised date. Returns a dict describing
    what happened: kept (bool), amount_recovered, and — if broken — the
    escalation intervention/reason to log as the event's next audit entry.

    `intervention` (the channel that got the promise in the first place)
    decides WHAT a broken promise escalates to: a human collections handoff
    if a human wasn't already involved, or a write-off if a human already
    tried and the promise still broke — re-escalating to the exact same
    channel that just failed isn't an escalation, it's a loop, and this
    project's whole stopping-rule philosophy (see agent.py) is "don't chase
    forever," not "keep trying the same thing."
    """
    now = now or datetime.utcnow()
    promised_by = datetime.fromisoformat(commitment["promised_by"])
    days_requested = max(0, (promised_by - now).days)

    base_prob = event["_base_recoverable_prob"]
    time_bonus = min(MAX_TIME_BONUS, TIME_SENSITIVITY.get(root_cause, 0.01) * days_requested)
    # Low-confidence extractions (the regex fallback guessing at a vague
    # reply) get discounted — an uncertain promise shouldn't earn the full
    # time-bonus credit a clearly-stated one does.
    effective_prob = min(0.95, base_prob + time_bonus * commitment["confidence"])

    kept = random.random() < effective_prob

    if kept:
        return {
            "kept": True,
            "outcome_recovered": True,
            "gross_amount_recovered": round(event["amount"], 2),
            "resolution_note": (
                f"promise kept: paid by {commitment['promised_by']} as committed"
            ),
        }

    escalation_intervention = (
        "write_off" if intervention == "human_collections_handoff" else "human_collections_handoff"
    )
    return {
        "kept": False,
        "outcome_recovered": False,
        "gross_amount_recovered": 0.0,
        "escalation_intervention": escalation_intervention,
        "resolution_note": (
            f"broken promise: committed to pay by {commitment['promised_by']}, "
            f"still unpaid as of {now.date().isoformat()} "
            f"-> escalating to {escalation_intervention}"
        ),
    }


def naive_baseline_outcome(event, intervention, from_agent_simulate_execution):
    """The counterfactual: what a FIXED-TIMER policy (the old behavior) would
    have produced for this exact event, using the project's existing
    simulate_execution() unchanged. This is what lets summary.json report an
    honest "promise tracking vs fixed timer" uplift number instead of an
    unfalsifiable claim — same underlying event, same probability model,
    the only thing that differs is whether the policy noticed the promise.
    """
    recovered, amount = from_agent_simulate_execution(event, None, intervention)
    return recovered, amount
