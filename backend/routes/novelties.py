"""Endpoints de Novedades (vacaciones, reposos, permisos, etc.).

Migrado desde server.py (líneas 2790-2900) durante la Fase A del refactor.
"""
from deps import (
    api, db, get_current_user, require_roles,
    LEADER_ROLES, LEADER_OR_ADMIN_ROLES,
    now_utc, new_id, strip_mongo_id, supervisor_scope_ids,
    NoveltyIn, NoveltyDecideIn, NoveltyPatchIn,
    HTTPException, Depends, Request,
    Any, Dict, List,
    audit_entity,
)


async def _validate_novelty_target(target: str, user: Dict[str, Any]) -> None:
    if target != user["user_id"] and user["role"] not in LEADER_OR_ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="No autorizado")
    if user["role"] in LEADER_ROLES and target != user["user_id"]:
        team_ids = await supervisor_scope_ids(user)
        if target not in team_ids:
            raise HTTPException(status_code=403, detail="El empleado no pertenece a tu equipo")


def _validate_novelty_range(payload: NoveltyIn) -> None:
    if payload.type == "vacation":
        return
    if not payload.start_time or not payload.end_time:
        raise HTTPException(status_code=400, detail="Debes indicar rango horario (hora inicio y hora fin)")
    if payload.start_time >= payload.end_time and payload.start_date == payload.end_date:
        raise HTTPException(status_code=400, detail="La hora fin debe ser mayor a la hora inicio")


@api.get("/novelties")
async def novelties_list(user: Dict[str, Any] = Depends(get_current_user)) -> List[Dict[str, Any]]:
    # Nunca listar novedades borradas (soft-delete)
    q: Dict[str, Any] = {"status": {"$ne": "deleted"}}
    if user["role"] == "employee":
        q["user_id"] = user["user_id"]
    elif user["role"] in LEADER_ROLES:
        q["user_id"] = {"$in": await supervisor_scope_ids(user)}
    docs = await db.novelties.find(q).sort("created_at", -1).to_list(1000)
    return [strip_mongo_id(d) for d in docs]


@api.post("/novelties")
async def novelties_create(request: Request, payload: NoveltyIn,
                           user: Dict[str, Any] = Depends(get_current_user)) -> Any:
    target = payload.user_id or user["user_id"]
    await _validate_novelty_target(target, user)

    # ── Modo multi-fecha ──────────────────────────────────────────────
    # Aplica sólo a remote/permission/leave. Cada fecha genera una novedad
    # independiente (start_date=end_date=fecha), reutilizando el resto del
    # payload. Preserva la validación de rango horario para no-vacation.
    multi = payload.dates or []
    if multi:
        if payload.type not in {"remote", "permission", "leave"}:
            raise HTTPException(status_code=400,
                                detail="Sólo Trabajo remoto, Permiso y Reposo admiten fechas múltiples")
        if payload.type != "vacation":
            if not payload.start_time or not payload.end_time:
                raise HTTPException(status_code=400, detail="Debes indicar rango horario (hora inicio y hora fin)")
            if payload.start_time >= payload.end_time:
                raise HTTPException(status_code=400, detail="La hora fin debe ser mayor a la hora inicio")
        unique_sorted = sorted({d for d in multi if d})
        docs = [{
            "novelty_id": new_id("nv", 12),
            "user_id": target,
            "type": payload.type,
            "start_date": d,
            "end_date": d,
            "start_time": payload.start_time,
            "end_time": payload.end_time,
            "reason": payload.reason,
            "status": "pending",
            "created_by": user["user_id"],
            "created_at": now_utc(),
            "decided_at": None,
            "decided_by": None,
            "decision_comment": None,
        } for d in unique_sorted]
        if docs:
            await db.novelties.insert_many(docs)
            for d in docs:
                await audit_entity(request, "CREATE", "novelties", d["novelty_id"], after=d, actor=user)
        return {"created": len(docs), "novelty_ids": [d["novelty_id"] for d in docs]}

    # ── Modo rango clásico ────────────────────────────────────────────
    _validate_novelty_range(payload)

    doc = {
        "novelty_id": new_id("nv", 12),
        "user_id": target,
        "type": payload.type,
        "start_date": payload.start_date,
        "end_date": payload.end_date,
        "start_time": payload.start_time if payload.type != "vacation" else None,
        "end_time": payload.end_time if payload.type != "vacation" else None,
        "reason": payload.reason,
        "status": "pending",
        "created_by": user["user_id"],
        "created_at": now_utc(),
        "decided_at": None,
        "decided_by": None,
        "decision_comment": None,
    }
    await db.novelties.insert_one(doc)
    await audit_entity(request, "CREATE", "novelties", doc["novelty_id"], after=doc, actor=user)
    return strip_mongo_id(doc)


