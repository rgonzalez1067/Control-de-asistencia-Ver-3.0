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
- **Fase 1 — Auth + Usuarios** ⏳ pendiente confirmación
- **Fase 2 — Config maestra (Sedes/Deptos/Horarios/Settings)** ⏳
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
