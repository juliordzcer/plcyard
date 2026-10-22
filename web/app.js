// PLCYard web: the page around plcyard/webapp.py (the PLC, the I/O panel model, the ladder editor and the
// exercise checker), which runs in the browser with Pyodide. Python owns the program; this file draws it.
"use strict";

const TICK_MS = 50;
const VERSION = document.documentElement.dataset.version;
const GUTTER = 48, MARGIN = 12, RUNG_GAP = 18, COMMENT_LINE = 16, WIRE_Y = 26;
const $ = (id) => document.getElementById(id);
let py, S, state = null, lastJson = "", family = null, palette = [], opsKey = "", HL = null, stKey = "", tagsKey = "";
let fbdKey = "", paletteLang = "", routinesKey = "", ifaceKey = "", machineKind = "", showAllIo = false;
let EXERCISES = [], EXAMPLES = [], THUMBS = {}, lastOpInput = null, zoom = 1;

function setTab(tab) {
  document.body.dataset.tab = tab;
  document.querySelectorAll("#tabbar [data-tab]").forEach((b) => b.classList.toggle("on", b.dataset.tab === tab));
}

function setZoom(z) {
  zoom = Math.min(2, Math.max(0.5, z));
  for (const id of ["ladder", "fbd"]) $(id).style.setProperty("--zoom", zoom);
}

