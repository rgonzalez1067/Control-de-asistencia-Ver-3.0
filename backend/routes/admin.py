"""Endpoints administrativos: Backup / Restore de colecciones + Onboarding selfie
   + Security Bootstrap (one-time init de contraseña admin y token de bóveda).

Migrado desde server.py durante la Fase A · Iteración 3 (feb-2026).
Iteración de seguridad (feb-2026): backup ampliado + X-Admin-Token en export/import/collections.
Iteración de deploy (feb-2026): security bootstrap idempotente para inicializar
producción sin editar `.env` (evita rotar el token en un dashboard).
"""
import json
import os
import secrets
from bson import ObjectId

from deps import (
    api, db, get_current_user, require_roles,
    now_utc,
    hash_password, verify_password,
    SelfieIn,
    HTTPException, Depends, UploadFile, File, Request,
    StreamingResponse,
    Any, Dict, List, Optional,
    datetime,
    audit_log,
)
from pydantic import BaseModel, Field


# ==================================================================
# BACKUP / RESTORE (admin only) — protegido con doble factor:
# JWT admin + header X-Admin-Token (ADMIN_VAULT_TOKEN en .env o vault_token_hash en DB).
# ==================================================================
# Colecciones exportables. Se AMPLIÓ (feb-2026) para incluir todo:
#   - access_profiles      → catálogos RBAC (perfiles y permisos por menú)
#   - attendance           → historial completo de marcajes
#   - schedule_assignments → asignaciones diarias (turnos rotativos)
#   - assignment_plans     → planes de asignación (rango de fechas)
EXPORTABLE_COLLECTIONS = [
    "users", "sites", "departments", "schedules",
    "novelties", "visits", "settings",
    "access_profiles", "attendance",
    "schedule_assignments", "assignment_plans",
]


async def _verify_vault_token(provided: str) -> bool:
    """Compara `provided` contra dos fuentes en cascada:
    1) Variable de entorno `ADMIN_VAULT_TOKEN` (útil en preview/desarrollo).
    2) `settings.vault_token_hash` en MongoDB (útil en producción tras bootstrap).
    Devuelve True si coincide contra alguna."""
    if not provided:
        return False
    env_token = os.environ.get("ADMIN_VAULT_TOKEN", "")
    if env_token and secrets.compare_digest(provided, env_token):
        return True
    doc = await db.settings.find_one({"_id": "company"}, {"vault_token_hash": 1})
    stored_hash = (doc or {}).get("vault_token_hash", "")
    if stored_hash and verify_password(provided, stored_hash):
        return True
    return False


async def require_admin_vault(request: Request,
                              _: Dict[str, Any] = Depends(require_roles("admin"))) -> None:
    """Doble autenticación: además del JWT admin, exige un header
    ``X-Admin-Token`` que sólo el admin conoce fuera-de-banda. La verificación
    consulta primero la variable de entorno ``ADMIN_VAULT_TOKEN`` y luego el
    hash guardado en ``settings.vault_token_hash`` (útil en producción)."""
    provided = request.headers.get("X-Admin-Token", "")
    if not await _verify_vault_token(provided):
        # ¿Está configurado en algún lado?
        env_token = os.environ.get("ADMIN_VAULT_TOKEN", "")
        doc = await db.settings.find_one({"_id": "company"}, {"vault_token_hash": 1})
        has_any = bool(env_token) or bool((doc or {}).get("vault_token_hash"))
        if not has_any:
            raise HTTPException(status_code=503,
                                detail="Vault administrativo no configurado. Ejecuta /api/admin/security/bootstrap.")
        raise HTTPException(status_code=403,
                            detail="Se requiere el token de bóveda administrativa (X-Admin-Token)")


# ==================================================================
# SECURITY BOOTSTRAP (one-time init de admin password + vault token)
# ==================================================================
class SecurityBootstrapIn(BaseModel):
    admin_password: str = Field(..., min_length=8, max_length=128)
    vault_token: str = Field(..., min_length=16, max_length=128)


