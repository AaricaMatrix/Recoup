"""
agent.py
The actual recovery agent. Three explicit stages per event, mirroring
the brief exactly: detect -> diagnose -> intervene, inside a bounded
and auditable loop.

Every decision is logged with its reasoning BEFORE the outcome is known,
so the audit trail can't be accused of rationalizing after the fact.

Stopping rules (compliance-shaped, not just "keep retrying"):
  - never contact a customer flagged opted_out_of_comms
  - max 3 total recovery attempts per event, ever
  - overdue invoices >45 days auto-escalate to a human collections
    step instead of another automated nudge
  - low-value events (< amount_floor) below a cost-of-recovery
    threshold are auto-written-off rather than chased forever
"""

import random
from datetime import datetime

MAX_ATTEMPTS = 3
WRITE_OFF_FLOOR = {
    "payment_failure": 150,
    "checkout_abandonment": 150,
    "overdue_invoice": 2000,
}
ESCALATE_DAYS_OVERDUE = 45

# cost per intervention channel, used to compute NET recovered, not just gross
CHANNEL_COST = {
    "auto_retry_same_instrument": 2,
    "retry_alternate_instrument": 2,
    "sms_nudge": 0.35,
    "whatsapp_nudge": 0.5,
    "email_reminder": 0.1,
    "hinglish_voice_call": 8,
    "human_collections_handoff": 45,
    "write_off": 0,
}


def diagnose(event):
    """Stage 1: figure out WHY the money is at risk, not just THAT it is."""
    t = event["type"]
    if t == "payment_failure":
        reason = event["failure_reason"]
        if reason in ("bank_server_timeout", "issuer_unavailable"):
            return "transient_infra_failure", "retryable without customer action"
        if reason == "insufficient_funds":
            return "customer_funds_gap", "needs a delay + retry, not an instant retry"
        if reason == "expired_card":
            return "instrument_invalid", "needs a new payment method, not a retry"
        return "risk_flagged_decline", "gateway suspects fraud risk, do not force-retry"

    if t == "checkout_abandonment":
        reason = event["abandon_reason"]
        if reason == "otp_timeout":
            return "auth_friction", "customer intended to pay, auth step broke"
        if reason == "no_payment_method_selected":
            return "decision_paralysis", "needs a lightweight nudge back to checkout"
        if reason == "app_backgrounded":
            return "session_drop", "likely accidental exit, short nudge should work"
        return "price_sensitivity", "needs incentive-based recovery, not a plain nudge"

    if t == "overdue_invoice":
        if event["days_overdue"] > ESCALATE_DAYS_OVERDUE:
            return "chronic_delinquency", "past automated-recovery window"
        return "cash_flow_delay", "standard B2B reminder cadence applies"

    return "unclassified", "no diagnosis rule matched"


def decide_intervention(event, root_cause):
    """Stage 2: pick ONE bounded action. Every branch is explainable in
    one sentence, which is the point: no action should need a black box."""
    t = event["type"]

    if event["opted_out_of_comms"]:
        return "write_off", "customer opted out of comms, no contact permitted"

    if event["amount"] < WRITE_OFF_FLOOR.get(t, 0):
        return "write_off", f"amount below cost-effective recovery floor for {t}"

    if event["prior_attempts"] >= MAX_ATTEMPTS:
        return "write_off", "hit max-attempts stopping rule, further contact is spam"

    if t == "payment_failure":
        if root_cause == "transient_infra_failure":
            return "auto_retry_same_instrument", "infra issue, same card will likely clear"
        if root_cause == "instrument_invalid":
            return "sms_nudge", "ask customer to update payment method"
        if root_cause == "customer_funds_gap":
            return "whatsapp_nudge", "delayed retry window, nudge to retry after payday-like gap"
        return "email_reminder", "risk-flagged decline, low-pressure channel only"

    if t == "checkout_abandonment":
        if root_cause == "auth_friction":
            return "sms_nudge", "quick link back past the broken auth step"
        if root_cause in ("decision_paralysis", "session_drop"):
            return "whatsapp_nudge", "low-friction return-to-cart nudge"
        return "hinglish_voice_call", "price-sensitive, needs a human-feeling touch"

    if t == "overdue_invoice":
        if root_cause == "chronic_delinquency":
            return "human_collections_handoff", "past automation window, needs a human"
        if event["days_overdue"] >= 15:
            return "human_collections_handoff", "aging past 15 days, escalate before it chronic-ifies"
        return "email_reminder", "standard B2B reminder cadence"

    return "write_off", "no rule matched, defaulting to safe no-action"