const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const store = {
  get(k) { try { return localStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch { /* private window: no autosave */ } },
};
const js = (proxy) => { const v = proxy.toJs({ dict_converter: Object.fromEntries }); proxy.destroy?.(); return v; };

// -- start ---------------------------------------------------------------------------------------
async function start() {
  try {
    py = await loadPyodide();
    $("loadmsg").textContent = "Unpacking PLCYard…";
    const zip = await (await fetch(`plcyard.zip?v=${VERSION}`)).arrayBuffer();
    py.unpackArchive(zip, "zip", { extractDir: "/home/pyodide/app" });
    py.runPython("import sys; sys.path.insert(0, '/home/pyodide/app')");
    S = py.runPython("from plcyard.webapp import Session\nSession()");
    EXAMPLES = js(S.examples());
    buildHighlighter(js(S.st_syntax()));
    EXERCISES = js(S.exercises());
    THUMBS = thumbnails(JSON.parse(S.previews()));
    const n = store.get("plcyard.notation") || "B";          // new visitors start with IEC symbols
    if (n === "A" || n === "B") { S.set_notation(n); $("b-notation").value = n; }
    const saved = store.get("plcyard.program");
    if (saved) S.open_text(saved);
    else S.open_example("start-stop");
    const sim = store.get("plcyard.sim");
    if (saved && sim) S.set_sim(sim);
    buildPalette();
    wire();
    $("loading").classList.add("gone");
    render(true);
    setInterval(loop, TICK_MS);
    watchVersion();
    if (!store.get("plcyard.welcomed")) { store.set("plcyard.welcomed", "1"); $("d-welcome").showModal(); }
  } catch (e) {
    $("loadmsg").textContent = "Could not start the simulator: " + e;
  }
}

function loop() {
  if (state && state.mode === "RUN") S.tick(TICK_MS);
  render();
}

function changed(msg) {
  store.set("plcyard.program", S.save_text());
  store.set("plcyard.sim", state ? state.machine.kind : "io");
  say(msg || "");
  render(true);
}

function say(msg, err) {
  const st = $("status");
  st.textContent = msg || "";
  st.classList.toggle("err", !!err);
}

// -- drawing -------------------------------------------------------------------------------------
function render(force) {
  const width = Math.max(window.innerWidth <= 760 ? 260 : 500, $("ladder").clientWidth - GUTTER - 2 * MARGIN - 8);
  const text = S.state(width);
  if (!force && text === lastJson) return;
  lastJson = text;
  state = JSON.parse(text);
  $("led-run").className = "led" + (state.mode === "RUN" ? " run" : "");
  $("led-fault").className = "led" + (state.fault ? " fault" : "");
  $("b-pgm").classList.toggle("on", state.mode !== "RUN");
  $("b-run").classList.toggle("on", state.mode === "RUN");
  $("scans").textContent = state.mode === "RUN" ? `${state.scans} scans` : "";
  $("b-undo").disabled = !state.can_undo;
  $("b-redo").disabled = !state.can_redo;
  $("b-download").hidden = !(state.mode === "RUN" && state.dirty);
  if (state.fault) say("Fault: " + state.fault, true);
  else if (state.problems.length) say(state.problems.join(" · "), true);
  else if (state.message) say(state.message);
  for (const sel of document.querySelectorAll(".simsel")) {
    if (!sel.options.length) for (const [k, t] of state.sims) sel.add(new Option(t, k));
    if (document.activeElement !== sel) sel.value = state.machine.kind;
  }
  $("led-run2").className = "led" + (state.mode === "RUN" ? " run" : "") + (state.fault ? " fault" : "");
  $("b-runm").textContent = state.mode !== "RUN" ? "RUN" : state.dirty ? "Send" : "Stop";
  $("tab-lab").textContent = state.lab ? "Exercise" : "Exercises";
  $("io").hidden = !state.io;
  $("machine").hidden = !!state.io;
  $("simhint").textContent = state.io
    ? "Click a switch to flip it (pushbuttons spring back). Select an instruction, then drag or tap an address to use it."
    : "Hold a button to press it. Select an instruction, then drag or tap an address to use it.";
  if (state.io) renderIo(state.io);
  else {
    if (machineKind !== state.machine.kind) { machineKind = state.machine.kind; Sims.reset(); Machines.reset(); }
    (state.machine.controls ? Machines : Sims).render($("machine"), state.machine);
  }
  const st = state.language === "ST", fb = state.language === "FBD";
  renderRoutines(state);
  renderInterface(state);
  if (paletteLang !== state.language) { paletteLang = state.language; family = null; buildPalette(); }
  for (const id of ["families", "palette"]) $(id).hidden = st;
  $("ladder").hidden = st || fb;
  $("fbd").hidden = !fb;
  $("stwrap").hidden = !st;
  if (st) { $("operands").hidden = true; opsKey = ""; renderSt(state.st); }
  else if (fb) { renderFbd(state); renderBlockForm(state); }
  else { renderLadder(state); renderOperands(state); }
  renderSuggestions(state);
  placeForm();
  if (!$("tagpane").hidden) renderTags(state.tags);
}

// -- structured text -------------------------------------------------------------------------------
function buildHighlighter(syn) {
  HL = new RegExp([
    String.raw`(\/\/[^\n]*|\(\*[\s\S]*?(?:\*\)|$)|\/\*[\s\S]*?(?:\*\/|$))`,
    String.raw`("[^"\n]*"|%[IQM][BWD]?\d+(?:\.\d)?)`,
    String.raw`\b((?:T|TIME)#[0-9A-Za-z_.]+|\d+#[0-9A-Fa-f_]+|\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\b`,
    String.raw`\b(${syn.keywords.join("|")})\b`,
    String.raw`\b(${syn.functions.join("|")}|\w+_TO_\w+)(?=\s*\()`,
  ].join("|"), "gi");
}

function highlight(src) {
  let out = "", last = 0;
  src.replace(HL, (m, c, a, n, k, f, off) => {
    out += esc(src.slice(last, off)) + `<span class="${c ? "hl-c" : a ? "hl-a" : n ? "hl-n" : k ? "hl-k" : "hl-f"}">${esc(m)}</span>`;
    last = off + m.length;
    return m;
  });
  return out + esc(src.slice(last)) + "\n";
}

function paintCode(src, errLines) {
  $("sthl").innerHTML = highlight(src);
  const bad = new Set(errLines || []);
  $("stgut").innerHTML = src.split("\n").map((_, i) => `<div${bad.has(i + 1) ? ' class="err"' : ""}>${i + 1}</div>`).join("");
}

function renderSt(st) {
  const ta = $("stsrc");
  if (document.activeElement !== ta && ta.value !== st.source) ta.value = st.source;
  const key = JSON.stringify([ta.value, st.lines, st.problems, st.watch]);
  if (key === stKey) return;
  stKey = key;
  paintCode(ta.value, st.lines);
  $("stprob").textContent = st.problems.slice(0, 6).join("\n") + (st.problems.length > 6 ? `\n…and ${st.problems.length - 6} more` : "");
  $("stwatch").innerHTML = st.watch.map(([n, v]) => `<tr><td>${esc(n)}</td><td>${esc(v)}</td></tr>`).join("");
}

// -- routines --------------------------------------------------------------------------------------
const KIND = { LAD: "", SBR: "SBR", FC: "FC", FB: "FB" };
const LANG = { LD: "LD", ST: "ST", FBD: "FBD" };

function renderRoutines(st) {
  const key = JSON.stringify([st.routines, st.routine]);
  if (key === routinesKey) return;
  routinesKey = key;
  $("routines").innerHTML = st.routines.map((r) => {
    const on = r.number === st.routine, main = r.number === 2;
    return `<span class="rt${on ? " on" : ""}" role="tab" aria-selected="${on}" data-routine="${r.number}" title="${esc(r.title)}: ${esc(KIND[r.kind] ? r.kind + " " : "")}in ${esc(LANG[r.language])}">
      ${esc(r.title)} <span class="k">${esc([KIND[r.kind], LANG[r.language]].filter(Boolean).join(" · "))}</span>
      ${on && !main ? `<button data-rename title="Rename">✎</button><button data-delroutine title="Delete">✕</button>` : ""}</span>`;
  }).join("");
}

function renderInterface(st) {
  const box = $("iface"), f = st.interface;
  box.hidden = !f;
  if (!f) { ifaceKey = ""; return; }
  const key = JSON.stringify(f);
  if (key === ifaceKey || box.contains(document.activeElement)) return;
  ifaceKey = key;
  box.querySelector("summary").textContent = `Parameters (${f.rows.length})`;
  const types = js(S.tag_types());
  const row = (p) => `<div class="prow" data-section="${esc(p.section)}" data-old="${esc(p.name)}">
    ${p.name ? `<span class="sec">${esc(p.section)}</span>` : `<select name="section" aria-label="Section">${f.sections.map((x) => `<option>${esc(x)}</option>`).join("")}</select>`}
    <input name="name" value="${esc(p.name)}" placeholder="Name" aria-label="Name" spellcheck="false">
    <input name="type" list="tagtypes" value="${esc(p.type)}" aria-label="Data type" spellcheck="false">
    ${p.name ? `<button class="ghost" data-delparam title="Delete">✕</button>` : `<button class="primary" data-addparam title="Add">+</button>`}</div>`;
  $("ifacelist").innerHTML = f.rows.map(row).join("") + row({ section: f.sections[0], name: "", type: "BOOL" });
  $("tagtypes").innerHTML = types.map((x) => `<option value="${esc(x)}">`).join("");
  const which = JSON.stringify(st.routines.find((r) => r.number === st.routine));
  if (box.dataset.routine !== which) { box.dataset.routine = which; box.open = !f.rows.length; }
}

// -- the operand form, next to what it edits -----------------------------------------------------------
let suggKey = "";
function renderSuggestions(st) {
  const out = new Map();
  const add = (v, label) => { if (v && !out.has(v)) out.set(v, label || ""); };
  if (st.io) for (const c of st.io.inputs.concat(st.io.outputs)) for (const p of c.points) if (p.symbol || p.used) add(p.addr, p.symbol);
  const m = st.machine;
  if (m && m.devices) for (const [label, addr] of m.devices.inputs.concat(m.devices.outputs)) add(addr, label);
  else if (m && m.addr) for (const [k, v] of Object.entries(m.addr)) for (const a of [].concat(v)) add(a, k.replace(/_/g, " "));
  for (const t of st.tags) add(t.name, `${t.type}${t.comment ? " · " + t.comment : ""}`);
  const key = JSON.stringify([...out]);
  if (key === suggKey) return;
  suggKey = key;
  $("opsugg").innerHTML = [...out].map(([v, l]) => `<option value="${esc(v)}">${esc(l)}</option>`).join("");
}

function placeForm() {
  const form = $("operands");
  if (form.hidden) return;
  const ed = form.parentElement.getBoundingClientRect();
  const target = state.language === "FBD" ? $("fbd").querySelector(".box.picked, path.w.picked") : $("ladder").querySelector("rect.sel");
  const r = target && target.getBoundingClientRect();
  if (!r || r.bottom < ed.top || r.top > ed.bottom || window.innerWidth <= 760) { form.classList.remove("float"); return; }
  form.classList.add("float");
  const fw = form.offsetWidth, fh = form.offsetHeight;
  let top = r.bottom - ed.top + 6;
  if (top + fh > ed.height - 4) top = Math.max(4, r.top - ed.top - fh - 6);
  form.style.top = `${top}px`;
  form.style.left = `${Math.min(Math.max(8, r.left - ed.left), Math.max(8, ed.width - fw - 8))}px`;
}

// -- function blocks -------------------------------------------------------------------------------
function renderFbd(st) {
  const key = JSON.stringify([st.fbd, st.sel, $("fbd").clientWidth]);
  if (key === fbdKey || Fbd.busy()) return;
  fbdKey = key;
  Fbd.render($("fbd"), st.fbd, st.sel);
}

function renderBlockForm(st) {
  const form = $("operands"), b = st.block;
  const wireSel = st.sel && st.sel[0] === "wire";
  const key = JSON.stringify([st.sel, b]);
  if (key === opsKey) return;
  opsKey = key;
  form.hidden = !b && !wireSel;
  if (wireSel) { form.innerHTML = `<span class="what">Wire</span><button type="button" id="b-del">Delete wire</button>`; return; }
  if (!b) return;
  const field = (name, label, value, attrs = "") => `<label>${esc(label)}<input name="${esc(name)}" list="opsugg" value="${esc(value)}" autocomplete="off" spellcheck="false" ${attrs}></label>`;
  form.innerHTML = `<span class="what" title="${esc(b.title)}">${esc(b.type)}</span>` +
    (b.kind ? field("@instance", `${b.kind} tag`, b.instance) : "") +
    b.pins.map((p) => p.wired ? field(p.name, p.name, "wired", "disabled") : field(p.name, p.name + (p.out ? " →" : ""), p.op, `placeholder="${p.out ? "none" : "tag, address or value"}"`)).join("") +
    `<button class="primary" type="submit">Apply</button>` +
    (b.variable ? `<button type="button" id="b-addin">Input +</button>${b.inputs > 2 ? `<button type="button" id="b-remin">Input −</button>` : ""}` : "") +
    `<button type="button" id="b-del">Delete</button>` +
    (b.problems.length ? `<span class="probs">${esc(b.problems.join(" · "))}</span>` : "");
}

// -- tags --------------------------------------------------------------------------------------------
function renderTags(tags) {
  const pane = $("tagpane");
  const key = JSON.stringify(tags);
  if (key === tagsKey || pane.contains(document.activeElement)) return;
  tagsKey = key;
  const types = js(S.tag_types());
  const row = (t) => `<div class="tagrow" data-old="${esc(t.name)}">
      <input name="name" value="${esc(t.name)}" placeholder="Name" aria-label="Name" spellcheck="false">
      <input name="type" list="tagtypes" value="${esc(t.type)}" aria-label="Type" title="A type, or an array like DINT[10]" spellcheck="false">
      ${t.name ? `<button class="ghost" data-del title="Delete">✕</button>` : `<button class="primary" data-add title="Add">+</button>`}
      <input class="tc" name="comment" value="${esc(t.comment)}" placeholder="Description" aria-label="Description"></div>`;
  $("taglist").innerHTML = tags.map(row).join("") + row({ name: "", type: "BOOL", comment: "" });
  $("tagtypes").innerHTML = types.map((x) => `<option value="${esc(x)}">`).join("");
}

function renderIo(io) {
  const all = io.inputs.concat(io.outputs).flatMap((c) => c.points);
  const some = all.some((p) => p.used || p.symbol);
  const full = showAllIo || !some;
  const shown = (p) => full || p.used || p.symbol;
  const card = (c, input) => !c.points.some(shown) ? "" : `<div class="card-io"><h3>${esc(c.name)}</h3>${c.points.filter(shown).map((p) => `
    <div class="pt">${input
      ? `<button class="sw${p.momentary ? " pb" : ""}${p.pressed !== p.nc ? " closed" : ""}" data-slot="${c.slot}" data-bit="${p.bit}"
           data-pb="${p.momentary ? 1 : 0}" aria-pressed="${p.pressed}" title="${p.nc ? "Normally closed" : "Normally open"}${p.momentary ? " pushbutton" : " switch"}"></button>`
      : `<span class="lamp${p.on ? " on" : ""}" role="img" aria-label="${p.on ? "on" : "off"}"></span>`}
      <span class="txt"><span class="addr" draggable="true" data-addr="${esc(p.addr)}" title="Drag onto an instruction · double-click to describe">${esc(p.addr)}</span>
      ${p.symbol ? `<span class="sym">${esc(p.symbol)}</span>` : ""}</span></div>`).join("")}</div>`;
  const bcd = !full && !io.bcd_used ? "" : `<div class="bcd"><span class="mono">${esc(io.thumb_name)} (BCD)</span><span class="digits">${io.thumbwheels.map((d, i) =>
      `<input type="number" min="0" max="9" value="${d}" data-digit="${i}" aria-label="Thumbwheel digit ${i + 1}">`).join("")}</span>
    <span class="mono">${esc(io.display_name)} (BCD)</span><span class="digits">${io.display.map((d) => `<span class="seg">${d > 9 ? "-" : d}</span>`).join("")}</span></div>`;
  const html = `<div class="cards">${card(io.inputs[0], true)}${card(io.outputs[0], false)}${card(io.inputs[1], true)}${card(io.outputs[1], false)}</div>
    ${some ? `<button class="linkbtn" id="b-allio">${showAllIo ? "Show only the points in use" : `Show all ${all.length} points`}</button>` : ""}${bcd}`;
  const el = $("io");
  if (el.dataset.html === html) return;
  el.dataset.html = html;
  el.innerHTML = html;
}

function wrapText(text, width) {
  const per = Math.max(20, Math.floor(width / 6.6)), out = [];
  for (const para of text.split("\n")) {
    let line = "";
    for (const word of para.split(" ")) {
      if ((line + " " + word).trim().length > per && line) { out.push(line); line = word; }
      else line = (line + " " + word).trim();
    }
    out.push(line);
  }
  return out;
}

function instrSvg(it, n, ox, oy, sel) {
  const x = ox + it.x, y = oy + it.y, w = it.w, h = it.h, mid = y + WIRE_Y, cx = x + w / 2;
  const cls = "w" + (it.on ? " on" : "");
  const unset = !it.ops.length || it.ops.some((o) => o === "" || o === "?");
  let s = sel ? `<rect class="sel" x="${x + 1}" y="${y + 1}" width="${w - 2}" height="${h - 2}" rx="4"/>` : "";
  if (it.shape !== "block") {
    s += `<line class="${cls}" x1="${x}" y1="${mid}" x2="${cx - 9}" y2="${mid}"/><line class="${cls}" x1="${cx + 9}" y1="${mid}" x2="${x + w}" y2="${mid}"/>`;
    if (it.on) s += `<rect class="fill" x="${cx - 8}" y="${mid - 9}" width="16" height="18"/>`;
    if (it.shape === "contact" || it.shape === "contact_nc") {
      s += `<line class="${cls}" x1="${cx - 8}" y1="${mid - 9}" x2="${cx - 8}" y2="${mid + 9}"/><line class="${cls}" x1="${cx + 8}" y1="${mid - 9}" x2="${cx + 8}" y2="${mid + 9}"/>`;
      if (it.shape === "contact_nc") s += `<line class="${cls}" x1="${cx - 6}" y1="${mid + 8}" x2="${cx + 6}" y2="${mid - 8}"/>`;
      else if (it.letter) s += `<text class="lab" x="${cx}" y="${mid + 4}" text-anchor="middle">${esc(it.letter)}</text>`;
    } else if (it.shape === "coil") {
      const half = 6 + 3.5 * Math.max((it.letter || "").length, 1);
      s += `<path class="${cls} nofill" d="M ${cx - half + 5} ${mid - 9} A 5 9 0 0 0 ${cx - half + 5} ${mid + 9} M ${cx + half - 5} ${mid - 9} A 5 9 0 0 1 ${cx + half - 5} ${mid + 9}"/>`;
      if (it.letter) s += `<text class="lab" x="${cx}" y="${mid + 4}" text-anchor="middle">${esc(it.letter)}</text>`;
    } else {
      s += `<rect class="${cls} nofill" x="${cx - 14}" y="${mid - 9}" width="28" height="18"/><text class="lab" x="${cx}" y="${mid + 4}" text-anchor="middle">${esc(it.letter || it.title)}</text>`;
    }
    s += `<text class="${unset ? "unset" : ""}" x="${cx}" y="${y + 12}" text-anchor="middle">${esc(it.ops[0] || "?")}</text>`;
    if (it.symbol) s += `<text class="sym" x="${cx}" y="${mid + 22}" text-anchor="middle">${esc(it.symbol)}</text>`;
  } else {
    const bx = x + 8, by = y + 4, bw = w - 16, bh = h - 8;
    s += `<line class="${cls}" x1="${x}" y1="${mid}" x2="${bx}" y2="${mid}"/><line class="${cls}" x1="${bx + bw}" y1="${mid}" x2="${x + w}" y2="${mid}"/>`;
    s += `<rect class="${cls} box${it.on ? " lit" : ""}" x="${bx}" y="${by}" width="${bw}" height="${bh}" rx="4"/>`;
    s += `<text class="title" x="${bx + 8}" y="${by + 17}">${esc(it.title)}</text>`;
    const rows = it.ops.map((op, i) => [it.labels[i] || "", op, false]);
    for (const [lab, val] of it.extra) {
      const k = rows.findIndex((r) => r[0] === lab);
      if (k < 0) rows.push([lab, val, true]); else rows[k] = [lab, val, true];
    }
    let ry = by + 26;
    for (const [lab, op, live] of rows) {
      s += `<text class="lab" x="${bx + 8}" y="${ry + 12}"><title>${esc(lab)}</title>${esc(lab.length > 11 ? lab.slice(0, 10) + "…" : lab)}</text>`;
      s += `<text class="${op === "" || op === "?" ? "unset" : live ? "live" : ""}" x="${bx + 70}" y="${ry + 12}">${esc(op || "?")}</text>`;
      ry += 17;
    }
    let py_ = by + 4;
    for (const [name, on] of it.pins) {
      s += `<rect class="pin${on ? " on" : ""}" x="${bx + bw - 30}" y="${py_}" width="26" height="14" rx="3"/>`;
      s += `<text class="pintext${on ? " on" : ""}" x="${bx + bw - 17}" y="${py_ + 11}" text-anchor="middle">${esc(name)}</text>`;
      py_ += 16;
    }
  }
  if (it.problems.length) s += `<rect class="badbox" x="${x + 1}" y="${y + 1}" width="${w - 2}" height="${h - 2}" rx="4"/>`;
  s += `<rect class="hit" data-n="${n}" data-path="${it.path.join(",")}" x="${x}" y="${y}" width="${w}" height="${h}">${it.problems.length ? `<title>${esc(it.problems.join("\n"))}</title>` : ""}</rect>`;
  return s;
}

function renderLadder(st) {
  const el = $("ladder");
  const left = GUTTER + MARGIN;
  const rails = st.rungs.length ? st.rungs[0].width : Math.max(500, el.clientWidth - left - MARGIN - 8);
  let y = 10, s = "";
  const selKey = st.sel ? JSON.stringify(st.sel) : "";
  st.rungs.forEach((r, n) => {
    const top = y;
    const lines = r.comment ? wrapText(r.comment, rails) : [];
    const rungSel = st.sel && st.sel[0] === "rung" && st.sel[1] === n;
    lines.forEach((t, i) => { s += `<text class="comment" x="${left}" y="${y + 12 + i * COMMENT_LINE}">${esc(t)}</text>`; });
    y += lines.length * COMMENT_LINE + (lines.length ? 4 : 0);
    s += `<rect class="hit rung" data-n="${n}" x="0" y="${top - 6}" width="${left + rails + MARGIN}" height="${y - top + r.height + 12}"/>`;
    if (rungSel) s += `<rect class="sel" x="${left - 4}" y="${y - 4}" width="${rails + 8}" height="${r.height + 8}" rx="4"/>`;
    s += `<text class="num${rungSel ? " live" : ""}" x="${GUTTER}" y="${y + WIRE_Y + 4}" text-anchor="end">${String(n).padStart(3, "0")}</text>`;
    s += `<line class="rail" x1="${left}" y1="${y}" x2="${left}" y2="${y + r.height}"/><line class="rail" x1="${left + rails}" y1="${y}" x2="${left + rails}" y2="${y + r.height}"/>`;
    const wires = [...r.wires].sort((a, b) => a[4] - b[4]);
    for (const [x1, y1, x2, y2, on] of wires) s += `<line class="w${on ? " on" : ""}" x1="${left + x1}" y1="${y + y1}" x2="${left + x2}" y2="${y + y2}"/>`;
    for (const leg of r.legs) {
      const sel = selKey === JSON.stringify(["leg", n, leg.path]);
      s += `<rect class="${sel ? "sel" : "hit"} leg" data-n="${n}" data-leg="${leg.path.join(",")}" x="${left + leg.x}" y="${y + leg.y + 8}" width="${leg.w}" height="${leg.h - 16}" rx="4"/>`;
    }
    for (const it of r.instrs) s += instrSvg(it, n, left, y, selKey === JSON.stringify(["instr", n, it.path]));
    y += r.height + RUNG_GAP;
  });
  s += `<line class="rail" x1="${left}" y1="${y}" x2="${left}" y2="${y + 40}"/><line class="rail" x1="${left + rails}" y1="${y}" x2="${left + rails}" y2="${y + 40}"/>`;
  s += `<line class="w" x1="${left}" y1="${y + 20}" x2="${left + rails}" y2="${y + 20}"/><text class="lab endtag" x="${left + rails / 2}" y="${y + 24}" text-anchor="middle">END</text>`;
  if (!st.rungs.length) s += `<text class="empty" x="${left + rails / 2}" y="${y + 64}" text-anchor="middle">Empty program. Click “Rung +”, then an instruction.</text>`;
  y += st.rungs.length ? 0 : 40;
  y += 50;
  el.innerHTML = `<svg width="${left + rails + MARGIN + 4}" height="${y}" role="img" aria-label="Ladder program">${s}</svg>`;
}

function renderOperands(st) {
  const form = $("operands");
  const o = st.operands;
  const key = o ? JSON.stringify([st.sel, o.mnemonic, o.labels, o.values, o.problems]) : "";
  if (key === opsKey) return;
  opsKey = key;
  if (!o) {
    const rungSel = st.sel && st.sel[0] === "rung" && st.sel[1] < st.rungs.length;
    form.hidden = !rungSel;
    if (rungSel) form.innerHTML = `<span class="what">Rung ${String(st.sel[1]).padStart(3, "0")}</span>
      <button type="button" id="b-comment">Comment…</button><button type="button" id="b-del">Delete rung</button>`;
    return;
  }
  const n = Math.max(o.values.length, 1);
  form.hidden = false;
  form.innerHTML = `<span class="what" title="${esc(o.title)}">${esc(o.mnemonic)}</span>` +
    Array.from({ length: n }, (_, i) => `<label>${esc(o.labels[i] || "Operand")}<input name="op" list="opsugg" value="${esc(o.values[i] || "")}" placeholder="address or tag" autocomplete="off" spellcheck="false"></label>`).join("") +
    `<button class="primary" type="submit">Apply</button><button type="button" id="b-branch">Branch</button>
     <button type="button" id="b-leg">Add leg</button><button type="button" id="b-del">Delete</button>` +
    (o.problems.length ? `<span class="probs">${esc(o.problems.join(" · "))}</span>` : "");
}

const ICON = {
  contact: `<svg class="ic" viewBox="0 0 24 14" aria-hidden="true"><path d="M0 7h8M16 7h8M8 1v12M16 1v12"/></svg>`,
  contact_nc: `<svg class="ic" viewBox="0 0 24 14" aria-hidden="true"><path d="M0 7h8M16 7h8M8 1v12M16 1v12M9 12L15 2"/></svg>`,
  coil: `<svg class="ic" viewBox="0 0 24 14" aria-hidden="true"><path d="M0 7h6M18 7h6M9 1a5 6 0 0 0 0 12M15 1a5 6 0 0 1 0 12"/></svg>`,
};

// -- input ---------------------------------------------------------------------------------------
function buildPalette() {
  const fb = paletteLang === "FBD";
  palette = js(fb ? S.fbd_palette() : S.palette());
  family = family || palette[0].family;
  $("families").innerHTML = palette.map((f) => `<button role="tab" class="${f.family === family ? "on" : ""}" data-family="${esc(f.family)}">${esc(f.family)}</button>`).join("");
  const fam = palette.find((f) => f.family === family) || palette[0];
  $("palette").innerHTML = fb
    ? fam.items.map((i) => `<button data-b="${esc(i.m)}" draggable="true" title="${esc(i.title)} · click to add, or drag onto the diagram">${esc(i.name)}</button>`).join("")
    : `<button data-m="RUNG" title="New rung">Rung +</button><button data-m="BRANCH" title="Put the selected instruction in a branch">Branch</button>` +
      fam.items.map((i) => `<button data-m="${esc(i.m)}" title="${esc(i.title)}">${ICON[i.shape] || ""}${esc(i.name)}</button>`).join("");
}

function act(fn) {
  const msg = fn();
  if (msg) say(String(msg), true);
  else changed();
}

function wire() {
  $("families").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-family]");
    if (b) { family = b.dataset.family; buildPalette(); }
  });
  $("palette").addEventListener("dragstart", (e) => {
    const b = e.target.closest("button[data-b]");
    if (b) { e.dataTransfer.setData("application/x-plcyard-block", b.dataset.b); e.dataTransfer.effectAllowed = "copy"; }
  });
  $("palette").addEventListener("click", (e) => {
    const fb = e.target.closest("button[data-b]");
    if (fb) { act(() => S.add_block(fb.dataset.b, ...Fbd.freeSpot())); return; }
    const b = e.target.closest("button[data-m]");
    if (!b) return;
    act(() => S.insert(b.dataset.m));
    setTimeout(() => $("operands").querySelector("input")?.focus(), 0);
  });
  $("io").addEventListener("pointerdown", (e) => {
    const b = e.target.closest(".sw");
    if (!b) return;
    const slot = +b.dataset.slot, bit = +b.dataset.bit, pt = state.io.inputs.find((c) => c.slot === slot).points[bit];
    if (b.dataset.pb === "1") {
      S.press(slot, bit, true);
      const up = () => { S.press(slot, bit, false); render(true); window.removeEventListener("pointerup", up); };
      window.addEventListener("pointerup", up);
    } else S.press(slot, bit, !pt.pressed);
    render(true);
  });
  $("io").addEventListener("change", (e) => {
    const i = e.target.closest("input[data-digit]");
    if (i) { S.thumbwheel(+i.dataset.digit, Math.max(0, Math.min(9, +i.value || 0))); render(true); }
  });
  $("io").addEventListener("dblclick", (e) => {
    const a = e.target.closest(".addr");
    if (!a) return;
    const cur = state.io.inputs.concat(state.io.outputs).flatMap((c) => c.points).find((p) => p.addr === a.dataset.addr);
    const text = prompt(`Description of ${a.dataset.addr} (add "NC" for a normally closed switch, "PB" for a pushbutton):`, cur?.symbol || "");
    if (text !== null) { S.set_symbol(a.dataset.addr, text); changed(); }
  });
  Sims.wire($("machine"), (name, value) => { S.sim_action(name, value); render(true); });
  document.querySelectorAll(".simsel").forEach((sel) => sel.onchange = (e) => {
    S.set_sim(e.target.value); Sims.reset(); store.set("plcyard.sim", e.target.value); render(true);
  });
  // Phone: one view at a time, chosen in the bar at the bottom.
  $("tabbar").addEventListener("click", (e) => {
    const t = e.target.closest("[data-tab]");
    if (!t) return;
    if (t.dataset.tab === "lab" && !state.lab) { openExercises(); return; }
    setTab(t.dataset.tab);
  });
  $("b-runm").onclick = () => {
    if (state.mode !== "RUN") S.set_mode("RUN");
    else if (state.dirty) S.download();
    else S.set_mode("PGM");
    render(true);
  };
  document.querySelectorAll("[data-proxy]").forEach((b) => b.onclick = () => $(b.dataset.proxy).click());
  $("b-zoomin").onclick = () => setZoom(zoom * 1.2);
  $("b-zoomout").onclick = () => setZoom(zoom / 1.2);
  setTab("program");
  // Tap an address (phones cannot drag): it goes into the operand box last used, or the selected instruction.
  $("simpane").addEventListener("click", (e) => {
    const a = e.target.closest(".addr");
    if (!a || !state) return;
    const box = lastOpInput && document.contains(lastOpInput) && !lastOpInput.disabled ? lastOpInput : $("operands").querySelector("input:not([disabled])");
    if (!box || $("operands").hidden) { say("Select an instruction first, then tap an address to use it."); return; }
    box.value = a.dataset.addr;
    $("operands").requestSubmit();
    if (window.innerWidth <= 760) setTab("program");
  });
  $("operands").addEventListener("focusin", (e) => { if (e.target.tagName === "INPUT") lastOpInput = e.target; });
  $("simpane").addEventListener("dragstart", (e) => {
    const a = e.target.closest(".addr");
    if (a) { e.dataTransfer.setData("text/plain", a.dataset.addr); e.dataTransfer.effectAllowed = "copy"; }
  });

  const ladder = $("ladder");
  const target = (e) => document.elementFromPoint(e.clientX, e.clientY)?.closest?.("rect[data-path]");
  ladder.addEventListener("dragover", (e) => {
    const t = target(e);
    ladder.querySelectorAll(".drop").forEach((d) => d.classList.remove("drop"));
    if (t) { e.preventDefault(); t.classList.add("drop"); }
  });
  ladder.addEventListener("drop", (e) => {
    const t = target(e);
    if (!t) return;
    e.preventDefault();
    const probs = js(S.drop_operand(+t.dataset.n, py.toPy(t.dataset.path.split(",").map(Number)), e.dataTransfer.getData("text/plain")));
    changed(probs.join(" · "));
  });
  ladder.addEventListener("click", (e) => {
    const r = e.target.closest("rect[data-n]");
    if (!r) { S.select(null); render(true); return; }
    const n = +r.dataset.n;
    const sel = r.dataset.path !== undefined ? ["instr", n, r.dataset.path.split(",").map(Number)]
      : r.dataset.leg !== undefined ? ["leg", n, r.dataset.leg.split(",").map(Number)] : ["rung", n];
    S.select(py.toPy(sel));
    render(true);
  });
  ladder.addEventListener("dblclick", (e) => {
    if (e.target.closest("rect[data-path]")) $("operands").querySelector("input")?.focus();
  });

  $("routines").addEventListener("click", (e) => {
    const t = e.target.closest("[data-routine]");
    if (!t) return;
    const n = +t.dataset.routine, r = state.routines.find((x) => x.number === n);
    if (e.target.closest("[data-rename]")) {
      const name = prompt("New name (calls to it are renamed too):", r.title);
      if (name !== null) act(() => S.rename_routine(n, name));
    } else if (e.target.closest("[data-delroutine]")) {
      if (confirm(`Delete ${r.title}? Calls to it stop the download until they are removed.`)) act(() => S.delete_routine(n));
    } else if (n !== state.routine) { S.open_routine(n); opsKey = ""; render(true); }
  });
  $("b-addroutine").onclick = () => { $("newroutine").hidden = false; $("newroutine").elements.name.focus(); };
  $("b-cancelroutine").onclick = () => { $("newroutine").hidden = true; };
  $("newroutine").addEventListener("submit", (e) => {
    e.preventDefault();
    const f = e.target, el = f.elements, err = S.add_routine(el.name.value, el.kind.value, el.language.value);
    if (err) { say(err, true); return; }
    f.hidden = true;
    el.name.value = "";
    changed();
  });
  const paramChange = (r, adding) => {
    if (!adding && !r.dataset.old) return;
    const v = (n) => r.querySelector(`[name=${n}]`)?.value ?? "";
    const err = S.set_param(r.dataset.old ? r.dataset.section : v("section"), r.dataset.old, v("name"), v("type"));
    $("ifacemsg").textContent = err;
    if (!err) { ifaceKey = ""; document.activeElement.blur(); changed(); }
  };
  $("ifacelist").addEventListener("change", (e) => { const r = e.target.closest(".prow"); if (r && e.target.name !== "section") paramChange(r, false); });
  $("ifacelist").addEventListener("click", (e) => {
    const r = e.target.closest(".prow");
    if (!r) return;
    if (e.target.closest("[data-addparam]")) paramChange(r, true);
    if (e.target.closest("[data-delparam]")) { r.querySelector("[name=name]").value = ""; paramChange(r, false); }
  });
  $("ifacelist").addEventListener("keydown", (e) => {
    const r = e.target.closest(".prow");
    if (e.key === "Enter" && r && !r.dataset.old) paramChange(r, true);
  });

  Fbd.wire($("fbd"), {
    select: (sel) => { S.select(sel ? py.toPy(sel) : null); render(true); },
    move: (id, x, y) => act(() => S.move_block(id, x, y)),
    connect: (a, ap, b, bp) => act(() => S.connect(a, ap, b, bp)),
    add: (kind, x, y) => act(() => S.add_block(kind, x, y)),
    drop: (id, pin, addr) => act(() => S.set_pin(id, pin, addr)),
  });
  $("fbd").addEventListener("dblclick", (e) => {
    const p = e.target.closest(".pinhit");
    const input = $("operands").querySelector(p ? `input[name="${CSS.escape(p.dataset.pin)}"]` : "input:not([disabled])");
    input?.focus();
  });

  $("ladder").addEventListener("scroll", placeForm);
  $("fbd").addEventListener("scroll", placeForm);
  const form = $("operands");
  form.addEventListener("keydown", (e) => { if (e.key === "Escape") { e.stopPropagation(); S.select(null); render(true); $("ladder").focus(); } });
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    if (state.block) {
      const ops = {};
      let inst = "";
      for (const i of form.querySelectorAll("input:not([disabled])")) {
        if (i.name === "@instance") inst = i.value; else ops[i.name] = i.value;
      }
      act(() => S.set_block(state.block.id, inst, py.toPy(ops)));
      return;
    }
    const vals = [...form.querySelectorAll("input[name=op]")].map((i) => i.value.trim());
    const probs = js(S.set_operands(py.toPy(vals)));
    changed(probs.join(" · "));
    if (probs.length) say(probs.join(" · "), true);
  });
  form.addEventListener("click", (e) => {
    const id = e.target.id;
    if (id === "b-branch") act(() => S.add_branch());
    else if (id === "b-leg") act(() => S.add_leg());
    else if (id === "b-del") act(() => S.delete());
    else if (id === "b-addin") act(() => S.set_inputs(state.block.id, state.block.inputs + 1));
    else if (id === "b-remin") act(() => S.set_inputs(state.block.id, state.block.inputs - 1));
    else if (id === "b-comment") {
      const n = state.sel[1];
      const text = prompt("Rung comment:", state.rungs[n].comment);
      if (text !== null) act(() => S.set_comment(n, text));
    }
  });

  document.addEventListener("keydown", (e) => {
    const typing = ["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement?.tagName);
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z" && !typing) { e.preventDefault(); S.undo_step(); changed(); }
    else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "y" && !typing) { e.preventDefault(); S.redo_step(); changed(); }
    else if ((e.key === "Delete" || e.key === "Backspace") && !typing && state.sel) { e.preventDefault(); act(() => S.delete()); }
    else if (e.key === "Insert" && !typing) act(() => S.new_rung());
    else if (e.key === "Escape") { S.select(null); render(true); }
  });

  $("b-undo").onclick = () => { S.undo_step(); changed(); };
  $("b-redo").onclick = () => { S.redo_step(); changed(); };
  $("b-download").onclick = () => { S.download(); render(true); };
  $("b-run").onclick = () => { S.set_mode("RUN"); render(true); };
  $("b-pgm").onclick = () => { S.set_mode("PGM"); render(true); };
  document.querySelectorAll("[data-new]").forEach((b) => b.onclick = () => {
    closeMenus();
    S.new(b.dataset.new); closeLab(); changed("New program. Pick an instruction above to start.");
  });
  const ta = $("stsrc");
  ta.setAttribute("wrap", "off");
  ta.addEventListener("input", () => { S.set_source(ta.value); paintCode(ta.value, []); store.set("plcyard.program", S.save_text()); });
  ta.addEventListener("keydown", (e) => {
    if (e.key === "Tab" && !e.shiftKey) { e.preventDefault(); ta.setRangeText("    ", ta.selectionStart, ta.selectionEnd, "end"); ta.dispatchEvent(new Event("input")); }
  });
  $("b-tags").onclick = () => { $("tagpane").hidden = !$("tagpane").hidden; tagsKey = ""; render(true); };
  $("b-tagclose").onclick = () => { $("tagpane").hidden = true; };
  const tagChange = (rowEl, adding) => {
    const v = (n) => rowEl.querySelector(`[name=${n}]`).value;
    if (!adding && !rowEl.dataset.old) return;
    const err = S.set_tag(rowEl.dataset.old, v("name"), v("type"), v("comment"));
    $("tagmsg").textContent = err;
    if (!err) { tagsKey = ""; document.activeElement.blur(); changed(); }
  };
  $("taglist").addEventListener("change", (e) => { const r = e.target.closest(".tagrow"); if (r) tagChange(r, false); });
  $("taglist").addEventListener("click", (e) => {
    const r = e.target.closest(".tagrow");
    if (!r) return;
    if (e.target.closest("[data-add]")) tagChange(r, true);
    if (e.target.closest("[data-del]")) { S.delete_tag(r.dataset.old); tagsKey = ""; changed(); }
  });
  $("taglist").addEventListener("keydown", (e) => {
    const r = e.target.closest(".tagrow");
    if (e.key === "Enter" && r && !r.dataset.old) tagChange(r, true);
  });
  document.querySelectorAll("[data-lablang]").forEach((b) => b.onclick = () => {
    if (!state.lab || !confirm("Start this exercise again with an empty program in " + b.textContent + "?")) return;
    showLab(js(S.open_exercise(state.lab.id, b.dataset.lablang)));
    changed();
  });
  $("b-exercises").onclick = openExercises;
  $("b-examples").onclick = $("b-examples2").onclick = () => { closeMenus(); openExamples(); };
  $("d-ex-list").addEventListener("click", (e) => {
    const c = e.target.closest("[data-lab]");
    if (c) { $("d-exercises").close(); openLab(c.dataset.lab); }
  });
  $("d-exa-list").addEventListener("click", (e) => {
    const c = e.target.closest("[data-example]");
    if (c) { $("d-examples").close(); S.open_example(c.dataset.example); closeLab(); changed(); }
  });
  document.querySelectorAll("dialog [data-close]").forEach((b) => b.onclick = () => b.closest("dialog").close());
  document.querySelectorAll("dialog").forEach((d) => d.addEventListener("click", (e) => { if (e.target === d) d.close(); }));
  $("b-w-first").onclick = () => { $("d-welcome").close(); openLab(EXERCISES[0].id); };
  $("b-w-example").onclick = () => { $("d-welcome").close(); openExamples(); };
  $("b-welcome").onclick = () => { closeMenus(); $("d-welcome").showModal(); };
  document.addEventListener("click", (e) => {
    document.querySelectorAll("details.dd[open]").forEach((d) => { if (!d.contains(e.target)) d.open = false; });
  });
  $("simpane").addEventListener("click", (e) => {
    if (e.target.id === "b-allio") { showAllIo = !showAllIo; render(true); }
  });
  $("b-notation").onchange = (e) => {
    S.set_notation(e.target.value);
    store.set("plcyard.notation", e.target.value);
    buildPalette();
    opsKey = "";
    if (state.lab && !$("labpane").hidden) showLab(js(S.lab_view()));
    render(true);
  };
  $("b-open").onclick = () => { closeMenus(); $("f-open").click(); };
  $("f-open").onchange = async (e) => {
    const f = e.target.files[0];
    if (!f) return;
    const err = S.open_text(await f.text());
    e.target.value = "";
    if (err) say(err, true); else { closeLab(); changed("Opened " + f.name); }
  };
  $("b-save").onclick = () => {
    closeMenus();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([S.save_text()], { type: "application/json" }));
    a.download = (state.lab ? `exercise-${state.lab.id}` : "program") + ".plcy";
    a.click();
    URL.revokeObjectURL(a.href);
  };
  $("b-check").onclick = check;
  $("b-labclose").onclick = closeLab;
  window.addEventListener("resize", () => render(true));
}

