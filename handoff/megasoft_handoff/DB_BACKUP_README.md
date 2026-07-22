# 💾 Backup de la BD — MegaSoft Asistencia

**Fecha del backup**: Julio 2026
**Origen**: proyecto Mobile/Expo actual (`attendance-mobile-3`)
**Destino**: proyecto Full Stack Web/PWA nuevo (a crear)

---

## 📊 Resumen del contenido

| Colección | Documentos |
|---|---|
| `users` | 17 |
| `attendance` | 80 |
| `departments` | 15 |
| `schedules` | 5 |
| `sites` | 2 |
| `settings` | 1 |
| `novelties` | 8 |
| `user_sessions` | 0 |

**Total tamaño BSON**: 7.1 MB
**Total tamaño JSON**: 7.5 MB
**Comprimido (`.tar.gz`)**: 12 MB

Todos los `password_hash` (bcrypt) están **preservados intactos en el BSON** — al restaurar, los usuarios podrán loguearse con las mismas contraseñas que tenían.

En el `users.sanitized.json` los hashes están reemplazados por `<REDACTED>` para poder compartir de forma segura si se necesita revisar el esquema sin exponer credenciales.

---

## 📁 Estructura del backup

```
/app/memory/
├── db_backup.tar.gz              # Backup comprimido — LO IMPORTANTE
└── db_backup/
    ├── dump/                     # Formato binario BSON (para mongorestore)
    │   └── test_database/
    │       ├── users.bson (+ metadata)
    │       ├── attendance.bson
    │       ├── departments.bson
    │       ├── schedules.bson
    │       ├── sites.bson
    │       ├── settings.bson
    │       ├── novelties.bson
    │       ├── user_sessions.bson
    │       └── prelude.json
    └── json/                     # Formato JSON legible (respaldo alterno)
        ├── users.json
        ├── users.sanitized.json  # Sin hashes de contraseñas
        ├── attendance.json
        ├── departments.json
        ├── schedules.json
        ├── sites.json
        ├── settings.json
        ├── novelties.json
        └── user_sessions.json
```

---

## 🔄 Cómo restaurar en el proyecto NUEVO

### Opción A: `mongorestore` (recomendado — más rápido y fiel)

Una vez tengas el proyecto nuevo creado y su `MONGO_URL` disponible:

```bash
# 1. Descomprimir el backup en el proyecto nuevo
cd /app  # o donde esté el proyecto nuevo
tar xzf /ruta/al/db_backup.tar.gz

# 2. Restaurar a la nueva BD
NEW_MONGO_URL="mongodb://localhost:27017"  # El MONGO_URL del proyecto nuevo
NEW_DB_NAME="attendance_prod"              # O el que uses en producción

mongorestore \
  --uri="$NEW_MONGO_URL" \
  --nsInclude="test_database.*" \
  --nsFrom="test_database.*" \
  --nsTo="$NEW_DB_NAME.*" \
  ./db_backup/dump

# 3. Verificar
mongo --eval "db.getSiblingDB('$NEW_DB_NAME').users.countDocuments({})"
# Debería devolver 17
```

### Opción B: Restore desde JSON (si `mongorestore` no está disponible)

```bash
NEW_DB_NAME="attendance_prod"

for col in users attendance departments schedules sites settings novelties user_sessions; do
  mongoimport \
    --uri="$NEW_MONGO_URL" \
    --db="$NEW_DB_NAME" \
    --collection="$col" \
    --file="./db_backup/json/${col}.json" \
    --jsonArray \
    --drop  # ⚠ borra la colección antes de importar
done
```

### Opción C: Restore programático con Python + motor

Útil si el nuevo proyecto quiere una migración más controlada (ej. renombrar campos, filtrar datos, etc.):

```python
import asyncio, json, os
from motor.motor_asyncio import AsyncIOMotorClient

async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client["attendance_prod"]
    for col in ["users", "attendance", "departments", "schedules",
                "sites", "settings", "novelties"]:
        with open(f"./db_backup/json/{col}.json") as f:
            docs = json.load(f)
        if docs:
            await db[col].insert_many(docs)
            print(f"  {col}: {len(docs)} docs")

asyncio.run(main())
```

---

## 🔐 Contraseñas de acceso conocidas

Estas se conservan intactas al restaurar (bcrypt hash en `password_hash`):

- **Admin**: `rgonzalez@megasoft.com.ve` / `admin123`
- Ver `/app/memory/test_credentials.md` para más credenciales de prueba si existieran.

---

## ⚠️ Cosas a tener en cuenta al restaurar

1. **Campo `_id` de MongoDB**: los BSON conservan los ObjectId originales. Si por alguna razón hay conflicto (colección ya existente), usa `--drop` en mongorestore o borra colecciones antes.

2. **Campo `user_id`**: es un string generado por la app (ej. `user_641b181ceb84`), NO el `_id` de Mongo. Se conserva 1:1.

3. **Selfies en base64**: los `selfie_base64` están dentro de `users.bson` (~90 KB cada uno). Por eso el backup pesa 7 MB — es normal.

4. **Face descriptors**: los `face_descriptor` (arrays de 128 floats) se conservan. Si el nuevo proyecto usa una versión distinta de face-api.js (por ejemplo `@vladmandic/face-api`), los descriptores podrían no ser 100% compatibles — pero como planeamos usar la misma versión desde CDN, deberían funcionar perfecto.

5. **Timezone**: los `timestamp` de `attendance` están en UTC (`tz_aware=True` en Motor). La conversión a GMT-4 se hace en el frontend.

6. **Zona de seguridad**: NO subas este backup a GitHub público — contiene hashes de contraseñas + imágenes personales de empleados.

---

## 📤 Cómo transferir el backup al proyecto nuevo

Como los dos proyectos de Emergent son contenedores separados, tienes 3 opciones:

### Opción 1 (más simple): descargar y subir
1. Descarga `/app/memory/db_backup.tar.gz` (12 MB) desde este proyecto — puedes usar el explorador de archivos del IDE de Emergent, o dile al agente actual que te lo empaquete para descarga.
2. Súbelo al nuevo proyecto en `/app/backend/` o donde te lo pida el agente nuevo.
3. Ejecutas `tar xzf db_backup.tar.gz` y luego `mongorestore` como se explicó arriba.

### Opción 2: usar un almacenamiento intermedio (S3, Drive, WeTransfer)
1. Sube el `.tar.gz` a Google Drive / WeTransfer / S3.
2. En el proyecto nuevo, dile al agente: "descarga `<URL>` con `curl` en `/tmp/db_backup.tar.gz` y restaura la BD".

### Opción 3: copy-paste de los JSON (para BDs pequeñas)
Los `.json` de `/app/memory/db_backup/json/` se pueden copiar-pegar en el agente del proyecto nuevo, pero el `users.json` y `attendance.json` son grandes (~5 MB), así que no es lo ideal.

**Mi recomendación: Opción 1 o 2**.

---

## ✅ Checklist para el usuario

- [ ] Confirmar que el backup se generó (**hecho, este documento**).
- [ ] Descargar `/app/memory/db_backup.tar.gz` antes de apagar este proyecto.
- [ ] Crear el proyecto nuevo en Emergent (Full Stack Web/PWA).
- [ ] Compartir el link del proyecto nuevo + este blueprint + este backup con el agente asignado.
- [ ] Restaurar la BD siguiendo la Opción A (mongorestore).
- [ ] Verificar login con `rgonzalez@megasoft.com.ve` / `admin123`.
- [ ] Arrancar Fase 0 del blueprint de migración.
