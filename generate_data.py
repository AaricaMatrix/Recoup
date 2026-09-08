"""
generate_data.py
Builds a synthetic batch of "revenue at risk" events across the three
leak points named in the brief: payment failures, checkout abandonment,
and overdue B2B receivables.

This stands in for pulling from Razorpay's test-mode Payments/Orders/
Invoices APIs. The schema mirrors what those APIs actually return
(payment.entity failure_reason/error_code, order.entity status,
invoice.entity due_by) so swapping this generator for a real API pull
is a data-source change, not a rewrite of the agent.
"""

import json
import random
from datetime import datetime, timedelta

random.seed(42)

CUSTOMERS = [f"cust_{i:04d}" for i in range(1, 121)]

PAYMENT_FAILURE_CODES = [
    ("BAD_REQUEST_ERROR", "insufficient_funds", 0.55),
    ("GATEWAY_ERROR", "bank_server_timeout", 0.70),
    ("BAD_REQUEST_ERROR", "card_declined_risk", 0.15),
    ("BAD_REQUEST_ERROR", "expired_card", 0.40),
    ("GATEWAY_ERROR", "issuer_unavailable", 0.65),
]

MERCHANT_CATEGORIES = ["subscription_saas", "d2c_retail", "b2b_services"]


def rand_amount(category):
    if category == "b2b_services":
        return round(random.uniform(15000, 250000), 2)
    if category == "subscription_saas":
        return round(random.uniform(499, 4999), 2)
    return round(random.uniform(399, 8000), 2)


def gen_payment_failures(n, now):
    events = []
    for i in range(n):
        cat = random.choice(MERCHANT_CATEGORIES)
        code, reason, base_recoverable_prob = random.choice(PAYMENT_FAILURE_CODES)
        attempt_count = random.choice([1, 1, 1, 2, 2, 3])
        events.append({
            "event_id": f"pay_{i:04d}",
            "type": "payment_failure",
            "customer_id": random.choice(CUSTOMERS),
            "merchant_category": cat,
            "amount": rand_amount(cat),
            "currency": "INR",
            "error_code": code,
            "failure_reason": reason,
            "prior_attempts": attempt_count,
            "opted_out_of_comms": random.random() < 0.05,
            "created_at": (now - timedelta(hours=random.randint(1, 96))).isoformat(),
            "_base_recoverable_prob": base_recoverable_prob,
        })
    return events


def gen_checkout_abandonment(n, now):
    events = []
    reasons = [
        ("no_payment_method_selected", 0.35),
        ("otp_timeout", 0.60),
        ("price_hesitation", 0.20),
        ("app_backgrounded", 0.45),
    ]
    for i in range(n):
        cat = random.choice(MERCHANT_CATEGORIES)
        reason, base_prob = random.choice(reasons)
        events.append({
            "event_id": f"chk_{i:04d}",
            "type": "checkout_abandonment",
            "customer_id": random.choice(CUSTOMERS),
            "merchant_category": cat,
            "amount": rand_amount(cat),
            "currency": "INR",
            "abandon_reason": reason,
            "prior_attempts": random.choice([1, 1, 2]),
            "opted_out_of_comms": random.random() < 0.05,
            "created_at": (now - timedelta(hours=random.randint(1, 48))).isoformat(),
            "_base_recoverable_prob": base_prob,
        })
    return events


def gen_overdue_receivables(n, now):
    events = []
    for i in range(n):
        days_overdue = random.choice([3, 7, 15, 30, 45, 60])
        base_prob = max(0.15, 0.75 - days_overdue / 100)
        events.append({
            "event_id": f"inv_{i:04d}",
            "type": "overdue_invoice",
            "customer_id": random.choice(CUSTOMERS),
            "merchant_category": "b2b_services",
            "amount": rand_amount("b2b_services"),
            "currency": "INR",
            "days_overdue": days_overdue,
            "prior_attempts": random.choice([0, 1, 1, 2, 3]),
            "opted_out_of_comms": random.random() < 0.03,
            "created_at": (now - timedelta(days=days_overdue)).isoformat(),
            "_base_recoverable_prob": base_prob,
        })
    return events


def main():
    now = datetime.utcnow()
    events = (
        gen_payment_failures(90, now)
        + gen_checkout_abandonment(70, now)
        + gen_overdue_receivables(40, now)
    )
    random.shuffle(events)
    with open("data/events.json", "w") as f:
        json.dump(events, f, indent=2)
    print(f"Wrote {len(events)} events to data/events.json")


if __name__ == "__main__":
    main()