def simulate_execution(event, root_cause, intervention):
    """Stage 3: 'execute' the bounded action. In production this is the
    call to Razorpay (create a Payment Link, trigger a subscription
    retry, fire a notification) — here it's a probabilistic outcome
    so the batch produces HONEST mixed results, not a cherry-picked win.
    """
    if intervention == "write_off":
        return False, 0.0

    base = event["_base_recoverable_prob"]
    channel_lift = {
        "auto_retry_same_instrument": 0.05,
        "retry_alternate_instrument": 0.10,
        "sms_nudge": 0.08,
        "whatsapp_nudge": 0.10,
        "email_reminder": -0.05,
        "hinglish_voice_call": 0.18,
        "human_collections_handoff": 0.15,
    }.get(intervention, 0.0)

    prob = max(0.02, min(0.95, base + channel_lift))
    recovered = random.random() < prob
    amount_recovered = event["amount"] if recovered else 0.0
    return recovered, amount_recovered


def run_event(event, use_ai=False, ai_client=None):
    """
    use_ai=False (the default) runs the exact same deterministic path this
    function always has — nothing about existing behavior changes unless
    you opt in.

    use_ai=True swaps ONLY the diagnose() call for a real LLM call
    (ai_diagnosis.diagnose_ai). decide_intervention() and simulate_execution()
    are untouched either way: the action space stays bounded and auditable
    regardless of which diagnosis path produced the root_cause feeding into
    it. See ai_diagnosis.py's module docstring for the reasoning behind
    keeping the split there.
    """
    if use_ai:
        # Imported here (not at module top) so agent.py has zero hard
        # dependency on the `groq` package or GROQ_API_KEY unless a caller
        # explicitly asks for AI diagnosis.
        from ai_diagnosis import diagnose_ai

        root_cause, cause_note, confidence, diagnosis_method = diagnose_ai(event, ai_client)
    else:
        root_cause, cause_note = diagnose(event)
        confidence, diagnosis_method = None, "rule_based"

    intervention, reason = decide_intervention(event, root_cause)
    recovered, amount_recovered = simulate_execution(event, root_cause, intervention)
    cost = CHANNEL_COST.get(intervention, 0)
    net_recovered = amount_recovered - cost if recovered else -cost if intervention != "write_off" else 0.0

    audit_entry = {
        "event_id": event["event_id"],
        "type": event["type"],
        "timestamp": datetime.utcnow().isoformat(),
        "amount_at_risk": event["amount"],
        "root_cause": root_cause,
        "diagnosis_reasoning": cause_note,
        # New fields — additive only, so any code (dashboard.html included)
        # that doesn't know about them yet keeps working unchanged.
        "diagnosis_method": diagnosis_method,  # "ai_llm" | "rule_based" | "rule_based_fallback"
        "diagnosis_confidence": confidence,    # float 0-1 from the model, or None for rule-based
        "intervention": intervention,
        "intervention_reasoning": reason,
        "stopping_rule_applied": intervention == "write_off",
        "outcome_recovered": recovered,
        "gross_amount_recovered": round(amount_recovered, 2),
        "intervention_cost": cost,
        "net_amount_recovered": round(net_recovered, 2),
    }
    return audit_entry
