# Architecture Patterns

**Domain:** Single-page property valuation tool — React landing page with interactive form  
**Researched:** 2025-05-13

## System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        App (root)                           │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │                   HeroSection                         │  │
│  │  PropHero branding, headline, subtext                 │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │               ValuationForm (card)                    │  │
│  │                                                       │  │
│  │  ┌─────────────────────────────────────────────────┐  │  │
│  │  │          AddressAutocomplete                    │  │  │
│  │  │  ┌──────────────┐  ┌─────────────────────────┐  │  │  │
│  │  │  │ ComboboxInput│  │    AddressMap (Leaflet)  │  │  │  │
│  │  │  │ + Popover    │  │    click → reverse geo   │  │  │  │
│  │  │  └──────────────┘  └─────────────────────────┘  │  │  │
│  │  └─────────────────────────────────────────────────┘  │  │
│  │                                                       │  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────────┐    │  │
│  │  │ Stepper  │  │ Stepper  │  │  NumberInput      │    │  │
│  │  │ (beds)   │  │ (baths)  │  │  (m²)            │    │  │
│  │  └──────────┘  └──────────┘  └──────────────────┘    │  │
│  │                                                       │  │
│  │  ┌─────────────────────────────────────────────────┐  │  │
│  │  │              SubmitButton                       │  │  │
│  │  └─────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │            ResultsSection (conditional)                │  │
│  │  ┌──────────┐ ┌──────────┐ ┌────────────────────┐    │  │
│  │  │StatsGrid │ │Estimate  │ │  ListingsGrid      │    │  │
│  │  │          │ │Card      │ │  (comparable cards) │    │  │
│  │  └──────────┘ └──────────┘ └────────────────────┘    │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│              ↕ fetch() via lib/api.ts                       │
│  ┌───────────────────────────────────────────────────────┐  │
│  │            FastAPI Backend (:8001)                     │  │
│  │  GET  /api/addresses/autocomplete?q=&limit=           │  │
│  │  GET  /api/addresses/reverse?lat=&lon=                │  │
│  │  POST /api/valuation                                  │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | Owns State? | Talks To |
|-----------|---------------|-------------|----------|
| **App** | Root layout, composes sections | No (passes form down) | HeroSection, ValuationForm, ResultsSection |
| **HeroSection** | PropHero branding, headline, value prop text | No (pure presentational) | Nothing |
| **ValuationForm** | Owns all form state via React Hook Form; validates; submits | **Yes** — form state + submission state | AddressAutocomplete, Stepper, NumberInput, SubmitButton, `lib/api.ts` |
| **AddressAutocomplete** | Address search combobox + map. Debounced Nominatim API calls, suggestion popover, map click for reverse geocode | Internal: search query, suggestions list, loading flag. Exposes selected `ResolvedAddress` via RHF controller | `lib/api.ts` (autocomplete + reverse), AddressMap |
| **AddressMap** | Leaflet map display, marker placement, click-to-select | Internal: map instance ref, marker ref | Parent (fires `onMapClick` callback) |
| **Stepper** | Increment/decrement control for beds & baths (min/max bounded) | Controlled via RHF `field.value` / `field.onChange` | Nothing (pure input) |
| **NumberInput** | Surface area (m²) numeric input with validation | Controlled via RHF | Nothing (pure input) |
| **SubmitButton** | Submit trigger, loading spinner state | Reads `isSubmitting` from RHF `formState` | Nothing |
| **ResultsSection** | Renders valuation response: stats, estimate card, listings grid | No (receives data as props) | StatsGrid, EstimateCard, ListingsGrid |

## Recommended Project Structure

