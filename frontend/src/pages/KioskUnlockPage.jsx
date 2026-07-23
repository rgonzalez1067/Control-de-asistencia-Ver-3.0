import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, formatApiErrorDetail } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent } from "@/components/ui/card";
import { toast } from "sonner";
import { ShieldCheck, ScanFace, LockKeyhole, ArrowRight, ArrowLeft } from "lucide-react";

const KIOSK_KEY = "megasoft.kiosk.unlocked";

export function isKioskUnlocked() {
  try { return sessionStorage.getItem(KIOSK_KEY) === "1"; }
  catch (_) { return false; }
}
export function setKioskUnlocked(v) {
  try {
    if (v) sessionStorage.setItem(KIOSK_KEY, "1");
    else sessionStorage.removeItem(KIOSK_KEY);
  } catch (_) { /* noop */ }
}

export default function KioskUnlockPage() {
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  async function onSubmit(e) {
    e.preventDefault();
    setBusy(true);
    try {
      await api.post("/kiosk/unlock", { email: email.trim(), password });
      setKioskUnlocked(true);
      toast.success("Kiosco desbloqueado");
      nav("/kiosk/scan", { replace: true });
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    } finally { setBusy(false); }
  }

  return (
    <div className="min-h-screen bg-primary text-primary-foreground grid place-items-center px-4 py-10 relative overflow-hidden">
      <div className="pointer-events-none absolute -top-40 -left-40 h-[520px] w-[520px] rounded-full border border-white/5" />
      <div className="pointer-events-none absolute -bottom-32 -right-32 h-[420px] w-[420px] rounded-full bg-accent/10 blur-3xl" />

      <Card className="relative w-full max-w-md border-white/10 bg-white/5 backdrop-blur-xl text-primary-foreground shadow-2xl">
        <CardContent className="pt-8 pb-6 space-y-6">
          <div className="flex flex-col items-center text-center">
            <div className="h-16 w-16 rounded-2xl bg-accent grid place-items-center shadow-lg shadow-accent/30 mb-4">
              <ScanFace className="h-8 w-8 text-foreground" />
            </div>
            <p className="text-xs uppercase tracking-[0.3em] text-white/50">MegaSoft · Modo</p>
            <h1 className="text-3xl font-bold mt-1">Kiosco compartido</h1>
            <p className="font-serif-display text-accent/80 text-xl mt-1">desbloquéalo con tu clave.</p>
            <p className="text-xs text-white/60 mt-3 max-w-xs">
              Sólo un administrador puede activar el modo kiosco en esta pantalla.
            </p>
          </div>

          <form onSubmit={onSubmit} className="space-y-4" data-testid="kiosk-unlock-form">
            <div className="space-y-1.5">
              <Label className="text-xs text-white/70">Correo del administrador</Label>
              <Input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="admin@empresa.com"
                required
                className="h-11 bg-white/10 border-white/10 text-white placeholder:text-white/40 focus-visible:ring-accent"
                data-testid="kiosk-email"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs text-white/70">Contraseña</Label>
              <Input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                required
                className="h-11 bg-white/10 border-white/10 text-white placeholder:text-white/40 focus-visible:ring-accent"
                data-testid="kiosk-password"
              />
            </div>
            <Button
              type="submit"
              disabled={busy}
              className="w-full h-12 rounded-full bg-accent hover:bg-accent/90 text-foreground font-semibold shadow-lg shadow-accent/20"
              data-testid="kiosk-unlock-btn"
            >
              {busy ? "Desbloqueando…" : (<><LockKeyhole className="h-4 w-4 mr-2" /> Desbloquear kiosco <ArrowRight className="h-4 w-4 ml-2" /></>)}
            </Button>
            <p className="text-[11px] text-white/50 text-center pt-2">
              Al desbloquear, la pantalla mostrará la cámara y aceptará marcas de cualquier empleado.
            </p>
          </form>

          <div className="pt-4 border-t border-white/10 text-center">
            <button
              type="button"
              onClick={() => nav("/", { replace: true })}
              className="text-xs text-white/60 hover:text-accent inline-flex items-center gap-1.5 transition-colors"
              data-testid="kiosk-back-to-admin"
            >
              <ArrowLeft className="h-3.5 w-3.5" />
              Regresar al panel administrativo
            </button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
