/* Wealth glass-box capability app — composite/annotated SVG chart forms.
 * Continues charts.js (shared helpers: cssVar/svgEl/svgText/linScale/niceMax/
 * chartShell/legend/wireHit/tableView — reused here, not redefined). Both
 * files are inlined into one <script> block at build time and share scope.
 *
 * Forms in this file: treemap, divergingStackedBar, heatmap, lineArea
 * (+ emphasis series / shaded crisis windows / event markers), stackedSharedX
 * (the mandated replacement for any dual-axis chart — never build dual-axis).
 */

function _hashStr(s) {
  var h = 0;
  for (var i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
  return Math.abs(h);
}
/* keys: the ordered list of unique identities in THIS render (so two keys
   never collide as long as there are <=7 of them — brief's cap, task-3-brief.md:49)
   — falls back to a hash only if the caller can't supply the full set.
   ponytail: index-in-set beats hashing for our real category counts (<=7),
   so just require it. */
function _seriesColor(el, key, keys) {
  var idx = keys ? keys.indexOf(String(key)) : -1;
  if (idx < 0) idx = _hashStr(String(key));
  return cssVar(el, "--series-" + ((idx % 7) + 1));
}

/* ---------- treemap ---------- */
/* data: [{...levelKeys, value}] flat leaf rows, e.g. capability_app's Q1
   treemap shape [{category,amc,fund,value_cr}]. opts: {levels:['category',
   'amc','fund'], valueKey:'value_cr', fmt}. Click a cell to descend one
   level; breadcrumb resets to the top. Simple binary slice-and-dice layout
   (not squarified) — ponytail: good enough for <=15 cells at a time, a
   squarified layout is unnecessary complexity for this data volume. */
Charts.treemap = function (el, data, opts) {
  opts = opts || {};
  var levels = opts.levels || ["category", "amc", "fund"];
  var valueKey = opts.valueKey || "value";
  var fmt = opts.fmt || defaultFmt;
  var W = 480,
    H = 300;

  function aggregate(depth, path) {
    var filtered = data.filter(function (r) {
      return path.every(function (p, i) {
        return r[levels[i]] === p;
      });
    });
    var groups = {};
    filtered.forEach(function (r) {
      var k = r[levels[depth]];
      groups[k] = (groups[k] || 0) + (r[valueKey] || 0);
    });
    return Object.keys(groups)
      .map(function (k) {
        return { key: k, value: groups[k] };
      })
      .sort(function (a, b) {
        return b.value - a.value;
      });
  }

  function sliceLayout(items, x0, y0, w, h, horiz) {
    if (items.length === 1) return [Object.assign({ x0: x0, y0: y0, w: w, h: h }, items[0])];
    var total = items.reduce(function (s, it) { return s + it.value; }, 0) || 1;
    var acc = 0,
      splitAt = 0,
      best = Infinity;
    for (var i = 1; i < items.length; i++) {
      acc += items[i - 1].value;
      var diff = Math.abs(acc / total - 0.5);
      if (diff < best) {
        best = diff;
        splitAt = i;
      }
    }
    var left = items.slice(0, splitAt),
      right = items.slice(splitAt);
    var leftSum = left.reduce(function (s, it) { return s + it.value; }, 0);
    var leftFrac = leftSum / total;
    if (horiz) {
      var lw = w * leftFrac;
      return sliceLayout(left, x0, y0, lw, h, !horiz).concat(sliceLayout(right, x0 + lw, y0, w - lw, h, !horiz));
    }
    var lh = h * leftFrac;
    return sliceLayout(left, x0, y0, w, lh, !horiz).concat(sliceLayout(right, x0, y0 + lh, w, h - lh, !horiz));
  }

  var path = [];
  function render() {
    el.textContent = "";
    var crumb = document.createElement("div");
    crumb.style.fontSize = ".78rem";
    crumb.style.color = "var(--muted)";
    crumb.style.marginBottom = "6px";
    var rootLink = document.createElement("a");
    rootLink.href = "javascript:void(0)";
    rootLink.textContent = "all";
    rootLink.addEventListener("click", function () {
      path = [];
      render();
    });
    crumb.appendChild(rootLink);
    path.forEach(function (p) {
      crumb.appendChild(document.createTextNode(" › " + p));
    });
    el.appendChild(crumb);

    var depth = path.length;
    var groups = aggregate(depth, path);
    var svg = svgEl("svg", { viewBox: "0 0 " + W + " " + H, role: "img" });
    el.appendChild(svg);
    var rects = sliceLayout(groups, 0, 0, W, H, true);
    var groupKeys = groups.map(function (g) { return g.key; });
    rects.forEach(function (r) {
      var color = _seriesColor(el, r.key, groupKeys);
      var rect = svgEl("rect", { x: r.x0 + 1, y: r.y0 + 1, width: Math.max(0, r.w - 2), height: Math.max(0, r.h - 2), fill: color, opacity: 0.85, rx: 3 });
      svg.appendChild(rect);
      // ponytail: label only, no value (brief: never print a number on every
      // mark) — wireHit tooltip + table-view + the legend below carry value/identity.
      if (r.w > 46 && r.h > 20) {
        svg.appendChild(svgText(r.x0 + 6, r.y0 + 16, r.key, { "font-size": 11, fill: "#fff", "font-weight": 600 }));
      }
      wireHit(rect, r.key, [{ label: "value", value: fmt(r.value) }]);
      if (depth < levels.length - 1) {
        rect.addEventListener("click", function () {
          path = path.concat([r.key]);
          render();
        });
      }
    });
    legend(el, groupKeys.map(function (k) { return { label: k, color: _seriesColor(el, k, groupKeys) }; }));
    var cols = [
      { key: "key", label: levels[depth] },
      { key: "value", label: "Value", numeric: true, fmt: fmt },
    ];
    el.appendChild(tableView(cols, groups));
  }
  render();
};

/* ---------- diverging stacked bar ---------- */
/* data: [{label, segments:[{key, value}]}] — value can be + or -; each
   row stacks negative segments leftward and positive segments rightward from
   a shared zero baseline. opts: {fmt, keyColors:{key:'--var'}} — default
   colors: 'good'/'warn'/'crit'/'neutral' keys map to those status tokens
   (genuine flagged states, e.g. B4's good|neutral|bad switch verdicts),
   anything else falls back to a stable categorical slot. */
Charts.divergingStackedBar = function (el, data, opts) {
  opts = opts || {};
  var fmt = opts.fmt || defaultFmt;
  var keyColors = opts.keyColors || { good: "--good", warn: "--warn", neutral: "--muted", bad: "--crit", crit: "--crit" };
  var segKeys = [];
  data.forEach(function (row) {
    row.segments.forEach(function (s) {
      if (segKeys.indexOf(s.key) === -1) segKeys.push(s.key);
    });
  });
  function colorFor(k) {
    return keyColors[k] ? cssVar(el, keyColors[k]) : _seriesColor(el, k, segKeys);
  }
  var W = 480,
    padL = 110,
    padR = 20,
    rowH = 28,
    H = data.length * rowH + 20;
  var shell = chartShell(el, { viewBox: "0 0 " + W + " " + H });
  var svg = shell.svg;
  var maxSide = 1;
  data.forEach(function (row) {
    var neg = 0,
      pos = 0;
    row.segments.forEach(function (s) {
      if (s.value < 0) neg += -s.value;
      else pos += s.value;
    });
    maxSide = Math.max(maxSide, neg, pos);
  });
  maxSide = niceMax(maxSide);
  var mid = padL + (W - padL - padR) / 2;
  var x = linScale(-maxSide, maxSide, padL, W - padR);
  svg.appendChild(svgEl("line", { x1: mid, x2: mid, y1: 6, y2: H - 14, stroke: cssVar(el, "--line") }));
  var seenKeys = [];
  data.forEach(function (row, i) {
    var cy = 10 + i * rowH;
    var barH = Math.min(18, rowH - 8);
    svg.appendChild(svgText(padL - 8, cy + barH / 2 + 4, row.label, { "text-anchor": "end", "font-size": 11, fill: "var(--ink)" }));
    var negCursor = 0,
      posCursor = 0;
    row.segments.forEach(function (s) {
      if (seenKeys.indexOf(s.key) === -1) seenKeys.push(s.key);
      var color = colorFor(s.key);
      var x0, x1;
      if (s.value < 0) {
        x0 = x(-negCursor);
        negCursor += -s.value;
        x1 = x(-negCursor);
      } else {
        x0 = x(posCursor);
        posCursor += s.value;
        x1 = x(posCursor);
      }
      var rect = svgEl("rect", { x: Math.min(x0, x1), y: cy, width: Math.max(0.5, Math.abs(x1 - x0)), height: barH, fill: color });
      svg.appendChild(rect);
      wireHit(rect, row.label, [{ label: s.key, value: fmt(s.value), color: color }]);
    });
  });
  legend(el, seenKeys.map(function (k) { return { label: k, color: colorFor(k) }; }));
  var cols = [{ key: "label", label: "" }].concat(
    seenKeys.map(function (k) {
      return { key: k, label: k, numeric: true, fmt: fmt };
    })
  );
  var rows = data.map(function (row) {
    var o = { label: row.label };
    row.segments.forEach(function (s) {
      o[s.key] = s.value;
    });
    return o;
  });
  shell.addTable(cols, rows);
};

/* ---------- heatmap ---------- */
/* data: {rowLabels:[...], colLabels:[...], cells:[{row, col, value}]} where
   cell.row/col match entries in rowLabels/colLabels exactly (caller maps its
   real pair rows, e.g. Q3's top15_pairwise {scheme_a,scheme_b,overlap_pct},
   into this shape). opts: {fmt, max, colorVar:'--seq'} sequential magnitude
   ramp (--seq-1..6), never categorical. */
Charts.heatmap = function (el, data, opts) {
  opts = opts || {};
  var fmt = opts.fmt || defaultFmt;
  var rows = data.rowLabels,
    cols = data.colLabels;
  var lookup = {};
  data.cells.forEach(function (c) {
    lookup[c.row + "|" + c.col] = c.value;
  });
  var max = opts.max || Math.max.apply(null, data.cells.map(function (c) { return c.value; }).concat([1]));
  var padL = 90,
    /* real fund names rotated -40deg at the top swing tall enough to collide
       with the chart-card's absolute-positioned "Table view" toggle (found
       eyeballing the scratch preview) — padT sized for a truncated label. */
    padT = 78,
    cell = Math.min(26, Math.floor((480 - padL) / cols.length));
  var W = padL + cell * cols.length + 10,
    H = padT + cell * rows.length + 10;
  var shell = chartShell(el, { viewBox: "0 0 " + W + " " + H });
  var svg = shell.svg;
  var steps = ["--seq-1", "--seq-2", "--seq-3", "--seq-4", "--seq-5", "--seq-6"].map(function (v) {
    return cssVar(el, v);
  });
  function colorFor(v) {
    if (v == null) return "transparent";
    var frac = Math.max(0, Math.min(1, v / max));
    return steps[Math.min(steps.length - 1, Math.floor(frac * steps.length))];
  }
  rows.forEach(function (r, ri) {
    svg.appendChild(svgText(padL - 6, padT + ri * cell + cell / 2 + 4, truncateLabel(r, padL - 6, 9), { "text-anchor": "end", "font-size": 9, fill: "var(--muted)" }));
  });
  cols.forEach(function (c, ci) {
    svg.appendChild(
      svgText(padL + ci * cell + cell / 2, padT - 4, truncateLabel(c, 95, 9), {
        "text-anchor": "start",
        "font-size": 9,
        fill: "var(--muted)",
        transform: "rotate(-40 " + (padL + ci * cell + cell / 2) + " " + (padT - 4) + ")",
      })
    );
  });
  var tableRows = [];
  rows.forEach(function (r, ri) {
    cols.forEach(function (c, ci) {
      var v = lookup[r + "|" + c];
      // ponytail: --seq-1 (palest step) fails WCAG contrast vs --paper (validate_palette.js
      // --ordinal, both modes) — a stroke keeps the low-magnitude cell visible without
      // touching the ramp itself.
      var rect = svgEl("rect", { x: padL + ci * cell + 1, y: padT + ri * cell + 1, width: cell - 2, height: cell - 2, fill: colorFor(v), stroke: "var(--line)", "stroke-width": 1, rx: 2 });
      svg.appendChild(rect);
      if (v != null) {
        wireHit(rect, r + " × " + c, [{ label: "overlap", value: fmt(v) }]);
        tableRows.push({ row: r, col: c, value: v });
      }
    });
  });
  shell.addTable(
    [
      { key: "row", label: "" },
      { key: "col", label: "" },
      { key: "value", label: "Value", numeric: true, fmt: fmt },
    ],
    tableRows
  );
};

/* ---------- line / area ---------- */
/* series: [{label, points:[{x,y}], emphasis?:bool}] — x is any monotonic
   numeric (build-time convert dates to ordinal indices/timestamps first).
   opts: {area:bool, xFmt, yFmt, xTickLabels:[...], shadedWindows:[{x0,x1,
   label}], events:[{x,label,kind}]} — the 3 composable additions. Emphasis
   series draw in accent (thicker); non-emphasis draw in muted gray — the
   "emphasis + gray" book-vs-index pairing, never a 3rd unrelated hue. */
Charts.lineArea = function (el, series, opts) {
  opts = opts || {};
  var xFmt = opts.xFmt || defaultFmt;
  var yFmt = opts.yFmt || defaultFmt;
  var W = 560,
    H = 260,
    padL = 46,
    padR = 14,
    padT = 16,
    padB = 26;
  var shell = chartShell(el, { viewBox: "0 0 " + W + " " + H });
  var svg = shell.svg;
  var allPts = [].concat.apply([], series.map(function (s) { return s.points; }));
  var xs = allPts.map(function (p) { return p.x; }),
    ys = allPts.map(function (p) { return p.y; });
  var xMin = Math.min.apply(null, xs),
    xMax = Math.max.apply(null, xs);
  var yMin = Math.min(0, Math.min.apply(null, ys)),
    yMax = niceMax(Math.max.apply(null, ys.concat([1])));
  var x = linScale(xMin, xMax, padL, W - padR);
  var y = linScale(yMin, yMax, H - padB, padT);

  (opts.shadedWindows || []).forEach(function (w) {
    var rect = svgEl("rect", { x: x(w.x0), y: padT, width: Math.max(0, x(w.x1) - x(w.x0)), height: H - padB - padT, fill: cssVar(el, "--crit"), opacity: 0.08 });
    svg.appendChild(rect);
  });
  svg.appendChild(svgEl("line", { x1: padL, x2: W - padR, y1: H - padB, y2: H - padB, stroke: cssVar(el, "--line") }));
  svg.appendChild(svgEl("line", { x1: padL, x2: padL, y1: padT, y2: H - padB, stroke: cssVar(el, "--line") }));

  var legendItems = [];
  series.forEach(function (s) {
    var color = s.emphasis ? cssVar(el, "--accent") : cssVar(el, "--muted");
    legendItems.push({ label: s.label, color: color, stroke: true });
    var d = s.points
      .map(function (p, i) {
        return (i === 0 ? "M" : "L") + x(p.x).toFixed(1) + "," + y(p.y).toFixed(1);
      })
      .join(" ");
    if (opts.area) {
      var areaD = d + " L" + x(s.points[s.points.length - 1].x).toFixed(1) + "," + y(yMin).toFixed(1) + " L" + x(s.points[0].x).toFixed(1) + "," + y(yMin).toFixed(1) + " Z";
      svg.appendChild(svgEl("path", { d: areaD, fill: color, opacity: 0.1, stroke: "none" }));
    }
    svg.appendChild(svgEl("path", { d: d, fill: "none", stroke: color, "stroke-width": s.emphasis ? 2.5 : 2, "stroke-linejoin": "round", "stroke-linecap": "round" }));
    var hit = svgEl("path", { d: d, fill: "none", stroke: "transparent", "stroke-width": 16 });
    svg.appendChild(hit);
    wireHit(hit, s.label, [{ label: opts.yLabel || "value", value: yFmt(s.points[s.points.length - 1].y), color: color }]);
  });
  legend(el, legendItems);

  (opts.events || []).forEach(function (ev) {
    var ex = x(ev.x);
    var mark = svgEl("circle", { cx: ex, cy: padT + 4, r: 4, fill: cssVar(el, "--warn"), stroke: cssVar(el, "--card"), "stroke-width": 1.5 });
    svg.appendChild(mark);
    wireHit(mark, ev.label, [{ label: "event", value: ev.kind || "" }]);
  });

  svg.appendChild(svgText(padL, H - 6, xFmt(xMin), { "font-size": 9, fill: "var(--muted)" }));
  svg.appendChild(svgText(W - padR, H - 6, xFmt(xMax), { "font-size": 9, fill: "var(--muted)", "text-anchor": "end" }));

  var cols = [
    { key: "series", label: "" },
    { key: "x", label: opts.xLabel || "x" },
    { key: "y", label: opts.yLabel || "value", numeric: true, fmt: yFmt },
  ];
  var tableRows = [];
  series.forEach(function (s) {
    s.points.forEach(function (p) {
      tableRows.push({ series: s.label, x: xFmt(p.x), y: p.y });
    });
  });
  shell.addTable(cols, tableRows);
};

/* ---------- stacked-shared-x panel pair ---------- */
/* panels: [{label, type:'line'|'bar', points:[{x,y}], emphasis?:bool}] —
   THE mandated replacement for any dual-axis chart: panels stack vertically,
   share one x domain, each keeps its OWN y-scale. x-axis ticks render once,
   under the bottom panel only. opts: {xFmt, yFmt} */
Charts.stackedSharedX = function (el, panels, opts) {
  opts = opts || {};
  var xFmt = opts.xFmt || defaultFmt;
  var yFmt = opts.yFmt || defaultFmt;
  var W = 560,
    panelH = 130,
    padL = 46,
    padR = 14,
    padT = 14,
    padB = 20,
    gap = 22;
  var H = panels.length * (panelH + gap) - gap + padB;
  var shell = chartShell(el, { viewBox: "0 0 " + W + " " + H });
  var svg = shell.svg;
  var allX = [].concat.apply([], panels.map(function (p) { return p.points.map(function (pt) { return pt.x; }); }));
  var xMin = Math.min.apply(null, allX),
    xMax = Math.max.apply(null, allX);
  var x = linScale(xMin, xMax, padL, W - padR);

  panels.forEach(function (panel, pi) {
    var top = pi * (panelH + gap);
    var ys = panel.points.map(function (p) { return p.y; });
    var yMin = Math.min(0, Math.min.apply(null, ys));
    var yMax = niceMax(Math.max.apply(null, ys.concat([1])));
    var y = linScale(yMin, yMax, top + panelH - padT, top + padT);
    svg.appendChild(svgText(padL, top + 10, panel.label, { "font-size": 10, fill: "var(--muted)", "font-weight": 600 }));
    svg.appendChild(svgEl("line", { x1: padL, x2: W - padR, y1: y(0), y2: y(0), stroke: cssVar(el, "--line") }));
    var color = panel.emphasis === false ? cssVar(el, "--muted") : cssVar(el, "--accent");
    if (panel.type === "bar") {
      var bw = Math.max(2, (W - padL - padR) / panel.points.length - 2);
      panel.points.forEach(function (p) {
        var px = x(p.x) - bw / 2;
        var py = Math.min(y(0), y(p.y));
        var rect = svgEl("rect", { x: px, y: py, width: bw, height: Math.abs(y(p.y) - y(0)), fill: p.y < 0 ? cssVar(el, "--div-neg-1") : color });
        svg.appendChild(rect);
        wireHit(rect, panel.label, [{ label: xFmt(p.x), value: yFmt(p.y) }]);
      });
    } else {
      var d = panel.points
        .map(function (p, i) {
          return (i === 0 ? "M" : "L") + x(p.x).toFixed(1) + "," + y(p.y).toFixed(1);
        })
        .join(" ");
      svg.appendChild(svgEl("path", { d: d, fill: "none", stroke: color, "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round" }));
      var hit = svgEl("path", { d: d, fill: "none", stroke: "transparent", "stroke-width": 16 });
      svg.appendChild(hit);
      wireHit(hit, panel.label, [{ label: "latest", value: yFmt(panel.points[panel.points.length - 1].y) }]);
    }
    if (pi === panels.length - 1) {
      svg.appendChild(svgText(padL, H - 4, xFmt(xMin), { "font-size": 9, fill: "var(--muted)" }));
      svg.appendChild(svgText(W - padR, H - 4, xFmt(xMax), { "font-size": 9, fill: "var(--muted)", "text-anchor": "end" }));
    }
  });

  var cols = [
    { key: "panel", label: "" },
    { key: "x", label: opts.xLabel || "x" },
    { key: "y", label: opts.yLabel || "value", numeric: true, fmt: yFmt },
  ];
  var tableRows = [];
  panels.forEach(function (p) {
    p.points.forEach(function (pt) {
      tableRows.push({ panel: p.label, x: xFmt(pt.x), y: pt.y });
    });
  });
  shell.addTable(cols, tableRows);
};

/* ---------- sankey (two-column flow) ---------- */
/* data: [{from, to, value}] — one edge per flow (e.g. Q7's cut-fund ->
   keep-fund consolidation). Fixed left column (unique `from`s) / right
   column (unique `to`s), ribbon width ∝ value. ponytail: a real d3-sankey
   does N-level layout + iterative de-crossing; every edge here is exactly
   2 levels (cut fund -> keep fund) so a fixed two-column layout is the
   whole problem — no general graph layout needed. Ribbons use a single
   translucent accent fill rather than per-edge categorical color: `from`
   node counts here can exceed the 8-slot categorical budget (any number of
   cut funds), and re-deriving identity color from a value already shown by
   ribbon position+label would just spend the identity channel for nothing. */
Charts.sankey = function (el, data, opts) {
  opts = opts || {};
  var fmt = opts.fmt || defaultFmt;
  var W = 480,
    padX = 130,
    nodeW = 8,
    H = Math.max(160, Math.max(
      _sankeySide(data, "from").length,
      _sankeySide(data, "to").length
    ) * 22 + 20);
  var shell = chartShell(el, { viewBox: "0 0 " + W + " " + H });
  var svg = shell.svg;
  var fromNodes = _sankeyLayout(data, "from", H);
  var toNodes = _sankeyLayout(data, "to", H);
  var x0 = padX,
    x1 = W - padX;
  var ribbonFill = cssVar(el, "--accent");
  data.forEach(function (e) {
    var fn = fromNodes[e.from],
      tn = toNodes[e.to];
    var y0top = fn.y + fn.used,
      y0bot = y0top + fn.scale(e.value);
    var y1top = tn.y + tn.used,
      y1bot = y1top + tn.scale(e.value);
    fn.used += fn.scale(e.value);
    tn.used += tn.scale(e.value);
    var xm = (x0 + x1) / 2;
    var d =
      "M" + x0 + "," + y0top +
      " C" + xm + "," + y0top + " " + xm + "," + y1top + " " + x1 + "," + y1top +
      " L" + x1 + "," + y1bot +
      " C" + xm + "," + y1bot + " " + xm + "," + y0bot + " " + x0 + "," + y0bot +
      " Z";
    var path = svgEl("path", { d: d, fill: ribbonFill, opacity: 0.28 });
    svg.appendChild(path);
    wireHit(path, e.from + " → " + e.to, [{ label: opts.valueLabel || "value", value: fmt(e.value) }]);
  });
  [
    { nodes: fromNodes, x: x0, anchor: "end", labelX: x0 - 6 },
    { nodes: toNodes, x: x1, anchor: "start", labelX: x1 + 6 },
  ].forEach(function (side) {
    Object.keys(side.nodes).forEach(function (k) {
      var n = side.nodes[k];
      svg.appendChild(svgEl("rect", { x: side.x - nodeW / 2, y: n.y, width: nodeW, height: Math.max(1, n.h), fill: cssVar(el, "--ink"), rx: 1.5 }));
      svg.appendChild(svgText(side.labelX, n.y + n.h / 2 + 3, truncateLabel(k, padX - 16, 10), { "font-size": 10, "text-anchor": side.anchor, fill: "var(--ink)" }));
    });
  });
  shell.addTable(
    [
      { key: "from", label: "From" },
      { key: "to", label: "To" },
      { key: "value", label: opts.valueLabel || "Value", numeric: true, fmt: fmt },
    ],
    data
  );
};
function _sankeySide(data, key) {
  var seen = [];
  data.forEach(function (e) { if (seen.indexOf(e[key]) === -1) seen.push(e[key]); });
  return seen;
}
function _sankeyLayout(data, key, H) {
  var totals = {};
  data.forEach(function (e) { totals[e[key]] = (totals[e[key]] || 0) + e.value; });
  var keys = Object.keys(totals);
  var grand = keys.reduce(function (s, k) { return s + totals[k]; }, 0) || 1;
  var gap = 6,
    usableH = H - gap * (keys.length - 1);
  var y = 0,
    nodes = {};
  keys.forEach(function (k) {
    var h = (totals[k] / grand) * usableH;
    var scale = h / totals[k];
    nodes[k] = { y: y, h: h, used: 0, scale: function (v) { return v * scale; } };
    y += h + gap;
  });
  return nodes;
}