```
frontend/src/
├── App.tsx                      ← Root: composes sections
├── main.tsx                     ← Entry point (StrictMode, createRoot)
├── index.css                    ← Tailwind directives + CSS variables
│
├── components/
│   ├── ui/                      ← shadcn/ui primitives (auto-generated)
│   │   ├── button.tsx
│   │   ├── command.tsx          ← needed for combobox autocomplete
│   │   ├── form.tsx             ← shadcn form wrapper (RHF integration)
│   │   ├── input.tsx
│   │   ├── label.tsx
│   │   ├── popover.tsx          ← needed for combobox dropdown
│   │   └── ...
│   │
│   ├── HeroSection.tsx          ← Branding, headline, subtext
│   ├── ValuationForm.tsx        ← Form container, RHF provider, submit handler
│   ├── AddressAutocomplete.tsx  ← Combobox + map, debounce, Nominatim integration
│   ├── AddressMap.tsx           ← Leaflet map (react-leaflet v5)
│   ├── Stepper.tsx              ← Reusable +/- counter (beds, baths)
│   └── ResultsSection.tsx       ← Stats, estimate, listings (future phase)
│
├── lib/
│   ├── utils.ts                 ← cn() helper (exists)
│   ├── api.ts                   ← Typed fetch wrappers for backend endpoints
│   ├── schemas.ts               ← Zod validation schemas for form
│   └── types.ts                 ← TypeScript types mirroring backend models
│
└── hooks/
    └── use-debounce.ts          ← Debounce hook for autocomplete input
```

### Why This Structure

**Flat components/ over feature folders.** This is a single-page app with ~8 components. Feature folders add navigation overhead without payoff at this scale. When a results section is added later, it can be extracted to `components/results/` if it grows beyond 3 files.

**shadcn/ui in `components/ui/`.** This is the shadcn default and keeps generated primitives separate from application components. The `shadcn add` CLI expects this path (configured in `components.json`).

**`lib/` for shared logic.** API client, Zod schemas, and types live here because multiple components import them. The API client is the single place that knows backend URLs.

**`hooks/` for custom hooks.** Only `use-debounce` is needed initially. Keeps hooks discoverable and avoids mixing them into component files.

## Data Flow

### 1. Form State (React Hook Form)

```
                    useForm({ resolver: zodResolver(valuationSchema) })
                                        │
                    ┌───────────────────┼───────────────────────┐
                    │                   │                       │
              Controller          Controller              register()
                    │                   │                       │
           AddressAutocomplete     Stepper ×2             NumberInput
           field.onChange(          field.onChange(         (m² — native
            ResolvedAddress)        number)               input binding)
```

`ValuationForm` creates the RHF form instance and passes field controllers down. Each input component receives `field` from RHF's `Controller` (or uses `register()` for simple inputs). No prop drilling of individual values — RHF manages the entire form tree.

### 2. Address Autocomplete Flow

```
User types in combobox
    │
    ▼
useDebounce(query, 300ms)
    │
    ▼ (when debounced value changes)
fetch GET /api/addresses/autocomplete?q={query}&limit=5
    │
    ▼
Render suggestions in Command/Popover dropdown
    │
    ▼ (user selects suggestion)
field.onChange(selectedAddress: ResolvedAddress)
    │
    ├──► Update map marker + flyTo(lat, lon)
    └──► RHF stores full ResolvedAddress object
```

### 3. Map Click → Reverse Geocode

```
User clicks map
    │
    ▼
AddressMap fires onMapClick({ lat, lon })
    │
    ▼
AddressAutocomplete calls:
  fetch GET /api/addresses/reverse?lat={lat}&lon={lon}
    │
    ▼
Receives ResolvedAddress → same path as suggestion select:
  field.onChange(address), update marker, update combobox display value
```

### 4. Form Submission

```
User clicks Submit
    │
    ▼
RHF validates via Zod schema
    │  (fail → inline field errors, no API call)
    ▼
onSubmit handler in ValuationForm:
  POST /api/valuation {
    address: string,
    m2: number,
    bedrooms: number,
    bathrooms: number,
    selected_address: ResolvedAddress | null
  }
    │
    ▼
Response → ValuationResponse passed to ResultsSection
    │
    ├──► StatsGrid renders price statistics
    ├──► EstimateCard renders estimated value + range
    └──► ListingsGrid renders comparable property cards
```

### State Ownership Summary

| State | Owner | Why Here |
|-------|-------|----------|
| Form values (address, m2, beds, baths) | `ValuationForm` via RHF | Single form, single owner. RHF handles all field state. |
| Autocomplete suggestions | `AddressAutocomplete` (local) | Transient UI state, not part of form data |
| Map instance + marker | `AddressMap` (ref) | Leaflet manages its own DOM; React controls it via refs |
| Submission loading state | `ValuationForm` via RHF `formState.isSubmitting` | RHF tracks this automatically |
| Valuation results | `App` (lifted) or `ValuationForm` (local) | Depends on whether results need to survive form re-renders. Start local, lift if needed. |
| Error state | `ValuationForm` (local) | API errors displayed inline within the form section |

