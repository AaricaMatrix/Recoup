"""
webhook_server.py

The webhook route now lives in api_server.py (see its module docstring
for why: one Flask app instead of two, so per-event actions and real-time
payment confirmation share the same server and the same database
connection helper). This file is kept as a one-line entry point purely so
`python webhook_server.py` — the command from the original setup docs —
still works exactly like it used to, without anyone needing to remember
the command changed.

For the real setup steps (ngrok, Razorpay webhook config, test card
numbers), see api_server.py's /webhook route and README.md's "Going
live" section.
"""

from api_server import app, WEBHOOK_SECRET

if __name__ == "__main__":
    if not WEBHOOK_SECRET:
        print("Warning: RAZORPAY_WEBHOOK_SECRET is not set — every webhook call will be rejected.")
    app.run(port=5000)
