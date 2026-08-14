import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import useCompanyBranding from "@/hooks/useCompanyBranding";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Fingerprint, Eye, EyeOff, ShieldCheck, ArrowRight } from "lucide-react";
import { toast } from "sonner";

const HIGHLIGHTS = [
  { k: "Reconocimiento facial", v: "face-api en el navegador, sin instalar apps" },
  { k: "Geocerca por sede", v: "valida ubicación en tiempo real al marcar" },
  { k: "Kiosco compartido", v: "una sola pantalla para toda la oficina" },
  { k: "Reportes exportables", v: "CSV listos para RRHH y nómina" },
];

export default function LoginPage() {
  const { login } = useAuth();
  const branding = useCompanyBranding();
  const logo = branding?.logo_base64;
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [tick, setTick] = useState(new Date());
  const nav = useNavigate();
  const location = useLocation();
  const from = location.state?.from?.pathname || "/";

  useEffect(() => {
    const t = setInterval(() => setTick(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  async function onSubmit(e) {
    e.preventDefault();
    if (!email || !password) return;
    setBusy(true);
    const res = await login(email.trim(), password);
    setBusy(false);
    if (res.ok) {
      toast.success(`Bienvenido, ${res.user.name.split(" ")[0]}`, { duration: 1800 });
      // Los usuarios operativos del Kiosco entran directo al modo Kiosco
      // (sin pasar por el panel administrativo ni por el selector de sede).
      if (res.user.role === "kiosk") {
        nav("/kiosk/auto", { replace: true });
      } else {
        nav(from, { replace: true });
      }
    } else {
      toast.error(res.error);
    }
  }

  const clock = tick.toLocaleTimeString("es-VE", { hour: "2-digit", minute: "2-digit", second: "2-digit", timeZone: "America/Caracas" });
  const day = tick.toLocaleDateString("es-VE", { weekday: "long", day: "numeric", month: "long", timeZone: "America/Caracas" });

  return (
    <div className="min-h-screen w-full bg-primary text-primary-foreground overflow-hidden">
      <div className="grid lg:grid-cols-[1.15fr_1fr] min-h-screen">
        {/* ============ LEFT: editorial panel ============ */}
        <aside
          className="relative hidden lg:flex flex-col justify-between p-14 xl:p-20"
          data-testid="login-brand-panel"
        >
          {/* decorative rings */}
          <div className="pointer-events-none absolute -top-40 -left-40 h-[520px] w-[520px] rounded-full border border-white/5" />
          <div className="pointer-events-none absolute -top-24 -left-24 h-[420px] w-[420px] rounded-full border border-white/10" />
          <div className="pointer-events-none absolute -bottom-32 -right-32 h-[420px] w-[420px] rounded-full bg-accent/10 blur-3xl" />
          <div className="pointer-events-none absolute inset-0 opacity-[0.04]"
               style={{ backgroundImage: "radial-gradient(#fff 1px, transparent 1px)", backgroundSize: "24px 24px" }} />

          {/* header */}
          <div className="relative flex items-center gap-3">
            {logo ? (
              <img
                src={logo}
                alt="Mega Soft"
                className="h-28 w-auto max-w-[360px] object-contain drop-shadow-[0_6px_18px_rgba(0,0,0,0.35)]"
                data-testid="login-brand-logo"
              />
            ) : (
              <>
                <div className="h-11 w-11 rounded-2xl bg-accent grid place-items-center shadow-lg shadow-accent/30">
                  <ShieldCheck className="h-5 w-5 text-foreground" />
                </div>
                <div>
                  <p className="text-[10px] uppercase tracking-[0.3em] text-white/50">Mega Soft</p>
                  <p className="text-base font-semibold">Asistencia · Web/PWA</p>
                </div>
              </>
            )}
            <div className="ml-auto rounded-full border border-white/10 bg-white/5 px-3 py-1 text-[11px] text-white/70">
              {day} · {clock}
            </div>
          </div>

          {/* headline */}
          <div className="relative max-w-xl mt-10">
            <p className="text-xs uppercase tracking-[0.3em] text-accent mb-6">
              — Suite corporativa de asistencia
            </p>
            <h1 className="text-5xl xl:text-6xl leading-[1.02] font-extrabold">
              Marca tu día
              <span className="block font-serif-display font-normal text-accent/90 mt-2">
                en un segundo, sin fricción.
              </span>
            </h1>
            <p className="mt-8 text-white/70 text-base max-w-md leading-relaxed">
              Una única URL productiva que reemplaza al app móvil: instalable como PWA,
              con reconocimiento facial en el kiosco, geocerca por sede y reportes en vivo.
            </p>

            <ul className="mt-10 grid grid-cols-2 gap-x-6 gap-y-4 max-w-lg">
              {HIGHLIGHTS.map((h) => (
                <li key={h.k} className="flex items-start gap-3">
                  <span className="mt-1 h-1.5 w-1.5 rounded-full bg-accent shrink-0" />
                  <div>
                    <p className="text-sm font-medium">{h.k}</p>
                    <p className="text-xs text-white/50">{h.v}</p>
                  </div>
                </li>
              ))}
            </ul>
          </div>

          {/* footer stats */}
          <div className="relative flex items-center gap-8 text-sm">
            <div>
              <p className="text-3xl font-bold leading-none">17</p>
              <p className="text-xs text-white/50 mt-1">empleados activos</p>
            </div>
            <div className="h-10 w-px bg-white/10" />
            <div>
              <p className="text-3xl font-bold leading-none">15</p>
              <p className="text-xs text-white/50 mt-1">departamentos</p>
            </div>
            <div className="h-10 w-px bg-white/10" />
            <div>
              <p className="text-3xl font-bold leading-none">2</p>
              <p className="text-xs text-white/50 mt-1">sedes activas</p>
            </div>
          </div>
        </aside>

        {/* ============ RIGHT: form on light surface ============ */}
        <section className="relative bg-background text-foreground flex items-center justify-center px-6 py-12 sm:px-12">
          {/* mobile brand mini header */}
          <div className="absolute top-6 left-6 lg:hidden flex items-center gap-2">
            {logo ? (
              <img src={logo} alt="Mega Soft" className="h-9 w-auto max-w-[150px] object-contain" data-testid="login-brand-logo-mobile" />
            ) : (
              <>
                <div className="h-9 w-9 rounded-xl bg-primary grid place-items-center">
                  <ShieldCheck className="h-4 w-4 text-accent" />
                </div>
                <p className="text-sm font-semibold text-foreground">Mega Soft Asistencia</p>
              </>
            )}
          </div>

          <div className="w-full max-w-md">
            <div className="mb-8">
              <p className="text-xs uppercase tracking-[0.25em] text-muted-foreground mb-3">
                Acceso corporativo
              </p>
              <h2 className="text-3xl font-bold text-foreground">Inicia sesión</h2>
              <p className="text-sm text-muted-foreground mt-1.5">
                Usa el correo y contraseña de tu cuenta de empleado.
              </p>
            </div>

            <form onSubmit={onSubmit} className="space-y-5" data-testid="login-form">
              <div className="space-y-1.5">
                <Label htmlFor="email" className="text-xs font-medium text-primary/80">
                  Correo electrónico
                </Label>
                <Input
                  id="email"
                  data-testid="login-email-input"
                  type="email"
                  autoComplete="email"
                  placeholder="tu@empresa.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="h-12 text-base border-border/70 focus-visible:ring-primary/40"
                  required
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="password" className="text-xs font-medium text-primary/80">
                  Contraseña
                </Label>
                <div className="relative">
                  <Input
                    id="password"
                    data-testid="login-password-input"
                    type={show ? "text" : "password"}
                    autoComplete="current-password"
                    placeholder="••••••••"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="h-12 text-base pr-11 border-border/70 focus-visible:ring-primary/40"
                    required
                  />
                  <button
                    type="button"
                    data-testid="login-toggle-password"
                    onClick={() => setShow((s) => !s)}
                    className="absolute right-1.5 top-1/2 -translate-y-1/2 h-9 w-9 grid place-items-center rounded-lg text-muted-foreground hover:text-primary hover:bg-muted transition-colors"
                    aria-label="Mostrar contraseña"
                  >
                    {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
              </div>

              <Button
                type="submit"
                data-testid="login-submit-btn"
                disabled={busy}
                className="group w-full h-12 text-base font-semibold rounded-full bg-primary hover:bg-primary/90 text-primary-foreground shadow-[0_18px_40px_-15px_hsl(var(--primary)/0.6)] hover:shadow-[0_22px_45px_-15px_hsl(var(--primary)/0.65)] hover:-translate-y-0.5 transition-[transform,box-shadow] duration-200"
              >
                {busy ? (
                  <span className="inline-flex items-center gap-2">
                    <span className="h-2 w-2 rounded-full bg-accent animate-pulse" />
                    Verificando credenciales…
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-2">
                    <Fingerprint className="h-4 w-4 text-accent" />
                    Entrar al panel
                    <ArrowRight className="h-4 w-4 opacity-0 -translate-x-1 group-hover:opacity-100 group-hover:translate-x-0 transition-all" />
                  </span>
                )}
              </Button>

              <div className="pt-2 flex items-center gap-3 text-[11px] text-muted-foreground">
                <div className="flex-1 h-px bg-border" />
                <span>zona segura · JWT · TLS</span>
                <div className="flex-1 h-px bg-border" />
              </div>

              <p className="text-xs text-center text-muted-foreground">
                ¿Problemas para acceder? Contacta a tu administrador de RRHH.
              </p>
            </form>
          </div>

          <p className="absolute bottom-4 right-6 text-[11px] text-muted-foreground/70">
            © Mega Soft Computación, C.A. · v0.1
          </p>
        </section>
      </div>
    </div>
  );
}
