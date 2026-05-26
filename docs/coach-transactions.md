# Coach transactions (Airtable proxy)

Internal interface for PropHero property coaches to search client
transactions stored in Airtable. Lives at **`/coach`** in the frontend and
is gated by a single shared password so the Airtable Personal Access Token
(PAT) never reaches the browser bundle.

## Architecture

```
Browser (/coach)
 └─► React (CoachPage.tsx)
        ├─► CoachLogin → POST password (X-Coach-Password) probe
        ├─► TransactionSearchPanel → GET /api/coach/transactions?q=…
        └─► TransactionDetailPanel → GET /api/coach/transactions/{id}
                                          │
                              FastAPI (main.py)
                                          │
                            backend/airtable/* (HTTPX)
                                          │
                            api.airtable.com/v0/<base>/transactions
```

Why a backend proxy:
- PAT stays in `backend/.env` (server-side env vars only).
- We can swap the search formula or add caching without touching the frontend.
- CORS/headers stay consistent with the rest of `/api/*`.

## Endpoints

All `/api/coach/*` routes accept a `X-Coach-Password` header and 401 when it
doesn't match `COACH_ACCESS_PASSWORD`. If the env var is unset the gate is
disabled (useful in local dev).

### `GET /api/coach/transactions?q=<text>&limit=<n>`

Server-side substring search against the Airtable `Transactions` table,
scoped to Spain and `Stage = "Property leased"` so coaches only see leased
Spanish transactions ready for the investor report. The query still uses
`filterByFormula` over the `Transaction Name` column; because the column
follows the `<Client> - <Address>` convention in production, the same search
matches both client name **and** street/city. Empty `q` returns the oldest
matching `limit` rows (sorted by `Created_Date` asc) so the first-paint
worklist starts with the oldest leased properties.

Response: `list[TransactionSummary]` (see `backend/models.py`).

### `GET /api/coach/transactions/{record_id}`

Fetch a single transaction by Airtable record id (`recXXXXXXXX`). Returns
`TransactionDetail` which extends `TransactionSummary` with the verbatim
`raw_fields` blob for any column not yet promoted to a typed field.

### `POST /api/coach/transactions/{record_id}/email/send`

Sends the coach-authored client email via Resend. The frontend submits the
edited message plus the already-computed `ValuationResponse` snapshot; the
backend re-fetches the Airtable record, renders the same client PDF used by
the preview, attaches it as `prophero-valoracion-<record_id>.pdf`, then sends
the email. If `RESEND_TEST_TO` is set, delivery is temporarily routed to that
test inbox instead of the client address. If `RESEND_API_KEY` is unset, the
route returns `sent=false` so the UI can exercise the flow locally without
delivering mail.

## Airtable field mapping

| Airtable column                                                                          | API field            |
|------------------------------------------------------------------------------------------|----------------------|
| `Transaction Name`                                                                       | `transaction_name`   |
| `Type`                                                                                   | `type`               |
| `Beds`                                                                                   | `bedrooms`           |
| `Baths`                                                                                  | `bathrooms`          |
| `Landsize`                                                                               | `landsize_m2`        |
| `Created_Date`                                                                           | `created_at`         |
| `Country (from Properties)`                                                              | filter only (`Spain`) |
| `Stage`                                                                                  | filter only (`Property leased`) |
| `Price`                                                                                  | `price`              |
| `Final reno cost`                                                                        | `final_reno_cost`    |
| `Final furniture cost`                                                                   | `final_furniture_cost` |
| `Technical project cost(s)`                                                              | `technical_project_costs` |
| `Home appliances cost`                                                                   | `home_appliances_cost` |
| `Cleaning cost`                                                                          | `cleaning_cost`      |
| `Real estate agent fee`                                                                  | `real_estate_agent_fee` |
| `Land registry cost`                                                                     | `land_registry_cost` |
| `PropHero fee`                                                                           | `prophero_fee`       |
| `Notary cost`                                                                            | `notary_cost`        |
| `Insurance`                                                                              | `insurance`          |
| `Council rate`                                                                           | `council_rate`       |
| `Service charges`                                                                        | `service_charges`    |
| `Final total price`                                                                      | `final_total_price`  |
| `Real settlement date`                                                                   | `real_settlement_date` |
| `Town` / `Town (from Properties)`                                                        | `town_record_id`     |

`final_total_price` is treated as the amount the client paid. The individual
cost columns are exposed for explanation and auditability, but the coach report
does not add them again on top of `final_total_price`.

`real_settlement_date` and `town_record_id` feed the new market-appreciation
block in the coach investor report — see [`market-price-series.md`](market-price-series.md)
for the full pipeline. Both are optional: when either is missing the
appreciation card simply doesn't render and the report falls back to the
comparables-only narrative.