// -- exercises -----------------------------------------------------------------------------------
const done = () => { try { return new Set(JSON.parse(store.get("plcyard.done") || "[]")); } catch { return new Set(); } };

function closeMenus() {
  document.querySelectorAll("details.dd[open]").forEach((d) => { d.open = false; });
}

// A small picture of every machine as it starts (the I/O panel gets a drawing of its own).
function thumbnails(previews) {
  const out = {};
  for (const [kind, m] of Object.entries(previews)) {
    let svg = (m.controls ? Machines : Sims).draw(m);
    svg = svg.slice(0, svg.indexOf("</svg>") + 6).replace('class="draw"', 'class="draw thumb"').replace(/id="drum"/, `id="drum-t"`).replace("url(#drum)", "url(#drum-t)");
    out[kind] = svg;
  }
  let io = "";
  for (let k = 0; k < 4; k++) {
    io += `<rect class="box" x="20" y="${18 + k * 34}" width="44" height="24" rx="12"/><circle class="${k === 1 ? "sensor on" : "sensor"}" cx="${k === 1 ? 52 : 32}" cy="${30 + k * 34}" r="9"/>`;
    io += `<circle class="lt ${k === 0 ? "green on" : "amber"}" cx="160" cy="${30 + k * 34}" r="11"/>`;
    io += `<line class="steel" x1="78" y1="${30 + k * 34}" x2="140" y2="${30 + k * 34}" stroke-dasharray="4 4"/>`;
  }
  out.io = `<svg viewBox="0 0 200 160" class="draw thumb" role="img" aria-label="I/O panel">${io}</svg>`;
  return out;
}

