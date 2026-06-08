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

### `GET /api/coach/transactions?q=<text>&limit=<n>&offset=<token>`

Server-side substring search against the Airtable `Transactions` table,
scoped to Spain and `Stage = "Property leased"` so coaches only see leased
Spanish transactions ready for the investor report. The query still uses
`filterByFormula` over the `Transaction Name` column; because the column
follows the `<Client> - <Address>` convention in production, the same search
matches both client name **and** street/city. Empty `q` returns the oldest
matching `limit` rows (sorted by `Created_Date` asc) so the first-paint
worklist starts with the oldest leased properties. The frontend requests
`limit=100`, which is also the backend maximum for now. Airtable pagination is
cursor-based: the response includes `next_offset`, and the frontend passes it
back as `offset` to load the next tab/page of transactions.

Response: `TransactionSearchResponse` (see `backend/models.py`):

```json
{
  "records": ["TransactionSummary"],
  "next_offset": "itr...",
  "page_size": 100,
  "has_more": true
}
```

Each list row is enriched before returning to the browser:
- `coach_id`, `coach_name`, `coach_email` are resolved from the Airtable
  `Coach` lookup via the `Team Profiles` table.
- `account_manager_id`, `account_manager_name` are resolved the same way.
- `appreciation_pct`, `appreciation_from_period`, `appreciation_to_period`,
  `appreciation_town_name`, `estimated_current_value`, and `capital_gain` are
  pre-computed from the TF Labs municipal price series. This uses the direct
  `Town` Airtable record id when available, otherwise a best-effort municipality
  guess from the transaction address. It does **not** geocode and does **not**
  scrape Idealista, so the list can rank/filter rows quickly.
- `estimated_current_value` uses the same no-scrape anchor as the PDF report:
  latest municipal €/m² × property surface. `capital_gain` is the same TF Labs
  zone appreciation percentage shown in `appreciation_pct`, converted to points
  for display and sorting.
- `purchase_eur_per_m2` is computed as `final_total_price / landsize_m2`.
  This is the actual initial acquisition €/m² paid by the client; the TF Labs
  `from_eur_per_m2` remains the municipal zone median at the settlement period.

### `GET /api/coach/transactions/{record_id}`

Fetch a single transaction by Airtable record id (`recXXXXXXXX`). Returns
`TransactionDetail` which extends `TransactionSummary` with the verbatim
`raw_fields` blob for any column not yet promoted to a typed field.

### `POST /api/coach/transactions/{record_id}/email/send`

Sends the coach-authored client email via Resend. The frontend submits the
edited message plus the already-computed `ValuationResponse` snapshot; the
backend re-fetches the Airtable record, renders the same client PDF used by
the preview, attaches it as `prophero-valoracion-<record_id>.pdf`, then sends
the email to the client address. The request can set `test_mode=true`; in that
case Resend delivers to `RESEND_TEST_EMAIL_TO` while keeping the client email as
metadata in the response. If `RESEND_API_KEY` is unset, the route returns
`sent=false` so the UI can exercise the flow locally without delivering mail.

### `POST /api/coach/transactions/{record_id}/email/auto-preview`

Prepares the default bulk-send draft without delivering anything:

```
Airtable transaction
 └─► ValuationRequest
 └─► no-scrape valuation (TF Labs €/m² series)
 └─► market appreciation enrichment
 └─► default coach email body
```

The frontend uses this endpoint before bulk delivery so the coach can review
the subject, body, headline numbers, and generated PDF. Drafts with missing
client email, negative capital gain, or non-positive municipal appreciation
return `review_warning` and should be manually checked before sending.

### `POST /api/coach/transactions/{record_id}/email/auto-send`

Legacy one-click pipeline that generates and sends the default email in a
single request. The current bulk UI avoids this direct path and instead calls
`auto-preview`, lets the coach review/edit the draft, then sends through
`POST /api/coach/transactions/{record_id}/email/send` with the reviewed
payload.

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
| `PM selected plan`                                                                       | `pm_selected_plan`   |
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
| computed from `Final total price / Landsize`                                             | `purchase_eur_per_m2` |
| `Real settlement date`                                                                   | `real_settlement_date` |
| `Town` / `Town (from Properties)`                                                        | `town_record_id`     |
| `Coach`                                                                                  | `coach_id` → `coach_name` / `coach_email` |
| `Account Manager`                                                                        | `account_manager_id` → `account_manager_name` |

`final_total_price` is treated as the amount the client paid. `purchase_eur_per_m2`
is the derived purchase basis (`final_total_price / landsize_m2`) shown as the
actual €/m² at acquisition. The individual cost columns are exposed for
explanation and auditability, but the coach report does not add them again on
top of `final_total_price`.

`real_settlement_date` and `town_record_id` feed the new market-appreciation
block in the coach investor report — see [`market-price-series.md`](market-price-series.md)
for the full pipeline. Both are optional: when either is missing the
appreciation card simply doesn't render and the report falls back to the
comparables-only narrative.

The list-level appreciation fields are precomputed for worklist triage only.
`capital_gain` is `appreciation_pct * 100`, so the list shows the TF Labs zone
revaluation percentage directly. `estimated_current_value` remains available as
latest municipal €/m² multiplied by `landsize_m2` and rounded to the nearest EUR
1,000. The detail report still recomputes the full payload when the coach opens
a transaction.

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
AIRTABLE_TEAM_PROFILES_TABLE=Team Profiles   # Optional override for coach owner lookup
COACH_ACCESS_PASSWORD=<shared-secret>        # Empty = gate disabled (dev only)
RESEND_API_KEY=re_...                        # Required for real coach email delivery
RESEND_FROM_EMAIL=PropHero <noreply@...>     # Must match a verified Resend domain
RESEND_REPLY_TO=reply@resend-inbound.example # Optional reply inbox for client responses
RESEND_TEST_EMAIL_MODE=true                  # Optional global force-test mode
RESEND_TEST_EMAIL_TO=ignacio.delacuba@prophero.com
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
- The `/coach` transaction list surfaces precomputed revaluation data:
  - sort by capital gain, appreciation, estimated value, or date
  - filter by minimum capital gain
  - filter by coach owner
  - filter by `PM selected plan`, including a shortcut for all rows except `Out of PH`
  - export the current filtered client list, or the selected rows, as a CSV that can be opened in Google Sheets
  - multi-select visible rows (max 25) for bulk send
- The list loads transactions in Airtable pages of 100. Loaded pages are exposed
  through a compact paginator (`Anterior`, `Siguiente`, and page chips). The
  paginator also shows loaded-total metrics: total loaded, positive-gain count,
  aggregate capital gain, average capital gain, and average appreciation.
- The `/coach` header includes a global `Dev mode ON/OFF` button, enabled by
  default from `RESEND_TEST_EMAIL_MODE`, that routes every Resend delivery to
  the configured dev/test inbox before sending to real clients.
- Bulk send opens a progress dialog and sends the default no-scrape report in
  parallel with concurrency 3. It follows the global Dev mode state.
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
  recommended range, active comparables when enabled, actual purchase €/m²
  (`final_total_price / landsize_m2`) as the first point in the €/m² evolution
  chart, followed by the TF Labs municipal median points for the later periods,
  and a call-to-action for the coach follow-up. It does not estimate
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
