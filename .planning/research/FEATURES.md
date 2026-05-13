# Feature Landscape

**Domain:** Property valuation landing page (form-only scope)
**Market:** Spain (PropHero brand)
**Researched:** 2026-05-13
**Scope:** React form page — address input, property details, submit to backend. No results display.

## Table Stakes

Features users expect from a property valuation form. Missing = users abandon or lose trust.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Address autocomplete | Idealista/Fotocasa both have it; users won't type full addresses manually | High | Nominatim + debounced search. Already proven in v1. |
| Map with pin confirmation | Visual confirmation that the system found the right location. 70% of Spanish RE traffic is mobile — a pin is faster than reading text. | Medium | Leaflet + OpenStreetMap tiles. Existing in v1. |
| Reverse geocode on map click | Idealista supports this. Users expect tap-to-select on map. | Medium | Nominatim reverse endpoint. Existing in v1. |
| Bedrooms stepper (- N +) | Faster than dropdowns on mobile. Common pattern on Fotocasa/Idealista property filters. | Low | Custom component, min 1 / max 10 bounds. |
| Bathrooms stepper (- N +) | Same rationale as bedrooms. Consistent UX across similar inputs. | Low | Same component, different bounds. |
| Square meters number input | Core property attribute. Every valuation tool requires it. | Low | Numeric keyboard on mobile via `inputmode="numeric"`. |
| Form validation with inline errors | Users expect immediate feedback. Missing validation = broken submissions, wasted time. | Medium | Per-field validation: required, min/max, format. |
| Submit button with loading state | Users need confirmation the system is working. Prevents double-submission. | Low | Spinner + disabled state + text change ("Estimando..."). |
| Mobile-responsive layout | 70% of Spanish RE valuations are requested on mobile. Non-negotiable. | Medium | Tailwind responsive breakpoints. Single-column mobile, two-column desktop. |
| PropHero branding (header/logo) | Users need to know whose tool this is. Brand recognition. | Low | Sticky header with logo. |
| Spanish language UI | Target market is Spain. English would be disorienting. | Low | All labels, placeholders, errors in Spanish. |
| Accessible form (WCAG 2.1 AA) | Legal compliance, usability for all users. Labels, ARIA, focus management. | Medium | `htmlFor`, `aria-invalid`, `aria-describedby`, focus on first error. |

## Differentiators

Features that elevate beyond competitors. Not expected, but create competitive advantage.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Selected address confirmation badge | Green badge showing parsed municipality + province. Gives confidence the system "understood" the address correctly. | Low | Already in v1. Simple derived display. |
| Animated transitions / micro-interactions | Polish that signals quality. Fade-ins, smooth steppers. Idealista's tool feels clinical — ours can feel premium. | Low | Tailwind + CSS transitions. No heavy library needed. |
| Hero section with value proposition | Explains what the tool does before asking for data. Reduces "what is this?" bounces. | Low | Headline + 1-line description. Already in v1. |
| Contextual help text per field | "Puedes escribir y elegir una sugerencia, o hacer click en el mapa" — reduces friction for first-time users. | Low | Small muted text below inputs. |
| Form state persistence (localStorage) | If user accidentally navigates away or refreshes, their input is preserved. Reduces abandonment on mobile. | Low | Save to localStorage on each input change, restore on mount. |
| Keyboard-optimized inputs | Numeric keyboard for m², stepper buttons large enough for thumb taps, proper `inputmode` attributes. | Low | `inputmode="numeric"`, large tap targets (44px min). |
| Error recovery with field focus | On submit with errors, focus jumps to first invalid field with shake animation. Clearly guides user to fix. | Low | `scrollIntoView` + focus + brief CSS animation. |
| Progress hint ("1 minute valuation") | Fotocasa says "Valora tu vivienda en 1 minuto" — setting time expectation reduces perceived effort. | Low | Single line in hero or above CTA. |

## Anti-Features

