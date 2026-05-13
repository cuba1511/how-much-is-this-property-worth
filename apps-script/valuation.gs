// 1. Pega la URL pública de tu backend aquí (la que te da `ngrok http 8001`).
//    Sin slash al final.
const API_URL = "https://CAMBIA-ESTO.ngrok-free.app";

/**
 * Valora una casa llamando al backend de House Valuation.
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
  const res = UrlFetchApp.fetch(API_URL + "/api/valuation/simple", {
    method: "post",
    contentType: "application/json",
    headers: { "ngrok-skip-browser-warning": "true" },
    payload: JSON.stringify({
      address: address,
      bedrooms: bedrooms,
      bathrooms: bathrooms,
      m2: m2,
    }),
    muteHttpExceptions: true,
  });

  if (res.getResponseCode() !== 200) {
    throw new Error("API " + res.getResponseCode() + ": " + res.getContentText());
  }

  const data = JSON.parse(res.getContentText());
  return [[data.price, data.asking_price, data.closing_price, data.negotiation_factor]];
}
