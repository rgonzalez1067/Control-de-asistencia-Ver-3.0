import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
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
  Menu, ScanFace,
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
  const [drawerOpen, setDrawerOpen] = useState(false);
  const items =
    user?.role === "admin" ? NAV_ADMIN :
    user?.role === "supervisor" ? NAV_SUPERVISOR : NAV_EMPLOYEE;
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
                      <div className="h-10 w-10 rounded-xl bg-accent grid place-items-center">
                        <ShieldCheck className="h-5 w-5 text-primary" />
                      </div>
                      <div>
                        <p className="text-[10px] uppercase tracking-[0.25em] text-white/60">MegaSoft</p>
                        <p className="text-sm font-semibold">Asistencia</p>
                      </div>
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
    </div>
  );
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
