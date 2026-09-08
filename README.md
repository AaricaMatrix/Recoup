# Recoup — an AI Revenue Recovery agent

Built for the **Razorpay AI Buildathon, Track 03: AI Revenue Recovery**.

## The problem

Revenue rarely disappears in one clean step. A card gets declined, a
checkout gets abandoned mid-OTP, an invoice quietly goes overdue. Most
teams either ignore this leakage or blast every customer with the same
generic "please pay" message regardless of *why* the money is stuck —
and regardless of what the customer already told them.

## What Recoup does

Recoup runs at-risk revenue events through three explicit, auditable
stages:

1. **Diagnose** — figure out *why* the money is stuck. This is a real
   LLM call (see "Genuinely AI, not a rule table" below), not a lookup
   table pretending to reason.
2. **Decide** — pick exactly one bounded intervention per event, with a
   one-sentence reason attached, chosen from a small fixed action set
   (retry, SMS nudge, WhatsApp nudge, email, voice call, human
   collections handoff, or write-off). This stays deterministic
   regardless of how the diagnosis was made — see why below.
3. **Act + log** — simulate execution and log the decision *before* the
   outcome is known, so the audit trail can't be accused of
   rationalizing after the fact.

On top of that base pipeline, two things happen after contact instead of
stopping at "message sent":

- **A reply gets tracked, not just a send** — the promise-to-pay tracker
  (below) treats the first contact as the start of a conversation, not
  the end of one.
- **A real payment closes the loop automatically** — the webhook route in
  `api_server.py` updates the `live_links` table the instant Razorpay
  confirms a real test-mode payment, instead of that confirmation only
  reaching a terminal print statement.

## Genuinely AI, not a rule table

Most "AI revenue recovery" demos — including ones we looked at building
this — describe their diagnosis step as "AI-agent-ready architecture,
deterministic today." That's an honest way to describe a rule table, but
it means the diagnosis itself isn't actually using AI yet.

`ai_diagnosis.py` swaps that lookup table for a real Groq LLM call that
reads the actual failure text/error code for each event and returns a
root cause plus a one-sentence reasoning, in one API call per event —
verifiable by reading the code, not just claimed in this README.

**Why the LLM call lives in `diagnose()` and nowhere else:** `diagnose()`
only produces a root-cause string and a reasoning string. It doesn't
choose an action or move any money. `decide_intervention()` reads that
root cause and picks from the same small, fixed, auditable action set as
before — completely unchanged. So the reasoning gets smarter while the
action space stays exactly as bounded and explainable. That split is
what makes "genuinely AI" and "still auditable" both true at once,
instead of trading one for the other.

**What happens if the API call fails, or the model hallucinates a
category we don't have a branch for:** it falls back to the exact same
deterministic rule table that used to be the only option — and that
fallback is *never* silent. Every audit-log entry carries a
`diagnosis_method` field (`ai_llm`, `rule_based`, or
`rule_based_fallback`), and a fallback's `diagnosis_reasoning` says
plainly why it fell back. `run_batch.py`'s summary reports
`diagnosis_method_counts` so a mixed AI/rule-based run is reported as a
mixed run, not dressed up as fully AI.

```bash
# rule-based only (default, always works, no API key needed)
python run_batch.py

# real LLM diagnosis on the first 25 events, rule-based for the rest
python run_batch.py --ai --ai-limit 25
```