@api.get("/admin/security/status")
async def admin_security_status(
    user: Dict[str, Any] = Depends(require_roles("admin")),
) -> Dict[str, Any]:
    """Devuelve el estado del bootstrap de seguridad para que la UI decida si
    debe mostrar el wizard obligatorio de configuración."""
    doc = await db.settings.find_one({"_id": "company"},
                                     {"security_bootstrapped": 1, "vault_token_hash": 1,
                                      "security_bootstrapped_at": 1}) or {}
    env_vault_present = bool(os.environ.get("ADMIN_VAULT_TOKEN"))
    return {
        "bootstrapped": bool(doc.get("security_bootstrapped")),
        "has_vault": env_vault_present or bool(doc.get("vault_token_hash")),
        "vault_source": ("env" if env_vault_present else
                         ("db" if doc.get("vault_token_hash") else None)),
        "admin_email": user.get("email"),
        "bootstrapped_at": (doc.get("security_bootstrapped_at").isoformat()
                            if doc.get("security_bootstrapped_at") else None),
    }


@api.post("/admin/security/bootstrap")
async def admin_security_bootstrap(
    request: Request,
    payload: SecurityBootstrapIn,
    user: Dict[str, Any] = Depends(require_roles("admin")),
) -> Dict[str, Any]:
    """Endpoint IDEMPOTENTE que sólo se puede ejecutar una vez por instancia.
    Configura la seguridad en producción sin necesidad de editar `.env`:
      1. Rota la contraseña del admin actual al valor recibido.
      2. Guarda el hash bcrypt del ``vault_token`` en ``settings.vault_token_hash``.
      3. Marca ``settings.security_bootstrapped=true`` (así nunca se re-ejecuta).
      4. Marca ``must_change_password=true`` en TODOS los empleados no-admin/no-kiosk.
      5. Registra el evento en ``audit_log``.
    """
    settings_doc = await db.settings.find_one({"_id": "company"}) or {}
    if settings_doc.get("security_bootstrapped"):
        raise HTTPException(status_code=409,
                            detail="El bootstrap de seguridad ya fue ejecutado. "
                                   "Usa el endpoint de rotación si necesitas cambiar el vault.")

    # 1) Rotar contraseña admin
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {
            "password_hash": hash_password(payload.admin_password),
            "must_change_password": False,
            "password_updated_at": now_utc(),
            "password_updated_by_user": True,
        }},
    )
    # 2) Guardar hash del vault token
    vault_hash = hash_password(payload.vault_token)
    # 3) Marcar bootstrap
    now = now_utc()
    await db.settings.update_one(
        {"_id": "company"},
        {"$set": {
            "vault_token_hash": vault_hash,
            "security_bootstrapped": True,
            "security_bootstrapped_at": now,
            "security_bootstrapped_by": user["user_id"],
        }},
        upsert=True,
    )
    # 4) Force must_change_password sobre empleados no-admin/no-kiosk
    forced = await db.users.update_many(
        {"role": {"$nin": ["admin", "kiosk"]}},
        {"$set": {"must_change_password": True, "password_updated_at": now}},
    )
    # 5) Audit
    await audit_log("security_bootstrap", request,
                    user_id=user["user_id"], email=user.get("email"),
                    extra={"forced_password_resets": forced.modified_count})
    return {
        "ok": True,
        "message": "Seguridad inicializada correctamente. Guarda el vault token en un lugar seguro.",
        "admin_password_rotated": True,
        "vault_token_saved": True,
        "employees_forced_reset": forced.modified_count,
        "bootstrapped_at": now.isoformat(),
    }


@api.post("/admin/security/generate-vault-token")
async def admin_security_generate_token(
    _: Dict[str, Any] = Depends(require_roles("admin")),
) -> Dict[str, str]:
    """Genera un vault token aleatorio criptográficamente fuerte que el admin
    puede usar en el paso bootstrap (o rotación futura). NO se persiste — es
    responsabilidad del cliente enviarlo luego a `/security/bootstrap`."""
    return {"vault_token": secrets.token_urlsafe(32)}


def _serialize_doc(d: Dict[str, Any]) -> Dict[str, Any]:
    """Convierte tipos no-JSON (datetime, ObjectId) a strings."""
    out = {}
    for k, v in d.items():
        if isinstance(v, datetime):
            out[k] = v.isoformat()
        elif isinstance(v, ObjectId):
            out[k] = str(v)
        elif isinstance(v, list):
            out[k] = [_serialize_doc(i) if isinstance(i, dict) else i for i in v]
        elif isinstance(v, dict):
            out[k] = _serialize_doc(v)
        else:
            out[k] = v
    return out


@api.get("/admin/collections", include_in_schema=False)
async def admin_collections(_: None = Depends(require_admin_vault)) -> List[Dict[str, Any]]:
    """Lista colecciones exportables con conteo de documentos."""
    out = []
    for name in EXPORTABLE_COLLECTIONS:
        n = await db[name].count_documents({})
        out.append({"name": name, "count": n})
    return out