@api.delete("/novelties/{novelty_id}")
async def novelties_delete(request: Request, novelty_id: str,
                           user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, bool]:
    """Elimina una novedad con SOFT DELETE (Adenda sep-2026).

    Permisos:
      - Admin: siempre puede.
      - Rol de liderazgo (coordinador/gerente/director): según jerarquía de
        visualización — director sobre toda la nómina; gerente/coordinador
        sobre su equipo a 2 niveles (vía `supervisor_scope_ids`).
      - Cualquier usuario: sobre las novedades creadas por él mismo.
    """
    doc = await db.novelties.find_one({"novelty_id": novelty_id})
    if not doc or doc.get("deleted_at"):
        raise HTTPException(status_code=404, detail="Novedad no encontrada")
    role = user.get("role")
    target_uid = doc.get("user_id")
    is_creator = doc.get("created_by") == user["user_id"]
    is_admin = role == "admin"
    is_leader = role in LEADER_OR_ADMIN_ROLES
    allowed = is_admin or is_creator
    if not allowed and is_leader:
        scope = await supervisor_scope_ids(user)
        allowed = target_uid in scope
    if not allowed:
        raise HTTPException(status_code=403, detail="No autorizado para eliminar esta novedad")
    # Soft delete: liberamos la novedad de la matriz sin perder el histórico.
    # Los generadores de matriz filtran por status ∈ {approved, pending}.
    await db.novelties.update_one(
        {"novelty_id": novelty_id},
        {"$set": {
            "status": "deleted",
            "deleted_at": now_utc(),
            "deleted_by": user["user_id"],
        }},
    )
    after = await db.novelties.find_one({"novelty_id": novelty_id})
    await audit_entity(request, "DELETE", "novelties", novelty_id, before=doc, after=after, actor=user)
    return {"ok": True}


@api.post("/novelties/bulk-decide")
async def novelties_decide(request: Request, payload: NoveltyDecideIn,
                           user: Dict[str, Any] = Depends(require_roles("admin", "coordinador", "gerente", "director"))) -> Dict[str, int]:
    updates = {
        "status": payload.decision,
        "decided_at": now_utc(),
        "decided_by": user["user_id"],
        "decision_comment": payload.comment,
    }
    res = await db.novelties.update_many({"novelty_id": {"$in": payload.novelty_ids}}, {"$set": updates})
    for nid in payload.novelty_ids:
        after = await db.novelties.find_one({"novelty_id": nid}, {"_id": 0})
        if after:
            await audit_entity(request, "UPDATE", "novelties", nid, after=after, actor=user,
                                extra={"decision": payload.decision})
    return {"modified_count": res.modified_count}


@api.patch("/novelties/{novelty_id}")
async def novelties_patch(request: Request, novelty_id: str, payload: NoveltyPatchIn,
                          user: Dict[str, Any] = Depends(require_roles("admin"))) -> Dict[str, Any]:
    before = await db.novelties.find_one({"novelty_id": novelty_id})
    if not before:
        raise HTTPException(status_code=404, detail="Novedad no encontrada")
    upd: Dict[str, Any] = {}
    for k in ("type", "start_date", "end_date", "start_time", "end_time",
              "reason", "status", "decision_comment", "user_id"):
        val = getattr(payload, k, None)
        if val is not None:
            upd[k] = val
    if upd:
        upd["updated_at"] = now_utc()
        upd["updated_by"] = user["user_id"]
        await db.novelties.update_one({"novelty_id": novelty_id}, {"$set": upd})
        doc = await db.novelties.find_one({"novelty_id": novelty_id})
        await audit_entity(request, "UPDATE", "novelties", novelty_id, before=before, after=doc, actor=user)
    else:
        doc = before
    return strip_mongo_id(doc)
