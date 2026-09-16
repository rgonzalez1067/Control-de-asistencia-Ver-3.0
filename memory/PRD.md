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



---

## Fase 14 — Endurecimiento de Seguridad + Backup Completo ✅ (2026-02-19)

**Disparador**: fuga externa de datos de empleados (un desarrollador con la URL
pública + credenciales débiles `admin123` obtuvo listado de usuarios).

**Backup ampliado** (`routes/admin.py`):
- `EXPORTABLE_COLLECTIONS` ahora incluye **11 colecciones** (antes 7):
  - `users`, `sites`, `departments`, `schedules`, `novelties`, `visits`, `settings`
  - **NUEVO**: `access_profiles` (RBAC), `attendance` (historial de marcajes),
    `schedule_assignments`, `assignment_plans`.
- `NAT_KEYS` extendido para upsert de las 4 nuevas colecciones.
- Se removió el skip forzado de `attendance` en `admin_import` — ahora se
  respalda y restaura como cualquier otra colección.

**Endurecimiento de seguridad**:
1. **Contraseña admin rotada** a `Sol*1401*1010` (env `ADMIN_PASSWORD`).
2. **Rate-limit** en `/api/auth/login` (5/min por IP) y `/api/auth/register`
   (3/min por IP) usando `slowapi` + middleware. Respuestas 429 tras exceder.
3. **CORS estricto** — `.env` `CORS_ORIGINS` fijado a dominios explícitos
   (`asistencia-web-1.emergent.host` + preview). Sin más `*` en producción.
4. **X-Admin-Token (bóveda administrativa)** en 4 endpoints sensibles:
   `/api/admin/collections`, `/api/admin/export`, `/api/admin/import`,
   `/api/admin/reset-all-passwords`. Token en env `ADMIN_VAULT_TOKEN` (32 bytes
   url-safe). Sin token → 403.
5. **Colección `audit_log`**: registra `login_success`, `login_failed`,
   `admin_reset_password`, `admin_reset_all_passwords`, `admin_export`,
   `admin_import`, `register_bootstrap_admin` con IP (respeta X-Forwarded-For),
   User-Agent, path, timestamp.
6. **`must_change_password=true`** propagado a 141 usuarios no-admin/no-kiosk
   tras la fuga.

**Frontend** (`SettingsPage.jsx`):
- `getVaultToken()` prompt one-shot que guarda el token en `sessionStorage`
  (`megasoft.vault_token`). Se anexa como header `X-Admin-Token` en todas las
  llamadas admin sensibles. Si el server responde 403 el token se borra y se
  vuelve a pedir.
- Copy actualizado: menciona que el backup **incluye asistencia** y protege con
  doble factor.

**Nuevos dependencias**: `slowapi==0.1.10`, `limits==5.8.0`.

---

## Fase 15 — Security Bootstrap Wizard (deploy-friendly) ✅ (2026-02-19)

**Motivación**: En Emergent, el `.env` del preview NO se propaga al deploy, y
editar variables sensibles en el dashboard de producción es tedioso y arriesga
fugas. Se necesita una forma de inicializar seguridad en producción sin tocar
el `.env`.

**Solución**: Un asistente idempotente que se ejecuta **una sola vez por
instancia** desde la UI (`SettingsPage`). Al terminar deja la instancia
protegida y bloquea la re-ejecución.

**Backend**:
- `GET /api/admin/security/status` → `{bootstrapped, has_vault, vault_source, admin_email, bootstrapped_at}`.
- `POST /api/admin/security/generate-vault-token` → genera un token seguro (`secrets.token_urlsafe(32)`), no lo persiste.
- `POST /api/admin/security/bootstrap` → idempotente (`409` si ya fue ejecutado). Rota contraseña admin, guarda hash del vault en `settings.vault_token_hash`, marca `security_bootstrapped=true`, `must_change_password=true` a todos los no-admin/no-kiosk, y registra en `audit_log`.
- `require_admin_vault` ahora consulta en cascada: env `ADMIN_VAULT_TOKEN` → `settings.vault_token_hash` (bcrypt.checkpw). Cualquiera de los dos autoriza.
- CORS defaults hardcoded en el código para los 2 dominios de Emergent (`asistencia-web-1.emergent.host` + preview) — el `.env` de producción ya no necesita `CORS_ORIGINS`.

