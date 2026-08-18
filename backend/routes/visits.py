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
        if not payload.company_name:
            raise HTTPException(status_code=400, detail="Nombre de empresa requerido para visita laboral")
        # Validación del motivo (catálogo fijo con opción “Otra”)
        if not payload.purpose or payload.purpose not in VISIT_PURPOSE_CATALOG:
            raise HTTPException(status_code=400,
                                detail="Selecciona un motivo válido del catálogo")
        if payload.purpose == "otra" and not (payload.purpose_other or "").strip():
            raise HTTPException(status_code=400,
                                detail="Debes especificar el motivo cuando eliges “Otra”")
        for v in payload.visitors:
            if not v.phone:
                raise HTTPException(status_code=400, detail="Cada visitante laboral requiere teléfono")
            if not v.cedula:
                raise HTTPException(status_code=400, detail="Cada visitante laboral requiere cédula")
    else:  # personal
        for v in payload.visitors:
            # En visitas personales: cédula obligatoria salvo que sea menor de edad
            if not v.cedula and not v.is_minor:
                raise HTTPException(status_code=400,
                                    detail="Cédula requerida (o marcar como menor de edad)")

    obs = (payload.observations or "").strip()
    if len(obs) > 300:
        raise HTTPException(status_code=400, detail="Observaciones no puede exceder 300 caracteres")

    visit_id = new_id("visit", 10)
    # NOTA: Ya no se genera un PIN aleatorio. La autenticación en el kiosco
    # se realiza por visitante usando los últimos 3 dígitos de la cédula del
    # visitante (endpoint /kiosk/visits/{id}/verify-visitor). Menos fricción
    # y sin confusión con un "PIN" adicional que había que compartir.
    doc = {
        "visit_id": visit_id,
        "type": payload.type,
        "host_user_id": payload.host_user_id,
        "host_name": host.get("name"),
        "scheduled_at": payload.scheduled_at or now_utc(),
        "company_name": payload.company_name if payload.type == "laboral" else None,
        # Motivo — nuevo catálogo
        "purpose": payload.purpose if payload.type == "laboral" else None,
        "purpose_label": (VISIT_PURPOSE_CATALOG.get(payload.purpose) if payload.type == "laboral" else None),
        "purpose_other": (payload.purpose_other.strip() if payload.type == "laboral" and payload.purpose == "otra" and payload.purpose_other else None),
        # Observaciones (nuevo campo, 300 caracteres)
        "observations": obs or None,
        # Retrocompat — se conservan los campos originales si el cliente antiguo los envía.
        "motive": payload.motive,
        "notes": payload.notes,
        "visitors": [v.model_dump() for v in payload.visitors],
        "selfies": [],
        "status": "pending",
        "created_at": now_utc(),
        "created_by": user["user_id"],
    }
    await db.visits.insert_one(doc)
    return {"visit_id": visit_id, "ok": True}


@api.get("/visits")
async def list_visits(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    type: Optional[str] = None,
    host_user_id: Optional[str] = None,
    company_name: Optional[str] = None,
    status: Optional[str] = None,
    user: Dict[str, Any] = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    if not user.get("can_view_visit_logs") and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="No tienes permiso para ver visitas")

    q: Dict[str, Any] = {}
    if from_date or to_date:
        rng: Dict[str, Any] = {}
        if from_date:
            rng["$gte"] = datetime.fromisoformat(from_date).replace(tzinfo=APP_TZ).astimezone(timezone.utc)
        if to_date:
            rng["$lt"] = (datetime.fromisoformat(to_date).replace(tzinfo=APP_TZ) + timedelta(days=1)).astimezone(timezone.utc)
        q["scheduled_at"] = rng
    if type:
        q["type"] = type
    if host_user_id:
        q["host_user_id"] = host_user_id
    if company_name:
        q["company_name"] = {"$regex": company_name, "$options": "i"}
    if status:
        q["status"] = status

    docs = []
    async for d in db.visits.find(q).sort("scheduled_at", -1).limit(500):
        d.pop("_id", None)
        d["selfies_count"] = len(d.get("selfies") or [])
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
        raise HTTPException(status_code=404, detail="Visita no encontrada")
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
        v.pop("check_in_pin", None)  # campo legacy — no se usa
        docs.append(v)
    return docs


