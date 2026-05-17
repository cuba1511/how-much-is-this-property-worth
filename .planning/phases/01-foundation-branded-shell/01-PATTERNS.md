# Phase 1: Foundation + Branded Shell - Pattern Map

**Mapped:** 2026-05-13
**Files analyzed:** 7 (4 new, 3 modified)
**Analogs found:** 5 / 7

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/lib/types.ts` | model | transform | `backend/models.py` (source of truth) | source-mirror |
| `src/lib/schemas.ts` | utility | transform | `src/lib/utils.ts` (export pattern) | partial |
| `src/lib/api.ts` | service | request-response | — | no-analog |
| `src/components/HeroSection.tsx` | component | presentational | `src/components/ui/button.tsx` | role-match |
| `src/App.tsx` (rewrite) | component | presentational | `src/main.tsx` + `src/components/TabBar.tsx` | role-match |
| `index.html` (modify) | config | — | itself | exact |
| `src/index.css` (modify) | config | — | itself | exact |

## Pattern Assignments

### `src/lib/types.ts` (model, transform)

**Source of truth:** `backend/models.py`

The TypeScript interfaces must mirror the Pydantic models field-by-field. No existing TypeScript type file exists in this project, so this establishes the pattern.

**Module export pattern** — copy from `src/lib/utils.ts` (lines 1-6):
```typescript
// Named exports, no default export
// One concern per file, clean imports at top
import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
```

**Backend model structure to mirror** — `backend/models.py` (lines 5-28):
```python
class ResolvedAddress(BaseModel):
    label: str
    lat: float
    lon: float
    municipality: str
    province: Optional[str] = None
    road: Optional[str] = None
    house_number: Optional[str] = None
    postcode: Optional[str] = None
    neighbourhood: Optional[str] = None
    quarter: Optional[str] = None
    city_district: Optional[str] = None
    country: Optional[str] = None
    provider: str = "nominatim"
    provider_id: Optional[str] = None
    precision: Optional[str] = None

class ValuationRequest(BaseModel):
    address: str = Field(..., description="Full address of the property")
    m2: int = Field(..., gt=0, description="Surface area in square meters")
    bedrooms: int = Field(..., ge=0, description="Number of bedrooms")
    bathrooms: int = Field(..., ge=1, description="Number of bathrooms")
    selected_address: Optional[ResolvedAddress] = None
```

**Full response model chain** — `backend/models.py` (lines 131-138):
```python
class ValuationResponse(BaseModel):
    municipio: MunicipioInfo
    listings: list[Listing]
    stats: ValuationStats
    search_url: str
    search_metadata: SearchMetadata
    market_transactions: Optional[MarketTransactions] = None
```

**Pydantic → TypeScript mapping rules:**
| Pydantic | TypeScript |
|----------|-----------|
| `str` | `string` |
| `int` | `number` |
| `float` | `number` |
| `Optional[T] = None` | `T \| null` or `T?` (use optional `?` for clarity) |
| `list[T]` | `T[]` |
| `Field(default_factory=list)` | `T[] = []` (default in runtime, just `T[]` in type) |

---

### `src/lib/schemas.ts` (utility, transform)

**Analog:** `src/lib/utils.ts` (export pattern only)

No Zod schemas exist in the project yet. This file establishes the validation pattern. Follow the same module conventions as `utils.ts`: named exports, no default export, `@/` path alias for internal imports.

**Import/export pattern** from `src/lib/utils.ts` (lines 1-6):
```typescript
import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
```

**Apply same structure:** single-responsibility module, named exports, external dependency import at top, internal imports below.

**Zod v4 API pattern** (from RESEARCH.md, verified against v4.zod.dev):
```typescript
import { z } from 'zod'

export const valuationRequestSchema = z.object({
  address: z.string().min(1),
  m2: z.number().int().min(20).max(500),
  bedrooms: z.number().int().min(1).max(10),
  bathrooms: z.number().int().min(1).max(5),
})

export type ValuationRequestForm = z.infer<typeof valuationRequestSchema>
```

---

### `src/lib/api.ts` (service, request-response)

**Analog:** None — first API client in this frontend.

No existing fetch wrapper or API service exists. This is a greenfield file. Use established project conventions:
- Named exports (per `utils.ts` pattern)
- `@/` path alias for type imports
- `import.meta.env.VITE_API_URL` for base URL (from `.env.example` conventions — note: the frontend `.env.example` does not yet define `VITE_API_URL` but RESEARCH.md confirms this is the correct variable name for Vite)

**Error handling convention** to establish (from RESEARCH.md Pattern 2):
```typescript
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

**Critical:** Endpoint is `/api/valuation` (NOT `/api/valuate` per CONTEXT.md typo). Verified in `backend/main.py`.

---

### `src/components/HeroSection.tsx` (component, presentational)

**Analog:** `src/components/ui/button.tsx`

**Import pattern** (lines 1-5):
```typescript
import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"
```

**Key conventions from button.tsx:**
- `@/lib/utils` import for `cn()` helper
- Named function exports (not default)
- Component at top level, export at bottom

**Component export pattern** (lines 43, 55-57):
```typescript
const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    // ...
  }
)
Button.displayName = "Button"

export { Button, buttonVariants }
```

**For HeroSection** — simpler pattern since it's a stateless presentational component with no props:
- No forwardRef needed (not a reusable primitive)
- Named export directly: `export function HeroSection()`
- Use `cn()` for class merging if conditional classes needed
- Reference existing design tokens via Tailwind utilities

