/* לזכרה של עלמה ז״ל
 * QUORUM · Worker — service worker. Caches the app shell so the worker page
 * installs as a PWA and reopens instantly. Model weights are NOT cached here —
 * WebLLM manages its own Cache API storage for those.
 */
"use strict";

const CACHE = "quorum-worker-v1";
const SHELL = [
  "./",
  "./index.html",
  "./worker.js",
  "./manifest.webmanifest",
  "./icon.svg",
  "./icon-192.png",
  "./icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE);
    // add files one by one so a single 404 does not sink the whole install
    await Promise.allSettled(SHELL.map((u) => cache.add(u)));
    await self.skipWaiting();
  })());
});

self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    const names = await caches.keys();
    await Promise.all(names.filter((n) => n !== CACHE).map((n) => caches.delete(n)));
    await self.clients.claim();
  })());
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;                    // API POSTs pass through
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;     // CDN + model weights pass through
  const scopePath = new URL(self.registration.scope).pathname;
  if (!url.pathname.startsWith(scopePath)) return;     // only our shell
  if (url.pathname.includes("/api/")) return;          // never cache API traffic

  // stale-while-revalidate: instant open, quiet refresh
  event.respondWith((async () => {
    const cache = await caches.open(CACHE);
    const cached = await cache.match(req);
    const refresh = fetch(req).then((res) => {
      if (res && res.ok) cache.put(req, res.clone());
      return res;
    }).catch(() => null);
    if (cached) { refresh.catch(() => {}); return cached; }
    const fresh = await refresh;
    if (fresh) return fresh;
    return new Response("offline and not cached", { status: 503, headers: { "Content-Type": "text/plain" } });
  })());
});
