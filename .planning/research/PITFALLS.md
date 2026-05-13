# Domain Pitfalls

**Domain:** React property valuation landing page with address autocomplete + Leaflet map + custom form controls
**Researched:** 2025-05-13
**Project stack:** React 19 + Vite 8 + Tailwind 3.4 + shadcn/ui + Leaflet + Nominatim

---

## Critical Pitfalls

Mistakes that cause rewrites, broken features, or blocked deployments.

### Pitfall 1: Leaflet "Map container is already initialized" in React 19 Strict Mode

**What goes wrong:** React 19's Strict Mode double-invokes effects during development. Leaflet's `MapContainer` initializes on mount, gets torn down, then re-initializes — but the underlying DOM node still holds Leaflet's internal state, throwing `Map container is already initialized`.

**Why it happens:** react-leaflet v5 internally calls `L.map(container)` in a `useEffect`. React 19 Strict Mode runs effects twice to surface cleanup bugs. Leaflet's cleanup doesn't fully remove internal references from the DOM element.

**Warning signs:**
- Gray/blank map area in dev mode but works in production
- Console error: `Map container is already initialized`
- Map works on first render but breaks after hot reload

**Prevention:**
- Use react-leaflet `v5.0.0` or later (explicitly built for React 19)
- Use a `useRef` guard to prevent double-initialization: only call map setup if `mapRef.current` is null
- Never disable Strict Mode to "fix" this — it masks real cleanup bugs

**Detection:** Immediately visible during dev server startup. If you see it, it's wrong.

**Phase:** Address this in the earliest phase that introduces the map component. Must be solved before any map feature work begins.

