# Deploy en un VPS / EC2 (recomendado)

Un solo servidor: **Caddy** (HTTPS + React estático) + **FastAPI** + **SQLite**.

Coste orientativo: **~€4–6/mes** (Hetzner CX23, AWS EC2 `t3.small`, etc.). Sin Vercel ni Railway.

**CI/CD:** push a `main` → [`.github/workflows/deploy-ec2.yml`](../.github/workflows/deploy-ec2.yml) (SSH + `docker compose`).

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

SSH como root o usuario con sudo (Ubuntu 24.04 en Hetzner o **AWS EC2**):

```bash
apt update && apt upgrade -y
apt install -y git docker.io docker-compose-v2 curl
systemctl enable --now docker

# Node 22 — build del frontend en el servidor (usado por vps-deploy.sh / Actions)
curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
apt install -y nodejs
```

**EC2:** Security Group con inbound **22, 80, 443** (tu IP en 22 si puedes). Asocia la IP elástica; en Namecheap, registro **A** → esa IP.

Opcional: usuario `ubuntu` + clave `.pem` (contenido → secret `EC2_SSH_KEY` en GitHub).

---

## 3. Clonar el repo en EC2 (una vez)

```bash
git clone git@github.com:TU_ORG/how-much-is-this-property-worth.git
cd how-much-is-this-property-worth
```

**No crees `deploy/.env` en el servidor.** Los secrets van en GitHub (sección siguiente).

Instala en la instancia: Docker, docker compose, Node 20+ (build del frontend), git.

| Variable | Dónde | Notas |
|----------|--------|--------|
| `SITE_ADDRESS` | GitHub var/secret | Dominio sin `https://`. Antes de DNS: `:80` |
| `ACME_EMAIL` | GitHub var/secret | Let's Encrypt |
| `BRIGHT_DATA_CDP` | GitHub **secret** | Igual que local |
| `RESEND_*`, `HV_API_KEY` | GitHub **secret** | Opcional |

No hace falta `CORS_ORIGINS` ni `VITE_API_URL` (mismo origen).

---

## 4. DNS (cuando tengas dominio)

En tu registrador, registro **A**:

| Nombre | Valor |
|--------|--------|
| `@` o `app` | IP del VPS |

Espera propagación. Configura `SITE_ADDRESS` y `ACME_EMAIL` en GitHub (abajo).

---

## 5. GitHub Actions → EC2 (deploy automático)

Workflow: `.github/workflows/deploy-ec2.yml`  
Trigger: push a `main` o **Run workflow** manual.

### Environment `production`

Repo → **Settings → Environments → production** → Add secret / variable.

Lista completa en `deploy/env.example`.

| Name | Tipo | Uso |
|------|------|-----|
| `EC2_HOST` | secret | IP o hostname de la instancia |
| `EC2_USER` | secret | `ubuntu` (Amazon Linux: `ec2-user`) |
| `EC2_SSH_KEY` | secret | Contenido del `.pem` (private key) |
| `EC2_APP_DIR` | secret | Ruta del clone, ej. `/home/ubuntu/how-much-is-this-property-worth` |
| `SITE_ADDRESS` | variable o secret | Dominio para Caddy |
| `ACME_EMAIL` | variable o secret | Email Let's Encrypt |
| `BRIGHT_DATA_CDP` | secret | Bright Data |
| `BRIGHT_DATA_API_KEY` | secret | Opcional |
| `RESEND_API_KEY` | secret | Opcional |
| `RESEND_FROM_EMAIL` | variable o secret | Opcional |
| `HV_API_KEY` | secret | Opcional |

Flujo:

1. Actions exporta secrets/vars en el job.
2. `appleboy/ssh-action` las pasa al shell remoto (`envs:`).
3. En EC2: `git pull` → `./scripts/vps-deploy.sh` → `docker compose up` lee **el entorno del shell**, no ningún fichero `.env`.

### Primer deploy manual en EC2 (opcional)

Solo si quieres probar sin Actions — exporta variables en la sesión SSH:

```bash
export SITE_ADDRESS=valoracion.tudominio.com
export ACME_EMAIL=tu@email.com
export BRIGHT_DATA_CDP='wss://...'
./scripts/vps-deploy.sh
```

### Comprobar

```bash
curl -sS https://tu-dominio.com/health
```

---

## 6. Comandos útiles en EC2

```bash
docker compose logs -f api
docker compose logs -f caddy
docker compose ps
```

**Backup SQLite:**

```bash
docker compose exec api cp /data/prophero.db /data/prophero.db.bak.$(date +%F)
```

---

## Probar en tu Mac (Docker local)

```bash
export SITE_ADDRESS=:80
export ACME_EMAIL=dev@local.test
export BRIGHT_DATA_CDP='wss://...'
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
