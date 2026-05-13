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

function fmtNumber(n) {
  if (n == null) return "—";
  return new Intl.NumberFormat("es-ES", {
    maximumFractionDigits: 0,
  }).format(n);
}

function fmtPct(n) {
  if (n == null) return "—";
  return `${new Intl.NumberFormat("es-ES", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  }).format(n)}%`;
}

function fmtDate(value) {
  if (!value) return "Fecha no disponible";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat("es-ES", {
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(parsed);
}

function relativeFromDate(value) {
  if (!value) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return null;

  const diffMs = Date.now() - parsed.getTime();
  const diffDays = Math.max(0, Math.round(diffMs / (1000 * 60 * 60 * 24)));
  if (diffDays === 0) return "hoy";
  if (diffDays === 1) return "hace 1 día";
  if (diffDays < 30) return `hace ${fmtNumber(diffDays)} días`;

  const diffMonths = Math.round(diffDays / 30);
  if (diffMonths <= 1) return "hace 1 mes";
  if (diffMonths < 12) return `hace ${fmtNumber(diffMonths)} meses`;

  const diffYears = Math.round(diffDays / 365);
  if (diffYears <= 1) return "hace 1 año";
  return `hace ${fmtNumber(diffYears)} años`;
}

function fmtDays(value) {
  if (value == null) return "—";
  if (value === 1) return "1 día";
  return `${fmtNumber(value)} días`;
}

function fmtDistance(value) {
  if (value == null) return null;
  if (value >= 1000) {
    return `${new Intl.NumberFormat("es-ES", {
      minimumFractionDigits: 1,
      maximumFractionDigits: 1,
    }).format(value / 1000)} km`;
  }
  return `${fmtNumber(value)} m`;
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

function sourceLabel(source) {
  if (!source) return "Fuente no disponible";
  if (source === "market-mock") return "Mock market";
  return source.replaceAll("-", " ");
}

const CONDITION_LABELS = {
  obra_nueva: "Obra nueva",
  reformado: "Reformado",
  a_reformar: "A reformar",
  segunda_mano: "Segunda mano",
};

function listingFeatures(listing) {
  const features = [];
  if (listing.condition && CONDITION_LABELS[listing.condition]) {
    features.push(CONDITION_LABELS[listing.condition]);
  }
  if (listing.has_elevator) features.push("Ascensor");
  if (listing.has_terrace) features.push("Terraza");
  if (listing.has_pool) features.push("Piscina");
  if (listing.has_garage) features.push("Garaje");
  if (listing.has_air_conditioning) features.push("A/C");
  return features;
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

  const features = listingFeatures(listing);
  const featuresMarkup = features.length
    ? `<div class="flex flex-wrap gap-1.5 mt-2">
         ${features
           .map(
             (feature) =>
               `<span class="text-xs bg-emerald-50 text-emerald-700 border border-emerald-100 rounded-full px-2 py-0.5 font-medium">${escapeHtml(feature)}</span>`,
           )
           .join("")}
       </div>`
    : "";

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
        ${featuresMarkup}
      </div>
    </a>
  `;
}

function transactionCard(transaction) {
  const badges = [];
  if (transaction.m2) badges.push(`${transaction.m2} m²`);
  if (transaction.bedrooms != null) badges.push(`${transaction.bedrooms} hab.`);
  if (transaction.bathrooms != null) badges.push(`${transaction.bathrooms} baños`);

  const distance = fmtDistance(transaction.distance_m);
  if (distance) badges.push(distance);
  const relativeClose = relativeFromDate(transaction.close_date);

  return `
    <article class="card-hover bg-white rounded-2xl border border-gray-100 overflow-hidden flex flex-col shadow-sm">
      <div class="p-4 flex flex-col flex-1">
        <div class="flex items-start justify-between gap-3">
          <div>
            <p class="text-sm text-gray-500">Transacción cerrada</p>
            <p class="font-semibold text-gray-900 mt-1">${escapeHtml(transaction.address || "Comparable reciente")}</p>
          </div>
          <span class="text-xs rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 px-2.5 py-1 font-semibold">
            Margen ${escapeHtml(fmtPct(transaction.negotiation_margin_pct))}
          </span>
        </div>

        <div class="grid grid-cols-2 gap-3 mt-4">
          <div class="rounded-xl bg-slate-50 border border-slate-100 p-3">
            <p class="text-xs uppercase tracking-wide text-slate-500 font-semibold">Asking</p>
            <p class="text-lg font-bold text-slate-800 mt-1">${escapeHtml(fmt(transaction.asking_price))}</p>
            <p class="text-xs text-slate-500 mt-1">${escapeHtml(fmtNumber(transaction.asking_price_per_m2))} €/m²</p>
          </div>
          <div class="rounded-xl bg-emerald-50 border border-emerald-100 p-3">
            <p class="text-xs uppercase tracking-wide text-emerald-700 font-semibold">Closing</p>
            <p class="text-lg font-bold text-emerald-800 mt-1">${escapeHtml(fmt(transaction.closing_price))}</p>
            <p class="text-xs text-emerald-700 mt-1">${escapeHtml(fmtNumber(transaction.closing_price_per_m2))} €/m²</p>
          </div>
        </div>

        <div class="flex flex-wrap gap-1.5 mt-3">
          ${badges.map((badge) => `<span class="text-xs bg-gray-100 text-gray-600 rounded-full px-2 py-0.5">${escapeHtml(badge)}</span>`).join("")}
        </div>

        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-4">
          <div class="rounded-xl border border-amber-100 bg-amber-50 px-3 py-2.5">
            <p class="text-[11px] uppercase tracking-wide text-amber-700 font-semibold">Tiempo en vender</p>
            <p class="text-sm font-bold text-amber-900 mt-1">${escapeHtml(fmtDays(transaction.days_on_market))}</p>
          </div>
          <div class="rounded-xl border border-blue-100 bg-blue-50 px-3 py-2.5">
            <p class="text-[11px] uppercase tracking-wide text-blue-700 font-semibold">Fecha de cierre</p>
            <p class="text-sm font-bold text-blue-900 mt-1">${escapeHtml(relativeClose || fmtDate(transaction.close_date))}</p>
            <p class="text-[11px] text-blue-700 mt-0.5">${escapeHtml(fmtDate(transaction.close_date))}</p>
          </div>
        </div>

        <div class="mt-4 pt-3 border-t border-gray-100 flex items-center justify-between gap-3 text-xs text-gray-500">
          <span>${escapeHtml(transaction.days_on_market != null ? `Vendida en ${fmtDays(transaction.days_on_market)}` : "Tiempo en mercado no disponible")}</span>
          <span>${escapeHtml(sourceLabel(transaction.source))}</span>
        </div>
      </div>
    </article>
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

function renderMarketChart(chartSeries) {
  const series = (chartSeries || []).filter((point) => point.asking_price || point.closing_price);
  if (series.length === 0) return "";

  const width = 720;
  const height = 260;
  const padding = { top: 20, right: 16, bottom: 46, left: 58 };
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const maxValue = Math.max(
    ...series.flatMap((point) => [point.asking_price || 0, point.closing_price || 0]),
    1,
  );
  const groupWidth = plotWidth / series.length;
  const barWidth = Math.min(24, groupWidth / 3);

  const gridLines = Array.from({ length: 5 }, (_, index) => {
    const ratio = index / 4;
    const y = padding.top + plotHeight - (plotHeight * ratio);
    const labelValue = Math.round((maxValue * ratio) / 1000);
    return `
      <g>
        <line x1="${padding.left}" y1="${y}" x2="${width - padding.right}" y2="${y}" stroke="#e5e7eb" stroke-width="1" />
        <text x="${padding.left - 10}" y="${y + 4}" text-anchor="end" font-size="11" fill="#94a3b8">${escapeHtml(labelValue)}k</text>
      </g>
    `;
  }).join("");

  const bars = series.map((point, index) => {
    const centerX = padding.left + (groupWidth * index) + (groupWidth / 2);
    const askingValue = point.asking_price || 0;
    const closingValue = point.closing_price || 0;
    const askingHeight = (askingValue / maxValue) * plotHeight;
    const closingHeight = (closingValue / maxValue) * plotHeight;
    const askingX = centerX - barWidth - 4;
    const closingX = centerX + 4;
    const askingY = padding.top + plotHeight - askingHeight;
    const closingY = padding.top + plotHeight - closingHeight;
    const label = point.label || `Comp ${index + 1}`;

    return `
      <g>
        <rect x="${askingX}" y="${askingY}" width="${barWidth}" height="${askingHeight}" rx="4" fill="#94a3b8" />
        <rect x="${closingX}" y="${closingY}" width="${barWidth}" height="${closingHeight}" rx="4" fill="#10b981" />
        <text x="${centerX}" y="${height - 16}" text-anchor="middle" font-size="11" fill="#64748b">${escapeHtml(label)}</text>
      </g>
    `;
  }).join("");

  return `
    <div class="flex items-center justify-between gap-3 mb-4">
      <div>
        <p class="text-sm font-semibold text-gray-800">Asking vs closing</p>
        <p class="text-xs text-gray-500 mt-1">Comparativa por transacción reciente para visualizar el margen de negociación.</p>
      </div>
      <div class="flex items-center gap-3 text-xs text-gray-500">
        <span class="flex items-center gap-1.5"><span class="w-3 h-3 rounded-sm bg-slate-400 inline-block"></span> Asking</span>
        <span class="flex items-center gap-1.5"><span class="w-3 h-3 rounded-sm bg-emerald-500 inline-block"></span> Closing</span>
      </div>
    </div>
    <div class="overflow-x-auto">
      <svg viewBox="0 0 ${width} ${height}" class="min-w-[640px] w-full h-auto" role="img" aria-label="Grafico de asking price frente a closing price">
        ${gridLines}
        <line x1="${padding.left}" y1="${padding.top + plotHeight}" x2="${width - padding.right}" y2="${padding.top + plotHeight}" stroke="#cbd5e1" stroke-width="1" />
        ${bars}
      </svg>
    </div>
  `;
}

const DATASET_NUMERIC_COLS = [
  { key: "metros", label: "metros" },
  { key: "precio", label: "precio" },
  { key: "habitaciones", label: "habitaciones" },
  { key: "banos", label: "baños" },
  { key: "planta", label: "planta" },
];

const DATASET_CATEGORICAL_COLS = [
  { key: "ascensor", label: "ascensor" },
  { key: "piscina", label: "piscina" },
  { key: "jardin", label: "jardín" },
  { key: "garaje", label: "garaje" },
  { key: "trastero", label: "trastero" },
];

function renderDataset(dataset) {
  const section = document.getElementById("datasetSection");
  const badge = document.getElementById("datasetBadge");
  const warning = document.getElementById("datasetWarning");
  const table = document.getElementById("datasetTable");

  if (!dataset || !dataset.rows?.length) {
    section.classList.add("hidden");
    table.innerHTML = "";
    warning.classList.add("hidden");
    return;
  }

  badge.textContent = `${dataset.row_count} / ${dataset.max_allowed} filas`;
  if (dataset.row_count < dataset.min_required) {
    warning.textContent = `Solo ${dataset.row_count} comparables disponibles, por debajo del mínimo recomendado (${dataset.min_required}). Los resultados pueden ser menos fiables.`;
    warning.classList.remove("hidden");
  } else {
    warning.classList.add("hidden");
  }

  const headerCells = [
    `<th class="text-left px-3 py-2 font-semibold text-gray-500">#</th>`,
    ...DATASET_NUMERIC_COLS.map(
      (col) => `<th class="text-right px-3 py-2 font-semibold text-gray-500">${escapeHtml(col.label)}</th>`,
    ),
    ...DATASET_CATEGORICAL_COLS.map(
      (col) => `<th class="text-center px-3 py-2 font-semibold text-gray-500">${escapeHtml(col.label)}</th>`,
    ),
  ].join("");

  const bodyRows = dataset.rows
    .map((row, index) => {
      const numericCells = DATASET_NUMERIC_COLS.map((col) => {
        const value = row[col.key];
        const cell = value == null
          ? '<span class="text-gray-300">-</span>'
          : escapeHtml(fmtNumber(value));
        return `<td class="text-right px-3 py-2 text-gray-800 tabular-nums">${cell}</td>`;
      }).join("");
      const categoricalCells = DATASET_CATEGORICAL_COLS.map((col) => {
        const value = row[col.key];
        const cls = value === 1
          ? "bg-emerald-50 text-emerald-700"
          : "bg-gray-50 text-gray-400";
        return `<td class="text-center px-3 py-2"><span class="inline-flex items-center justify-center w-7 h-7 rounded-full ${cls} font-semibold">${value}</span></td>`;
      }).join("");
      return `
        <tr class="border-t border-gray-100">
          <td class="px-3 py-2 text-gray-500">${index + 1}</td>
          ${numericCells}
          ${categoricalCells}
        </tr>
      `;
    })
    .join("");

  table.innerHTML = `
    <thead class="bg-gray-50">
      <tr>${headerCells}</tr>
    </thead>
    <tbody>${bodyRows}</tbody>
  `;
  section.classList.remove("hidden");
}

function renderMarketTransactions(marketTransactions) {
  const section = document.getElementById("marketTransactionsSection");
  const badge = document.getElementById("marketTransactionsBadge");
  const statsGrid = document.getElementById("marketTransactionsStats");
  const insight = document.getElementById("marketTransactionsInsight");
  const chart = document.getElementById("marketTransactionsChart");
  const grid = document.getElementById("marketTransactionsGrid");

  if (!marketTransactions?.summary || !marketTransactions.transactions?.length) {
    section.classList.add("hidden");
    badge.classList.add("hidden");
    insight.classList.add("hidden");
    chart.classList.add("hidden");
    statsGrid.innerHTML = "";
    insight.innerHTML = "";
    chart.innerHTML = "";
    grid.innerHTML = "";
    return;
  }

  const { summary, transactions } = marketTransactions;
  statsGrid.innerHTML = [
    statCard(
      "Asking medio",
      fmt(summary.avg_asking_price),
      summary.avg_asking_price_per_m2 ? `${fmtNumber(summary.avg_asking_price_per_m2)} €/m²` : "precio de salida",
    ),
    statCard(
      "Closing medio",
      fmt(summary.avg_closing_price),
      summary.avg_closing_price_per_m2 ? `${fmtNumber(summary.avg_closing_price_per_m2)} €/m²` : "precio de cierre",
    ),
    statCard("Margen neg.", fmtPct(summary.negotiation_margin_pct), "gap medio asking vs closing"),
    statCard("Muestra", fmtNumber(summary.sample_size), "transacciones recientes"),
  ].join("");

  badge.textContent = transactions.every((transaction) => transaction.source === "market-mock")
    ? `Mockups · ${summary.sample_size} transacciones`
    : `${summary.sample_size} transacciones`;
  badge.classList.remove("hidden");

  insight.innerHTML = `
    <p class="text-sm font-semibold text-gray-800">Lectura de mercado</p>
    <p class="text-sm text-gray-600 mt-1">
      El closing medio se sitúa en <strong>${escapeHtml(fmt(summary.avg_closing_price))}</strong>,
      un <strong>${escapeHtml(fmtPct(summary.asking_vs_closing_gap_pct))}</strong> por debajo del asking medio
      (<strong>${escapeHtml(fmt(summary.avg_asking_price))}</strong>).
    </p>
    <p class="text-xs text-gray-500 mt-3">
      La valoración principal sigue basada en los comparables de Idealista; esta capa añade contexto para negociación.
    </p>
  `;
  insight.classList.remove("hidden");

  const chartMarkup = renderMarketChart(summary.chart_series);
  if (chartMarkup) {
    chart.innerHTML = chartMarkup;
    chart.classList.remove("hidden");
  } else {
    chart.innerHTML = "";
    chart.classList.add("hidden");
  }

  grid.innerHTML = transactions.map(transactionCard).join("");
  section.classList.remove("hidden");
}

export function renderResults(data, payload) {
  const { municipio, listings, stats, search_url, search_metadata, market_transactions, dataset } = data;

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

  renderMarketTransactions(market_transactions);
  renderDataset(dataset);

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
