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
| `backend/main.py` | FastAPI app, routes, stats calculation |
| `backend/scraper.py` | Idealista scraper via Bright Data (SERP collection) |
| `backend/listing_detail.py` | Parallel per-listing detail enrichment (bathrooms, features, description) |
| `backend/geocoder.py` | Address → municipio (Nominatim) |
| `backend/models.py` | Pydantic models |
| `frontend/index.html` | Single-page UI |

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
