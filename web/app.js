// PLCYard web: the page around plcyard/webapp.py (the PLC, the I/O panel model, the ladder editor and the
// exercise checker), which runs in the browser with Pyodide. Python owns the program; this file draws it.
"use strict";

const TICK_MS = 50;
const GUTTER = 48, MARGIN = 12, RUNG_GAP = 18, COMMENT_LINE = 16, WIRE_Y = 26;
const $ = (id) => document.getElementById(id);
let py, S, state = null, lastJson = "", family = null, palette = [], opsKey = "";

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
    const zip = await (await fetch("plcyard.zip")).arrayBuffer();
    py.unpackArchive(zip, "zip", { extractDir: "/home/pyodide/app" });
    py.runPython("import sys; sys.path.insert(0, '/home/pyodide/app')");
    S = py.runPython("from plcyard.webapp import Session\nSession()");
    for (const ex of js(S.examples())) $("b-example").add(new Option(ex.title, ex.key));
    for (const lab of js(S.exercises())) $("b-lab").add(new Option(`${lab.id}. ${lab.title}`, lab.id));
    const n = store.get("plcyard.notation");
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
  const width = Math.max(500, $("ladder").clientWidth - GUTTER - 2 * MARGIN - 8);
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
  $("b-download").textContent = state.dirty ? "Download" : "Downloaded";
  if (state.fault) say("Fault: " + state.fault, true);
  else if (state.problems.length) say(state.problems.join(" · "), true);
  else if (state.message) say(state.message);
  const sel = $("b-sim");
  if (!sel.options.length) for (const [k, t] of state.sims) sel.add(new Option(t, k));
  if (document.activeElement !== sel) sel.value = state.machine.kind;
  $("io").hidden = !state.io;
  $("machine").hidden = !!state.io;
  $("simhint").textContent = state.io
    ? "Click a switch to flip it (pushbuttons spring back). Drag an address onto an instruction to use it."
    : "Hold a button to press it. Drag an address onto an instruction to use it.";
  if (state.io) renderIo(state.io);
  else Sims.render($("machine"), state.machine);
  renderLadder(state);
  renderOperands(state);
}

function renderIo(io) {
  const card = (c, input) => `<div class="card-io"><h3>${esc(c.name)}</h3>${c.points.map((p) => `
    <div class="pt">${input
      ? `<button class="sw${p.momentary ? " pb" : ""}${p.pressed !== p.nc ? " closed" : ""}" data-slot="${c.slot}" data-bit="${p.bit}"
           data-pb="${p.momentary ? 1 : 0}" aria-pressed="${p.pressed}" title="${p.nc ? "Normally closed" : "Normally open"}${p.momentary ? " pushbutton" : " switch"}"></button>`
      : `<span class="lamp${p.on ? " on" : ""}" role="img" aria-label="${p.on ? "on" : "off"}"></span>`}
      <span class="txt"><span class="addr" draggable="true" data-addr="${esc(p.addr)}" title="Drag onto an instruction · double-click to describe">${esc(p.addr)}</span>
      ${p.symbol ? `<span class="sym">${esc(p.symbol)}</span>` : ""}</span></div>`).join("")}</div>`;
  const html = `<div class="cards">${card(io.inputs[0], true)}${card(io.outputs[0], false)}${card(io.inputs[1], true)}${card(io.outputs[1], false)}</div>
    <div class="bcd"><span class="mono">${esc(io.thumb_name)} (BCD)</span><span class="digits">${io.thumbwheels.map((d, i) =>
      `<input type="number" min="0" max="9" value="${d}" data-digit="${i}" aria-label="Thumbwheel digit ${i + 1}">`).join("")}</span>
    <span class="mono">${esc(io.display_name)} (BCD)</span><span class="digits">${io.display.map((d) => `<span class="seg">${d > 9 ? "-" : d}</span>`).join("")}</span></div>`;
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
  s += `<rect class="hit" data-n="${n}" data-path="${it.path.join(",")}" x="${x}" y="${y}" width="${w}" height="${h}"/>`;
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
  const key = o ? JSON.stringify([st.sel, o.mnemonic, o.labels, o.values]) : "";
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
    Array.from({ length: n }, (_, i) => `<label>${esc(o.labels[i] || "Operand")}<input name="op" value="${esc(o.values[i] || "")}" autocomplete="off" spellcheck="false"></label>`).join("") +
    `<button class="primary" type="submit">Apply</button><button type="button" id="b-branch">Branch</button>
     <button type="button" id="b-leg">Add leg</button><button type="button" id="b-del">Delete</button>`;
}

