"""Endpoints de Novedades (vacaciones, reposos, permisos, etc.).

Migrado desde server.py (líneas 2790-2900) durante la Fase A del refactor.
"""
from deps import (
    api, db, get_current_user, require_roles,
    LEADER_ROLES, LEADER_OR_ADMIN_ROLES,
    now_utc, new_id, strip_mongo_id, supervisor_scope_ids,
    NoveltyIn, NoveltyDecideIn, NoveltyPatchIn,
    HTTPException, Depends,
    Any, Dict, List,
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
    q: Dict[str, Any] = {}
    if user["role"] == "employee":
        q["user_id"] = user["user_id"]
    elif user["role"] in LEADER_ROLES:
        team = await db.users.find({"supervisor_id": user["user_id"]}, {"user_id": 1}).to_list(1000)
        team_ids = [t["user_id"] for t in team] + [user["user_id"]]
        q["user_id"] = {"$in": team_ids}
    docs = await db.novelties.find(q).sort("created_at", -1).to_list(1000)
    return [strip_mongo_id(d) for d in docs]


@api.post("/novelties")
async def novelties_create(payload: NoveltyIn,
                           user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    target = payload.user_id or user["user_id"]
    await _validate_novelty_target(target, user)
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
    return strip_mongo_id(doc)


@api.delete("/novelties/{novelty_id}")
async def novelties_delete(novelty_id: str,
                           user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, bool]:
    doc = await db.novelties.find_one({"novelty_id": novelty_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Novedad no encontrada")
    if doc.get("created_by") != user["user_id"] and user["role"] not in LEADER_OR_ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="No autorizado para eliminar esta novedad")
    await db.novelties.delete_one({"novelty_id": novelty_id})
    return {"ok": True}


@api.post("/novelties/bulk-decide")
async def novelties_decide(payload: NoveltyDecideIn,
                           user: Dict[str, Any] = Depends(require_roles("admin", "coordinador", "gerente", "director"))) -> Dict[str, int]:
    updates = {
        "status": payload.decision,
        "decided_at": now_utc(),
        "decided_by": user["user_id"],
        "decision_comment": payload.comment,
    }
    res = await db.novelties.update_many({"novelty_id": {"$in": payload.novelty_ids}}, {"$set": updates})
    return {"modified_count": res.modified_count}


@api.patch("/novelties/{novelty_id}")
async def novelties_patch(novelty_id: str, payload: NoveltyPatchIn,
                          user: Dict[str, Any] = Depends(require_roles("admin"))) -> Dict[str, Any]:
    doc = await db.novelties.find_one({"novelty_id": novelty_id})
    if not doc:
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
    return strip_mongo_id(doc)
