"""Endpoints de Control de Visitas.

Migrado desde server.py durante la Fase A · Iteración 2 (feb-2026).
"""
from deps import (
    api, db, get_current_user, require_roles,
    APP_TZ, now_utc, new_id, strip_mongo_id, supervisor_scope_ids,
    UserPermissionsIn, VisitIn, VisitorPinIn, VisitSelfieIn,
    VISIT_PURPOSE_CATALOG,
    HTTPException, Depends, Query,
    Any, Dict, List, Optional,
    datetime, timezone, timedelta,
)

ERR_VISIT_NOT_FOUND = "Visita no encontrada"


# ==================================================================
# VISITS (Control de Visitas) — 6 endpoints
# ==================================================================
@api.post("/users/{user_id}/visit-permissions")
async def set_visit_permissions(
    user_id: str,
    payload: UserPermissionsIn,
    _: Dict[str, Any] = Depends(require_roles("admin")),
) -> Dict[str, Any]:
    """Admin toggles can_create_visits / can_view_visit_logs on a user."""
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        return {"ok": True, "changed": 0}
    res = await db.users.update_one({"user_id": user_id}, {"$set": updates})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return {"ok": True, "changed": res.modified_count, "updates": updates}


def _validate_laboral_visit(payload: VisitIn) -> None:
    if not payload.company_name:
        raise HTTPException(status_code=400, detail="Nombre de empresa requerido para visita laboral")
    if not payload.purpose or payload.purpose not in VISIT_PURPOSE_CATALOG:
        raise HTTPException(status_code=400, detail="Selecciona un motivo válido del catálogo")
    if payload.purpose == "otra" and not (payload.purpose_other or "").strip():
        raise HTTPException(status_code=400, detail="Debes especificar el motivo cuando eliges “Otra”")
    for v in payload.visitors:
        # Visitantes internos (empleados de la empresa) no se validan estrictamente
        # — sus datos vienen autocompletados desde el catálogo de usuarios y algunos
        # campos (teléfono) pueden no estar registrados en la BD.
        if v.kind == "internal":
            if not v.internal_user_id:
                raise HTTPException(status_code=400, detail="Falta identificar al empleado interno")
            continue
        if not v.phone:
            raise HTTPException(status_code=400, detail="Cada visitante laboral requiere teléfono")
        if not v.cedula:
            raise HTTPException(status_code=400, detail="Cada visitante laboral requiere cédula")


def _validate_personal_visit(payload: VisitIn) -> None:
    for v in payload.visitors:
        if v.kind == "internal":
            if not v.internal_user_id:
                raise HTTPException(status_code=400, detail="Falta identificar al empleado interno")
            continue
        if not v.cedula and not v.is_minor:
            raise HTTPException(status_code=400, detail="Cédula requerida (o marcar como menor de edad)")


@api.post("/visits")
async def create_visit(payload: VisitIn,
                       user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    if not user.get("can_create_visits") and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="No tienes permiso para crear visitas")
    if payload.type not in ("personal", "laboral"):
        raise HTTPException(status_code=400, detail="type debe ser 'personal' o 'laboral'")
    if not payload.visitors:
        raise HTTPException(status_code=400, detail="Debe registrar al menos un visitante")

    host = await db.users.find_one({"user_id": payload.host_user_id}, {"user_id": 1, "name": 1, "_id": 0})
    if not host:
        raise HTTPException(status_code=404, detail="Empleado anfitrión no encontrado")

    if payload.type == "laboral":
        _validate_laboral_visit(payload)
    else:
        _validate_personal_visit(payload)

    obs = (payload.observations or "").strip()
    if len(obs) > 300:
        raise HTTPException(status_code=400, detail="Observaciones no puede exceder 300 caracteres")

    visit_id = new_id("visit", 10)
    doc = {
        "visit_id": visit_id,
        "type": payload.type,
        "host_user_id": payload.host_user_id,
        "host_name": host.get("name"),
        "scheduled_at": payload.scheduled_at or now_utc(),
        "company_name": payload.company_name if payload.type == "laboral" else None,
        "purpose": payload.purpose if payload.type == "laboral" else None,
        "purpose_label": VISIT_PURPOSE_CATALOG.get(payload.purpose or "") if payload.type == "laboral" else None,
        "purpose_other": payload.purpose_other if payload.purpose == "otra" else None,
        "observations": obs or None,
        "visitors": [v.model_dump() for v in payload.visitors],
        "status": "pending",
        "created_by": user["user_id"],
        "created_at": now_utc(),
        "selfies": [],
    }
    await db.visits.insert_one(doc)
    return strip_mongo_id(doc)