**Frontend** (`SettingsPage.jsx`):
- Nuevo componente `SecurityBootstrapCard`: si `bootstrapped=false` muestra un banner rojo prominente con botón "Iniciar asistente de seguridad". Si `bootstrapped=true`, muestra estado en verde y fuente del vault.
- `SecurityBootstrapWizard`: modal de 3 pasos. Paso 1: nueva contraseña con validación 12+ chars A/a/0/símbolo. Paso 2: token de bóveda auto-generado readonly con botón "copiar" (checkbox obligatorio de confirmación de haberlo guardado). Paso 3: confirmación explícita y ejecución. Paso 4: resumen con conteo de empleados forzados a cambiar contraseña.
- Al terminar el wizard, guarda automáticamente el token en `sessionStorage.megasoft.vault_token` para que `BackupCard` no lo pida de nuevo en esa sesión.

**Flujo del admin en producción**:
1. Deploy con "Save to GitHub" + redeploy — sin tocar `.env` de prod.
2. Login con la contraseña actual (aun si es débil).
3. Entra a Ajustes → aparece banner rojo → clic → wizard.
4. Nueva contraseña + copia el token generado → confirma.
5. Producción queda protegida. `.env` de producción intacto.

**Rotación futura del vault**: el flag `security_bootstrapped` bloquea el wizard.
Para rotar el token en el futuro se necesita implementar un endpoint separado
`/admin/security/rotate-vault` que exija el vault actual (a construir cuando
sea necesario).

---

## 2026-09-10 — Homologación con fork GitLab (ticket #74354)

Se fusionó el ZIP del repo externo GitLab (`control-de-asistencia-main`, v1.2, ajustado para ambiente NO-Emergent con Docker/Nginx) sobre esta versión.

### Aplicado desde el ZIP
- **Kiosco roster endurecido**: `GET /api/kiosk/roster` ahora exige Bearer (rol kiosk/admin), respuesta sin PII (sin cédula/cargo/departamento/posición), `include_in_schema=False`, sort en Mongo.
- **Refactor SonarQube** en todos los `backend/routes/*.py` (helpers extraídos: `_restore_collection_docs`, `_compute_checkin_lateness`, `_validate_novelty_*`, `_process_late_record`, etc., constantes `ERR_*`).
- **UsersPage**: password temporal con `window.crypto.getRandomValues` (antes `Math.random`).
- **Deployment externo**: `docker-compose.yml`, `Jenkinsfile`, `backend/Dockerfile`, `frontend/Dockerfile`, `frontend/nginx-ssl.conf` (CSP/HSTS), README con pipeline GitLab CI + Redmine.
- `requirements.txt` / `package.json` del ZIP (sin deps Emergent; el código no las importa).

### Decisiones del usuario (aplicadas)
1. **wipe-database ELIMINADO** (endpoint + UI "Zona de Peligro") — el ZIP no lo tiene y el usuario decidió no conservarlo.
2. **Seed admin env-autoritativo** (comportamiento ZIP): en cada arranque, si `ADMIN_PASSWORD` del `.env` no valida contra el hash, se re-sella. El flag `password_updated_by_user` ya NO protege. → La clave admin activa es siempre la del `.env` (actualmente `Sol*1401*1010`).
3. **Adenda Matriz CONSERVADA** (nuestra): `matrix_report.py` y `routes/matrix.py` NO se tocaron — Horario Especial unibloque + `sort_by=name|entry_asc|entry_desc` (rango completo). El ZIP traía versión anterior (sort_order por primer día, 2 bloques) que se descartó.

### Verificación post-merge
- Login admin UI+e2e con `Sol*1401*1010` ✅ (seed restauró la clave al reiniciar)
- `GET /kiosk/roster` sin token → 401 ✅ / con token kiosk → 200 sin PII ✅
- `GET /reports/matrix?sort_by=entry_asc` → 200 ✅ (Adenda intacta)
- RBAC schedules (`_has_rbac_perm`) presente en versión ZIP ✅
- Frontend compila (webpack OK) ✅

---

## 2026-09-14 — Requerimiento formal: 12 mejoras en 5 módulos

Especificación técnica unificada implementada por bloques:

