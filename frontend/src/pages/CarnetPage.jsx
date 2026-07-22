import { useEffect, useState } from "react";
import { api, formatApiErrorDetail } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { toast } from "sonner";
import { ShieldCheck, IdCard, Camera, Building2, MapPin, CalendarClock, UserCircle2, KeyRound } from "lucide-react";
import { useNavigate } from "react-router-dom";
import SetPinDialog from "@/components/SetPinDialog";

export default function CarnetPage() {
  const { user } = useAuth();
  const nav = useNavigate();
  const [dept, setDept] = useState(null);
  const [site, setSite] = useState(null);
  const [schedule, setSchedule] = useState(null);
  const [company, setCompany] = useState({});
  const [selfie, setSelfie] = useState(user?.selfie_base64 || null);
  const [pinDialogOpen, setPinDialogOpen] = useState(false);

  useEffect(() => {
    async function load() {
      try {
        const calls = [api.get("/settings"), api.get("/auth/me")];
        if (user?.department_id) calls.push(api.get("/departments"));
        if (user?.site_id) calls.push(api.get("/sites"));
        if (user?.schedule_id) calls.push(api.get("/schedules"));
        const results = await Promise.all(calls);
        setCompany(results[0].data);
        setSelfie(results[1].data.selfie_base64 || null);
        let idx = 2;
        if (user?.department_id) {
          setDept(results[idx++].data.find((d) => d.department_id === user.department_id));
        }
        if (user?.site_id) {
          setSite(results[idx++].data.find((s) => s.site_id === user.site_id));
        }
        if (user?.schedule_id) {
          setSchedule(results[idx++].data.find((s) => s.schedule_id === user.schedule_id));
        }
      } catch (e) {
        toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message);
      }
    }
    load();
  }, [user]);

  const roleLabel = { admin: "Administrador", supervisor: "Supervisor", employee: "Empleado" }[user?.role] || user?.role;

  return (
    <div className="p-4 sm:p-8 max-w-5xl mx-auto" data-testid="carnet-page">
      <div className="mb-6">
        <Badge variant="secondary" className="rounded-full mb-3">Identificación</Badge>
        <h1 className="text-3xl sm:text-4xl font-bold text-foreground flex items-center gap-3">
          <IdCard className="h-8 w-8 text-primary/70" /> Mi carnet
        </h1>
        <p className="text-muted-foreground mt-1 text-sm">
          Muéstrale este carnet a tu supervisor o al vigilante cuando lo necesites.
        </p>
      </div>

      <div className="grid lg:grid-cols-[420px_1fr] gap-8 items-start">
        {/* Card */}
        <div className="relative mx-auto lg:mx-0 w-full max-w-[420px] aspect-[7/10] rounded-[28px] overflow-hidden shadow-2xl shadow-primary/25" data-testid="carnet-card">
          {/* background */}
          <div className="absolute inset-0 bg-gradient-to-br from-primary via-primary to-[#173e6b]" />
          <div className="absolute -top-32 -right-32 h-64 w-64 rounded-full bg-accent/25 blur-3xl" />
          <div className="absolute -bottom-24 -left-24 h-56 w-56 rounded-full bg-white/5 blur-2xl" />
          <div className="absolute inset-0 opacity-10"
               style={{ backgroundImage: "radial-gradient(#fff 1px, transparent 1px)", backgroundSize: "18px 18px" }} />

          <div className="relative h-full flex flex-col p-6 text-primary-foreground">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                {company.logo_base64 ? (
                  <img src={company.logo_base64} alt="logo" className="h-9 w-9 rounded-lg object-contain bg-white/10 p-1" />
                ) : (
                  <div className="h-9 w-9 rounded-lg bg-accent grid place-items-center">
                    <ShieldCheck className="h-4 w-4 text-foreground" />
                  </div>
                )}
                <div>
                  <p className="text-[9px] uppercase tracking-[0.25em] text-white/60 leading-none">Carnet corporativo</p>
                  <p className="text-xs font-semibold leading-tight mt-0.5">{company.name || "MegaSoft"}</p>
                </div>
              </div>
              <span className="text-[9px] uppercase tracking-[0.25em] px-2 py-1 rounded-full bg-accent text-foreground font-bold">
                {roleLabel}
              </span>
            </div>

            <div className="flex-1 flex flex-col items-center justify-center text-center">
              <div className="relative mb-5">
                <div className="h-40 w-40 rounded-full bg-white/10 border-4 border-accent/60 overflow-hidden grid place-items-center">
                  {selfie ? (
                    <img src={selfie} alt="selfie" className="h-full w-full object-cover" data-testid="carnet-selfie" />
                  ) : (
                    <UserCircle2 className="h-24 w-24 text-white/40" />
                  )}
                </div>
                {!selfie && (
                  <button
                    onClick={() => nav("/onboarding")}
                    className="absolute -bottom-2 left-1/2 -translate-x-1/2 rounded-full bg-accent text-foreground text-[10px] font-semibold px-3 py-1 shadow-lg hover:scale-105 transition-transform"
                    data-testid="carnet-cta-onboarding"
                  >
                    <Camera className="h-3 w-3 inline mr-1" /> Añadir foto
                  </button>
                )}
              </div>
              <h2 className="font-serif-display text-3xl leading-tight">{user?.name}</h2>
              <p className="text-sm text-white/70 mt-1">{user?.position || "—"}</p>
            </div>

            <div className="space-y-1 text-[11px] text-white/70">
              <div className="flex items-center gap-2"><UserCircle2 className="h-3 w-3 text-accent" /> C.I. {user?.cedula || "—"}</div>
              <div className="flex items-center gap-2"><Building2 className="h-3 w-3 text-accent" /> {dept?.name || "Sin departamento"}</div>
              <div className="flex items-center gap-2"><MapPin className="h-3 w-3 text-accent" /> {site?.name || "Sin sede"}</div>
              <div className="flex items-center gap-2"><CalendarClock className="h-3 w-3 text-accent" /> {schedule?.name || "Sin horario"}</div>
            </div>

            <p className="mt-4 text-[9px] tracking-widest text-white/40 text-center">
              ID · {user?.user_id?.slice(-8).toUpperCase()}
            </p>
          </div>
        </div>

        {/* Right column */}
        <div className="space-y-4">
          <Card className="border-border/70 bg-card/80 backdrop-blur">
            <CardContent className="pt-5">
              <h3 className="text-sm font-semibold text-foreground mb-3">Datos personales</h3>
              <dl className="grid grid-cols-2 gap-y-3 text-sm">
                <dt className="text-muted-foreground">Nombre</dt><dd>{user?.name}</dd>
                <dt className="text-muted-foreground">Correo</dt><dd className="text-xs">{user?.email}</dd>
                <dt className="text-muted-foreground">Cédula</dt><dd>{user?.cedula || "—"}</dd>
                <dt className="text-muted-foreground">Cargo</dt><dd>{user?.position || "—"}</dd>
                <dt className="text-muted-foreground">Departamento</dt><dd>{dept?.name || "—"}</dd>
                <dt className="text-muted-foreground">Sede</dt><dd>{site?.name || "—"}</dd>
                <dt className="text-muted-foreground">Horario</dt><dd>{schedule?.name || "—"}</dd>
                <dt className="text-muted-foreground">Rol</dt><dd className="capitalize">{roleLabel}</dd>
              </dl>
            </CardContent>
          </Card>

          <Card className="border-border/70 bg-card/80 backdrop-blur">
            <CardContent className="pt-5 space-y-3">
              <h3 className="text-sm font-semibold text-foreground">Rostro biométrico</h3>
              {selfie ? (
                <p className="text-xs text-muted-foreground">
                  Ya tienes tu rostro registrado. Puedes actualizarlo en cualquier momento.
                </p>
              ) : (
                <p className="text-xs text-muted-foreground">
                  Registra tu rostro para poder usar el kiosco compartido con reconocimiento facial.
                </p>
              )}
              <Button onClick={() => nav("/onboarding")} className="w-full rounded-full bg-primary hover:bg-primary/90 text-primary-foreground" data-testid="carnet-onboarding-btn">
                <Camera className="h-4 w-4 mr-1.5" /> {selfie ? "Actualizar foto" : "Registrar rostro"}
              </Button>
            </CardContent>
          </Card>

          <Card className="border-border/70 bg-card/80 backdrop-blur">
            <CardContent className="pt-5 space-y-3">
              <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
                <KeyRound className="h-4 w-4 text-accent" /> Mi PIN del kiosco
              </h3>
              <p className="text-xs text-muted-foreground">
                Úsalo para marcar sin rostro o para reintentar tu foto en el kiosco si no te reconoce.
                Un PIN de 4 a 8 dígitos que solo tú conoces.
              </p>
              <Button
                onClick={() => setPinDialogOpen(true)}
                variant="outline"
                className="w-full rounded-full"
                data-testid="carnet-pin-btn"
              >
                <KeyRound className="h-4 w-4 mr-1.5" /> Crear o cambiar mi PIN
              </Button>
            </CardContent>
          </Card>
        </div>
      </div>

      <SetPinDialog
        open={pinDialogOpen}
        onOpenChange={setPinDialogOpen}
        userId={user?.user_id}
        userName={user?.name}
      />
    </div>
  );
}