@api.get("/kiosk/visits/today")
async def kiosk_visits_today() -> List[Dict[str, Any]]:
    """Listado público de todas las visitas activas del día para el Kiosco.
    Se autentican después con los 3 últimos dígitos de la cédula del visitante."""
    today_local = now_utc().astimezone(APP_TZ)
    start = today_local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    end = (today_local.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)).astimezone(timezone.utc)
    docs: List[Dict[str, Any]] = []
    async for v in db.visits.find(
        {"status": {"$in": ["pending", "in_progress"]},
         "scheduled_at": {"$gte": start, "$lt": end}}
    ).sort("scheduled_at", 1):
        visitors = v.get("visitors") or []
        # Devuelve sólo lo necesario para pintar el listado; NUNCA el PIN.
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
            # Nombres de visitantes (para la vista "Visita Seleccionada"); la cédula
            # completa queda oculta — sólo se expone al validar los 3 dígitos.
            "visitors": [{"name": vs.get("name")} for vs in visitors],
            "primary_visitor_name": (visitors[0].get("name") if visitors else None),
            "status": v.get("status"),
        })
    return docs


@api.post("/kiosk/visits/{visit_id}/verify-visitor")
async def kiosk_verify_visitor_pin(visit_id: str, payload: VisitorPinIn) -> Dict[str, Any]:
    """Valida los últimos 3 dígitos de la cédula del visitante indicado.
    Se usa en el nuevo flujo de recepción: cada visitante se autentica por
    separado con los 3 últimos dígitos de su documento antes de la selfie."""
    pin = (payload.pin or "").strip()
    if not pin or not pin.isdigit() or len(pin) != 3:
        raise HTTPException(status_code=400, detail="El PIN debe ser numérico de 3 dígitos")
    doc = await db.visits.find_one({"visit_id": visit_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Visita no encontrada")
    if doc.get("status") not in ("pending", "in_progress"):
        raise HTTPException(status_code=400, detail="Esta visita ya fue completada o cancelada")
    visitors = doc.get("visitors") or []
    idx = payload.visitor_index
    if idx < 0 or idx >= len(visitors):
        raise HTTPException(status_code=400, detail="Índice de visitante inválido")
    visitor = visitors[idx]
    cedula = (visitor.get("cedula") or "")
    # Extrae únicamente dígitos para tolerar formatos "V-12345678", "12.345.678", etc.
    digits = "".join(ch for ch in cedula if ch.isdigit())
    if len(digits) < 3:
        raise HTTPException(status_code=400,
                            detail="La cédula del visitante no permite validación por 3 dígitos")
    if digits[-3:] != pin:
        raise HTTPException(status_code=403, detail="Los 3 dígitos no coinciden con la cédula del visitante")
    return {"ok": True, "visitor": {"name": visitor.get("name"), "cedula": cedula}}


@api.post("/visits/{visit_id}/capture-selfie")
async def capture_visit_selfie(visit_id: str, payload: VisitSelfieIn) -> Dict[str, Any]:
    doc = await db.visits.find_one({"visit_id": visit_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Visita no encontrada")
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
    """Cierra manualmente una visita: registra exit_at y cambia status='closed'.
       Requiere can_view_visit_logs o rol admin.
       Un usuario no-admin solo puede cerrar visitas que él mismo creó."""
    if not user.get("can_view_visit_logs") and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="No tienes permiso para cerrar visitas")
    doc = await db.visits.find_one({"visit_id": visit_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Visita no encontrada")
    if user.get("role") != "admin" and doc.get("created_by") != user["user_id"]:
        raise HTTPException(status_code=403,
                            detail="Solo puedes cerrar visitas que tú hayas programado")
    if doc.get("status") == "closed":
        raise HTTPException(status_code=400, detail="La visita ya está cerrada")
    exit_at = now_utc()
    scheduled_at = doc.get("scheduled_at") or doc.get("created_at")
    duration_min = None
    if scheduled_at:
        if isinstance(scheduled_at, datetime):
            if scheduled_at.tzinfo is None:
                scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)
            raw = (exit_at - scheduled_at).total_seconds() / 60
            duration_min = round(max(0.0, raw), 1)  # clamp para evitar negativos si scheduled_at es futuro
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
    """Elimina una visita. Un usuario no-admin solo puede borrar visitas que él mismo creó.
       Requiere can_view_visit_logs o rol admin."""
    if not user.get("can_view_visit_logs") and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="No tienes permiso para eliminar visitas")
    doc = await db.visits.find_one({"visit_id": visit_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Visita no encontrada")
    if user.get("role") != "admin" and doc.get("created_by") != user["user_id"]:
        raise HTTPException(status_code=403,
                            detail="Solo puedes eliminar visitas que tú hayas programado")
    await db.visits.delete_one({"visit_id": visit_id})
    return {"ok": True}



