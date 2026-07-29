// SHIM service worker — network first for all navigation
const CACHE = 'shim-v8';

self.addEventListener('install', e => {
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  // Always go to network — no caching
  // This ensures the app always loads the latest version
  e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
});