**Button class usage** from `src/index.css` (lines 137-138):
```css
.btn-primary {
  @apply inline-flex items-center justify-center gap-2 rounded-pill bg-accent px-6 py-3 text-center font-semibold text-accent-foreground shadow-card transition hover:bg-accent-light focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary;
}
```

**Typography tokens** from `src/index.css` (lines 167-178):
```css
h1 {
  font-size: clamp(2rem, 4vw + 1rem, 3.25rem);
  letter-spacing: -0.03em;
  line-height: 1.1;
  margin: 24px 0 12px;
}
```

**Available spacing utilities** from `tailwind.config.js` (lines 92-99):
```javascript
spacing: {
  xs: '4px',
  sm: '8px',
  md: '16px',
  lg: '24px',
  xl: '32px',
  '2xl': '48px',
  '3xl': '64px',
},
```

**Surface color for placeholder card** from `tailwind.config.js` (lines 62-66):
```javascript
surface: {
  DEFAULT: '#ffffff',
  muted: '#f5f7f9',
  tint: '#f3f5fe',
},
```

---

### `src/App.tsx` (component/layout, presentational) — REWRITE

**Analog:** `src/components/TabBar.tsx` (layout component pattern)

The current `App.tsx` is demo code being fully replaced. `TabBar.tsx` shows how a layout component is structured in this project.

**Layout component pattern** from `src/components/TabBar.tsx` (lines 1-5):
```typescript
import type { ReactNode } from "react"
import { BookOpen, Home, Users } from "lucide-react"

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { cn } from "@/lib/utils"
```

**Key conventions:**
- Type-only imports use `import type`
- Icon imports from `lucide-react` (tree-shakeable)
- Internal `@/` path alias for project imports
- `cn()` used for complex class compositions

**Entry point pattern** from `src/main.tsx` (lines 1-15):
```typescript
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App'

const root = document.getElementById('root')
if (!root) {
  throw new Error('Root element #root not found')
}

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
```

**Note:** `main.tsx` uses `import App from './App'` — the rewritten `App.tsx` must maintain a default export for compatibility.

---

### `index.html` (config) — MODIFY

**Self-analog** — `frontend/index.html` (lines 1-19):
```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link
      href="https://fonts.googleapis.com/css2?family=Inter:ital,opsz,wght@0,14..32,400..700;1,14..32,400..700&display=swap"
      rel="stylesheet"
    />
    <title>House valuation — PropHero style</title>
  </head>
```

**Changes required:**
- Line 2: `lang="en"` → `lang="es"`
- Line 13: `<title>` → Spanish title (e.g., "¿Cuánto vale tu casa? — PropHero")
- **Preserve** lines 7-12 (Google Fonts preconnect + link) — critical for Inter font loading

---

### `src/index.css` (config/styles) — MODIFY

**Self-analog** — `frontend/src/index.css` (lines 154-164):
```css
#root {
  width: 1126px;
  max-width: 100%;
  margin: 0 auto;
  text-align: center;
  border-inline: 1px solid var(--border);
  min-height: 100svh;
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
}
```

**Change required:** Remove `text-align: center` (line 158) — UI-SPEC requires left-aligned text for PropHero brand aesthetic. Keep all other #root styles.

---

## Shared Patterns

### Path Alias (`@/`)
**Source:** `frontend/vite.config.ts` (line 9)
**Apply to:** All new `src/` files
```typescript
// vite.config.ts configures @ → ./src
resolve: {
  alias: {
    "@": fileURLToPath(new URL("./src", import.meta.url)),
  },
},
```
Usage: `import { cn } from '@/lib/utils'`

### Class Merging Utility
**Source:** `src/lib/utils.ts` (lines 1-6)
**Apply to:** All component files that compose classes conditionally
```typescript
import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
```

### Design Token Access
**Source:** `frontend/tailwind.config.js` + `src/index.css`
**Apply to:** All component files

| Token | Tailwind Utility | Raw Value |
|-------|-----------------|-----------|
| Electric blue | `text-primary`, `bg-primary` | `#2050f6` |
| Orange CTA | `bg-accent`, `text-accent` | `#f45504` |
| Surface tint | `bg-surface-tint` | `#f3f5fe` |
| Body text | `text-ink` | `#1e252d` |
| Secondary text | `text-ink-secondary` | `#596b7d` |
| Card shadow | `shadow-card` | `0 10px 40px rgba(32,80,246,0.08)` |
| Pill radius | `rounded-pill` | `9999px` |
| Large radius | `rounded-2xl` | `20px` |

### Component Export Convention
**Source:** `src/components/ui/button.tsx` + `src/components/TabBar.tsx`
**Apply to:** All new component files

- shadcn/ui primitives: `forwardRef` + named export at bottom
- App-level components (HeroSection, App): direct named function export or default export
- `cn()` for class composition

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `src/lib/api.ts` | service | request-response | No fetch wrappers or API clients exist in the frontend yet. This is the first service module. Use RESEARCH.md Pattern 2 as reference. |
| `src/lib/schemas.ts` | utility | transform | No Zod schemas exist in the project. First validation module. Follow `utils.ts` export style + Zod v4 API from RESEARCH.md. |

## Metadata

**Analog search scope:** `frontend/src/`, `backend/models.py`
**Files scanned:** 12
**Pattern extraction date:** 2026-05-13
