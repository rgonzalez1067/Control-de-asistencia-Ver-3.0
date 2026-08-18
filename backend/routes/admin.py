"""Endpoints administrativos: Backup / Restore de colecciones + Onboarding selfie.

Migrado desde server.py durante la Fase A · Iteración 3 (feb-2026).
"""
import json
from bson import ObjectId

from deps import (
    api, db, get_current_user, require_roles,
    now_utc,
    SelfieIn,
    HTTPException, Depends, UploadFile, File,
    StreamingResponse,
    Any, Dict, List, Optional,
    datetime,
)


# ==================================================================
# BACKUP / RESTORE (admin only)
# ==================================================================
# Colecciones exportables. `attendance` queda excluida por regla del producto.
EXPORTABLE_COLLECTIONS = [
    "users", "sites", "departments", "schedules",
    "novelties", "visits", "settings",
]


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
async def admin_collections(_: Dict[str, Any] = Depends(require_roles("admin"))) -> List[Dict[str, Any]]:
    """Lista colecciones exportables con conteo de documentos."""
    out = []
    for name in EXPORTABLE_COLLECTIONS:
        n = await db[name].count_documents({})
        out.append({"name": name, "count": n})
    return out


@api.post("/admin/export", include_in_schema=False)
async def admin_export(payload: Dict[str, Any],
                       _: Dict[str, Any] = Depends(require_roles("admin"))) -> StreamingResponse:
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
    for name in selected:
        docs = await db[name].find({}).to_list(20000)
        dump["collections"][name] = [_serialize_doc(d) for d in docs]
    payload_bytes = json.dumps(dump, ensure_ascii=False, indent=2).encode("utf-8")
    ts = now_utc().strftime("%Y%m%d_%H%M%S")
    filename = f"megasoft-backup-{ts}.json"
    return StreamingResponse(
        iter([payload_bytes]),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@api.post("/admin/import", include_in_schema=False)
async def admin_import(file: UploadFile = File(...),
                       mode: str = "upsert",
                       collections: Optional[str] = None,
                       _: Dict[str, Any] = Depends(require_roles("admin"))) -> Dict[str, Any]:
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
    }
    summary: Dict[str, Any] = {"restored": {}, "skipped": {}, "mode": mode}
    for name, docs in (payload.get("collections") or {}).items():
        if name == "attendance":
            summary["skipped"][name] = "asistencia excluida por regla del producto"
            continue
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