### Módulo 1 · Asignación de Horarios
- **[1.A]** Reordenamiento manual de filas con flechas ↑↓ (elección del usuario: no drag-and-drop). Estado `rowOrder` en `AsignarHorariosPage`, se reinicia al reconstruir matriz. data-testids: `asg-row-up-{userId}` / `asg-row-down-{userId}`.
- **[1.B]** Superposición inteligente: `_find_overlapping_plans(user_ids=...)` en `routes/schedules.py`. Se permite coexistencia de planes simultáneos con equipos disjuntos. Sólo dispara 409 `plan_range_overlap` si comparten ≥1 empleado.
- **[1.C]** Código de colores dinámico: paleta cerrada de 10 colores + "Sin color" (`SCHEDULE_COLOR_PALETTE` en SchedulesPage). Whitelist validada en backend con `Literal[...]` en `ScheduleIn.color`. Celdas de turno en la matriz de asignación adoptan el color del horario.
- **[1.D]** Día Libre implícito: nuevo status `STATUS_DAY_OFF` en `matrix_report.py`. Se calcula `planned_days` desde `assignment_plans`; si el usuario está incluido en un plan y la celda queda sin asignación de turno ni novedad → "Día Libre" (gris, no cuenta como falta).

### Módulo 2 · Matriz de Asistencia
- **[2]** Proyección de novedades futuras: en `matrix_report.py` la evaluación de novedades aprobadas (`novs`) se movió ANTES del corte `STATUS_FUTURE`. Ahora vacaciones/reposo/remoto planificados en fechas futuras se visualizan.

### Módulo 3 · Control de Visitas
- **[3.A]** Motivos actualizados en `VISIT_PURPOSE_CATALOG` (backend) y `PURPOSE_OPTIONS` (frontend): reemplazo de "Visita al Data Center" por dos opciones específicas: `visita_data_center_tbp` y `visita_data_center_lch`.
- **[3.B]** Visitante Interno vs Externo: `VisitorIn` acepta `kind: "external"|"internal"` + `internal_user_id`. Validaciones (`phone`/`cedula` requeridos) sólo aplican a externos. Frontend `VisitorsList` muestra toggle + dropdown de empleados con autocompletado.

### Módulo 4 · Kiosco
- **[4]** Debounce anti-doble-clic: nuevo state `confirming` en `KioskScanPage`. Botón "Sí, soy yo" pasa a disabled + spinner "Registrando…" apenas se dispara. `confirmMark()` con guardia + `finally { setConfirming(false) }`. Idem PIN dialog.

### Módulo 5 · Novedades
- **[5]** Multi-fecha no consecutiva: `NoveltyIn.dates: Optional[List[str]]`. Sólo aplica a `remote`, `permission`, `leave` (por decisión del usuario). Endpoint POST /novelties itera `dates` y crea N documentos con start_date=end_date=fecha. Respuesta: `{created:N, novelty_ids:[...]}`. Frontend NoveltiesPage con toggle "Rango continuo / Días alternos" y calendario `mode="multiple"` de shadcn.

### Verificación
- **Backend**: 12/12 tests pytest PASS (test_iter17_features.py). Whitelist de color validada con 422.
- **Frontend**: compila (webpack OK), data-testids verificados por testing agent.
- **Regresiones**: Ninguna detectada.

---

## 2026-09-15 — Adenda: Integridad de Datos Asignación↔Matriz (PRIORITARIO)

### Bug raíz corregido
**Producto cartesiano fantasma**: `bulkApply`/`clearCells` enviaban `user_ids` y `dates` por separado y el backend hacía el cruce cartesiano completo. En selecciones NO rectangulares se persistían asignaciones fantasma (invisibles en pantalla pero presentes al recargar). Era la causa del reporte "la matriz presenta datos alterados al recargar".

### Correcciones aplicadas
- **`routes/schedules.py`**: nuevos modelos `AssignmentCell` ({user_id, date}), `AssignmentBulkIn.cells`, `AssignmentClearIn.cells`, `AssignmentPlanIn.row_order`. Bulk y clear aceptan celdas exactas (modo legacy cartesiano preservado por compatibilidad). `_prune_out_of_range_assignments()` purga asignaciones fuera del rango al guardar/actualizar un plan (sincronización con Matriz de Asistencia). `row_order` persiste el orden manual de filas (flechas ↑↓).
- **`AsignarHorariosPage.jsx`**: bulk/clear envían `cells` exactos; `savePlan` incluye `row_order`; `loadPlan` lo restaura (filtrado por user_ids del plan).
- **`matrix_report.py`**: refinado `STATUS_DAY_OFF` — sólo aplica a celdas realmente vacías (`not day_asg`). Turno asignado futuro → `future`; novedad asignada → `novelty_full`; vacía en plan → `day_off`.

### Verificación (testing agent iter 18)
Backend 6/6 PASS: cells exactos (2 docs, no 4), clear exacto, regresión legacy OK, row_order persiste, purga de rango funciona, matriz especial con 3 estados correctos. Frontend: smoke sin errores. Cero issues reportados.

