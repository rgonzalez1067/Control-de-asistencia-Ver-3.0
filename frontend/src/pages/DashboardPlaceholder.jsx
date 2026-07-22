import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { LogOut, LayoutDashboard, Users, Building2, CalendarClock, MapPin, Fingerprint, FileBarChart2, Bell, CheckCircle2, Circle } from "lucide-react";

const PHASES = [
  { id: 0, name: "Setup + backend + BD", status: "done", desc: "React CRA + Tailwind + shadcn/ui · FastAPI portado (47 endpoints) · BD restaurada (128 docs)." },
  { id: 1, name: "Auth + Usuarios", status: "next", desc: "Login/logout · Middleware por rol · Onboarding con cámara · Gestión de empleados · Import CSV." },
  { id: 2, name: "Config maestra", status: "pending", desc: "Sedes (geocerca + Google Maps) · Departamentos · Horarios · Ajustes de la empresa." },
  { id: 3, name: "Kiosco + Carnet", status: "pending", desc: "Modo kiosco compartido · Reconocimiento facial · Re-enrolamiento con PIN · Carnet digital." },
  { id: 4, name: "Reportería + Equipo + Novedades", status: "pending", desc: "Historial · Novedades · Reportes con export · Dashboard admin con gráficas." },
  { id: 5, name: "PWA + Deploy", status: "pending", desc: "Manifest + service worker · Install prompt · Testing iOS/Android · URL productiva estable." },
];

const MODULES = [
  { icon: Users, name: "Empleados", desc: "17 usuarios en BD" },
  { icon: Building2, name: "Departamentos", desc: "15 configurados" },
  { icon: MapPin, name: "Sedes", desc: "2 activas con geocerca" },
  { icon: CalendarClock, name: "Horarios", desc: "5 turnos definidos" },
  { icon: Fingerprint, name: "Kiosco / Face-API", desc: "Fase 3" },
  { icon: FileBarChart2, name: "Reportes", desc: "80 registros de asistencia" },
  { icon: Bell, name: "Novedades", desc: "8 en historial" },
  { icon: LayoutDashboard, name: "Dashboard admin", desc: "Fase 4" },
];

export default function DashboardPlaceholder() {
  const { user, logout } = useAuth();

  return (
    <div className="min-h-screen bg-soft-grid">
      <header className="bg-white/80 backdrop-blur border-b border-border/70 sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="h-9 w-9 rounded-xl bg-primary grid place-items-center">
              <LayoutDashboard className="h-4 w-4 text-accent" />
            </div>
            <div>
              <p className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground">MegaSoft</p>
              <p className="text-sm font-semibold text-primary">Asistencia Web</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className="text-right hidden sm:block">
              <p className="text-sm font-medium text-primary" data-testid="user-name">{user?.name}</p>
              <p className="text-xs text-muted-foreground capitalize">{user?.role} · {user?.email}</p>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={logout}
              data-testid="logout-btn"
              className="rounded-full"
            >
              <LogOut className="h-4 w-4 mr-1.5" /> Salir
            </Button>
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-6 py-10">
        <div className="mb-10">
          <Badge variant="secondary" className="mb-3 rounded-full">
            Fase 0 completa · Listo para revisión
          </Badge>
          <h1 className="text-3xl sm:text-4xl font-bold text-primary">
            Setup y backend migrados con éxito
            <span className="block font-serif-display text-primary/60 text-2xl mt-1">
              esperando tu OK para arrancar Fase 1.
            </span>
          </h1>
          <p className="mt-4 text-muted-foreground max-w-2xl">
            La base de datos fue restaurada desde el backup del proyecto Mobile y el
            backend FastAPI está exponiendo los 47 endpoints del blueprint bajo el prefijo{" "}
            <code className="text-xs px-1.5 py-0.5 bg-muted rounded">/api</code>.
            Puedes ver el resumen de módulos y fases más abajo.
          </p>
        </div>

        <section className="mb-12">
          <h2 className="text-base font-semibold text-primary mb-4">Módulos disponibles en el backend</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3" data-testid="modules-grid">
            {MODULES.map((m) => (
              <div
                key={m.name}
                className="rounded-2xl border border-border/70 bg-white/70 backdrop-blur px-4 py-4 hover:border-primary/40 transition-colors"
              >
                <m.icon className="h-5 w-5 text-primary mb-2" />
                <p className="text-sm font-semibold text-primary">{m.name}</p>
                <p className="text-xs text-muted-foreground mt-0.5">{m.desc}</p>
              </div>
            ))}
          </div>
        </section>

        <section>
          <h2 className="text-base font-semibold text-primary mb-4">Hoja de ruta de la migración</h2>
          <div className="space-y-3" data-testid="phases-list">
            {PHASES.map((p) => (
              <Card
                key={p.id}
                className={
                  "border-border/70 " +
                  (p.status === "done" ? "bg-emerald-50/50 border-emerald-200/70" :
                    p.status === "next" ? "bg-amber-50/60 border-amber-200/70" : "bg-white/70")
                }
              >
                <CardHeader className="pb-2 flex flex-row items-start gap-3 space-y-0">
                  {p.status === "done"
                    ? <CheckCircle2 className="h-5 w-5 text-emerald-600 mt-0.5" />
                    : <Circle className={"h-5 w-5 mt-0.5 " + (p.status === "next" ? "text-amber-600" : "text-muted-foreground")} />}
                  <div className="flex-1">
                    <CardTitle className="text-base flex items-center gap-2">
                      <span className="text-xs font-mono text-muted-foreground">Fase {p.id}</span>
                      {p.name}
                      {p.status === "next" && (
                        <Badge className="ml-1 rounded-full bg-amber-500 hover:bg-amber-500 text-white">Siguiente</Badge>
                      )}
                    </CardTitle>
                    <CardDescription className="mt-1">{p.desc}</CardDescription>
                  </div>
                </CardHeader>
              </Card>
            ))}
          </div>
        </section>

        <footer className="mt-14 pt-6 border-t border-border/60 text-xs text-muted-foreground flex items-center justify-between">
          <span>Backend healthcheck: <code className="text-[10px]">GET /api/</code></span>
          <span>PWA instalable · service worker activo</span>
        </footer>
      </main>
    </div>
  );
}
