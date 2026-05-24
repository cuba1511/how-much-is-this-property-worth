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
scoped by default to the Spain-only `SP - AUM` view. This is intentionally
faster than filtering the full table by `Country (from Properties)` on every
request. Search still uses `filterByFormula` over the `Transaction Name`
column; because the column follows the `<Client> - <Address>` convention in
production, the same search matches both client name **and** street/city.
Empty `q` returns the most recent `limit` rows (sorted by `Created_Date`
desc) so the UI has something to show on first paint.

Response: `list[TransactionSummary]` (see `backend/models.py`).

### `GET /api/coach/transactions/{record_id}`

Fetch a single transaction by Airtable record id (`recXXXXXXXX`). Returns
`TransactionDetail` which extends `TransactionSummary` with the verbatim
`raw_fields` blob for any column not yet promoted to a typed field.

## Airtable field mapping

| Airtable column                                                                          | API field            |
|------------------------------------------------------------------------------------------|----------------------|
| `Transaction Name`                                                                       | `transaction_name`   |
| `Type`                                                                                   | `type`               |
| `Beds`                                                                                   | `bedrooms`           |
| `Baths`                                                                                  | `bathrooms`          |
| `Landsize`                                                                               | `landsize_m2`        |
| `Created_Date`                                                                           | `created_at`         |
| `Total est. costs (Reno + furniture + technical project costs + Apportionment Amount)`   | `total_est_costs`    |
| `Final Total Price (from Properties)`                                                    | `final_total_price`  |

Lookup fields (like `Final Total Price (from Properties)`) come back as
arrays from Airtable; `backend/airtable/transactions.py` flattens them to a
scalar before returning. The original arrays are preserved under
`raw_fields` so the detail view can show any column we haven't typed yet.

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
- By default the coach valuation endpoint returns an instant mock
  `ValuationResponse` (`strategy=coach_mock`) so coaches can test the investor
  report and email flow without waiting on Bright Data/Idealista. Add
  `?live=true` to run the real scrape.
- The coach result view intentionally does **not** render the public valuation
  dashboard. It renders an investor-facing report: sale range, capital gain,
  ROI, quick/recommended/aspirational exit scenarios, comparables, closing
  references, and a call-to-action for the coach follow-up.

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
