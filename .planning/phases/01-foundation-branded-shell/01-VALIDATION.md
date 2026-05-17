---
phase: 1
slug: foundation-branded-shell
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-13
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | vitest |
| **Config file** | frontend/vite.config.ts (vitest inline config or separate vitest.config.ts) |
| **Quick run command** | `cd frontend && npx vitest run --reporter=verbose` |
| **Full suite command** | `cd frontend && npx vitest run` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd frontend && npx vitest run --reporter=verbose`
- **After every plan wave:** Run `cd frontend && npx vitest run`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 1-01-01 | 01 | 1 | BRAND-01 | — | N/A | visual | `cd frontend && npx vite build` | ❌ W0 | ⬜ pending |
| 1-01-02 | 01 | 1 | BRAND-02 | — | N/A | visual | `cd frontend && npx vite build` | ❌ W0 | ⬜ pending |
| 1-01-03 | 01 | 1 | BRAND-04 | — | N/A | visual | `cd frontend && npx vite build` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Vitest installed as dev dependency if not already present
- [ ] Basic test config in vite.config.ts or vitest.config.ts

*Existing infrastructure covers most phase requirements — this phase is primarily visual/UI.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| PropHero branding visible on page load | BRAND-01 | Visual branding check | Open http://localhost:5173, verify headline "¿Cuánto vale tu casa?" with PropHero colors |
| Design tokens applied | BRAND-02 | Visual token check | Inspect page elements for electric blue, cyan, orange CTA, Inter font |
| All UI text in Spanish | BRAND-04 | Language check | Review all visible text on page — no English strings |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
