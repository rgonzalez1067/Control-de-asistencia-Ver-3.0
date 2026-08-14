import { useEffect, useRef, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { api, formatApiErrorDetail } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Loader2, ShieldCheck, AlertTriangle } from "lucide-react";
import { toast } from "sonner";

const KIOSK_KEY = "megasoft.kiosk.unlocked";
const KIOSK_SITE_KEY = "megasoft.kiosk.site_id";
const KIOSK_SITE_NAME_KEY = "megasoft.kiosk.site_name";
const KIOSK_SESSION_KEY = "megasoft.kiosk.session_id";

/**
 * Página de arranque automático del Kiosco para usuarios con rol `kiosk`.
 *
 * Al iniciar sesión con Kiosco TBP / Kiosco LCH, este componente:
 *  1. Toma la sede fija asignada al usuario (`user.site_id`).
 *  2. Llama a `POST /api/kiosk/session/open` — el backend, al reconocer el
 *     token de un usuario kiosk cuya `site_id` coincide, cierra automáticamente
 *     cualquier sesión huérfana (ej. la tablet perdió energía).
 *  3. Guarda las claves en sessionStorage (igual que KioskUnlockPage).
 *  4. Redirige a `/kiosk/scan`.
 */
export default function KioskAutoStart() {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  const [err, setErr] = useState(null);
  const ran = useRef(false);

  useEffect(() => {
    if (!user || user.role !== "kiosk" || ran.current) return;
    ran.current = true;
    (async () => {
      if (!user.site_id) {
        setErr("Este usuario Kiosco no tiene una sede asignada. Contacta al administrador.");
        return;
      }
      try {
        const { data } = await api.post("/kiosk/session/open", { site_id: user.site_id });
        try {
          sessionStorage.setItem(KIOSK_SITE_KEY, data.site_id);
          sessionStorage.setItem(KIOSK_SITE_NAME_KEY, data.site_name || "");
          sessionStorage.setItem(KIOSK_SESSION_KEY, data.session_id);
          sessionStorage.setItem(KIOSK_KEY, "1");
        } catch (_) { /* noop */ }
        toast.success(`Kiosco activo en “${data.site_name || "sede"}”`);
        nav("/kiosk/scan", { replace: true });
      } catch (e) {
        setErr(formatApiErrorDetail(e.response?.data?.detail) || e.message);
      }
    })();
  }, [user, nav]);

  if (user === undefined) {
    return (
      <div className="min-h-screen grid place-items-center text-muted-foreground text-sm">
        Cargando sesión…
      </div>
    );
  }
  if (user === null) return <Navigate to="/login" replace />;
  if (user.role !== "kiosk") return <Navigate to="/" replace />;

  return (
    <div className="min-h-screen bg-primary text-primary-foreground grid place-items-center px-4">
      <div className="max-w-md w-full text-center space-y-6" data-testid="kiosk-auto-start">
        <div className="mx-auto h-16 w-16 rounded-2xl bg-accent grid place-items-center shadow-lg shadow-accent/30">
          {err
            ? <AlertTriangle className="h-8 w-8 text-foreground" />
            : <ShieldCheck className="h-8 w-8 text-foreground" />}
        </div>
        <div>
          <p className="text-xs uppercase tracking-[0.3em] text-white/50">Mega Soft · Kiosco</p>
          <h1 className="text-3xl font-bold mt-1">
            {err ? "No se pudo iniciar" : "Activando kiosco…"}
          </h1>
          <p className="font-serif-display text-accent/80 text-xl mt-1">
            {err ? "revisa lo siguiente." : `${user.name}`}
          </p>
        </div>

        {!err ? (
          <div className="inline-flex items-center gap-2 text-white/70">
            <Loader2 className="h-4 w-4 animate-spin" />
            Abriendo la sesión de la sede asignada
          </div>
        ) : (
          <div className="space-y-4">
            <div className="rounded-lg border border-red-400/30 bg-red-500/10 p-3 text-sm text-red-100">
              {err}
            </div>
            <button
              type="button"
              onClick={() => { logout(); nav("/login", { replace: true }); }}
              className="text-xs text-white/70 underline hover:text-accent"
              data-testid="kiosk-auto-logout"
            >
              Cerrar sesión y volver al login
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