function groups(items) {
  const out = new Map();
  for (const it of items) { if (!out.has(it.machine)) out.set(it.machine, []); out.get(it.machine).push(it); }
  return out;
}

function openExercises() {
  const ok = done();
  $("d-ex-progress").textContent = `${EXERCISES.filter((x) => ok.has(x.id)).length} of ${EXERCISES.length} done`;
  $("d-ex-list").innerHTML = [...groups(EXERCISES)].map(([machine, list]) => `<section class="mgroup"><div class="mhead">${THUMBS[list[0].sim] || ""}<h3>${esc(machine)}</h3></div><div class="cardgrid">` +
    list.map((x) => `<button class="pick${ok.has(x.id) ? " done" : ""}" data-lab="${esc(x.id)}">
      <span class="num">${esc(x.id)}</span><span class="ptitle">${esc(x.title)}</span>
      <span class="lvl" title="Level ${x.level} of 5">${"●".repeat(x.level)}${"○".repeat(5 - x.level)}</span>
      ${ok.has(x.id) ? `<span class="tick" title="Passed">✔</span>` : ""}</button>`).join("") + `</div></section>`).join("");
  $("d-exercises").showModal();
}

function openExamples() {
  const LANG = { LD: "Ladder", ST: "Structured text", FBD: "Function blocks" };
  $("d-exa-list").innerHTML = [...groups(EXAMPLES)].map(([machine, list]) => `<section class="mgroup"><div class="mhead">${THUMBS[list[0].sim] || ""}<h3>${esc(machine)}</h3></div><div class="cardgrid">` +
    list.map((x) => `<button class="pick ex" data-example="${esc(x.key)}"><span class="ptitle">${esc(x.title)}</span>
      <span class="lang">${esc(x.languages.map((l) => LANG[l]).join(" + "))}</span></button>`).join("") + `</div></section>`).join("");
  $("d-examples").showModal();
}

