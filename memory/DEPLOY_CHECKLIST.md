# Deploy checklist — MegaSoft Asistencia Web/PWA

## ✅ Pre-deploy (ya cumplido)
- Backend prefijado con `/api` para el ingress Kubernetes
- `REACT_APP_BACKEND_URL` leído desde `.env` (no hardcoded)
- `MONGO_URL` y `DB_NAME` leídos desde `.env`
- CORS abierto con `allow_origins='*'` y credentials desactivados
- Manifest PWA (`/manifest.webmanifest`) con íconos 192/512 SVG
- Service Worker en `/sw.js` (cacheo del app-shell, nunca /api)
- Meta `theme-color` y `apple-touch-icon`
- Instalación PWA vía `beforeinstallprompt` (`InstallPWAPrompt.jsx`)
- Sin claves hardcoded en el frontend
- Todos los endpoints probados (49/49 pytest)
- Credenciales de admin en `/app/memory/test_credentials.md`

## 🔄 Al desplegar
1. Verifica que `REACT_APP_BACKEND_URL` en producción apunta al dominio real
2. Confirma que la BD de producción tenga:
   - El admin seed (bootstrap automático desde `startup`)
   - Timezone (`APP_TIMEZONE`) según empresa
3. Verifica que `JWT_SECRET` fue rotado con `secrets.token_hex(48)` para prod

## 📱 Testing manual iOS / Android
- **iOS Safari (iPhone/iPad)**:
  - Menú "Compartir" → "Añadir a pantalla de inicio" → verificar ícono e inicio en modo standalone
  - Verifica que la cámara pide permisos (onboarding y kiosco)
  - Comprueba tarjeta `carnet` y la marca de asistencia
- **Android Chrome/Samsung Internet**:
  - Debería dispararse `beforeinstallprompt` → el prompt custom aparece → "Instalar"
  - Alternativa: menú "Instalar app"
  - Verifica reconocimiento facial en `/kiosk/scan` con face-api en device real
- **Desktop Chrome/Edge**:
  - Ícono de instalación en la barra de URL → "Instalar MegaSoft"
  - Verifica que el service worker aparece en DevTools → Application → Service Workers

## 🚀 Post-deploy
- Ejecuta `GET /api/` en la URL productiva → debe responder `{status:"ok"}`
- Loguéate como admin en la URL productiva y verifica dashboard, reportes, equipo, novedades
- Verifica que el manifest carga: `curl -sI https://tu-dominio/manifest.webmanifest`
- Verifica que el SW carga: `curl -sI https://tu-dominio/sw.js`
- Lighthouse: verifica score PWA (target ≥ 90)

## 🔐 Endurecimiento (opcional, post-MVP)
- Rate limiting en `/api/auth/login` (protección brute-force)
- Content Security Policy (CSP) más estricta
- Rotación de JWT + refresh token
- Bcrypt cost ≥ 12 (ya está en 12)
- Logs estructurados a Sentry o similar
- Backup automatizado de MongoDB
