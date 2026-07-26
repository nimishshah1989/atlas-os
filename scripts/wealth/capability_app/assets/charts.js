/* Wealth glass-box capability app — hand-rolled SVG chart kit, no dependencies.
 *
 * Every chart form is `Charts.<name>(el, data, opts) -> void`. `el` is the
 * `.chart-card` container DOM node (see app.css); each call clears `el` and
 * appends: an SVG, a legend (only when >=2 series), and a hidden `.table-view`
 * (the WCAG-clean accessibility twin) wired to a toggle button — per the
 * dataviz skill's interaction rules (glass-box design spec section 5/11).
 *
 * Colors are ALWAYS read from CSS custom properties via cssVar() — never a
 * hardcoded hex in this file. Untrusted strings (client/fund names) always go
 * through `textContent`, never string-concatenated into markup.
 *
 * This file holds shared helpers + the "simple" chart forms (one axis, one
 * series-shape). See charts-composite.js for treemap / divergingStackedBar /
 * heatmap / lineArea / stackedSharedX, which reuse the helpers below (both
 * files are inlined into one <script> block at build time, sharing scope).
 */
var Charts = {};

var SVG_NS = "http://www.w3.org/2000/svg";

/* ---------- shared helpers ---------- */

function cssVar(el, name, fallback) {
  var v = getComputedStyle(el).getPropertyValue(name);
  v = v && v.trim();
  return v || fallback || "#888";
}

function svgEl(tag, attrs) {
  var n = document.createElementNS(SVG_NS, tag);
  for (var k in attrs) {
    if (attrs[k] != null) n.setAttribute(k, attrs[k]);
  }
  return n;
}

function svgText(x, y, str, attrs) {
  var t = svgEl("text", Object.assign({ x: x, y: y }, attrs || {}));
  t.textContent = str == null ? "" : String(str);
  return t;
}

function defaultFmt(v) {
  if (v == null || isNaN(v)) return "—";
  return Math.abs(v) >= 1000 ? Math.round(v).toLocaleString("en-IN") : (Math.round(v * 10) / 10).toString();
}

/* linear scale: value in [dMin,dMax] -> pixel in [rMin,rMax] */
function linScale(dMin, dMax, rMin, rMax) {
  var span = dMax - dMin || 1;
  return function (v) {
    return rMin + ((v - dMin) / span) * (rMax - rMin);
  };
}

/* real fund/category names run long (30+ chars) and the left label gutter is
   fixed-width — without this a long label silently overflows past the card,
   even off the page (found by eyeballing the scratch preview). Character-
   width heuristic (~0.5*fontSize for this sans stack), not a live text
   measurement — good enough for a truncate-with-ellipsis, not pixel-exact.
   ponytail: getComputedTextLength() would be exact but needs the node already
   attached to the DOM; this avoids a layout round-trip per label. */
function truncateLabel(str, maxWidth, fontSize) {
  str = str == null ? "" : String(str);
  var charW = fontSize * 0.5;
  var maxChars = Math.max(1, Math.floor(maxWidth / charW));
  if (str.length <= maxChars) return str;
  return str.slice(0, Math.max(1, maxChars - 1)) + "…";
}

function niceMax(v) {
  if (v <= 0) return 1;
  var mag = Math.pow(10, Math.floor(Math.log10(v)));
  var n = v / mag;
  var step = n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10;
  return step * mag;
}

/* single shared tooltip element, reused across every chart on the page */
var _tooltipEl = null;
function ensureTooltip() {
  if (_tooltipEl) return _tooltipEl;
  _tooltipEl = document.createElement("div");
  _tooltipEl.className = "viz-tooltip";
  document.body.appendChild(_tooltipEl);
  return _tooltipEl;
}

/* rows: [{label, value, color}]; values lead, labels follow (dataviz rule) */
function showTooltip(clientX, clientY, title, rows) {
  var tt = ensureTooltip();
  tt.textContent = "";
  if (title) {
    var h = document.createElement("div");
    h.style.fontWeight = "700";
    h.style.marginBottom = "4px";
    h.textContent = title;
    tt.appendChild(h);
  }
  rows.forEach(function (r) {
    var row = document.createElement("div");
    row.className = "row";
    var b = document.createElement("b");
    b.textContent = r.value;
    var lab = document.createElement("span");
    if (r.color) lab.style.color = r.color;
    lab.textContent = r.label;
    row.appendChild(b);
    row.appendChild(lab);
    tt.appendChild(row);
  });
  tt.style.left = Math.min(clientX + 14, window.innerWidth - 270) + "px";
  tt.style.top = Math.max(clientY - 12, 8) + "px";
  tt.classList.add("on");
}
function hideTooltip() {
  if (_tooltipEl) _tooltipEl.classList.remove("on");
}