function openLab(id) {
  showLab(js(S.open_exercise(id)));
  changed();
}

function showLab(lab) {
  setTab("lab");
  document.querySelectorAll("[data-lablang]").forEach((b) => b.classList.toggle("on", b.dataset.lablang === S.language));
  $("labtitle").textContent = `${lab.id}. ${lab.title}`;
  $("labbody").innerHTML = window.marked ? marked.parse(lab.body) : `<pre>${esc(lab.body)}</pre>`;
  $("report").innerHTML = "";
  $("labpane").hidden = false;
}

function closeLab() {
  $("labpane").hidden = true;
  if (document.body.dataset.tab === "lab") setTab("program");
}

function check() {
  $("report").innerHTML = "<p class='muted'>Checking… the machine runs several minutes of simulated time, this can take a few seconds.</p>";
  setTimeout(() => {
    const r = js(S.check());
    if (r.error) { $("report").innerHTML = `<p class="bad">${esc(r.error)}</p>`; return; }
    if (r.passed) { const ok = done(); ok.add(state.lab.id); store.set("plcyard.done", JSON.stringify([...ok])); }
    $("report").innerHTML = `<p class="${r.passed ? "passed" : ""}"><strong>${r.passed ? "✔ All requirements met" : "Score"}: ${esc(r.score)}</strong></p><ul>` +
      r.checks.map((c) => `<li><span class="${c.passed ? "ok" : "bad"}">${c.passed ? "✔" : "✘"}</span> ${esc(c.text)}${!c.passed && c.detail ? `<span class="detail">${esc(c.detail)}</span>` : ""}</li>`).join("") + "</ul>";
  }, 20);
}

// A tab left open keeps running the version it loaded: ask the site, now and then, for the current one.
function watchVersion() {
  const check = async () => {
    try {
      const v = (await (await fetch("version.json", { cache: "no-store" })).json()).version;
      if (v && v !== VERSION) $("update").hidden = false;
    } catch { /* offline: try again later */ }
  };
  $("b-reload").onclick = () => location.reload();
  setInterval(check, 5 * 60 * 1000);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) check(); });
}

start();
