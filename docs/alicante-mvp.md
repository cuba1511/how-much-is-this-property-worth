# Alicante MVP — paquete aislado

## Propósito

Validar la valoración contra **datos reales de transacciones cerradas** en Alicante (vs los listings de Idealista que usa la API productiva) **sin tocar el código productivo**. Todo el MVP vive en un único paquete `backend/alicante/` y se expone bajo endpoints separados.

## Lo que NO se mezcla con producción

- ✅ El endpoint `POST /api/valuation` sigue funcionando exactamente igual: geocoder → Bright Data + Idealista scraper → valoración → mock de transacciones.
- ✅ `backend/db.py`, `backend/main.py`, `backend/valuation/` y `backend/scraping/` no contienen ningún símbolo Alicante-only.
- ✅ Borrar el directorio `backend/alicante/` + la línea `app.include_router(alicante_router)` en `main.py` **desactiva el MVP por completo** sin efectos colaterales.

## Endpoints

| Método | Ruta | Descripción |
|--------|------|-------------|
| `POST` | `/api/valuation/alicante` | Drop-in de `/api/valuation`. Mismo contrato `ValuationResponse`. Listings desde SQLite local (<50 ms), `market_transactions` con KPIs reales del dataset. **Solo direcciones en Alicante/Alacant con calle + número.** |
| `GET`  | `/api/valuation/alicante/status` | Health check: dataset cargado, conteos, cobertura, formato esperado. |

### Reglas de entrada del POST

1. **Calle + número de portal** obligatorios. La heurística mira el primer
   segmento (antes de la primera coma) y exige al menos un dígito. `"Calle
   Gravina 5, Alicante"` ✅, `"Alicante"` ❌, `"Calle Mayor, Madrid"` ❌.
2. El **geocoder DEBE resolver** la dirección a un municipio. Si no
   resuelve → 422 con instrucciones de formato.
3. El municipio resuelto **debe estar en `COVERAGE_SLUGS`** del MVP. Si no
   está → 422 indicando el slug que se obtuvo y los aceptados. No hay
   fallback silencioso al centroide de Alicante.

Ejemplos de respuestas:

```json
// 200 OK — "Calle Gravina 5, Alicante", 90m², 3 hab, 2 baños
{ "stats": { "estimated_value": 433080, ... }, ... }

// 422 — "Alicante"
{ "detail": "La dirección debe incluir calle y número de portal
            (ej. 'Calle Gravina 5, Alicante'). Recibido: 'Alicante'." }

// 422 — "Gran Via 1, Madrid"
{ "detail": "Este endpoint solo cubre direcciones en Alicante/Alacant.
            La dirección resolvió a 'Madrid' (slug='madrid').
            Slugs aceptados: ['alacant', 'alicante', 'alicante-alacant'].
            Usa POST /api/valuation para el resto de España." }
```

## Estructura del paquete

```
backend/alicante/
├── __init__.py            # exporta `router` + dispara registro de schema hook
├── routes.py              # APIRouter con los 2 endpoints anteriores
├── storage.py             # SQLite: schema + queries + bulk upsert + ensure_schema
├── listings_provider.py   # query_alicante_listings (reemplazo del scraper)
├── transactions.py        # build_alicante_transactions (closing KPIs reales)
├── coverage.py            # municipio_in_coverage — slugs aceptados
└── _pipeline.py           # copia local de los helpers de orquestación de main.py
```

## Cómo se enchufa al resto del backend

1. **Schema autocreado.** `alicante/storage.py` llama a `db.register_schema_hook(ensure_schema)` al importarse. La primera vez que `main.py` ejecuta `db.init_db()` el hook crea las tablas `alicante_listings` y `alicante_transactions`. `db.py` no menciona Alicante por su nombre.
2. **Router incluido.** `main.py` hace `from alicante import router` y `app.include_router(router)`. Una sola línea de "mención" de Alicante en `main.py`.
3. **Conexión SQLite reutilizada.** El paquete usa `db.connect` (alias público de `db._connect`) — sin abrir conexiones propias ni introducir nuevas pragmas.

## Tablas (SQLite)

### `alicante_listings`
Snapshot de listings de Idealista para la provincia de Alicante. Cargado desde la hoja `Listing_Semanal`. PK: `gsraw_id`.

### `alicante_transactions`
KPIs **agregados** (no por transacción) de cierre. Cargado desde `Indicadores_Transacciones_Reales`. PK: `table_id`. Granularidad: `(boundary_id, period_id, indicator_id, segment_id)`. Indicadores relevantes:

| ID  | Significado |
|-----|-------------|
| 101 | €/m² closing (mediana) |
| 102 | €/m² closing (media) ← preferido |
| 103 | Precio closing (mediana) |
| 104 | Precio closing (media) |
| 108 | Margen bruto (no usado — unidades inconsistentes en el snapshot) |

## ETL

```bash
make load-alicante                          # busca backend/data/alicante-mvp.xlsx
make load-alicante FILE=/ruta/al.xlsx       # archivo custom
```

El script `scripts/load_alicante.py` es stdlib puro (no openpyxl/pandas). Lee el `.xlsx` como ZIP+XML, hace upsert por PK. Idempotente.

## Cómo se construye `market_transactions` (datos reales)

1. **Closing side** — leer la última `period_id` de `alicante_transactions` para boundary `224` (Alicante/Alacant admin3), `operation_type_id=10` (residencial), `segment_id=0`, indicadores 102 y 104. Eso da `avg_closing_price_per_m2` y `avg_closing_price` reales del periodo más reciente (típicamente último trimestre).
2. **Asking side** — agregado municipio-wide de `alicante_listings` (`admin3 = 'Alicante/Alacant'`, `property_type = 'Pisos'`). Mismo scope espacial que el closing → la comparación es válida.
3. **Margen** — `(asking - closing) / asking` derivado de los dos agregados anteriores en lugar del indicador 108 (que tiene unidades inconsistentes en este snapshot).
4. **Filas de la tabla / chart series** — sintetizadas desde los listings más cercanos al inmueble, aplicando el margen agregado. `source = "alicante-derived"` deja claro que el closing por fila es modelado, no observado.

## Diferencias frente a producción

| Aspecto | `/api/valuation` (prod) | `/api/valuation/alicante` (MVP) |
|---------|-------------------------|---------------------------------|
| Listings | Bright Data + Idealista (15-60 s) | SQLite local (<50 ms) |
| `market_transactions` | `build_market_transactions_mock` (seeded) | `build_alicante_transactions` (KPIs reales del dataset) |
| Cobertura | Cualquier dirección en España | Solo Alicante/Alacant — el resto se rechaza con 422 |
| Formato dirección | Tolerante | Exige calle + número en el primer segmento del label |
| Persistencia leads/valuations | Sí | No (es un endpoint de validación) |

## Cuando el MVP "gradúe"

1. Promover los helpers de `alicante/_pipeline.py` a `valuation/pipeline.py` compartido y borrar `_pipeline.py`.
2. Mover la cobertura de un `frozenset` hardcoded a una tabla `coverage_areas` con índice por slug.
3. Integrar el route picker (`/api/valuation` debería elegir provider Alicante vs scraper) en `main.py` — pero solo cuando confiemos en los datos.
4. Si la respuesta es muy distinta del scraper, mantener ambos endpoints como producto separado ("estimación con datos cerrados" vs "comparables abiertos").
