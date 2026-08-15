import { Navigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import DashboardHome from "@/pages/DashboardHome";

/** Ruta index: admin/supervisor van al dashboard (si su perfil lo permite);
 *  employees a su historial; usuarios kiosco entran directamente al
 *  arranque automático del Kiosco. Se respeta `effective_permissions`. */
export default function HomeRedirect() {
  const { user } = useAuth();
  if (!user) return null;
  if (user.role === "kiosk") return <Navigate to="/kiosk/auto" replace />;

  const perms = user.effective_permissions || {};
  const isAdmin = user.role === "admin";
  const hasPerm = (k) => isAdmin || perms[k] === true;

  if (user.role === "employee") {
    if (hasPerm("historial")) return <Navigate to="/historial" replace />;
    if (hasPerm("mi_carnet")) return <Navigate to="/carnet" replace />;
    return <DashboardHome />;   // fallback — muestra "No autorizado" con menú
  }

  // supervisor / admin
  if (hasPerm("dashboard")) return <DashboardHome />;
  if (hasPerm("matriz")) return <Navigate to="/reporte-matricial" replace />;
  if (hasPerm("equipo")) return <Navigate to="/equipo" replace />;
  if (hasPerm("historial")) return <Navigate to="/historial" replace />;
  return <DashboardHome />;
}
