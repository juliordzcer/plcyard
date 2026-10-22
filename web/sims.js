// The machines of the web version: controls (built once per machine), a list of devices with their
// addresses (drag them onto the ladder) and an SVG drawing redrawn every frame from webapp.machine().
"use strict";

const Sims = (() => {
  const e = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const hold = (act, label, title) => `<button class="pbtn" data-act="${act}" data-hold title="${e(title || "Hold to press")}">${e(label)}</button>`;
  const dev = (name, addr, key) => `<li><span class="dot" data-dev="${key}"></span><span class="dname">${e(name)}</span>
    <span class="addr" draggable="true" data-addr="${e(addr)}" title="Drag onto an instruction">${e(addr)}</span></li>`;
  const devices = (inputs, outputs) => `<!--devs--><div class="devs"><div><h4>Inputs</h4><ul>${inputs.map((d) => dev(...d)).join("")}</ul></div>
    <div><h4>Outputs</h4><ul>${outputs.map((d) => dev(...d)).join("")}</ul></div></div>`;

  // -- controls and device lists ------------------------------------------------------------------
  function controls(m) {
    const a = m.addr, reset = `<button data-act="reset" title="Start the machine again">Reset</button>`;
    if (m.kind === "silo") {
      return `<div class="ctl">${hold("start", "Start")}${hold("stop", "Stop", "Hold to press (normally closed)")}
        <span class="group" role="group" aria-label="Selector">${["A", "B", "C"].map((v) => `<button data-act="selector" data-value="${v}">${v}</button>`).join("")}</span>${reset}</div>` +
        devices([["Start (NO)", a.start, "start"], ["Stop (NC)", a.stop, "stop"], ["Prox: box under the hopper", a.prox, "prox"],
          ["Level: box full", a.level, "level"], ["Selector A/B/C", a.selector, "selector"]],
        [["Conveyor motor", a.motor, "motor"], ["Fill solenoid", a.solenoid, "solenoid"], ["Run lamp", a.run, "run"],
          ["Fill lamp", a.fill, "fill"], ["Full lamp", a.full, "full"]]);
    }
    if (m.kind === "traffic") {
      return `<div class="ctl">${hold("button_A", "Walk button A")}${hold("button_B", "Walk button B")}
        <label><input type="checkbox" data-act="park_A"> Park car A</label><label><input type="checkbox" data-act="park_B"> Park car B</label>${reset}</div>` +
        devices([["Walk button A", a.button_A, "button_A"], ["Walk button B", a.button_B, "button_B"],
          ["Car waiting at A", a.car_A, "car_A"], ["Car waiting at B", a.car_B, "car_B"]],
        [["Red A", a.A[0], "A_red"], ["Amber A", a.A[1], "A_amber"], ["Green A", a.A[2], "A_green"], ["Walk A", a.A[3], "A_walk"],
          ["Red B", a.B[0], "B_red"], ["Amber B", a.B[1], "B_amber"], ["Green B", a.B[2], "B_green"], ["Walk B", a.B[3], "B_walk"]]);
    }
    if (m.kind === "tank") {
      return `<div class="ctl">${hold("start", "Start")}${hold("stop", "Stop", "Hold to press (normally closed)")}${reset}</div>
        <div class="knobs"><label>Setpoint knob <span data-val="setpoint"></span><input type="range" min="0" max="100" step="1" data-act="setpoint"></label>
        <label>Outlet opening (disturbance) <span data-val="outlet"></span><input type="range" min="0" max="100" step="1" data-act="outlet"></label></div>` +
        devices([["Start (NO)", a.start, "start"], ["Stop (NC)", a.stop, "stop"], ["High level switch (≥ 90 %)", a.high, "high"],
          ["Low level switch (≤ 10 %)", a.low, "low"], ["Level 0-10 V = 0-100 %", a.level, "level"], ["Setpoint knob 0-10 V", a.setpoint, "setpoint"]],
        [["Pump", a.pump, "pump"], ["Run lamp", a.run, "run"], ["High alarm lamp", a.alarm, "alarm"], ["Inlet valve 0-10 V", a.valve, "valve"]]);
    }
    return "";
  }

  // device key → on/off (analog devices show a value instead)
  function states(m) {
    if (m.kind === "silo") {
      return { start: m.start, stop: !m.stop, prox: m.prox, level: m.level, selector: true, motor: m.motor, solenoid: m.solenoid,
        run: m.lamps[0], fill: m.lamps[1], full: m.lamps[2] };
    }
    if (m.kind === "traffic") {
      const s = { button_A: m.buttons.A, button_B: m.buttons.B, car_A: m.cars.A.waiting, car_B: m.cars.B.waiting };
      for (const r of ["A", "B"]) for (const c of ["red", "amber", "green", "walk"]) s[`${r}_${c}`] = m.lights[r][c];
      return s;
    }
    if (m.kind === "tank") {
      return { start: m.start, stop: !m.stop, high: m.high, low: m.low, pump: m.pump, run: m.lamps[0], alarm: m.lamps[1],
        level: `${m.level.toFixed(1)} %`, setpoint: `${m.setpoint.toFixed(0)} %`, valve: `${m.valve.toFixed(0)} %` };
    }
    return {};
  }

  // -- drawings -----------------------------------------------------------------------------------
  function silo(m) {
    const X = 20, sx = X + m.sensor_x, beltY = 250, boxH = 60;
    let s = `<svg viewBox="0 0 700 300" class="draw" role="img" aria-label="Silo filling line">`;
    s += `<path class="steel" d="M ${sx - 70} 14 H ${sx + 70} V 64 L ${sx + 14} 100 H ${sx - 14} L ${sx - 70} 64 Z"/>`;
    s += `<path class="product" d="M ${sx - 64} 34 H ${sx + 64} V 61 L ${sx + 12} 94 H ${sx - 12} L ${sx - 64} 61 Z"/>`;
    s += `<rect class="${m.solenoid ? "valve on" : "valve"}" x="${sx - 12}" y="100" width="24" height="12" rx="2"/>`;
    if (m.solenoid) s += `<rect class="product" x="${sx - 4}" y="112" width="8" height="${beltY - boxH - 112 + 4}"/>`;
    s += `<rect class="${m.level ? "sensor on" : "sensor"}" x="${sx + 22}" y="150" width="8" height="26" rx="2"/>`;
    for (const b of m.boxes) {
      const bx = X + b.x, fh = boxH * Math.min(b.fill, 100) / 100;
      if (bx > X + m.belt || bx + m.box_w < X - 10) continue;
      s += `<rect class="box" x="${bx}" y="${beltY - boxH}" width="${m.box_w}" height="${boxH}"/>`;
      if (fh > 0) s += `<rect class="product" x="${bx + 2}" y="${beltY - fh}" width="${m.box_w - 4}" height="${fh}"/>`;
      if (b.spilled) s += `<rect class="spilled" x="${bx}" y="${beltY - boxH}" width="${m.box_w}" height="${boxH}"/>`;
    }
    s += `<rect class="belt" x="${X - 6}" y="${beltY}" width="${m.belt + 12}" height="10" rx="5"/>`;
    for (let r = 0; r <= m.belt; r += 80) s += `<circle class="roller" cx="${X + r}" cy="${beltY + 5}" r="3"/>`;
    s += `<path class="${m.prox ? "sensor on" : "sensor"}" d="M ${sx - 7} ${beltY + 30} L ${sx + 7} ${beltY + 30} L ${sx} ${beltY + 16} Z"/>`;
    s += `<circle class="${m.motor ? "motor on" : "motor"}" cx="${X + m.belt + 18}" cy="${beltY + 5}" r="12"/>`;
    s += `<text class="cap" x="${X}" y="${beltY + 40}">Boxes shipped ${m.shipped} · full ${m.full}${m.spill > 0 ? ` · spilled ${m.spill.toFixed(0)} %` : ""}</text>`;
    return s + `</svg>`;
  }

  function traffic(m) {
    const [j1, j2] = m.junction, L = m.road, line = m.stop_line;
    let s = `<svg viewBox="0 0 ${L} ${L}" class="draw" role="img" aria-label="Road crossing">`;
    s += `<rect class="grass" x="0" y="0" width="${L}" height="${L}"/>`;
    s += `<rect class="road" x="0" y="${j1}" width="${L}" height="${j2 - j1}"/><rect class="road" x="${j1}" y="0" width="${j2 - j1}" height="${L}"/>`;
    s += `<line class="lane" x1="0" y1="${(j1 + j2) / 2}" x2="${L}" y2="${(j1 + j2) / 2}"/><line class="lane" x1="${(j1 + j2) / 2}" y1="0" x2="${(j1 + j2) / 2}" y2="${L}"/>`;
    s += `<line class="stop" x1="${line}" y1="${(j1 + j2) / 2}" x2="${line}" y2="${j2}"/><line class="stop" x1="${j1}" y1="${line}" x2="${(j1 + j2) / 2}" y2="${line}"/>`;
    for (let k = 0; k < 6; k++) {
      s += `<rect class="zebra" x="${j1 - 34}" y="${j1 + 4 + k * 13}" width="20" height="7"/><rect class="zebra" x="${j1 + 4 + k * 13}" y="${j1 - 34}" width="7" height="20"/>`;
    }
    const head = (x, y, r, label) => {
      const l = m.lights[r];
      return `<rect class="head" x="${x}" y="${y}" width="26" height="74" rx="5"/>` +
        ["red", "amber", "green"].map((c, i) => `<circle class="lt ${c}${l[c] ? " on" : ""}" cx="${x + 13}" cy="${y + 13 + i * 24}" r="9"/>`).join("") +
        `<rect class="walk${l.walk ? " on" : ""}" x="${x}" y="${y + 80}" width="26" height="16" rx="3"/><text class="cap" x="${x + 13}" y="${y + 92}" text-anchor="middle">${l.walk ? "WALK" : "wait"}</text>` +
        `<text class="cap" x="${x + 13}" y="${y - 6}" text-anchor="middle">${label}</text>`;
    };
    s += head(line - 70, j2 + 14, "A", "A") + head(j2 + 14, line - 120, "B", "B");
    const ca = m.cars.A, cb = m.cars.B;
    if (!ca.parked && !ca.hidden) s += `<rect class="car a" x="${ca.pos - m.car_len}" y="${(j1 + j2) / 2 + 8}" width="${m.car_len}" height="26" rx="6"/>`;
    if (!cb.parked && !cb.hidden) s += `<rect class="car b" x="${j1 + 8}" y="${cb.pos - m.car_len}" width="26" height="${m.car_len}" rx="6"/>`;
    s += `<text class="cap" x="8" y="${j1 - 8}">Road A →</text><text class="cap" x="${j1 - 70}" y="16">Road B ↓</text>`;
    s += `<text class="cap" x="8" y="${L - 10}">Cars through: A ${ca.passes} · B ${cb.passes}</text>`;
    if (m.crashed) s += `<text class="crash" x="${L / 2}" y="${j1 - 40}" text-anchor="middle">CRASH — press Reset</text>`;
    return s + `</svg>`;
  }

  function tank(m) {
    const tx = 150, ty = 70, tw = 130, th = 190, lvl = th * m.level / 100, sp = ty + th - th * m.setpoint / 100;
    let s = `<svg viewBox="0 0 400 300" class="draw" role="img" aria-label="Tank level">`;
    s += `<path class="pipe${m.pump || m.valve > 0.5 ? " flow" : ""}" d="M 10 40 H ${tx + 40} V ${ty + 6}"/>`;
    s += `<circle class="${m.pump ? "motor on" : "motor"}" cx="50" cy="40" r="14"/><text class="cap" x="50" y="70" text-anchor="middle">pump</text>`;
    s += `<path class="valve2" d="M 92 30 L 92 50 L 120 30 L 120 50 Z"/><text class="cap" x="106" y="70" text-anchor="middle">valve ${m.valve.toFixed(0)} %</text>`;
    s += `<rect class="tank" x="${tx}" y="${ty}" width="${tw}" height="${th}"/>`;
    s += `<rect class="product" x="${tx + 2}" y="${ty + th - lvl}" width="${tw - 4}" height="${lvl}"/>`;
    s += `<line class="spline" x1="${tx - 10}" y1="${sp}" x2="${tx + tw + 10}" y2="${sp}"/>`;
    for (const [at, on, name] of [[m.high_at, m.high, "High"], [m.low_at, m.low, "Low"]]) {
      const y = ty + th - th * at / 100;
      s += `<circle class="${on ? "sensor on" : "sensor"}" cx="${tx + tw + 8}" cy="${y}" r="5"/><text class="cap" x="${tx + tw + 18}" y="${y + 4}">${name}</text>`;
    }
    s += `<path class="pipe${m.outlet > 0.5 && m.level > 0.1 ? " flow" : ""}" d="M ${tx + tw} ${ty + th - 8} H 390"/>`;
    s += `<text class="cap" x="${tx + tw + 20}" y="${ty + th + 18}">outlet ${m.outlet.toFixed(0)} %</text>`;
    s += `<text class="big" x="${tx + tw / 2}" y="${ty + 30}" text-anchor="middle">${m.level.toFixed(1)} %</text>`;
    s += `</svg>`;
    return s + trend(m.trend);
  }

  function trend(pts) {
    const W = 400, H = 120, now = pts.length ? pts[pts.length - 1][0] : 0, t0 = Math.max(0, now - 120);
    const px = (t) => 30 + (W - 40) * (t - t0) / 120, py = (v) => 10 + (H - 30) * (1 - Math.min(Math.max(v, 0), 100) / 100);
    const poly = (k, cls) => `<polyline class="${cls}" points="${pts.filter((p) => p[0] >= t0).map((p) => `${px(p[0]).toFixed(1)},${py(p[k]).toFixed(1)}`).join(" ")}"/>`;
    let s = `<svg viewBox="0 0 ${W} ${H}" class="draw trend" role="img" aria-label="Trend of setpoint, level and valve">`;
    for (const v of [0, 50, 100]) s += `<line class="grid" x1="30" y1="${py(v)}" x2="${W - 10}" y2="${py(v)}"/><text class="cap" x="24" y="${py(v) + 4}" text-anchor="end">${v}</text>`;
    s += poly(3, "t-cv") + poly(1, "t-sp") + poly(2, "t-pv");
    s += `<text class="cap" x="30" y="${H - 4}"><tspan class="k-sp">— setpoint</tspan>  <tspan class="k-pv">— level</tspan>  <tspan class="k-cv">— valve</tspan>  (last 2 min)</text>`;
    return s + `</svg>`;
  }

  const DRAW = { silo, traffic, tank };
  let key = "";

  function render(el, m) {
    const k = m.kind + JSON.stringify(m.addr);
    if (k !== key) {
      key = k;
      const [ctl, devs] = controls(m).split("<!--devs-->");
      el.innerHTML = `<div class="machine">${ctl}<div class="drawing"></div><ul class="events"></ul>${devs || ""}</div>`;
    }
    el.querySelector(".drawing").innerHTML = DRAW[m.kind](m);
    const st = states(m);
    el.querySelectorAll("[data-dev]").forEach((d) => {
      const v = st[d.dataset.dev];
      d.className = "dot" + (v === true ? " on" : "") + (typeof v === "string" ? " val" : "");
      d.textContent = typeof v === "string" ? v : "";
    });
    el.querySelectorAll("button[data-act=selector]").forEach((b) => b.classList.toggle("on", b.dataset.value === m.selector));
    for (const r of ["A", "B"]) {
      const c = el.querySelector(`input[data-act=park_${r}]`);
      if (c && m.cars) c.checked = m.cars[r].parked;
    }
    for (const n of ["setpoint", "outlet"]) {
      const r = el.querySelector(`input[data-act=${n}]`);
      if (r && document.activeElement !== r) r.value = m[n];
      const v = el.querySelector(`[data-val=${n}]`);
      if (v) v.textContent = `${Math.round(m[n])} %`;
    }
    el.querySelector(".events").innerHTML = m.events.map((t) => `<li>⚠ ${e(t)}</li>`).join("");
  }

  function reset() { key = ""; }

  // pointer and input handling; act(name, value) calls the session
  function wire(el, act) {
    el.addEventListener("pointerdown", (ev) => {
      const b = ev.target.closest("[data-act][data-hold]");
      if (!b) return;
      act(b.dataset.act, true);
      b.classList.add("down");
      const up = () => { act(b.dataset.act, false); b.classList.remove("down"); window.removeEventListener("pointerup", up); };
      window.addEventListener("pointerup", up);
    });
    el.addEventListener("click", (ev) => {
      const b = ev.target.closest("button[data-act]:not([data-hold])");
      if (b) act(b.dataset.act, b.dataset.value);
    });
    el.addEventListener("input", (ev) => {
      const r = ev.target.closest("input[type=range][data-act]");
      if (r) act(r.dataset.act, +r.value);
    });
    el.addEventListener("change", (ev) => {
      const c = ev.target.closest("input[type=checkbox][data-act]");
      if (c) act(c.dataset.act, c.checked);
    });
  }

  return { render, reset, wire };
})();
