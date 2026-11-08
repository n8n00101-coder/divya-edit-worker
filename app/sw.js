// Divya PWA service worker: app shell offline, API always network. Paths are relative so it works at / and at /divya-edit-worker/app/.
const V = "divya-v6";
const ROOT = new URL("./", self.location).href; // scope root
const SHELL = ["./", "app.css", "app.js", "manifest.webmanifest", "icon-192.png", "icon-512.png", "apple-touch-icon.png", "favicon.png"].map(p => new URL(p, ROOT).href);
self.addEventListener("install", e => { e.waitUntil(caches.open(V).then(c => c.addAll(SHELL)).then(() => self.skipWaiting())); });
self.addEventListener("activate", e => { e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== V).map(k => caches.delete(k)))).then(() => self.clients.claim())); });
self.addEventListener("fetch", e => {
  const u = new URL(e.request.url);
  if (e.request.method !== "GET" || u.origin !== location.origin || !u.href.startsWith(ROOT)) return;
  const page = e.request.mode === "navigate" || u.href.split(/[?#]/)[0] === ROOT || u.pathname.endsWith("/index.html");
  // network-first so updates land fast; cache fallback offline (pages fall back to the app shell)
  e.respondWith(fetch(e.request).then(r => { if (r.ok) { const c = r.clone(); caches.open(V).then(x => x.put(page ? ROOT : e.request, c)); } return r; })
    .catch(() => (page ? caches.match(ROOT) : caches.match(e.request)).then(r => r || caches.match(ROOT))));
});
