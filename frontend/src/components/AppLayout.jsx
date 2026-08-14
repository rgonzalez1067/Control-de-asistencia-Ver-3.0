import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import useCompanyBranding from "@/hooks/useCompanyBranding";
import { api, formatApiErrorDetail } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import ThemeToggle from "@/components/ThemeToggle";
import {
  DropdownMenu, DropdownMenuTrigger, DropdownMenuContent,
  DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import {
  Sheet, SheetContent, SheetTrigger, SheetHeader, SheetTitle, SheetDescription,
} from "@/components/ui/sheet";
import {
  LayoutDashboard, Users, Building2, MapPin, CalendarClock,
  Fingerprint, FileBarChart2, Bell, LogOut, Settings2, ShieldCheck,
  IdCard, History as HistoryIcon, ChevronDown, UserCircle2,
  Menu, ScanFace, KeyRound, Eye, EyeOff, UserPlus, ClipboardList,
  LayoutGrid, CalendarCog,
} from "lucide-react";

const NAV_ADMIN = [
  { to: "/", icon: LayoutDashboard, label: "Dashboard" },
  { to: "/usuarios", icon: Users, label: "Empleados" },
  { to: "/equipo", icon: Users, label: "Mi equipo" },
  { to: "/sedes", icon: MapPin, label: "Sedes" },
  { to: "/departamentos", icon: Building2, label: "Departamentos" },
  { to: "/horarios", icon: CalendarClock, label: "Horarios" },
  { to: "/reportes", icon: FileBarChart2, label: "Reportes" },
  { to: "/reporte-matricial", icon: LayoutGrid, label: "Matriz de asistencia" },
  { to: "/asignar-horarios", icon: CalendarCog, label: "Asignación de horarios" },
  { to: "/novedades", icon: Bell, label: "Novedades" },
  { to: "/ajustes", icon: Settings2, label: "Ajustes" },
];

const NAV_EMPLOYEE = [
  { to: "/carnet", icon: IdCard, label: "Mi carnet" },
  { to: "/historial", icon: HistoryIcon, label: "Historial" },
  { to: "/reportes", icon: FileBarChart2, label: "Reportes" },
  { to: "/reporte-matricial", icon: LayoutGrid, label: "Matriz" },
  { to: "/novedades", icon: Bell, label: "Novedades" },
];

const NAV_SUPERVISOR = [
  ...NAV_EMPLOYEE,
  { to: "/equipo", icon: Users, label: "Mi equipo" },
];

function initials(name) {
  return (name || "?")
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join("");
}

export default function AppLayout() {
  const { user, logout } = useAuth();
  const branding = useCompanyBranding();
  const logo = branding?.logo_base64;
  const nav = useNavigate();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [changePwOpen, setChangePwOpen] = useState(false);

  const canCreateVisits = user?.role === "admin" || user?.can_create_visits;
  const canViewVisitLogs = user?.role === "admin" || user?.can_view_visit_logs;
  const canManageSchedules = user?.role === "admin" || user?.can_manage_schedules;
  const canAssignSchedules = user?.role === "admin" || user?.can_assign_schedules;

  const baseItems =
    user?.role === "admin" ? NAV_ADMIN :
    user?.role === "supervisor" ? NAV_SUPERVISOR : NAV_EMPLOYEE;

  const visitItems = [];
  if (canCreateVisits) visitItems.push({ to: "/visitas/agendar", icon: UserPlus, label: "Agendar visita" });
  if (canViewVisitLogs) visitItems.push({ to: "/visitas/historico", icon: ClipboardList, label: "Histórico de visitas" });

  // "Horarios" para no-admin sólo si tiene permiso especial
  const extraItems = [];
  if (canManageSchedules && user?.role !== "admin") {
    extraItems.push({ to: "/horarios", icon: CalendarClock, label: "Horarios" });
  }
  if (canAssignSchedules && user?.role !== "admin") {
    extraItems.push({ to: "/asignar-horarios", icon: CalendarCog, label: "Asignación de horarios" });
  }

  const items = [...baseItems, ...extraItems, ...visitItems];
  const isAdmin = user?.role === "admin";

  async function handleLogout() {
    await logout();
    nav("/login", { replace: true });
  }

  function openKiosk() {
    // Modo kiosco vive en /kiosk (login público con credenciales admin). Abrimos
    // en la misma pestaña porque en iOS PWA abrir nueva pestaña puede fallar.
    setDrawerOpen(false);
    nav("/kiosk");
  }

  return (
    <div className="min-h-screen bg-soft-grid flex">
      {/* Sidebar (desktop) */}
      <aside className="hidden lg:flex w-64 shrink-0 flex-col bg-primary text-primary-foreground">
        <div className="px-6 py-6 flex items-center gap-3 border-b border-white/10">
          {logo ? (
            <div className="bg-white/95 rounded-lg px-2 py-1.5 shadow-sm">
              <img
                src={logo}
                alt="Mega Soft"
                className="h-9 w-auto max-w-[170px] object-contain"
                data-testid="sidebar-brand-logo"
              />
            </div>
          ) : (
            <>
              <div className="h-10 w-10 rounded-xl bg-accent grid place-items-center">
                <ShieldCheck className="h-5 w-5 text-foreground" />
              </div>
              <div>
                <p className="text-[10px] uppercase tracking-[0.25em] text-white/60">Mega Soft</p>
                <p className="text-sm font-semibold">Asistencia</p>
              </div>
            </>
          )}
        </div>
        <nav className="flex-1 px-3 py-4 space-y-0.5" data-testid="sidebar-nav">
          {items.map((it) => (
            <NavItem key={it.to} item={it} />
          ))}
          {isAdmin && (
            <button
              type="button"
              onClick={openKiosk}
              data-testid="sidebar-kiosk-btn"
              className="w-full mt-2 flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm text-white/70 hover:bg-white/5 hover:text-white transition-colors"
            >
              <ScanFace className="h-4 w-4 opacity-80" />
              <span>Modo kiosco</span>
            </button>
          )}
        </nav>
        <div className="p-4 border-t border-white/10 text-[11px] text-white/50">
          v1.0 · Producción
        </div>
      </aside>

      {/* Main */}
      <div className="flex-1 flex flex-col min-w-0">
        <header className="sticky top-0 z-20 bg-card/80 backdrop-blur border-b border-border/70">
          <div className="h-16 px-4 sm:px-8 flex items-center justify-between gap-4">
            <div className="lg:hidden flex items-center gap-2">
              <Sheet open={drawerOpen} onOpenChange={setDrawerOpen}>
                <SheetTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    data-testid="mobile-menu-btn"
                    aria-label="Abrir menú"
                    className="rounded-full"
                  >
                    <Menu className="h-5 w-5" />
                  </Button>
                </SheetTrigger>
                <SheetContent side="left" className="w-72 p-0 bg-primary text-primary-foreground border-0" data-testid="mobile-nav-drawer">
                  <SheetHeader className="px-5 py-5 border-b border-white/10 text-left">
                    <SheetTitle className="text-primary-foreground flex items-center gap-3">
                      {logo ? (
                        <div className="bg-white/95 rounded-lg px-2 py-1.5 shadow-sm">
                          <img src={logo} alt="Mega Soft" className="h-8 w-auto max-w-[160px] object-contain" />
                        </div>
                      ) : (
                        <>
                          <div className="h-10 w-10 rounded-xl bg-accent grid place-items-center">
                            <ShieldCheck className="h-5 w-5 text-primary" />
                          </div>
                          <div>
                            <p className="text-[10px] uppercase tracking-[0.25em] text-white/60">Mega Soft</p>
                            <p className="text-sm font-semibold">Asistencia</p>
                          </div>
                        </>
                      )}
                    </SheetTitle>
                    <SheetDescription className="sr-only">
                      Menú de navegación de la aplicación
                    </SheetDescription>
                  </SheetHeader>
                  <nav className="flex-1 px-3 py-3 space-y-0.5 overflow-y-auto" data-testid="mobile-nav">
                    {items.map((it) => (
                      <NavItem key={it.to} item={it} onClick={() => setDrawerOpen(false)} />
                    ))}
                    {isAdmin && (
                      <button
                        type="button"
                        onClick={openKiosk}
                        data-testid="mobile-kiosk-btn"
                        className="w-full mt-3 flex items-center gap-3 px-3 py-3 rounded-xl bg-accent/15 text-accent hover:bg-accent/25 transition-colors"
                      >
                        <ScanFace className="h-5 w-5" />
                        <div className="text-left">
                          <p className="text-sm font-semibold">Activar modo kiosco</p>
                          <p className="text-[11px] opacity-80">Marca compartida con rostro o PIN</p>
                        </div>
                      </button>
                    )}
                  </nav>
                  <div className="px-5 py-4 border-t border-white/10 text-[11px] text-white/50">
                    {user?.email}
                  </div>
                </SheetContent>
              </Sheet>
              {logo ? (
                <img src={logo} alt="Mega Soft" className="h-8 w-auto max-w-[140px] object-contain" />
              ) : (
                <>
                  <div className="h-9 w-9 rounded-xl bg-primary grid place-items-center">
                    <ShieldCheck className="h-4 w-4 text-accent" />
                  </div>
                  <p className="text-sm font-semibold text-foreground">Mega Soft</p>
                </>
              )}
            </div>
            <div className="hidden lg:block">
              <p className="text-xs text-muted-foreground">Bienvenido</p>
              <p className="text-sm font-semibold text-foreground" data-testid="topbar-name">{user?.name}</p>
            </div>
            <div className="flex items-center gap-3">
              <ThemeToggle />
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    variant="ghost"
                    data-testid="user-menu-btn"
                    className="h-11 rounded-full pl-1 pr-3 gap-2 hover:bg-muted"
                  >
                    <div className="h-9 w-9 rounded-full bg-primary text-primary-foreground grid place-items-center text-xs font-semibold">
                      {initials(user?.name)}
                    </div>
                    <div className="hidden sm:block text-left">
                      <p className="text-sm font-medium leading-tight">{user?.name?.split(" ")[0]}</p>
                      <p className="text-[11px] capitalize text-muted-foreground leading-tight">{user?.role}</p>
                    </div>
                    <ChevronDown className="h-4 w-4 text-muted-foreground" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-56">
                  <DropdownMenuLabel>
                    <p className="text-xs text-muted-foreground">Sesión iniciada</p>
                    <p className="text-sm font-semibold">{user?.email}</p>
                  </DropdownMenuLabel>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onClick={() => nav("/onboarding")} data-testid="menu-onboarding">
                    <UserCircle2 className="h-4 w-4 mr-2" /> Registrar rostro
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => setChangePwOpen(true)} data-testid="menu-change-password">
                    <KeyRound className="h-4 w-4 mr-2" /> Cambiar contraseña
                  </DropdownMenuItem>
                  {isAdmin && (
                    <DropdownMenuItem onClick={openKiosk} data-testid="menu-kiosk">
                      <ScanFace className="h-4 w-4 mr-2" /> Activar modo kiosco
                    </DropdownMenuItem>
                  )}
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onClick={handleLogout} data-testid="menu-logout" className="text-destructive focus:text-destructive">
                    <LogOut className="h-4 w-4 mr-2" /> Cerrar sesión
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </div>
        </header>

        <main className="flex-1 min-w-0">
          <Outlet />
        </main>

        {/* Mobile bottom nav — 3 accesos rápidos + "Más" que abre el drawer */}
        <nav className="lg:hidden sticky bottom-0 z-20 bg-card/95 backdrop-blur border-t border-border/70 px-2 py-2 pb-[max(0.5rem,env(safe-area-inset-bottom))]">
          <ul className="grid grid-cols-4 gap-1">
            {items.slice(0, 3).map((it) => (
              <li key={it.to}>
                <NavLink
                  to={it.to}
                  end={it.to === "/"}
                  className={({ isActive }) =>
                    "flex flex-col items-center gap-0.5 py-1.5 rounded-xl text-[10px] transition-colors " +
                    (isActive ? "text-foreground bg-primary/5" : "text-muted-foreground hover:text-primary")
                  }
                >
                  <it.icon className="h-5 w-5" />
                  <span className="truncate max-w-full px-1">{it.label}</span>
                </NavLink>
              </li>
            ))}
            <li>
              <button
                type="button"
                onClick={() => setDrawerOpen(true)}
                data-testid="mobile-more-btn"
                className="w-full flex flex-col items-center gap-0.5 py-1.5 rounded-xl text-[10px] text-muted-foreground hover:text-primary transition-colors"
              >
                <Menu className="h-5 w-5" />
                <span>Más</span>
              </button>
            </li>
          </ul>
        </nav>
      </div>

      <ChangePasswordDialog
        open={changePwOpen}
        onOpenChange={setChangePwOpen}
        userEmail={user?.email}
      />
    </div>
  );
}

