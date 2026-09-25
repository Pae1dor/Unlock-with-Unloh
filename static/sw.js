// Service worker: makes the site installable as an app and shows an offline page
// instead of the browser's error screen. Served from /sw.js so its scope is the whole site.
//
// Everything is network-first: pages are per-user and live (prayer times, login state),
// and static files change during development, so the cache is only a fallback.

const CACHE = "unloh-v1";
const OFFLINE_URL = "/static/offline.html";
const PRECACHE = [OFFLINE_URL, "/static/css/style.css", "/static/img/icon-192.png"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(PRECACHE)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  if (req.mode === "navigate") {
    event.respondWith(fetch(req).catch(() => caches.match(OFFLINE_URL)));
    return;
  }

  if (url.pathname.startsWith("/static/")) {
    event.respondWith(
      fetch(req)
        .then((res) => {
          if (res.ok) {
            const copy = res.clone();
            caches.open(CACHE).then((cache) => cache.put(req, copy));
          }
          return res;
        })
        .catch(async () => (await caches.match(req)) || Response.error())
    );
  }
});
