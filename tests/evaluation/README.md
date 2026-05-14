# Calibration Harness

Mide la precisión del endpoint `/api/valuation` contra un dataset de tasaciones
profesionales. Nos da un número objetivo (MAE, MAPE, % dentro del intervalo)
antes y después de cada cambio en la lógica de cálculo.

## CSV de entrada

El dataset vive en `tests/data/test_valuation.csv`. Mira
`tests/data/test_valuation.example.csv` para el schema completo.

**Columnas obligatorias** (sin esto la fila se salta):

| Columna           | Tipo  | Notas                                          |
| ----------------- | ----- | ---------------------------------------------- |
| `address`         | str   | Dirección completa. Aceptamos "Dirección" como alias |
| `m2`              | int   | Superficie útil                                 |
| `bedrooms`        | int   | Habitaciones                                    |
| `bathrooms`       | int   | Baños                                           |
| `appraiser_value` | int   | Ground truth (€). Alias: "Valoraciones manuales" |

**Columnas opcionales**:

`property_type` · `property_condition` · `pool` · `terrace` · `elevator` ·
`parking` · `notes`

El parser tolera:

- Números con separadores: `465,000` · `465.000` · `465 000`.
- Celdas vacías y los marcadores `N/A`, `NA`, `-`, `—`, `#DIV/0!`.
- BOM UTF-8.
- Sufijos de planta/puerta en la dirección (`6D`, `3°-7`, `PB-2`,
  `2C`) — se limpian antes de mandar al scraper porque a Idealista no le
  gustan.

## Cómo correrlo

Necesitas el backend levantado (por defecto en `http://localhost:8001`).

```bash
# Repo root
make dev  # en otra terminal — levanta FastAPI en :8001
python -m tests.evaluation.run_evaluation \
  --csv tests/data/test_valuation.csv \
  --label baseline
```

Opciones:

| Flag         | Default                              | Qué hace                                       |
| ------------ | ------------------------------------ | ---------------------------------------------- |
| `--csv`      | `tests/data/test_valuation.csv`      | Ruta al CSV                                    |
| `--api`      | `http://localhost:8001`              | Base URL del backend                           |
| `--label`    | `run`                                | Tag corto para el nombre del reporte           |
| `--no-cache` | off                                  | Ignora el cache y re-pega contra la API        |

## Caching

Por fila, cacheamos la respuesta del backend en
`tests/evaluation/.cache/{hash}.json` (clave = `address+m²+beds+baths+condition`).
Esto convierte re-runs en segundos (el scraper tarda 5-15s por propiedad).

Cuando cambies la lógica de cálculo (regresión, weighted comps, etc.) **borrá
el cache** para volver a pegarle a la API:

```bash
rm -rf tests/evaluation/.cache
```

O usá `--no-cache` directamente.

## Outputs

Por cada run se generan dos archivos en `tests/evaluation/reports/`:

```
{UTC-timestamp}-{git-sha}-{label}.json   # estructurado, diffeable
{UTC-timestamp}-{git-sha}-{label}.md     # tabla legible
```

Métricas agregadas que reportamos:

| Métrica           | Qué mide                                                          |
| ----------------- | ----------------------------------------------------------------- |
| **MAE**           | Mean Absolute Error en €                                          |
| **MAPE**          | Mean Absolute % Error — la principal métrica de calidad           |
| **Median % err**  | Mediana del % error (robusto a outliers)                          |
| **RMSE**          | Root Mean Square Error en €                                       |
| **Within range %**| % de tasaciones que caen dentro del intervalo `[low, high]`       |
| **Bias %**        | Error medio con signo. Positivo = sobreestimamos, negativo = subestimamos |

## Flujo recomendado

1. Llenar `tests/data/test_valuation.csv` con `m2`, `bedrooms`, `bathrooms`
   y `appraiser_value` para las filas que quieras evaluar.
2. Correr con `--label baseline` para fotografiar el estado actual.
3. Implementar Mejora 1 (regresión OLS aplicada), borrar cache, correr con
   `--label ols`.
4. Diffear `baseline.json` vs `ols.json` — solo mergear el cambio si MAPE bajó.
5. Repetir para cada mejora.

## Limitaciones conocidas

- El scraper de Idealista es secuencial → ~5-15s/propiedad. 25 propiedades =
  ~6 min en frío, segundos en cache.
- Direcciones muy informales o pueblos pequeños pueden no encontrar
  comparables; esas filas aparecen como `failed` en el reporte.
- El parser de pisos/puertas es heurístico; si una dirección llega "rota"
  al scraper, ajusta `strip_floor_info` en `run_evaluation.py`.
