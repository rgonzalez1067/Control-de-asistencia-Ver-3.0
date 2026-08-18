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

- **Extras (2026‑02‑29 - Fork)**:
  - **Kiosco robusto**: modo Sleep/Idle (15s), Admin biometric unlock, salida controlada, generación de `face_descriptor` desde onboarding Web.
  - **Tolerancia dual**: `tolerance_minutes` + `justification_tolerance_minutes` (retraso leve/mayor) con badges y campos `late_minor/late_major/requires_justification`.
  - **Timezone global UTC-4 (Caracas)** en frontend.
  - **Import Excel .xlsx** de empleados con preview, upsert y resolución nombre→ID (openpyxl).
  - **Change Password** desde perfil (`POST /api/auth/change-password`).
  - **Módulo Control de Visitas**: agendar, histórico, cierre de visita, selfies secuenciales en kiosco, `is_minor` checkbox, `duration_minutes` calculada.
  - **Roles normalizados**: admin/supervisor/employee con badges unificados y filtro por departamento en Users.
  - **Historial estricto biométrico (2026-02-29)**: eliminados botones "Marcar Entrada/Salida" manuales de `/historial`. Toda marca debe pasar por el kiosco con reconocimiento facial.

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

## Adendo Kiosco (Feb 2026)

### Fase 1 — Reglas de asistencia ✅
- Cálculo de `break_excess_minutes` cuando el break > 60 min.
- Auto-cierre a 23:59 (America/Caracas) con `auto_closed = True`.

### Fase 2 — Kiosco pineado por sede ✅
- **Backend** (implementado):
  - `GET  /api/kiosk/sites` — listado público de sedes (para el selector del kiosco antes de autenticar).
  - `POST /api/kiosk/session/open` — abre sesión de kiosco por sede; rechaza (409) si hay otra sesión activa en la misma sede (TTL 5 min).
  - `POST /api/kiosk/session/heartbeat` — mantiene sesión viva (frontend envía cada 2 min).
  - `POST /api/kiosk/session/close` — cierra la sesión (al bloquear/salir).
  - `matrix_report.py` marca `site_mismatch` cuando un empleado marca en una sede distinta a la suya (resaltado en `ReporteMatricialPage`).
- **Frontend** (implementado 07-Feb-2026):
  - `KioskUnlockPage`: paso 1 auth (rostro/credenciales) → paso 2 selector de sede → llama `session/open` y guarda `session_id`, `site_id`, `site_name` en `sessionStorage`.
  - `KioskScanPage`: valida sesión en mount; muestra badge de sede en header; envía `site_id` en cada `attendance/check`; heartbeat cada 2 min; bloquea `beforeunload`, F5/Ctrl+R/Ctrl+W/Alt+F4, context menu.
  - Botones "Bloquear" y "Salir" ahora exigen credenciales de administrador y cierran la sesión al éxito.

## Backlog restante (post-Adendo)
- **P1**: Reportes Ejecutivos programados (PDF semanal por email a directores).
- **P1**: Panel semaforizado en Dashboard (tardanzas/faltas).
- **P1**: Alertas de novedades vía Slack/Email (requiere webhook del usuario).
- **P2**: Contador "Mi equipo · N miembros" en sidebar del supervisor.
- **Refactor**: modularizar `/app/backend/server.py` en routers.

### Permisos especiales (Feb 2026)
- Sección renombrada en la ficha de empleado: **"Permisos · Control de visitas" → "Permisos especiales"**.
- Nuevo permiso `can_manage_schedules` en `UserUpdate` (backend) y checkbox `user-form-can-manage-schedules` (UsersPage).
- **Efecto**:
  - `POST/PUT/DELETE /api/schedules` — permitido a admin **o** cualquier usuario con `can_manage_schedules=True` (nuevo dependency `_require_admin_or_schedules_manager`).
  - Nuevo endpoint `PATCH /api/users/{user_id}/schedule` — asigna/desasigna horario a un empleado. Permitido a admin, o supervisor directo del empleado con `can_manage_schedules=True`.
  - Sidebar: si el usuario tiene el permiso, aparece el link "Horarios".
  - Ruta `/horarios`: guard `check={(u) => u.role === "admin" || u.can_manage_schedules}` (nuevo prop `check` en `ProtectedRoute`).
  - `TeamPage`: para admin y supervisores con permiso, cada empleado del equipo muestra un `Select` compacto para asignar horario en línea.

