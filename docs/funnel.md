# Funnel — métricas del producto

Qué medimos, dónde vive cada dato y cómo se calcula. Este doc es el contrato
de medición: si un evento no aparece aquí, no lo estamos contando.

## Etapas del funnel

```
[1] Report enviado ─► [2] Respuesta cliente ─► [3] Llamada agendada
                                                       │
                                                       ▼
                              [5] Desinversión ◄─ [4] Llamada realizada
                                       │
                                       ▼
                                [6] Repeat buy
```

Cada etapa tiene un evento atómico, una fuente de verdad única y un timestamp
en UTC. Las etapas son monótonas: un lead solo avanza, nunca retrocede. Si un
cliente cae fuera, la etapa última alcanzada queda fija.

## Definiciones

| # | Métrica | Evento que cuenta | Fuente de verdad | Estado actual |
|---|---------|-------------------|------------------|---------------|
| 1 | **Reports enviados** | Email con PDF entregado por Resend (HTTP 200 a `/emails`) | `valuations.email_sent_at IS NOT NULL` (SQLite) | ✅ Instrumentado — ver [`email-report.md`](./email-report.md) |
| 2 | **Respuestas de clientes** | El lead responde al email del report (reply o click en CTA "Hablar con un coach") | Resend webhook (`email.replied`) o landing de CTA con `lead_id` | ❌ Pendiente |
| 3 | **Llamadas agendadas** | El lead reserva slot en el calendario del coach | Webhook del proveedor de scheduling (Cal.com / Calendly / Google Calendar) | ❌ Pendiente |
| 4 | **Llamadas realizadas** | El coach marca la call como realizada (no no-show) | Airtable `Calls` table o columna en `Transactions` (`first_call_at`) | ❌ Pendiente |
| 5 | **Desinversiones** | El cliente vende una propiedad gestionada por PropHero | Airtable — nueva `Stage = "Property sold"` o columna `divested_at` en `Transactions` | ❌ Pendiente |
| 6 | **Repeat buys** | Un cliente con ≥1 transacción cerrada compra otra propiedad | Airtable `Transactions` agrupadas por `Client` con `count(stage="Property leased") ≥ 2` | ❌ Pendiente |

## KPIs derivados

Conversion rates entre etapas — el output que mira el equipo:

| KPI | Cálculo | Pregunta de negocio |
|-----|---------|---------------------|
| `report_to_reply_rate` | (2) / (1) | ¿El report es lo bastante interesante para responder? |
| `reply_to_call_booked_rate` | (3) / (2) | ¿El CTA de reserva funciona? |
| `call_show_up_rate` | (4) / (3) | ¿La gente que agenda llega? |
| `call_to_close_rate` | nuevas filas en `Transactions` con `Stage="Property leased"` / (4) | ¿Las calls convierten a operaciones? |
| `divestment_rate` | (5) / cierres totales | ¿Cuánta gente desinvierte y en qué horizonte? |
| `repeat_buy_rate` | (6) / clientes con ≥1 cierre | LTV proxy — ¿vuelven? |

Cada KPI necesita ventana temporal explícita (`last_30d`, `last_90d`, `ytd`).
Sin ventana el número no significa nada.

## Esquema mínimo (propuesto)

Tabla nueva en SQLite para los eventos 1–4 (lo que toca al lead pre-coach).
Las etapas 5 y 6 viven en Airtable porque dependen del ciclo post-cierre que
ya gestionan los coaches allí.

```sql
CREATE TABLE funnel_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER NOT NULL REFERENCES leads(id),
    stage TEXT NOT NULL,            -- 'report_sent' | 'reply_received'
                                    -- | 'call_booked' | 'call_completed'
    occurred_at TEXT NOT NULL,      -- ISO 8601 UTC
    source TEXT NOT NULL,           -- 'resend' | 'cal.com' | 'manual' | …
    metadata TEXT,                  -- JSON con payload original (opcional)
    created_at TEXT NOT NULL
);

CREATE INDEX idx_funnel_events_lead_stage
  ON funnel_events(lead_id, stage);
```

Reglas:

- **Append-only**, igual que `leads` y `valuations`. Si un evento llega
  duplicado (webhook reentregado), se inserta otra fila — la deduplicación
  se hace en consulta con `MIN(occurred_at) GROUP BY (lead_id, stage)`.
- `source` documenta de dónde vino el evento. Si mañana cambiamos de
  Cal.com a Calendly, los datos viejos siguen siendo legibles.
- `metadata` guarda el payload original para forenses sin acoplar el
  schema a un proveedor concreto.

## De dónde sale cada evento

### (1) Report enviado — ya existe

`backend/main.py` → `BackgroundTask` → `db.mark_email_sent(valuation_id)` →
escribe `valuations.email_sent_at`. Cuando creemos `funnel_events`, el mismo
background task debe insertar también `funnel_events(stage='report_sent')`
con `source='resend'`. Atómico: si Resend devuelve 2xx, se escriben las dos
columnas en la misma transacción.

### (2) Respuesta cliente — pendiente

Dos señales válidas:

