import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, formatApiErrorDetail } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent } from "@/components/ui/card";
import { ArrowLeft, MailCheck, KeyRound } from "lucide-react";
import { toast } from "sonner";

export default function ForgotPasswordPage() {
  const [identifier, setIdentifier] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const [smtpOk, setSmtpOk] = useState(true);
  const nav = useNavigate();

  async function onSubmit(e) {
    e.preventDefault();
    if (!identifier.trim()) return;
    setBusy(true);
    try {
      const { data } = await api.post("/auth/forgot-password", { identifier: identifier.trim() });
      setSmtpOk(!!data?.smtp_configured);
      setSent(true);
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || err.message);
    } finally { setBusy(false); }
  }

  return (
    <div className="min-h-screen w-full bg-primary text-primary-foreground grid place-items-center p-6">
      <Card className="w-full max-w-md border-border/40 bg-card text-card-foreground shadow-2xl">
        <CardContent className="p-8 space-y-6">
          <button onClick={() => nav("/login")} className="text-xs inline-flex items-center gap-1 text-muted-foreground hover:text-foreground" data-testid="forgot-back">
            <ArrowLeft className="h-3 w-3" /> Volver al login
          </button>
          {!sent ? (
            <>
              <div>
                <div className="h-11 w-11 rounded-2xl bg-primary/10 grid place-items-center mb-3">
                  <KeyRound className="h-5 w-5 text-primary" />
                </div>
                <h1 className="text-xl font-semibold">Recuperar contraseña</h1>
                <p className="text-sm text-muted-foreground mt-1">Indícanos tu correo o cédula y te enviaremos un enlace seguro para restablecerla (válido 30 minutos).</p>
              </div>
              <form onSubmit={onSubmit} className="space-y-4">
                <div className="space-y-1.5">
                  <Label htmlFor="ident">Correo o cédula</Label>
                  <Input
                    id="ident"
                    autoFocus
                    value={identifier}
                    onChange={(e) => setIdentifier(e.target.value)}
                    placeholder="nombre@empresa.com o V-12345678"
                    className="h-12"
                    data-testid="forgot-identifier"
                  />
                </div>
                <Button
                  type="submit" disabled={busy || !identifier.trim()}
                  className="w-full h-12 rounded-full bg-primary hover:bg-primary/90 text-primary-foreground font-semibold"
                  data-testid="forgot-submit"
                >
                  {busy ? "Enviando…" : "Enviar enlace de recuperación"}
                </Button>
              </form>
            </>
          ) : (
            <div className="text-center py-4">
              <div className="h-14 w-14 rounded-full bg-emerald-500/10 text-emerald-600 grid place-items-center mx-auto mb-4">
                <MailCheck className="h-7 w-7" />
              </div>
              <h1 className="text-xl font-semibold" data-testid="forgot-sent">Revisa tu correo</h1>
              <p className="text-sm text-muted-foreground mt-2">
                Si el usuario existe, te enviamos un enlace para restablecer la contraseña.
                Puede tardar unos segundos en llegar. Revisa la carpeta de spam.
              </p>
              {!smtpOk && (
                <p className="mt-3 text-xs text-amber-600 border border-amber-200 rounded-lg bg-amber-50 p-2">
                  <b>Nota admin:</b> el servidor SMTP aún no está configurado en <code>backend/.env</code>. El enlace no se envió por correo, pero fue generado.
                </p>
              )}
              <Button onClick={() => nav("/login")} variant="outline" className="mt-5 rounded-full" data-testid="forgot-back-login">
                Volver al inicio de sesión
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