@api.post("/admin/export", include_in_schema=False)
async def admin_export(request: Request, payload: Dict[str, Any],
                       _: None = Depends(require_admin_vault)) -> StreamingResponse:
    """Exporta las colecciones seleccionadas como JSON."""
    selected = payload.get("collections") or []
    selected = [c for c in selected if c in EXPORTABLE_COLLECTIONS]
    if not selected:
        raise HTTPException(status_code=400, detail="Selecciona al menos una colección")
    dump: Dict[str, Any] = {
        "app": "megasoft-asistencia",
        "generated_at": now_utc().isoformat(),
        "collections": {},
    }
    total_docs = 0
    for name in selected:
        docs = await db[name].find({}).to_list(200000)
        dump["collections"][name] = [_serialize_doc(d) for d in docs]
        total_docs += len(docs)
    payload_bytes = json.dumps(dump, ensure_ascii=False, indent=2).encode("utf-8")
    ts = now_utc().strftime("%Y%m%d_%H%M%S")
    filename = f"megasoft-backup-{ts}.json"
    await audit_log("admin_export", request,
                    extra={"collections": selected, "total_docs": total_docs,
                           "bytes": len(payload_bytes)})
    return StreamingResponse(
        iter([payload_bytes]),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@api.post("/admin/import", include_in_schema=False)
async def admin_import(request: Request,
                       file: UploadFile = File(...),
                       mode: str = "upsert",
                       collections: Optional[str] = None,
                       _: None = Depends(require_admin_vault)) -> Dict[str, Any]:
    """Importa un backup JSON.
    - mode='upsert' (por defecto): inserta o actualiza según llave natural.
    - mode='replace': elimina todos los documentos existentes de esa colección y reemplaza.
    - collections: lista separada por comas para restaurar solo ciertas colecciones.
    """
    if mode not in {"upsert", "replace"}:
        raise HTTPException(status_code=400, detail="mode debe ser 'upsert' o 'replace'")
    raw = await file.read()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"JSON inválido: {e}")
    if not isinstance(payload, dict) or "collections" not in payload:
        raise HTTPException(status_code=400, detail="Archivo no reconocido")

    filter_list = set()
    if collections:
        filter_list = {c.strip() for c in collections.split(",") if c.strip()}

    # llave natural por colección para upsert
    NAT_KEYS = {
        "users": "user_id", "sites": "site_id", "departments": "department_id",
        "schedules": "schedule_id", "novelties": "novelty_id",
        "visits": "visit_id", "settings": "_id",
        "access_profiles": "profile_id",
        "attendance": "record_id",
        "schedule_assignments": "assignment_id",
        "assignment_plans": "plan_id",
    }
    summary: Dict[str, Any] = {"restored": {}, "skipped": {}, "mode": mode}
    for name, docs in (payload.get("collections") or {}).items():
        if name not in EXPORTABLE_COLLECTIONS:
            summary["skipped"][name] = "colección no permitida"
            continue
        if filter_list and name not in filter_list:
            summary["skipped"][name] = "no seleccionada"
            continue
        if not isinstance(docs, list):
            summary["skipped"][name] = "formato inválido"
            continue

        # Limpia campos no reinsertables y convierte ISO string → datetime en campos de tiempo
        cleaned = []
        for d in docs:
            if not isinstance(d, dict):
                continue
            doc = dict(d)
            doc.pop("_id", None)  # deja que Mongo asigne uno nuevo si es replace
            for tk in ("created_at", "updated_at", "decided_at", "exit_at", "timestamp"):
                if tk in doc and isinstance(doc[tk], str):
                    try:
                        doc[tk] = datetime.fromisoformat(doc[tk].replace("Z", "+00:00"))
                    except Exception:
                        pass
            cleaned.append(doc)

        if mode == "replace":
            await db[name].delete_many({})
            if cleaned:
                await db[name].insert_many(cleaned)
            summary["restored"][name] = len(cleaned)
        else:  # upsert
            key = NAT_KEYS.get(name)
            n_up = 0
            for doc in cleaned:
                if name == "settings":
                    await db.settings.update_one({"_id": "company"}, {"$set": doc}, upsert=True)
                    n_up += 1
                elif key and doc.get(key) is not None:
                    await db[name].update_one({key: doc[key]}, {"$set": doc}, upsert=True)
                    n_up += 1
                else:
                    await db[name].insert_one(doc)
                    n_up += 1
            summary["restored"][name] = n_up

    await audit_log("admin_import", request, extra={"mode": mode, "summary": summary})
    return summary


