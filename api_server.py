"""
api_server.py

The live backend behind the per-event dashboard pages (risks.html,
recoveries.html, audit.html) and the thing that makes "act on ONE event"
possible at all — mirrors Revyn's src/app/api/recover/[id]/{decide,
payment-link} routes, same idea (diagnose/decide/act as three separate,
individually-callable actions on a single event), same underlying
agent.py logic as every batch script, just exposed one event at a time
instead of only in a loop.

This also absorbs webhook_server.py's job (see the /webhook route below)
— one Flask app, one place real-time payment confirmation and per-event
actions both live, instead of two separate servers you'd have to run at
once. webhook_server.py itself now just imports and runs this same app,
so `python webhook_server.py` still works exactly like it used to.

Security notes (why each thing below is here, not just that it's here):
  - Every DB read/write goes through db/repository.py, which only ever
    uses parameterized `?` queries — this file never builds SQL itself,
    so it inherits that injection safety for free.
  - Rate limiting (Flask-Limiter) on every route, tighter on
    /payment-link specifically, since that one makes a REAL Razorpay API
    call and re-triggering the same rate-limit crash create_live_links.py
    used to hit is exactly what unrestricted per-event calls could cause.
  - State-changing routes (POST) require an `X-Requested-With` header,
    which a plain cross-origin HTML form cannot set — this blocks the
    classic form-based CSRF pattern without needing session cookies or a
    CSRF token store, which this stateless local-demo API doesn't
    otherwise have any use for.
  - app.run(debug=...) defaults to OFF. Flask's debugger, if left on and
    the port is ever reachable from outside your machine, allows remote
    code execution — there's no scenario in this project where that
    trade-off is worth it, even for a demo.

Usage:
    python api_server.py
    # then open http://localhost:5000/dashboard.html (or risks.html, etc.)
"""

import hashlib
import hmac
import os
from datetime import datetime
from functools import wraps

from dotenv import load_dotenv
from flask import Flask, abort, jsonify, request, send_from_directory
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from agent import diagnose, decide_intervention, simulate_execution, CHANNEL_COST
from db import repository as repo

load_dotenv()

app = Flask(__name__, static_folder=".", static_url_path="")
limiter = Limiter(get_remote_address, app=app, default_limits=["60 per minute"])

WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")


def require_ajax_header(fn):
    """Blocks the classic CSRF pattern (an attacker's page auto-submits a
    plain HTML form to this endpoint using the victim's browser session) —
    a plain form submission can't set a custom header without triggering a
    CORS preflight that this server never approves, so a request that
    reaches this decorator without the header didn't come from a bare
    cross-origin <form>. Not a replacement for real auth if this ever
    stops being a local, no-login demo tool.
    """
    @wraps(fn)
    def wrapper(*a, **kw):
        if request.headers.get("X-Requested-With") != "XMLHttpRequest":
            abort(403, "missing X-Requested-With header")
        return fn(*a, **kw)
    return wrapper


def get_event_or_404(event_id):
    event = repo.get_event(event_id)
    if event is None:
        abort(404, f"no event with id {event_id!r}")
    return event


# ---------------------------------------------------------------------------
# Static pages — Flask serves the HTML/CSS/JS files directly so everything
# runs from one origin (http://localhost:5000) and the dashboard pages can
# `fetch('/api/...')` with no CORS configuration needed at all.
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return send_from_directory(".", "dashboard.html")


# ---------------------------------------------------------------------------
# Read endpoints
# ---------------------------------------------------------------------------

@app.route("/api/events")
def list_events():
    limit = request.args.get("limit", type=int)
    offset = request.args.get("offset", 0, type=int)
    return jsonify(repo.get_events(limit=limit, offset=offset))


@app.route("/api/events/<event_id>")
def get_event(event_id):
    event = get_event_or_404(event_id)
    event["status"] = repo.get_event_status(event_id)
    return jsonify(event)


