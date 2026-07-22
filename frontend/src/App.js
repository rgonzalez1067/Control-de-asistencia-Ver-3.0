import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { AuthProvider } from "@/context/AuthContext";
import ProtectedRoute from "@/components/ProtectedRoute";
import AppLayout from "@/components/AppLayout";
import LoginPage from "@/pages/LoginPage";
import DashboardHome from "@/pages/DashboardHome";
import UsersPage from "@/pages/UsersPage";
import OnboardingPage from "@/pages/OnboardingPage";
import ComingSoon from "@/pages/ComingSoon";

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />

          {/* Onboarding sin layout (pantalla completa dedicada) */}
          <Route
            path="/onboarding"
            element={
              <ProtectedRoute>
                <OnboardingPage />
              </ProtectedRoute>
            }
          />

          {/* App shell */}
          <Route
            element={
              <ProtectedRoute>
                <AppLayout />
              </ProtectedRoute>
            }
          >
            <Route index element={<DashboardHome />} />
            <Route
              path="usuarios"
              element={
                <ProtectedRoute roles={["admin"]}>
                  <UsersPage />
                </ProtectedRoute>
              }
            />
            <Route path="sedes" element={<ComingSoon title="Sedes" phase="Fase 2" description="Aquí podrás crear y editar las sedes con geocerca, coordenadas y resolución automática desde Google Maps." />} />
            <Route path="departamentos" element={<ComingSoon title="Departamentos" phase="Fase 2" description="Gestión de departamentos y estructura organizativa." />} />
            <Route path="horarios" element={<ComingSoon title="Horarios" phase="Fase 2" description="Turnos con bloques configurables, tolerancia y asignación por sede." />} />
            <Route path="reportes" element={<ComingSoon title="Reportes" phase="Fase 4" description="Historial de asistencias con filtros por fecha, sede y usuario. Exportación a CSV lista para RRHH." />} />
            <Route path="novedades" element={<ComingSoon title="Novedades" phase="Fase 4" description="Vacaciones, permisos y ausencias con flujo de aprobación bulk." />} />
            <Route path="ajustes" element={<ComingSoon title="Ajustes de la empresa" phase="Fase 2" description="Método de identificación (rostro/PIN), habilitar kiosco, logo corporativo y zona horaria." />} />
            <Route path="equipo" element={<ComingSoon title="Mi equipo" phase="Fase 4" description="Vista de supervisor con asistencia del equipo asignado." />} />
            <Route path="carnet" element={<ComingSoon title="Mi carnet" phase="Fase 3" description="Tarjeta digital con tu foto, cargo y sede — lista para mostrar en el ingreso." />} />
            <Route path="historial" element={<ComingSoon title="Mi historial" phase="Fase 4" description="Todas tus marcas de entrada/salida con justificaciones y estado de tolerancia." />} />
          </Route>

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        <Toaster position="top-right" richColors closeButton />
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
