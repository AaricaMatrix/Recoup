"""
check_live_status.py

Polls Razorpay for the real, current status of every payment link created by
create_live_links.py, and reports which ones actually got paid.

outcome_recovered is only True when Razorpay's own /payment_links/:id endpoint
says status == "paid" — nothing here is inferred, assumed, or simulated.

Usage:
    python check_live_status.py
"""

import os

import razorpay
from dotenv import load_dotenv

from db import repository as repo

load_dotenv()
client = razorpay.Client(auth=(os.getenv("RAZORPAY_KEY_ID"), os.getenv("RAZORPAY_KEY_SECRET")))


def main():
    links = repo.get_live_links()
    if not links:
        raise SystemExit("No live links in the database yet — run create_live_links.py first.")

    total_at_risk = 0.0
    total_recovered = 0.0

    for entry in links:
        live = client.payment_link.fetch(entry["payment_link_id"])
        paid = live["status"] == "paid"
        total_at_risk += entry["amount"]
        total_recovered += entry["amount"] if paid else 0

        # Writes the real status straight back into the same live_links
        # table create_live_links.py populated — the same row webhook_server.py's
        # /webhook route would also update in real time, so polling and
        # webhook confirmation both converge on one source of truth instead
        # of two separate result files that could disagree.
        entry["status"] = live["status"]
        entry["outcome_recovered"] = paid
        repo.upsert_live_link(entry)

        tag = "PAID" if paid else live["status"].upper()
        print(f"[{entry['event_id']}] {entry['short_url']}  -> {tag}")

    recovery_rate = round(100 * total_recovered / total_at_risk, 2) if total_at_risk else 0
    print(f"\n₹{total_recovered:.0f} / ₹{total_at_risk:.0f} recovered on real test-mode links "
          f"({recovery_rate}%) -> live_links table updated")


if __name__ == "__main__":
    main()
