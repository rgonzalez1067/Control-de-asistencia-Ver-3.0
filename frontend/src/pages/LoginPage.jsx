import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Fingerprint, Eye, EyeOff, ShieldCheck } from "lucide-react";
import { toast } from "sonner";

export default function LoginPage() {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const nav = useNavigate();
  const location = useLocation();

  const from = location.state?.from?.pathname || "/";

  async function onSubmit(e) {
    e.preventDefault();
    if (!email || !password) return;
    setBusy(true);
    const res = await login(email.trim(), password);
    setBusy(false);
    if (res.ok) {
      toast.success(`Hola, ${res.user.name.split(" ")[0]}`);
      nav(from, { replace: true });
    } else {
      toast.error(res.error);
    }
  }

  return (
    <div className="min-h-screen bg-soft-grid flex items-center justify-center px-4 py-10">
      <div className="w-full max-w-5xl grid lg:grid-cols-[1.1fr_1fr] gap-10 items-center">
        {/* Left: brand */}
        <div className="hidden lg:block pr-8" data-testid="login-brand-panel">
          <div className="flex items-center gap-3 mb-8">
            <div className="h-12 w-12 rounded-2xl bg-primary grid place-items-center shadow-lg shadow-primary/20">
              <ShieldCheck className="h-6 w-6 text-accent" />
            </div>
            <div>
              <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">MegaSoft</p>
              <p className="text-lg font-semibold text-primary">Asistencia Web</p>
            </div>
          </div>
          <h1 className="text-4xl sm:text-5xl lg:text-6xl font-extrabold leading-[1.05] text-primary">
            Control de asistencia
            <span className="block font-serif-display text-accent-foreground/80 mt-2">
              rápido, verificable y en la nube.
            </span>
          </h1>
          <p className="mt-6 text-base text-muted-foreground max-w-md">
            Reconocimiento facial, geocerca por sede, kiosco compartido y reportes
            exportables — todo desde una única URL productiva instalable como PWA.
          </p>
          <div className="mt-10 grid grid-cols-3 gap-3 max-w-md">
            <BrandStat n="17" label="empleados" />
            <BrandStat n="15" label="departamentos" />
            <BrandStat n="2" label="sedes" />
          </div>
        </div>

        {/* Right: form */}
        <Card className="border-border/70 shadow-xl shadow-primary/5 backdrop-blur">
          <CardHeader className="pb-2">
            <div className="lg:hidden flex items-center gap-3 mb-3">
              <div className="h-10 w-10 rounded-xl bg-primary grid place-items-center">
                <ShieldCheck className="h-5 w-5 text-accent" />
              </div>
              <p className="text-lg font-semibold text-primary">MegaSoft Asistencia</p>
            </div>
            <CardTitle className="text-2xl">Iniciar sesión</CardTitle>
            <CardDescription>
              Ingresa con las credenciales de tu cuenta corporativa.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={onSubmit} className="space-y-5" data-testid="login-form">
              <div className="space-y-2">
                <Label htmlFor="email">Correo electrónico</Label>
                <Input
                  id="email"
                  data-testid="login-email-input"
                  type="email"
                  autoComplete="email"
                  placeholder="tu@empresa.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="password">Contraseña</Label>
                <div className="relative">
                  <Input
                    id="password"
                    data-testid="login-password-input"
                    type={show ? "text" : "password"}
                    autoComplete="current-password"
                    placeholder="••••••••"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                  />
                  <button
                    type="button"
                    data-testid="login-toggle-password"
                    onClick={() => setShow((s) => !s)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 p-2 text-muted-foreground hover:text-foreground transition-colors"
                    aria-label="Mostrar contraseña"
                  >
                    {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
              </div>
              <Button
                type="submit"
                data-testid="login-submit-btn"
                className="w-full h-11 text-base rounded-full bg-primary hover:bg-primary/90 text-primary-foreground shadow-lg shadow-primary/20 transition-all hover:shadow-primary/30"
                disabled={busy}
              >
                {busy ? "Verificando…" : (
                  <>
                    <Fingerprint className="h-4 w-4 mr-2" />
                    Entrar
                  </>
                )}
              </Button>
              <p className="text-xs text-muted-foreground text-center pt-2">
                ¿Problemas para acceder? Contacta a tu administrador.
              </p>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function BrandStat({ n, label }) {
  return (
    <div className="rounded-2xl bg-white/70 border border-border/60 px-4 py-3 backdrop-blur">
      <p className="text-2xl font-bold text-primary leading-none">{n}</p>
      <p className="text-xs text-muted-foreground mt-1">{label}</p>
    </div>
  );
}
