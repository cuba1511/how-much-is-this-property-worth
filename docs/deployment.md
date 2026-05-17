# Deploy en un VPS (recomendado)

Un solo servidor: **Caddy** (HTTPS + React estático) + **FastAPI** + **SQLite**.

Coste orientativo: **~€4–6/mes** (Hetzner CX23 o similar). Sin Vercel ni Railway.

```text
Usuario → https://tu-dominio.com
              ├─ /          → frontend/dist (React)
              └─ /api/*     → FastAPI :8000
              SQLite → volumen Docker /data
```

---

## 1. Contratar el VPS

1. [Hetzner Cloud](https://www.hetzner.com/cloud) (o DigitalOcean, etc.).
2. Servidor **Ubuntu 24.04**, mínimo **2 vCPU / 4 GB RAM** (Playwright PDF).
3. Anota la **IP pública**.

---

## 2. Preparar el servidor (una vez)

SSH como root o usuario con sudo:

```bash
apt update && apt upgrade -y
apt install -y git docker.io docker-compose-v2
systemctl enable --now docker
```

Opcional: usuario `deploy` + clave SSH, firewall solo 22/80/443.

---

## 3. Clonar el repo y secrets

```bash
git clone https://github.com/TU_ORG/how-much-is-this-property-worth.git
cd how-much-is-this-property-worth
cp deploy/env.example deploy/.env
nano deploy/.env
```

| Variable | Ejemplo | Notas |
|----------|---------|--------|
| `SITE_ADDRESS` | `valoracion.tudominio.com` | Antes de DNS: `:80` (solo HTTP por IP) |
| `ACME_EMAIL` | `tu@email.com` | Obligatorio con dominio real (Let's Encrypt) |
| `BRIGHT_DATA_CDP` | `wss://brd-customer-...` | Igual que `backend/.env` local |
| `RESEND_API_KEY` | `re_...` | Opcional (email informes) |
| `RESEND_FROM_EMAIL` | `PropHero <noreply@...>` | Si usas Resend |
| `HV_API_KEY` | | Opcional (Apps Script) |

No hace falta `CORS_ORIGINS` ni `VITE_API_URL` en producción VPS (mismo origen).

---

## 4. DNS (cuando tengas dominio)

En tu registrador, registro **A**:

| Nombre | Valor |
|--------|--------|
| `@` o `app` | IP del VPS |

Espera propagación (minutos–horas). Luego en `deploy/.env`:

```env
SITE_ADDRESS=valoracion.tudominio.com
ACME_EMAIL=tu@email.com
```

---

## 5. Primer deploy

En el VPS, dentro del repo:

```bash
chmod +x scripts/vps-deploy.sh
./scripts/vps-deploy.sh
```

O con Make (si tienes Node en el servidor):

```bash
make install   # solo si quieres dev local; en VPS basta Node para build
# En VPS mínimo: apt install -y nodejs npm  (o nvm)
make vps-up
```

El script:

1. `npm run build` en `frontend/` (usa `frontend/.env.production` → API en mismo host).
2. `docker compose up -d --build` (API + Caddy).

**Comprobar:**

```bash
curl -sS http://127.0.0.1/health
# o https://tu-dominio.com/health
```

Abre el dominio en el navegador y prueba una valoración completa.

---

## 6. Actualizar tras `git pull`

```bash
git pull
./scripts/vps-deploy.sh
```

---

## 7. Comandos útiles

```bash
docker compose --env-file deploy/.env logs -f api    # API
docker compose --env-file deploy/.env logs -f caddy
docker compose --env-file deploy/.env ps
make vps-down   # parar
```

**Backup SQLite** (leads/valoraciones):

```bash
docker compose --env-file deploy/.env exec api \
  cp /data/prophero.db /data/prophero.db.bak.$(date +%F)
# o copiar el volumen: docker volume inspect ...
```

---

## Probar en tu Mac (sin VPS)

```bash
cp deploy/env.example deploy/.env
# SITE_ADDRESS=:80
echo "BRIGHT_DATA_CDP=..." >> deploy/.env   # tu secret real
make vps-up
open http://127.0.0.1
```

---

## Costes (solo infra)

| Concepto | €/mes aprox. |
|----------|----------------|
| Hetzner CX23 (4 GB) | 4–5 |
| Dominio | ~1 (anual/12) |
| Bright Data / Resend | según uso (igual en cualquier opción) |

---

## Alternativa: Vercel + Railway

Si más adelante prefieres no administrar el servidor, ver commits con `railway.toml` y `frontend/vercel.json`. En Vercel define `VITE_API_URL=https://tu-api.railway.app`.

Para este proyecto, **VPS único** suele ser más barato y más simple operativamente a medio plazo.
