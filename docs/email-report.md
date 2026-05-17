# Email + PDF Report Flow

Pipeline for capturing a lead, persisting it, generating a branded PDF
valuation report, and sending it by email — all triggered by a single
`POST /api/lead` from the frontend.

## High-level flow

```
frontend                  backend (FastAPI)                  external
────────                  ─────────────────                  ────────
ValuationForm
  │
  ├──► submitLead({...}) ───► POST /api/lead
  │                            │
  │                            ├── db.insert_lead()
  │                            ├── get_valuation()  ── Idealista (Bright Data CDP)
  │                            ├── db.insert_valuation()
  │                            └── BackgroundTask:
  │                                  ├── render_report_html()
  │                                  ├── generate_pdf_bytes()  ── Playwright local
  │                                  ├── send_valuation_email() ─ Resend API
  │                                  └── db.mark_email_sent()
  │
  ◄── LeadResponse (lead_id, valuation_id, valuation, email_scheduled)
  │
ConversionSignalsBlock
  ✓ "Te enviamos el reporte a {email}"
  [Descargar PDF]   ── POST /api/report/pdf ─► same PDF, no email
```

Why two endpoints:

- **`POST /api/lead`** — the production submission flow. Captures the lead,
  persists it, runs the valuation, schedules the email + PDF send as a
  `BackgroundTask`, and returns the valuation payload synchronously. The
  user sees results in ~5–15s without waiting on email delivery.
- **`POST /api/report/pdf`** — pure render. Re-uses the same template +
  generator but doesn't persist anything or send email. Used by the
  "Descargar PDF" button on the results page (and useful for QA / preview).

## Modules

| File                                            | Role                                                                     |
|-------------------------------------------------|--------------------------------------------------------------------------|
| `backend/db.py`                                 | SQLite persistence (`leads`, `valuations` tables). WAL mode.             |
| `backend/report/template.html`                  | Jinja2 template with embedded CSS, A4 page setup, PropHero branding.     |
| `backend/report/renderer.py`                    | `render_report_html(valuation, request_payload, lead?)` — pure function. |
| `backend/report/pdf.py`                         | `generate_pdf_bytes(html)` via Playwright local Chromium.                |
| `backend/notifications/email_sender.py`         | `send_valuation_email(lead, valuation, pdf_bytes)` via Resend REST.      |
| `backend/main.py`                               | Wires it all together in `/api/lead` + `/api/report/pdf`.                |

## Configuration

All knobs live in environment variables (see `.env.example`):

```bash
# Resend — required for actual email delivery
RESEND_API_KEY=re_xxxxxxxxxxxxxxxxx
RESEND_FROM_EMAIL="PropHero <noreply@prophero.com>"

# SQLite location (defaults to backend/data/leads.db)
HV_DB_PATH=/absolute/path/to/leads.db

# Optional API key gate (not yet enforced; placeholder for future)
HV_API_KEY=...
```

**If `RESEND_API_KEY` is unset**, `send_valuation_email` logs a warning and
returns without sending. The lead and valuation are still persisted and the
HTTP response is still 200 — useful in dev where we don't want to spam test
inboxes. The `email_scheduled` field in `LeadResponse` reflects this.

## Resend setup (one-time)

1. Sign up at [resend.com](https://resend.com) (free tier covers MVP).
2. Add a domain in the Resend console and add the DNS records they show you
   (DKIM + SPF). Wait for verification (usually <10 min).
3. Create an API key with `emails.send` scope and put it in `.env`.
4. Set `RESEND_FROM_EMAIL` to a `Name <addr@your-domain.com>` value that
   matches the verified domain.

Note: with an unverified domain you can only send to your own login email —
fine for smoke tests, useless for production.

## Playwright dependency

The PDF generator launches a **local** Chromium, not the Bright Data CDP
endpoint the scraper uses (that's a paid scraping resource we shouldn't
burn on internal rendering). `make install` runs `playwright install
chromium` so this Just Works after `git clone`.

The browser is launched + closed per request. For higher throughput later
we can swap to a long-lived `BrowserContext` pool, but at lead-submission
volume (1–10/min) per-request launch is fine and avoids stale-state bugs.

## Background task vs. inline send

We push the PDF + email pipeline into a `BackgroundTask` rather than running
it inline because:

1. Playwright + Resend together add 3–8s on top of the 5–15s valuation,
   which is a bad UX (user stares at a spinner after they already saw their
   number).
2. If Resend is having a bad day, we don't want to fail the whole lead
   submission. The lead is already in SQLite and the user has their result
   on screen.
3. Failures in the background task are caught and persisted in
   `valuations.email_error` so we can investigate without alerting.

The trade-off: if the server crashes between the response and the
background task running, the email is lost. For an MVP this is acceptable —
the lead is still recoverable from SQLite, and we can add a backfill job
later that re-sends emails for rows where `email_sent_at IS NULL AND
email_error IS NULL`.

## Schema

`leads`:

```sql
CREATE TABLE leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL,
    phone TEXT NOT NULL,
    created_at TEXT NOT NULL  -- ISO 8601 UTC
);
```

`valuations`:

```sql
CREATE TABLE valuations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER NOT NULL REFERENCES leads(id),
    address TEXT NOT NULL,
    municipio TEXT,
    estimated_eur INTEGER,
    request_payload TEXT NOT NULL,   -- JSON
    response_payload TEXT NOT NULL,  -- JSON
    email_sent_at TEXT,
    email_error TEXT,
    created_at TEXT NOT NULL
);
```

Both tables are designed to be append-only. We never update a lead's
contact info — if they re-submit with different data, that's a new row.
This keeps audit trails honest and avoids race conditions.

## What this stack intentionally does NOT include

- **HTML email tracking pixels.** Resend has opens/clicks reporting; we use
  it but don't put anything in the email template that the user has to
  consent to beyond standard email tracking.
- **Retry queue.** If Resend is down, the email_error column captures the
  failure and we move on. No exponential backoff. Add this if email
  becomes business-critical.
- **CRM sync.** Leads stay in SQLite. Surface them via a simple admin
  endpoint or sync to Pipedrive/HubSpot when the volume justifies it.

## Testing locally

```bash
# 1. install + chromium + npm + cp .env (one-time)
make install

# 2. create the SQLite file (idempotent — safe to re-run)
make db

# 3. start backend + frontend together
make dev
# Or backend only:
#   make backend

# 4. hit the endpoint
curl -X POST http://localhost:8001/api/lead \
  -H 'Content-Type: application/json' \
  -d '{
    "lead": {
      "full_name": "Test User",
      "email": "you@example.com",
      "phone": "+34611222333"
    },
    "valuation_request": {
      "address": "Calle Granada 24, Madrid",
      "m2": 95,
      "bedrooms": 3,
      "bathrooms": 2
    }
  }'
```

Inspect the SQLite DB with `sqlite3 backend/data/leads.db`:

```sql
.mode column
SELECT id, full_name, email, created_at FROM leads;
SELECT id, lead_id, address, estimated_eur, email_sent_at, email_error FROM valuations;
```