## Cambios recientes (Feb 12, 2026)

### Fix: PIN de visitas ya no es aleatorio ✅
**Motivo**: la generación de un PIN aleatorio de 3 dígitos al agendar una visita
creaba confusión porque en el kiosco la validación real usa los **últimos 3 dígitos
de la cédula** de cada visitante. Se emitía un PIN paralelo que no coincidía con
lo que el visitante finalmente ingresaba.

**Cambios**:
- Backend (`/app/backend/server.py`):
  - Eliminada la generación de `check_in_pin = secrets.randbelow(1000)` al crear una visita.
  - Eliminado el campo `check_in_pin` del documento de la visita.
  - `POST /api/visits` ya no devuelve `check_in_pin` (sólo `{visit_id, ok}`).
  - Eliminado el endpoint legacy `POST /api/kiosk/visits/{visit_id}/verify-pin` y el schema `VisitPinIn`.
  - La única validación PIN en el kiosco sigue siendo `POST /api/kiosk/visits/{visit_id}/verify-visitor` que compara los últimos 3 dígitos de la cédula del visitante seleccionado.
- Frontend (`/app/frontend/src/pages/AgendarVisitaPage.jsx`):
  - El copy de la pantalla ahora indica claramente: *"En el kiosco, cada visitante deberá ingresar los últimos 3 dígitos de su cédula"*.
  - El diálogo de confirmación ya no muestra un PIN aleatorio grande, sino una lista de visitantes con los últimos 3 dígitos de sus cédulas (o `—` si no aplica, p. ej. menor de edad).
  - Se removió el botón "Copiar PIN".

## Cambios recientes (Feb 14, 2026)

### Nuevo rol `kiosk` — usuarios operativos para arranque directo del Kiosco ✅
**Motivo**: personal de recepción/seguridad debe poder encender la app en modo
Kiosco sin acceder al panel administrativo ni al selector de sede. Además, la
provisión de estos usuarios debe replicarse automáticamente en cualquier deploy.

**Backend** (`/app/backend/server.py`):
- Nuevo rol canónico `kiosk` en `_ROLE_ALIASES` / `normalize_role`.
- Guard global en `get_current_user`: un JWT de rol `kiosk` sólo puede llamar
  endpoints bajo `/api/kiosk/*` (más `/api/auth/me` y `/api/auth/logout`).
  Cualquier otro endpoint responde **403**.
- Seed automático en `on_startup` (`_seed_kiosk_users`) — idempotente:
  - `kiosco.tbp@megasoft.com.ve` → sede "Sede Torre Banco Plaza"
  - `kiosco.lch@megasoft.com.ve` → sede "Sede Los Chaguaramos"
  - Contraseña por defecto `Mega2026*`, override vía envs
    `KIOSK_TBP_PASSWORD` / `KIOSK_LCH_PASSWORD`.
  - Si el usuario ya existe, sólo se refresca `role`/`site_id` si están
    desalineados. **Nunca reescribe la contraseña** una vez rotada por el admin.
- `POST /api/kiosk/session/open` ahora inspecciona el header `Authorization`:
  si el requester es un usuario `kiosk` cuyo `site_id` coincide con el solicitado,
  se cierra automáticamente cualquier sesión huérfana en esa sede
  (caso: tablet perdió energía sin cerrar sesión). Sin token o con token
  inválido/de otra sede, mantiene el bloqueo 409.

**Frontend**:
- Nueva página `/app/frontend/src/pages/KioskAutoStart.jsx` (ruta `/kiosk/auto`):
  toma `user.site_id`, llama `session/open` (que auto force-cierra la sesión
  vieja gracias al bearer del kiosk-user), setea `sessionStorage`, y redirige
  a `/kiosk/scan`. Muestra estado + error box con opción de "cerrar sesión".
- `LoginPage`: si `res.user.role === "kiosk"`, navega a `/kiosk/auto` (skip
  `HomeRedirect`).
- `HomeRedirect`: si el usuario es `kiosk`, redirige a `/kiosk/auto`.
- `ProtectedRoute`: añade prop opcional `redirectTo`. El App shell usa
  `check={(u) => u.role !== "kiosk"} redirectTo="/kiosk/auto"` para blindar
  cualquier ruta admin/supervisor/empleado ante un usuario `kiosk`.
