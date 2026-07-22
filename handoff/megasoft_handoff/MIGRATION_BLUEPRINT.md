# 📘 Blueprint: Migración Expo → Next.js Full Stack Web/PWA

> **Proyecto**: App de Control de Asistencia — MegaSoft
> **Origen**: React Native + Expo Web (proyecto Mobile de Emergent)
> **Destino**: Next.js 15 + Tailwind + shadcn/ui (proyecto Full Stack de Emergent)
> **Preparado**: Junio 2026

---

## 🎯 Objetivos de la migración

1. Obtener una **URL productiva estable** para desplegar el kiosco y el dashboard.
2. **PWA instalable** nativa del navegador (con manifest, service worker, offline caching).
3. Mantener **100% de funcionalidad actual**.
4. Aprovechar la migración para **mejorar la UI/UX** del dashboard admin (que hoy es una vista adaptada de mobile).

---

## 🧱 Stack recomendado (elegido por mí según tus requisitos)

| Capa | Tecnología | Por qué |
|---|---|---|
| Framework frontend | **Next.js 15 (App Router)** | Es el estándar oficial de Emergent para Full Stack Web/PWA. SSR + PWA nativo. |
| Estilos | **Tailwind CSS 4** | Productividad alta, sistema de diseño consistente, tamaño de bundle chico. |
| Componentes UI | **shadcn/ui** | Componentes accesibles pre-hechos (Dialog, Dropdown, Toast, Tabs, DataTable). |
| Iconos | **lucide-react** | Reemplaza `@expo/vector-icons`. Ligero y moderno. |
| Formularios | **react-hook-form + zod** | Validación tipada, best-in-class para admin/CSV. |
| Fetch/HTTP | **fetch nativo + SWR o TanStack Query** | Caching declarativo, revalidación automática. |
| Auth (cliente) | **cookies HTTP-only + Middleware Next.js** | Más seguro que localStorage; funciona con SSR. |
| Cámara | **`getUserMedia()` + `<video>` + `<canvas>`** | Reemplaza `expo-camera` + `expo-image-manipulator`. |
| Face detection | **face-api.js@0.22.2 desde CDN** *(sin cambios)* | Ya lo tenemos funcionando. |
| Charts | **Recharts** o **shadcn/ui charts** | Reemplaza `react-native-svg` custom charts. |
| PWA | **`next-pwa`** o service worker manual | Manifest + offline caching + install prompt. |
| Notificaciones | **sonner** (toast) o shadcn/ui `<Toast>` | Reemplaza `Alert.alert` que era problemático. |
| Backend | **FastAPI + Motor + MongoDB** *(sin cambios)* | 47 endpoints ya listos. Solo se copia. |

---

## 📁 Inventario completo del proyecto ACTUAL

### Backend (`/app/backend/server.py` — 1504 líneas)
**47 endpoints agrupados por dominio**:

| Dominio | Endpoints | Prioridad migración |
|---|---|---|
| **Auth** (7) | `/auth/register, login, me, logout, change-password, reset-password, needs-bootstrap` | 🔴 Fase 1 |
| **Users** (8) | `/users` (CRUD, import, template, selfie, pin) | 🔴 Fase 1 |
| **Settings** (2) | `/settings` GET/PUT | 🟡 Fase 2 |
| **Sites** (5) | `/sites` (CRUD + resolve-link) | 🟡 Fase 2 |
| **Departments** (3) | `/departments` (CRUD) | 🟡 Fase 2 |
| **Schedules** (3) | `/schedules` (CRUD) | 🟡 Fase 2 |
| **Kiosk** (5) | `/kiosk/unlock, roster, verify-pin, attendance/check, reenroll-face` | 🟠 Fase 3 |
| **Attendance** (5) | `/attendance/check, me, today, team, justify` | 🟢 Fase 4 |
| **Novelties** (4) | `/novelties` (CRUD + bulk-decide) | 🟢 Fase 4 |
| **Reports/Stats** (3) | `/stats/dashboard, reports, reports/export` | 🟢 Fase 4 |
| **Onboarding** (1) | `/onboarding/selfie` | 🟠 Fase 3 |
| **Root** (1) | `/` health | — |