@api.get("/visits")
async def list_visits(user: Dict[str, Any] = Depends(get_current_user)) -> List[Dict[str, Any]]:
    if not user.get("can_view_visit_logs") and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="No tienes permiso para ver el registro de visitas")
    q: Dict[str, Any] = {}
    if user.get("role") != "admin":
        q["created_by"] = user["user_id"]
    docs = []
    for d in await db.visits.find(q).sort("created_at", -1).to_list(1000):
        d.pop("_id", None)
        d.pop("selfies", None)
        docs.append(d)
    return docs


@api.get("/visits/{visit_id}")
async def get_visit(visit_id: str,
                    user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    if not user.get("can_view_visit_logs") and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="No tienes permiso para ver visitas")
    d = await db.visits.find_one({"visit_id": visit_id})
    if not d:
        raise HTTPException(status_code=404, detail=ERR_VISIT_NOT_FOUND)
    d.pop("_id", None)
    return d


@api.get("/kiosk/pending-visits/{host_user_id}")
async def kiosk_pending_visits(host_user_id: str) -> List[Dict[str, Any]]:
    today_local = now_utc().astimezone(APP_TZ)
    start = today_local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    end = (today_local.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)).astimezone(timezone.utc)
    docs = []
    async for v in db.visits.find(
        {"host_user_id": host_user_id,
         "status": {"$in": ["pending", "in_progress"]},
         "scheduled_at": {"$gte": start, "$lt": end}}
    ).sort("scheduled_at", 1):
        v.pop("_id", None)
        v.pop("selfies", None)
        v.pop("check_in_pin", None)
        docs.append(v)
    return docs


@api.get("/kiosk/visits/today")
async def kiosk_visits_today() -> List[Dict[str, Any]]:
    today_local = now_utc().astimezone(APP_TZ)
    start = today_local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    end = (today_local.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)).astimezone(timezone.utc)
    docs: List[Dict[str, Any]] = []
    async for v in db.visits.find(
        {"status": {"$in": ["pending", "in_progress"]},
         "scheduled_at": {"$gte": start, "$lt": end}}
    ).sort("scheduled_at", 1):
        visitors = v.get("visitors") or []
        docs.append({
            "visit_id": v.get("visit_id"),
            "type": v.get("type"),
            "host_name": v.get("host_name"),
            "company_name": v.get("company_name"),
            "purpose_label": v.get("purpose_label"),
            "purpose_other": v.get("purpose_other"),
            "observations": v.get("observations"),
            "scheduled_at": v.get("scheduled_at").isoformat() if v.get("scheduled_at") else None,
            "visitors_count": len(visitors),
            "visitors": [{"name": vs.get("name")} for vs in visitors],
            "primary_visitor_name": (visitors[0].get("name") if visitors else None),
            "status": v.get("status"),
        })
    return docs


@api.post("/kiosk/visits/{visit_id}/verify-visitor")
async def kiosk_verify_visitor_pin(visit_id: str, payload: VisitorPinIn) -> Dict[str, Any]:
    pin = (payload.pin or "").strip()
    if not pin or not pin.isdigit() or len(pin) != 3:
        raise HTTPException(status_code=400, detail="El PIN debe ser numérico de 3 dígitos")
    doc = await db.visits.find_one({"visit_id": visit_id})
    if not doc:
        raise HTTPException(status_code=404, detail=ERR_VISIT_NOT_FOUND)
    if doc.get("status") not in ("pending", "in_progress"):
        raise HTTPException(status_code=400, detail="Esta visita ya fue completada o cancelada")
    visitors = doc.get("visitors") or []
    idx = payload.visitor_index
    if idx < 0 or idx >= len(visitors):
        raise HTTPException(status_code=400, detail="Índice de visitante inválido")
    visitor = visitors[idx]
    cedula = (visitor.get("cedula") or "")
    digits = "".join(ch for ch in cedula if ch.isdigit())
    if len(digits) < 3:
        raise HTTPException(status_code=400, detail="La cédula del visitante no permite validación por 3 dígitos")
    if digits[-3:] != pin:
        raise HTTPException(status_code=403, detail="Los 3 dígitos no coinciden con la cédula del visitante")
    return {"ok": True, "visitor": {"name": visitor.get("name"), "cedula": cedula}}