Features to deliberately NOT build in this milestone. Either out of scope, harmful to UX, or premature.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Multi-step wizard form | Only 4 inputs — a wizard adds unnecessary clicks and complexity. Wizard pattern is for 8+ fields. | Single-page form with all fields visible. |
| Lead capture / email gate | PropHero tool is for internal use / direct users. Gating results behind email destroys trust and isn't needed. | Direct submission, no registration. |
| Property type selector (apartment/house/land) | Backend doesn't use it. Adding unused fields confuses scope and delays delivery. | Omit entirely. Add when backend supports it. |
| Results display | Explicitly out of scope for this milestone. Will be Phase 2. | Submit redirects or shows "processing" — results handled later. |
| Official appraisal disclaimer | We're not competing with bank tasaciones. Legal disclaimers add noise for an internal tool. | Skip unless legal requires it later. |
| Photo upload | No backend support. Adds massive complexity (upload, storage, processing) for zero value in MVP. | Omit entirely. |
| Property age / year built | Not used by current backend scraper filters. Would be dead UI. | Omit. Add when backend consumes it. |
| Neighborhood/zone selector | Address autocomplete + geocoding already resolves location. Manual zone selection is redundant. | Let geocoder handle zone inference. |
| A/B testing infrastructure | Premature optimization. Build the form first, measure later. | Ship one version. Iterate based on real usage. |
| Analytics/tracking | Out of scope for form-only milestone. Add in a dedicated pass. | Omit. Can be layered on later. |

## Feature Dependencies

```
Address Autocomplete ─────► Map Pin Confirmation
       │                          │
       ▼                          ▼
Reverse Geocode (map click)   Selected Address Badge
       │
       ▼
Form Validation (address required = must have selection)

Stepper Components (beds/baths) ─► Form Validation (bounds checking)

Square Meters Input ─► Form Validation (min > 0)

All Inputs ─► Submit Button ─► Loading State ─► Backend Call
```

Key dependency: Address selection must be confirmed (from autocomplete OR map click) before form can submit. This is the gating input — other fields are simple values.

## MVP Recommendation

**Must ship (table stakes):**
1. Address autocomplete + map + reverse geocode (core interaction)
2. Stepper components for beds/baths
3. Square meters numeric input
4. Form validation with inline errors
5. Submit with loading state
6. Mobile-responsive layout
7. PropHero branding + Spanish copy
8. Basic accessibility (labels, focus, ARIA)

**Ship if time allows (high-value differentiators):**
1. Selected address confirmation badge (very low effort, high clarity)
2. Form state persistence in localStorage (low effort, prevents abandonment)
3. Contextual help text (low effort, reduces confusion)
4. Micro-interactions / transitions (low effort, premium feel)

**Defer:**
- Results display (next milestone)
- Analytics (separate pass)
- Additional property fields (when backend supports them)

## Feature Prioritization Matrix

| Feature | User Value | Dev Effort | Risk | Priority |
|---------|-----------|-----------|------|----------|
| Address autocomplete + map | Critical | High | Medium (API reliability) | P0 |
| Beds/baths steppers | High | Low | Low | P0 |
| Square meters input | High | Low | Low | P0 |
| Form validation | High | Medium | Low | P0 |
| Submit + loading state | High | Low | Low | P0 |
| Mobile responsive | Critical | Medium | Low | P0 |
| Branding + Spanish | High | Low | Low | P0 |
| Accessibility | High | Medium | Low | P0 |
| Address confirmation badge | Medium | Low | Low | P1 |
| localStorage persistence | Medium | Low | Low | P1 |
| Help text | Medium | Low | Low | P1 |
| Micro-interactions | Low | Low | Low | P2 |
| Progress hint copy | Low | Low | Low | P2 |

## Sources

- Idealista valoración: idealista.com/valoracion-de-inmuebles/
- Fotocasa tasación: fotocasa.es/es/tasacion-online/
- Realty Crux guide: realtycrux.com/complete-guide-to-creating-home-valuation-landing-page-examples-included/
- AgentFire AVM features: agentfire.com/blog/home-valuation-features/
- MapAtlas address autocomplete conversion: mapatlas.eu/blog/address-autocomplete-api-checkout-conversion
- Repliers property estimate tool: help.repliers.com/en/article/building-a-step-by-step-property-estimate-tool-for-homeowners-and-sellers
- Spanish RE landing page patterns: adaix.es/landing-page-para-inmobiliaria-potencia-tus-conversiones/
- Hogaria mobile stats (70% mobile): hogaria.net/hogaria/servicios/webinmobiliaria.aspx