**Migración backend**: prácticamente COPY-PASTE. Solo hay que:
1. Copiar `server.py`, `.env` (con MONGO_URL nuevo), `requirements.txt`.
2. Verificar que el CORS acepte el dominio productivo del Next.
3. Configurar el prefix `/api` en el ingress del nuevo proyecto.

### Frontend actual (`/app/frontend/` — 7637 líneas TypeScript)

| Archivo actual (Expo) | Archivo destino (Next.js) | Líneas | Complejidad |
|---|---|---|---|
| `app/index.tsx` (login) | `app/(auth)/login/page.tsx` | 357 | 🟢 Baja |
| `app/onboarding.tsx` | `app/onboarding/page.tsx` | 328 | 🟡 Media (usa cámara) |
| `app/_layout.tsx` | `app/layout.tsx` (root) | 21 | 🟢 Baja |
| `app/+html.tsx` | *(no aplica en Next.js)* | 57 | — |
| `app/(tabs)/_layout.tsx` | `app/(app)/layout.tsx` (nav bar) | 80 | 🟡 Media |
| `app/(tabs)/home.tsx` (carnet) | `app/(app)/carnet/page.tsx` | 602 | 🟡 Media |
| `app/(tabs)/history.tsx` | `app/(app)/historial/page.tsx` | 119 | 🟢 Baja |
| `app/(tabs)/novelties.tsx` | `app/(app)/novedades/page.tsx` | 192 | 🟢 Baja |
| `app/(tabs)/reports.tsx` | `app/(app)/reportes/page.tsx` | 154 | 🟢 Baja |
| `app/(tabs)/team.tsx` | `app/(app)/equipo/page.tsx` | 162 | 🟢 Baja |
| `app/(tabs)/admin.tsx` ⚠ | `app/(admin)/*/page.tsx` **DIVIDIDO** | 2105 | 🔴 Alta (mucho refactor) |
| `app/dashboard.tsx` | `app/(admin)/dashboard/page.tsx` | 590 | 🟡 Media |
| `app/kiosk.tsx` | `app/kiosk/page.tsx` | 823 | 🔴 Alta (cámara + face-api) |
| `src/auth/AuthContext.tsx` | `lib/auth/*.ts` + middleware | 266 | 🟡 Media |
| `src/utils/faceMatch.ts` | `lib/faceMatch.ts` | 277 | 🟢 Baja (copy-paste) |
| `src/theme.ts` | `tailwind.config.ts` + globals.css | — | 🟢 Baja |
| `src/utils/storage/*` | *(reemplazado por cookies)* | — | — |

**Total**: ~13 pantallas, ~7500 líneas de UI a reescribir.

---

## 🗓 Plan de migración por fases

### Fase 0 — Setup (0.5 día)
- [ ] Crear proyecto **Full Stack** nuevo en Emergent (**el usuario debe hacer este paso** desde el dashboard).
- [ ] Setup Next.js 15 + Tailwind + shadcn/ui inicial.
- [ ] Copiar `/app/backend/` completo al nuevo proyecto.
- [ ] Configurar MongoDB en el nuevo proyecto (Emergent lo hará automático).
- [ ] Migrar datos de la BD actual (opcional: usar `mongodump`/`mongorestore` o rehacer desde CSV).
- [ ] Configurar `.env` con el nuevo `NEXT_PUBLIC_BACKEND_URL`.

### Fase 1 — Auth + Users (1.5 días)
- [ ] Login/logout con **cookies HTTP-only** (más seguro que localStorage actual).
- [ ] Middleware Next.js para proteger rutas por rol (`/admin/*`, `/kiosk`, `/carnet`).
- [ ] Página **Login** (`/login`) responsive.
- [ ] Página **Onboarding** con cámara (`getUserMedia`) para primera selfie.
- [ ] Contexto/hooks: `useAuth`, `useUser`.
- [ ] Admin — Gestión de usuarios (crear en un solo paso, editar, eliminar, resetear password, import CSV).

