# MegaSoft Asistencia Web/PWA — PRD

## Contexto
Migración del proyecto Mobile/Expo (`attendance-mobile-3`) al stack Full Stack Web/PWA
para obtener una URL productiva estable, PWA instalable y mejorar la UI/UX del admin.
Blueprint original: `/app/handoff/megasoft_handoff/MIGRATION_BLUEPRINT.md`.

## Stack final (adaptado al entorno Emergent)
- **Frontend**: React 19 (CRA + craco) + Tailwind + shadcn/ui + Manrope/Instrument Serif
- **Backend**: FastAPI + Motor + MongoDB (47 endpoints bajo `/api`)
- **Autenticación**: JWT (Authorization: Bearer) + bcrypt (compatible con hashes existentes)
- **PWA**: manifest.webmanifest + service worker (`/sw.js`)
- **Idioma**: español (GMT-4 Caracas)

## Personas
- **Admin**: Gestiona empleados, sedes, departamentos, horarios, ajustes, reportes.
- **Supervisor**: Ve su equipo, aprueba/rechaza novedades, revisa reportes.
- **Employee**: Marca asistencia, ve historial, crea novedades, usa carnet.

## Datos restaurados (Julio 2026)
17 usuarios · 80 asistencias · 15 departamentos · 5 horarios · 2 sedes · 1 settings · 8 novedades.
Todos los `password_hash` (bcrypt) intactos.

## Fases (según blueprint)
- **Fase 0 — Setup + backend + BD** ✅ (2026-07-22)
  - React + Tailwind + shadcn/ui scaffolding
  - Backend FastAPI con 47 endpoints (Auth, Users, Settings, Sites, Departments,
    Schedules, Kiosk, Attendance, Novelties, Reports/Stats, Onboarding)
  - Base de datos restaurada desde `db_backup.tar.gz`
  - Login funcional con `rgonzalez@megasoft.com.ve / admin123`
  - PWA manifest + service worker básico
- **Fase 1 — Auth + Usuarios** ✅ (2026-07-22)
  - Login rediseñado (editorial dual-panel, dark corporate + amber accent)
  - AppLayout con sidebar (desktop) + bottom nav (mobile) + dropdown de usuario
  - Dashboard admin real con KPIs y gráfica de 7 días (Recharts)
  - CRUD completo de empleados: crear, editar, eliminar, resetear password
  - Import CSV con plantilla descargable
  - Onboarding con `getUserMedia` (selfie 480×480)
  - ProtectedRoute con soporte de `roles`
  - Testing 100% (32/32 backend + flujos frontend E2E)
- **Fase 2 — Config maestra** ✅ (2026-07-22)
  - Sedes CRUD (sin geocerca — geocerca removida del backend en `_register_attendance`)
  - Departamentos CRUD con conteo de empleados
  - Horarios como cards con bloques editables
  - Ajustes de la empresa: nombre, timezone, logo (subida base64), método de identificación (face/pin/both), switch kiosk_enabled
  - `sites_update` / `departments_update` / `schedules_update` con `exclude_unset=True` (no borra campos ausentes)
- **Fase 3 — Kiosco + Carnet** ✅ (2026-07-22)
  - `/kiosk` — desbloqueo con credenciales admin (sessionStorage) 
  - `/kiosk/scan` — face-api.js@0.22.2 desde CDN + fallback PIN visual cuando WebGL no está disponible
  - Confirmación con foto + botones "Entrada/Salida" 
  - Modo PIN: picker de empleados con fotos + entrada de PIN
  - `/carnet` — tarjeta digital editorial con selfie, cargo, sede, horario, ID
- **Vista Employee** ✅ (2026-07-22)
  - `/historial` — mis marcas con KPIs (hoy/mes), botones rápidos marcar entrada/salida (con geolocation opcional), justificación de tardanzas
  - `HomeRedirect` — employees van a `/historial`, admin/supervisor al dashboard
- **UsersPage** — avatar clickeable con badge verde si onboarded, diálogo `user-photo-dialog` que llama `/api/users/{id}/photo`

