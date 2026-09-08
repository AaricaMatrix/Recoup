"""
run_promise_batch.py

Runs a capped, clearly-labeled sample of events through the promise-to-pay
tracker (see promise_tracker.py for the actual logic) and writes:
  - data/commitments.jsonl        one line per commitment made
  - data/promise_audit_log.jsonl  audit-style entries for the tracked sample
  - data/promise_summary.json     aggregate stats + the fixed-timer comparison
  - promise_dashboard_data.js     same summary, embedded for dashboard.html

This is a SEPARATE script from run_batch.py on purpose — run_batch.py keeps
producing the exact same full-200-event, rule-or-AI-diagnosed baseline it
always has (dashboard_data.js / AUDIT_LOG / SUMMARY are untouched by this
file). This script adds a second, additive data source
(promise_dashboard_data.js) that dashboard.html loads alongside the first
one — so running this is opt-in and never breaks the existing dashboard if
you don't run it.

Why a capped sample instead of the whole batch: the same reason
create_live_links.py caps real Payment Link creation instead of doing it
for all 200 events — this is meant to be inspected in full fidelity
(every commitment, every extraction, every resolution reasoned about
individually), not skimmed at 200-row scale. --limit controls the sample
size.

Usage:
    python run_promise_batch.py                # rule-based extraction, 50-event sample
    python run_promise_batch.py --ai            # real LLM commitment extraction
    python run_promise_batch.py --limit 80
"""

import argparse
import json
from datetime import datetime

from agent import diagnose, decide_intervention, simulate_execution, CHANNEL_COST
from db import repository as repo
from promise_tracker import (
    TRACKABLE_INTERVENTIONS,
    simulate_customer_reply,
    extract_commitment,
    resolve_commitment,
)


