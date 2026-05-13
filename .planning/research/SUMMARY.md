# Project Research Summary

**Project:** PropHero Landing Page — Property Valuation
**Domain:** Single-page interactive form (address autocomplete + map + property details)
**Researched:** 2026-05-13
**Confidence:** HIGH

## Executive Summary

This is a single-page React form that collects property details (address via autocomplete/map, bedrooms, bathrooms, m²) and submits to an existing FastAPI backend. The domain is well-understood: Spanish real-estate portals (Idealista, Fotocasa) set user expectations for address autocomplete with map confirmation, stepper-style numeric inputs, and mobile-first responsive design. The recommended approach is a lean build using React Hook Form + Zod for form state (matching shadcn/ui's native integration), Leaflet + react-leaflet v5 for the map (pairing naturally with the backend's Nominatim geocoding), and a custom combobox autocomplete backed by the existing `/api/addresses/autocomplete` endpoint.

The primary technical risk is Leaflet integration under React 19's Strict Mode — double-initialization bugs, broken marker icons under Vite bundling, and missing CSS are all well-documented failure modes with known fixes. The secondary risk is Nominatim rate limiting (1 req/s) breaking autocomplete under real usage; this is mitigated by aggressive debouncing (300–500ms), minimum character thresholds, and proxying through the backend. Both risks have deterministic solutions that must be applied during initial setup, not patched later.

The project's constraints are favorable: the stack is already scaffolded (React 19, Vite 8, Tailwind 3.4, shadcn/ui with PropHero tokens), the backend API endpoints exist, and scope is explicitly limited to the form — no results display, no routing, no authentication. This allows a focused 4-5 phase build following the component dependency chain: foundation → map → autocomplete → form composition → polish.

## Key Findings

### Recommended Stack

The core stack (React 19, Vite 8, TypeScript 6, Tailwind 3.4, shadcn/ui) is already scaffolded and confirmed stable. Three capability gaps need filling: form management, map rendering, and input debouncing.

**Core additions:**
- **react-hook-form + zod + @hookform/resolvers**: Form state management — shadcn/ui's `<Form>` component is built on this stack; using anything else means fighting the library
- **leaflet + react-leaflet v5**: Map rendering — the only open-source option that pairs with Nominatim/OSM without API keys; v5 specifically built for React 19
- **use-debounce**: Autocomplete throttling — <1KB, zero deps, respects Nominatim's 1 req/s rate limit

**Explicitly not needed:** Redux/Zustand (single form), React Router (single page), TanStack Query (two API calls), Mapbox/Google Maps (require paid keys), Formik/Yup (not shadcn-integrated).

### Expected Features

**Must have (table stakes):**
- Address autocomplete with suggestion dropdown
- Map with pin confirmation + reverse geocode on click
- Stepper controls for bedrooms/bathrooms
- Square meters numeric input with mobile keyboard
- Form validation with inline errors
- Submit button with loading state (15-60s backend response)
- Mobile-responsive layout (70% of Spanish RE traffic is mobile)
- PropHero branding + Spanish language UI
- Basic accessibility (labels, ARIA, focus management)

**Should have (competitive edge, low effort):**
- Selected address confirmation badge (visual trust signal)
- Form state persistence in localStorage (prevents abandonment)
- Contextual help text per field
- Micro-interactions / transitions (premium feel)

**Defer (v2+):**
- Results display (stats, estimate, comparable listings)
- Property type selector, photo upload, year built
- Analytics/tracking, A/B testing
- Multi-step wizard (only 4 inputs — wizard is overkill)

### Architecture Approach

Flat component architecture with React Hook Form as the single state owner. The form is a composition of ~8 components in a clear dependency chain: types/schemas → presentational components (HeroSection, Stepper, AddressMap) → complex components (AddressAutocomplete) → form container (ValuationForm) → root (App). No global state, no routing, no feature folders.

**Major components:**
1. **ValuationForm** — owns all form state via RHF; composes inputs; handles submission
2. **AddressAutocomplete** — combobox + map integration; debounced Nominatim calls; manages suggestions
3. **AddressMap** — Leaflet wrapper; marker placement; click-to-reverse-geocode callback
4. **Stepper** — reusable increment/decrement control; ARIA spinbutton pattern
5. **HeroSection** — branding, headline, value proposition (pure presentational)

### Critical Pitfalls

1. **Leaflet double-init in React 19 Strict Mode** — use react-leaflet v5.0.0+; never disable StrictMode to "fix" this
2. **Marker icons break under Vite bundling** — explicitly import and configure icon paths before any marker creation
3. **Missing Leaflet CSS = gray/shattered tiles** — import `leaflet/dist/leaflet.css` in main.tsx, AFTER Tailwind base styles
4. **Nominatim rate limiting** — debounce 300-500ms, 3-char minimum, proxy through backend, cache results
5. **Autocomplete race conditions** — use AbortController per request; cancel previous fetch on new keystroke

## Implications for Roadmap

Based on the architecture's dependency chain and pitfall clustering, the build should follow this sequence:

### Phase 1: Foundation — Types, Schemas, API Client

**Rationale:** Every component depends on shared types, Zod schemas, and the API client. Building these first enables parallel development of Wave 2 components and catches type mismatches with the backend immediately.
**Delivers:** `lib/types.ts`, `lib/schemas.ts`, `lib/api.ts`, shared TypeScript interfaces mirroring backend Pydantic models
**Addresses:** Type safety, API contract alignment
**Avoids:** Type drift between frontend and backend, duplicated fetch logic

