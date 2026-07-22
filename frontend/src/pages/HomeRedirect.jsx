import { Navigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import DashboardHome from "@/pages/DashboardHome";

/** Ruta index: admin/supervisor van al dashboard; employees a su historial. */
export default function HomeRedirect() {
  const { user } = useAuth();
  if (!user) return null;
  if (user.role === "employee") return <Navigate to="/historial" replace />;
  return <DashboardHome />;
}
