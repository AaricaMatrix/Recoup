"""
create_live_links.py

Takes a capped sample of at-risk events, runs them through the exact same
diagnose() / decide_intervention() logic as the offline batch, and for every
event whose chosen intervention is a "get the customer to pay" action,
creates a REAL Razorpay Payment Link in TEST MODE via the official SDK.

This is the difference between a simulated demo and working software: these
links are real and clickable, payable with Razorpay's own published test
cards. Test-mode keys physically cannot move real money, so this is safe to
run and safe to show a panel.

Usage:
    python create_live_links.py            # first 8 eligible events
    python create_live_links.py --limit 15
"""

import argparse
import hashlib
import os
import random
import time

import razorpay
from dotenv import load_dotenv

from agent import diagnose, decide_intervention

load_dotenv()

KEY_ID = os.getenv("RAZORPAY_KEY_ID")
KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")

# Only these interventions mean "ask the customer to pay" — human handoffs
# and write-offs correctly get no payment link at all.
PAYABLE_INTERVENTIONS = {
    "auto_retry_same_instrument",
    "retry_alternate_instrument",
    "sms_nudge",
    "whatsapp_nudge",
    "email_reminder",
    "hinglish_voice_call",
}


def fake_contact(seed: str) -> str:
    """A distinct, validly-formatted Indian mobile number per event.
    Razorpay's API rejects numbers with long runs of the same digit
    (e.g. 9999999999), so this breaks up any run of 3+ before returning it.
    """
    digest = hashlib.sha256(seed.encode()).hexdigest()
    digits = [str(int(c, 16) % 10) for c in digest[:9]]
    for i in range(2, len(digits)):
        if digits[i] == digits[i - 1] == digits[i - 2]:
            digits[i] = str((int(digits[i]) + 3) % 10)
    first = str(6 + (int(digest[9], 16) % 4))  # valid Indian mobile prefix: 6-9
    return "+91" + first + "".join(digits)


def get_client():
    if not KEY_ID or not KEY_SECRET:
        raise SystemExit(
            "Missing RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET.\n"
            "Copy .env.example to .env and paste your TEST MODE keys\n"
            "(Razorpay Dashboard -> Settings -> API Keys -> Generate Test Key)."
        )
    return razorpay.Client(auth=(KEY_ID, KEY_SECRET))


def build_description(event, root_cause, intervention):
    return f"Recoup recovery | {event['type']} | {root_cause} | via {intervention}"


def build_payload(event, root_cause, intervention):
    """Builds the Razorpay Payment Link request body for ONE event. Split
    out from the batch loop so the new per-event API route
    (POST /api/events/<id>/payment-link) can create exactly the same kind
    of real link for a single event without duplicating this payload
    shape — one definition of "what a Recoup payment link looks like",
    used by both the CLI batch tool and the live API.
    """
    return {
        "amount": int(round(event["amount"] * 100)),
        "currency": "INR",
        "description": build_description(event, root_cause, intervention),
        "customer": {
            "name": event["customer_id"],
            "email": f"{event['customer_id']}@example.com",
            "contact": fake_contact(event["event_id"]),
        },
        # synthetic customers aren't real people, so no actual notification is sent
        "notify": {"sms": False, "email": False},
        "reminder_enable": False,
        "notes": {
            "event_id": event["event_id"],
            "root_cause": root_cause,
            "intervention": intervention,
        },
    }


def create_link_for_event(client, event, root_cause, intervention):
    """The single-event version of what the batch loop below does per
    iteration: build the payload, create the link (with the same retry/
    backoff behavior), return a dict ready for db.repository.upsert_live_link
    or None if Razorpay is still rate-limited after every retry. Raises
    ValueError if `intervention` isn't one that should get a payment link
    at all (write-offs and human handoffs don't) — the API route turns
    that into a 400, the CLI batch loop below just skips via its own
    membership check instead of calling this at all for those events.
    """
    if intervention not in PAYABLE_INTERVENTIONS:
        raise ValueError(
            f"intervention={intervention!r} doesn't get a payment link "
            f"(only {sorted(PAYABLE_INTERVENTIONS)} do)"
        )
    payload = build_payload(event, root_cause, intervention)
    link = create_link_with_retry(client, payload)
    if link is None:
        return None
    return {
        "payment_link_id": link["id"],
        "event_id": event["event_id"],
        "amount": event["amount"],
        "root_cause": root_cause,
        "intervention": intervention,
        "intervention_reasoning": "",  # caller fills this in from decide_intervention()'s own reason
        "short_url": link["short_url"],
        "status": link["status"],
    }