- **Fase 4 — Reportería + Team + Novedades** ✅ (2026-07-22)
  - ReportsPage: 6 filtros (from/to/user/site/type/status), 4 KPIs, tabla con badges y export CSV
  - NoveltiesPage: tabs (pendientes/historial/todas), crear con selector empleado (admin), aprobación bulk sticky, decisión individual con comentario, delete propio para employees
  - TeamPage: matriz día×empleado con horas de primera entrada / última salida, KPIs, selector 1/3/7/14/30 días. Admin ve todos los no-admin; supervisor sólo su equipo (`supervisor_id`)
  - Fix: `NAV_ADMIN` ahora incluye "Mi equipo" en sidebar
- **Fase 5 — PWA productivo** ✅ parcial (2026-07-22)
  - `InstallPWAPrompt` — banner discreto tras `beforeinstallprompt`, con dismiss persistente en localStorage
  - Deploy checklist en `/app/memory/DEPLOY_CHECKLIST.md`
  - Supresión de warnings `ResizeObserver loop` en dev overlay

- **Extras (2026‑07‑22)**:
  - **Dashboard Ejecutivo** con backend `GET /api/stats/executive?days=N` (top‑5 tardanzas + ranking por departamento + prom. minutos tarde). Widget en dashboard con selector de rango (7/14/30/60/90) y **export PDF** (jsPDF + jsPDF-autoTable) con branding corporativo, KPIs y tablas.
  - **Modo Oscuro** con `ThemeContext` + `ThemeToggle` en el header. Persiste en localStorage, respeta `prefers-color-scheme`. Paleta `.dark` refinada. Reemplazado en batch `bg-white/80 backdrop-blur → bg-card/80 backdrop-blur` y `text-primary → text-foreground` en headings para legibilidad.
  - Testing: 57/57 backend (49 previos + 8 nuevos `TestExecutiveStats`), 100% frontend en flujos de widget + toggle.
- **Fase 3 — Kiosco + Carnet (cámara + face-api)** ⏳
- **Fase 4 — Reportería + Team + Novedades** ⏳
- **Fase 5 — PWA productivo + Deploy** ⏳

## Endpoints backend (implementados)
`/api/auth/*` · `/api/users/*` · `/api/settings` · `/api/sites/*` · `/api/departments/*` ·
`/api/schedules/*` · `/api/kiosk/*` · `/api/attendance/*` · `/api/novelties/*` ·
`/api/stats/dashboard` · `/api/reports` · `/api/reports/export` · `/api/onboarding/selfie`.

## Backlog / Frontend por construir (P0 → P2)
- **P0 Fase 1**: LoginPage ✅ · Layout con navbar/sidebar · Users CRUD (admin) · Import CSV
  · Onboarding con `getUserMedia` (selfie).
- **P0 Fase 2**: Sites CRUD (con Google Maps resolve-link) · Departments CRUD ·
  Schedules CRUD · Company Settings.
- **P0 Fase 3**: `/kiosk` con face-api.js@0.22.2 desde CDN · `/carnet` digital · re-enrolamiento con PIN.
- **P1 Fase 4**: `/historial` · `/novedades` · `/reportes` (export) · `/equipo` · `/dashboard` admin (Recharts).
- **P1 Fase 5**: install prompt PWA · testing iOS/Android · deploy productivo.

## Credenciales
Ver `/app/memory/test_credentials.md`.

## Archivos clave
- Backend: `/app/backend/server.py`, `/app/backend/.env`
- Frontend: `/app/frontend/src/App.js`, `/app/frontend/src/context/AuthContext.jsx`,
  `/app/frontend/src/pages/LoginPage.jsx`, `/app/frontend/src/pages/DashboardPlaceholder.jsx`
- PWA: `/app/frontend/public/manifest.webmanifest`, `/app/frontend/public/sw.js`
- Handoff: `/app/handoff/megasoft_handoff/` (blueprint, backup, README)
