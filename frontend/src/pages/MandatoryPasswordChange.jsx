import { useState } from "react";
import { api, formatApiErrorDetail } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ShieldAlert, Check, X, KeyRound, Eye, EyeOff } from "lucide-react";
import { toast } from "sonner";

// Reglas de política — coinciden con backend `validate_password_policy`.
const RULES = [
  { key: "len",  label: "Al menos 8 caracteres",       test: (p) => p.length >= 8 },
  { key: "up",   label: "Al menos una letra MAYÚSCULA", test: (p) => /[A-Z]/.test(p) },
  { key: "lo",   label: "Al menos una letra minúscula", test: (p) => /[a-z]/.test(p) },
  { key: "num",  label: "Al menos un número",           test: (p) => /\d/.test(p) },
  { key: "spec", label: "Al menos un carácter especial (!@#$%*...)", test: (p) => /[^A-Za-z0-9]/.test(p) },
];

export default function MandatoryPasswordChange() {
  const { refresh, logout } = useAuth();
  const [oldPw, setOldPw] = useState("");
  const [newPw, setNewPw] = useState("");
  const [confirm, setConfirm] = useState("");
  const [showOld, setShowOld] = useState(false);
  const [showNew, setShowNew] = useState(false);
  const [saving, setSaving] = useState(false);

  const passing = RULES.every((r) => r.test(newPw));
  const matchesConfirm = newPw && newPw === confirm;
  const canSubmit = oldPw && passing && matchesConfirm && !saving;

  async function submit(e) {
    e.preventDefault();
    if (!canSubmit) return;
    setSaving(true);
    try {
      await api.post("/auth/change-password", {
        old_password: oldPw,
        new_password: newPw,
      });
      toast.success("Contraseña actualizada correctamente");
      await refresh();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-[100] bg-primary text-primary-foreground flex items-center justify-center p-4">
      <div className="w-full max-w-xl bg-card text-foreground rounded-2xl shadow-2xl border border-border/60 overflow-hidden" data-testid="mandatory-password-change">
        <div className="p-6 border-b border-border/50 bg-amber-50 flex items-start gap-3">
          <div className="h-11 w-11 rounded-xl bg-amber-500/20 grid place-items-center shrink-0">
            <ShieldAlert className="h-6 w-6 text-amber-700" />
          </div>
          <div>
            <p className="text-xs uppercase tracking-[0.2em] text-amber-700 font-semibold">Acción obligatoria</p>
            <h1 className="text-xl font-bold text-amber-900 mt-1">Debes cambiar tu contraseña</h1>
            <p className="text-sm text-amber-900/80 mt-1">
              Por seguridad, la clave temporal debe reemplazarse antes de continuar. Elige una nueva contraseña que cumpla la política corporativa.
            </p>
          </div>
        </div>

        <form onSubmit={submit} className="p-6 space-y-4">
          {/* Actual */}
          <div className="space-y-1.5">
            <Label htmlFor="old-pw">Contraseña actual (temporal)</Label>
            <div className="relative">
              <Input
                id="old-pw"
                type={showOld ? "text" : "password"}
                value={oldPw}
                onChange={(e) => setOldPw(e.target.value)}
                autoFocus
                required
                data-testid="mpc-old"
              />
              <button type="button" onClick={() => setShowOld((s) => !s)}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground p-1">
                {showOld ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
          </div>

          {/* Nueva */}
          <div className="space-y-1.5">
            <Label htmlFor="new-pw">Nueva contraseña</Label>
            <div className="relative">
              <Input
                id="new-pw"
                type={showNew ? "text" : "password"}
                value={newPw}
                onChange={(e) => setNewPw(e.target.value)}
                required
                data-testid="mpc-new"
              />
              <button type="button" onClick={() => setShowNew((s) => !s)}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground p-1">
                {showNew ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
          </div>

          {/* Reglas */}
          <ul className="text-sm space-y-1 bg-muted/40 rounded-lg p-3 border border-border/50" data-testid="mpc-rules">
            {RULES.map((r) => {
              const ok = r.test(newPw);
              return (
                <li key={r.key} className={`flex items-center gap-2 ${ok ? "text-emerald-700" : "text-muted-foreground"}`}>
                  {ok ? <Check className="h-4 w-4" /> : <X className="h-4 w-4" />}
                  <span>{r.label}</span>
                </li>
              );
            })}
          </ul>

          {/* Confirmar */}
          <div className="space-y-1.5">
            <Label htmlFor="confirm-pw">Confirmar nueva contraseña</Label>
            <Input
              id="confirm-pw"
              type={showNew ? "text" : "password"}
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              required
              data-testid="mpc-confirm"
              className={confirm && !matchesConfirm ? "border-red-500" : ""}
            />
            {confirm && !matchesConfirm && (
              <p className="text-xs text-red-600">Las contraseñas no coinciden</p>
            )}
          </div>

          <div className="flex items-center gap-3 pt-2">
            <Button type="submit" disabled={!canSubmit} className="rounded-full flex-1 bg-primary hover:bg-primary/90" data-testid="mpc-submit">
              <KeyRound className="h-4 w-4 mr-2" /> {saving ? "Guardando…" : "Cambiar contraseña"}
            </Button>
            <Button type="button" variant="ghost" onClick={logout} className="text-muted-foreground">
              Cerrar sesión
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