### Fase 2 — Config maestra (1 día)
- [ ] Admin — Sites (CRUD con resolve-link de Google Maps).
- [ ] Admin — Departments (CRUD).
- [ ] Admin — Schedules (CRUD con intervalos de 30min).
- [ ] Admin — Company Settings (identification_method, kiosk_enabled, timezone, logo).

### Fase 3 — Modo Kiosco + Carnet (1.5 días)
- [ ] Página **`/kiosk`**: lock screen + main screen con cámara, face-api desde CDN.
- [ ] Panel de diagnóstico técnico (ya diseñado).
- [ ] Modal de re-enrolamiento con PIN + cámara propia.
- [ ] Página **`/carnet`** (ex home): tarjeta digital con foto, nombre, sede.
- [ ] Selfie replacement flow (`/onboarding?replace=1` → nuevo flujo Next).

### Fase 4 — Reportería + Team + Novedades (1 día)
- [ ] Página **`/historial`** — listado propio.
- [ ] Página **`/novedades`** — crear + listar.
- [ ] Página **`/reportes`** — solo admin/supervisor con export.
- [ ] Página **`/equipo`** — solo supervisor.
- [ ] Página **`/dashboard`** — SVG charts (con Recharts) + bulk actions.

### Fase 5 — PWA + Deploy productivo (0.5 día)
- [ ] `manifest.webmanifest` con íconos.
- [ ] Service worker (via `next-pwa`) con caching de rutas.
- [ ] Install prompt personalizado.
- [ ] Testing en iOS Safari + Android Chrome.
- [ ] Deploy en Emergent → URL productiva estable.

**⏱ Total estimado: 5-6 días de trabajo intensivo**.

---

## 🎨 Decisiones de diseño y patrones a mantener

### Del proyecto actual (bueno, conservar)
- ✅ Tema corporativo suave (blanco, azul suave, gris, verde/rojo/amarillo semánticos).
- ✅ Timezone GMT-4 (Caracas) en toda la app.
- ✅ Estructura de roles: admin / supervisor / employee.
- ✅ Endpoints RESTful con prefix `/api`.
- ✅ JWT en Authorization header (aunque en Next.js iremos a **cookies HTTP-only**).
- ✅ face-api.js@0.22.2 cargado desde CDN (evita el bug de bundler).

### Nuevo (aprovechar la migración)
- 🆕 **Data tables** con filtros/sort/paginación real (shadcn/ui DataTable) — hoy son listas simples.
- 🆕 **Server components** para dashboard admin — carga inicial más rápida.
- 🆕 **Optimistic updates** con SWR/TanStack Query.
- 🆕 **Focus visible / accesibilidad** con shadcn/ui.
- 🆕 **Dark mode** opcional (Tailwind lo soporta trivialmente).
- 🆕 **Toast notifications** persistentes con `sonner`.

---

## 🗄 Migración de datos existente

Al crear el proyecto nuevo en Emergent, la BD MongoDB también será nueva. Opciones para no perder los datos actuales:

### Opción A — `mongodump` + `mongorestore` (recomendado)
```bash
# En el proyecto actual (dump)
mongodump --uri="$MONGO_URL" --out=/tmp/dump

# En el proyecto nuevo (restore)
mongorestore --uri="$NEW_MONGO_URL" /tmp/dump
```

### Opción B — Exportar a CSV y re-importar
- Los usuarios podrían re-importarse usando el CSV wizard ya construido.
- Asistencia histórica se perdería — pero como es solo para testing, quizás no importa.

### Opción C — Empezar limpio
- Nueva BD vacía.
- Bootstrap del primer admin.
- Todo lo demás se carga fresco.