---

## 2026-09-15 — Limpieza operativa solicitada por el usuario
Borrados a petición del usuario para probar desde cero:
- `assignment_plans`: 3 → 0 (Planes de Octubre)
- `schedule_assignments`: 421 → 0
- Conservados: attendance (3544), novelties (58), visits (1), users, schedules, sites.

---

## 2026-09-15 — Adenda: Botón "Crear Planificación" + Guardado Transaccional

### 1. Botón "Crear Planificación"
- `AsignarHorariosPage.jsx`: botón junto a "Cargar planificación existente" (data-testid `asg-new-plan`). `resetToNewPlan()` limpia fechas/empleados/matriz/orden/plan actual y deja "Construir matriz" listo.

### 2. Guardado TRANSACCIONAL (fix de corrupción por solapamiento)
**Bug raíz**: `bulkApply`/`clearCells` persistían asignaciones INMEDIATAMENTE en `schedule_assignments` (colección global por user+date). Si luego el guardado del plan era rechazado por solapamiento (409), las líneas del plan original YA habían sido sobrescritas.

**Solución — persistencia diferida + escritura atómica:**
- Frontend: `bulkApply`/`clearCells`/`moveRow` sólo actualizan estado local + badge "Cambios sin guardar" (`dirty`). Nada se escribe hasta "Guardar planificación".
- Backend: `AssignmentPlanIn.assignments` (matriz completa). POST/PUT validan solape ANTES de escribir → 409 = rollback natural (cero escrituras). Si pasa: `_replace_plan_assignments()` hace delete+insert exacto del rango (incluye limpieza de empleados removidos en PUT) + purga fuera de rango.

### Verificación (testing agent iter 19)
6/6 backend PASS: plan+assignments atómico, 409 no toca original (snapshot idéntico), overwrite reemplaza, PUT exacto, regresión bulk legacy OK, matriz especial refleja. 6/6 frontend UI PASS: botón limpia pantalla, persistencia diferida confirmada (sin guardar → nada persiste; guardar+cargar → idéntico).

---

## 2026-09-15 (2) — Adenda: Resolución QUIRÚRGICA de solapamientos

**Regla anterior**: con `overwrite=true` se eliminaba el plan completo aunque el conflicto fuera de un solo empleado.

**Regla nueva** (`_resolve_overlaps_surgical` en `routes/schedules.py`, usada por POST y PUT de planes):
- Del plan original se retiran SÓLO las filas de los empleados en conflicto: sus asignaciones dentro del rango del plan original se eliminan y se quitan de `user_ids`/`row_order`.
- Las filas sin conflicto quedan intactas.
- Si el plan original queda sin empleados → se elimina.
- Diálogo de solapamiento actualizado para explicar el comportamiento.

**Verificado e2e**: Plan A (3 empleados) + Plan B (solapa 1, overwrite) → A conserva 2 filas intactas, fila en conflicto migrada a B. Caso límite: plan que queda vacío se elimina.

---

## 2026-09-15 (3) — Drag-and-drop + flechas ↑↓ en Asignación de Horarios

Reordenamiento dual implementado (opción c del requerimiento):
- `@dnd-kit/core` + `@dnd-kit/sortable` + `@dnd-kit/utilities` instalados.
- Componente `SortableRow` (fila de tabla con useSortable). El drag inicia SÓLO desde el grip ⋮⋮ (`asg-row-drag-{userId}`) para no interferir con la selección de celdas. PointerSensor con 6px de activationConstraint (touch-friendly).
- Flechas ↑↓ (`moveRow`) se conservan como alternativa accesible/tablet.
- Ambos manipulan el mismo `rowOrder` → persistencia `row_order` del plan compartida (sin lógica duplicada).
- Verificado e2e con Playwright: drag real reordena filas y activa badge "Cambios sin guardar".

---

## 2026-09-15 (4) — Calendario de Festivos + Recuperación de Contraseña

