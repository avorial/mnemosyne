// Minimal service worker: exists so the app is installable (and therefore
// can register as a share target). Network passthrough; no offline cache —
// a capture surface that silently queues writes would lie about saving.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));
self.addEventListener("fetch", () => {
  // Intentionally empty: default network handling.
});
