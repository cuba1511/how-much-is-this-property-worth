// 1. Pega la URL pública de tu backend aquí (la que te da `ngrok http 8001`).
//    Sin slash al final.
const API_URL = "https://3b41-195-158-89-154.ngrok-free.app";

// Cache del lado de Apps Script. 6h. Reduce llamadas al backend cuando
// arrastras una fórmula sobre muchas filas con la misma dirección.
const SHEETS_CACHE_TTL_SECONDS = 6 * 60 * 60;

/**
 * Valora una casa llamando al backend de House Valuation (MODO RÁPIDO).
 *
 * Devuelve precios mockeados realistas al instante (~1s). Usa esto para demos
 * en Google Sheets — el modo "real" (scraping de Idealista) tarda 40-70s
 * y Apps Script tiene un límite duro de 30s para custom functions.
 *
 * Uso en una celda:
 *   =VALORAR_CASA("Calle Mayor 12, Madrid", 3, 2, 95)
 *
 * Devuelve 4 columnas: price | asking_price | closing_price | negotiation_factor
 *
 * @param {string} address     Dirección completa.
 * @param {number} bedrooms    Habitaciones.
 * @param {number} bathrooms   Baños.
 * @param {number} m2          Superficie en m².
 * @return {Array<Array<number>>}
 * @customfunction
 */
function VALORAR_CASA(address, bedrooms, bathrooms, m2) {
  validateArgs_(address, bedrooms, bathrooms, m2);
  return callValuationCached_(address, Number(bedrooms), Number(bathrooms), Number(m2), /*fast=*/ true);
}

/**
 * Valora una casa llamando al backend de House Valuation (MODO REAL).
 *
 * Scrapea Idealista en vivo. Tarda 40-70s la primera vez por dirección, y
 * Apps Script te matará la celda a los 30s con "Loading..." perdido. Solo
 * funciona si el backend tiene la dirección en caché (1h de TTL): pre-calienta
 * con curl o con el frontend web antes de demoear.
 *
 * Uso en una celda:
 *   =VALORAR_CASA_REAL("Calle Mayor 12, Madrid", 3, 2, 95)
 *
 * @param {string} address     Dirección completa.
 * @param {number} bedrooms    Habitaciones.
 * @param {number} bathrooms   Baños.
 * @param {number} m2          Superficie en m².
 * @return {Array<Array<number>>}
 * @customfunction
 */
function VALORAR_CASA_REAL(address, bedrooms, bathrooms, m2) {
  validateArgs_(address, bedrooms, bathrooms, m2);
  return callValuationCached_(address, Number(bedrooms), Number(bathrooms), Number(m2), /*fast=*/ false);
}

/**
 * Función de prueba: ejecútala con el botón ▶ "Run" del editor de Apps Script
 * para verificar conectividad/permisos sin pasar por una celda.
 * Mira el resultado en "Execution log" (View → Executions o Ctrl+Enter).
 */
function testValuation() {
  const result = callValuation_("Calle Mayor 12, Madrid", 3, 2, 95, /*fast=*/ true);
  Logger.log("Result (fast mode): " + JSON.stringify(result));
  return result;
}

function validateArgs_(address, bedrooms, bathrooms, m2) {
  if (!address || bedrooms == null || bathrooms == null || m2 == null) {
    throw new Error(
      "Faltan argumentos. Uso: =VALORAR_CASA(\"Calle Mayor 12, Madrid\", 3, 2, 95). " +
      "Recibido: address=" + address + ", bedrooms=" + bedrooms +
      ", bathrooms=" + bathrooms + ", m2=" + m2
    );
  }
}

function callValuationCached_(address, bedrooms, bathrooms, m2, fast) {
  const cache = CacheService.getScriptCache();
  const key = "v1|" + (fast ? "fast" : "real") + "|" + [address, bedrooms, bathrooms, m2].join("|");
  const cached = cache.get(key);
  if (cached) {
    return JSON.parse(cached);
  }

  const result = callValuation_(address, bedrooms, bathrooms, m2, fast);
  try {
    cache.put(key, JSON.stringify(result), SHEETS_CACHE_TTL_SECONDS);
  } catch (_) {
    // CacheService limita el valor a 100KB; nuestra respuesta es pequeña, pero
    // si crece en el futuro y peta el límite, simplemente seguimos sin cache.
  }
  return result;
}

function callValuation_(address, bedrooms, bathrooms, m2, fast) {
  const url = API_URL + "/api/valuation/simple" + (fast ? "?fast=true" : "");
  const payload = {
    address: address,
    bedrooms: bedrooms,
    bathrooms: bathrooms,
    m2: m2,
  };

  const res = UrlFetchApp.fetch(url, {
    method: "post",
    contentType: "application/json",
    headers: { "ngrok-skip-browser-warning": "true" },
    payload: JSON.stringify(payload),
    muteHttpExceptions: true,
  });

  const code = res.getResponseCode();
  const body = res.getContentText();
  if (code !== 200) {
    throw new Error("API " + code + ": " + body);
  }

  const data = JSON.parse(body);
  return [[data.price, data.asking_price, data.closing_price, data.negotiation_factor]];
}
