# Phase 1: Foundation + Branded Shell - Context

**Gathered:** 2026-05-13
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver a PropHero-branded landing page shell with a hero section showing the "¿Cuánto vale tu casa?" headline, PropHero design tokens applied throughout, all UI text in Spanish, and foundation code (TypeScript types, Zod schemas, API client) ready for downstream phases to consume.

</domain>

<decisions>
## Implementation Decisions

### Hero Section Visual Style
- **D-01:** Clean white background with electric blue accent on headline text, a subtle `surface-tint` (#f3f5fe) section for visual separation, and the orange CTA button. No heavy gradient banners or background illustrations.
- **D-02:** Matches PropHero's actual site aesthetic — professional, clean, trust-building.

### Page Shell & Layout
- **D-03:** Remove the TabBarLayout navigation entirely. Use a simple single-page scroll layout: hero at top, form content section below.
- **D-04:** No header navigation needed — this is a single-purpose landing page (valuation tool).
- **D-05:** Replace current `App.tsx` demo content completely.

### Form Area Presence
- **D-06:** Include an empty card container below the hero section with `surface-tint` background and rounded corners. This gives phases 2-4 a clear mount point for map, autocomplete, and form inputs.
- **D-07:** The placeholder should feel intentional (a styled section/card), not a visibly "empty" gap.

### Foundation Code Scope
- **D-08:** Set up TypeScript types for the valuation API request/response shape (`lib/types.ts`).
- **D-09:** Create a Zod schema matching the API contract (`lib/schemas.ts`) — lightweight, prevents rework in Phase 4.
- **D-10:** Create a minimal API client module (`lib/api.ts`) with a single `valuateProperty()` function stub pointing to the existing backend `/api/valuate` endpoint.
- **D-11:** Keep foundation code thin — just types, schema, and the fetch wrapper. No form state management or validation wiring yet.

### Claude's Discretion
- Exact spacing, padding, and responsive breakpoints within the hero section
- CTA button label copy (suggest "Valorar mi propiedad" or similar — must be Spanish)
- Whether to include a brief subtitle paragraph below the headline explaining the tool's purpose

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Context
- `.planning/PROJECT.md` — Project definition, constraints, key decisions
- `.planning/REQUIREMENTS.md` — Full requirements list with traceability (BRAND-01, BRAND-02, BRAND-04 for this phase)
- `.planning/ROADMAP.md` — Phase dependencies and success criteria

### Design System (already scaffolded)
- `frontend2/tailwind.config.js` — PropHero color tokens, typography, spacing, shadows, border-radius
- `frontend2/src/index.css` — CSS custom properties (PropHero palette), shadcn/ui HSL variables, button component classes

### Existing Reference Implementation
- `frontend/index.html` — Original vanilla HTML frontend showing UX flow, form layout, and Spanish copy

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `.btn-primary` / `.btn-secondary` / `.btn-ghost`: Button component classes already defined in `index.css` — use directly
- shadcn/ui `Button` component (`src/components/ui/button.tsx`): Available for more complex button needs
- `cn()` utility (`src/lib/utils.ts`): Class merging helper
- `lucide-react`: Icon library already installed

### Established Patterns
- CSS variables for design tokens with shadcn HSL mapping pattern
- Tailwind utility classes + `@layer components` for reusable styles
- `@/` path alias configured for clean imports

### Integration Points
- `App.tsx` is the entry point — replace demo content with hero + shell layout
- Root `#root` has max-width 1126px centered layout — keep or adjust for full-width hero
- `main.tsx` renders `<App />` directly — no router needed for this phase

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches. The PropHero site (prophero.com) serves as the visual reference for brand alignment.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 1-Foundation + Branded Shell*
*Context gathered: 2026-05-13*