/* attach a >=24px hit target around a mark that reports `rows` on hover/focus */
function wireHit(hitEl, title, rows) {
  hitEl.style.cursor = "pointer";
  hitEl.setAttribute("tabindex", "0");
  hitEl.addEventListener("pointermove", function (e) {
    showTooltip(e.clientX, e.clientY, title, rows);
  });
  hitEl.addEventListener("pointerleave", hideTooltip);
  hitEl.addEventListener("focus", function (e) {
    var r = hitEl.getBoundingClientRect();
    showTooltip(r.right, r.top, title, rows);
  });
  hitEl.addEventListener("blur", hideTooltip);
}

/* legend(container, items) — items: [{label, color, stroke:bool}]. Only call
   for >=2 series; the exhibit title already names a lone series. */
function legend(container, items) {
  if (!items || items.length < 2) return;
  var wrap = document.createElement("div");
  wrap.className = "legend";
  items.forEach(function (it) {
    var key = document.createElement("span");
    key.className = "key";
    var sw = document.createElement("span");
    sw.className = it.stroke ? "stroke" : "swatch";
    sw.style.background = it.stroke ? "none" : it.color;
    if (it.stroke) {
      sw.style.borderTop = "2px solid " + it.color;
    }
    var lab = document.createElement("span");
    lab.textContent = it.label;
    key.appendChild(sw);
    key.appendChild(lab);
    wrap.appendChild(key);
  });
  container.appendChild(wrap);
}

/* tableView(columns, rows) — the WCAG-clean accessibility twin of a chart.
   columns: [{key, label, numeric}]. Every value a chart can show must also be
   reachable here (nothing is tooltip-only). Exposed as Charts.tableView too
   for exhibits that want a standalone evidence table. */
