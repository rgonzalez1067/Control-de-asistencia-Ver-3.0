#!/usr/bin/env bash
# =====================================================================
# MegaSoft Asistencia — Carga seed inicial (admin bootstrap)
# =====================================================================
# Uso local con docker-compose:
#   ./seed/load-seed.sh
# Uso con backend directo (sin docker):
#   API_URL=https://tu-dominio.com ./seed/load-seed.sh
#
# El script:
#   1. Detecta si la BD ya tiene un admin (endpoint /auth/needs-bootstrap).
#   2. Si NO tiene admin, registra el primer admin usando /auth/register.
#   3. Si YA tiene admin, sale sin hacer nada.
# =====================================================================
set -euo pipefail

API_URL="${API_URL:-http://localhost}"
ADMIN_EMAIL="${ADMIN_EMAIL:-rgonzalez@megasoft.com.ve}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-admin123}"
ADMIN_NAME="${ADMIN_NAME:-Rafael González}"

echo "→ Verificando estado de bootstrap en $API_URL ..."
needs=$(curl -sS "$API_URL/api/auth/needs-bootstrap" | grep -o '"needs_bootstrap":[^,}]*' | cut -d: -f2 | tr -d ' ')

if [ "$needs" != "true" ]; then
  echo "✔ Ya existe un admin. No se realizan cambios."
  exit 0
fi

echo "→ No hay admin todavía. Creando '$ADMIN_EMAIL' ..."
response=$(curl -sS -X POST "$API_URL/api/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PASSWORD\",\"name\":\"$ADMIN_NAME\"}")

echo "✔ Admin creado."
echo "  Email:    $ADMIN_EMAIL"
echo "  Password: $ADMIN_PASSWORD"
echo ""
echo "⚠️  IMPORTANTE: entra al sistema y cambia la contraseña de inmediato desde"
echo "   Menú de usuario → Cambiar contraseña."