## Key Technology Decisions

### react-leaflet v5 for Map Component
React-Leaflet v5.0.0 requires React 19 as a peer dependency — aligns exactly with this project's React version. It resolves the "Map container is already initialized" bug that affected v4 under React 19's StrictMode. Use `MapContainer`, `TileLayer`, and `Marker` components directly.

**Confidence:** HIGH (verified via react-leaflet v5.0.0 release notes and GitHub issues)

### shadcn Command + Popover for Address Autocomplete
The Combobox pattern in shadcn/ui combines `Command` (from cmdk) with `Popover`. Set `shouldFilter={false}` on Command to disable client-side filtering — results come from the Nominatim API. This gives accessible keyboard navigation, proper ARIA roles, and consistent styling for free.

**Confidence:** HIGH (verified via shadcn/ui combobox docs)

### React Hook Form + Zod for Form Management
The canonical shadcn/ui form pattern. `useForm` with `zodResolver` provides: type-safe validation inferred from schemas, accessible error messages via `FormMessage`, uncontrolled inputs for performance. The Zod schema can mirror the backend's `ValuationRequest` Pydantic model for consistency.

**Confidence:** HIGH (verified via shadcn/ui form docs)

### Custom Stepper Over Native Select
The existing frontend uses `<select>` dropdowns for beds/baths. A custom Stepper (increment/decrement buttons around a display) is more tactile for small integer ranges (1–5). Follow WAI-ARIA spinbutton pattern: `role="spinbutton"`, `aria-valuenow`, `aria-valuemin`, `aria-valuemax`, Arrow key support.

**Confidence:** MEDIUM (pattern is well-established, but implementation is custom — no shadcn primitive exists)

## Patterns to Follow

### Pattern 1: Controlled Components via RHF Controller

All custom inputs (AddressAutocomplete, Stepper) integrate through RHF's `Controller` component. This provides a consistent `field` object with `value`, `onChange`, `onBlur`, and `ref`.

```tsx
<FormField
  control={form.control}
  name="bedrooms"
  render={({ field }) => (
    <FormItem>
      <FormLabel>Bedrooms</FormLabel>
      <FormControl>
        <Stepper
          value={field.value}
          onChange={field.onChange}
          min={1}
          max={5}
        />
      </FormControl>
      <FormMessage />
    </FormItem>
  )}
/>
```

### Pattern 2: Debounced API Calls in Autocomplete

Use a `useDebounce` hook (or `useEffect` with timeout cleanup) to batch keystrokes before hitting the Nominatim API. 300ms debounce is the sweet spot for address typing.

```tsx
const [query, setQuery] = useState("")
const debouncedQuery = useDebounce(query, 300)

useEffect(() => {
  if (debouncedQuery.length < 3) return
  fetchSuggestions(debouncedQuery)
}, [debouncedQuery])
```

### Pattern 3: Map as Imperative Ref, Not Declarative State

Leaflet's map instance is fundamentally imperative. `react-leaflet` v5 bridges this well, but avoid trying to make the map "reactive" to every state change. Instead:
- Use `useMap()` hook inside child components to access the map instance
- Call `map.flyTo()` imperatively when the selected address changes
- Keep the marker position in a ref or derive it from the selected address

### Pattern 4: API Client with TypeScript Types

The `lib/api.ts` module is the single boundary between frontend and backend. It returns typed objects matching the backend's Pydantic models. This prevents type drift and makes API changes immediately visible at compile time.

```tsx
export async function autocompleteAddresses(
  query: string,
  limit = 5,
): Promise<ResolvedAddress[]> {
  const params = new URLSearchParams({ q: query, limit: String(limit) })
  return fetchJson(`/api/addresses/autocomplete?${params}`)
}
```

## Anti-Patterns to Avoid

### Anti-Pattern 1: Global State for Form Data
**What:** Reaching for Zustand, Redux, or React Context for form state.  
**Why bad:** This is a single form on a single page. Global state adds indirection, makes the form harder to reason about, and creates unnecessary re-renders. React Hook Form already manages all field state efficiently via refs.  
**Instead:** Keep all form state inside `useForm()`. Lift only the valuation *response* to a shared parent if it's needed outside the form.