Lookup fields may come back as arrays from Airtable;
`backend/airtable/transactions.py` flattens them to a scalar before returning.
The search proxy intentionally does not pass a strict `fields[]` projection for
the financial fields, because Airtable returns 422 when any optional column name
differs by singular/plural or lookup suffix. The original fields are preserved
under `raw_fields` so the detail view can show any column we haven't typed yet.

If columns get renamed in Airtable, patch the `FIELD_*` constants at the top
of `backend/airtable/transactions.py` — that's the only place you need to
touch.

## Environment variables (`backend/.env`)

```env
# Required
AIRTABLE_PAT=pat...                          # PAT with data.records:read on the base
AIRTABLE_BASE_ID=app...                      # Base id (appears in airtable.com/<base>/api docs)

# Optional
AIRTABLE_TRANSACTIONS_TABLE=Transactions     # Override if the table is renamed
AIRTABLE_TRANSACTIONS_VIEW=SP - AUM          # Spain-only view; empty = formula fallback
COACH_ACCESS_PASSWORD=<shared-secret>        # Empty = gate disabled (dev only)
RESEND_API_KEY=re_...                        # Required for real coach email delivery
RESEND_FROM_EMAIL=PropHero <noreply@...>     # Must match a verified Resend domain
RESEND_TEST_TO=salchiwolf@gmail.com          # Optional test override; unset for real clients
```

Generate a PAT at <https://airtable.com/create/tokens> with scope
`data.records:read` limited to the base that holds the transactions table.

## Frontend

- Routes live in `frontend/src/main.tsx` (BrowserRouter):
  - `/` → existing public valuation flow (`App.tsx`)
  - `/coach` and `/coach/:transactionId` → `pages/CoachPage.tsx`
- The coach password is cached in `localStorage` under
  `prophero.coach.password` and attached to every request as
  `X-Coach-Password`.
- The "Generate valuation" button on the detail view calls
  `POST /api/coach/transactions/{id}/valuation`. The backend adapts the
  Airtable row into the existing `ValuationRequest`: it prefers Catastro
  resolution when a cadastral reference exists and otherwise strips
  floor/door suffixes from the Airtable address before geocoding.
- Report generation intentionally re-fetches the Airtable record with a
  projected `fields[]` list instead of loading the full `raw_fields` payload.
  Full records can include heavy lookup blobs and have produced Airtable 504s;
  the projected path only requests the fields needed for valuation, purchase
  economics, and market appreciation. Unknown optional aliases are dropped
  when Airtable returns a 422 for renamed columns.
- By default the coach valuation endpoint runs the live Bright Data/Idealista
  scrape so the investor report shows real active comparables. Add
  `?live=false` to return the instant mock `ValuationResponse`
  (`strategy=coach_mock`) when coaches need to test the investor report and
  email flow without waiting on the scraper.
- Add `?include_comparables=false` to skip Idealista scraping entirely and
  build the response from the TF Labs municipal €/m² series only
  (`strategy=no_scrape`, `estimation_method=market_series`). Returns in <2s
  with a real-data headline anchor, empty `listings`, no `regression`, and
  triggers the methodology copy that explicitly attributes the figure to
  TF Labs. This is the variant surfaced as the "Sin comparables" toggle on
  the CoachPage **Generar reporte** card.
- The coach result view intentionally does **not** render the public valuation
  dashboard. It renders an investor-facing report: a single conservative
  recommended sale range, **plusvalía de zona** (real TF Labs €/m² appreciation
  since the `Real settlement date`), gain/ROI versus purchase at that
  recommended range, active comparables when enabled, purchase €/m² vs today's
  zone €/m², and a call-to-action for the coach follow-up. It does not estimate
  time-to-sale, because that depends on demand, asset condition, documentation,
  tax position, and negotiation. The mocked "real closings" panel was removed in
  favour of the appreciation block — see
  [`market-price-series.md`](market-price-series.md).

## Local dev

```bash
# 1) Backend
cd backend
echo "AIRTABLE_PAT=pat..." >> .env
echo "AIRTABLE_BASE_ID=app..." >> .env
echo "COACH_ACCESS_PASSWORD=letmein" >> .env   # optional in dev
python main.py

# 2) Frontend
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173/coach`, enter the password, and start searching.

## Next steps (out of MVP scope)

- Persist the resulting valuation alongside the Airtable record id (so a
  coach can re-open a transaction and see the last valuation we produced).
- Replace the shared password with proper user auth once we have more than
  a handful of coaches.
