/* Commutative-diagram view of the benchmark.
 *
 * Left column: models. Right column: problem sets (overview) or the problems of
 * one set. Each arrow model -> target carries the score / pass count; solid when
 * the model solved something, dashed when it never did. Hovering highlights
 * (colour only, no motion); clicking pins the selection.
 */
(function () {
  const VIEWS = JSON.parse(document.getElementById("diagram-data").textContent);
  const host = document.getElementById("diagram");
  const scroll = document.getElementById("diagram-scroll");
  const info = document.getElementById("info");
  const tabs = document.getElementById("view-tabs");
  const SVGNS = "http://www.w3.org/2000/svg";

  // red -> amber -> green
  const STOPS = [[224, 112, 122], [232, 193, 112], [95, 212, 163]];
  function color(v) {
    if (v === null || v === undefined) return "#5b6f94";
    v = Math.max(0, Math.min(1, v));
    const [a, b, t] = v < 0.5 ? [STOPS[0], STOPS[1], v * 2] : [STOPS[1], STOPS[2], (v - 0.5) * 2];
    return `rgb(${a.map((x, i) => Math.round(x + (b[i] - x) * t)).join(",")})`;
  }

  let view = null, pinned = null, els = null;

  function esc(s) {
    return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  }

  function showInfo(title, rows, url) {
    info.innerHTML =
      `<h3>${esc(title)}</h3><dl class="kv">` +
      rows.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("") +
      "</dl>" + (url ? `<p class="small" style="margin-top:10px"><a href="${esc(url)}">Open →</a></p>` : "");
  }

  function defaultInfo() {
    info.innerHTML =
      `<h3>${esc(view.name)}</h3>
       <p class="small muted">Hover a node to see its arrows and their labels; click to pin.
       Hover an arrow for its numbers.</p>
       <dl class="kv"><dt>Models</dt><dd>${view.sources.length}</dd>
       <dt>${view.key === "overview" ? "Sets" : "Problems"}</dt><dd>${view.targets.length}</dd>
       <dt>Arrows</dt><dd>${view.edges.length}</dd></dl>`;
  }

  function node(n, x, y, w, h, side, idx) {
    const d = document.createElement("div");
    d.className = "node";
    d.style.cssText = `left:${x}px;top:${y}px;width:${w}px;height:${h}px`;
    d.innerHTML = `<div class="nl">${esc(n.label)}</div><div class="ns">${esc(n.sub || "")}</div>`;
    if (n.value !== null && n.value !== undefined) {
      const bar = document.createElement("div");
      bar.className = "bar";
      // sources: bar = score; targets: bar = difficulty (red when hard)
      const good = side === "s" ? n.value : 1 - n.value;
      bar.style.cssText = `width:${Math.round(n.value * 100)}%;background:${color(good)}`;
      d.append(bar);
    }
    d.title = n.label;
    d.addEventListener("mouseenter", () => focus({ side, idx }));
    d.addEventListener("mouseleave", () => focus(pinned));
    d.addEventListener("click", () => {
      pinned = pinned && pinned.side === side && pinned.idx === idx ? null : { side, idx };
      focus(pinned || { side, idx });
    });
    host.append(d);
    return d;
  }

  function layout() {
    host.innerHTML = "";
    const W = Math.max(560, scroll.clientWidth);
    const nodeW = Math.min(250, Math.round(W * 0.3));
    const nodeH = 52, gap = 70, top = 34, pad = 16;
    const ns = view.sources.length, nt = view.targets.length, rows = Math.max(ns, nt, 1);
    const H = top + rows * gap + pad;
    host.style.width = W + "px";
    host.style.height = H + "px";

    const svg = document.createElementNS(SVGNS, "svg");
    svg.setAttribute("width", W);
    svg.setAttribute("height", H);
    host.append(svg);

    const colTitle = (text, x, align) => {
      const t = document.createElement("div");
      t.className = "col-title";
      t.textContent = text;
      t.style[align] = x + "px";
      host.append(t);
    };
    colTitle("Models", pad, "left");
    colTitle(view.key === "overview" ? "Problem sets" : "Problems", pad, "right");

    const xs = pad, xt = W - nodeW - pad;
    const ypos = (k, i) => top + (rows - k) * gap / 2 + i * gap + (gap - nodeH) / 2;
    const srcEls = view.sources.map((n, i) => node(n, xs, ypos(ns, i), nodeW, nodeH, "s", i));
    const tgtEls = view.targets.map((n, i) => node(n, xt, ypos(nt, i), nodeW, nodeH, "t", i));

    const edgeEls = view.edges.map((e, k) => {
      const x1 = xs + nodeW + 4, y1 = ypos(ns, e.s) + nodeH / 2;
      const x2 = xt - 5, y2 = ypos(nt, e.t) + nodeH / 2;
      const c = color(e.value);
      const g = document.createElementNS(SVGNS, "g");
      const line = document.createElementNS(SVGNS, "path");
      line.setAttribute("d", `M${x1},${y1} L${x2},${y2}`);
      line.setAttribute("class", "edge" + (e.dashed ? " dashed" : ""));
      line.setAttribute("stroke", c);
      // tikz-cd style open arrowhead
      const len = Math.hypot(x2 - x1, y2 - y1), ux = (x2 - x1) / len, uy = (y2 - y1) / len;
      const bx = x2 - ux * 8, by = y2 - uy * 8, px = -uy * 4.5, py = ux * 4.5;
      const head = document.createElementNS(SVGNS, "path");
      head.setAttribute("d", `M${bx + px},${by + py} Q${x2 - ux * 3},${y2 - uy * 3} ${x2},${y2} Q${x2 - ux * 3},${y2 - uy * 3} ${bx - px},${by - py}`);
      head.setAttribute("class", "edge");
      head.setAttribute("stroke", c);
      const hit = document.createElementNS(SVGNS, "path");
      hit.setAttribute("d", `M${x1},${y1} L${x2},${y2}`);
      hit.setAttribute("class", "hit");
      hit.addEventListener("mouseenter", () => {
        focusEdge(k);
        showInfo(e.title, e.info);
      });
      hit.addEventListener("mouseleave", () => focus(pinned));
      g.append(line, head, hit);
      svg.append(g);

      const lab = document.createElement("div");
      lab.className = "elabel";
      lab.style.color = c;
      Boxed.tex(e.label, lab);
      host.append(lab);
      return { g, parts: [line, head], lab, x1, y1, x2, y2 };
    });

    els = { srcEls, tgtEls, edgeEls };
    focus(pinned);
  }

  function placeLabel(el, t) {
    el.lab.style.left = el.x1 + (el.x2 - el.x1) * t + "px";
    el.lab.style.top = el.y1 + (el.y2 - el.y1) * t + "px";
  }

  function style(edgeOn) {
    view.edges.forEach((e, k) => {
      const el = els.edgeEls[k], on = edgeOn(e, k);
      el.parts.forEach((p) => p.setAttribute("stroke-opacity", on === null ? 0.45 : on ? 1 : 0.07));
      if (on) el.g.parentNode.append(el.g); // draw highlighted arrows on top
    });
  }

  function focus(f) {
    if (!els) return;
    const all = [...els.srcEls, ...els.tgtEls];
    all.forEach((d) => d.classList.remove("on", "dim"));
    if (!f) {
      style(() => null);
      const few = view.edges.length <= 10;
      els.edgeEls.forEach((el) => { placeLabel(el, 0.5); el.lab.classList.toggle("show", few); });
      defaultInfo();
      return;
    }
    const key = f.side === "s" ? "s" : "t";
    const linked = new Set(view.edges.filter((e) => e[key] === f.idx).map((e) => (key === "s" ? e.t : e.s)));
    const own = f.side === "s" ? els.srcEls : els.tgtEls;
    const other = f.side === "s" ? els.tgtEls : els.srcEls;
    own.forEach((d, i) => d.classList.toggle(i === f.idx ? "on" : "dim", true));
    other.forEach((d, i) => { if (!linked.has(i)) d.classList.add("dim"); });
    style((e) => e[key] === f.idx);
    // labels sit where the fan of arrows is widest
    els.edgeEls.forEach((el, k) => {
      const on = view.edges[k][key] === f.idx;
      placeLabel(el, f.side === "s" ? 0.62 : 0.38);
      el.lab.classList.toggle("show", on);
    });
    const n = (f.side === "s" ? view.sources : view.targets)[f.idx];
    showInfo(n.label, n.info, n.url);
  }

  function focusEdge(k) {
    const e = view.edges[k];
    [...els.srcEls, ...els.tgtEls].forEach((d) => d.classList.remove("on", "dim"));
    els.srcEls.forEach((d, i) => d.classList.add(i === e.s ? "on" : "dim"));
    els.tgtEls.forEach((d, i) => d.classList.add(i === e.t ? "on" : "dim"));
    style((_, j) => j === k);
    els.edgeEls.forEach((el, j) => { placeLabel(el, 0.5); el.lab.classList.toggle("show", j === k); });
  }

  function select(key) {
    view = VIEWS.find((v) => v.key === key) || VIEWS[0];
    pinned = null;
    tabs.querySelectorAll("button").forEach((b) => b.classList.toggle("on", b.dataset.key === view.key));
    try { history.replaceState(null, "", "#" + view.key); } catch (e) { /* ignore */ }
    layout();
  }

  VIEWS.forEach((v) => {
    const b = document.createElement("button");
    b.textContent = v.name;
    b.dataset.key = v.key;
    b.addEventListener("click", () => select(v.key));
    tabs.append(b);
  });

  let rt;
  window.addEventListener("resize", () => { clearTimeout(rt); rt = setTimeout(layout, 120); });
  document.addEventListener("DOMContentLoaded", () => select(location.hash.slice(1)));
})();