@api.post("/visits/{visit_id}/capture-selfie")
async def capture_visit_selfie(visit_id: str, payload: VisitSelfieIn) -> Dict[str, Any]:
    doc = await db.visits.find_one({"visit_id": visit_id})
    if not doc:
        raise HTTPException(status_code=404, detail=ERR_VISIT_NOT_FOUND)
    if payload.visitor_index < 0 or payload.visitor_index >= len(doc.get("visitors") or []):
        raise HTTPException(status_code=400, detail="visitor_index fuera de rango")
    if not payload.selfie_base64 or not payload.selfie_base64.startswith("data:image"):
        raise HTTPException(status_code=400, detail="selfie_base64 inválido")

    selfies = doc.get("selfies") or []
    selfies = [s for s in selfies if s.get("visitor_index") != payload.visitor_index]
    selfies.append({
        "visitor_index": payload.visitor_index,
        "selfie_base64": payload.selfie_base64,
        "captured_at": now_utc(),
    })
    total_visitors = len(doc.get("visitors") or [])
    new_status = "completed" if len(selfies) >= total_visitors else "in_progress"
    updates: Dict[str, Any] = {"selfies": selfies, "status": new_status}
    if new_status == "completed":
        updates["completed_at"] = now_utc()
    await db.visits.update_one({"visit_id": visit_id}, {"$set": updates})
    return {"ok": True, "status": new_status, "captured": len(selfies), "total": total_visitors}


@api.post("/visits/{visit_id}/close")
async def close_visit(visit_id: str,
                      user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    if not user.get("can_view_visit_logs") and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="No tienes permiso para cerrar visitas")
    doc = await db.visits.find_one({"visit_id": visit_id})
    if not doc:
        raise HTTPException(status_code=404, detail=ERR_VISIT_NOT_FOUND)
    if user.get("role") != "admin" and doc.get("created_by") != user["user_id"]:
        raise HTTPException(status_code=403, detail="Solo puedes cerrar visitas que tú hayas programado")
    if doc.get("status") == "closed":
        raise HTTPException(status_code=400, detail="La visita ya está cerrada")
    exit_at = now_utc()
    scheduled_at = doc.get("scheduled_at") or doc.get("created_at")
    duration_min = None
    if scheduled_at and isinstance(scheduled_at, datetime):
        if scheduled_at.tzinfo is None:
            scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)
        raw = (exit_at - scheduled_at).total_seconds() / 60
        duration_min = round(max(0.0, raw), 1)
    await db.visits.update_one(
        {"visit_id": visit_id},
        {"$set": {
            "status": "closed",
            "exit_at": exit_at,
            "duration_minutes": duration_min,
            "closed_by": user["user_id"],
        }},
    )
    return {"ok": True, "exit_at": exit_at.isoformat(), "duration_minutes": duration_min}


@api.delete("/visits/{visit_id}")
async def delete_visit(visit_id: str,
                       user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, bool]:
    if not user.get("can_view_visit_logs") and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="No tienes permiso para eliminar visitas")
    doc = await db.visits.find_one({"visit_id": visit_id})
    if not doc:
        raise HTTPException(status_code=404, detail=ERR_VISIT_NOT_FOUND)
    if user.get("role") != "admin" and doc.get("created_by") != user["user_id"]:
        raise HTTPException(status_code=403, detail="Solo puedes eliminar visitas que tú hayas programado")
    await db.visits.delete_one({"visit_id": visit_id})
    return {"ok": True}