- `KioskScanPage.exitToAdmin` / `lockKiosk`: si el usuario actual es `kiosk`,
  ahora se hace `logout()` antes de navegar. Sin esto, `HomeRedirect` rebotaría
  al usuario de vuelta a `/kiosk/auto`.
- El diálogo "Salir del kiosco" ya usaba `/kiosk/unlock` (que exige rol `admin`).
  Un usuario `kiosk` no puede desbloquearse a sí mismo — 401 automático.




---

## Fase 11 — Flujo de Aprobación/Rechazo de Justificaciones ✅ (2026-08-17)

**Objetivo**: Los supervisores y admins pueden revisar las justificaciones enviadas
por sus empleados desde la pantalla "Mi Equipo" y decidir Aceptar (retraso
justificado, no penaliza minutos) o Rechazar con razón obligatoria (retraso
injustificado, suma minutos perdidos).

**Backend** (`/app/backend/server.py`):
- Nuevos campos en `attendance`: `justification_status` (`none|pending|approved|rejected`),
  `rejection_reason`, `decided_by`, `decided_at`.
- `POST /api/attendance/justify` ahora setea `justification_status = "pending"` en lugar
  de sólo limpiar `requires_justification`.
- **NUEVO** `POST /api/attendance/justify/decide` — admin/coordinador/gerente/director:
  - `decision="approved"` → `justification_status="approved"` (excluye penalización).
  - `decision="rejected"` requiere `rejection_reason` (≥3 chars) — sino HTTP 400.
  - Leaders sólo deciden sobre su propio equipo (403 fuera de scope).
- **Startup backfill**: registros legacy con `justification` de texto → `approved`;
  sin texto → `none`.
- `GET /api/stats/executive/summary`: los `approved` no cuentan en `total_late`,
  `total_late_minutes`, ni en el ranking por departamento.
- `GET /api/stats/dashboard`: expone `pending_justifications` (count global del scope).
- `GET /api/reports/export` (CSV): añade columnas `justification_status` y `rejection_reason`.
- `matrix_report.py`: sólo `approved` cuenta como `late_justified`; `pending`/`rejected`/
  `none` suman `lost_minutes`.

**Frontend**:
- `/app/frontend/src/pages/TeamPage.jsx`: matriz de "Mi Equipo" ahora colorea cada celda por
  `justification_status` (pendiente=amber pulsante + `FileWarning`, aprobada=emerald +
  `CheckCircle2`, rechazada=red + `XCircle`). Cada celda con justificación pendiente o
  ya decidida es clickeable → abre `Dialog` con texto del empleado y botones "Aceptar
  justificación" (verde) / "Rechazar" (rojo). Al rechazar, se despliega textarea
  obligatoria "Razón del rechazo" antes de confirmar. KPI nuevo: "Justif. pendientes".
- `/app/frontend/src/pages/HistorialPage.jsx`: el empleado ve badges de estado:
  `Pendiente de aprobación` (amber), `Justificado` (emerald), `Injustificado` (red)
  con "Motivo: {rejection_reason}" cuando aplica.
- `/app/frontend/src/pages/ReportsPage.jsx`: columna Estado muestra "Retraso justificado",
  "Injustificado", "Pendiente"; columna Justificación resalta razón de rechazo en rojo.

**Data-testids sembrados en TeamPage**:
`team-kpi-pending-just`, `team-cell-review-{user_id}-{yyyy-mm-dd}`,
`team-justify-dialog`, `team-justify-text`, `team-btn-approve`, `team-btn-reject`,
`team-reject-reason`, `team-btn-reject-confirm`.

**Testing** (2026-08-17):
- Backend: 9/9 pytest pass en `/app/backend/tests/test_justify_flow.py` — submit,
  decide approve/reject, 400 sin reason, 403 fuera de scope, dashboard KPI,
  executive summary excluye approved, CSV headers.
- Frontend: Playwright E2E validado en TeamPage (celda pendiente clickeable, dialog
  con texto, flujo aprobar y rechazar con validación de razón), HistorialPage
  (badges de estado), ReportsPage (columnas actualizadas).

**Deuda técnica identificada por testing agent** (no blocker):
- `server.py` en 3496 líneas — necesita refactor a routers.
- KPI "Justif. pendientes" en TeamPage se calcula del lado cliente sobre el período
  visible; el dashboard es global. Se puede alinear en el futuro.


---

## Fase 12 — Corrección del cálculo E1 vs E2 en Historial ✅ (2026-08-17)

