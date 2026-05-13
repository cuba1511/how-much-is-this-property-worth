# Requirements: PropHero Landing Page — Property Valuation

**Defined:** 2026-05-13
**Core Value:** Users can quickly and intuitively submit their property details through a polished, branded form that feels trustworthy and modern.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Form Inputs

- [ ] **FORM-01**: User can type an address and see autocomplete suggestions from Nominatim API with debounced search
- [ ] **FORM-02**: User can select a suggestion to populate the address field with full address details
- [ ] **FORM-03**: User can increment/decrement bedrooms using a stepper component (- NUM +)
- [ ] **FORM-04**: User can increment/decrement bathrooms using a stepper component (- NUM +)
- [ ] **FORM-05**: User can enter property area in square meters via a number input

### Map Integration

- [ ] **MAP-01**: User sees a Leaflet map with a marker pin on the selected address after choosing from autocomplete

### Form Behavior

- [ ] **BEHV-01**: User sees inline validation errors when submitting with missing or invalid fields (Zod schema)
- [ ] **BEHV-02**: User sees a loading state on the submit button while the backend processes the request
- [ ] **BEHV-03**: User's form data persists in localStorage so they don't lose progress on page refresh
- [ ] **BEHV-04**: Form submits to the existing FastAPI backend `/api/valuate` endpoint

### Branding & Layout

- [ ] **BRAND-01**: User sees a hero section with "¿Cuánto vale tu casa?" headline and PropHero branding
- [ ] **BRAND-02**: Page uses PropHero design tokens (electric blue #2050f6, cyan #65c6eb, orange CTA #f45504, Inter font)
- [ ] **BRAND-03**: Page is mobile-responsive and works well on all screen sizes
- [ ] **BRAND-04**: All UI text is in Spanish

### Polish & UX

- [ ] **UX-01**: User sees a confirmation badge when an address has been selected from autocomplete
- [ ] **UX-02**: User sees contextual help text below each form field
- [ ] **UX-03**: Form elements have smooth micro-interactions and transitions (hover, focus, loading states)

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Results Display

- **RES-01**: User sees estimated property value after submission
- **RES-02**: User sees comparable listings grid from Idealista
- **RES-03**: User sees statistics cards (avg price, price/m², min, max)
- **RES-04**: User sees market transactions data with negotiation margins

### Advanced Form

- **ADV-01**: User can click on the map to reverse geocode and set address
- **ADV-02**: User can select property type (apartment, house, studio)
- **ADV-03**: User can input year built
- **ADV-04**: User can upload property photos

## Out of Scope

| Feature | Reason |
|---------|--------|
| User authentication / accounts | Not needed for a valuation form |
| Backend modifications | Using existing FastAPI endpoints as-is |
| Dark mode | Not required for MVP, PropHero site is light-only |
| SEO / meta tags optimization | Defer to later iteration |
| Multi-step wizard form | Only 4 inputs — wizard is overkill |
| Google Maps / Mapbox | Require paid API keys; Leaflet + OSM is free |
| Analytics / tracking | Defer to post-launch |
| Multi-language support | Spanish only for now |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| FORM-01 | — | Pending |
| FORM-02 | — | Pending |
| FORM-03 | — | Pending |
| FORM-04 | — | Pending |
| FORM-05 | — | Pending |
| MAP-01 | — | Pending |
| BEHV-01 | — | Pending |
| BEHV-02 | — | Pending |
| BEHV-03 | — | Pending |
| BEHV-04 | — | Pending |
| BRAND-01 | — | Pending |
| BRAND-02 | — | Pending |
| BRAND-03 | — | Pending |
| BRAND-04 | — | Pending |
| UX-01 | — | Pending |
| UX-02 | — | Pending |
| UX-03 | — | Pending |

**Coverage:**
- v1 requirements: 17 total
- Mapped to phases: 0
- Unmapped: 17

---
*Requirements defined: 2026-05-13*
*Last updated: 2026-05-13 after initial definition*
