"""
db/seed.py

Populates the `events` table for a demo run. This is the SQL-backed
analog of Revyn's prisma/seed.ts — same purpose (get a demo-ready dataset
into the database with one command), implemented by REUSING
generate_data.py's existing gen_payment_failures() / gen_checkout_abandonment()
/ gen_overdue_receivables() functions rather than duplicating that logic
here. generate_data.py itself still works standalone too (still writes
data/events.json) — this just gives the same events a second, queryable
home in the database.

Usage:
    python -m db.seed              # wipes and reseeds events (200 events)
    python -m db.seed --keep       # only seeds if the events table is empty
"""

import argparse
from datetime import datetime

from db.connection import get_connection
from generate_data import gen_payment_failures, gen_checkout_abandonment, gen_overdue_receivables


def build_events():
    """Same 90/70/40 split and same random.seed(42) as generate_data.main()
    — reusing the functions (not reimplementing the split) means this can
    never silently drift out of sync with what generate_data.py produces
    standalone.
    """
    now = datetime.utcnow()
    return (
        gen_payment_failures(90, now)
        + gen_checkout_abandonment(70, now)
        + gen_overdue_receivables(40, now)
    )


def seed(conn, events):
    conn.executemany(
        """
        INSERT OR REPLACE INTO events (
            event_id, type, customer_id, merchant_category, amount, currency,
            error_code, failure_reason, abandon_reason, days_overdue,
            prior_attempts, opted_out_of_comms, created_at, _base_recoverable_prob
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                e["event_id"], e["type"], e["customer_id"], e["merchant_category"],
                e["amount"], e["currency"],
                e.get("error_code"), e.get("failure_reason"),
                e.get("abandon_reason"), e.get("days_overdue"),
                e["prior_attempts"], int(e["opted_out_of_comms"]),
                e["created_at"], e["_base_recoverable_prob"],
            )
            for e in events
        ],
    )
    conn.commit()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep", action="store_true",
                         help="only seed if the events table is currently empty, "
                              "don't wipe existing events (and their audit history)")
    args = parser.parse_args()

    conn = get_connection()

    if args.keep:
        count = conn.execute("SELECT COUNT(*) AS n FROM events").fetchone()["n"]
        if count > 0:
            print(f"events table already has {count} rows and --keep was passed — not reseeding.")
            conn.close()
            return

    events = build_events()
    seed(conn, events)
    print(f"Seeded {len(events)} events -> {conn.execute('SELECT COUNT(*) AS n FROM events').fetchone()['n']} total rows in events table")
    conn.close()


if __name__ == "__main__":
    main()
