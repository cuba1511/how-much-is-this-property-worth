# Roadmap: PropHero Landing Page — Property Valuation

## Overview

Build a React landing page where users input property details (address via autocomplete + map, bedrooms, bathrooms, m²) and submit to the existing FastAPI backend for valuation. The build follows the component dependency chain: shared types and branding shell → Leaflet map → address autocomplete wired to map → full form with validation and submission → polish, responsive, and persistence.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Foundation + Branded Shell** — Types, schemas, API client, hero section with PropHero branding *(completed 2026-05-13)*
- [ ] **Phase 2: Interactive Map** — Leaflet map component with marker placement and tile rendering
- [ ] **Phase 3: Address Autocomplete** — Debounced Nominatim search, suggestion selection, map integration
- [ ] **Phase 4: Form Composition + Submission** — Stepper inputs, m² field, Zod validation, backend submission
- [ ] **Phase 5: Polish + Responsive + Persistence** — Mobile optimization, localStorage, micro-interactions

## Phase Details

### Phase 1: Foundation + Branded Shell
**Goal:** Users see a PropHero-branded landing page with hero section, design tokens applied, and Spanish copy
**Mode:** mvp
**Depends on:** Nothing (first phase)
**Requirements:** BRAND-01, BRAND-02, BRAND-04
**Success Criteria**:
  1. User sees "¿Cuánto vale tu casa?" headline with PropHero branding when loading the page
  2. Page renders with PropHero design tokens — electric blue, cyan, orange CTA colors, and Inter font
  3. All visible UI text is in Spanish
**Plans:** 2 plans

Plans:
- [x] 01-01-PLAN.md — Foundation modules + demo cleanup (types, schemas, API client, remove demo artifacts, Spanish lang) *(complete)*
- [x] 01-02-PLAN.md — Hero section + app shell (HeroSection component, App.tsx rewrite, placeholder card) *(complete)*

**UI hint**: yes

### Phase 2: Interactive Map
**Goal:** Users see an interactive Leaflet map that renders correctly and displays location markers
**Mode:** mvp
**Depends on:** Phase 1
**Requirements:** MAP-01
**Success Criteria**:
  1. User sees a Leaflet map with OpenStreetMap tiles rendered on the page
  2. Map displays a marker pin at a given coordinate
  3. Map is interactive — user can pan and zoom without visual glitches
**Plans**: TBD
**UI hint**: yes

### Phase 3: Address Autocomplete
**Goal:** Users can search for their property address and see it confirmed on the map
**Mode:** mvp
**Depends on:** Phase 1, Phase 2
**Requirements:** FORM-01, FORM-02, UX-01
**Success Criteria**:
  1. User types at least 3 characters and sees address suggestions appear after a debounced delay
  2. User selects a suggestion and the address field populates with the full formatted address
  3. Map pin moves to the selected address location
  4. User sees a visual confirmation badge indicating a valid address is selected
**Plans**: TBD
**UI hint**: yes

### Phase 4: Form Composition + Submission
**Goal:** Users can fill in all property details and submit to the existing FastAPI backend for valuation
**Mode:** mvp
**Depends on:** Phase 1, Phase 3
**Requirements:** FORM-03, FORM-04, FORM-05, BEHV-01, BEHV-02, BEHV-04, UX-02
**Success Criteria**:
  1. User can adjust bedrooms using a stepper control (- NUM +) with min/max bounds
  2. User can adjust bathrooms using a stepper control (- NUM +) with min/max bounds
  3. User can enter property area in square meters via a numeric input
  4. User sees inline validation errors when submitting with missing or invalid fields
  5. User sees a loading state on the submit button while the backend processes the request
**Plans**: TBD
**UI hint**: yes

### Phase 5: Polish + Responsive + Persistence
**Goal:** The form is polished, mobile-optimized, and preserves user input across sessions
**Mode:** mvp
**Depends on:** Phase 4
**Requirements:** BRAND-03, BEHV-03, UX-03
**Success Criteria**:
  1. Page layout adapts correctly across mobile, tablet, and desktop screen sizes
  2. User's form data persists in localStorage and restores on page refresh
  3. Form elements have smooth micro-interactions — hover, focus, and loading transitions
**Plans**: TBD
**UI hint**: yes

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation + Branded Shell | 0/0 | Not started | - |
| 2. Interactive Map | 0/0 | Not started | - |
| 3. Address Autocomplete | 0/0 | Not started | - |
| 4. Form Composition + Submission | 0/0 | Not started | - |
| 5. Polish + Responsive + Persistence | 0/0 | Not started | - |