# ==================================================================
# ONBOARDING (1 endpoint)
# ==================================================================
@api.post("/onboarding/selfie")
async def onboarding_selfie(payload: SelfieIn,
                            user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, bool]:
    updates: Dict[str, Any] = {"selfie_base64": payload.selfie_base64, "onboarded": True}
    if payload.face_descriptor is not None:
        updates["face_descriptor"] = payload.face_descriptor
    await db.users.update_one({"_id": user["_id"]}, {"$set": updates})
    return {"ok": True}



# ==================================================================
# WIPE DATABASE (destructivo, admin only, con doble factor + frase)
# ==================================================================
# Colecciones que se borran completamente. `attendance` incluida — es la razón
# por la que este endpoint se creó (limpiar el entorno para volver a empezar).
_WIPE_COLLECTIONS = [
    "attendance",
    "novelties",
    "visits",
    "schedule_assignments",
    "assignment_plans",
    "schedules",
    "access_profiles",
    "sites",
    "departments",
    "kiosk_sessions",
]
_WIPE_CONFIRMATION_PHRASE = "BORRAR TODO"


class WipeDatabaseIn(BaseModel):
    confirmation_phrase: str = Field(..., min_length=1, max_length=64)


@api.post("/admin/wipe-database", include_in_schema=False)
async def admin_wipe_database(
    request: Request,
    payload: WipeDatabaseIn,
    user: Dict[str, Any] = Depends(require_roles("admin")),
    __: None = Depends(require_admin_vault),
) -> Dict[str, Any]:
    """💥 Borra TODOS los datos operativos del sistema.

    **Preserva** (para que el admin pueda seguir entrando):
      - Su propia cuenta de administrador (`user_id == current admin`).
      - Ajustes de seguridad en `settings`: `vault_token_hash`,
        `security_bootstrapped`, `security_bootstrapped_at`.
      - Colección `audit_log` — el evento del wipe queda registrado.

    **Borra** todo lo demás: usuarios (excepto el admin actual), asistencia,
    novedades, visitas, asignaciones, planes, horarios, perfiles RBAC, sedes,
    departamentos, sesiones de kiosco. También limpia el resto de campos del
    doc `settings` (nombre de empresa, logo, tolerancias, etc.) preservando
    únicamente los campos de seguridad listados arriba.

    Requiere:
      - JWT admin
      - X-Admin-Token válido (bóveda)
      - `confirmation_phrase == "BORRAR TODO"` (mayúsculas exactas).
    """
    if payload.confirmation_phrase.strip() != _WIPE_CONFIRMATION_PHRASE:
        raise HTTPException(
            status_code=400,
            detail=f"Debes escribir exactamente '{_WIPE_CONFIRMATION_PHRASE}' para confirmar.",
        )

    admin_id = user["user_id"]
    admin_email = user.get("email")
    counts: Dict[str, int] = {}

    # 1) Borrar colecciones completas
    for name in _WIPE_COLLECTIONS:
        res = await db[name].delete_many({})
        counts[name] = res.deleted_count

    # 2) Borrar usuarios excepto el admin actual
    res = await db.users.delete_many({"user_id": {"$ne": admin_id}})
    counts["users"] = res.deleted_count

    # 3) Limpiar settings preservando sólo los campos de seguridad
    settings_doc = await db.settings.find_one({"_id": "company"}) or {}
    preserved_keys = {
        "vault_token_hash",
        "security_bootstrapped",
        "security_bootstrapped_at",
        "security_bootstrapped_by",
    }
    preserved = {k: settings_doc[k] for k in preserved_keys if k in settings_doc}
    # Reemplaza el doc entero por uno mínimo con sólo los campos preservados.
    await db.settings.replace_one(
        {"_id": "company"},
        {"_id": "company", **preserved, "wiped_at": now_utc(), "wiped_by": admin_id},
        upsert=True,
    )
    counts["settings_reset"] = 1

    # 4) Audit log del evento
    await audit_log("admin_wipe_database", request, user_id=admin_id, email=admin_email,
                    extra={"deleted": counts, "preserved_admin": admin_id})
    return {
        "ok": True,
        "message": "Base de datos vaciada. Sólo se preservó el admin actual y los ajustes de seguridad.",
        "deleted": counts,
        "preserved_admin": {"user_id": admin_id, "email": admin_email},
    }
