/* MegaSoft Asistencia — Service Worker mínimo (Fase 0)
   Cacheo básico para permitir instalación PWA. La estrategia
   se refinará en Fase 5.                                       */

const CACHE = "megasoft-asistencia-v0";
const APP_SHELL = ["/", "/index.html", "/manifest.webmanifest"];

self.addEventListener("install", (event) => {
    event.waitUntil(
        caches.open(CACHE).then((c) => c.addAll(APP_SHELL)).catch(() => null)
    );
    self.skipWaiting();
});

self.addEventListener("activate", (event) => {
    event.waitUntil(
        caches
            .keys()
            .then((keys) =>
                Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
            )
    );
    self.clients.claim();
});

self.addEventListener("fetch", (event) => {
    const req = event.request;
    if (req.method !== "GET") return;
    const url = new URL(req.url);
    // Nunca cachear /api ni orígenes de terceros
    if (url.pathname.startsWith("/api/")) return;
    if (url.origin !== self.location.origin) return;

    event.respondWith(
        caches.match(req).then((cached) => {
            const fetchPromise = fetch(req)
                .then((resp) => {
                    if (resp && resp.status === 200 && resp.type === "basic") {
                        const clone = resp.clone();
                        caches.open(CACHE).then((c) => c.put(req, clone)).catch(() => null);
                    }
                    return resp;
                })
                .catch(() => cached);
            return cached || fetchPromise;
        })
    );
});