**Sources:** [react-leaflet #1133](https://github.com/PaulLeCam/react-leaflet/issues/1133) — HIGH confidence

---

### Pitfall 2: Leaflet marker icons break under Vite bundling

**What goes wrong:** Default Leaflet marker icons (pin, shadow) don't render. Instead you get broken image icons or invisible markers. The map tiles load fine, but markers are silently broken.

**Why it happens:** Leaflet's `Icon.Default` detects icon paths by parsing its own CSS. Vite transforms asset URLs (hashing, base64 inlining), so Leaflet concatenates filenames onto transformed URLs, producing garbage paths like `data:image/png;base64,...)marker-icon.png`.

**Warning signs:**
- Map tiles render correctly but markers are invisible or show broken-image icons
- No console errors (Leaflet swallows the 404)
- Works with CDN Leaflet but breaks with `npm install leaflet`

**Prevention:**
Explicitly import and configure marker icons at app init:
```tsx
import markerIcon from "leaflet/dist/images/marker-icon.png";
import markerIcon2x from "leaflet/dist/images/marker-icon-2x.png";
import markerShadow from "leaflet/dist/images/marker-shadow.png";
import L from "leaflet";

L.Icon.Default.mergeOptions({
  iconUrl: markerIcon,
  iconRetinaUrl: markerIcon2x,
  shadowUrl: markerShadow,
});
```
Do this once in your map setup module, before any markers are created.

**Phase:** Same phase as map introduction. Include in the Leaflet setup utility.

**Sources:** [Leaflet #7424](https://github.com/Leaflet/Leaflet/issues/7424), [Leaflet #6247](https://github.com/Leaflet/Leaflet/issues/6247) — HIGH confidence

---

### Pitfall 3: Missing Leaflet CSS import produces gray/shattered tiles

**What goes wrong:** The map area renders as a gray box, or tiles load but appear scattered/misaligned across the container. The map is technically working but visually broken.

**Why it happens:** Leaflet CSS (`leaflet/dist/leaflet.css`) handles tile positioning, zoom controls, and container layout. Without it, tiles render at wrong positions. Unlike CDN-loaded Leaflet (which the existing `frontend/index.html` uses), bundled Leaflet requires an explicit CSS import.

**Warning signs:**
- Gray rectangle where the map should be
- Tiles visible but overlapping or offset
- Zoom controls missing or unstyled

**Prevention:**
- Import `leaflet/dist/leaflet.css` in your map component or `main.tsx`
- Set explicit height on the map container (Leaflet requires a pixel/viewport height, not `auto`)
- Call `map.invalidateSize()` after the container becomes visible (relevant for tabbed UIs where the map starts hidden)

**Phase:** Map component foundation phase. This is a setup-time checklist item.

**Sources:** [react-leaflet #1108](https://github.com/PaulLeCam/react-leaflet/issues/1108), [react-leaflet #156](https://github.com/PaulLeCam/react-leaflet/issues/156) — HIGH confidence

---

### Pitfall 4: Nominatim rate limiting blocks production autocomplete

**What goes wrong:** Address autocomplete stops working in production. Users see no suggestions. The public Nominatim API returns HTTP 429 or silently drops requests.

**Why it happens:** Nominatim's public API enforces **max 1 request/second** and ~2,500 requests/day. A popular landing page with type-ahead autocomplete easily exceeds this. Nominatim also requires a custom `User-Agent` header — generic agents get deprioritized or blocked.

**Warning signs:**
- Autocomplete works in dev, fails in production under load
- Intermittent 429 errors in network tab
- Autocomplete "sometimes works, sometimes doesn't"

**Prevention:**
- **Debounce aggressively:** 300ms minimum, 500ms recommended for Nominatim
- **Minimum character threshold:** Don't query until 3+ characters typed (already in existing code)
- **Client-side result caching:** Cache recent queries in a Map to avoid duplicate requests
- **Proxy through FastAPI backend:** Add a `/api/geocode` endpoint that rate-limits, caches, and sets proper `User-Agent`
- **Set a custom User-Agent:** Include app name and contact email per Nominatim policy
- **Plan for fallback:** If the app scales, budget for LocationIQ or OpenCage (Nominatim-compatible APIs with higher limits)

**Phase:** Address autocomplete implementation phase. The proxy/caching architecture should be designed upfront, not bolted on later.

**Sources:** [Nominatim Usage Policy](https://operations.osmfoundation.org/policies/nominatim/) — HIGH confidence

---

### Pitfall 5: Race conditions in autocomplete + reverse geocode

**What goes wrong:** Stale autocomplete results overwrite newer results. User types "Madrid", results for "Mad" arrive after "Madrid" results and replace them. Or: user clicks map while a previous reverse geocode is in-flight, and the old result overwrites the new click.

**Why it happens:** Async network requests don't complete in order. Without request tracking, the last response to arrive wins, regardless of which request was most recent.

**Warning signs:**
- Suggestions flicker or change after appearing to settle
- Map click shows wrong address momentarily then corrects
- Selected address doesn't match what user clicked

**Prevention:**
- Use an incrementing request ID (the existing vanilla JS code does this correctly with `requestId`)
- In React, use an `AbortController` per request and cancel it on new input
- For the autocomplete hook: abort previous fetch when a new keystroke triggers a new query
- For map click reverse geocode: abort any pending geocode when a new click arrives

```tsx
const controllerRef = useRef<AbortController>();

async function search(query: string) {
  controllerRef.current?.abort();
  controllerRef.current = new AbortController();
  const result = await fetch(url, { signal: controllerRef.current.signal });
  // ...
}
```

**Phase:** Autocomplete implementation phase. Must be built into the hook from the start, not patched later.

**Sources:** Verified pattern from existing codebase + [Leaflet reverse geocode SO](https://stackoverflow.com/questions/55059844/leaflet-reverse-geocode) — HIGH confidence

---

## Moderate Pitfalls

### Pitfall 6: Mobile touch scroll trapped by Leaflet map

**What goes wrong:** On mobile devices, users can't scroll past the map. Their finger touches the map container and Leaflet captures the gesture for panning, blocking page scroll.

**Prevention:**
- Disable `dragging` on mobile by default: `dragging: !L.Browser.mobile`
- Disable `tap: false` to prevent touch capture when dragging is off
- Disable `scrollWheelZoom` (already done in existing code)
- Add a "tap to interact" overlay that enables map interaction on deliberate gesture
- Consider `gestureHandling` plugin for Google Maps-like two-finger scroll behavior

**Phase:** Map component phase. This is a mobile UX requirement, not a nice-to-have.

**Sources:** [Leaflet #2031](https://github.com/Leaflet/Leaflet/issues/2031), [Leaflet #4677](https://github.com/Leaflet/Leaflet/issues/4677) — HIGH confidence

---

### Pitfall 7: Custom stepper (- NUM +) fails accessibility audit

**What goes wrong:** Custom `<button> - </button> <span>3</span> <button> + </button>` steppers are visually clear but inaccessible. Screen readers can't identify the control's purpose, keyboard users can't increment/decrement, and voice control can't target buttons with "-" and "+" labels.

**Prevention:**
- Use `role="spinbutton"` with `aria-valuenow`, `aria-valuemin`, `aria-valuemax`
- Support keyboard: Up/Down arrows to increment/decrement, Home/End for min/max
- Add `aria-label` to buttons: "Disminuir habitaciones" / "Aumentar habitaciones" (Spanish)
- Use `tabindex="-1"` on +/- buttons (keyboard users use arrows on the input instead)
- Announce value changes with `aria-live="polite"` region
- Consider using React Aria's `useNumberField` hook as the foundation — it handles all WCAG requirements

**Phase:** Form components phase. Build accessible from the start; retrofitting ARIA is error-prone.

**Sources:** [W3C Spin Button APG](https://www.w3.org/WAI/ARIA/apg/patterns/spinbutton/examples/quantity-spinbutton/), [React Aria NumberField](https://react-aria.adobe.com/NumberField) — HIGH confidence

---

### Pitfall 8: Leaflet map invisible in hidden tabs (zero-height container)

**What goes wrong:** If the map is in a tab that isn't visible on initial render (e.g., the existing `TabBarLayout` renders content conditionally), Leaflet calculates tile positions based on a 0×0 container. When the tab becomes visible, tiles are misaligned or missing.

**Prevention:**
- Call `map.invalidateSize()` when the map's container becomes visible
- In React, trigger this via a `useEffect` that watches the active tab state
- Alternative: lazy-mount the map component only when its tab is active (unmount when hidden)
- The existing vanilla code already calls `setTimeout(() => map.invalidateSize(), 0)` — the React version needs an equivalent tied to visibility

**Phase:** Map component phase. Must be handled if the map lives inside any conditionally-rendered container.

**Sources:** [react-leaflet #1108](https://github.com/PaulLeCam/react-leaflet/issues/1108) — HIGH confidence

---

### Pitfall 9: React 19 form actions clear uncontrolled inputs on submission

**What goes wrong:** After form submission, all uncontrolled input values reset to empty. If the submission fails (validation error, network error), the user loses everything they typed.

**Why it happens:** React 19 aligns with MPA form behavior — successful action submission clears the form. This also affects failed submissions if you're using `<form action={serverAction}>`.

**Prevention:**
- Use controlled components for all form inputs (value + onChange in state)
- Or: return `formData` from the action and use it as `defaultValue` on re-render
- For this project: controlled components are recommended since form state needs to sync with the map (selected address) and steppers (bed/bath counts)

**Phase:** Form architecture phase. The controlled vs. uncontrolled decision must be made upfront.

**Sources:** [React #31649](https://github.com/facebook/react/issues/31649) — HIGH confidence

---

### Pitfall 10: OSM tile URL uses deprecated subdomain pattern

**What goes wrong:** Map tiles load slowly or inconsistently because the tile URL uses the old `{s}.tile.openstreetmap.org` subdomain pattern, which is deprecated.

**Prevention:**
- Use the single canonical URL: `https://tile.openstreetmap.org/{z}/{x}/{y}.png`
- Do not use `a.tile.openstreetmap.org`, `b.tile.openstreetmap.org` variants
- The existing `frontend/js/address-picker.js` uses the old `{s}` pattern — do not copy this into the React version
- Always use HTTPS to avoid mixed-content blocking

**Phase:** Map component phase. A one-line fix if caught early, a confusing debug session if not.

**Sources:** [OSM Operations #737](https://github.com/openstreetmap/operations/issues/737), [OSM Tile Policy](https://operations.osmfoundation.org/policies/tiles/) — HIGH confidence

---

## Minor Pitfalls

### Pitfall 11: Suggestion dropdown z-index war with map tiles

**What goes wrong:** The autocomplete dropdown renders behind Leaflet map tiles or controls. Leaflet uses high z-index values internally (tiles at 200, controls at 800+).

**Prevention:**
- Set autocomplete dropdown to `z-index: 1000` or higher
- Use a portal (`createPortal`) if the dropdown is inside a stacking context that constrains it
- Test with the map positioned directly below the address input (the layout in `frontend/index.html`)

**Phase:** Autocomplete UI phase.

---

### Pitfall 12: Nominatim returns inconsistent address structures by country

**What goes wrong:** Spanish addresses from Nominatim have different field names than expected. `address.city` might be empty while `address.town` or `address.village` has the value. Province/municipality extraction logic breaks silently.

**Prevention:**
- Never rely on a single field for municipality: check `city || town || village || hamlet` in order
- Parse the `display_name` as a fallback
- Test with rural and urban Spanish addresses (Madrid vs. small pueblo)
- The existing backend `geocoder.py` likely handles this — reuse its parsing logic via the API rather than reimplementing client-side

**Phase:** Autocomplete implementation phase.

---

### Pitfall 13: Form submission blocks UI without loading state

**What goes wrong:** The valuation request hits the FastAPI backend, which triggers a Playwright scrape of Idealista. This takes 15-60+ seconds. Without proper loading state, users think the page is broken and resubmit or leave.

**Prevention:**
- Show an immediate loading indicator on submit (the existing vanilla UI does this well with a spinner + progress messages)
- Disable the submit button during request
- Show progress messages if the backend supports streaming/SSE
- Set a generous client-side timeout (90+ seconds) and show "still searching" messages after 15s and 30s
- Consider `useTransition` or `isPending` from React 19 for the loading state

**Phase:** Form submission phase. The UX pattern already exists in the vanilla frontend — port it.

---

## Technical Debt Patterns

| Pattern | How It Starts | Where It Leads | Prevention |
|---------|---------------|----------------|------------|
| Leaflet state outside React | Direct `L.map()` calls in useEffect with manual cleanup | Memory leaks, stale references, broken hot reload | Use react-leaflet's declarative components (`MapContainer`, `Marker`, `TileLayer`) |
| Duplicated geocoding logic | Client-side Nominatim calls + backend Nominatim calls | Two rate-limited consumers, inconsistent parsing | Single geocoding proxy endpoint in FastAPI |
| Inline map configuration | Tile URL, zoom levels, bounds hardcoded in components | Can't switch tile providers or adjust per-environment | Extract map config to a constants file |
| Mixed controlled/uncontrolled | Address input controlled (synced to map), others uncontrolled | Inconsistent state management, form reset bugs | Decide controlled for all inputs from day one |

## Integration Gotchas

| Integration | Gotcha | Mitigation |
|-------------|--------|------------|
| react-leaflet + Tailwind | Tailwind's CSS reset (`preflight`) strips Leaflet control styling | Add `leaflet/dist/leaflet.css` import AFTER Tailwind's base styles, or scope Leaflet CSS to the map container |
| shadcn/ui + custom stepper | shadcn has no built-in number stepper component | Build a custom stepper using shadcn's `Button` for +/- and `Input` for the value, wrapping React Aria's `useNumberField` for accessibility |
| Nominatim + Spanish addresses | Spanish-specific fields (`comunidad_autonoma`, `provincia`) may not map to Nominatim's standard `state`/`county` | Parse `address.state` for comunidad, `address.county` or `address.province` for provincia |
| Leaflet + React 19 refs | `useRef` callback refs changed behavior in React 19 (cleanup function return) | Use `MapContainer` from react-leaflet v5 which handles ref lifecycle correctly |
| FastAPI backend + long requests | Playwright scraping takes 15-60s; default fetch timeout may abort | Set `signal` with `AbortSignal.timeout(120_000)` on the fetch call |

## UX Pitfalls

| Issue | Impact | Fix |
|-------|--------|-----|
| No feedback on map click | User clicks map, nothing visible happens until geocode completes (~1s) | Show an immediate temporary marker at click position, replace with final marker after geocode |
| Stepper allows 0 bedrooms | User decrements below valid range | Enforce `min={1}` for bedrooms, `min={1}` for bathrooms; disable the minus button at minimum |
| Address input loses focus on suggestion click | Click on suggestion triggers blur, which hides suggestions before the click registers | Use `onMouseDown` with `preventDefault()` on suggestions, or delay hiding by 150ms (existing code uses 120ms setTimeout) |
| Map covers fold on mobile | Large map pushes the form below the viewport | Set map height responsively: `h-40 md:h-64`; on mobile the map is supplementary, not primary |
| No empty state for autocomplete loading | User types and waits with no visual feedback | Show a skeleton/spinner in the dropdown while fetching (existing code shows "Buscando direcciones…") |

## "Looks Done But Isn't" Checklist

- [ ] **Map works in production build** — Dev mode may hide Strict Mode double-init issues; test with `vite build && vite preview`
- [ ] **Marker icons render in production** — Vite's asset hashing changes paths; verify markers appear after `vite build`
- [ ] **Autocomplete works with real Nominatim** — Mock data in dev doesn't hit rate limits; test with the real API under realistic typing patterns
- [ ] **Mobile scroll works past the map** — Test on a real device, not just Chrome DevTools responsive mode
- [ ] **Tab switch re-renders map correctly** — Switch away from the map tab and back; tiles should not be misaligned
- [ ] **Form preserves state on failed submission** — Trigger a network error mid-submit; all fields should retain their values
- [ ] **Stepper keyboard navigation works** — Tab to stepper, use arrow keys; value should increment/decrement
- [ ] **Back button doesn't lose form state** — Navigate away and back; consider persisting form state to sessionStorage
- [ ] **Address + map stay in sync** — Type an address, select suggestion, then click map elsewhere; both the input text and selected-address box should update
- [ ] **Spanish characters render correctly** — Test with "Calle Ñoño, Alcázar" — no mojibake in the address display or API calls
- [ ] **HTTPS tile URL in production** — Verify no mixed-content warnings in browser console

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Map component setup | Double-init in Strict Mode, missing CSS, broken markers | Use react-leaflet v5, import CSS, configure icons explicitly |
| Address autocomplete | Rate limiting, race conditions, dropdown z-index | Debounce 500ms, AbortController, z-index ≥ 1000 |
| Custom form controls | Accessibility failures, uncontrolled state bugs | Use React Aria hooks, controlled components throughout |
| Form → backend submission | Long request timeout, no loading feedback, lost state on error | 120s timeout, progress UI, controlled inputs |
| Mobile optimization | Map traps scroll, oversized map, touch target size | Disable map dragging on mobile, responsive heights, 44px min touch targets |
| Production deployment | Broken markers, tile URL issues, rate limit discovery | Full `vite build` + `vite preview` QA pass |

## Sources

- [react-leaflet #1133 — Map container already initialized](https://github.com/PaulLeCam/react-leaflet/issues/1133) (React 19 Strict Mode)
- [Leaflet #7424 — Default marker icon with Webpack](https://github.com/Leaflet/Leaflet/issues/7424)
- [Leaflet #6247 — Icon URL replaced by Webpack](https://github.com/Leaflet/Leaflet/issues/6247)
- [react-leaflet #1108 — Map rendered with missing parts](https://github.com/PaulLeCam/react-leaflet/issues/1108)
- [Nominatim Usage Policy](https://operations.osmfoundation.org/policies/nominatim/)
- [OSM Tile Usage Policy](https://operations.osmfoundation.org/policies/tiles/)
- [OSM Operations #737 — Preferred tile URL](https://github.com/openstreetmap/operations/issues/737)
- [Leaflet #2031 — Touch scroll conflict](https://github.com/Leaflet/Leaflet/issues/2031)
- [Leaflet #4677 — Mobile scroll blocked](https://github.com/Leaflet/Leaflet/issues/4677)
- [W3C Spin Button APG](https://www.w3.org/WAI/ARIA/apg/patterns/spinbutton/examples/quantity-spinbutton/)
- [React Aria NumberField](https://react-aria.adobe.com/NumberField)
- [React #31649 — Form action clears inputs](https://github.com/facebook/react/issues/31649)
