import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { AuthProvider } from "@/context/AuthContext";
import { ThemeProvider } from "@/context/ThemeContext";
import ProtectedRoute from "@/components/ProtectedRoute";
import AppLayout from "@/components/AppLayout";
import InstallPWAPrompt from "@/components/InstallPWAPrompt";
import ForgotPasswordPage from "@/pages/ForgotPasswordPage";
import ResetPasswordPage from "@/pages/ResetPasswordPage";
import HolidaysPage from "@/pages/HolidaysPage";
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
import ReportsPage from "@/pages/ReportsPage";
import ReporteMatricialPage from "@/pages/ReporteMatricialPage";
import AsignarHorariosPage from "@/pages/AsignarHorariosPage";
import NoveltiesPage from "@/pages/NoveltiesPage";
import TeamPage from "@/pages/TeamPage";
import AgendarVisitaPage from "@/pages/AgendarVisitaPage";
import HistoricoVisitasPage from "@/pages/HistoricoVisitasPage";
import ReporteVisitasRegulatorioPage from "@/pages/ReporteVisitasRegulatorioPage";
import KioskAutoStart from "@/pages/KioskAutoStart";
import SecurityProfilesPage from "@/pages/SecurityProfilesPage";
import UserPermissionsPage from "@/pages/UserPermissionsPage";

const ADMIN = ["admin"];
const ADMIN_OR_SUP = ["admin", "coordinador", "gerente", "director"];

function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <BrowserRouter>
        <Routes>
          {/* Public / kiosk */}
          <Route path="/login" element={<LoginPage />} />
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />
          <Route path="/reset-password" element={<ResetPasswordPage />} />
          <Route path="/kiosk" element={<KioskUnlockPage />} />
          <Route path="/kiosk/scan" element={<KioskScanPage />} />
          <Route path="/kiosk/auto" element={<KioskAutoStart />} />

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
              <ProtectedRoute
                check={(u) => u.role !== "kiosk"}
                redirectTo="/kiosk/auto"
              >
                <AppLayout />
              </ProtectedRoute>
            }
          >
            <Route index element={<HomeRedirect />} />

            {/* Admin */}
            <Route path="usuarios" element={<ProtectedRoute roles={ADMIN} permKey="empleados"><UsersPage /></ProtectedRoute>} />
            <Route path="sedes" element={<ProtectedRoute roles={ADMIN} permKey="sedes"><SedesPage /></ProtectedRoute>} />
            <Route path="departamentos" element={<ProtectedRoute roles={ADMIN} permKey="departamentos"><DepartmentsPage /></ProtectedRoute>} />
            <Route path="horarios" element={
              <ProtectedRoute permKey="horarios" check={(u) => u.role === "admin" || (u.effective_permissions||{}).horarios || u.can_manage_schedules}>
                <SchedulesPage />
              </ProtectedRoute>
            } />
            <Route path="asignar-horarios" element={
              <ProtectedRoute permKey="asignar_horarios" check={(u) => u.role === "admin" || (u.effective_permissions||{}).asignar_horarios || u.can_assign_schedules}>
                <AsignarHorariosPage />
              </ProtectedRoute>
            } />
            <Route path="ajustes" element={<ProtectedRoute roles={ADMIN} permKey="ajustes"><SettingsPage /></ProtectedRoute>} />
            <Route path="festivos" element={<ProtectedRoute roles={ADMIN}><HolidaysPage /></ProtectedRoute>} />

            {/* Seguridad · RBAC — sólo admin */}
            <Route path="seguridad/perfiles" element={<ProtectedRoute roles={ADMIN} permKey="seguridad_perfiles"><SecurityProfilesPage /></ProtectedRoute>} />
            <Route path="seguridad/permisos" element={<ProtectedRoute roles={ADMIN} permKey="seguridad_permisos"><UserPermissionsPage /></ProtectedRoute>} />

            {/* Admin + Supervisor */}
            <Route path="reportes" element={<ProtectedRoute permKey="reportes"><ReportsPage /></ProtectedRoute>} />
            <Route path="reporte-matricial" element={<ProtectedRoute permKey="matriz"><ReporteMatricialPage /></ProtectedRoute>} />
            <Route path="equipo" element={<ProtectedRoute roles={ADMIN_OR_SUP} permKey="equipo"><TeamPage /></ProtectedRoute>} />

            {/* Todos los roles */}
            <Route path="novedades" element={<ProtectedRoute permKey="novedades"><NoveltiesPage /></ProtectedRoute>} />
            <Route path="carnet" element={<ProtectedRoute permKey="mi_carnet"><CarnetPage /></ProtectedRoute>} />
            <Route path="historial" element={<ProtectedRoute permKey="historial"><HistorialPage /></ProtectedRoute>} />

            {/* Control de visitas — permisos individuales */}
            <Route path="visitas/agendar" element={
              <ProtectedRoute permKey="visitas_agendar"
                check={(u) => u.role === "admin" || (u.effective_permissions||{}).visitas_agendar || u.can_create_visits}>
                <AgendarVisitaPage />
              </ProtectedRoute>
            } />
            <Route path="visitas/historico" element={
              <ProtectedRoute permKey="visitas_historico"
                check={(u) => u.role === "admin" || (u.effective_permissions||{}).visitas_historico || u.can_view_visit_logs}>
                <HistoricoVisitasPage />
              </ProtectedRoute>
            } />
            <Route path="reportes/visitas-realizadas" element={
              <ProtectedRoute permKey="visitas_reporte_regulatorio">
                <ReporteVisitasRegulatorioPage />
              </ProtectedRoute>
            } />
          </Route>

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        <Toaster position="top-right" richColors closeButton />
        <InstallPWAPrompt />
      </BrowserRouter>
    </AuthProvider>
    </ThemeProvider>
  );
}

export default App;