def process_event(event, ai_client, now):
    """Runs ONE event through diagnose -> decide -> (promise-aware) execute.
    Returns (audit_entries, commitment_or_None) — audit_entries is a list
    because a broken promise produces a second entry (the escalation), not
    just one.
    """
    root_cause, cause_note = diagnose(event)
    intervention, reason = decide_intervention(event, root_cause)
    base_entry = {
        "event_id": event["event_id"],
        "type": event["type"],
        "timestamp": now.isoformat(),
        "amount_at_risk": event["amount"],
        "root_cause": root_cause,
        "diagnosis_reasoning": cause_note,
        "intervention": intervention,
        "intervention_reasoning": reason,
        "stopping_rule_applied": intervention == "write_off",
    }

    # Write-offs and non-trackable interventions (silent technical retries)
    # behave EXACTLY like the baseline agent — no promise tracking applies,
    # so these rows are directly comparable to run_batch.py's output.
    if intervention not in TRACKABLE_INTERVENTIONS:
        recovered, amount = simulate_execution(event, root_cause, intervention)
        cost = CHANNEL_COST.get(intervention, 0)
        base_entry.update({
            "reply_category": "n/a",
            "commitment_made": False,
            "outcome_recovered": recovered,
            "gross_amount_recovered": round(amount, 2),
            "intervention_cost": cost,
            "naive_baseline_recovered": round(amount, 2),  # identical to actual — nothing to compare
        })
        return [base_entry], None

    reply_text, category = simulate_customer_reply(intervention)
    cost = CHANNEL_COST.get(intervention, 0)

    # Always compute what the OLD fixed-timer policy would have produced for
    # this exact event+intervention — this is the number promise-tracking's
    # "actual" outcome gets compared against in the summary. Computed
    # unconditionally (not just for the promise branch) so every trackable
    # event contributes to a fair, like-for-like total.
    naive_recovered, naive_amount = simulate_execution(event, root_cause, intervention)

    if category == "immediate":
        base_entry.update({
            "reply_category": category,
            "commitment_made": False,
            "outcome_recovered": True,
            "gross_amount_recovered": round(event["amount"], 2),
            "intervention_cost": cost,
            "naive_baseline_recovered": round(naive_amount, 2),
        })
        return [base_entry], None

    if category in ("silence", "no_promise"):
        base_entry.update({
            "reply_category": category,
            "commitment_made": False,
            "outcome_recovered": naive_recovered,
            "gross_amount_recovered": round(naive_amount, 2),
            "intervention_cost": cost,
            "naive_baseline_recovered": round(naive_amount, 2),
        })
        return [base_entry], None

    # category == "promise" from here on
    commitment = extract_commitment(reply_text, event, client=ai_client, now=now)
    if not commitment["has_promise"]:
        # The reply READ like a promise but didn't contain a parseable date
        # (e.g. too vague) — honest fallback to the same untracked path
        # rather than inventing a date the extractor wasn't confident about.
        base_entry.update({
            "reply_category": "promise_unparsed",
            "commitment_made": False,
            "outcome_recovered": naive_recovered,
            "gross_amount_recovered": round(naive_amount, 2),
            "intervention_cost": cost,
            "naive_baseline_recovered": round(naive_amount, 2),
        })
        return [base_entry], None

    commitment["event_id"] = event["event_id"]
    resolution = resolve_commitment(event, root_cause, commitment, intervention=intervention, now=now)

    entry = dict(base_entry)
    entry.update({
        "reply_category": category,
        "commitment_made": True,
        "promised_by": commitment["promised_by"],
        "extraction_method": commitment["extraction_method"],
        "resolution_note": resolution["resolution_note"],
        "naive_baseline_recovered": round(naive_amount, 2),
    })

    if resolution["kept"]:
        entry.update({
            "outcome_recovered": True,
            "gross_amount_recovered": resolution["gross_amount_recovered"],
            "intervention_cost": cost,
        })
        return [entry], commitment

    # Broken promise: log the original attempt as unresolved-then-broken,
    # AND log the escalation as its own audit entry with its own outcome —
    # this is the "escalate on a broken promise, not a timer" behavior the
    # whole feature is built around.
    entry.update({
        "outcome_recovered": False,
        "gross_amount_recovered": 0.0,
        "intervention_cost": cost,
    })

    escalation_intervention = resolution["escalation_intervention"]
    # simulate_execution already special-cases "write_off" to (False, 0.0) —
    # no separate branch needed here, it's the same safe-no-action path
    # agent.py's own decide_intervention() uses when it write-offs an event.
    escalation_recovered, escalation_amount = simulate_execution(event, root_cause, escalation_intervention)
    escalation_cost = CHANNEL_COST.get(escalation_intervention, 0)
    escalation_reasoning = (
        f"a human already handled this and the promise still broke — writing off "
        f"rather than contacting again (was: {intervention})"
        if escalation_intervention == "write_off"
        else f"escalated to a human after the automated promise broke (was: {intervention})"
    )
    escalation_entry = {
        "event_id": event["event_id"],
        "type": event["type"],
        "timestamp": now.isoformat(),
        "amount_at_risk": event["amount"],
        "root_cause": root_cause,
        "diagnosis_reasoning": cause_note,
        "intervention": escalation_intervention,
        "intervention_reasoning": escalation_reasoning,
        "stopping_rule_applied": escalation_intervention == "write_off",
        "reply_category": "n/a",
        "commitment_made": False,
        "outcome_recovered": escalation_recovered,
        "gross_amount_recovered": round(escalation_amount, 2),
        "intervention_cost": escalation_cost,
        "naive_baseline_recovered": 0.0,  # the baseline policy never gets this second chance
    }

    return [entry, escalation_entry], commitment


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ai", action="store_true",
                         help="use a real LLM call to extract commitment dates from replies (needs GROQ_API_KEY)")
    parser.add_argument("--limit", type=int, default=50,
                         help="how many events (from the database, in event_id order) to run through the tracker")
    args = parser.parse_args()

    ai_client = None
    if args.ai:
        from ai_diagnosis import get_ai_client
        ai_client = get_ai_client()
        if ai_client is None:
            print("--ai was passed but GROQ_API_KEY isn't set — falling back to regex extraction for all replies.")

    events = repo.get_events(limit=args.limit, random_order=True)
    if not events:
        raise SystemExit("No events in the database yet — run `python -m db.seed` first.")

    now = datetime.utcnow()
    audit_log = []
    commitments = []

    for event in events:
        entries, commitment = process_event(event, ai_client, now)
        for entry in entries:
            entry["run_type"] = "promise"
            entry.setdefault("diagnosis_method", "rule_based")
        audit_log.extend(entries)
        if commitment:
            # entries[0] is always the original (non-escalation) attempt for
            # a tracked commitment — its outcome_recovered tells us whether
            # THIS promise was kept or broken, without process_event needing
            # to return that as a separate value.
            status = "kept" if entries[0]["outcome_recovered"] else "broken"
            commitment_id = repo.save_commitment(commitment)
            repo.resolve_commitment_status(commitment_id, status)
            commitments.append(commitment)

    repo.save_audit_entries(audit_log)

    # ---- aggregate stats, including the fixed-timer counterfactual ----
    tracked_entries = [e for e in audit_log if e.get("reply_category") not in ("n/a",)]
    replied = [e for e in tracked_entries if e["reply_category"] != "silence"]
    promises = [e for e in tracked_entries if e.get("commitment_made")]
    kept = [e for e in promises if e["outcome_recovered"]]
    broken = [e for e in promises if not e["outcome_recovered"]]

    # Escalation entries (logged separately, right after their broken-promise
    # parent in `audit_log`) count toward the ACTUAL recovered total, since
    # they're a real second chance the fixed-timer baseline never gets.
    actual_recovered = sum(e["gross_amount_recovered"] for e in audit_log)
    naive_recovered = sum(e["naive_baseline_recovered"] for e in audit_log)

    avg_days_requested = 0.0
    if promises:
        days = []
        for e in promises:
            promised = datetime.fromisoformat(e["promised_by"])
            days.append(max(0, (promised - now).days))
        avg_days_requested = round(sum(days) / len(days), 1)

    summary = {
        "sample_size": len(events),
        "trackable_contacts": len(tracked_entries),
        "replied": len(replied),
        "promises_made": len(promises),
        "promises_kept": len(kept),
        "promises_broken": len(broken),
        "kept_rate_pct": round(100 * len(kept) / len(promises), 1) if promises else 0,
        "avg_days_requested": avg_days_requested,
        "actual_recovered_with_promise_tracking": round(actual_recovered, 2),
        "naive_recovered_fixed_timer_baseline": round(naive_recovered, 2),
        "uplift_amount": round(actual_recovered - naive_recovered, 2),
        "uplift_pct": round(
            100 * (actual_recovered - naive_recovered) / naive_recovered, 1
        ) if naive_recovered else 0,
        "extraction_method": "ai_llm" if args.ai and ai_client else "regex_fallback",
    }

    # This run's own numbers (this specific sample) exported for the
    # static dashboard, same as run_batch.py's dashboard_data.js — the live
    # /api/promise-summary endpoint (backed by repo.get_promise_summary())
    # instead reflects ALL commitments ever saved to the database, across
    # every run_promise_batch.py invocation, not just the most recent one.
    with open("promise_dashboard_data.js", "w") as f:
        f.write("const PROMISE_SUMMARY = ")
        json.dump(summary, f)
        f.write(";\nconst COMMITMENTS = ")
        json.dump(commitments, f)
        f.write(";\nconst PROMISE_AUDIT_LOG = ")
        json.dump(audit_log, f)
        f.write(";\n")

    print(json.dumps(summary, indent=2))
    print(f"\n-> {len(audit_log)} audit entries + {len(commitments)} commitments written to the "
          f"database, promise_dashboard_data.js exported")


if __name__ == "__main__":
    main()
