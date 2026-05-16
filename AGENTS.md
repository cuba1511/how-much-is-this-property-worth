# House Valuation — Agent Context

## What this project does
AI-powered house valuation tool. Users input property details and receive real-time comparable listings from Idealista plus a price estimate.

## Architecture (MVP)
```
Input (address, m2, beds, baths)
 └─► Geocoder (Nominatim OSM) → municipio metadata
 └─► Idealista Scraper
 ├─► Open idealista.com
 ├─► Search using the real address
 ├─► Apply comparable filters (m2 / beds / baths)
 ├─► Extract SERP listings (no bathrooms / amenities here)
 └─► Detail enrichment (parallel): open each top-N listing detail page
 to fill bathrooms + features (pool, terrace, garden, AC, condition)
 + full description, with merge-non-destructive into the SERP listing
 └─► Stats calculator → estimated value
 └─► Linear regression (OLS with intercept) on [m², habitaciones, baños]
     → per-feature contribution + personalized prediction
 └─► FastAPI response → HTML frontend
```

## Stack
- **Backend**: FastAPI + Python 3.11+
- **Scraping**: Playwright (async) connected to Bright Data Scraping Browser via CDP
- **Geocoding**: Nominatim (OpenStreetMap) — no API key needed
- **Frontend**: Vanilla HTML + Tailwind CSS (CDN)

## Key files
| File | Purpose |
|------|---------|
| `backend/main.py` | FastAPI app, routes, stats calculation, OLS-vs-baseline arbitration, honest CI |
| `backend/scraper.py` | Idealista scraper via Bright Data (SERP collection) |
| `backend/listing_detail.py` | Parallel per-listing detail enrichment (bathrooms, features, description) |
| `backend/regression.py` | OLS regression with intercept (numpy lstsq) on [m², habitaciones, baños] + `predict_from_regression()` |
| `backend/geocoder.py` | Address → municipio (Nominatim) |
| `backend/db.py` | SQLite persistence for leads + valuations (WAL mode) |
| `backend/report/template.html` | Jinja2 PDF template (PropHero brand) |
| `backend/report/renderer.py` | Render `ValuationResponse` → HTML for PDF |
| `backend/report/pdf.py` | HTML → PDF via local Playwright Chromium |
| `backend/email_sender.py` | Resend transactional email + branded HTML body |
| `backend/models.py` | Pydantic models (incl. `LeadInfo`, `LeadSubmission`, `LeadResponse`) |
| `frontend2/` | React + Vite + Tailwind UI (production) |
| `frontend/index.html` | Legacy single-page UI |

## Documentation
- [`docs/email-report.md`](docs/email-report.md) — lead + PDF + email pipeline (`/api/lead`, `/api/report/pdf`)
- [`docs/market-transactions.md`](docs/market-transactions.md) — transactions data layer
- [`docs/apps-script.md`](docs/apps-script.md) — Apps Script integration
- [`tests/evaluation/README.md`](tests/evaluation/README.md) — calibration harness against ground-truth appraiser CSV

## Running locally
```bash
cd backend
pip install -r requirements.txt
playwright install chromium
cp ../.env.example .env
python main.py
# → http://localhost:8001
```

## Bright Data
- Zone: `idealista` (already configured for Idealista anti-bot bypass)
- Protocol: CDP over WebSocket (port 9222)
- CAPTCHAs are auto-solved by BRD's SBR service

## Roadmap
- [ ] Phase 2: Market transactions data (TF Labs)
- [ ] Phase 3: Internal PropHero transactions
- [ ] Phase 4: Calculations Agent + Report Generation Agent
