# Project structure

## Carpetas que importan

| Path | Qué es |
|------|--------|
| `backend/` | API FastAPI, scraping, valoración, SQLite, PDF/email |
| `frontend/` | **UI de producción** — React + Vite + Tailwind + shadcn |
| `legacy/old-frontend/` | HTML viejo — solo referencia, no se ejecuta |
| `tests/evaluation/` | Harness de calibración vs CSV de tasadores |
| `apps-script/` | Integración Google Apps Script |
| `docs/` | Docs de arquitectura y pipelines |
| `design-tokens/` | Export JSON de Figma (referencia; los tokens activos están en `frontend/src/index.css`) |

## Cosas en la raíz — qué hacer con cada una

| Item | Estado | Acción |
|------|--------|--------|
| `.env.example` | ✅ Canónico | Plantilla de secrets del **backend** |
| `backend/.env` | ✅ Usar este | Creado por `make install`; el API lee **solo** este archivo |
| `.env` (raíz) | ⚠️ Suelto / legacy | Si lo usabas antes: **copia el contenido a `backend/.env`** y borra el de la raíz para no tener dos sitios |
| `venv/` (raíz) | ❌ No usar | El Makefile usa `backend/.venv`. Si reaparece, bórralo: `rm -rf venv` |
| `backend/.venv/` | ✅ Python del proyecto | `make install` |
| `.planning/` | Interno GSD | Planes de fases; no afecta `make dev` |
| `.cursor/` | IDE | Reglas y skills de Cursor |
| `design-tokens/` | Referencia diseño | JSON de Figma; gitignored |

## Ya no existe

- **`frontend2/`** — Renombrado a `frontend/` (commit `a08a7e2`).

## Arrancar en local

```bash
make install   # venv + npm + playwright + backend/.env
make db
make dev       # API :8001 + Vite :5173
```

**Frontend:** `frontend/.env` con `VITE_API_URL=http://localhost:8001` (ver `frontend/.env.example`).

**Backend:** variables en `backend/.env` (Bright Data, Resend, `HV_API_KEY`, etc.).

## Dentro de `frontend/` (ruido normal)

| Path | Qué es |
|------|--------|
| `frontend/.agents/` | Skills de shadcn para el agente; no es código de la app |
| `frontend/node_modules/` | Dependencias npm (gitignored) |
| `frontend/.vite/` | Caché de Vite (gitignored) |