@app.route("/api/audit")
def get_audit():
    rows = repo.get_audit_log(
        event_type=request.args.get("type"),
        intervention=request.args.get("intervention"),
        recovered_only=request.args.get("recovered_only") == "true",
        search=request.args.get("search"),
        limit=request.args.get("limit", 500, type=int),
    )
    return jsonify(rows)


@app.route("/api/summary")
def get_summary():
    return jsonify(repo.get_summary())


@app.route("/api/commitments")
def get_commitments():
    return jsonify(repo.get_commitments())


@app.route("/api/promise-summary")
def get_promise_summary():
    return jsonify(repo.get_promise_summary())


@app.route("/api/live-links")
def get_live_links():
    return jsonify(repo.get_live_links())


# ---------------------------------------------------------------------------
# Per-event actions — the actual new capability. Each one does exactly one
# stage (diagnose OR decide OR act), matching agent.py's own three-stage
# split, and requires the previous stage to have already run — you can't
# decide an intervention for an event that hasn't been diagnosed yet, same
# as the batch pipeline never would either.
# ---------------------------------------------------------------------------

@app.route("/api/events/<event_id>/diagnose", methods=["POST"])
@require_ajax_header
@limiter.limit("20 per minute")
def diagnose_event(event_id):
    event = get_event_or_404(event_id)
    body = request.get_json(silent=True) or {}
    use_ai = bool(body.get("ai", False))

    if use_ai:
        from ai_diagnosis import diagnose_ai, get_ai_client
        client = get_ai_client()
        root_cause, reasoning, confidence, method = diagnose_ai(event, client)
    else:
        root_cause, reasoning = diagnose(event)
        confidence, method = None, "rule_based"

    repo.upsert_event_status(
        event_id,
        root_cause=root_cause,
        diagnosis_reasoning=reasoning,
        diagnosis_method=method,
        diagnosis_confidence=confidence,
    )
    return jsonify({
        "event_id": event_id, "root_cause": root_cause, "diagnosis_reasoning": reasoning,
        "diagnosis_method": method, "diagnosis_confidence": confidence,
    })


@app.route("/api/events/<event_id>/decide", methods=["POST"])
@require_ajax_header
@limiter.limit("20 per minute")
def decide_event(event_id):
    event = get_event_or_404(event_id)
    status = repo.get_event_status(event_id)
    if not status or not status["root_cause"]:
        abort(400, "this event hasn't been diagnosed yet — call /diagnose first")

    intervention, reason = decide_intervention(event, status["root_cause"])
    repo.upsert_event_status(event_id, intervention=intervention, intervention_reasoning=reason)
    return jsonify({"event_id": event_id, "intervention": intervention, "intervention_reasoning": reason})


@app.route("/api/events/<event_id>/payment-link", methods=["POST"])
@require_ajax_header
@limiter.limit("6 per minute")  # tighter — this makes a REAL Razorpay API call
def create_payment_link_for_event(event_id):
    event = get_event_or_404(event_id)
    status = repo.get_event_status(event_id)
    if not status or not status["intervention"]:
        abort(400, "this event hasn't been decided yet — call /decide first")

    from create_live_links import get_client, create_link_for_event, PAYABLE_INTERVENTIONS

    if status["intervention"] not in PAYABLE_INTERVENTIONS:
        abort(400, f"intervention {status['intervention']!r} doesn't get a payment link "
                    f"(write-offs and human handoffs don't)")

    try:
        client = get_client()
    except SystemExit as e:
        abort(400, str(e))  # missing Razorpay keys — a config problem, not a server crash

    link_record = create_link_for_event(client, event, status["root_cause"], status["intervention"])
    if link_record is None:
        abort(429, "Razorpay is rate-limiting payment link creation right now — try again shortly")

    link_record["intervention_reasoning"] = status["intervention_reasoning"]
    repo.upsert_live_link(link_record)
    repo.upsert_event_status(event_id, payment_link_id=link_record["payment_link_id"])

    repo.save_audit_entries([{
        "event_id": event_id, "run_type": "api",
        "timestamp": datetime.utcnow().isoformat(),
        "amount_at_risk": event["amount"], "root_cause": status["root_cause"],
        "diagnosis_reasoning": status["diagnosis_reasoning"], "diagnosis_method": status["diagnosis_method"],
        "diagnosis_confidence": status["diagnosis_confidence"],
        "intervention": status["intervention"], "intervention_reasoning": status["intervention_reasoning"],
        "stopping_rule_applied": False, "outcome_recovered": None,  # unknown until Razorpay confirms payment
        "gross_amount_recovered": 0, "intervention_cost": CHANNEL_COST.get(status["intervention"], 0),
        "net_amount_recovered": 0,
    }])

    return jsonify(link_record)


