import { autocompleteAddresses, reverseGeocode } from "./api.js";

const DEFAULT_CENTER = [40.4168, -3.7038];
const DEFAULT_ZOOM = 6;
const SELECTED_ZOOM = 17;

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

export function createAddressPicker({
  input,
  suggestionsBox,
  selectedBox,
  selectedText,
  mapElement,
  onError,
}) {
  if (!window.L) {
    throw new Error("Leaflet no está disponible");
  }

  const map = window.L.map(mapElement, {
    scrollWheelZoom: false,
  }).setView(DEFAULT_CENTER, DEFAULT_ZOOM);

  window.L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap contributors",
  }).addTo(map);

  let marker = null;
  let selectedAddress = null;
  let debounceTimer = null;
  let requestId = 0;

  function updateMarker(address, zoom = SELECTED_ZOOM) {
    const latLng = [address.lat, address.lon];
    if (!marker) {
      marker = window.L.marker(latLng).addTo(map);
    } else {
      marker.setLatLng(latLng);
    }
    map.setView(latLng, zoom);
  }

  function renderSelectedAddress(address) {
    if (!address) {
      selectedBox.classList.add("hidden");
      selectedText.textContent = "";
      return;
    }

    const locality = [address.municipality, address.province].filter(Boolean).join(", ");
    selectedText.textContent = locality && locality !== address.label
      ? `${address.label} · ${locality}`
      : address.label;
    selectedBox.classList.remove("hidden");
  }

  function hideSuggestions() {
    suggestionsBox.classList.add("hidden");
    suggestionsBox.innerHTML = "";
  }

  function clearSelection() {
    selectedAddress = null;
    renderSelectedAddress(null);
  }

  function applySelection(address, { zoom = SELECTED_ZOOM } = {}) {
    selectedAddress = address;
    input.value = address.label;
    renderSelectedAddress(address);
    updateMarker(address, zoom);
    hideSuggestions();
  }

  function renderSuggestions(suggestions) {
    if (!suggestions.length) {
      suggestionsBox.innerHTML = `
        <div class="px-4 py-3 text-sm text-gray-500">
          No encontramos direcciones para esta búsqueda.
        </div>
      `;
      suggestionsBox.classList.remove("hidden");
      return;
    }

    suggestionsBox.innerHTML = suggestions
      .map((address, index) => {
        const locality = [address.municipality, address.province].filter(Boolean).join(", ");
        return `
          <button
            type="button"
            data-index="${index}"
            class="w-full px-4 py-3 text-left hover:bg-gray-50 border-b border-gray-100 last:border-b-0"
          >
            <span class="block text-sm font-medium text-gray-800">${escapeHtml(address.label)}</span>
            <span class="block text-xs text-gray-500 mt-0.5">${escapeHtml(locality)}</span>
          </button>
        `;
      })
      .join("");

    suggestionsBox.classList.remove("hidden");

    suggestionsBox.querySelectorAll("button[data-index]").forEach((button) => {
      button.addEventListener("click", () => {
        const address = suggestions[Number(button.dataset.index)];
        applySelection(address);
      });
    });
  }

  async function lookupSuggestions(query) {
    const currentRequestId = ++requestId;
    suggestionsBox.innerHTML = `
      <div class="px-4 py-3 text-sm text-gray-500">Buscando direcciones…</div>
    `;
    suggestionsBox.classList.remove("hidden");

    try {
      const suggestions = await autocompleteAddresses(query, 5);
      if (currentRequestId !== requestId) return;
      renderSuggestions(suggestions);
    } catch (error) {
      hideSuggestions();
      onError(error);
    }
  }

  input.addEventListener("input", () => {
    const query = input.value.trim();

    if (selectedAddress && query !== selectedAddress.label) {
      clearSelection();
    }

    if (debounceTimer) {
      window.clearTimeout(debounceTimer);
    }

    if (query.length < 3) {
      hideSuggestions();
      return;
    }

    debounceTimer = window.setTimeout(() => {
      lookupSuggestions(query);
    }, 250);
  });

  input.addEventListener("blur", () => {
    window.setTimeout(hideSuggestions, 120);
  });

  map.on("click", async (event) => {
    try {
      const address = await reverseGeocode(event.latlng.lat, event.latlng.lng);
      applySelection(address, { zoom: map.getZoom() < 16 ? 16 : map.getZoom() });
    } catch (error) {
      onError(error);
    }
  });

  window.setTimeout(() => map.invalidateSize(), 0);

  return {
    getSelectedAddress() {
      return selectedAddress;
    },
  };
}