### Calendario de Festivos (`/festivos`)
- **Backend**: `routes/holidays.py` — CRUD admin. Modelo `HolidayIn(date, name, is_recurrent)`. Anti-duplicados: recurrente `MM-DD` único; fijo `YYYY-MM-DD` único.
- **Matriz**: `_load_holiday_names()` en `matrix_report.py` — resuelve por (mes, día) para recurrentes y por fecha exacta para fijos. Nuevo `STATUS_HOLIDAY` con celda ámbar "Día Festivo".
- **Reglas**: turnos "día completo" (sin `is_special`) → exhiben "Día Festivo" y eximen marcajes. Turnos especiales/rotativos siguen registrando marcajes (para reporte futuro de horas festivas).
- **Frontend**: `HolidaysPage` con cards, dialog crear/editar (con Switch "Siempre festivo"), delete con confirm. Ítem sidebar "Días festivos" en Configuración. `ReporteMatricialPage` renderiza `holiday` en ámbar; renderers XLSX/PDF también.

### Motor de Correos + Recuperación (auto-servicio)
- **`email_service.py`**: `send_email()` con `aiosmtplib`. Modo NO-OP si SMTP no configurado (devuelve `sent:false`, no rompe el flujo).
- **Vars .env** (esperan datos del usuario): `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_TLS`, `APP_PUBLIC_URL`.
- **Endpoints públicos** (`routes/auth.py`):
  - `POST /auth/forgot-password` — idempotente (nunca revela existencia), rate-limit 5/min. Genera token urlsafe(48), TTL 30 min, envía correo con enlace `/reset-password?token=...`. Auditado.
  - `POST /auth/reset-password-with-token` — consume token (single-use), rate-limit 10/min. Valida política, actualiza password, marca `password_updated_by_user=true`, invalida otros tokens pendientes del usuario.
- **Frontend**:
  - Login: link "¿Olvidaste tu contraseña?" (`login-forgot-link`).
  - `/forgot-password` — pide email/cédula, muestra confirmación siempre (con aviso admin si SMTP no está configurado).
  - `/reset-password?token=` — pide nueva contraseña + confirmación, redirige a login al finalizar.

### Verificado
- Backend: crear/editar/borrar feriado, anti-duplicado 409, matriz aplica recurrentes en 2027 ✅
- Recuperación: forgot idempotente (200 aun con email inexistente), token urlsafe consumido, doble consumo → 400 "ya utilizado", login con nueva pwd OK ✅
- UI: link forgot en login, página forgot muestra "Revisa tu correo" con aviso SMTP no configurado, /festivos crea con recurrente y toast ✅

## 2026-09-15 (5) — FIX: Día Festivo no se mostraba en turnos completos
Bug: condición invertida en matrix_report.py (`not eff_has_schedule` excluía justo a los empleados con horario fijo). Corregida a `hol_name and not is_special` — todo horario estándar queda exento con etiqueta "Día Festivo"; el modo Especial sigue evaluando marcajes. Verificado en UI: 236 celdas "Día Festivo" en ámbar, FALTAS=0. La etiqueta de feriado prima sobre novedades aprobadas (un feriado no consume vacaciones).

## 2026-09-15 (6) — Adenda: Permisos de eliminación (Novedades + Visitas)

### Novedades — Eliminación por Supervisor (con scope)
- **Backend** `routes/novelties.py`:
  - `DELETE /novelties/{id}` — soft delete (`status='deleted'`, `deleted_at`, `deleted_by`). Permisos: admin siempre; creador de la novedad; roles de liderazgo sólo si el `user_id` de la novedad está en su `supervisor_scope_ids()` (equipo directo + él mismo).
  - `GET /novelties` — filtra `status != deleted`. Matrix ya filtraba `status=='approved'`, así que las eliminadas liberan automáticamente los días para re-evaluación.
- **Frontend** `NoveltiesPage.jsx`:
  - `teamIds` set = él mismo + `users.supervisor_id == user.user_id`.
  - Nuevo prop `canSupervisorDelete` en `NoveltyRow` → botón `novelty-team-delete-{id}` visible sólo para líderes no-admin, y sólo cuando el `user_id` está en `teamIds`.

### Visitas — Eliminación exclusiva de Admin
- **Backend** `routes/visits.py`: `DELETE /visits/{id}` responde 403 para todo rol ≠ admin.
- **Frontend** `HistoricoVisitasPage.jsx`: botón `visit-delete-{id}` renderiza sólo si `isAdmin`.

### Verificado
Backend curl: soft-delete OK con `deleted_at/deleted_by`, listado la oculta ✅. Frontend: compila ✅.

## 2026-09-16 — SMTP configurado (Gmail) y flujo de recuperación verificado e2e
- Credenciales reales inyectadas en `backend/.env` (Gmail, puerto 587, STARTTLS, remitente `gestor@megasoft.com.ve`).
- Verificado end-to-end: forgot-password → correo enviado OK (log `Email enviado a ...`) → token consumido vía `reset-password-with-token` → login con nueva clave OK → contraseña admin restaurada y login confirmado ✅.
- El motor SMTP queda habilitado para futuras notificaciones (reportes programados P1, alertas de novedades P1).

