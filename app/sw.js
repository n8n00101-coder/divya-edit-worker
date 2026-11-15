// Julie PWA service worker: app shell offline, API always network. Paths are relative so it works at / and at /divya-edit-worker/app/.
const V = "julie-v50";
const ROOT = new URL("./", self.location).href; // scope root
const SHELL = ["./", "app.css", "app.js", "voices-kokoro.js", "manifest.webmanifest", "mascot.webp", "icon-192.png", "icon-512.png", "apple-touch-icon.png", "favicon.png"].map(p => new URL(p, ROOT).href);
self.addEventListener("install", e => { e.waitUntil(caches.open(V).then(c => c.addAll(SHELL)).then(() => self.skipWaiting())); });
self.addEventListener("activate", e => { e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== V).map(k => caches.delete(k)))).then(() => self.clients.claim())); });
self.addEventListener("fetch", e => {
  const u = new URL(e.request.url);
  if (e.request.method !== "GET" || u.origin !== location.origin || !u.href.startsWith(ROOT)) return;
  const page = e.request.mode === "navigate" || u.href.split(/[?#]/)[0] === ROOT || u.pathname.endsWith("/index.html");
  // v50 (V1): MEDIA (mp3/mp4/wav) is cache-first from THIS version's cache
  // and NEVER falls back to the app shell — the old catch-all served the
  // HTML shell for a failed audio fetch, so the sample "played" a web page
  // and died silently on real phones. A failed media fetch is an honest
  // 504, and media is not force-reloaded (Range/HTTP cache keep working).
  if (/\.(mp3|mp4|wav|m4a|webm)$/i.test(u.pathname)) {
    e.respondWith(caches.match(e.request).then(hit => hit || fetch(e.request).then(r => { if (r.ok) { const c = r.clone(); caches.open(V).then(x => x.put(e.request, c)); } return r; }).catch(() => new Response("", { status: 504 }))));
    return;
  }
  // network-first so updates land fast; cache:"reload" bypasses the HTTP cache so a
  // stale browser-cached copy can never be served as "fresh"; cache fallback offline
  // (pages fall back to the app shell)
  e.respondWith(fetch(new Request(e.request, { cache: "reload" })).then(r => { if (r.ok) { const c = r.clone(); caches.open(V).then(x => x.put(page ? ROOT : e.request, c)); } return r; })
    .catch(() => (page ? caches.match(ROOT) : caches.match(e.request)).then(r => r || caches.match(ROOT))));
});