**Mi recomendación**: **Opción A** (mongodump) para conservar los datos que ya tienes.

---

## 📦 Estructura de directorios propuesta para el nuevo proyecto

```
new-project/
├── backend/
│   ├── server.py                # Copy-paste del actual
│   ├── requirements.txt         # Copy-paste
│   ├── tests/                   # Copy-paste
│   └── .env                     # Con nuevo MONGO_URL
│
├── frontend/                    # Next.js
│   ├── app/
│   │   ├── layout.tsx           # Root layout
│   │   ├── globals.css          # Tailwind + tokens
│   │   ├── page.tsx             # Landing / redirect
│   │   ├── (auth)/
│   │   │   ├── layout.tsx
│   │   │   └── login/page.tsx
│   │   ├── onboarding/page.tsx
│   │   ├── kiosk/page.tsx       # No requiere auth de employee (solo admin unlock)
│   │   ├── (app)/               # Rutas para usuarios logueados
│   │   │   ├── layout.tsx       # Nav bar inferior
│   │   │   ├── carnet/page.tsx
│   │   │   ├── historial/page.tsx
│   │   │   ├── novedades/page.tsx
│   │   │   ├── reportes/page.tsx
│   │   │   └── equipo/page.tsx
│   │   └── (admin)/             # Rutas solo para admin
│   │       ├── layout.tsx       # Sidebar
│   │       ├── dashboard/page.tsx
│   │       ├── usuarios/page.tsx
│   │       ├── sedes/page.tsx
│   │       ├── departamentos/page.tsx
│   │       ├── horarios/page.tsx
│   │       ├── ajustes/page.tsx
│   │       └── importar/page.tsx
│   ├── components/
│   │   ├── ui/                  # shadcn/ui components
│   │   ├── camera-capture.tsx   # Reemplaza expo-camera
│   │   ├── face-diagnostic.tsx
│   │   ├── kiosk-*.tsx
│   │   └── nav-bar.tsx
│   ├── lib/
│   │   ├── auth/
│   │   │   ├── session.ts       # Session helpers (cookies)
│   │   │   ├── middleware.ts    # Route protection
│   │   │   └── use-auth.ts
│   │   ├── face-match.ts        # Copy-paste con adaptaciones
│   │   └── api-client.ts        # Wrapper de fetch
│   ├── middleware.ts            # Next middleware (rol-based)
│   ├── next.config.mjs
│   ├── tailwind.config.ts
│   ├── package.json
│   └── .env.local
│
└── README.md
```

---

## ⚠️ Riesgos y consideraciones

| Riesgo | Mitigación |
|---|---|
| Migración parcial (nos quedamos a medias) | Fases atómicas, cada una entregable independiente |
| Pérdida de datos actuales | Backup con `mongodump` antes de migrar |
| Bugs en el nuevo código | Testing por fase con `testing_agent` |
| Costo de créditos | Trabajo por fases con hitos claros; puedes pausar en cualquier momento |
| Este proyecto queda "colgado" | Recomendación: mantenerlo apagado o pausado tras completar migración |

---

## ✅ Pasos siguientes (para el usuario)

1. **Revisar este blueprint** y aprobar el enfoque técnico.
2. Desde el dashboard de Emergent, **crear un proyecto NUEVO** de tipo:
   - `Full Stack App` o
   - `Web / PWA` o
   - `Next.js` (según cómo lo llame Emergent en su UI actual)
3. Compartir el link del nuevo proyecto con el agente asignado.
4. El agente del nuevo proyecto **debe recibir este blueprint** como contexto inicial.
5. Backup opcional de la BD actual (te ayudo con `mongodump` antes de que apagues este preview).

---

## 🤝 Compromiso del agente

- Cada fase se entrega funcional y testeada.
- No se avanza a la siguiente fase sin validación tuya.
- El backend se copia sin modificaciones para no romper la lógica actual.
- El look & feel corporativo suave se conserva (con mejoras).
- La face-api.js sigue funcionando exactamente igual.