Get a free Groq API key at [console.groq.com/keys](https://console.groq.com/keys)
(no card required), put it in `.env` as `GROQ_API_KEY`.

## The promise-to-pay tracker

The brief itself suggests this direction, and it's a genuinely different
mental model, not a UI change on the same pipeline:

| | fixed-timer approach | promise tracker |
|---|---|---|
| after contact | wait N days, re-contact regardless | wait for a reply |
| if customer says "I'll pay Friday" | irrelevant, still recontacted on schedule | tracked — no further contact until Friday |
| when does it escalate | on a timer, whether or not it's warranted | only when a *specific promise* is broken |

`promise_tracker.py` implements this in three stages, each independently
testable:

1. **`simulate_customer_reply()`** — stands in for a real inbound
   SMS/WhatsApp/email reply or call transcript. There's no real two-way
   channel wired up in this project (see "what's simulated vs real"
   below) — this generates a realistic reply (a promise, an immediate
   payment, a refusal, or silence) weighted by how likely a *human*
   channel is to get a real reply vs a one-way SMS blast.
2. **`extract_commitment()`** — turns free text like *"give me 3 more
   days"* into a structured `{has_promise, promised_by, confidence}`
   record. Tries a real LLM call first (same Groq setup as diagnosis),
   falls back to a deterministic date parser that's been tested against
   every phrasing the reply bank actually generates — so this stage
   never silently does nothing just because an API call failed.
3. **`resolve_commitment()`** — simulates, at the promised date, whether
   the customer paid. The odds of a promise being kept scale with *how
   much a delay genuinely helps that root cause* — a customer with a
   temporary funds gap benefits a lot from a week's grace; someone
   chronically delinquent barely does. That calibration is what makes
   the honest counterfactual below defensible instead of a made-up
   number.

**Broken promises escalate, they don't just re-nudge**: a broken promise
hands off to a human collections agent — unless a human already tried,
in which case it's written off instead of looping back to the same
channel that already failed (matches this project's existing "don't
chase forever" stopping-rule philosophy).

**The honest comparison** — for every tracked event, `run_promise_batch.py`
also computes what the *old* fixed-timer policy (`agent.simulate_execution`,
completely unchanged) would have produced for that exact same event. Same
starting probability, same event, the only difference is whether the
policy noticed the promise:

```bash
python run_promise_batch.py               # regex-based extraction, 50-event sample
python run_promise_batch.py --ai           # real LLM commitment extraction
python run_promise_batch.py --limit 80
```

One real run on a 60-event sample:

```
sample_size: 60          trackable_contacts: 45      replied: 21
promises_made: 14        kept: 8   broken→escalated: 6   kept_rate: 57.1%
avg_days_requested: 6.3
actual_recovered_with_promise_tracking: ₹12,59,545
naive_recovered_fixed_timer_baseline:   ₹11,75,229
uplift: +₹84,315 (+7.2%)
```
(Re-running produces different numbers — it's a random simulation, not a
fixed demo script. That's deliberate: a cherry-picked single run would be
exactly the kind of unfalsifiable claim this README is trying to avoid.)

**One modeling assumption worth stating plainly**: the "naive baseline" is
one automated attempt with no follow-up — the way a batch job typically
treats "sent, mark resolved" today. It is NOT a full multi-round
fixed-cadence sequence that also eventually escalates to a human after
repeated failures (agent.py's own 3-attempt cap implies real fixed-timer
systems often do exactly that). Modeling that fuller sequence would need
its own simulation layer and isn't done here — so part of the uplift
number reflects "we escalate immediately on a broken promise" rather than
"we escalate eventually anyway," and that distinction matters if you're
asked to defend the number live.

Open `dashboard.html` after running this — it renders a "Promise-to-pay
tracker" panel with these stats and the individual tracked commitments,
in the same paper/ledger styling as the rest of the dashboard. If you
haven't run `run_promise_batch.py` yet, the panel says so instead of
showing broken or fake data.

## What's simulated vs real — the honest map

| Piece | Status |
|---|---|
| Diagnosis reasoning (`--ai` mode) | **Real** — actual Groq API call, actual model output |
| Payment Link creation (`create_live_links.py`) | **Real** — actual Razorpay test-mode API, actual clickable links |
| Payment confirmation (`webhook_server.py`, `check_live_status.py`) | **Real** — actual Razorpay webhook / polling API, `outcome_recovered` only ever set from Razorpay's own `status` field |
| Customer replies (`promise_tracker.simulate_customer_reply`) | **Simulated** — there's no real inbound SMS/WhatsApp/voice channel wired up. This generates realistic text, it does not receive real messages. |
| Commitment extraction from a reply | **Real LLM call available**, tested regex fallback always available |
| Outreach delivery (SMS/WhatsApp/voice actually being sent) | **Not implemented** — `sms_nudge` etc. are decision *labels* the agent picks; no Twilio/WhatsApp Business API call actually fires yet |

## Stopping rules (the part most demos skip)

- Never contacts anyone flagged `opted_out_of_comms`.
- Hard cap of 3 recovery attempts per event, ever.
- Invoices overdue more than 45 days auto-escalate to a human instead of
  another automated nudge.
- Low-value events below a per-category cost-of-recovery floor are
  written off instead of chased forever — chasing a ₹120 failed payment
  with a ₹45 human handoff is a loss, not a win.
- A broken promise escalates once, not indefinitely — if a human
  collections agent already tried and the promise still broke, the event
  is written off rather than looping back through the same channel.

## The numbers (one run, untouched afterward)

On a synthetic batch of 200 events (₹1.33 Cr at risk across payment
failures, checkout abandonment, and overdue invoices):

- **45.5% gross recovery rate**, ~₹60.7L recovered
- 170 events acted on, 30 auto-written-off by the stopping rules
- 54.7% win rate on the events actually acted on
- Full per-channel win rate available via `/api/summary` (or
  `data/summary.json` if you're still on the pre-database version) —
  nothing cherry-picked, the worst-performing channel (Hinglish voice
  call, 21% win rate) is reported alongside the best.

Run it yourself:

```bash
pip install -r requirements.txt
cp .env.example .env              # then paste in your Razorpay/Groq keys
python -m db.migrate              # creates data/recoup.db from db/migrations/
python -m db.seed                 # populates the events table (200 synthetic events)
python run_batch.py               # rule-based batch (add --ai --ai-limit 25 for real LLM diagnosis)
```

Then either open `dashboard.html` directly in a browser (works with zero
server, reads the static `dashboard_data.js` this just exported) — or run
`python api_server.py` and open `http://localhost:5000` for the live,
per-event version (see the next section).

## Real database + per-event actions

Everything above used to live in flat JSON files (`data/events.json`,
`data/audit_log.jsonl`, `data/live_links.json`, `data/commitments.jsonl`).
It's now a real SQLite database (`data/recoup.db`), with a proper
migration file (`db/migrations/0001_init.sql`) instead of hand-editing
JSON — the same idea as a `prisma/schema.prisma` + `prisma migrate`
setup, just with SQLite instead of Postgres so there's no separate
database server to install or host for a hackathon demo.

`db/repository.py` is the only place any SQL gets written — every query
uses parameterized `?` placeholders, never a string-built query, which is
what actually prevents SQL injection (not just "being careful"). Every
script (`run_batch.py`, `run_promise_batch.py`, `check_live_status.py`)
and the API below all read and write through this one file, so the
recovery-rate/win-rate math is computed in exactly one place and can't
drift out of sync between them.

**Per-event actions** — `api_server.py` exposes diagnose, decide, and act
as three separate, individually-callable actions on ONE event, instead of
only ever running in a 200-event loop:

```
POST /api/events/<id>/diagnose      # rule-based, or {"ai": true} for a real LLM call
POST /api/events/<id>/decide        # requires the event already diagnosed
POST /api/events/<id>/simulate      # offline simulated outcome
POST /api/events/<id>/payment-link  # REAL Razorpay payment link — requires the event already decided
GET  /api/events/<id>               # current status of one event
GET  /api/events | /api/audit | /api/summary | /api/commitments | /api/promise-summary
```

Every state-changing route needs an `X-Requested-With: XMLHttpRequest`
header (the frontend's `apiPost()` helper in `shared.js` always sends it)
— a plain cross-origin HTML form can't set that header, which blocks the
classic CSRF pattern without needing session cookies or a token store.
Rate limiting (Flask-Limiter) applies to every route, tighter on
`/payment-link` specifically (6/minute) since that one makes a real
Razorpay API call and unrestricted per-event clicking could reproduce the
same rate-limit crash `create_live_links.py` used to hit before it was
fixed.

**Four dashboard pages**, all served by `api_server.py` from one origin
(no CORS setup needed):

- `dashboard.html` — the original funnel/breakdown overview. Still works
  with zero server (reads static `dashboard_data.js`), for a Vercel deploy.
- `audit.html` — **the per-event action explorer**. Every row gets its
  own Diagnose / Decide / Simulate / Real payment link buttons, live
  against the database.
- `risks.html` — every root cause within each leak-point type (not just
  the type-level total), plus the largest at-risk events with no outcome
  yet.
- `recoveries.html` — only the wins, with a by-channel breakdown.

```bash
python api_server.py
# open http://localhost:5000  (or click through the nav bar from dashboard.html)
```

`webhook_server.py` still works exactly like before — it's now a
one-line shim that runs `api_server.py`'s app, since the webhook route
lives there too (one server, one database connection, instead of two
separate processes writing to two separate files that could disagree).

The offline batch above simulates execution so the numbers are
reproducible. This part is not simulated — it creates real Razorpay
Payment Links in test mode, which you can actually open and pay with
Razorpay's own test cards. Test-mode keys physically cannot move real
money, so this is safe to run and safe to show a panel.

**Setup (takes about 3 minutes):**

1. Sign up at [razorpay.com](https://razorpay.com) — no KYC needed for test mode.
2. In the Dashboard, make sure you're in **Test Mode** (toggle, top left).
3. Settings -> API Keys -> Generate Test Key. Copy the Key ID and Key Secret.
4. `pip install -r requirements.txt`
5. `cp .env.example .env` and paste your keys in.

**Create real payment links:**

```bash
python create_live_links.py --limit 8
```

This diagnoses a randomly-mixed sample of events (across all three leak
points, not just whichever type happens to sort first) with the exact
same `agent.py` logic as the offline batch, and for every event where the
agent decided on a "get the customer to pay" intervention, creates a real
Razorpay Payment Link. It prints each link's `short_url` and saves them
to the `live_links` table. If Razorpay's test-mode rate limit kicks in,
it backs off adaptively and skips-and-continues instead of crashing the
whole run — re-run the same command later and it picks up exactly where
it left off (already-created links aren't recreated).

**Pay a couple of them** with a Razorpay test card, any future expiry, any
CVV, and a random 4–10 digit OTP:

| Network | Test card number |
|---|---|
| Visa | 4111 1111 1111 1111 |
| Mastercard | 5267 3181 8797 5449 |

**Check what actually got recovered:**

```bash
python check_live_status.py
```

This polls Razorpay's own `/payment_links/:id` endpoint for each link.
`outcome_recovered` is only `True` when Razorpay itself reports
`status == "paid"` — nothing here is inferred or simulated. Results are
written straight back into the same `live_links` table
`create_live_links.py` populated.

**Real-time confirmation instead of polling:** the `/webhook` route in
`api_server.py` (also reachable via `python webhook_server.py`, kept as a
one-line backward-compatible shim) receives Razorpay's
`payment_link.paid` webhook directly, with HMAC-SHA256 signature
verification (constant-time comparison, so timing can't leak the correct
signature) so a spoofed request gets rejected. A confirmed payment flips
the matching row's status to `"paid"` — idempotently (checked via
`rowcount` on the UPDATE), so a retried webhook delivery (Razorpay
resends until it gets a fast 2xx) never double-counts recovered revenue.
Needs a public URL (ngrok works fine for a demo) — full setup steps are
in `api_server.py`'s module docstring.

## Why synthetic data, and how this maps to the real thing

The event schema (`payment_failure`, `checkout_abandonment`,
`overdue_invoice`) mirrors what Razorpay's test-mode Payments, Orders,
and Invoices APIs actually return — `error_code` / `failure_reason` on a
failed payment, `status` on an abandoned order, `due_by` on an overdue
invoice. Swapping `generate_data.py` for a real pull against those
test-mode endpoints, and swapping the reply simulation in
`promise_tracker.py` for a real inbound-message webhook, is a
data-source and I/O change — the diagnose → decide → act logic and the
stopping rules don't need to change at all.

## Project structure

```
db/
  migrations/0001_init.sql   schema — events, event_status, audit_log, commitments, live_links
  connection.py               one shared sqlite3 connection helper (foreign keys on, dict-like rows)
  migrate.py                  applies pending migrations — `python -m db.migrate`
  seed.py                     populates the events table — `python -m db.seed`
  repository.py                every SQL query in the project lives here, all parameterized
generate_data.py      synthetic event generation functions (reused by db/seed.py)
agent.py               diagnose / decide / act + stopping rules (deterministic core)
ai_diagnosis.py         real LLM diagnosis, with the rule table as its fallback
promise_tracker.py      reply simulation + commitment extraction + kept/broken resolution
api_server.py           live API: per-event diagnose/decide/act routes + the webhook route
run_batch.py            offline batch -> database + dashboard_data.js (--ai for real LLM diagnosis)
run_promise_batch.py    promise-to-pay demo -> database + promise_dashboard_data.js
create_live_links.py    creates REAL Razorpay test-mode Payment Links from the same agent logic
check_live_status.py    polls Razorpay for real payment status, writes back to live_links table
webhook_server.py       one-line shim -> api_server.py's app (kept for backward-compatible `python webhook_server.py`)
dashboard.html          static funnel/breakdown overview — works with zero server
shared.css / shared.js  styling + fetch helpers shared by the three live pages below
audit.html              per-event action explorer (needs api_server.py running)
risks.html              root-cause deep dive + largest unresolved events (needs api_server.py running)
recoveries.html         wins only, by channel (needs api_server.py running)
```

## What's next if this goes further

- Wire a real inbound channel (Twilio/WhatsApp Business API webhook) so
  `promise_tracker.py` extracts commitments from actual customer replies
  instead of a simulated reply bank.
- Actually send the nudges: `sms_nudge`/`whatsapp_nudge`/`email_reminder`
  are decision labels today, not real outbound API calls.
- Extend `create_live_links.py` to overdue B2B invoices too, once there's
  a real Invoices API flow to pair it with.
- Multi-merchant support — right now every script assumes a single
  merchant's event batch.
