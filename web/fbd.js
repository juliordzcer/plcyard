// The function block diagram editor of the web version: blocks with pins, wires dragged from pin to pin,
// operands on unwired pins. Drawn as SVG from webapp's fbd view, with the desktop editor's geometry.
"use strict";

const Fbd = (() => {
  const BLOCK_W = 110, HEAD = 30, ROW = 24, STUB = 14, GRID = 20;
  const e = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const snap = (v) => Math.max(0, Math.round(v / GRID) * GRID);
  let view = null, drag = null;

  const height = (b) => HEAD + Math.max(b.inputs.length, b.outputs.length, 1) * ROW + 8;
  const pinPoint = (b, pin, out) => {
    const k = Math.max(0, (out ? b.outputs : b.inputs).findIndex((p) => p.name === pin));
    return [out ? b.x + BLOCK_W + STUB : b.x - STUB, b.y + HEAD + k * ROW + ROW / 2];
  };

  function wirePath(blocks, w) {
    const s = blocks.get(w[0]), d = blocks.get(w[2]);
    if (!s || !d) return "";
    const [ax, ay] = pinPoint(s, w[1], true), [bx, by] = pinPoint(d, w[3], false);
    if (bx > ax) {
      const mid = ax + Math.max(GRID, (bx - ax) / 2);
      return `M ${ax} ${ay} H ${mid} V ${by} H ${bx}`;
    }
    const low = Math.max(s.y + height(s), d.y + height(d)) + GRID;     // back to an earlier block: around below
    return `M ${ax} ${ay} H ${ax + GRID} V ${low} H ${bx - GRID} V ${by} H ${bx}`;
  }

  function blockSvg(b, sel, bad) {
    const h = height(b);
    let s = `<g class="blk" data-block="${b.id}">`;
    s += `<rect class="box${sel ? " picked" : ""}${bad ? " bad" : ""}" x="${b.x}" y="${b.y}" width="${BLOCK_W}" height="${h}" rx="4"><title>${e(b.title)}</title></rect>`;
    s += `<text class="title" x="${b.x + BLOCK_W / 2}" y="${b.y + 19}" text-anchor="middle">${e(b.type)}</text>`;
    if (b.kind) s += `<text class="${b.instance ? "" : "unset"}" x="${b.x + BLOCK_W / 2}" y="${b.y - 6}" text-anchor="middle">${e(b.instance || "?")}</text>`;
    for (const [out, pins] of [[false, b.inputs], [true, b.outputs]]) {
      pins.forEach((p, k) => {
        const y = b.y + HEAD + k * ROW + ROW / 2;
        const [x0, x1] = out ? [b.x + BLOCK_W, b.x + BLOCK_W + STUB] : [b.x - STUB, b.x];
        s += `<line class="w${p.value === true ? " on" : ""}" x1="${x0}" y1="${y}" x2="${x1}" y2="${y}"/>`;
        s += `<text class="lab" x="${out ? b.x + BLOCK_W - 5 : b.x + 5}" y="${y + 4}" text-anchor="${out ? "end" : "start"}">${e(p.name)}</text>`;
        let text = p.op;
        const constant = /^([-+]?[\d.]|T#|TIME#)/i.test(p.op);
        if (p.value !== null && p.value !== undefined && typeof p.value !== "boolean" && !constant) text = (text ? text + " = " : "") + p.value;
        if (text) {
          const cls = p.value === true ? "opv live" : "opv";
          s += out ? `<text class="${cls}" x="${x1 + 4}" y="${y + 4}">${e(text)}</text>`
            : `<text class="${cls}" x="${x0 - 4}" y="${y + 4}" text-anchor="end">${e(text)}</text>`;
        }
        s += `<rect class="pinhit" data-block="${b.id}" data-pin="${e(p.name)}" data-out="${out ? 1 : 0}" x="${x0 - 4}" y="${y - ROW / 2}" width="${STUB + 8}" height="${ROW}"><title>${e(p.name)}: drag to another pin to wire it · drop an address to use it</title></rect>`;
      });
    }
    return s + "</g>";
  }

  function render(el, fbd, sel) {
    view = fbd;
    const blocks = new Map(fbd.blocks.map((b) => [b.id, b]));
    const on = (w) => blocks.get(w[0])?.outputs.find((p) => p.name === w[1])?.value === true;
    let s = "";
    fbd.wires.forEach((w, k) => {
      const picked = sel && sel[0] === "wire" && sel[1] === k;
      const d = wirePath(blocks, w);
      if (!d) return;
      s += `<path class="w nofill${on(w) ? " on" : ""}${picked ? " picked" : ""}" d="${d}"/>`;
      s += `<path class="wirehit" data-wire="${k}" d="${d}"/>`;
    });
    for (const b of fbd.blocks) s += blockSvg(b, sel && sel[0] === "block" && sel[1] === b.id, !!fbd.problems[String(b.id)]);
    const w = Math.max(el.clientWidth - 8, ...fbd.blocks.map((b) => b.x + BLOCK_W + 260));
    const h = Math.max(el.clientHeight - 8, ...fbd.blocks.map((b) => b.y + height(b) + 80));
    if (!fbd.blocks.length) s += `<text class="empty" x="${w / 2}" y="80" text-anchor="middle">Empty diagram. Click a block above, or drag it here.</text>`;
    s += `<line id="fbd-rubber" class="rubber" x1="0" y1="0" x2="0" y2="0" visibility="hidden"/>`;
    el.innerHTML = `<svg width="${w}" height="${h}" role="img" aria-label="Function block diagram">${s}</svg>`;
  }

  // Where a new block goes when it is clicked in the bar: below the others.
  function freeSpot() {
    const bottom = Math.max(0, ...view.blocks.map((b) => b.y + height(b)));
    return [GRID * 6, view.blocks.length ? snap(bottom + GRID * 2) : GRID * 2];
  }

  // Pointer work on the canvas. `api` has select(sel), move(id, x, y), connect(src, srcPin, dst, dstPin),
  // add(kind, x, y), drop(id, pin, address).
  function wire(el, api) {
    const at = (ev) => {
      const r = el.querySelector("svg").getBoundingClientRect();
      return [ev.clientX - r.left, ev.clientY - r.top];
    };
    el.addEventListener("pointerdown", (ev) => {
      if (ev.button !== 0) return;
      const pin = ev.target.closest(".pinhit"), blk = ev.target.closest("[data-block]"), wh = ev.target.closest(".wirehit");
      if (pin) {
        const b = view.blocks.find((x) => x.id === +pin.dataset.block);
        drag = { kind: "wire", id: b.id, pin: pin.dataset.pin, out: pin.dataset.out === "1", from: pinPoint(b, pin.dataset.pin, pin.dataset.out === "1") };
        el.setPointerCapture(ev.pointerId);
        ev.preventDefault();
      } else if (blk) {
        const b = view.blocks.find((x) => x.id === +blk.dataset.block);
        const [px, py] = at(ev);
        api.select(["block", b.id]);
        drag = { kind: "move", id: b.id, dx: px - b.x, dy: py - b.y, x: b.x, y: b.y };
        el.setPointerCapture(ev.pointerId);
        ev.preventDefault();
      } else api.select(wh ? ["wire", +wh.dataset.wire] : null);
    });
    el.addEventListener("pointermove", (ev) => {
      if (!drag) return;
      const [px, py] = at(ev);
      if (drag.kind === "move") {
        drag.x = snap(px - drag.dx);
        drag.y = snap(py - drag.dy);
        const g = el.querySelector(`g[data-block="${drag.id}"]`), b = view.blocks.find((x) => x.id === drag.id);
        if (g) g.setAttribute("transform", `translate(${drag.x - b.x} ${drag.y - b.y})`);
      } else {
        const r = el.querySelector("#fbd-rubber");
        r.setAttribute("x1", drag.from[0]); r.setAttribute("y1", drag.from[1]);
        r.setAttribute("x2", px); r.setAttribute("y2", py);
        r.setAttribute("visibility", "visible");
      }
    });
    el.addEventListener("pointerup", (ev) => {
      const d = drag;
      drag = null;
      if (!d) return;
      if (d.kind === "move") { api.move(d.id, d.x, d.y); return; }
      el.querySelector("#fbd-rubber")?.setAttribute("visibility", "hidden");
      const t = document.elementFromPoint(ev.clientX, ev.clientY)?.closest?.(".pinhit");
      if (!t || (t.dataset.out === "1") === d.out || +t.dataset.block === d.id) return;
      const other = [+t.dataset.block, t.dataset.pin];
      if (d.out) api.connect(d.id, d.pin, ...other);
      else api.connect(...other, d.id, d.pin);
    });
    el.addEventListener("dragover", (ev) => {
      const t = document.elementFromPoint(ev.clientX, ev.clientY)?.closest?.(".pinhit");
      el.querySelectorAll(".drop").forEach((x) => x.classList.remove("drop"));
      if (t) t.classList.add("drop");
      if (t || ev.dataTransfer.types.includes("application/x-plcyard-block")) ev.preventDefault();
    });
    el.addEventListener("drop", (ev) => {
      ev.preventDefault();
      const kind = ev.dataTransfer.getData("application/x-plcyard-block");
      if (kind) { const [x, y] = at(ev); api.add(kind, snap(x - BLOCK_W / 2), snap(y - HEAD / 2)); return; }
      const t = document.elementFromPoint(ev.clientX, ev.clientY)?.closest?.(".pinhit");
      if (t) api.drop(+t.dataset.block, t.dataset.pin, ev.dataTransfer.getData("text/plain"));
    });
  }

  return { render, wire, freeSpot, busy: () => !!drag };
})();
