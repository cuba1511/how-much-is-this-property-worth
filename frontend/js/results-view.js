function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function fmt(n) {
  if (n == null) return "—";
  return new Intl.NumberFormat("es-ES", {
    style: "currency",
    currency: "EUR",
    maximumFractionDigits: 0,
  }).format(n);
}

function statCard(label, value, sub) {
  return `
    <div class="stat-card rounded-xl p-4 border border-gray-100">
      <p class="text-xs text-gray-500 font-medium uppercase tracking-wide">${escapeHtml(label)}</p>
      <p class="text-xl font-extrabold text-gray-800 mt-1">${escapeHtml(value)}</p>
      ${sub ? `<p class="text-xs text-gray-400 mt-0.5">${escapeHtml(sub)}</p>` : ""}
    </div>
  `;
}

function listingCard(listing) {
  const img = listing.image_url
    ? `<img src="${escapeHtml(listing.image_url)}" alt="" class="listing-img" onerror="this.style.display='none'">`
    : `<div class="listing-img flex items-center justify-center bg-gray-100">
         <svg class="w-8 h-8 text-gray-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
           <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"
             d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z"/>
         </svg>
       </div>`;

  const badges = [];
  if (listing.m2) badges.push(`${listing.m2} m²`);
  if (listing.bedrooms) badges.push(`${listing.bedrooms} hab.`);
  if (listing.bathrooms) badges.push(`${listing.bathrooms} baños`);
  if (listing.floor) badges.push(listing.floor);

  return `
    <a href="${escapeHtml(listing.url)}" target="_blank" rel="noreferrer"
       class="card-hover bg-white rounded-2xl border border-gray-100 overflow-hidden flex flex-col shadow-sm">
      ${img}
      <div class="p-4 flex flex-col flex-1">
        <p class="text-sm text-gray-500 truncate mb-1">${escapeHtml(listing.address || "")}</p>
        <p class="font-bold text-gray-900 text-lg">${escapeHtml(fmt(listing.price))}</p>
        ${listing.price_per_m2 ? `<p class="text-xs text-gray-400">${escapeHtml(fmt(listing.price_per_m2))}/m²</p>` : ""}
        <div class="flex flex-wrap gap-1.5 mt-3">
          ${badges.map((badge) => `<span class="text-xs bg-gray-100 text-gray-600 rounded-full px-2 py-0.5">${escapeHtml(badge)}</span>`).join("")}
        </div>
      </div>
    </a>
  `;
}

function renderSearchMetadata(searchMetadata) {
  const box = document.getElementById("searchMeta");
  if (!searchMetadata) {
    box.classList.add("hidden");
    box.innerHTML = "";
    return;
  }

  box.innerHTML = `
    <p class="text-sm font-semibold text-gray-800 mb-1">Cómo encontramos los comparables</p>
    <p class="text-sm text-gray-600 mb-3">
      Estrategia: capas geográficas · etapa final: <strong>${escapeHtml(searchMetadata.final_stage)}</strong> · tiempo total: <strong>${(searchMetadata.total_duration_ms / 1000).toFixed(1)}s</strong>
    </p>
    <div class="flex flex-wrap gap-2">
      ${searchMetadata.stages.map((stage) => `
        <div class="text-xs rounded-full border border-gray-200 bg-gray-50 px-3 py-1.5 text-gray-700">
          ${escapeHtml(stage.label)}: ${stage.listings_found} comps · ${(stage.duration_ms / 1000).toFixed(1)}s
        </div>
      `).join("")}
    </div>
  `;
  box.classList.remove("hidden");
}

export function renderResults(data, payload) {
  const { municipio, listings, stats, search_url, search_metadata } = data;

  document.getElementById("municipioLabel").textContent =
    `${municipio.name}${municipio.province ? `, ${municipio.province}` : ""}`;
  document.getElementById("idealistaLink").href = search_url;
  renderSearchMetadata(search_metadata);

  const statsGrid = document.getElementById("statsGrid");
  statsGrid.innerHTML = [
    statCard("Comparables", stats.total_comparables, "listados encontrados"),
    statCard("Precio medio", fmt(stats.avg_price), "en esta búsqueda"),
    statCard(
      "€/m² medio",
      stats.avg_price_per_m2 ? `${stats.avg_price_per_m2.toLocaleString("es-ES")} €` : "—",
      "precio por metro cuadrado",
    ),
    statCard(
      "Rango",
      stats.min_price && stats.max_price ? `${fmt(stats.min_price)} – ${fmt(stats.max_price)}` : "—",
      "mín – máx",
    ),
  ].join("");

  const estimateCard = document.getElementById("estimateCard");
  if (stats.estimated_value) {
    document.getElementById("estimateValue").textContent = fmt(stats.estimated_value);
    document.getElementById("estimateRange").textContent =
      `Rango estimado: ${fmt(stats.price_range_low)} – ${fmt(stats.price_range_high)}`;
    document.getElementById("estimateCount").textContent = stats.total_comparables;
    document.getElementById("estimateM2").textContent = payload.m2;
    estimateCard.classList.remove("hidden");
  } else {
    estimateCard.classList.add("hidden");
  }

  const listingsGrid = document.getElementById("listingsGrid");
  if (listings.length === 0) {
    document.getElementById("noListings").classList.remove("hidden");
    listingsGrid.innerHTML = "";
  } else {
    document.getElementById("noListings").classList.add("hidden");
    listingsGrid.innerHTML = listings.map(listingCard).join("");
  }

  document.getElementById("results").classList.remove("hidden");
  document.getElementById("results").scrollIntoView({ behavior: "smooth", block: "start" });
}
