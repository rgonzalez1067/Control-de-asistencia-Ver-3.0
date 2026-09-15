import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, formatApiErrorDetail } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent } from "@/components/ui/card";
import { KeyRound, Eye, EyeOff, CheckCircle2 } from "lucide-react";
import { toast } from "sonner";

export default function ResetPasswordPage() {
  const [params] = useSearchParams();
  const token = params.get("token") || "";
  const [pwd, setPwd] = useState("");
  const [confirm, setConfirm] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const nav = useNavigate();

  async function onSubmit(e) {
    e.preventDefault();
    if (!token) { toast.error("Enlace inválido"); return; }
    if (pwd.length < 8) { toast.error("La contraseña debe tener al menos 8 caracteres"); return; }
    if (pwd !== confirm) { toast.error("Las contraseñas no coinciden"); return; }
    setBusy(true);
    try {
      await api.post("/auth/reset-password-with-token", { token, new_password: pwd });
      setDone(true);
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || err.message);
    } finally { setBusy(false); }
  }

  return (
    <div className="min-h-screen w-full bg-primary text-primary-foreground grid place-items-center p-6">
      <Card className="w-full max-w-md border-border/40 bg-card text-card-foreground shadow-2xl">
        <CardContent className="p-8 space-y-6">
          {done ? (
            <div className="text-center py-4">
              <div className="h-14 w-14 rounded-full bg-emerald-500/10 text-emerald-600 grid place-items-center mx-auto mb-4">
                <CheckCircle2 className="h-7 w-7" />
              </div>
              <h1 className="text-xl font-semibold" data-testid="reset-done">Contraseña actualizada</h1>
              <p className="text-sm text-muted-foreground mt-2">Ya puedes iniciar sesión con tu nueva contraseña.</p>
              <Button onClick={() => nav("/login")} className="mt-5 rounded-full bg-primary hover:bg-primary/90 text-primary-foreground" data-testid="reset-goto-login">
                Ir al inicio de sesión
              </Button>
            </div>
          ) : (
            <>
              <div>
                <div className="h-11 w-11 rounded-2xl bg-primary/10 grid place-items-center mb-3">
                  <KeyRound className="h-5 w-5 text-primary" />
                </div>
                <h1 className="text-xl font-semibold">Elige una nueva contraseña</h1>
                <p className="text-sm text-muted-foreground mt-1">
                  Mínimo 8 caracteres. Elige una robusta — te recomendamos mezclar mayúsculas, minúsculas, números y símbolos.
                </p>
              </div>
              <form onSubmit={onSubmit} className="space-y-4">
                <div className="space-y-1.5">
                  <Label htmlFor="pwd">Nueva contraseña</Label>
                  <div className="relative">
                    <Input id="pwd" type={show ? "text" : "password"}
                           value={pwd} onChange={(e) => setPwd(e.target.value)}
                           className="h-12 pr-11" required data-testid="reset-password" />
                    <button type="button" onClick={() => setShow((s) => !s)}
                            className="absolute right-1.5 top-1/2 -translate-y-1/2 h-9 w-9 grid place-items-center rounded-lg text-muted-foreground hover:text-primary hover:bg-muted"
                            data-testid="reset-toggle-show">
                      {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                    </button>
                  </div>
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="confirm">Confirma la contraseña</Label>
                  <Input id="confirm" type={show ? "text" : "password"}
                         value={confirm} onChange={(e) => setConfirm(e.target.value)}
                         className="h-12" required data-testid="reset-confirm" />
                </div>
                <Button type="submit" disabled={busy || !pwd || !confirm}
                        className="w-full h-12 rounded-full bg-primary hover:bg-primary/90 text-primary-foreground font-semibold"
                        data-testid="reset-submit">
                  {busy ? "Guardando…" : "Cambiar contraseña"}
                </Button>
              </form>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
