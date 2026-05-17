# Phase 1: Foundation + Branded Shell - Research

**Researched:** 2026-05-13
**Domain:** React component architecture, design token application, TypeScript API contracts
**Confidence:** HIGH

## Summary

Phase 1 is a low-risk, high-certainty phase. The entire scaffold already exists — React 19 + Vite 8 + Tailwind 3.4 + shadcn/ui are installed and configured, PropHero design tokens are mapped to both CSS custom properties and Tailwind utility classes, and the button component classes (`.btn-primary`, `.btn-secondary`) are ready to use. The work is primarily removal of demo content and replacement with the PropHero-branded hero section, plus creating thin foundation TypeScript modules (types, Zod schema, API client stub) for downstream phases.

The backend API contract is fully defined via Pydantic models in `backend/models.py`. The frontend TypeScript types must mirror these models exactly. One critical correction: the actual backend endpoint is `POST /api/valuation` (not `/api/valuate` as mentioned in CONTEXT.md D-10). The Zod schema provides frontend-specific validation bounds (stricter than the backend's) for UX quality.

**Primary recommendation:** Rewrite `App.tsx` from scratch (it's demo code), create `HeroSection.tsx` as a pure presentational component, add foundation modules under `src/lib/`, and clean up all demo assets. No new npm dependencies needed except Zod for schema validation.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Clean white background with electric blue accent on headline text, a subtle `surface-tint` (#f3f5fe) section for visual separation, and the orange CTA button. No heavy gradient banners or background illustrations.
- **D-02:** Matches PropHero's actual site aesthetic — professional, clean, trust-building.
- **D-03:** Remove the TabBarLayout navigation entirely. Use a simple single-page scroll layout: hero at top, form content section below.
- **D-04:** No header navigation needed — this is a single-purpose landing page (valuation tool).
- **D-05:** Replace current `App.tsx` demo content completely.
- **D-06:** Include an empty card container below the hero section with `surface-tint` background and rounded corners. This gives phases 2-4 a clear mount point for map, autocomplete, and form inputs.
- **D-07:** The placeholder should feel intentional (a styled section/card), not a visibly "empty" gap.
- **D-08:** Set up TypeScript types for the valuation API request/response shape (`lib/types.ts`).
- **D-09:** Create a Zod schema matching the API contract (`lib/schemas.ts`) — lightweight, prevents rework in Phase 4.
- **D-10:** Create a minimal API client module (`lib/api.ts`) with a single `valuateProperty()` function stub pointing to the existing backend `/api/valuate` endpoint.
- **D-11:** Keep foundation code thin — just types, schema, and the fetch wrapper. No form state management or validation wiring yet.

### Claude's Discretion
- Exact spacing, padding, and responsive breakpoints within the hero section
- CTA button label copy (suggest "Valorar mi propiedad" or similar — must be Spanish)
- Whether to include a brief subtitle paragraph below the headline explaining the tool's purpose

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| BRAND-01 | User sees a hero section with "¿Cuánto vale tu casa?" headline and PropHero branding | HeroSection component with h1 using existing CSS typography rules, "tu casa" in `text-primary` electric blue. Design tokens already configured in tailwind.config.js and index.css. |
| BRAND-02 | Page uses PropHero design tokens (electric blue #2050f6, cyan #65c6eb, orange CTA #f45504, Inter font) | All tokens already mapped: CSS custom properties (`--ph-blue`, `--ph-orange`, etc.), shadcn HSL variables, Tailwind utility classes (`bg-primary`, `bg-accent`, `text-primary`), Inter font loaded from Google Fonts in index.html. |
| BRAND-04 | All UI text is in Spanish | Change `<html lang="en">` to `<html lang="es">` in index.html, all copy defined in UI-SPEC copywriting contract. Reference: original `frontend/index.html` uses Spanish throughout. |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Hero section rendering | Browser / Client | — | Pure presentational React component, no server-side concerns |
| Design token application | Browser / Client | — | CSS custom properties + Tailwind utilities, all client-side |
| Spanish copy | Browser / Client | — | Static text in JSX, no i18n framework needed for single language |
| TypeScript types | Browser / Client | — | Compile-time contract mirroring backend Pydantic models |
| Zod schema | Browser / Client | — | Frontend-only validation, consumed by Phase 4 form |
| API client stub | Browser / Client | API / Backend | Client-side fetch wrapper targeting `POST /api/valuation` on existing FastAPI backend |
| Placeholder card | Browser / Client | — | Static mount point for downstream phases |

## Standard Stack

### Core (Already Installed)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| react | ^19.2.6 | UI framework | Already installed, latest stable [VERIFIED: package.json] |
| react-dom | ^19.2.6 | DOM rendering | Already installed [VERIFIED: package.json] |
| vite | ^8.0.12 | Build tool + dev server | Already installed [VERIFIED: package.json] |
| tailwindcss | ^3.4.17 | Utility CSS with PropHero tokens | Already configured with full design system [VERIFIED: tailwind.config.js] |
| lucide-react | ^1.14.0 | Icon library | Already installed, needed for placeholder card icon [VERIFIED: package.json] |
| class-variance-authority | ^0.7.1 | Component variant management | Already installed for shadcn/ui [VERIFIED: package.json] |
| clsx + tailwind-merge | ^2.1.1 / ^3.6.0 | Class merging (`cn()` utility) | Already installed [VERIFIED: package.json] |

### To Install
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| zod | ^4.4.3 | Schema validation for API contract | Latest stable. Required by D-09 for `ValuationRequest` schema. Basic API (`z.object`, `z.string`, `z.number`, `.min`, `.max`) is stable in v4. [VERIFIED: npm registry 2026-05-13] |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Zod v4 | Zod v3 (3.24.x via `zod@next`) | v3 still maintained as `next` tag but v4 is `latest`. v4 is a clean start for new code — no migration burden. Error customization API changed but doesn't affect Phase 1 (schemas only, no error rendering yet). |
| Zod | yup / valibot | Zod is the ecosystem standard with shadcn/ui. Valibot is smaller but less integrated. Yup is older. |

**Installation:**
```bash
cd frontend && npm install zod
```

**Version verification:**
- `zod@latest` = 4.4.3 [VERIFIED: npm registry 2026-05-13]
- `vitest@latest` = 4.1.6 [VERIFIED: npm registry 2026-05-13] (for Validation Architecture)

## Architecture Patterns

### System Architecture Diagram

```
[User loads page]
    │
    ▼
[index.html]  ← lang="es", Inter font via Google Fonts
    │
    ▼
[main.tsx]  ← StrictMode + createRoot
    │
    ▼
[App.tsx]  ← Layout shell (single-page scroll)
    │
    ├──► [HeroSection]  ← h1 headline, subtitle, CTA button
    │       └── "¿Cuánto vale tu casa?" + "Valorar mi propiedad" CTA
    │
    └──► [PlaceholderCard]  ← Inline in App or extracted
            └── Lucide icon + "Aquí aparecerá el formulario" text
            └── Mount point for Phase 2-4 components

[Foundation modules — no UI, consumed by downstream phases]
    ├── lib/types.ts      ← TypeScript interfaces mirroring backend Pydantic models
    ├── lib/schemas.ts    ← Zod schema for ValuationRequest (frontend validation bounds)
    └── lib/api.ts        ← valuateProperty() fetch wrapper → POST /api/valuation
```

### Recommended Project Structure
```
src/
├── components/
│   ├── ui/              # shadcn/ui primitives (button.tsx exists)
│   └── HeroSection.tsx  # Phase 1 hero component
├── lib/
│   ├── utils.ts         # cn() utility (exists)
│   ├── types.ts         # TypeScript interfaces for API contract
│   ├── schemas.ts       # Zod validation schemas
│   └── api.ts           # API client (fetch wrapper)
├── App.tsx              # Layout shell (rewritten)
├── App.css              # DELETE — demo styles
├── index.css            # Global styles + design tokens (exists, keep)
└── main.tsx             # Entry point (exists, keep)
```

### Pattern 1: Presentational Component (HeroSection)
**What:** Stateless component that receives no props, renders static branded content.
**When to use:** Components that render fixed content with no interactivity or state.
**Example:**
```tsx
// Source: UI-SPEC component inventory
import { cn } from '@/lib/utils'

export function HeroSection() {
  return (
    <section className={cn('px-xl pt-2xl pb-xl', 'md:px-md')}>
      <h1>
        ¿Cuánto vale{' '}
        <span className="text-primary">tu casa</span>?
      </h1>
      <p className="mt-3 max-w-[560px] text-ink-secondary">
        Introduce los datos de tu propiedad y te mostramos comparables
        reales para estimar su valor de mercado.
      </p>
      <a href="#form-area" className="btn-primary mt-6 inline-flex">
        Valorar mi propiedad
      </a>
    </section>
  )
}
```

### Pattern 2: Typed API Client Stub
**What:** Thin async function wrapping `fetch()` with TypeScript generics for request/response typing.
**When to use:** API modules that downstream phases consume without modification.
**Example:**
```tsx
// Source: backend/main.py endpoint definition
import type { ValuationRequest, ValuationResponse } from './types'

const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8001'

export async function valuateProperty(
  request: ValuationRequest,
): Promise<ValuationResponse> {
  const res = await fetch(`${API_BASE}/api/valuation`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })
  if (!res.ok) {
    throw new Error(`Valuation failed: ${res.status}`)
  }
  return res.json()
}
```

### Anti-Patterns to Avoid
- **Importing TabBar or demo components:** These are removed in this phase. Ensure zero references remain after cleanup.
- **Hardcoding the API base URL:** Use `import.meta.env.VITE_API_URL` with localhost fallback. The `.env.example` already has this variable defined.
- **Mixing backend validation bounds with frontend bounds:** The Zod schema has stricter bounds (m2: 20-500) than the backend (m2: >0). This is intentional — the frontend prevents nonsensical inputs, the backend is the safety net.
- **Adding state management to Phase 1 components:** D-11 explicitly says no form state management yet. HeroSection is pure presentational.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Design tokens | Custom CSS variables from scratch | Existing `tailwind.config.js` + `index.css` token system | Already mapped PropHero palette to both CSS custom properties and Tailwind utilities. 40+ tokens configured. [VERIFIED: codebase] |
| Button styles | Custom button CSS | `.btn-primary` / `.btn-secondary` classes in `index.css` | Pre-built with correct colors, hover states, focus rings, pill radius. [VERIFIED: index.css line 137-148] |
| Class merging | Manual string concatenation | `cn()` from `src/lib/utils.ts` | Handles Tailwind class conflicts correctly via `tailwind-merge`. [VERIFIED: codebase] |
| Typography scale | Custom font sizes | Existing `h1`, `h2` CSS rules + `:root` font declaration | Responsive clamp, letter-spacing, line-height all pre-configured. [VERIFIED: index.css lines 167-188] |
| Icon rendering | SVG files or custom icon component | `lucide-react` (installed) | Tree-shakeable, consistent with shadcn/ui ecosystem. [VERIFIED: package.json] |

**Key insight:** This phase has an unusually low build-from-scratch ratio. ~80% of the design system infrastructure already exists. The main work is wiring existing tokens into new components and writing the API contract modules.

## Common Pitfalls

### Pitfall 1: Wrong API Endpoint URL
**What goes wrong:** CONTEXT.md D-10 says `/api/valuate` but the actual backend endpoint is `POST /api/valuation`.
**Why it happens:** Typo in the discussion notes vs. actual route definition.
**How to avoid:** The API client MUST use `/api/valuation`. Verify against `backend/main.py` line 89: `@app.post("/api/valuation")`.
**Warning signs:** 404 errors when downstream phases try to submit the form.
**Confidence:** HIGH [VERIFIED: backend/main.py source code]

### Pitfall 2: Forgetting to Change HTML lang Attribute
**What goes wrong:** `index.html` currently has `lang="en"` but BRAND-04 requires Spanish.
**Why it happens:** The scaffold was generated with English defaults.
**How to avoid:** Change `<html lang="en">` to `<html lang="es">` in `frontend/index.html`. Also update the `<title>` tag.
**Warning signs:** Accessibility audit failures, screen readers announcing wrong language.
**Confidence:** HIGH [VERIFIED: frontend/index.html line 2]

### Pitfall 3: Leaving text-align: center on #root
**What goes wrong:** Hero content appears centered instead of left-aligned per D-02 / UI-SPEC.
**Why it happens:** `#root` in `index.css` line 158 has `text-align: center` from the demo layout.
**How to avoid:** Remove or override `text-align: center` on `#root`. UI-SPEC explicitly calls for left-aligned text.
**Warning signs:** All text appears centered, doesn't match PropHero site aesthetic.
**Confidence:** HIGH [VERIFIED: index.css line 158]

### Pitfall 4: Orphaned Demo Imports
**What goes wrong:** Build warnings or runtime errors from imports of deleted files.
**Why it happens:** `App.tsx` imports `react.svg`, `vite.svg`, `hero.png`, `TabBar`, and `App.css` — all scheduled for removal.
**How to avoid:** When rewriting `App.tsx`, start fresh — don't try to selectively edit the existing file. Also remove the `@radix-ui/react-tabs` dependency if no other component uses it, and delete `src/components/ui/tabs.tsx`.
**Warning signs:** Build errors on missing modules, unused dependency warnings.
**Confidence:** HIGH [VERIFIED: App.tsx source code]

### Pitfall 5: TypeScript Types Drifting from Backend Models
**What goes wrong:** Frontend types don't match backend Pydantic models, causing runtime deserialization issues.
**Why it happens:** Types are written by hand instead of being derived from the source of truth.
**How to avoid:** Mirror `backend/models.py` field-by-field. Key details: `selected_address` is optional, `m2` is an integer (not float), `bedrooms` allows 0 on the backend (ge=0). Include all models used in the response chain (`ValuationResponse`, `MunicipioInfo`, `Listing`, `ValuationStats`, `SearchMetadata`, `MarketTransactions`, etc.).
**Warning signs:** TypeScript type errors when consuming API responses in Phase 4+.
**Confidence:** HIGH [VERIFIED: backend/models.py source code]

### Pitfall 6: Inter Font Not Loading
**What goes wrong:** Font falls back to system-ui, subtle visual mismatch with PropHero branding.
**Why it happens:** Google Fonts link removed during cleanup, or `font-display: swap` causes FOUT.
**How to avoid:** Keep the existing Google Fonts `<link>` tags in `index.html` (lines 7-12). The `preconnect` hints are already correct. Don't remove them during the `<title>` change.
**Warning signs:** Font inspector shows system-ui instead of Inter.
**Confidence:** HIGH [VERIFIED: index.html lines 7-12]

## Code Examples

### Backend API Contract (Source of Truth for Types)

The following Pydantic models define the API contract. Frontend types MUST mirror these:

```python
# Source: backend/models.py — ValuationRequest
class ValuationRequest(BaseModel):
    address: str = Field(..., description="Full address of the property")
    m2: int = Field(..., gt=0, description="Surface area in square meters")
    bedrooms: int = Field(..., ge=0, description="Number of bedrooms")
    bathrooms: int = Field(..., ge=1, description="Number of bathrooms")
    selected_address: Optional[ResolvedAddress] = None
```

```python
# Source: backend/models.py — ValuationResponse (abbreviated)
class ValuationResponse(BaseModel):
    municipio: MunicipioInfo
    listings: list[Listing]
    stats: ValuationStats
    search_url: str
    search_metadata: SearchMetadata
    market_transactions: Optional[MarketTransactions] = None
```

### Zod Schema Pattern (Zod v4)

```typescript
// Source: https://v4.zod.dev/api — verified 2026-05-13
import { z } from 'zod'

export const valuationRequestSchema = z.object({
  address: z.string().min(1),
  m2: z.number().int().min(20).max(500),
  bedrooms: z.number().int().min(1).max(10),
  bathrooms: z.number().int().min(1).max(5),
})

export type ValuationRequestForm = z.infer<typeof valuationRequestSchema>
```

Note: `.int()` is available in Zod v4 as a refinement on `z.number()`. The schema uses stricter bounds than the backend for UX purposes (e.g., m2 minimum 20 instead of >0). [VERIFIED: v4.zod.dev/api]

### Backend API Endpoints (Full Surface)

| Method | Path | Request | Response | Phase |
|--------|------|---------|----------|-------|
| `POST` | `/api/valuation` | `ValuationRequest` (JSON body) | `ValuationResponse` | Phase 4 (form submission) |
| `GET` | `/api/addresses/autocomplete?q=...&limit=...` | Query params | `ResolvedAddress[]` | Phase 3 (autocomplete) |
| `GET` | `/api/addresses/reverse?lat=...&lon=...` | Query params | `ResolvedAddress` | Phase 2 (map click) |

Source: `backend/main.py` route definitions [VERIFIED: codebase]

### Existing Design Token Usage

```tsx
// Source: tailwind.config.js + index.css — verified in codebase
// Colors available as Tailwind utilities:
// bg-primary (#2050f6), text-primary, bg-accent (#f45504), text-accent
// bg-surface (#fff), bg-surface-tint (#f3f5fe), bg-surface-muted (#f5f7f9)
// text-ink (#1e252d), text-ink-secondary (#596b7d), text-ink-muted (#abb8c7)
//
// Pre-built CSS component classes:
// .btn-primary — orange bg, white text, pill radius, shadow-card, hover to accent-light
// .btn-secondary — blue border, white bg, pill radius
// .btn-ghost — transparent, subtle hover
//
// Spacing tokens: xs(4), sm(8), md(16), lg(24), xl(32), 2xl(48), 3xl(64)
// Border radius: pill(9999px), 2xl(20px), xl(16px)
// Shadows: card, lift
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Zod v3 (`z.object()`, `message` param) | Zod v4 (`z.object()`, `error` param) | Zod 4.0.0 stable release (2025) | Error customization API changed. Basic schema definition unchanged. No impact for Phase 1 (schemas only, no error rendering). [VERIFIED: v4.zod.dev/v4/changelog] |
| Tailwind CSS v3 | Tailwind CSS v4 (Rust engine) | Tailwind v4 released 2025 | Project uses Tailwind v3.4.17 — this is fine, v4 migration not in scope. No action needed. [VERIFIED: package.json] |
| React 18 | React 19 (stable) | Dec 2024 | Project already on React 19.2.6. No migration needed. [VERIFIED: package.json] |

**Deprecated/outdated:**
- `TabBar.tsx` + `tabs.tsx` — demo components, removed in this phase per D-03
- `App.css` — demo styles, fully replaced by index.css token system

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `VITE_API_URL` env var is the correct name for the backend base URL | Code Examples (API Client) | Low — `.env.example` exists in frontend; planner should verify the variable name matches |
| A2 | No other components depend on `@radix-ui/react-tabs` besides TabBar | Pitfall 4 | Low — if something else imports tabs, removing the package would break it. Verify before removing. |

## Open Questions

1. **CTA button behavior in Phase 1**
   - What we know: UI-SPEC suggests either disabled state (`opacity-50 cursor-not-allowed`) or scroll-to-placeholder behavior
   - What's unclear: Which approach provides better UX signal to early testers
   - Recommendation: Use scroll-to-placeholder (`href="#form-area"`) — feels more alive than a disabled button. Claude's discretion per CONTEXT.md.

2. **Should `lib/types.ts` include ALL backend models or just Phase 1 essentials?**
   - What we know: D-08 says "valuation API request/response shape", D-11 says "keep foundation code thin"
   - What's unclear: Whether to include `Listing`, `MarketTransaction`, `SearchMetadata` types now or defer to Phase 4
   - Recommendation: Include the full response type tree now. These are just type definitions (zero runtime cost) and prevent downstream phases from re-deriving the same types. Omitting them creates rework.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Node.js | Build + dev server | ✓ | v25.3.0 | — |
| npm | Package management | ✓ | 11.6.2 | — |
| node_modules | All dependencies | ✓ | Installed | `npm install` if missing |
| Google Fonts CDN | Inter font loading | ✓ (external) | — | System font stack fallback (Inter, system-ui, sans-serif) configured in tailwind.config.js |
| Backend (FastAPI) | API client target | Not required for Phase 1 | — | API client is a stub; no actual calls in this phase |

**Missing dependencies with no fallback:** None
**Missing dependencies with fallback:** None

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | Vitest 4.1.6 (not yet installed) |
| Config file | None — needs Wave 0 setup |
| Quick run command | `npx vitest run --reporter=verbose` |
| Full suite command | `npx vitest run` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| BRAND-01 | Hero section renders with correct headline text | unit (component) | `npx vitest run src/__tests__/HeroSection.test.tsx -t "headline"` | ❌ Wave 0 |
| BRAND-02 | Design tokens are applied (CSS classes present) | unit (component) | `npx vitest run src/__tests__/HeroSection.test.tsx -t "tokens"` | ❌ Wave 0 |
| BRAND-04 | All visible text is in Spanish | unit (snapshot or assertion) | `npx vitest run src/__tests__/HeroSection.test.tsx -t "spanish"` | ❌ Wave 0 |
| D-08/D-09 | Zod schema validates correct/invalid payloads | unit | `npx vitest run src/__tests__/schemas.test.ts` | ❌ Wave 0 |
| D-10 | API client sends to correct endpoint | unit (mock fetch) | `npx vitest run src/__tests__/api.test.ts` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `npx vitest run --reporter=verbose`
- **Per wave merge:** `npx vitest run`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] Install vitest + @testing-library/react + @testing-library/jest-dom + jsdom: `npm install -D vitest @testing-library/react @testing-library/jest-dom jsdom`
- [ ] Create `vitest.config.ts` with jsdom environment and path alias resolution
- [ ] `src/__tests__/HeroSection.test.tsx` — covers BRAND-01, BRAND-02, BRAND-04
- [ ] `src/__tests__/schemas.test.ts` — covers D-09 (Zod schema validation)
- [ ] `src/__tests__/api.test.ts` — covers D-10 (API client endpoint + error handling)

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | N/A — no auth in this app |
| V3 Session Management | No | N/A — stateless landing page |
| V4 Access Control | No | N/A — no protected resources |
| V5 Input Validation | Yes (Phase 4, not Phase 1) | Zod schema prepared in this phase, wired in Phase 4 |
| V6 Cryptography | No | N/A — no sensitive data handling |

### Known Threat Patterns for This Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| XSS via user input in JSX | Tampering | React auto-escapes JSX expressions. No `dangerouslySetInnerHTML` needed. |
| API base URL injection | Information Disclosure | Use `import.meta.env.VITE_API_URL` (build-time only, not exposed at runtime beyond the bundle). |

**Phase 1 security exposure is minimal** — no user input processing, no API calls, no authentication. The Zod schema defined here provides the input validation foundation consumed by Phase 4.

## Files to Create

| File | Purpose | Dependencies |
|------|---------|-------------|
| `src/lib/types.ts` | TypeScript interfaces mirroring backend Pydantic models | None |
| `src/lib/schemas.ts` | Zod validation schema for ValuationRequest | zod (to install) |
| `src/lib/api.ts` | API client with `valuateProperty()` stub | types.ts |
| `src/components/HeroSection.tsx` | Hero section presentational component | cn() utility |

## Files to Modify

| File | Change | Reason |
|------|--------|--------|
| `index.html` | `lang="en"` → `lang="es"`, update `<title>` | BRAND-04 |
| `src/App.tsx` | Complete rewrite — remove demo, add HeroSection + PlaceholderCard | D-03, D-05, D-06 |
| `src/index.css` | Remove `text-align: center` from `#root` | UI-SPEC layout contract |

## Files to Delete

| File | Reason |
|------|--------|
| `src/App.css` | Demo styles, not needed (UI-SPEC "Assets to Remove") |
| `src/assets/react.svg` | Demo asset |
| `src/assets/vite.svg` | Demo asset |
| `src/assets/hero.png` | Demo asset |
| `src/components/TabBar.tsx` | D-03: Remove TabBarLayout entirely |
| `src/components/ui/tabs.tsx` | No tabs in single-page layout (verify no other consumers first — A2) |

## Sources

### Primary (HIGH confidence)
- `backend/models.py` — Full Pydantic model definitions for API contract [VERIFIED: codebase]
- `backend/main.py` — Route definitions, endpoint URLs [VERIFIED: codebase]
- `frontend/tailwind.config.js` — Design token configuration [VERIFIED: codebase]
- `frontend/src/index.css` — CSS custom properties, typography, button classes [VERIFIED: codebase]
- `frontend/package.json` — Installed dependencies and versions [VERIFIED: codebase]
- `frontend/index.html` — Current HTML scaffold, Google Fonts link [VERIFIED: codebase]
- `frontend/src/App.tsx` — Current demo code to be replaced [VERIFIED: codebase]
- npm registry — zod@4.4.3, vitest@4.1.6, lucide-react@1.14.0 [VERIFIED: npm view, 2026-05-13]

### Secondary (MEDIUM confidence)
- [v4.zod.dev/api](https://v4.zod.dev/api) — Zod v4 schema definition API [CITED: official docs]
- [v4.zod.dev/v4/changelog](https://v4.zod.dev/v4/changelog) — Zod v4 migration guide [CITED: official docs]

### Tertiary (LOW confidence)
- None — all claims verified against codebase or official sources

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all packages verified in package.json or npm registry
- Architecture: HIGH — simple component architecture with no ambiguity, scaffold already exists
- Pitfalls: HIGH — all identified from direct codebase inspection
- API contract: HIGH — verified against backend source code

**Research date:** 2026-05-13
**Valid until:** 2026-06-13 (stable — no fast-moving dependencies)
