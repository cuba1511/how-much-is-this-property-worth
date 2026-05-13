# PropHero Landing Page — Property Valuation

## What This Is

A React landing page (`frontend2/`) where users input their property details and get a real-time market valuation. The page captures address (with autocomplete + map), bedrooms, bathrooms, and square meters, then hits the existing FastAPI backend to trigger the Idealista scraper. Built with PropHero's brand tokens on React + Vite + Tailwind + shadcn/ui.

## Core Value

Users can quickly and intuitively submit their property details through a polished, branded form that feels trustworthy and modern.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Hero section with "¿Cuánto vale tu casa?" headline and PropHero branding
- [ ] Address autocomplete input powered by Nominatim API with debounced search
- [ ] Interactive Leaflet map showing pin on selected address (click map to reverse geocode)
- [ ] Stepper component (- NUM +) for number of bedrooms
- [ ] Stepper component (- NUM +) for number of bathrooms
- [ ] Number input for property area in square meters (m²)
- [ ] Form submission calls existing FastAPI backend `/api/valuate`
- [ ] Responsive design (mobile-first, works on all screen sizes)
- [ ] PropHero design tokens (electric blue, cyan, orange CTAs, Inter typography)

### Out of Scope

- Results display (stats, estimate card, comparable listings) — future phase
- User authentication / accounts — not needed for MVP
- Backend modifications — using existing FastAPI endpoints as-is
- Dark mode — not required for v1
- SEO / meta tags optimization — defer to later

## Context

- **Existing backend**: FastAPI at `localhost:8001` with `/api/valuate` endpoint, Nominatim geocoder, Idealista scraper via Bright Data
- **Original frontend**: Vanilla HTML + Tailwind CDN at `frontend/index.html` — serves as reference for UX flow and behavior
- **Frontend2 scaffold**: React 19 + Vite 8 + Tailwind 3.4 + shadcn/ui already set up with PropHero color tokens and design system variables
- **Address picker reference**: Existing vanilla JS implementation with autocomplete, suggestions panel, reverse geocode on map click, and marker management
- **Language**: Spanish (es)

## Constraints

- **Stack**: React + Vite + Tailwind + shadcn/ui (already scaffolded in `frontend2/`)
- **Design system**: Must match PropHero brand — electric blue (#2050f6), cyan (#65c6eb), orange CTA (#f45504), Inter font
- **API**: Nominatim for address autocomplete (free, no key needed), existing backend for valuation
- **Map**: Leaflet for interactive map display
- **Scope**: Form-only landing page — no results rendering in this milestone

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| React + Vite over vanilla HTML | Better component reusability, state management for stepper/autocomplete | — Pending |
| Stepper component (- NUM +) for beds/baths | More tactile UX than dropdown selects, user specified | — Pending |
| Nominatim for address autocomplete | Free, no API key, already used by backend geocoder | — Pending |
| Form-only scope (no results) | Ship form fast, add results display in next phase | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-05-13 after initialization*