function tableView(columns, rows) {
  var t = document.createElement("table");
  t.className = "table-view";
  var thead = document.createElement("thead");
  var htr = document.createElement("tr");
  columns.forEach(function (c) {
    var th = document.createElement("th");
    if (c.numeric) th.className = "n";
    th.textContent = c.label;
    htr.appendChild(th);
  });
  thead.appendChild(htr);
  t.appendChild(thead);
  var tbody = document.createElement("tbody");
  rows.forEach(function (r) {
    var tr = document.createElement("tr");
    columns.forEach(function (c) {
      var td = document.createElement("td");
      if (c.numeric) td.className = "n";
      var v = r[c.key];
      td.textContent = c.fmt ? c.fmt(v) : v == null ? "—" : String(v);
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
  t.appendChild(tbody);
  return t;
}
Charts.tableView = tableView;

/* chartShell(el) — clears el, adds the "Table view" toggle button, returns
   {svg, addTable(columns, rows)} for chart forms to fill in. */
function chartShell(el, svgAttrs) {
  el.textContent = "";
  var btn = document.createElement("button");
  btn.type = "button";
  btn.className = "table-toggle";
  btn.textContent = "Table view";
  el.appendChild(btn);
  var svg = svgEl("svg", Object.assign({ viewBox: "0 0 480 260", role: "img" }, svgAttrs || {}));
  el.appendChild(svg);
  var tableEl = null;
  btn.addEventListener("click", function () {
    var showingTable = svg.classList.toggle("hidden");
    if (tableEl) tableEl.classList.toggle("on", showingTable);
    btn.textContent = showingTable ? "Chart view" : "Table view";
  });
  return {
    svg: svg,
    addTable: function (columns, rows) {
      tableEl = tableView(columns, rows);
      el.appendChild(tableEl);
    },
  };
}

/* ---------- stat tile / hero ---------- */
/* data: {label, value, delta?, deltaDirection?:'up'|'down', honesty?}
   opts: {hero:bool} — hero uses the big serif numeral, otherwise a compact
   KPI tile (matches .kpi-tile in app.css; KPI strips can also be built
   directly in HTML — this exists for JS-driven tile grids). */
Charts.statTile = function (el, data, opts) {
  opts = opts || {};
  el.textContent = "";
  el.className = opts.hero ? "" : "kpi-tile";
  var label = document.createElement("div");
  label.className = opts.hero ? "eyebrow" : "kpi-label";
  label.textContent = data.label;
  var value = document.createElement("div");
  value.className = opts.hero ? "big" : "kpi-value";
  value.textContent = data.value;
  el.appendChild(label);
  el.appendChild(value);
  if (data.delta != null) {
    var d = document.createElement("div");
    d.className = "kpi-delta " + (data.deltaDirection || "");
    d.textContent = data.delta;
    el.appendChild(d);
  }
  if (data.honesty) {
    var chip = document.createElement("span");
    chip.className = "chip chip--" + data.honesty.replace(/\s+/g, "-");
    chip.textContent = data.honesty;
    chip.style.marginTop = "6px";
    chip.style.display = "inline-block";
    el.appendChild(chip);
  }
};

/* ---------- histogram ---------- */
/* data: {edges:[n+1], counts:[n], median, n} — exact shape of
   capability_app/data.py's _hist(). opts: {fmt, unit, medianLabel} */
Charts.histogram = function (el, data, opts) {
  opts = opts || {};
  var fmt = opts.fmt || defaultFmt;
  var W = 480,
    H = 260,
    padL = 36,
    padB = 28,
    padT = 10,
    padR = 10;
  var shell = chartShell(el, { viewBox: "0 0 " + W + " " + H });
  var svg = shell.svg;
  var edges = data.edges,
    counts = data.counts;
  var maxCount = niceMax(Math.max.apply(null, counts.concat([1])));
  var x = linScale(edges[0], edges[edges.length - 1], padL, W - padR);
  var y = linScale(0, maxCount, H - padB, padT);
  svg.appendChild(svgEl("line", { x1: padL, x2: W - padR, y1: H - padB, y2: H - padB, stroke: cssVar(el, "--line") }));
  var barColor = cssVar(el, "--accent");
  counts.forEach(function (c, i) {
    var x0 = x(edges[i]),
      x1 = x(edges[i + 1]);
    var barW = Math.max(1, x1 - x0 - 2); /* ponytail: 2px gap approximated by shrinking width, not a paint-order separator */
    var barY = y(c);
    var rect = svgEl("rect", { x: x0 + 1, y: barY, width: barW, height: H - padB - barY, fill: barColor, rx: 3 });
    svg.appendChild(rect);
    var hit = svgEl("rect", { x: x0, y: padT, width: x1 - x0, height: H - padB - padT, fill: "transparent" });
    svg.appendChild(hit);
    wireHit(hit, fmt(edges[i]) + "–" + fmt(edges[i + 1]) + (opts.unit || ""), [{ label: "clients", value: String(c) }]);
  });
  if (data.median != null) {
    var mx = x(data.median);
    svg.appendChild(svgEl("line", { x1: mx, x2: mx, y1: padT, y2: H - padB, stroke: cssVar(el, "--muted"), "stroke-width": 1, "stroke-dasharray": "3 3" }));
    svg.appendChild(svgText(mx, padT - 2, (opts.medianLabel || "median") + " " + fmt(data.median), { "text-anchor": "middle", "font-size": 10, fill: "var(--muted)" }));
  }
  svg.appendChild(svgText(padL, H - 8, fmt(edges[0]), { "font-size": 10, fill: "var(--muted)" }));
  svg.appendChild(svgText(W - padR, H - 8, fmt(edges[edges.length - 1]), { "font-size": 10, fill: "var(--muted)", "text-anchor": "end" }));
  shell.addTable(
    [
      { key: "range", label: "Range" },
      { key: "n", label: "Clients", numeric: true },
    ],
    counts.map(function (c, i) {
      return { range: fmt(edges[i]) + "–" + fmt(edges[i + 1]), n: c };
    })
  );
};

/* ---------- horizontal bar ---------- */
/* data: [{label, value}]. opts: {fmt, sort:true, color:'--accent'} */
Charts.horizontalBar = function (el, data, opts) {
  opts = opts || {};
  var fmt = opts.fmt || defaultFmt;
  var rows = opts.sort === false ? data.slice() : data.slice().sort(function (a, b) { return b.value - a.value; });
  var W = 480,
    padL = 140,
    padR = 50,
    rowH = 26,
    H = rows.length * rowH + 20;
  var shell = chartShell(el, { viewBox: "0 0 " + W + " " + H });
  var svg = shell.svg;
  var maxV = niceMax(Math.max.apply(null, rows.map(function (r) { return r.value; }).concat([1])));
  var x = linScale(0, maxV, padL, W - padR);
  var color = cssVar(el, opts.color || "--accent");
  rows.forEach(function (r, i) {
    var cy = 10 + i * rowH;
    var barH = Math.min(22, rowH - 6);
    var x1 = x(r.value);
    svg.appendChild(svgText(padL - 8, cy + barH / 2 + 4, truncateLabel(r.label, padL - 12, 11), { "text-anchor": "end", "font-size": 11, fill: "var(--ink)" }));
    var rect = svgEl("rect", { x: padL, y: cy, width: Math.max(0, x1 - padL), height: barH, fill: color, rx: 3 });
    svg.appendChild(rect);
    // ponytail: no value label here (brief: never print a number on every mark) —
    // wireHit tooltip + table-view toggle below already carry the value.
    var hit = svgEl("rect", { x: 0, y: cy - 2, width: W, height: barH + 4, fill: "transparent" });
    svg.appendChild(hit);
    wireHit(hit, r.label, [{ label: "value", value: fmt(r.value) }]);
  });
  shell.addTable(
    [
      { key: "label", label: "" },
      { key: "value", label: "Value", numeric: true, fmt: fmt },
    ],
    rows
  );
};

/* ---------- diverging bar strip ---------- */
/* data: [{label, value}] — value diverges around 0 (e.g. excess return pp/yr).
   opts: {fmt, zeroLabel} — two-hue diverging palette, not per-item color. */
Charts.divergingBarStrip = function (el, data, opts) {
  opts = opts || {};
  var fmt = opts.fmt || defaultFmt;
  var rows = data.slice().sort(function (a, b) { return b.value - a.value; });
  var W = 480,
    padL = 10,
    padR = 10,
    rowH = 14,
    H = rows.length * rowH + 20;
  var shell = chartShell(el, { viewBox: "0 0 " + W + " " + H });
  var svg = shell.svg;
  var ext = Math.max.apply(null, rows.map(function (r) { return Math.abs(r.value); }).concat([1]));
  var maxV = niceMax(ext);
  var mid = W / 2;
  var x = linScale(-maxV, maxV, padL, W - padR);
  var posColor = cssVar(el, "--div-pos-1");
  var negColor = cssVar(el, "--div-neg-1");
  svg.appendChild(svgEl("line", { x1: mid, x2: mid, y1: 6, y2: H - 14, stroke: cssVar(el, "--line") }));
  rows.forEach(function (r, i) {
    var cy = 10 + i * rowH;
    var barH = Math.min(10, rowH - 3);
    var x0 = x(0),
      x1 = x(r.value);
    var rect = svgEl("rect", {
      x: Math.min(x0, x1),
      y: cy,
      width: Math.max(1, Math.abs(x1 - x0)),
      height: barH,
      fill: r.value >= 0 ? posColor : negColor,
      rx: 2,
    });
    svg.appendChild(rect);
    var hit = svgEl("rect", { x: 0, y: cy - 1, width: W, height: barH + 2, fill: "transparent" });
    svg.appendChild(hit);
    wireHit(hit, r.label, [{ label: opts.valueLabel || "value", value: fmt(r.value) }]);
  });
  svg.appendChild(svgText(mid, H - 4, opts.zeroLabel || "0", { "text-anchor": "middle", "font-size": 9, fill: "var(--muted)" }));
  shell.addTable(
    [
      { key: "label", label: "" },
      { key: "value", label: "Value", numeric: true, fmt: fmt },
    ],
    rows
  );
};

/* ---------- dumbbell ---------- */
/* data: [{label, a, b}]. opts: {fmt, aLabel, bLabel, aColor:'--muted',
   bColor:'--accent'} — e.g. Q4's regular-vs-direct expense ratio. */
Charts.dumbbell = function (el, data, opts) {
  opts = opts || {};
  var fmt = opts.fmt || defaultFmt;
  var rows = data;
  var W = 480,
    padL = 130,
    padR = 40,
    rowH = 30,
    H = rows.length * rowH + 20;
  var shell = chartShell(el, { viewBox: "0 0 " + W + " " + H });
  var svg = shell.svg;
  var all = [];
  rows.forEach(function (r) {
    all.push(r.a, r.b);
  });
  var maxV = niceMax(Math.max.apply(null, all.concat([1])));
  var x = linScale(0, maxV, padL, W - padR);
  var aColor = cssVar(el, opts.aColor || "--muted");
  var bColor = cssVar(el, opts.bColor || "--accent");
  legend(el, [
    { label: opts.aLabel || "A", color: aColor },
    { label: opts.bLabel || "B", color: bColor },
  ]);
  rows.forEach(function (r, i) {
    var cy = 14 + i * rowH;
    svg.appendChild(svgText(padL - 8, cy + 4, truncateLabel(r.label, padL - 12, 11), { "text-anchor": "end", "font-size": 11, fill: "var(--ink)" }));
    var xa = x(r.a),
      xb = x(r.b);
    svg.appendChild(svgEl("line", { x1: xa, x2: xb, y1: cy, y2: cy, stroke: cssVar(el, "--line"), "stroke-width": 2 }));
    [
      { v: r.a, cx: xa, color: aColor, label: opts.aLabel || "A" },
      { v: r.b, cx: xb, color: bColor, label: opts.bLabel || "B" },
    ].forEach(function (pt) {
      var c = svgEl("circle", { cx: pt.cx, cy: cy, r: 5, fill: pt.color, stroke: cssVar(el, "--card"), "stroke-width": 2 });
      svg.appendChild(c);
      var hit = svgEl("circle", { cx: pt.cx, cy: cy, r: 12, fill: "transparent" });
      svg.appendChild(hit);
      wireHit(hit, r.label, [{ label: pt.label, value: fmt(pt.v), color: pt.color }]);
    });
  });
  shell.addTable(
    [
      { key: "label", label: "" },
      { key: "a", label: opts.aLabel || "A", numeric: true, fmt: fmt },
      { key: "b", label: opts.bLabel || "B", numeric: true, fmt: fmt },
    ],
    rows
  );
};

/* ---------- scatter ---------- */
/* data: [{label, x, y, size?}]. opts: {xFmt, yFmt, xLabel, yLabel, onClick} */
Charts.scatter = function (el, data, opts) {
  opts = opts || {};
  var xFmt = opts.xFmt || defaultFmt;
  var yFmt = opts.yFmt || defaultFmt;
  var W = 480,
    H = 320,
    padL = 44,
    padB = 30,
    padT = 14,
    padR = 14;
  var shell = chartShell(el, { viewBox: "0 0 " + W + " " + H });
  var svg = shell.svg;
  var xs = data.map(function (d) { return d.x; });
  var ys = data.map(function (d) { return d.y; });
  var xMin = Math.min.apply(null, xs.concat([0])),
    xMax = niceMax(Math.max.apply(null, xs.concat([1])));
  var yMin = Math.min.apply(null, ys.concat([0])),
    yMax = niceMax(Math.max.apply(null, ys.concat([1])));
  var x = linScale(xMin, xMax, padL, W - padR);
  var y = linScale(yMin, yMax, H - padB, padT);
  svg.appendChild(svgEl("line", { x1: padL, x2: W - padR, y1: H - padB, y2: H - padB, stroke: cssVar(el, "--line") }));
  svg.appendChild(svgEl("line", { x1: padL, x2: padL, y1: padT, y2: H - padB, stroke: cssVar(el, "--line") }));
  var color = cssVar(el, "--accent");
  data.forEach(function (d) {
    var r = d.size ? Math.max(4, Math.min(14, d.size)) : 4.5;
    var c = svgEl("circle", { cx: x(d.x), cy: y(d.y), r: r, fill: color, opacity: 0.65, stroke: cssVar(el, "--card"), "stroke-width": 1.5 });
    svg.appendChild(c);
    var hit = svgEl("circle", { cx: x(d.x), cy: y(d.y), r: Math.max(12, r), fill: "transparent" });
    svg.appendChild(hit);
    wireHit(hit, d.label, [
      { label: opts.xLabel || "x", value: xFmt(d.x) },
      { label: opts.yLabel || "y", value: yFmt(d.y) },
    ]);
    if (opts.onClick) hit.addEventListener("click", function () { opts.onClick(d); });
  });
  shell.addTable(
    [
      { key: "label", label: "" },
      { key: "x", label: opts.xLabel || "x", numeric: true, fmt: xFmt },
      { key: "y", label: opts.yLabel || "y", numeric: true, fmt: yFmt },
    ],
    data
  );
};