function ChangePasswordDialog({ open, onOpenChange, userEmail }) {
  const [oldPw, setOldPw] = useState("");
  const [newPw, setNewPw] = useState("");
  const [confirmPw, setConfirmPw] = useState("");
  const [showOld, setShowOld] = useState(false);
  const [showNew, setShowNew] = useState(false);
  const [saving, setSaving] = useState(false);

  function reset() {
    setOldPw(""); setNewPw(""); setConfirmPw("");
    setShowOld(false); setShowNew(false);
  }

  function handleClose(v) {
    if (!v) reset();
    onOpenChange(v);
  }

  async function submit(e) {
    e.preventDefault();
    if (newPw.length < 8) {
      toast.error("La nueva contraseña debe tener al menos 8 caracteres");
      return;
    }
    if (newPw !== confirmPw) {
      toast.error("La confirmación no coincide con la nueva contraseña");
      return;
    }
    if (newPw === oldPw) {
      toast.error("La nueva contraseña debe ser distinta a la actual");
      return;
    }
    setSaving(true);
    try {
      await api.post("/auth/change-password", { old_password: oldPw, new_password: newPw });
      toast.success("Contraseña actualizada correctamente");
      reset();
      onOpenChange(false);
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    } finally {
      setSaving(false);
    }
  }

  const strength = passwordStrength(newPw);

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-sm" data-testid="change-password-dialog">
        <DialogHeader className="items-center text-center">
          <div className="h-14 w-14 rounded-2xl bg-primary/10 grid place-items-center mb-2">
            <KeyRound className="h-7 w-7 text-primary dark:text-foreground" />
          </div>
          <DialogTitle>Cambiar contraseña</DialogTitle>
          <DialogDescription className="text-xs">
            {userEmail && <span className="font-mono">{userEmail}</span>}
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-3">
          <div className="space-y-1.5">
            <Label className="text-xs">Contraseña actual</Label>
            <div className="relative">
              <Input
                type={showOld ? "text" : "password"}
                value={oldPw}
                onChange={(e) => setOldPw(e.target.value)}
                placeholder="••••••••"
                required
                className="h-11 pr-10"
                autoFocus
                data-testid="change-pw-old"
              />
              <button
                type="button"
                onClick={() => setShowOld((v) => !v)}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                tabIndex={-1}
                aria-label="Mostrar contraseña"
              >
                {showOld ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Nueva contraseña</Label>
            <div className="relative">
              <Input
                type={showNew ? "text" : "password"}
                value={newPw}
                onChange={(e) => setNewPw(e.target.value)}
                placeholder="Mínimo 8 caracteres"
                required
                minLength={8}
                className="h-11 pr-10"
                data-testid="change-pw-new"
              />
              <button
                type="button"
                onClick={() => setShowNew((v) => !v)}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                tabIndex={-1}
                aria-label="Mostrar contraseña"
              >
                {showNew ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
            {newPw && (
              <div className="flex items-center gap-1.5 pt-0.5" data-testid="change-pw-strength">
                <div className="h-1 flex-1 rounded-full bg-muted overflow-hidden">
                  <div
                    className={"h-full transition-all " + strength.color}
                    style={{ width: `${strength.pct}%` }}
                  />
                </div>
                <span className={"text-[10px] font-medium " + strength.textColor}>{strength.label}</span>
              </div>
            )}
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Confirmar nueva contraseña</Label>
            <Input
              type={showNew ? "text" : "password"}
              value={confirmPw}
              onChange={(e) => setConfirmPw(e.target.value)}
              placeholder="Repite la nueva contraseña"
              required
              minLength={8}
              className="h-11"
              data-testid="change-pw-confirm"
            />
          </div>

          <ul className="text-[11px] text-muted-foreground space-y-0.5 pt-1">
            <li>• Mínimo 8 caracteres</li>
            <li>• Distinta a la contraseña actual</li>
            <li>• Se recomiendan mayúsculas, números y símbolos</li>
          </ul>

          <DialogFooter className="flex-row gap-2 sm:justify-stretch pt-2">
            <Button type="button" variant="outline" onClick={() => handleClose(false)} disabled={saving}
              className="rounded-full flex-1" data-testid="change-pw-cancel">
              Cancelar
            </Button>
            <Button type="submit" disabled={saving}
              className="rounded-full flex-1 bg-primary hover:bg-primary/90 font-semibold"
              data-testid="change-pw-submit">
              {saving ? "Guardando…" : "Actualizar"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function passwordStrength(pw) {
  const p = pw || "";
  let score = 0;
  if (p.length >= 8) score++;
  if (p.length >= 12) score++;
  if (/[A-Z]/.test(p) && /[a-z]/.test(p)) score++;
  if (/\d/.test(p)) score++;
  if (/[^A-Za-z0-9]/.test(p)) score++;
  const map = [
    { label: "Muy débil", pct: 15, color: "bg-red-500", textColor: "text-red-600" },
    { label: "Débil",     pct: 30, color: "bg-orange-500", textColor: "text-orange-600" },
    { label: "Aceptable", pct: 55, color: "bg-yellow-500", textColor: "text-yellow-600" },
    { label: "Buena",     pct: 80, color: "bg-lime-500", textColor: "text-lime-600" },
    { label: "Fuerte",    pct: 100, color: "bg-emerald-500", textColor: "text-emerald-600" },
  ];
  return map[Math.min(score, map.length - 1)];
}

function NavItem({ item, onClick }) {
  return (
    <NavLink
      to={item.to}
      end={item.to === "/"}
      onClick={onClick}
      data-testid={`nav-${item.to.replace("/", "") || "home"}`}
      className={({ isActive }) =>
        "group flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm transition-colors " +
        (isActive
          ? "bg-white/10 text-white"
          : "text-white/70 hover:bg-white/5 hover:text-white")
      }
    >
      {({ isActive }) => (
        <>
          <item.icon className={"h-4 w-4 " + (isActive ? "text-accent" : "opacity-80")} />
          <span>{item.label}</span>
        </>
      )}
    </NavLink>
  );
}

export function BottomNavSpacer() {
  return <div className="h-16 lg:hidden" />;
}

export function LayoutIcons() {
  return { Fingerprint };
}