### Phase 2: Map Component + Leaflet Setup

**Rationale:** The map has the highest pitfall density (5 of 13 pitfalls are Leaflet-related). Solving Strict Mode init, marker icons, CSS import, mobile scroll, and tile URL issues in isolation — before wiring into the autocomplete — prevents debugging these problems inside a complex component.
**Delivers:** `AddressMap` component with marker placement, click handler, mobile scroll handling, correct tile URL
**Addresses:** Map with pin confirmation, reverse geocode on click (map half)
**Avoids:** Pitfalls 1, 2, 3, 6, 8, 10

### Phase 3: Address Autocomplete

**Rationale:** Depends on Phase 1 (API client) and Phase 2 (AddressMap). This is the highest-complexity feature — combobox UI, debounced API calls, race condition prevention, map integration, reverse geocode wiring. Building it after the map and API client are proven reduces integration unknowns.
**Delivers:** `AddressAutocomplete` component with debounced search, suggestion dropdown, map interaction, reverse geocode
**Addresses:** Address autocomplete, map pin confirmation, reverse geocode on click
**Avoids:** Pitfalls 4, 5, 11, 12

### Phase 4: Form Composition + Submission

**Rationale:** All input components are ready — now wire them into a single form with validation and submission. This phase is lower risk because it assembles proven parts.
**Delivers:** `ValuationForm` with RHF + Zod validation, `Stepper` components, submit handler with loading state, `HeroSection`
**Addresses:** Stepper controls, m² input, form validation, submit with loading, branding, Spanish copy
**Avoids:** Pitfalls 7, 9, 13

### Phase 5: Polish + Mobile + Accessibility

**Rationale:** After core functionality works, add the differentiators and ensure WCAG compliance. These are low-effort, high-value additions that benefit from seeing the complete form in context.
**Delivers:** localStorage persistence, responsive refinements, ARIA audit, contextual help text, address confirmation badge, micro-interactions
**Addresses:** All P1/P2 differentiators from feature research
**Avoids:** Shipping without mobile QA or accessibility review

### Phase Ordering Rationale

- **Dependency-driven:** Each phase builds on outputs of the previous (types → map → autocomplete → form → polish)
- **Risk-front-loaded:** The hardest integration (Leaflet + React 19) is Phase 2, isolated from form complexity
- **Testable in isolation:** Each phase produces a working component that can be verified independently before integration
- **Pitfall-clustered:** Leaflet pitfalls grouped in Phase 2, API pitfalls in Phase 3, form pitfalls in Phase 4 — each phase has a clear "pitfall checklist"

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 3 (Autocomplete):** Complex interaction between combobox, debounce, abort controllers, and map sync — review shadcn/ui combobox examples and test Nominatim behavior with Spanish addresses

Phases with standard patterns (skip research-phase):
- **Phase 1 (Foundation):** Well-documented Zod + TypeScript + fetch patterns
- **Phase 2 (Map):** react-leaflet v5 docs are comprehensive; pitfall fixes are one-liners
- **Phase 4 (Form):** shadcn/ui form docs provide exact patterns; RHF is extensively documented
- **Phase 5 (Polish):** Standard CSS/ARIA work with clear acceptance criteria

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All libraries verified at specific versions; scaffolded project confirms compatibility |
| Features | HIGH | Feature set derived from competitor analysis + existing v1 reference implementation |
| Architecture | HIGH | Component structure follows react-leaflet v5 docs, shadcn/ui form patterns, established React SPA conventions |
| Pitfalls | HIGH | Every pitfall backed by GitHub issues with confirmed fixes; existing v1 code validates Nominatim/Leaflet behavior |

**Overall confidence:** HIGH

### Gaps to Address

- **Long submission UX:** Backend scraping takes 15-60s; need to validate what progress feedback the backend provides (SSE? polling?) during Phase 4 planning
- **Nominatim at scale:** If the landing page gets significant traffic, the free Nominatim API will hit limits; plan a LocationIQ/OpenCage fallback path but don't build it now
- **React 19 form actions:** Need to verify that react-hook-form's `handleSubmit` doesn't conflict with React 19's native form action behavior — test during Phase 4

## Sources

### Primary (HIGH confidence)
- react-leaflet v5.0.0 release notes — React 19 compatibility, API surface
- Leaflet GitHub issues #7424, #6247, #1133 — marker icon fixes, StrictMode handling
- shadcn/ui Form docs — react-hook-form + Zod integration patterns
- shadcn/ui Combobox docs — Command + Popover autocomplete pattern
- Nominatim Usage Policy — rate limits, User-Agent requirements
- OSM Tile Policy — canonical tile URL, usage restrictions
- W3C Spin Button APG — accessible stepper implementation
- React #31649 — form action state clearing behavior

### Secondary (MEDIUM confidence)
- Spanish RE portal analysis (Idealista, Fotocasa, Hogaria) — feature expectations, mobile usage stats
- React SPA folder structure guides — flat vs. feature folder patterns

### Tertiary (LOW confidence)
- Nominatim Spanish address field mapping — `state`/`county`/`province` behavior varies by region; needs runtime testing

---
*Research completed: 2026-05-13*
*Ready for roadmap: yes*