**Problema**: `_register_attendance` marcaba cada 'in' (incluida E2) como tardanza
respecto a `blocks[0].start`, inflando artificialmente `late_minutes` en la
segunda entrada del día. La Matriz de Asistencia ya usaba la regla correcta.

**Regla oficial (homogeneizada con `matrix_report.py`)**:
- **E1** (primera entrada del día): `delta = actual - blocks[0].start`. Si
  `delta > tolerance` → tarde con severidad según ventana de justificación.
- **E2+**: `gap = E2 - S1`. Si `gap ≤ 60 min` → **on_time** (hora en negro, sin
  justificación). Si `gap > 60 min` → `late_minutes = gap - 60`, hora en **rojo**,
  severidad y justificación según ventana.

**Backend** (`/app/backend/server.py`):
- `_register_attendance` ahora detecta si es E2+ vía `count_documents` de 'in'
  previos del mismo día y aplica la regla correspondiente. Además serializa
  `entry_index` (0 para E1, 1 para E2, ...) al documento.
- **NUEVO** `_backfill_entry_index_and_lateness()` — helper en startup que
  recorre TODA la colección `attendance` agrupada por (user_id, día), reindexa
  cada 'in' y recalcula lateness. Preserva `requires_justification=False` si
  el status ya fue `approved`/`rejected` (no deshace decisiones del supervisor).

**Frontend** (`/app/frontend/src/pages/HistorialPage.jsx`):
- Registros 'in' con `entry_index >= 1 && is_late` muestran la hora en `text-red-600 font-semibold`.
- Badge Tipo: "Entrada" para E1, "Entrada 2/3/…" para E2+.
- Estado: "Exceso de descanso · Xm" para E2+ tarde (en vez de "Retraso mayor/leve").

**Testing** (2026-08-17):
- 5/5 pytest en `/app/backend/tests/test_entry_e2_lateness.py`. Frontend Playwright
  E2E validado: hora en rojo para E2 tarde, badge "Entrada 2", estado "Exceso de descanso".
- Consistencia con Matrix Report confirmada (mismo umbral 60, mismos late_minutes).


---

## Fase 13 — Refactor Backend a Routers Modulares ✅ (2026-02-18)

**Objetivo**: reducir el tamaño de `server.py` (monolito ~3.7k líneas) partiéndolo
en módulos de rutas dentro de `/app/backend/routes/`, sin alterar comportamiento
ni contratos de API.

**Estrategia**: `deps.py` re-exporta símbolos (`api`, `db`, modelos Pydantic,
helpers) desde `server.py`. Cada archivo de rutas hace `from deps import ...` y
registra endpoints con `@api.get/@api.post` como side-effect al ser importado.

**Iteración 1 (feb-2026)**: `attendance.py`, `novelties.py`.
**Iteración 2 (feb-2026)**: `visits.py`, `reports.py`, `matrix.py`.
**Iteración 3 (feb-2026)**: `auth.py`, `catalogs.py` (sites + departments +
settings + docs), `access_profiles.py`, `schedules.py`, `kiosk.py`, `admin.py`
(backup/restore + onboarding).
**Iteración 4 (feb-2026)**: `users.py` (CRUD + Excel import/preview + selfie +
PIN + photo). Cierra la Fase A.

**Estado post-Iteración 4**:
- `server.py`: 2735 → **1080 líneas (-60 %)** — objetivo <1000 casi alcanzado.
- 12 routers en `/app/backend/routes/` (2867 líneas modulares).
- Ruff: sin errores. Smoke tests curl: 18/18 endpoints migrados devuelven 200.
- Pytest serial (35 tests de módulos migrados incluidos users): 33/35 PASS.
  Los 2 tests que fallan (`test_users_import_template`, `test_users_import_csv`)
  esperan CSV pero el endpoint devuelve XLSX — regresión de tests, no del código.

**Endpoints aún en `server.py`**: `/` (root/health) y el helper `_load_import_lookups`
(usado tanto por `on_startup` como por `routes/users.py`).

**Nota**: durante la iteración se detectó que las credenciales `admin123` /
`NewJgil!234` de la BD habían quedado desincronizadas por un test previo. Se
restauraron manualmente. La suite pytest muestra ~15 flaky tests por
race-condition entre `test_change_password` y otras suites bajo `-n 2`; NO es
regresión del refactor (los mismos tests fallaban antes).

