import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import ThemeToggle from "@/components/ThemeToggle";
import {
  DropdownMenu, DropdownMenuTrigger, DropdownMenuContent,
  DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import {
  LayoutDashboard, Users, Building2, MapPin, CalendarClock,
  Fingerprint, FileBarChart2, Bell, LogOut, Settings2, ShieldCheck,
  IdCard, History as HistoryIcon, ChevronDown, UserCircle2,
} from "lucide-react";

const NAV_ADMIN = [
  { to: "/", icon: LayoutDashboard, label: "Dashboard" },
  { to: "/usuarios", icon: Users, label: "Empleados" },
  { to: "/equipo", icon: Users, label: "Mi equipo" },
  { to: "/sedes", icon: MapPin, label: "Sedes" },
  { to: "/departamentos", icon: Building2, label: "Departamentos" },
  { to: "/horarios", icon: CalendarClock, label: "Horarios" },
  { to: "/reportes", icon: FileBarChart2, label: "Reportes" },
  { to: "/novedades", icon: Bell, label: "Novedades" },
  { to: "/ajustes", icon: Settings2, label: "Ajustes" },
];

const NAV_EMPLOYEE = [
  { to: "/carnet", icon: IdCard, label: "Mi carnet" },
  { to: "/historial", icon: HistoryIcon, label: "Historial" },
  { to: "/novedades", icon: Bell, label: "Novedades" },
];

const NAV_SUPERVISOR = [
  ...NAV_EMPLOYEE,
  { to: "/equipo", icon: Users, label: "Mi equipo" },
  { to: "/reportes", icon: FileBarChart2, label: "Reportes" },
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
  const nav = useNavigate();
  const items =
    user?.role === "admin" ? NAV_ADMIN :
    user?.role === "supervisor" ? NAV_SUPERVISOR : NAV_EMPLOYEE;

  async function handleLogout() {
    await logout();
    nav("/login", { replace: true });
  }

  return (
    <div className="min-h-screen bg-soft-grid flex">
      {/* Sidebar (desktop) */}
      <aside className="hidden lg:flex w-64 shrink-0 flex-col bg-primary text-primary-foreground">
        <div className="px-6 py-6 flex items-center gap-3 border-b border-white/10">
          <div className="h-10 w-10 rounded-xl bg-accent grid place-items-center">
            <ShieldCheck className="h-5 w-5 text-foreground" />
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-[0.25em] text-white/60">MegaSoft</p>
            <p className="text-sm font-semibold">Asistencia</p>
          </div>
        </div>
        <nav className="flex-1 px-3 py-4 space-y-0.5" data-testid="sidebar-nav">
          {items.map((it) => (
            <NavLink
              key={it.to}
              to={it.to}
              end={it.to === "/"}
              data-testid={`nav-${it.to.replace("/", "") || "home"}`}
              className={({ isActive }) =>
                "group flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm transition-colors " +
                (isActive
                  ? "bg-white/10 text-white"
                  : "text-white/70 hover:bg-white/5 hover:text-white")
              }
            >
              {({ isActive }) => (
                <>
                  <it.icon className={"h-4 w-4 " + (isActive ? "text-accent" : "opacity-80")} />
                  <span>{it.label}</span>
                </>
              )}
            </NavLink>
          ))}
        </nav>
        <div className="p-4 border-t border-white/10 text-[11px] text-white/50">
          v0.1 · Fase 1 en curso
        </div>
      </aside>

      {/* Main */}
      <div className="flex-1 flex flex-col min-w-0">
        <header className="sticky top-0 z-20 bg-card/80 backdrop-blur border-b border-border/70">
          <div className="h-16 px-4 sm:px-8 flex items-center justify-between gap-4">
            <div className="lg:hidden flex items-center gap-2">
              <div className="h-9 w-9 rounded-xl bg-primary grid place-items-center">
                <ShieldCheck className="h-4 w-4 text-accent" />
              </div>
              <p className="text-sm font-semibold text-foreground">MegaSoft</p>
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

        {/* Mobile bottom nav */}
        <nav className="lg:hidden sticky bottom-0 z-20 bg-card/95 backdrop-blur border-t border-border/70 px-2 py-2">
          <ul className="grid grid-cols-4 gap-1">
            {items.slice(0, 4).map((it) => (
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
                  <span>{it.label}</span>
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
      </div>
    </div>
  );
}

export function BottomNavSpacer() {
  return <div className="h-16 lg:hidden" />;
}

export function LayoutIcons() {
  return { Fingerprint };
}
