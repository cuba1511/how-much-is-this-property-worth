# Apps Script Integration

Use the House Valuation backend as a custom Google Sheets function. Inputs are
**address, bedrooms, bathrooms, m²**; outputs are **price, asking_price,
closing_price, negotiation_factor**.

> **Heads-up — partial mock**: today only `price` is computed from real
> Idealista comparables. `asking_price`, `closing_price`, and
> `negotiation_factor` come from the mocked market-transactions layer (see
> [`market-transactions.md`](./market-transactions.md)). The response includes
> `is_mock: true` while this is the case. The contract will not change when
> real data replaces the mock.

## API contract

`POST /api/valuation/simple`

Request:

```json
{
  "address": "Calle Mayor 12, Madrid",
  "bedrooms": 3,
  "bathrooms": 2,
  "m2": 95
}
```

Response:

```json
{
  "address": "Calle Mayor",
  "price": 412000,
  "asking_price": 425000,
  "closing_price": 398000,
  "negotiation_factor": 0.063,
  "comparables_used": 18,
  "is_mock": true
}
```

`negotiation_factor` is a **decimal** equal to `(asking - closing) / asking`,
so `0.063` means buyers are negotiating a 6.3% discount off asking.

## Auth

If the env var `HV_API_KEY` is set on the backend, callers must send header
`X-API-Key: <value>`. If unset, the endpoint is open (fine for local dev).

Generate a key:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Then set it in `backend/.env` and (later) in the Apps Script script
properties.

## Step 1 — Expose the local backend with ngrok

```bash
# Terminal A — backend
cd backend
python main.py
# → http://localhost:8001

# Terminal B — public tunnel
ngrok http 8001
# → forwards https://xxxx-xx-xx-xx.ngrok-free.app → localhost:8001
```

Sanity check from your laptop:

```bash
curl -s -X POST https://xxxx.ngrok-free.app/api/valuation/simple \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $HV_API_KEY" \
  -d '{"address":"Calle Mayor 12, Madrid","bedrooms":3,"bathrooms":2,"m2":95}' | jq
```

> ngrok URLs change every time you restart the tunnel (on the free tier).
> When you move to Cloud Run / Render the URL becomes stable.

## Step 2 — Install the Apps Script function

1. Open your Google Sheet → **Extensions → Apps Script**.
2. Replace `Code.gs` with the contents of
   [`apps-script/valuation.gs`](../apps-script/valuation.gs).
3. **Project Settings** (gear icon) → **Script properties** → **Add script
   property** twice:

   | Property            | Value                                              |
   |---------------------|----------------------------------------------------|
   | `HV_API_BASE_URL`   | `https://xxxx.ngrok-free.app` (no trailing slash) |
   | `HV_API_KEY`        | Same value as `HV_API_KEY` in `backend/.env`      |

4. **Save**. Reload the Sheet tab so the custom function is picked up.

## Step 3 — Use it in a cell

```text
=VALORAR_CASA("Calle Mayor 12, Madrid", 3, 2, 95)
```

Spills into 4 columns:

| price   | asking_price | closing_price | negotiation_factor |
|---------|--------------|---------------|--------------------|
| 412000  | 425000       | 398000        | 0.063              |

For a single-cell variant returning only the price:

```text
=HV_PRICE("Calle Mayor 12, Madrid", 3, 2, 95)
```

## Caching & rate limits

- Apps Script caches each `(address, beds, baths, m2)` result for 24h via
  `CacheService` to avoid burning Bright Data quota when you drag-fill a
  column. Edit `HV_CACHE_TTL_SECONDS` in `valuation.gs` to change.
- Apps Script custom-function calls have a **30-second** hard timeout and the
  whole script execution caps at **6 minutes**. The valuation typically takes
  4–10s, so dragging across more than ~30 rows in one go can hit the cap —
  fill in batches if you need many rows at once.
- All calls share one Bright Data Scraping Browser session; expect serialized
  scraping, not parallel.

## Going from ngrok to production

When you outgrow ngrok:

- **Google Cloud Run** — best fit since you’re already in the Google
  ecosystem. Requires a Dockerfile that installs Playwright + Chromium
  (~1GB image). Set `HV_API_KEY` and `BRIGHT_DATA_CDP` as env vars in the
  service. Update only `HV_API_BASE_URL` in Apps Script — no code change.
- **Render / Railway / Fly.io** — simpler deploy from GitHub, ~$5–7/mo.

The Apps Script side does not change.
