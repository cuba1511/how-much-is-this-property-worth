# Technology Stack

**Project:** PropHero Property Valuation Landing Page
**Researched:** 2026-05-13
**Overall confidence:** HIGH

## Recommended Stack

### Core Framework (already scaffolded)

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| React | ^19.2.6 | UI framework | Already scaffolded. React 19 is stable, wide ecosystem, team familiarity | HIGH |
| Vite | ^8.0.12 | Build tool | Already scaffolded. Sub-second HMR, native ESM, fastest DX in class | HIGH |
| TypeScript | ^6.0.3 | Type safety | Already scaffolded. Catches bugs at compile time, IDE autocomplete | HIGH |
| Tailwind CSS | ^3.4.17 | Utility-first CSS | Already scaffolded. PropHero design tokens configured, shadcn/ui dependency | HIGH |
| shadcn/ui | ^4.7.0 | Component library | Already scaffolded. Copy-paste components, full control, Radix primitives underneath | HIGH |

### Form Handling (to add)

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| react-hook-form | ^7.75.0 | Form state management | Official shadcn/ui form integration. Uncontrolled inputs = minimal re-renders. 48M weekly downloads, zero deps | HIGH |
| zod | ^4.4.3 | Schema validation | shadcn/ui's recommended validator. Single schema drives TypeScript types + runtime validation. Shares shape with backend Pydantic models | HIGH |
| @hookform/resolvers | ^5.2.2 | Bridge RHF ↔ Zod | Officially maintained resolver, v5.2.2 includes Zod 4 output type fix | HIGH |

**Rationale:** shadcn/ui's `<Form>` component is built on react-hook-form + zod. Using anything else (Formik, Yup) means fighting the component library. The ValuationRequest schema (address, m2, bedrooms, bathrooms) maps 1:1 to a Zod schema that mirrors the backend Pydantic model.

### Map & Geocoding (to add)

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| leaflet | ^1.9.4 | Map rendering engine | Stable, 40K+ GitHub stars, free/open-source. The backend already uses Nominatim (OSM), so Leaflet + OSM tiles is the natural pairing | HIGH |
| react-leaflet | ^5.0.0 | React bindings for Leaflet | v5 requires React 19 (which we have). Declarative `<MapContainer>`, `<TileLayer>`, `<Marker>` components. 2.7M weekly downloads | HIGH |
| @types/leaflet | ^1.9.21 | TypeScript definitions | Required for TS — Leaflet itself ships no types | HIGH |

**Rationale:** Leaflet is the only serious open-source option that pairs with OSM/Nominatim without API keys or billing. Mapbox GL JS and Google Maps require paid API keys and don't align with the existing Nominatim geocoding backend. The backend already has `/api/addresses/autocomplete` and `/api/addresses/reverse` endpoints using Nominatim — the frontend just needs to consume them.

### Supporting Libraries (to add)

| Library | Version | Purpose | Why | Confidence |
|---------|---------|---------|-----|------------|
| use-debounce | ^10.1.1 | Debounce autocomplete input | <1KB, zero deps, provides `useDebouncedCallback` for throttling Nominatim requests to respect the 1 req/s rate limit | HIGH |
| sonner | ^2.0.7 | Toast notifications | shadcn/ui's recommended toast library. Zero deps, 42M weekly downloads. For error states ("address not found", "valuation failed") | MEDIUM |
| lucide-react | ^1.14.0 | Icons | Already installed. shadcn/ui's default icon library | HIGH |

### Already Installed (no action needed)

| Library | Version | Purpose |
|---------|---------|---------|
| @radix-ui/react-slot | ^1.2.4 | Primitive composition (shadcn/ui dependency) |
| @radix-ui/react-tabs | ^1.1.13 | Tab primitives |
| class-variance-authority | ^0.7.1 | Component variant management |
| clsx | ^2.1.1 | Conditional classnames |
| tailwind-merge | ^3.6.0 | Merge Tailwind classes without conflicts |
| tailwindcss-animate | ^1.0.7 | Animation utilities |

## Address Autocomplete Strategy

**Decision:** Build a custom autocomplete component using shadcn/ui primitives + the existing backend endpoint. Do NOT use a third-party OSM autocomplete library.

**Why:**
1. The backend already exposes `GET /api/addresses/autocomplete?q=...&limit=5` returning `ResolvedAddress[]` — the API contract is settled
2. Third-party React-Nominatim libraries (react-osm-geocoding, osm-autocomplete) are low-download, poorly maintained, and would bypass the backend's geocoding layer
3. A shadcn/ui Combobox (Radix Popover + Command) with `use-debounce` gives full design control and matches PropHero branding
4. Nominatim enforces 1 request/second — debounce at 350ms + the backend's own throttling handles this

