import { useEffect, useState } from "react";
import { api } from "@/lib/api";

// Caché en memoria por sesión — el logo no cambia con frecuencia
let cache = null;
let inflight = null;

async function fetchBranding() {
  if (cache) return cache;
  if (!inflight) {
    inflight = api.get("/settings")
      .then((r) => { cache = r.data || {}; return cache; })
      .catch(() => ({}))
      .finally(() => { inflight = null; });
  }
  return inflight;
}

/** Devuelve `{ logo_base64, company_name }` de los ajustes públicos. */
export default function useCompanyBranding() {
  const [branding, setBranding] = useState(cache || {});
  useEffect(() => {
    let alive = true;
    fetchBranding().then((data) => { if (alive) setBranding(data); });
    return () => { alive = false; };
  }, []);
  return branding;
}
