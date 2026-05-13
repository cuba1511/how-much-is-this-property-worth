# Phase 1: Foundation + Branded Shell - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-13
**Phase:** 1-Foundation + Branded Shell
**Areas discussed:** Hero visual style, Page shell & layout, Form area presence, Foundation code scope

---

## Hero Section Visual Style

| Option | Description | Selected |
|--------|-------------|----------|
| Full-width colored banner | Gradient or solid-color background spanning full viewport width | |
| Clean white with accent elements | White bg, blue accent on headline, subtle tint sections, orange CTA | ✓ |
| Background illustration/pattern | Decorative SVG or image pattern behind hero content | |

**User's choice:** Claude's recommendation (clean white with accents) — user delegated all decisions
**Notes:** User said "can take decisions" — approved Claude's recommendations for all areas in a single confirmation.

---

## Page Shell & Layout

| Option | Description | Selected |
|--------|-------------|----------|
| Keep TabBar navigation | Reuse existing mobile tab layout, form in one tab | |
| Simple scroll layout | Remove tabs, single-page scroll: hero → form section | ✓ |
| Header + footer frame | Add persistent nav header and footer around content | |

**User's choice:** Claude's recommendation (simple scroll layout, no tabs)
**Notes:** Single-purpose landing page doesn't need navigation.

---

## Form Area Presence

| Option | Description | Selected |
|--------|-------------|----------|
| No form hint | Pure hero + branding only, form added from scratch in later phases | |
| Visible card container | Styled section/card placeholder where form components mount | ✓ |
| Skeleton/wireframe preview | Show greyed-out input placeholders as preview of coming form | |

**User's choice:** Claude's recommendation (visible card container)
**Notes:** Gives phases 2-4 a clear integration point without looking incomplete.

---

## Foundation Code Scope

| Option | Description | Selected |
|--------|-------------|----------|
| Defer all to Phase 4 | No types/schemas until form is actually built | |
| Types + schema + API client now | Set up thin foundation (types.ts, schemas.ts, api.ts) | ✓ |
| Full form infrastructure | Types + schemas + react-hook-form setup + validation | |

**User's choice:** Claude's recommendation (thin foundation now)
**Notes:** Lightweight setup prevents rework without over-engineering.

---

## Claude's Discretion

- Exact spacing/padding/responsive breakpoints in hero section
- CTA button label copy (Spanish)
- Whether to include subtitle paragraph below headline

## Deferred Ideas

None — discussion stayed within phase scope.
