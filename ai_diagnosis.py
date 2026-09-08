"""
ai_diagnosis.py

This replaces the "diagnose WHY" step with a real LLM call instead of the
if/else lookup table in agent.diagnose(). The lookup table isn't deleted —
it becomes the fallback path, used when there's no API key, the network
call fails, or the model returns something we can't trust. That fallback
is a deliberate design choice, not a shortcut: a revenue-recovery agent
that goes silent or crashes because an LLM provider had a bad minute is a
worse product than one that quietly drops back to a known-safe rule.

WHY THIS IS THE RIGHT PLACE FOR THE LLM CALL, NOT decide_intervention():
diagnose() only produces a root_cause STRING and a reasoning string — it
doesn't choose an action or move money. decide_intervention() reads that
root_cause and picks from a small, fixed, auditable action set (the same
6 interventions + write-off, unchanged). So swapping diagnose() for an LLM
call means the REASONING gets smarter, while the ACTION SPACE stays exactly
as bounded and explainable as before. That split is what makes "genuinely
AI" and "still auditable" both true at once instead of trading one for
the other.

Usage:
    from ai_diagnosis import diagnose_ai, get_ai_client
    client = get_ai_client()                 # None if no API key set
    root_cause, reasoning, confidence, method = diagnose_ai(event, client)
"""

import json
import os
import time

# The exact same root-cause vocabulary agent.diagnose() and
# agent.decide_intervention() already use. This list is the contract
# between the AI and the deterministic decision layer downstream — the
# model is ONLY allowed to pick from here, scoped further by event type
# below, so decide_intervention() never sees a root_cause it doesn't
# already have a branch for.
ALLOWED_ROOT_CAUSES = {
    "payment_failure": [
        "transient_infra_failure",
        "customer_funds_gap",
        "instrument_invalid",
        "risk_flagged_decline",
    ],
    "checkout_abandonment": [
        "auth_friction",
        "decision_paralysis",
        "session_drop",
        "price_sensitivity",
    ],
    "overdue_invoice": [
        "chronic_delinquency",
        "cash_flow_delay",
    ],
}

# One-line description of what each root cause MEANS, shown to the model so
# it's classifying against real definitions instead of guessing from the
# name alone. Kept in sync with the comments in agent.diagnose().
ROOT_CAUSE_DESCRIPTIONS = {
    "transient_infra_failure": "a bank/gateway-side glitch, retryable without the customer doing anything",
    "customer_funds_gap": "the customer's account likely didn't have enough balance at that moment",
    "instrument_invalid": "the payment method itself is broken (expired, blocked), needs a new one",
    "risk_flagged_decline": "the gateway's fraud/risk engine blocked it, forcing a retry could look like fraud",
    "auth_friction": "the customer was trying to pay but an OTP/auth step broke or timed out",
    "decision_paralysis": "the customer reached checkout but didn't pick a payment method",
    "session_drop": "likely an accidental exit (app backgrounded, tab closed), not a real objection",
    "price_sensitivity": "the customer hesitated on price/value, not on a technical problem",
    "chronic_delinquency": "a long-overdue B2B invoice past the point automated reminders work on",
    "cash_flow_delay": "a B2B invoice that's overdue but still within normal reminder-cadence territory",
}

DEFAULT_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
# Groq's free tier is generous but not unlimited — this is a floor on the
# gap between consecutive calls so a full-speed loop over many events
# doesn't immediately trip a per-minute rate limit. Override with the
# GROQ_MIN_INTERVAL_SECONDS env var if your account has different limits.
MIN_INTERVAL_SECONDS = float(os.getenv("GROQ_MIN_INTERVAL_SECONDS", "0.5"))

_last_call_at = 0.0  # module-level clock used by _throttle(), see below


