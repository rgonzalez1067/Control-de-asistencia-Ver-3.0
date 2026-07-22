import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { AuthProvider } from "@/context/AuthContext";
import ProtectedRoute from "@/components/ProtectedRoute";
import AppLayout from "@/components/AppLayout";
import LoginPage from "@/pages/LoginPage";
import HomeRedirect from "@/pages/HomeRedirect";
import UsersPage from "@/pages/UsersPage";
import SedesPage from "@/pages/SedesPage";
import DepartmentsPage from "@/pages/DepartmentsPage";
import SchedulesPage from "@/pages/SchedulesPage";
import SettingsPage from "@/pages/SettingsPage";
import HistorialPage from "@/pages/HistorialPage";
import CarnetPage from "@/pages/CarnetPage";
import OnboardingPage from "@/pages/OnboardingPage";
import KioskUnlockPage from "@/pages/KioskUnlockPage";
import KioskScanPage from "@/pages/KioskScanPage";
import ComingSoon from "@/pages/ComingSoon";

const ADMIN = ["admin"];
const ADMIN_OR_SUP = ["admin", "supervisor"];

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          {/* Public / kiosk */}
          <Route path="/login" element={<LoginPage />} />
          <Route path="/kiosk" element={<KioskUnlockPage />} />
          <Route path="/kiosk/scan" element={<KioskScanPage />} />

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
            <Route index element={<HomeRedirect />} />

            {/* Admin */}
            <Route path="usuarios" element={<ProtectedRoute roles={ADMIN}><UsersPage /></ProtectedRoute>} />
            <Route path="sedes" element={<ProtectedRoute roles={ADMIN}><SedesPage /></ProtectedRoute>} />
            <Route path="departamentos" element={<ProtectedRoute roles={ADMIN}><DepartmentsPage /></ProtectedRoute>} />
            <Route path="horarios" element={<ProtectedRoute roles={ADMIN}><SchedulesPage /></ProtectedRoute>} />
            <Route path="ajustes" element={<ProtectedRoute roles={ADMIN}><SettingsPage /></ProtectedRoute>} />

            {/* Admin + Supervisor */}
            <Route path="reportes" element={<ProtectedRoute roles={ADMIN_OR_SUP}><ComingSoon title="Reportes" phase="Fase 4" description="Historial global de asistencia con filtros por fecha, sede y usuario. Exportación a CSV lista para RRHH." /></ProtectedRoute>} />
            <Route path="equipo" element={<ProtectedRoute roles={ADMIN_OR_SUP}><ComingSoon title="Mi equipo" phase="Fase 4" description="Vista de supervisor con asistencia del equipo asignado y aprobación de novedades." /></ProtectedRoute>} />

            {/* Todos los roles */}
            <Route path="novedades" element={<ComingSoon title="Novedades" phase="Fase 4" description="Vacaciones, permisos y ausencias con flujo de aprobación bulk." />} />
            <Route path="carnet" element={<CarnetPage />} />
            <Route path="historial" element={<HistorialPage />} />
          </Route>

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        <Toaster position="top-right" richColors closeButton />
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
