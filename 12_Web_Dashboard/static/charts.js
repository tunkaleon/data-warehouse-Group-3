/* =====================================================================
   charts.js - tiny chart drawer (no internet needed, no library)
   Every function draws an SVG picture inside an HTML element:
     lineChart(id, labels, series)          lines over time
     barChart(id, items, options)           horizontal bars  (items = [{label, value}])
     columnChart(id, items, options)        vertical bars
     donutChart(id, items, centerText)      pie chart with a hole
     comboChart(id, labels, bars, line)     bars + a line (daily + 7-day average)
     heatMap(id, rows, cols, grid)          coloured table (dark = busy)
   Hover a bar / point / slice to see the exact number (SVG <title>).
   ===================================================================== */

const COLORS = ["#e8673a", "#1fa774", "#2a78d6", "#e57fa5", "#6650d6", "#e9a10b"];
const SVG = "http://www.w3.org/2000/svg";

function el(tag, attrs, parent, text) {             // create one SVG element
  const e = document.createElementNS(SVG, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  if (text !== undefined) e.textContent = text;
  if (parent) parent.appendChild(e);
  return e;
}
function svgIn(id, w, h) {                          // empty SVG that scales with the card
  const box = document.getElementById(id);
  box.innerHTML = "";
  return el("svg", { viewBox: `0 0 ${w} ${h}`, role: "img" }, box);
}
function widthOf(id) {                             // real width of the card in pixels
  return Math.max(280, Math.round(document.getElementById(id).clientWidth) || 600);
}
function niceMax(v) {                               // round the axis maximum up (e.g. 187 -> 200)
  if (v <= 0) return 1;
  const p = Math.pow(10, Math.floor(Math.log10(v)));
  return Math.ceil(v / p * 2) / 2 * p;
}
function fmt(v) { return Number(v).toLocaleString("en-US"); }
function legend(id, names, colors) {
  const box = document.getElementById(id);
  const div = document.createElement("div");
  div.className = "legend";
  names.forEach((n, i) => { div.innerHTML += `<span><i style="background:${colors[i]}"></i>${n}</span>`; });
  box.appendChild(div);
}

/* ---------- line chart ---------- */
function lineChart(id, labels, series, opts = {}) {
  const W = widthOf(id), H = 300, L = 44, R = 16, T = 14, B = 34;
  const svg = svgIn(id, W, H);
  const max = niceMax(Math.max(...series.flatMap(s => s.values)));
  const x = i => L + i * (W - L - R) / Math.max(1, labels.length - 1);
  const y = v => T + (H - T - B) * (1 - v / max);
  for (let k = 0; k <= 4; k++) {                    // grid lines + y labels
    const v = max * k / 4;
    el("line", { x1: L, x2: W - R, y1: y(v), y2: y(v), stroke: "#ececea" }, svg);
    el("text", { x: L - 6, y: y(v) + 4, "text-anchor": "end" }, svg, fmt(Math.round(v)));
  }
  if (opts.refLine) el("line", { x1: L, x2: W - R, y1: y(opts.refLine), y2: y(opts.refLine),
                                 stroke: "#9a9a94", "stroke-dasharray": "4 4" }, svg);
  const step = Math.ceil(labels.length / 12);       // at most ~12 x labels
  labels.forEach((lab, i) => {
    if (i % step === 0) el("text", { x: x(i), y: H - 12, "text-anchor": "middle" }, svg, lab);
  });
  series.forEach((s, si) => {
    const c = s.color || COLORS[si];
    const pts = s.values.map((v, i) => `${x(i)},${y(v)}`).join(" ");
    el("polyline", { points: pts, fill: "none", stroke: c, "stroke-width": 2.2, "stroke-linejoin": "round" }, svg);
    s.values.forEach((v, i) => {
      const dot = el("circle", { cx: x(i), cy: y(v), r: 3.5, fill: c, opacity: 0 }, svg);
      dot.addEventListener("mouseenter", () => dot.setAttribute("opacity", 1));
      dot.addEventListener("mouseleave", () => dot.setAttribute("opacity", 0));
      el("title", {}, dot, `${s.name} ${labels[i]}: ${fmt(v)}`);
    });
  });
  legend(id, series.map(s => s.name), series.map((s, i) => s.color || COLORS[i]));
}

/* ---------- horizontal bar chart ---------- */
function barChart(id, items, opts = {}) {
  const rowH = 28, L = opts.labelWidth || 170, R = 56, T = 6;
  const W = widthOf(id), H = T + items.length * rowH + 6;
  const svg = svgIn(id, W, H);
  const max = niceMax(Math.max(...items.map(d => d.value)));
  const c = opts.color || "#2a78d6", suffix = opts.suffix || "";
  items.forEach((d, i) => {
    const y = T + i * rowH, w = (W - L - R) * d.value / max;
    el("text", { x: L - 8, y: y + rowH / 2 + 4, "text-anchor": "end" }, svg, d.label);
    const bar = el("rect", { x: L, y: y + 5, width: Math.max(1, w), height: rowH - 10, rx: 3, fill: c }, svg);
    el("title", {}, bar, `${d.label}: ${fmt(d.value)}${suffix}`);
    el("text", { x: L + w + 6, y: y + rowH / 2 + 4 }, svg, fmt(d.value) + suffix);
  });
}

/* ---------- vertical column chart ---------- */
function columnChart(id, items, opts = {}) {
  const W = widthOf(id), H = 260, L = 40, R = 10, T = 22, B = 34;
  const svg = svgIn(id, W, H);
  const max = niceMax(Math.max(...items.map(d => d.value)));
  const bw = (W - L - R) / items.length;
  const c = opts.color || "#2a78d6", suffix = opts.suffix || "";
  for (let k = 0; k <= 4; k++) {
    const v = max * k / 4, y = T + (H - T - B) * (1 - k / 4);
    el("line", { x1: L, x2: W - R, y1: y, y2: y, stroke: "#ececea" }, svg);
    el("text", { x: L - 6, y: y + 4, "text-anchor": "end" }, svg, fmt(Math.round(v * 10) / 10));
  }
  items.forEach((d, i) => {
    const h = (H - T - B) * d.value / max, x = L + i * bw + bw * 0.2;
    const bar = el("rect", { x, y: H - B - h, width: bw * 0.6, height: h, rx: 3, fill: (opts.colors || [])[i] || c }, svg);
    el("title", {}, bar, `${d.label}: ${fmt(d.value)}${suffix}`);
    el("text", { x: x + bw * 0.3, y: H - B - h - 6, "text-anchor": "middle" }, svg, fmt(d.value) + suffix);
    el("text", { x: x + bw * 0.3, y: H - 12, "text-anchor": "middle" }, svg, d.label);
  });
}

/* ---------- donut (pie) chart ---------- */
function donutChart(id, items, centerText) {
  const W = 420, H = 230, cx = 115, cy = 115, R = 100, r = 60;
  const svg = svgIn(id, W, H);
  const total = items.reduce((s, d) => s + d.value, 0);
  const colors = ["#e57fa5", "#6650d6", "#e9a10b", "#2a78d6", "#1fa774"];
  let a = -Math.PI / 2;
  items.forEach((d, i) => {
    const a2 = a + 2 * Math.PI * d.value / total, big = a2 - a > Math.PI ? 1 : 0;
    const p = (ang, rad) => `${cx + rad * Math.cos(ang)},${cy + rad * Math.sin(ang)}`;
    const path = el("path", { d: `M${p(a, R)} A${R},${R} 0 ${big} 1 ${p(a2, R)} L${p(a2, r)} A${r},${r} 0 ${big} 0 ${p(a, r)} Z`,
                              fill: colors[i], stroke: "#fff", "stroke-width": 2 }, svg);
    el("title", {}, path, `${d.label}: ${fmt(d.value)} (${Math.round(100 * d.value / total)}%)`);
    el("rect", { x: 250, y: 50 + i * 40, width: 13, height: 13, rx: 2, fill: colors[i] }, svg);
    el("text", { x: 272, y: 61 + i * 40, style: "font-size:14px" }, svg,
       `${d.label}  ${Math.round(100 * d.value / total)}%`);
    a = a2;
  });
  el("text", { x: cx, y: cy + 2, "text-anchor": "middle", style: "font-size:24px;font-weight:600;fill:#1d1d1b" }, svg, fmt(total));
  el("text", { x: cx, y: cy + 22, "text-anchor": "middle" }, svg, centerText || "");
}

/* ---------- bars + line (daily bookings + 7-day average) ---------- */
function comboChart(id, labels, bars, line) {
  const W = widthOf(id), H = 280, L = 34, R = 10, T = 12, B = 34;
  const svg = svgIn(id, W, H);
  const max = niceMax(Math.max(...bars, ...line));
  const bw = (W - L - R) / labels.length;
  const y = v => T + (H - T - B) * (1 - v / max);
  for (let k = 0; k <= 4; k++) {
    const v = max * k / 4;
    el("line", { x1: L, x2: W - R, y1: y(v), y2: y(v), stroke: "#ececea" }, svg);
    el("text", { x: L - 6, y: y(v) + 4, "text-anchor": "end" }, svg, fmt(Math.round(v)));
  }
  bars.forEach((v, i) => {
    const bar = el("rect", { x: L + i * bw + 1, y: y(v), width: bw - 2, height: y(0) - y(v), fill: "#1fa774" }, svg);
    el("title", {}, bar, `${labels[i]}: ${v} bookings (7-day avg ${line[i]})`);
    if (i % 7 === 0) el("text", { x: L + i * bw + bw / 2, y: H - 12, "text-anchor": "middle" }, svg, labels[i].slice(5));
  });
  el("polyline", { points: line.map((v, i) => `${L + i * bw + bw / 2},${y(v)}`).join(" "),
                   fill: "none", stroke: "#1d1d1b", "stroke-width": 1.8 }, svg);
  legend(id, ["Bookings per day", "7-day average"], ["#1fa774", "#1d1d1b"]);
}

/* ---------- heat map (HTML table, darker blue = more bookings) ---------- */
function heatMap(id, rows, cols, grid) {
  const max = Math.max(...grid.flat()), min = Math.min(...grid.flat());
  let html = "<table class='heat'><tr><th></th>" + cols.map(c => `<th>${c}</th>`).join("") + "</tr>";
  rows.forEach((r, i) => {
    html += `<tr><th style="text-align:right">${r}</th>`;
    grid[i].forEach(v => {
      const t = (v - min) / Math.max(1, max - min);                 // 0 = quiet, 1 = busiest
      const light = Math.round(92 - t * 62);                          // lightness 92% -> 30%
      html += `<td class="${t < 0.45 ? "dark-text" : ""}" style="background:hsl(214,68%,${light}%)" title="${r} ${v}">${v}</td>`;
    });
    html += "</tr>";
  });
  document.getElementById(id).innerHTML = html + "</table>";
}