1. **Reply al email** — Resend webhook `email.replied`. Configurar en el
   dashboard de Resend apuntando a `POST /api/webhooks/resend` (a crear).
   Match contra `lead_id` por el `Reply-To` o un header custom
   `X-PropHero-Lead-Id` que añadimos al enviar.
2. **Click en CTA "Hablar con un coach"** — landing con query string
   `?lead_id=<id>&utm_source=report_email`. La página llama a
   `POST /api/funnel/cta-click` antes de redirigir al booking.

Cualquiera de las dos cuenta como `reply_received`. El primero que llegue
gana — los siguientes se ignoran en el cálculo del KPI (pero se persisten).

### (3) Llamada agendada — pendiente

Webhook del proveedor de scheduling. Decisión pendiente entre:

- **Cal.com** (open source, self-hostable, webhook nativo `BOOKING_CREATED`).
- **Calendly** (más extendido pero el webhook está en el plan pago).
- **Google Calendar API** (gratis pero hay que construir la UI de booking).

Recomendación: empezar con Cal.com hosted, mover a self-host si el volumen
lo justifica. Webhook → `POST /api/webhooks/scheduling` →
`funnel_events(stage='call_booked', source='cal.com')`.

### (4) Llamada realizada — pendiente

No hay un evento automático bueno (Zoom/Meet no distinguen no-show de
llamada efectiva con fiabilidad). El coach marca un checkbox en Airtable
después de la call: columna `First call completed` (boolean) o
`first_call_at` (datetime).

Sync periódico (cada 15 min via cron / Apps Script) lee Airtable y hace
upsert en `funnel_events(stage='call_completed', source='airtable')`. El
match lead↔transaction se hace por email — el coach ya tiene esta info en
Airtable porque el lead llega ahí desde el report.

### (5) Desinversiones — Airtable

Se mide directamente sobre `Transactions`:

- Añadir columna `Divested at` (datetime) y `Divestment reason` (single select).
- El KPI se calcula con un query Airtable filtrado por `Divested at IS NOT EMPTY`.
- No replicamos esto a SQLite — Airtable es la fuente de verdad operativa
  del coach (ver [`coach-transactions.md`](./coach-transactions.md)).

### (6) Repeat buys — Airtable

Mismo origen. Query: agrupar `Transactions` por `Client (linked record)`,
contar filas con `Stage = "Property leased"`. Cliente con `count ≥ 2` =
repeat buyer. La ventana temporal se aplica sobre `Real settlement date`.

## Reporting

Una sola query consolidada que joinea `funnel_events` (SQLite) con
`Transactions` (Airtable, vía export periódico o el proxy de coach). Output:

```
Período: 2026-Q2

Reports enviados        1.842
Respuestas               412   (22.4%)
Llamadas agendadas       198   (48.1% reply→book)
Llamadas realizadas      164   (82.8% show-up)
Cierres                   38   (23.2% call→close)
Desinversiones             3   (en cohortes ≥ 12 meses)
Repeat buys                7   (de 142 clientes con ≥1 cierre, 4.9%)
```

Implementación pendiente — primer paso es un script ad-hoc en
`scripts/funnel_report.py` que genere el cuadro arriba en texto plano. Si
el dashboard se vuelve crítico se sube a Metabase/Looker apuntando a la
SQLite + un sync de Airtable.

## Qué NO medimos (todavía)

Decisiones explícitas para no dispersar esfuerzos de instrumentación:

- **Aperturas de email.** Resend las da gratis, pero los rates de open
  son ruido (Apple Mail Privacy Protection, prefetch corporate). Solo nos
  fijamos en respuestas — señal alta, ruido bajo.
- **Tiempo en página del report.** El PDF se descarga, no hay sesión web
  larga que medir. Si añadimos versión web del report, este KPI vuelve.
- **Atribución multi-touch.** Un report → una respuesta. No intentamos
  modelar "vio el report, se fue, volvió por anuncio, agendó". Es un MVP
  de funnel, no un MMM.
- **No-shows separados de cancelaciones.** Hasta que el volumen lo
  justifique, ambos cuentan como "no `call_completed`".

## Checklist de implementación

Orden recomendado — cada paso es desbloqueante del siguiente:

1. [ ] Crear tabla `funnel_events` (migración en `backend/db.py`).
2. [ ] Backfill: poblar `stage='report_sent'` desde `valuations.email_sent_at`.
3. [ ] Wire del background task de email para insertar evento atómicamente.
4. [ ] Webhook `POST /api/webhooks/resend` con verificación de firma
       (`Resend-Signature` + secret) → `stage='reply_received'`.
5. [ ] Endpoint `POST /api/funnel/cta-click` para el CTA del email →
       `stage='reply_received'` con `source='cta'`.
6. [ ] Decidir scheduler (Cal.com vs Calendly) y wirearlo:
       `POST /api/webhooks/scheduling` → `stage='call_booked'`.
7. [ ] Añadir columnas `First call completed`, `Divested at`,
       `Divestment reason` en Airtable.
8. [ ] Cron 15 min (`scripts/sync_airtable_calls.py`) que lee Airtable y
       hace upsert de `stage='call_completed'`.
9. [ ] Script `scripts/funnel_report.py` que imprime el cuadro de KPIs
       para una ventana dada.
