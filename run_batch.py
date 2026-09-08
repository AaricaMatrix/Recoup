"""
run_batch.py
Runs every event in the database through the agent and:
  - writes one audit_log row per decision (run_type='batch')
  - exports dashboard_data.js — same AUDIT_LOG/SUMMARY shape as before,
    still embedded for the static dashboard so Vercel deploys keep working
    with zero server required

Reads from and writes to data/recoup.db now instead of data/events.json /
data/audit_log.jsonl / data/summary.json — run `python -m db.migrate` and
`python -m db.seed` once first if you haven't already (see README).

AI diagnosis (--ai):
  By default every event is diagnosed by the deterministic rule table in
  agent.diagnose() — same as always. Pass --ai to diagnose the first
  --ai-limit events (default 25) with a REAL Groq LLM call instead
  (see ai_diagnosis.py), falling back to the rule table only if that call
  fails. The rest of the batch stays rule-based.

  Why cap it instead of running all 200 events through the LLM: it keeps
  a full run fast and free-tier-friendly, and it mirrors how
  create_live_links.py already treats "real API calls" as a capped,
  clearly-labeled sample rather than pretending the whole synthetic batch
  is live. summary.json records exactly how many entries used which
  method (diagnosis_method_counts) so this is never hidden from the
  numbers — a mixed rule/AI batch is reported as a mixed rule/AI batch.
"""

import argparse
import json

from agent import run_event
from db import repository as repo


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ai", action="store_true",
                         help="diagnose the first --ai-limit events with a real LLM call (needs GROQ_API_KEY)")
    parser.add_argument("--ai-limit", type=int, default=25,
                         help="how many events get real AI diagnosis when --ai is set")
    args = parser.parse_args()

    events = repo.get_events()
    if not events:
        raise SystemExit("No events in the database yet — run `python -m db.seed` first.")

    ai_client = None
    if args.ai:
        from ai_diagnosis import get_ai_client
        ai_client = get_ai_client()
        if ai_client is None:
            print(
                "--ai was passed but GROQ_API_KEY isn't set — every event will "
                "fall back to rule-based diagnosis (see .env.example)."
            )

    audit_log = []
    for i, event in enumerate(events):
        use_ai_for_this_event = args.ai and i < args.ai_limit
        entry = run_event(event, use_ai=use_ai_for_this_event, ai_client=ai_client)
        entry["run_type"] = "batch"
        audit_log.append(entry)
        if use_ai_for_this_event:
            print(f"  [{i + 1}/{args.ai_limit}] AI-diagnosed {event['event_id']} "
                  f"-> {entry['root_cause']} ({entry['diagnosis_method']})")

    repo.save_audit_entries(audit_log)

    # This run's own numbers in isolation (run_type="batch") — NOT the same
    # as /api/summary, which combines batch + promise + per-event API
    # actions into one live total. dashboard_data.js is a static snapshot
    # of just this run, which is what the static (no-server) dashboard.html
    # export has always shown.
    summary = repo.get_summary(run_type="batch")
    summary["batch_size"] = len(events)

    with open("dashboard_data.js", "w") as f:
        f.write("const AUDIT_LOG = ")
        json.dump(audit_log, f)
        f.write(";\nconst SUMMARY = ")
        json.dump(summary, f)
        f.write(";\n")

    print(json.dumps(summary, indent=2))
    print(f"\n-> {len(audit_log)} audit entries written to the database, dashboard_data.js exported")


if __name__ == "__main__":
    main()