## 2026-09-16 (2) — FIX: "Not Found" en Reportes de asistencia
- **Causa raíz**: la homologación con el ZIP de GitLab eliminó los endpoints `GET /api/reports` (lista) y `GET /api/reports/export` (CSV) que el frontend (`ReportsPage.jsx`) consume. Además, el endpoint `/reports/export-csv` traído de GitLab estaba roto (desempaquetaba `_parse_date_range` como tupla cuando devuelve un dict) y nadie lo llamaba.
- **Fix**: restaurados ambos endpoints en `routes/reports.py` desde el historial git (lógica con scope por rol: employee→solo sus marcas, líderes→equipo), y eliminado el `export-csv` defectuoso y sin uso.
- **Verificado**: curl /reports → 3544 registros; /reports/export → CSV válido; UI /reportes → 500 filas renderizadas, stats OK, sin toast de error ✅

## 2026-09-16 (3) — FIX: 403 "No tienes permiso" en Histórico de Visitas pese a tener permiso por perfil
- **Causa raíz**: `routes/visits.py` solo validaba los flags directos `can_view_visit_logs` / `can_create_visits` (o rol admin), ignorando los permisos del perfil de acceso (`visitas_historico` / `visitas_agendar`) que el frontend sí respeta en sus guards. Usuarios con permiso vía perfil (ej. Anna Tata, perfil Gerente) recibían 403.
- **Fix**: helpers `_can_view_visit_logs` / `_can_create_visits` en visits.py que combinan flag directo + permiso RBAC del perfil (mismo patrón que schedules.py). Aplicado a list/get/close/create de visitas.
- **Adicional**: eliminado el scope `created_by` del listado — la página es de auditoría ("Consulta y auditoría de todas las visitas") y era su único consumidor; los no-admin veían lista vacía.
- **Verificado**: Anna (perfil Gerente, historico=true) → 200 con la visita "Mega Soft" en UI ✅; admin → 200 (regresión) ✅; coordinador con perfil sin el permiso → 403 ✅.

## 2026-09-16 (4) — Módulo: Reporte Regulatorio de Visitas (Auditoría de Control de Acceso)
- **RBAC**: nueva clave `visitas_reporte_regulatorio` ("Reporte de Visitas Realizadas", sección Visitas) en MENU_CATALOG → aparece en la grilla de Perfiles de Acceso. Activada ON solo en perfil "Administrador" (update puntual en BD); admin sin perfil la tiene por safety net; resto de perfiles OFF hasta que el admin las habilite.
- **Backend**: `visits_report.py` (build + export PDF/XLSX con PIL para miniaturas) y `routes/reports_visits.py` con `GET /api/reports/visits` (JSON), `export.pdf` (reportlab A4 landscape, membrete institucional, selfies embebidas), `export.xlsx` (openpyxl, fotos ancladas por fila). Permiso validado server-side con `enrich_user_with_permissions`.
- **Reglas confirmadas**: sede = sede del anfitrión · entrada real = timestamp de la 1ra selfie en Kiosco · salida = `exit_at` · una fila por visitante (incluye clasificación Interno/Externo, empresa/motivo laboral, motivo personal).
- **Frontend**: `/reportes/visitas-realizadas` — filtros (rango obligatorio, tipo, sede, anfitrión), grilla con 11 columnas y miniaturas, botones PDF / Excel / Imprimir (ventana con membrete y print stylesheet; detecta popup blocker).
- **Verificado**: testing agent iteración 20 → 11/11 UI PASS (exports reales descargan PDF/XLSX válidos, impresión limpia, filtros, validación de fechas, toggle visible en Perfiles sección Visitas, RBAC OFF en Gerente). Backend curl: 200 JSON/PDF/XLSX, 400 sin fechas, 403 sin permiso ✅

## 2026-09-16 (5) — Adenda: Membrete institucional en Reporte de Visitas Realizadas
- PDF oficial y vista de impresión ahora incluyen el logo corporativo (desde Ajustes) en el encabezado y debajo la línea "Gerencia de Seguridad de la Información · Unidad generadora del reporte".
- Verificado: PDF extraído con texto "Gerencia de Seguridad…" + logo embebido ✅; popup de impresión con logo y gerencia ✅.