def get_ai_client():
    """Returns a ready Groq client, or None if no API key is configured.
    Returning None (instead of raising) is intentional: every caller of
    diagnose_ai() already has to handle "no client" as a normal case
    (that's what triggers the rule-based fallback), so a missing key is
    just the fallback path taken from the very first call, not a crash.
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return None
    # Imported lazily, inside the function, so importing this module (or
    # agent.py, which imports this module) never requires the `groq`
    # package to be installed if you're only ever running the rule-based
    # path — matches how the rest of this project treats razorpay/flask
    # as "only needed if you use that script" dependencies.
    from groq import Groq

    return Groq(api_key=api_key)


def _throttle():
    """Sleeps just long enough to keep calls at least MIN_INTERVAL_SECONDS
    apart. A module-level `_last_call_at` (rather than a class/instance) is
    fine here because run_batch.py calls this from a single-threaded loop —
    there's no concurrent access to race on.
    """
    global _last_call_at
    elapsed = time.time() - _last_call_at
    if elapsed < MIN_INTERVAL_SECONDS:
        time.sleep(MIN_INTERVAL_SECONDS - elapsed)
    _last_call_at = time.time()


def _event_context_lines(event):
    """Pulls out exactly the fields relevant to diagnosis, in the same
    spirit as agent.diagnose()'s branching — the model sees the same
    signals the rule table keys off (failure_reason/abandon_reason/
    days_overdue), plus a bit more raw context (error_code, prior_attempts,
    merchant_category) the rule table doesn't use but a model reasoning in
    free text can actually make use of.
    """
    t = event["type"]
    lines = [
        f"event_type: {t}",
        f"merchant_category: {event.get('merchant_category', 'unknown')}",
        f"amount: {event['amount']} {event.get('currency', 'INR')}",
        f"prior_attempts: {event.get('prior_attempts', 0)}",
    ]
    if t == "payment_failure":
        lines.append(f"error_code: {event.get('error_code', 'unknown')}")
        lines.append(f"failure_reason: {event.get('failure_reason', 'unknown')}")
    elif t == "checkout_abandonment":
        lines.append(f"abandon_reason: {event.get('abandon_reason', 'unknown')}")
    elif t == "overdue_invoice":
        lines.append(f"days_overdue: {event.get('days_overdue', 0)}")
    return "\n".join(lines)


def _build_prompt(event):
    t = event["type"]
    allowed = ALLOWED_ROOT_CAUSES.get(t, [])
    definitions = "\n".join(f'- "{rc}": {ROOT_CAUSE_DESCRIPTIONS[rc]}' for rc in allowed)
    return (
        "You are the diagnosis stage of a revenue-recovery agent for an Indian "
        "payments platform. Given one at-risk event, decide WHY the money is at "
        "risk — not just that it is — by picking exactly one root cause from the "
        "allowed list below and explaining your reasoning in one short sentence.\n\n"
        f"Allowed root causes for event_type={t} (pick exactly one, verbatim):\n"
        f"{definitions}\n\n"
        "Event:\n"
        f"{_event_context_lines(event)}\n\n"
        "Respond with ONLY a JSON object, no markdown fences, no extra text, in "
        "exactly this shape:\n"
        '{"root_cause": "<one of the allowed values above, verbatim>", '
        '"reasoning": "<one short sentence, specific to this event, not generic>", '
        '"confidence": <number between 0 and 1>}'
    )


def _parse_ai_response(raw_text, event_type):
    """Turns the model's raw text into a validated (root_cause, reasoning,
    confidence) tuple, or raises ValueError if anything about it can't be
    trusted. Every raise here is a deliberate guardrail — a plausible-
    looking but wrong root_cause is worse than an honest fallback, because
    decide_intervention() would silently act on it downstream.
    """
    # Models sometimes wrap JSON in ```json fences even when told not to —
    # strip those before parsing rather than failing on the first stray
    # backtick.
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()

    parsed = json.loads(text)  # raises json.JSONDecodeError -> caught by caller

    root_cause = parsed.get("root_cause")
    reasoning = parsed.get("reasoning")
    confidence = parsed.get("confidence")

    allowed = ALLOWED_ROOT_CAUSES.get(event_type, [])
    if root_cause not in allowed:
        raise ValueError(
            f"model returned root_cause={root_cause!r}, not one of the "
            f"allowed values for {event_type}: {allowed}"
        )
    if not isinstance(reasoning, str) or not reasoning.strip():
        raise ValueError("model returned empty or non-string reasoning")
    if not isinstance(confidence, (int, float)) or not (0 <= confidence <= 1):
        raise ValueError(f"model returned invalid confidence={confidence!r}")

    return root_cause, reasoning.strip(), float(confidence)


def diagnose_ai(event, client, max_retries=2):
    """The main entry point. Tries a real LLM call first; on ANY problem
    (no client, network error, bad JSON, invalid category), falls back to
    the exact same deterministic diagnose() agent.py already had — so this
    function ALWAYS returns a usable, decide_intervention()-compatible
    result no matter what.

    Returns (root_cause, reasoning, confidence, method) where method is
    "ai_llm" or "rule_based_fallback" — that fourth field is what makes the
    fallback honest instead of invisible: it gets logged in the audit trail
    (see agent.run_event), so nobody can mistake a fallback run for a real
    AI call after the fact.
    """
    # Local import avoids a circular import at module load time (agent.py
    # imports this module; this function needs agent.diagnose as the
    # fallback), and keeps agent.py importable even in environments that
    # never touch AI diagnosis at all.
    from agent import diagnose as diagnose_rule_based

    if client is None:
        root_cause, reasoning = diagnose_rule_based(event)
        return root_cause, reasoning, None, "rule_based_fallback"

    prompt = _build_prompt(event)
    last_error = None

    for attempt in range(max_retries + 1):
        try:
            _throttle()
            response = client.chat.completions.create(
                model=DEFAULT_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,  # low temperature: this is a classification task, not creative writing
                max_tokens=200,
                # Groq's OpenAI-compatible API supports forcing valid JSON
                # output — this alone doesn't guarantee our SPECIFIC shape
                # (still validated in _parse_ai_response), but it rules out
                # the model wrapping the JSON in prose.
                response_format={"type": "json_object"},
            )
            raw_text = response.choices[0].message.content
            root_cause, reasoning, confidence = _parse_ai_response(raw_text, event["type"])
            return root_cause, reasoning, confidence, "ai_llm"
        except Exception as e:  # network errors, rate limits, bad JSON, invalid category — all land here
            last_error = e
            if attempt < max_retries:
                time.sleep(1.5 * (attempt + 1))
                continue

    # Every attempt failed — fall back, but don't fail silently: the
    # reasoning field says exactly why, so it shows up in the audit trail
    # and in dashboard.html rather than looking like an unexplained
    # rule-based entry.
    root_cause, reasoning = diagnose_rule_based(event)
    reasoning = f"{reasoning} (AI diagnosis unavailable: {last_error})"
    return root_cause, reasoning, None, "rule_based_fallback"
