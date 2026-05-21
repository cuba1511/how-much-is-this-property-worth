/* report-chart.js — Price-over-time chart
 * Plain JS, no React. Renders into #chart on load and on range change.
 *
 * The dataset is a believable monthly series for a 53m² apartment in
 * Zaragoza purchased Mar 2023 at 134.541€, drifting up at ~4% annual
 * with realistic noise, landing at the recommended 153.148€ in May 2026.
 * Projection 6m forward to ~158.5k.
 */

(function () {
  const W = 1080, H = 340;
  const PAD = { l: 56, r: 24, t: 24, b: 36 };
  const innerW = W - PAD.l - PAD.r;
  const innerH = H - PAD.t - PAD.b;

  // Monthly series: Mar 2023 → Nov 2026 (45 months including 6 projected)
  // Anchors: Mar 2023 = 134541 ; May 2026 = 153148 ; +6m projection 158500
  const series = [
    { m: "2023-03", v: 134541, kind: "actual", label: "Compra" },
    { m: "2023-04", v: 134900 },
    { m: "2023-05", v: 135420 },
    { m: "2023-06", v: 135280 },
    { m: "2023-07", v: 135940 },
    { m: "2023-08", v: 136780 },
    { m: "2023-09", v: 137620 },
    { m: "2023-10", v: 138110 },
    { m: "2023-11", v: 138520 },
    { m: "2023-12", v: 138970 },
    { m: "2024-01", v: 139840 },
    { m: "2024-02", v: 140260 },
    { m: "2024-03", v: 141540 },
    { m: "2024-04", v: 142210 },
    { m: "2024-05", v: 142840 },
    { m: "2024-06", v: 143120 },
    { m: "2024-07", v: 142750 },
    { m: "2024-08", v: 143480 },
    { m: "2024-09", v: 144610 },
    { m: "2024-10", v: 145820 },
    { m: "2024-11", v: 146040 },
    { m: "2024-12", v: 146960 },
    { m: "2025-01", v: 147980 },
    { m: "2025-02", v: 148540 },
    { m: "2025-03", v: 148210 },
    { m: "2025-04", v: 149340 },
    { m: "2025-05", v: 150060 },
    { m: "2025-06", v: 149780 },
    { m: "2025-07", v: 150420 },
    { m: "2025-08", v: 151080 },
    { m: "2025-09", v: 151690 },
    { m: "2025-10", v: 152110 },
    { m: "2025-11", v: 151860 },
    { m: "2025-12", v: 152430 },
    { m: "2026-01", v: 152840 },
    { m: "2026-02", v: 152610 },
    { m: "2026-03", v: 152970 },
    { m: "2026-04", v: 153240 },
    { m: "2026-05", v: 153148, kind: "actual", label: "Hoy" },
    // Projection (dashed)
    { m: "2026-06", v: 153940, kind: "projection" },
    { m: "2026-07", v: 154720, kind: "projection" },
    { m: "2026-08", v: 155650, kind: "projection" },
    { m: "2026-09", v: 156550, kind: "projection" },
    { m: "2026-10", v: 157520, kind: "projection" },
    { m: "2026-11", v: 158500, kind: "projection", label: "Proy." }
  ];

  // Range filter — returns the subset to plot
  function filterRange(range) {
    if (range === "ALL")  return series.filter(p => p.kind !== "projection");
    if (range === "+6M")  return series.slice();
    if (range === "1Y")   return series.slice(series.length - 18, series.length - 6); // last 12 actual months
    if (range === "6M")   return series.slice(series.length - 12, series.length - 6); // last 6 actual months
    return series.filter(p => p.kind !== "projection");
  }

  // Format helpers
  const fmtEur = v => v.toLocaleString("es-ES", { maximumFractionDigits: 0 }) + " €";
  const monthEs = ["ene","feb","mar","abr","may","jun","jul","ago","sep","oct","nov","dic"];
  function fmtMonth(s) {
    const [y, mm] = s.split("-");
    return monthEs[parseInt(mm,10)-1] + " " + y.slice(2);
  }

  function render(range, host) {
    if (!host) return;
    host.innerHTML = "";

    const data = filterRange(range);
    if (!data.length) return;

    const values = data.map(d => d.v);
    let vMin = Math.min(...values);
    let vMax = Math.max(...values);
    // Pad y range
    const pad = (vMax - vMin) * 0.18 || 5000;
    vMin = vMin - pad;
    vMax = vMax + pad;
    // Round to nice numbers
    const niceStep = 5000;
    vMin = Math.floor(vMin / niceStep) * niceStep;
    vMax = Math.ceil(vMax / niceStep) * niceStep;

    const n = data.length;
    const x = i => PAD.l + (i / Math.max(n-1, 1)) * innerW;
    const y = v => PAD.t + innerH - ((v - vMin) / (vMax - vMin)) * innerH;

    // Build path strings — split actual vs projection
    const actualPts = data.filter(d => d.kind !== "projection").map((d, i) => ({ ...d, _i: data.indexOf(d) }));
    const projPts   = data.filter(d => d.kind === "projection").map((d, i) => ({ ...d, _i: data.indexOf(d) }));

    function pathOf(pts) {
      if (pts.length < 2) return "";
      const [first, ...rest] = pts;
      let d = `M ${x(first._i)} ${y(first.v)}`;
      // Smooth with simple cubic between successive points
      for (let i = 0; i < pts.length - 1; i++) {
        const a = pts[i], b = pts[i+1];
        const x1 = x(a._i), y1 = y(a.v);
        const x2 = x(b._i), y2 = y(b.v);
        const cpx = (x1 + x2) / 2;
        d += ` C ${cpx} ${y1} ${cpx} ${y2} ${x2} ${y2}`;
      }
      return d;
    }

    const actualPath = pathOf(actualPts);
    const projPath   = pathOf(projPts);

    // Area under actual line
    let areaPath = "";
    if (actualPts.length) {
      areaPath = actualPath + ` L ${x(actualPts[actualPts.length-1]._i)} ${PAD.t + innerH} L ${x(actualPts[0]._i)} ${PAD.t + innerH} Z`;
    }

    // Bridge between last actual and first projection
    let bridgePath = "";
    if (actualPts.length && projPts.length) {
      const a = actualPts[actualPts.length-1], b = projPts[0];
      const x1 = x(a._i), y1 = y(a.v), x2 = x(b._i), y2 = y(b.v);
      const cpx = (x1 + x2) / 2;
      bridgePath = `M ${x1} ${y1} C ${cpx} ${y1} ${cpx} ${y2} ${x2} ${y2}`;
    }

    // Y axis ticks (5 of them)
    const ticks = [];
    const TICK_N = 5;
    for (let i = 0; i <= TICK_N; i++) {
      const v = vMin + (vMax - vMin) * (i / TICK_N);
      ticks.push({ v: Math.round(v / niceStep) * niceStep, y: y(vMin + (vMax - vMin) * (i / TICK_N)) });
    }

    // X labels — every ~6 points, plus first & last
    const xLabels = [];
    const step = Math.max(1, Math.floor(n / 8));
    for (let i = 0; i < n; i += step) xLabels.push({ i, m: data[i].m });
    if (xLabels[xLabels.length-1].i !== n-1) xLabels.push({ i: n-1, m: data[n-1].m });

    // Find key markers (Compra, Hoy)
    const compra = data.find(d => d.label === "Compra");
    const hoy    = data.find(d => d.label === "Hoy");

    // Recommended sale range band (146.765 – 161.178)
    const rangeLow = 146765, rangeHigh = 161178;
    const showRangeBand = rangeLow >= vMin && rangeLow <= vMax;
    const bandTop = y(rangeHigh), bandBottom = y(rangeLow);

    const svg = `
      <svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%"  stop-color="#2050F6" stop-opacity=".18"/>
            <stop offset="100%" stop-color="#2050F6" stop-opacity="0"/>
          </linearGradient>
          <pattern id="diag" patternUnits="userSpaceOnUse" width="6" height="6" patternTransform="rotate(-45)">
            <line x1="0" y1="0" x2="0" y2="6" stroke="#1E9F6E" stroke-opacity=".18" stroke-width="1"/>
          </pattern>
        </defs>

        ${showRangeBand ? `
          <rect x="${PAD.l}" y="${bandTop}" width="${innerW}" height="${bandBottom - bandTop}"
                fill="url(#diag)" />
          <line x1="${PAD.l}" y1="${bandTop}" x2="${PAD.l + innerW}" y2="${bandTop}"
                stroke="#1E9F6E" stroke-width="1" stroke-dasharray="3 3" stroke-opacity=".5" />
          <line x1="${PAD.l}" y1="${bandBottom}" x2="${PAD.l + innerW}" y2="${bandBottom}"
                stroke="#1E9F6E" stroke-width="1" stroke-dasharray="3 3" stroke-opacity=".5" />
          <text x="${PAD.l + innerW - 6}" y="${bandTop - 6}" text-anchor="end"
                font-family="'JetBrains Mono', monospace" font-size="10" fill="#1E9F6E" letter-spacing="0.06em">
            RANGO SALIDA · 146.765 – 161.178 €
          </text>
        ` : ""}

        <!-- Y grid -->
        ${ticks.map(t => `
          <line x1="${PAD.l}" y1="${t.y}" x2="${PAD.l + innerW}" y2="${t.y}"
                stroke="#E3E3E7" stroke-dasharray="2 4" />
          <text x="${PAD.l - 10}" y="${t.y + 4}" text-anchor="end"
                font-family="'JetBrains Mono', monospace" font-size="11" fill="#9A9AA0">
            ${(t.v/1000).toFixed(0)}k
          </text>
        `).join("")}

        <!-- X labels -->
        ${xLabels.map(l => `
          <text x="${x(l.i)}" y="${H - 12}" text-anchor="middle"
                font-family="'JetBrains Mono', monospace" font-size="11" fill="#9A9AA0">
            ${fmtMonth(l.m)}
          </text>
        `).join("")}

        <!-- Area -->
        <path d="${areaPath}" fill="url(#areaGrad)" />

        <!-- Actual line -->
        <path d="${actualPath}" fill="none" stroke="#2050F6" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" />

        <!-- Bridge (dashed transition) -->
        ${bridgePath ? `<path d="${bridgePath}" fill="none" stroke="#5B7EF9" stroke-width="2" stroke-dasharray="5 5" stroke-linecap="round" />` : ""}

        <!-- Projection line -->
        ${projPath ? `<path d="${projPath}" fill="none" stroke="#5B7EF9" stroke-width="2" stroke-dasharray="5 5" stroke-linecap="round" />` : ""}

        <!-- Key markers -->
        ${compra ? markerSVG(x(compra._i ?? data.indexOf(compra)), y(compra.v), "Compra · " + fmtEur(compra.v), "below", "#212121") : ""}
        ${hoy    ? markerSVG(x(hoy._i ?? data.indexOf(hoy)),       y(hoy.v),    "Hoy · " + fmtEur(hoy.v),       "above", "#2050F6") : ""}

      </svg>
    `;

    host.innerHTML = svg;
  }

  function markerSVG(cx, cy, label, where, color) {
    const labelY = where === "above" ? cy - 18 : cy + 28;
    const align = cx > W - 180 ? "end" : (cx < 120 ? "start" : "middle");
    const tx = align === "end" ? cx - 14 : align === "start" ? cx + 14 : cx;
    return `
      <g>
        <line x1="${cx}" y1="${PAD.t}" x2="${cx}" y2="${H - PAD.b}"
              stroke="${color}" stroke-opacity=".18" stroke-dasharray="3 3"/>
        <circle cx="${cx}" cy="${cy}" r="5" fill="#fff" stroke="${color}" stroke-width="2"/>
        <text x="${tx}" y="${labelY}" text-anchor="${align}"
              font-family="'JetBrains Mono', monospace" font-size="11" fill="${color}"
              letter-spacing="0.04em" font-weight="500">
          ${label}
        </text>
      </g>
    `;
  }

  // Wire up
  function init() {
    const host = document.getElementById("chart");
    const seg  = document.getElementById("seg-range");
    if (!host || !seg) return;

    let current = "ALL";
    render(current, host);

    seg.addEventListener("click", e => {
      const b = e.target.closest("button[data-range]");
      if (!b) return;
      seg.querySelectorAll("button").forEach(x => x.classList.remove("is-on"));
      b.classList.add("is-on");
      current = b.dataset.range;
      render(current, host);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
