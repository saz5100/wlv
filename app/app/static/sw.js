// WLV CS Revision — Service Worker
// Provides offline fallback and installable PWA support
const CACHE_NAME = 'wlvcs-v1';
const STATIC_ASSETS = [
  '/static/css/style.css',
  '/static/js/app.js',
  '/static/js/markdown-it.min.js',
  '/static/favicon.ico',
  '/static/favicon.png',
  '/static/manifest.json'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(clients.claim());
});

self.addEventListener('fetch', event => {
  // Network-first for HTML pages, cache-first for static assets
  const url = new URL(event.request.url);
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(event.request).then(cached => cached || fetch(event.request))
    );
  }
});