**Implementation pattern:**
```
Input onChange → useDebouncedCallback(350ms) → fetch /api/addresses/autocomplete?q=...
                                              → populate Combobox dropdown
                                              → on select → set form value + update map marker
```

## Stepper Controls Strategy

**Decision:** Build custom `<Stepper>` components using shadcn/ui `<Button>` + react-hook-form's `Controller`. No library needed.

**Why:** Stepper controls (bedrooms: 1-10, bathrooms: 1-5, m²: 20-500) are trivial UI: two buttons (−/+) flanking a number display. Adding a library for this is over-engineering. react-hook-form's `Controller` wraps the value/onChange contract.

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Map library | Leaflet + react-leaflet | Mapbox GL JS | Requires paid API key above free tier, doesn't match Nominatim/OSM backend |
| Map library | Leaflet + react-leaflet | Google Maps (@vis.gl/react-google-maps) | Requires billing-enabled API key, overkill for a pin-on-map display |
| Map library | Leaflet + react-leaflet | MapLibre GL JS | Better for vector tiles, but adds WebGL complexity for a simple marker map. Leaflet is simpler and sufficient |
| Form library | react-hook-form | Formik | Heavier, more re-renders, not integrated with shadcn/ui's Form component |
| Validation | Zod | Yup | Zod has better TypeScript inference, is shadcn/ui's default, and Zod 4 is current |
| Address autocomplete | Custom (shadcn Combobox) | react-osm-geocoding | 3 GitHub stars, unmaintained, bypasses our backend API |
| Address autocomplete | Custom (shadcn Combobox) | @amraneze/osm-autocomplete | Low adoption, calls Nominatim directly (bypasses backend), no shadcn integration |
| Toast | sonner | react-hot-toast | sonner is shadcn/ui's default, better animations, actively maintained |
| State management | React useState/context | Redux, Zustand, Jotai | Single-page form with one API call — global state management is unnecessary overhead |
| Routing | None | React Router, TanStack Router | Single landing page with no navigation — routing adds complexity for zero benefit |
| Data fetching | Native fetch | TanStack Query, SWR | One POST endpoint, one autocomplete GET — a fetching library adds abstraction for 2 API calls |

## What NOT to Use

| Technology | Why Not |
|------------|---------|
| Redux / Zustand / Jotai | No shared state beyond the form. react-hook-form manages form state. useState handles UI state |
| React Router / TanStack Router | Single-page app with no routes. The entire UI is one form + results view |
| TanStack Query / SWR | Two API calls total (autocomplete + valuation). A caching/fetching layer adds complexity without benefit |
| Formik | Heavier than react-hook-form, more re-renders, no shadcn/ui integration |
| Yup | Zod has better TypeScript inference and is shadcn/ui's default |
| Google Maps / Mapbox | Require paid API keys. The project uses Nominatim (free, no key) — mixing paid map tiles with free geocoding is architecturally inconsistent |
| Framer Motion | Nice-to-have animations, but tailwindcss-animate is already installed and sufficient for the MVP. Can add later if needed |
| Next.js / Remix | This is a Vite SPA that calls an existing FastAPI backend. SSR frameworks add deployment complexity (Node server) for zero SEO benefit on a form-based tool |

## Installation

```bash
cd frontend2

# Form handling
npm install react-hook-form zod @hookform/resolvers

# Map
npm install leaflet react-leaflet
npm install -D @types/leaflet

# Utilities
npm install use-debounce sonner

# shadcn/ui components (as needed during development)
npx shadcn add form input label popover command
```

## Leaflet CSS Import

Leaflet requires its CSS to be imported globally. Add to `src/main.tsx`:

```typescript
import 'leaflet/dist/leaflet.css'
```

## Sources

- react-leaflet v5.0.0: https://github.com/PaulLeCam/react-leaflet/releases/tag/v5.0.0 (Dec 2024)
- Leaflet 1.9.4: https://www.npmjs.com/package/leaflet (stable, May 2023)
- react-hook-form 7.75.0: https://www.npmjs.com/package/react-hook-form (May 2026)
- Zod 4.4.3: https://www.npmjs.com/package/zod (May 2026)
- @hookform/resolvers 5.2.2: https://www.npmjs.com/package/@hookform/resolvers (Sep 2025, includes Zod 4 fix)
- use-debounce 10.1.1: https://www.npmjs.com/package/use-debounce (Mar 2026)
- sonner 2.0.7: https://www.npmjs.com/package/sonner (Aug 2025)
- @types/leaflet 1.9.21: https://www.npmjs.com/package/@types/leaflet (Oct 2025)
- shadcn/ui Form docs: https://ui.shadcn.com/docs/forms/react-hook-form
- Nominatim usage policy (1 req/s limit): https://operations.osmfoundation.org/policies/nominatim/
