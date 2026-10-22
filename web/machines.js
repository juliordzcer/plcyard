// The eleven newer machines of the web version: controls and device lists built from webmachines.py's
// description, and a small SVG drawing per machine redrawn every frame. Input goes through Sims.wire.
"use strict";

const Machines = (() => {
  const e = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const f0 = (v) => Number(v).toFixed(0), f1 = (v) => Number(v).toFixed(1);
  const cls = (base, on) => base + (on ? " on" : "");
  const svg = (w, h, label, body) => `<svg viewBox="0 0 ${w} ${h}" class="draw" role="img" aria-label="${e(label)}">${body}</svg>`;
  const cap = (x, y, t, anchor) => `<text class="cap" x="${x}" y="${y}"${anchor ? ` text-anchor="${anchor}"` : ""}>${e(t)}</text>`;
  const lamp = (x, y, on, tone, label) => `<circle class="lt ${tone}${on ? " on" : ""}" cx="${x}" cy="${y}" r="8"/>${label ? cap(x + 13, y + 4, label) : ""}`;
  const tank = (x, y, w, h, level, cls2 = "product") => {
    const l = h * Math.min(Math.max(level, 0), 100) / 100;
    return `<rect class="${cls2}" x="${x + 2}" y="${y + h - l}" width="${w - 4}" height="${l}"/><path class="tank" d="M ${x} ${y} V ${y + h} H ${x + w} V ${y}"/>`;
  };
  const sensor = (x, y, on) => `<circle class="${cls("sensor", on)}" cx="${x}" cy="${y}" r="5"/>`;
  const belt = (y, moving) => `<rect class="belt" x="10" y="${y}" width="360" height="10" rx="5"/>` +
    Array.from({ length: 7 }, (_, k) => `<circle class="roller" cx="${10 + k * 60}" cy="${y + 5}" r="3"/>`).join("") +
    `<circle class="${cls("motor", moving)}" cx="384" cy="${y + 5}" r="11"/>`;

  function trend(pts, series, label) {
    const W = 400, H = 120, now = pts.length ? pts[pts.length - 1][0] : 0, t0 = Math.max(0, now - 120);
    const px = (t) => 30 + (W - 40) * (t - t0) / 120, py = (v) => 10 + (H - 30) * (1 - Math.min(Math.max(v, 0), 100) / 100);
    let s = "";
    for (const v of [0, 50, 100]) s += `<line class="grid" x1="30" y1="${py(v)}" x2="${W - 10}" y2="${py(v)}"/>${cap(24, py(v) + 4, v, "end")}`;
    for (const [k, c] of series) s += `<polyline class="${c}" points="${pts.filter((p) => p[0] >= t0).map((p) => `${px(p[0]).toFixed(1)},${py(p[k]).toFixed(1)}`).join(" ")}"/>`;
    s += `<text class="cap" x="30" y="${H - 4}">${series.map(([, c, n]) => `<tspan class="${c.replace("t-", "k-")}">— ${e(n)}</tspan>`).join("  ")}  (last 2 min)</text>`;
    return `<svg viewBox="0 0 ${W} ${H}" class="draw trend" role="img" aria-label="${e(label)}">${s}</svg>`;
  }

  // -- drawings -----------------------------------------------------------------------------------
  const DRAW = {
    two_tanks(d) {
      let s = `<path class="${cls("pipe", d.pump || d.inlet > 0.5)}" d="M 10 30 H 90 V 50"/>`;
      s += `<circle class="${cls("motor", d.pump)}" cx="30" cy="30" r="11"/>${cap(10, 18, `pump · inlet ${f0(d.inlet)} %`)}`;
      s += tank(60, 50, 100, 120, d.level1);
      s += `<path class="${cls("pipe", d.transfer > 0.5 && d.level1 > 0.1)}" d="M 160 160 H 230 V 120"/>${cap(166, 150, `${f0(d.transfer)} %`)}`;
      s += tank(220, 120, 110, 120, d.level2);
      const sp = 120 + 120 - 120 * d.setpoint / 100;
      s += `<line class="spline" x1="212" y1="${sp}" x2="338" y2="${sp}"/>`;
      s += `<path class="${cls("pipe", d.outlet > 0.5 && d.level2 > 0.1)}" d="M 330 232 H 395"/>${cap(330, 254, `outlet ${f0(d.outlet)} %`)}`;
      s += `<text class="big" x="110" y="44" text-anchor="middle">${f1(d.level1)}</text><text class="big" x="275" y="112" text-anchor="middle">${f1(d.level2)}</text>`;
      s += sensor(166, 50 + 120 * 0.1, d.level1 >= d.high) + sensor(338, 120 + 120 * 0.1, d.level2 >= d.high) + sensor(338, 120 + 120 * 0.9, d.level2 <= d.low);
      s += lamp(20, 220, d.lamps[0], "green", "Run") + lamp(20, 244, d.lamps[1], "red", "Alarm");
      return svg(400, 262, "Two tanks in series", s) +
        trend(d.trend, [[1, "t-sp", "setpoint"], [2, "t-cv", "tank 1"], [3, "t-pv", "tank 2"]], "Trend of the two levels");
    },
    garage(d) {
      const x = 120, w = 180, top = 40, h = 170, open = h * d.position / 100;
      let s = `<rect class="road" x="0" y="${top + h}" width="400" height="30"/>`;
      s += `<path class="steel" d="M ${x - 10} ${top + h} V ${top - 10} H ${x + w + 10} V ${top + h}"/>`;
      for (let y = top; y < top + h - open; y += 24) s += `<rect class="box" x="${x}" y="${y}" width="${w}" height="${Math.min(22, top + h - open - y)}"/>`;
      if (d.car) s += `<rect class="car a" x="${x + 30}" y="${top + h - 50}" width="120" height="40" rx="10"/>`;
      s += `<line class="${d.car ? "stop" : "lane"}" x1="${x - 6}" y1="${top + h - 20}" x2="${x + w + 6}" y2="${top + h - 20}"/>${cap(x + w + 14, top + h - 16, "photo-eye")}`;
      s += `<circle class="${cls("motor", d.up || d.down)}" cx="${x + w / 2}" cy="${top - 22}" r="10"/>${cap(x + w / 2 + 16, top - 18, d.up ? "▲ up" : d.down ? "▼ down" : "")}`;
      s += lamp(40, 60, d.warning, "amber", "warning") + lamp(40, 90, d.light, "green", "light");
      s += cap(10, 262, `Door ${f0(d.position)} % open · openings ${d.cycles}${d.hits ? ` · hit the car ${d.hits}×` : ""}`);
      return svg(400, 270, "Garage door", s);
    },
    mixer(d) {
      const x = 120, y = 60, w = 160, h = 170, lvl = d.a + d.b, o = d.outs;
      let s = `<path class="${cls("pipe", o[0])}" d="M 40 20 H ${x + 30} V ${y}"/>${cap(10, 14, "A")}`;
      s += `<path class="${cls("pipe", o[1])}" d="M 360 20 H ${x + w - 30} V ${y}"/>${cap(380, 14, "B")}`;
      const ha = h * Math.min(d.a, 100) / 100, hb = h * Math.min(d.b, 100 - Math.min(d.a, 100)) / 100;
      s += `<rect class="product" x="${x + 2}" y="${y + h - ha}" width="${w - 4}" height="${ha}"/>`;
      s += `<rect class="t-b" x="${x + 2}" y="${y + h - ha - hb}" width="${w - 4}" height="${hb}"/>`;
      s += `<path class="tank" d="M ${x} ${y} V ${y + h} H ${x + w} V ${y}"/>`;
      const a = d.angle * Math.PI / 180, cx = x + w / 2, cy = y + h - 30;
      s += `<line class="steel" x1="${cx}" y1="${y - 20}" x2="${cx}" y2="${cy}"/><line class="steel" x1="${cx - 30 * Math.cos(a)}" y1="${cy}" x2="${cx + 30 * Math.cos(a)}" y2="${cy}"/>`;
      s += `<circle class="${cls("motor", o[2])}" cx="${cx}" cy="${y - 26}" r="11"/>`;
      if (o[3]) s += `<path class="heat" d="M ${x + 10} ${y + h - 6} h ${w - 20}"/>`;
      d.levels.forEach((l, k) => { s += sensor(x + w + 8, y + h - h * l / 100, lvl >= l) + cap(x + w + 16, y + h - h * l / 100 + 4, ["low", "middle", "high"][k]); });
      s += `<path class="${cls("pipe", o[4] && lvl > 0.1)}" d="M ${cx} ${y + h} V ${y + h + 26} H 390"/>`;
      s += lamp(30, 120, o[5], "green", "done");
      s += `<text class="big" x="${cx + 12}" y="${y + 30}">${f1(d.temperature)} °C</text>`;
      s += cap(10, 292, `Mixed ${f1(d.mixed)} s · batches ${d.batches} (good ${d.good})`);
      return svg(400, 300, "Batch mixer", s);
    },
    elevator(d) {
      const x = 150, w = 90, top = 20, fh = 80, bottom = top + 3 * fh, carY = bottom - fh - d.position / d.floor * fh;
      let s = `<rect class="road" x="${x}" y="${top}" width="${w}" height="${3 * fh}"/>`;
      for (let k = 0; k < 3; k++) {
        const y = bottom - k * fh;
        s += `<line class="steel" x1="${x - 140}" y1="${y}" x2="${x}" y2="${y}"/>${cap(x - 138, y - 8, `Floor ${k + 1}`)}`;
        s += lamp(x + w + 20, y - fh / 2, d.outs[4 + k], "amber");
        s += `<circle class="${cls("sensor", d.hall[k])}" cx="${x - 14}" cy="${y - 30}" r="6"/>`;
        if (d.waiting.includes(k)) s += `<circle class="person" cx="${x - 40}" cy="${y - 34}" r="6"/><rect class="person" x="${x - 45}" y="${y - 28}" width="10" height="20" rx="3"/>`;
      }
      s += `<rect class="box" x="${x + 6}" y="${carY + 4}" width="${w - 12}" height="${fh - 8}"/>`;
      const door = (w - 16) / 2 * (1 - d.door / 100);
      s += `<rect class="door" x="${x + 8}" y="${carY + 6}" width="${door}" height="${fh - 12}"/><rect class="door" x="${x + w - 8 - door}" y="${carY + 6}" width="${door}" height="${fh - 12}"/>`;
      if (d.blocked) s += `<circle class="person" cx="${x + w / 2}" cy="${carY + 30}" r="7"/>`;
      s += cap(x + w + 34, 30, d.outs[0] ? "▲ up" : d.outs[1] ? "▼ down" : "") + cap(x + w + 34, 48, d.outs[2] ? "door opening" : d.outs[3] ? "door closing" : "");
      s += cap(10, 285, `Calls served ${d.served}`);
      return svg(400, 292, "Elevator", s);
    },
    bottles(d) {
      const y = 170, o = d.outs, X = (v) => 10 + v * 360 / d.length;
      let s = belt(y, o[0]);
      const [fx, cx, ix] = d.stations.map(X);
      s += `<rect class="${cls("valve", o[1])}" x="${fx - 10}" y="60" width="20" height="30"/>${cap(fx, 50, "filler", "middle")}`;
      if (o[1]) s += `<rect class="product" x="${fx - 3}" y="90" width="6" height="${y - 90 - 40}"/>`;
      s += `<rect class="${cls("valve", o[2])}" x="${cx - 16}" y="${o[2] ? 96 : 70}" width="32" height="18"/>${cap(cx, 50, "capper", "middle")}`;
      s += `<rect class="${cls("valve", o[3])}" x="${ix - 12}" y="${o[3] ? y - 40 : y - 70}" width="24" height="24"/>${cap(ix, 50, "inspect", "middle")}`;
      for (const b of d.bottles) {
        const bx = X(b.x);
        if (bx < 0 || bx > 372) continue;
        const fh = 50 * Math.min(b.fill, 110) / 110;
        s += `<rect class="box" x="${bx - 10}" y="${y - 52}" width="20" height="52" rx="4"/><rect class="product" x="${bx - 8}" y="${y - fh}" width="16" height="${fh}"/>`;
        if (b.capped) s += `<rect class="${b.bad ? "badcap" : "cap2"}" x="${bx - 7}" y="${y - 60}" width="14" height="8"/>`;
      }
      s += lamp(20, 30, o[4], "green", "run");
      s += cap(10, 215, `Shipped good ${d.good} · bad ${d.bad} · rejected ${d.rejected}`);
      return svg(400, 225, "Bottle line", s);
    },
    sorter(d) {
      const y = 160, o = d.outs, X = (v) => 10 + v * 360 / d.length;
      let s = belt(y, o[0]);
      const mx = X(d.measure);
      s += `<line class="lane beam" x1="${mx}" y1="${y - d.heights.M + 6}" x2="${mx}" y2="${y - 60}"/>${cap(mx, y - 66, "beams", "middle")}`;
      d.pushers.forEach((p, k) => {
        const px = X(p);
        s += `<rect class="${cls("valve", o[k + 1])}" x="${px - 14}" y="${o[k + 1] ? y + 14 : y + 30}" width="28" height="14"/>`;
        s += `<rect class="tank" x="${px - 22}" y="20" width="44" height="50"/>${cap(px, 90, d.bins[k], "middle")}${cap(px, 15, `bin ${k + 1} · ${"SML"[k]}`, "middle")}`;
      });
      for (const b of d.boxes) {
        const bx = X(b.x), h = d.heights[b.size];
        if (bx < -20 || bx > 372) continue;
        s += `<rect class="box" x="${bx - 14}" y="${y - h}" width="28" height="${h}"/>${cap(bx, y - h / 2 + 4, b.size, "middle")}`;
      }
      s += lamp(20, 30, o[4], "green", "run");
      s += cap(10, 222, `Wrong bin ${d.wrong} · fell off ${d.fallen}`);
      return svg(400, 230, "Sorting conveyor", s);
    },
    pick_place(d) {
      const x0 = 80, x1 = 320, ax = x0 + (x1 - x0) * d.x / 100, top = 50, az = top + 30 + 110 * d.z / 100;
      let s = `<rect class="steel" x="40" y="${top - 10}" width="320" height="16"/>`;
      s += `<rect class="${cls("valve", d.outs[0])}" x="${ax - 18}" y="${top - 14}" width="36" height="24"/>`;
      s += `<line class="steel" x1="${ax}" y1="${top + 10}" x2="${ax}" y2="${az}"/><rect class="${cls("valve", d.outs[2])}" x="${ax - 14}" y="${az}" width="28" height="10"/>`;
      if (d.held) s += `<rect class="part" x="${ax - 12}" y="${az + 10}" width="24" height="18"/>`;
      s += `<rect class="belt" x="${x0 - 40}" y="210" width="80" height="10"/>${cap(x0, 236, "pick", "middle")}`;
      if (d.waiting) s += `<rect class="part" x="${x0 - 12}" y="192" width="24" height="18"/>`;
      s += `<path class="tank" d="M ${x1 - 40} 190 V 220 H ${x1 + 40} V 190"/>${cap(x1, 236, "tray", "middle")}`;
      s += lamp(20, 20, d.outs[3], "green", "cycle");
      s += cap(10, 262, `Placed ${d.placed} · dropped ${d.dropped}`);
      return svg(400, 270, "Pick and place", s);
    },
    parking(d) {
      let s = `<rect class="road" x="0" y="80" width="400" height="90"/>`;
      const barrier = (x, y, up, label) => {
        const a = up / 100 * Math.PI / 2;
        return `<circle class="motor" cx="${x}" cy="${y}" r="6"/><line class="barrier" x1="${x}" y1="${y}" x2="${x + 80 * Math.cos(a)}" y2="${y - 80 * Math.sin(a)}"/>${cap(x - 10, y + 20, label)}`;
      };
      s += barrier(120, 120, d.entry, "entry →") + barrier(250, 160, d.exit, "← exit");
      for (let k = 0; k < Math.min(d.entry_queue, 4); k++) s += `<rect class="car a" x="${70 - k * 50}" y="90" width="44" height="24" rx="6"/>`;
      for (let k = 0; k < Math.min(d.exit_queue, 4); k++) s += `<rect class="car b" x="${270 + k * 50}" y="136" width="44" height="24" rx="6"/>`;
      s += `<rect class="head" x="300" y="10" width="90" height="56" rx="6"/><text class="seg7" x="345" y="42" text-anchor="middle">${d.display >= 0 ? String(d.display).padStart(2, "0") : "--"}</text>`;
      s += `<text class="${d.full ? "fullsign on" : "fullsign"}" x="345" y="60" text-anchor="middle">FULL</text>`;
      for (let k = 0; k < d.capacity; k++) s += `<rect class="${k < d.parked ? "car a" : "box"}" x="${10 + k * 28}" y="200" width="22" height="36" rx="4"/>`;
      s += cap(10, 262, `Parked ${d.parked}/${d.capacity} · in ${d.entered} · out ${d.left}`);
      return svg(400, 270, "Parking garage", s);
    },
    pumps(d) {
      const x = 140, y = 30, w = 140, h = 200;
      let s = `<path class="pipe flow" d="M 10 16 H ${x + 20} V ${y + 10}"/>${cap(10, 36, "inflow")}`;
      s += tank(x, y, w, h, d.level);
      d.levels.forEach((l, k) => { s += sensor(x - 10, y + h - h * l / 100, d.level >= l) + cap(x - 18, y + h - h * l / 100 + 4, ["low", "start", "high", "alarm"][k], "end"); });
      for (let k = 0; k < 2; k++) {
        const px = x + 30 + k * 70;
        s += `<path class="${cls("pipe", d.running[k])}" d="M ${px} ${y + h - 20} V ${y - 10} H ${px + 30}"/>`;
        s += `<circle class="${d.fault[k] ? "motor fault" : cls("motor", d.running[k])}" cx="${px}" cy="${y + h - 20}" r="13"/>${cap(px, y + h + 22, `P${k + 1} ${d.hours[k]} s`, "middle")}`;
      }
      s += `<text class="big" x="${x + w / 2}" y="${y + 40}" text-anchor="middle">${f1(d.level)} %</text>`;
      s += lamp(330, 60, d.alarm, "red", "alarm");
      s += cap(10, 285, `Starts P1 ${d.starts[0]} · P2 ${d.starts[1]}`);
      return svg(400, 292, "Pump station", s);
    },
    hvac(d) {
      let s = `<rect class="tank" x="60" y="30" width="260" height="170"/>`;
      s += `<rect class="${d.window ? "winopen" : "box"}" x="250" y="60" width="60" height="50"/>${cap(250, 52, d.window ? "window open" : "window")}`;
      s += `<circle class="${cls("motor", d.fan)}" cx="100" cy="170" r="14"/>${cap(84, 214, "fan")}`;
      s += `<rect class="heater" x="130" y="160" width="60" height="20" opacity="${0.2 + 0.8 * d.heater / 100}"/>${cap(130, 214, `heat ${f0(d.heater)} %`)}`;
      s += `<rect class="cooler" x="210" y="160" width="60" height="20" opacity="${0.2 + 0.8 * d.cooler / 100}"/>${cap(210, 214, `cool ${f0(d.cooler)} %`)}`;
      s += `<text class="big" x="150" y="100" text-anchor="middle">${f1(d.temperature)} °C</text>${cap(110, 124, `setpoint ${f1(d.setpoint)} °C`)}`;
      s += cap(330, 40, `outside`) + cap(330, 56, `${f1(d.outside)} °C`);
      s += lamp(340, 150, d.lamps[0], "red", "heat") + lamp(340, 174, d.lamps[1], "green", "cool");
      return svg(400, 225, "Room climate", s) +
        trend(d.trend, [[1, "t-sp", "setpoint"], [2, "t-pv", "room"], [3, "t-cv", "heater"]], "Trend of the room temperature (0-100 = 0-50 °C)");
    },
    washer(d) {
      const cx = 170, cy = 130, r = 80, o = d.outs;
      let s = `<rect class="box" x="60" y="20" width="220" height="230" rx="10"/>`;
      s += `<circle class="tank" cx="${cx}" cy="${cy}" r="${r}"/>`;
      const wl = 2 * r * Math.min(d.water, 100) / 100;
      s += `<clipPath id="drum"><circle cx="${cx}" cy="${cy}" r="${r - 3}"/></clipPath><rect class="product" clip-path="url(#drum)" x="${cx - r}" y="${cy + r - wl}" width="${2 * r}" height="${wl}"/>`;
      const a = d.angle * Math.PI / 180;
      for (let k = 0; k < 3; k++) {
        const b = a + k * 2 * Math.PI / 3;
        s += `<line class="steel" x1="${cx + 30 * Math.cos(b)}" y1="${cy + 30 * Math.sin(b)}" x2="${cx + 70 * Math.cos(b)}" y2="${cy + 70 * Math.sin(b)}"/>`;
      }
      s += `<circle class="${d.door_closed ? "doorring" : "doorring open"}" cx="${cx}" cy="${cy}" r="${r + 6}"/>`;
      s += cap(300, 40, d.locked ? "🔒 locked" : "unlocked") + cap(300, 60, `${f0(Math.abs(d.rpm))} rpm ${d.rpm < -1 ? "left" : d.rpm > 1 ? "right" : ""}`);
      s += cap(300, 80, `water ${f0(d.water)} %`);
      s += `<path class="${cls("pipe", o[1])}" d="M 300 110 H 280"/>${cap(300, 114, "fill")}<path class="${cls("pipe", o[5])}" d="M ${cx} 250 V 270 H 300"/>${cap(306, 274, "drain")}`;
      s += lamp(310, 150, o[6], "green", "done");
      s += cap(10, 292, `Washed left ${d.left} s · right ${d.right} s · spun ${d.spun} s · cycles ${d.cycles}`);
      return svg(400, 300, "Washing machine", s);
    },
  };

  // -- controls and devices -------------------------------------------------------------------------
  function controls(m) {
    const c = m.controls.map((x) => {
      if (x.t === "hold") return `<button class="pbtn" data-act="${e(x.act)}" data-hold title="${x.nc ? "Hold to press (normally closed)" : "Hold to press"}">${e(x.label)}</button>`;
      if (x.t === "button") return `<button data-act="${e(x.act)}">${e(x.label)}</button>`;
      if (x.t === "check") return `<label><input type="checkbox" data-act="${e(x.act)}"> ${e(x.label)}</label>`;
      return "";
    }).join("");
    const sliders = m.controls.filter((x) => x.t === "slider").map((x) =>
      `<label>${e(x.label)} <span data-val="${e(x.act)}"></span><input type="range" min="${x.min}" max="${x.max}" step="1" data-act="${e(x.act)}"></label>`).join("");
    const dev = ([name, addr], k) => `<li><span class="dot" data-dev="${k}"></span><span class="dname">${e(name)}</span>
      <span class="addr" draggable="true" data-addr="${e(addr)}" title="Drag onto an instruction">${e(addr)}</span></li>`;
    const ins = m.devices.inputs, outs = m.devices.outputs;
    return `<div class="ctl">${c}<button data-act="reset" title="Start the machine again">Reset</button></div>` +
      (sliders ? `<div class="knobs">${sliders}</div>` : "") +
      `<div class="drawing"></div><ul class="events"></ul>` +
      `<div class="devs"><div><h4>Inputs</h4><ul>${ins.map((d, k) => dev(d, "i" + k)).join("")}</ul></div>
       <div><h4>Outputs</h4><ul>${outs.map((d, k) => dev(d, "o" + k)).join("")}</ul></div></div>`;
  }

  let key = "";
  function render(el, m) {
    const k = m.kind + JSON.stringify([m.controls.map((c) => c.act), m.devices.inputs.map((d) => d[1]), m.devices.outputs.map((d) => d[1])]);
    if (k !== key) { key = k; el.innerHTML = `<div class="machine">${controls(m)}</div>`; }
    el.querySelector(".drawing").innerHTML = DRAW[m.kind](m.draw);
    const all = { ...Object.fromEntries(m.devices.inputs.map((d, i) => ["i" + i, d[2]])), ...Object.fromEntries(m.devices.outputs.map((d, i) => ["o" + i, d[2]])) };
    el.querySelectorAll("[data-dev]").forEach((dot) => {
      const v = all[dot.dataset.dev];
      dot.className = "dot" + (v === true ? " on" : "") + (typeof v === "string" ? " val" : "");
      dot.textContent = typeof v === "string" ? v : "";
    });
    for (const c of m.controls) {
      const input = el.querySelector(`input[data-act="${c.act}"]`);
      if (c.t === "check" && input) input.checked = !!c.value;
      if (c.t === "slider") {
        if (input && document.activeElement !== input) input.value = c.value;
        const v = el.querySelector(`[data-val="${c.act}"]`);
        if (v) v.textContent = `${Math.round(c.value)} ${c.unit}`;
      }
    }
    el.querySelector(".events").innerHTML = m.events.map((t) => `<li>⚠ ${e(t)}</li>`).join("");
  }

  return { render, reset: () => { key = ""; }, draw: (m) => DRAW[m.kind](m.draw) };
})();
