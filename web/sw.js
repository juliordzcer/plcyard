// PLCYard web works offline once it has loaded: this worker keeps the page, the Python package and
// Pyodide in the browser's cache. A new release (a new __VERSION__) installs a fresh cache.
"use strict";

const VERSION = "__VERSION__";
const CACHE = `plcyard-${VERSION}`;
const CDN = "plcyard-cdn";                       // Pyodide and the markdown library: pinned versions
const PYODIDE = "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/";
const SHELL = ["./", "index.html", "manifest.webmanifest", "icon.svg", "icons/icon-192.png", "icons/icon-512.png",
  "fonts/Inter.ttf", "fonts/JetBrainsMono.ttf",
  ...["style.css", "tokens.css", "app.js", "sims.js", "machines.js", "fbd.js", "plcyard.zip"].map((f) => `${f}?v=${VERSION}`)];
const LIBS = [...["pyodide.js", "pyodide.asm.js", "pyodide.asm.wasm", "python_stdlib.zip", "pyodide-lock.json"].map((f) => PYODIDE + f),
  "https://cdn.jsdelivr.net/npm/marked@12.0.2/marked.min.js"];

self.addEventListener("install", (e) => {
  e.waitUntil((async () => {
    await (await caches.open(CACHE)).addAll(SHELL);
    const cdn = await caches.open(CDN);
    for (const url of LIBS) if (!(await cdn.match(url))) await cdn.add(url);
    await self.skipWaiting();
  })());
});

self.addEventListener("activate", (e) => {
  e.waitUntil((async () => {
    for (const k of await caches.keys()) if (k !== CACHE && k !== CDN) await caches.delete(k);
    await self.clients.claim();
  })());
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin === location.origin && url.pathname.endsWith("/version.json")) return;   // always the network
  if (req.mode === "navigate") {                // the page: the newest when online, the cached one offline
    e.respondWith(fetch(req).then((res) => {
      const copy = res.clone();
      caches.open(CACHE).then((c) => c.put("index.html", copy));
      return res;
    }).catch(async () => (await caches.match("index.html")) || Response.error()));
    return;
  }
  e.respondWith((async () => {                  // everything else is versioned: the cache first
    const hit = await caches.match(req);
    if (hit) return hit;
    const res = await fetch(req);
    if (res.ok && (url.origin === location.origin || url.hostname === "cdn.jsdelivr.net")) {
      const c = await caches.open(url.origin === location.origin ? CACHE : CDN);
      c.put(req, res.clone());
    }
    return res;
  })());
});
