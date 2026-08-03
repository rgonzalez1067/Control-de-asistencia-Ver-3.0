# Seed inicial — MegaSoft Asistencia

Esta carpeta contiene los archivos necesarios para inicializar la base de datos
de un ambiente nuevo con un usuario administrador.

## Archivos

| Archivo | Uso |
|---|---|
| `admin-seed.json` | Backup JSON compatible con `/api/admin/import`. Contiene 1 admin. |
| `load-seed.sh` | Script para crear el primer admin automáticamente al arranque. |

## Método recomendado · Script automático

Después de `docker compose up -d` y de que el backend esté arriba:

```bash
chmod +x seed/load-seed.sh
./seed/load-seed.sh
```

Salida esperada:

```
→ Verificando estado de bootstrap en http://localhost ...
→ No hay admin todavía. Creando 'rgonzalez@megasoft.com.ve' ...
✔ Admin creado.
  Email:    rgonzalez@megasoft.com.ve
  Password: admin123
```

Si ya existe un admin, el script sale sin cambios.

### Personalizar credenciales

```bash
API_URL="https://gestor.megasoft.com.ve" \
ADMIN_EMAIL="admin@empresa.com" \
ADMIN_PASSWORD="MiClaveSegura2026!" \
ADMIN_NAME="Administrador de Sistemas" \
./seed/load-seed.sh
```

## Método alternativo · Import JSON desde Ajustes

1. Entra al sistema como cualquier usuario admin (por ejemplo el creado con `.env`).
2. Ve a **Ajustes → Copia de seguridad**.
3. Presiona **Importar backup** y sube `admin-seed.json`.
4. Modo **Upsert** — no borra datos existentes.

## Método alternativo · Variables de entorno

Al arranque del backend, si `ADMIN_EMAIL` y `ADMIN_PASSWORD` están en `backend/.env`
y no existe un admin con ese email, se crea automáticamente. Ya viene incluido
en el `.env.example`.

---

## ⚠️ Seguridad

- **Cambia la contraseña `admin123` de inmediato** al primer login desde el menú
  de usuario → Cambiar contraseña.
- El hash del `admin-seed.json` es bcrypt y **no puede revertirse a la contraseña
  original**, pero cualquiera con acceso al archivo puede crear un admin con esa
  clave si aún es válida.
- Para ambientes de producción, considera regenerar el seed con una contraseña
  única (ver siguiente sección).

## Regenerar el seed con nueva contraseña

Desde dentro del contenedor backend:

```bash
docker exec -it megasoft-backend python -c "
import bcrypt, json, datetime
password = input('Nueva contraseña admin: ')
seed = {
  'app':'megasoft-asistencia',
  'generated_at': datetime.datetime.utcnow().isoformat()+'Z',
  'collections': {'users': [{
    'user_id':'user_admin_seed',
    'name':'Rafael González',
    'email':'rgonzalez@megasoft.com.ve',
    'role':'admin',
    'password_hash': bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(),
    'onboarded': False, 'active': True,
    'department_id': None, 'site_id': None, 'schedule_id': None,
    'created_at': datetime.datetime.utcnow().isoformat()+'Z',
  }]}
}
print(json.dumps(seed, indent=2, ensure_ascii=False))
" > seed/admin-seed.json
```
