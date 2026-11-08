// Divya PWA service worker: app shell offline, API always network.
const V = "divya-v3";
const SHELL = ["/", "/app.css", "/app.js", "/manifest.webmanifest", "/icon-192.png", "/icon-512.png", "/apple-touch-icon.png", "/favicon.png"];
self.addEventListener("install", e => { e.waitUntil(caches.open(V).then(c => c.addAll(SHELL)).then(() => self.skipWaiting())); });
self.addEventListener("activate", e => { e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== V).map(k => caches.delete(k)))).then(() => self.clients.claim())); });
self.addEventListener("fetch", e => {
  const u = new URL(e.request.url);
  if (e.request.method !== "GET" || u.origin !== location.origin) return;
  // network-first so updates land fast; cache fallback offline
  e.respondWith(fetch(e.request).then(r => { if (r.ok) { const c = r.clone(); caches.open(V).then(x => x.put(u.pathname === "/" || u.pathname === "/index.html" ? "/" : e.request, c)); } return r; })
    .catch(() => caches.match(u.pathname === "/index.html" ? "/" : e.request).then(r => r || caches.match("/"))));
});
