/* Mega Soft Asistencia — Service Worker.
   Estrategia:
   - HTML (navegaciones): network-first. Así, cada deploy nuevo se ve al
     recargar sin necesidad de que el usuario limpie caché.
   - Assets estáticos con hash (`/static/**`): cache-first (los nombres cambian
     con el build, no hay riesgo de servir versiones viejas).
   - Modelos de face-api en `/vendor/face-api/**`: cache-first (son inmutables
     y grandes, ~7MB — vale la pena cachearlos agresivamente).
   - Otros GET del mismo origen: stale-while-revalidate.
   - `/api/**` y orígenes cross-domain: nunca se cachean.
*/

const CACHE = "megasoft-asistencia-v3";
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

function isNavigationRequest(req) {
    return req.mode === "navigate"
        || (req.method === "GET" && req.headers.get("accept")?.includes("text/html"));
}

self.addEventListener("fetch", (event) => {
    const req = event.request;
    if (req.method !== "GET") return;
    const url = new URL(req.url);

    // Nunca cachear /api ni orígenes de terceros
    if (url.pathname.startsWith("/api/")) return;
    if (url.origin !== self.location.origin) return;

    // Modelos de face-api: cache-first agresivo (son inmutables y grandes).
    if (url.pathname.startsWith("/vendor/face-api/")) {
        event.respondWith(
            caches.open(CACHE).then((c) =>
                c.match(req).then((cached) =>
                    cached || fetch(req).then((resp) => {
                        if (resp && resp.status === 200) c.put(req, resp.clone());
                        return resp;
                    })
                )
            )
        );
        return;
    }

    // HTML / navegación → network-first. Si la red falla, sirve cache.
    if (isNavigationRequest(req)) {
        event.respondWith(
            fetch(req)
                .then((resp) => {
                    if (resp && resp.status === 200 && resp.type === "basic") {
                        const clone = resp.clone();
                        caches.open(CACHE).then((c) => c.put(req, clone)).catch(() => null);
                    }
                    return resp;
                })
                .catch(() => caches.match(req).then((c) => c || caches.match("/index.html")))
        );
        return;
    }

    // Otros assets del mismo origen → stale-while-revalidate.
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