def create_link_with_retry(client, payload, max_retries=6, base_delay=4):
    """Razorpay's test-mode API rate-limits Payment Link creation harder than
    the docs suggest — in practice we've seen it reject requests well under
    1/sec. Back off and retry on 'Too many requests'.

    Returns the created link dict on success, or None if we're STILL
    rate-limited after every retry — the caller decides what to do with a
    None (skip-and-continue, not crash-the-whole-batch), which is the actual
    bug fix here: the old version let the final `raise` escape and kill the
    entire script, losing the chance to create links for every event after
    the one that got unlucky.
    """
    for attempt in range(max_retries + 1):
        try:
            return client.payment_link.create(payload)
        except razorpay.errors.BadRequestError as e:
            is_rate_limit = "Too many requests" in str(e)
            if is_rate_limit and attempt < max_retries:
                # Exponential backoff (4, 8, 16, 32, 64, 128s) plus up to 1s
                # of random jitter — jitter matters once you're calling this
                # for many events in a row, since without it every retry
                # lands on the exact same clock tick and you re-collide with
                # whatever else is hitting the same rate-limit bucket.
                wait = base_delay * (2 ** attempt) + random.uniform(0, 1)
                print(
                    f"  rate-limited, waiting {wait:.1f}s before retry "
                    f"{attempt + 1}/{max_retries}..."
                )
                time.sleep(wait)
                continue
            if is_rate_limit:
                # Exhausted every retry and we're STILL rate-limited — this
                # event goes back to the caller as a "couldn't do it this
                # run" signal instead of raising, so the batch moves on.
                return None
            # Any other Razorpay error (bad payload, invalid amount, etc.)
            # is a real bug, not a transient rate limit — re-raise so it's
            # not silently swallowed alongside rate-limit skips.
            raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=8,
                         help="how many real payment links to create (keep this small for a demo)")
    parser.add_argument("--delay", type=float, default=4.0,
                         help="seconds to wait between each link creation, avoids hitting the rate limit")
    parser.add_argument("--max-skips", type=int, default=3,
                         help="stop early after this many consecutive rate-limit skips, "
                              "instead of grinding through the rest of the batch at a delay "
                              "that's clearly still too fast")
    args = parser.parse_args()

    from db import repository as repo

    events = repo.get_events(random_order=True)
    client = get_client()

    # Resume instead of re-creating links you already have from a prior
    # run — reads from the database now instead of data/live_links.json,
    # same resume behavior either way.
    done_event_ids = {link["event_id"] for link in repo.get_live_links()}
    created_count = len(done_event_ids)
    if created_count:
        print(f"Resuming: {created_count} links already exist in the database")

    consecutive_skips = 0
    current_delay = args.delay

    for event in events:
        if created_count >= args.limit:
            break
        if event["event_id"] in done_event_ids:
            continue

        root_cause, _ = diagnose(event)
        intervention, reason = decide_intervention(event, root_cause)
        if intervention not in PAYABLE_INTERVENTIONS:
            continue  # write-offs and human handoffs don't get a payment link

        if created_count:
            time.sleep(current_delay)

        link_record = create_link_for_event(client, event, root_cause, intervention)

        if link_record is None:
            # Still rate-limited after every retry inside create_link_with_retry.
            # Don't crash, don't mark this event as done — a future run
            # will pick it right back up.
            consecutive_skips += 1
            current_delay = min(current_delay * 1.5, 30)  # cap the growth, don't spiral to minutes
            print(
                f"[{event['event_id']}] skipped — still rate-limited after all retries "
                f"(next attempts will wait {current_delay:.1f}s apart; re-run this "
                f"script later to pick it back up)"
            )
            if consecutive_skips >= args.max_skips:
                print(
                    f"\n{consecutive_skips} consecutive skips — the API is telling us to "
                    f"slow down more than retries alone can fix. Stopping early instead of "
                    f"grinding through the rest of the batch.\n"
                    f"Wait a minute or two, then re-run with a larger --delay, e.g.:\n"
                    f"  python create_live_links.py --limit {args.limit} --delay {current_delay * 2:.0f}"
                )
                break
            continue

        # A real success resets the skip counter — one flaky stretch
        # shouldn't permanently slow down the rest of a long batch.
        consecutive_skips = 0
        created_count += 1

        link_record["intervention_reasoning"] = reason
        repo.upsert_live_link(link_record)
        print(f"[{event['event_id']}] {intervention:<28} -> {link_record['short_url']}  ({link_record['status']})")

    print(f"\n{created_count} real test-mode payment links total -> data/recoup.db (live_links table)")
    print("Open a few of the short_url links above and pay them with a Razorpay test card,")
    print("then run: python check_live_status.py")


if __name__ == "__main__":
    main()
