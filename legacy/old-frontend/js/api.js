const API_BASE = "";

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(data.detail || `HTTP ${response.status}`);
  }

  return data;
}

export function autocompleteAddresses(query, limit = 5) {
  const params = new URLSearchParams({
    q: query,
    limit: String(limit),
  });
  return fetchJson(`${API_BASE}/api/addresses/autocomplete?${params.toString()}`);
}

export function reverseGeocode(lat, lon) {
  const params = new URLSearchParams({
    lat: String(lat),
    lon: String(lon),
  });
  return fetchJson(`${API_BASE}/api/addresses/reverse?${params.toString()}`);
}

export function submitValuation(payload) {
  return fetchJson(`${API_BASE}/api/valuation`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}