### Anti-Pattern 2: Uncontrolled Leaflet in React's Render Cycle
**What:** Creating the map with `new L.Map()` inside a `useEffect` and manually managing DOM.  
**Why bad:** Conflicts with React's virtual DOM, causes "already initialized" errors in StrictMode, makes cleanup unreliable.  
**Instead:** Use `react-leaflet` v5's `<MapContainer>` which handles lifecycle correctly with React 19.

### Anti-Pattern 3: Prop Drilling Form Values
**What:** Passing individual form values (`address`, `m2`, `bedrooms`) as props through multiple layers.  
**Why bad:** Every value change re-renders the entire chain. Verbose and error-prone when fields are added.  
**Instead:** Use RHF's `Controller` and `FormField` pattern. Each input component receives only its own `field` object.

### Anti-Pattern 4: Inline API Calls in Components
**What:** Writing `fetch("/api/...")` directly inside component event handlers.  
**Why bad:** Duplicated URLs, no centralized error handling, impossible to swap backends or add auth headers later.  
**Instead:** All API calls go through `lib/api.ts`. Components call typed functions like `submitValuation(payload)`.

### Anti-Pattern 5: Overengineering the File Structure
**What:** Creating `features/valuation/components/form/inputs/stepper/` for a 10-component app.  
**Why bad:** Navigation overhead exceeds organizational benefit. A single-page app doesn't need feature isolation.  
**Instead:** Flat `components/` directory. Extract sub-folders only when a component group exceeds 3 files.

## Build Order (Dependency Chain)

Components have clear dependencies that dictate build sequence:

```
Phase order (→ means "depends on"):

1. lib/types.ts          ← TypeScript types (ResolvedAddress, ValuationRequest, etc.)
   lib/schemas.ts        ← Zod schemas (mirrors types, adds validation rules)
   lib/api.ts            ← Typed fetch wrappers
   hooks/use-debounce.ts ← Debounce hook

2. HeroSection           ← Pure presentational, no dependencies
   Stepper               ← Reusable input, depends only on shadcn/ui Button
   AddressMap            ← Leaflet wrapper, depends on react-leaflet + types

3. AddressAutocomplete   ← Depends on: AddressMap, lib/api.ts, use-debounce,
                            shadcn Command/Popover, types
4. ValuationForm         ← Depends on: AddressAutocomplete, Stepper, shadcn Form,
                            lib/api.ts, lib/schemas.ts

5. App                   ← Depends on: HeroSection, ValuationForm
                            (ResultsSection deferred to later phase)
```

**Implication for roadmap phases:**
- **Wave 1** (parallel, no dependencies): types/schemas/api module, HeroSection, Stepper, AddressMap
- **Wave 2** (needs Wave 1): AddressAutocomplete
- **Wave 3** (needs Wave 2): ValuationForm (composing all inputs)
- **Wave 4** (needs Wave 3): App integration, replacing scaffold content

This ordering means the form's complex pieces (autocomplete, map) can be developed and tested in isolation before wiring them into the form.

## Scalability Considerations

| Concern | Now (MVP) | If Results Phase Added | If Multiple Pages |
|---------|-----------|----------------------|-------------------|
| State management | RHF only | Lift response to App via `useState` | Add React Router + lift shared state to context |
| API client | Simple fetch wrappers | Add response caching (TanStack Query) | TanStack Query becomes essential |
| Component count | ~8 components, flat folder | ~15 components, extract `results/` subfolder | Feature folders become justified |
| Map instances | Single map in form | Could add results map | Share map context or use separate instances |
| Bundle size | Small (shadcn tree-shakes) | Add Leaflet (~40KB gz) only if map shown | Code-split per route |

## Sources

- react-leaflet v5.0.0 release: https://github.com/PaulLeCam/react-leaflet/releases/tag/v5.0.0 (HIGH confidence)
- react-leaflet React 19 issue: https://github.com/PaulLeCam/react-leaflet/issues/1133 (HIGH confidence)
- shadcn/ui Combobox docs: https://ui.shadcn.com/docs/components/combobox (HIGH confidence)
- shadcn/ui Form docs: https://ui.shadcn.com/docs/forms/react-hook-form (HIGH confidence)
- WAI-ARIA spinbutton pattern: https://react-aria.adobe.com/NumberField/useNumberField (HIGH confidence)
- React SPA folder structure patterns: https://learnwebcraft.com/learn/react/structuring-large-react-apps (MEDIUM confidence)
