import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import MandatoryPasswordChange from "@/pages/MandatoryPasswordChange";

export default function ProtectedRoute({ children, roles, check }) {
  const { user } = useAuth();
  const location = useLocation();

  if (user === undefined) {
    return (
      <div className="min-h-screen grid place-items-center text-muted-foreground text-sm">
        Cargando sesión…
      </div>
    );
  }
  if (user === null) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }
  // Bloqueo global: si el usuario debe cambiar la contraseña, no puede ir a ninguna otra ruta.
  if (user.must_change_password) {
    return <MandatoryPasswordChange />;
  }
  if (roles && !roles.includes(user.role)) {
    return <Navigate to="/" replace />;
  }
  if (typeof check === "function" && !check(user)) {
    return <Navigate to="/" replace />;
  }
  return children;
}
