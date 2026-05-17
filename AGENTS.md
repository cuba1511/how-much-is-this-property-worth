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

## Layout
```
backend/
├── main.py              FastAPI app, routes, OLS-vs-baseline arbitration, honest CI
├── models.py            Pydantic models (cross-cutting types — incl. LeadInfo, LeadResponse)
├── db.py                SQLite persistence (leads + valuations, WAL mode)
├── data/                Runtime DB file (gitignored)
│
├── scraping/            Idealista data collection (Bright Data CDP + Playwright)
│   ├── scraper.py       SERP scraper
│   └── listing_detail.py  Per-listing detail enrichment (bathrooms, features, description)
│
├── valuation/           Pure business logic — no I/O
│   ├── regression.py    OLS with intercept (numpy lstsq) + predict_from_regression()
│   └── market_transactions.py  Mock layer for closing-price / negotiation signals
│
├── geocoding/
│   └── geocoder.py      Address → municipio (Nominatim/OSM)
│
├── notifications/
│   └── email_sender.py  Resend transactional email + branded HTML body
│
└── report/              Branded PDF generation
    ├── template.html    Jinja2 template (PropHero brand tokens, A4)
    ├── renderer.py      ValuationResponse → HTML
    └── pdf.py           HTML → PDF via local Playwright Chromium

frontend2/               React + Vite + Tailwind UI (production)
frontend/                Legacy vanilla HTML — kept for reference
tests/evaluation/        Calibration harness against appraiser ground-truth
```

## Documentation
- [`docs/email-report.md`](docs/email-report.md) — lead + PDF + email pipeline (`/api/lead`, `/api/report/pdf`)
- [`docs/market-transactions.md`](docs/market-transactions.md) — transactions data layer
- [`docs/apps-script.md`](docs/apps-script.md) — Apps Script integration
- [`tests/evaluation/README.md`](tests/evaluation/README.md) — calibration harness against ground-truth appraiser CSV

## Running locally
```bash
make install      # python venv + pip deps + chromium + npm + cp .env.example
make db           # create backend/data/prophero.db
make dev          # API on :8001 + Vite dev server on :5173
```
Other targets: `make backend`, `make frontend`, `make clean`, `make help`.

## Bright Data
- Zone: `idealista` (already configured for Idealista anti-bot bypass)
- Protocol: CDP over WebSocket (port 9222)
- CAPTCHAs are auto-solved by BRD's SBR service

## Roadmap
- [ ] Phase 2: Market transactions data (TF Labs)
- [ ] Phase 3: Internal PropHero transactions
- [ ] Phase 4: Calculations Agent + Report Generation Agent