@app.route("/api/events/<event_id>/simulate", methods=["POST"])
@require_ajax_header
@limiter.limit("20 per minute")
def simulate_event(event_id):
    """The offline alternative to /payment-link — runs agent.simulate_execution
    instead of touching real Razorpay, for a write-off/human-handoff
    intervention (which never gets a real link) or when you just want to
    see a simulated outcome without spending a real API call.
    """
    event = get_event_or_404(event_id)
    status = repo.get_event_status(event_id)
    if not status or not status["intervention"]:
        abort(400, "this event hasn't been decided yet — call /decide first")

    recovered, amount = simulate_execution(event, status["root_cause"], status["intervention"])
    cost = CHANNEL_COST.get(status["intervention"], 0)
    net = (amount - cost) if recovered else (0 if status["intervention"] == "write_off" else -cost)

    repo.save_audit_entries([{
        "event_id": event_id, "run_type": "api",
        "timestamp": datetime.utcnow().isoformat(),
        "amount_at_risk": event["amount"], "root_cause": status["root_cause"],
        "diagnosis_reasoning": status["diagnosis_reasoning"], "diagnosis_method": status["diagnosis_method"],
        "diagnosis_confidence": status["diagnosis_confidence"],
        "intervention": status["intervention"], "intervention_reasoning": status["intervention_reasoning"],
        "stopping_rule_applied": status["intervention"] == "write_off", "outcome_recovered": recovered,
        "gross_amount_recovered": round(amount, 2), "intervention_cost": cost, "net_amount_recovered": round(net, 2),
    }])

    return jsonify({"event_id": event_id, "outcome_recovered": recovered, "gross_amount_recovered": round(amount, 2)})


# ---------------------------------------------------------------------------
# Webhook — absorbed from webhook_server.py, see that file's new one-line body
# ---------------------------------------------------------------------------

def _verify_webhook_signature(body: bytes, signature: str) -> bool:
    if not WEBHOOK_SECRET:
        return False
    expected = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)  # constant-time, see webhook_server.py's original comment on why


@app.route("/webhook", methods=["POST"])
@limiter.limit("120 per minute")  # Razorpay may retry deliveries; don't choke on a legitimate burst
def webhook():
    signature = request.headers.get("X-Razorpay-Signature", "")
    if not _verify_webhook_signature(request.data, signature):
        abort(400, "invalid or missing webhook signature")

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        abort(400, "request body is not valid JSON")

    if payload.get("event") == "payment_link.paid":
        try:
            link = payload["payload"]["payment_link"]["entity"]
        except (KeyError, TypeError):
            abort(400, "unexpected payment_link.paid payload shape")

        payment_link_id = link.get("id", "")
        updated = repo.mark_link_paid(payment_link_id)
        if updated:
            print(f"CONFIRMED PAID  link={payment_link_id}  -> live_links table updated")
        else:
            print(f"webhook for unknown payment_link_id={payment_link_id} (ignored)")

    return jsonify({"status": "ok"})


if __name__ == "__main__":
    if not WEBHOOK_SECRET:
        print("Note: RAZORPAY_WEBHOOK_SECRET is not set — /webhook will reject every call "
              "until you set it (only needed if you're using ngrok + Razorpay's webhook feature).")
    debug_mode = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    app.run(port=5000, debug=debug_mode)