// -- input ---------------------------------------------------------------------------------------
function buildPalette() {
  palette = js(S.palette());
  family = family || palette[0].family;
  $("families").innerHTML = palette.map((f) => `<button role="tab" class="${f.family === family ? "on" : ""}" data-family="${esc(f.family)}">${esc(f.family)}</button>`).join("");
  const fam = palette.find((f) => f.family === family) || palette[0];
  $("palette").innerHTML = `<button data-m="RUNG" title="New rung">Rung +</button><button data-m="BRANCH" title="Put the selected instruction in a branch">Branch</button>` +
    fam.items.map((i) => `<button data-m="${esc(i.m)}" title="${esc(i.title)}">${esc(i.name)}</button>`).join("");
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
  $("palette").addEventListener("click", (e) => {
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
  $("b-sim").onchange = (e) => { S.set_sim(e.target.value); Sims.reset(); store.set("plcyard.sim", e.target.value); render(true); };
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

  const form = $("operands");
  form.addEventListener("submit", (e) => {
    e.preventDefault();
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
  $("b-new").onclick = () => { S.new(); closeLab(); changed(); };
  $("b-example").onchange = (e) => {
    if (e.target.value) { S.open_example(e.target.value); closeLab(); changed(); }
    e.target.value = "";
  };
  $("b-lab").onchange = (e) => {
    if (e.target.value) openLab(e.target.value);
    e.target.value = "";
  };
  $("b-notation").onchange = (e) => {
    S.set_notation(e.target.value);
    store.set("plcyard.notation", e.target.value);
    buildPalette();
    opsKey = "";
    if (state.lab && !$("labpane").hidden) showLab(js(S.lab_view()));
    render(true);
  };
  $("b-open").onclick = () => $("f-open").click();
  $("f-open").onchange = async (e) => {
    const f = e.target.files[0];
    if (!f) return;
    const err = S.open_text(await f.text());
    e.target.value = "";
    if (err) say(err, true); else { closeLab(); changed("Opened " + f.name); }
  };
  $("b-save").onclick = () => {
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
function openLab(id) {
  showLab(js(S.open_exercise(id)));
  changed();
}

function showLab(lab) {
  $("labtitle").textContent = `${lab.id}. ${lab.title}`;
  $("labbody").innerHTML = window.marked ? marked.parse(lab.body) : `<pre>${esc(lab.body)}</pre>`;
  $("report").innerHTML = "";
  $("labpane").hidden = false;
}

function closeLab() {
  $("labpane").hidden = true;
}

function check() {
  $("report").innerHTML = "<p class='muted'>Checking…</p>";
  setTimeout(() => {
    const r = js(S.check());
    if (r.error) { $("report").innerHTML = `<p class="bad">${esc(r.error)}</p>`; return; }
    $("report").innerHTML = `<p><strong>${r.passed ? "All requirements met" : "Score"}: ${esc(r.score)}</strong></p><ul>` +
      r.checks.map((c) => `<li><span class="${c.passed ? "ok" : "bad"}">${c.passed ? "✔" : "✘"}</span> ${esc(c.text)}${!c.passed && c.detail ? `<span class="detail">${esc(c.detail)}</span>` : ""}</li>`).join("") + "</ul>";
  }, 20);
}

start();
