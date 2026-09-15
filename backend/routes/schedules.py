"""Endpoints de Horarios (Schedules), Asignaciones diarias y Planes.

Migrado desde server.py durante la Fase A · Iteración 3 (feb-2026).
"""
from typing import Optional
from pymongo import UpdateOne
from pydantic import BaseModel

from deps import (
    api, db, get_current_user,
    now_utc, new_id, strip_mongo_id,
    ScheduleIn,
    HTTPException, Depends,
    Any, Dict, List,
)


# ------------------------------------------------------------------
# Dependencies locales (permisos específicos de horarios y asignaciones)
# ------------------------------------------------------------------
async def _has_rbac_perm(user: Dict[str, Any], key: str) -> bool:
    from deps import enrich_user_with_permissions
    enriched_user = await enrich_user_with_permissions(user)
    perms = enriched_user.get("effective_permissions") or {}
    return bool(perms.get(key))

async def _require_admin_or_schedules_manager(
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Admin siempre puede; empleado/supervisor puede si tiene can_manage_schedules=True o permiso RBAC."""
    if user.get("role") == "admin" or user.get("can_manage_schedules") or await _has_rbac_perm(user, "horarios"):
        return user
    raise HTTPException(status_code=403, detail="Se requiere permiso 'Puede crear y asignar horarios'.")

async def _require_admin_or_assigner(
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Admin siempre; empleado/supervisor con can_assign_schedules=True o permiso RBAC también."""
    if user.get("role") == "admin" or user.get("can_assign_schedules") or await _has_rbac_perm(user, "asignar_horarios"):
        return user
    raise HTTPException(
        status_code=403,
        detail="Se requiere permiso 'Puede asignar turnos y novedades a personal sin horario fijo'.",
    )

# ==================================================================
# SCHEDULES CRUD
# ==================================================================
@api.get("/schedules")
async def schedules_list(_: Dict[str, Any] = Depends(get_current_user)) -> List[Dict[str, Any]]:
    docs = await db.schedules.find({}).to_list(500)
    return [strip_mongo_id(d) for d in docs]


ERR_SCHEDULE_NOT_FOUND = "Horario no encontrado"


@api.post("/schedules")
async def schedules_create(payload: ScheduleIn,
                           _: Dict[str, Any] = Depends(_require_admin_or_schedules_manager)) -> Dict[str, Any]:
    doc = payload.model_dump()
    doc["schedule_id"] = new_id("sch", 10)
    doc["created_at"] = now_utc()
    await db.schedules.insert_one(doc)
    return strip_mongo_id(doc)


@api.put("/schedules/{schedule_id}")
async def schedules_update(schedule_id: str, payload: ScheduleIn,
                           _: Dict[str, Any] = Depends(_require_admin_or_schedules_manager)) -> Dict[str, Any]:
    updates = payload.model_dump(exclude_unset=True)
    res = await db.schedules.update_one({"schedule_id": schedule_id}, {"$set": updates})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail=ERR_SCHEDULE_NOT_FOUND)
    doc = await db.schedules.find_one({"schedule_id": schedule_id})
    return strip_mongo_id(doc)


@api.delete("/schedules/{schedule_id}")
async def schedules_delete(schedule_id: str,
                           _: Dict[str, Any] = Depends(_require_admin_or_schedules_manager)) -> Dict[str, bool]:
    res = await db.schedules.delete_one({"schedule_id": schedule_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail=ERR_SCHEDULE_NOT_FOUND)
    return {"ok": True}


@api.patch("/users/{user_id}/schedule")
async def users_assign_schedule(user_id: str, payload: Dict[str, Any],
                                current: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Asigna (o desasigna con null) un horario a un empleado.
       Permitido a: admin, o cualquier usuario con can_manage_schedules=True
       que sea el supervisor directo del empleado objetivo."""
    schedule_id = (payload or {}).get("schedule_id")
    target = await db.users.find_one({"user_id": user_id})
    if not target:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    is_admin = current.get("role") == "admin"
    has_perm = bool(current.get("can_manage_schedules"))
    is_supervisor_of_target = target.get("supervisor_id") == current["user_id"]

    if not (is_admin or (has_perm and is_supervisor_of_target)):
        raise HTTPException(
            status_code=403,
            detail="No autorizado. Necesitas ser admin, o supervisor del empleado con permiso 'Puede crear y asignar horarios'.",
        )

    if schedule_id:
        sch = await db.schedules.find_one({"schedule_id": schedule_id})
        if not sch:
            raise HTTPException(status_code=404, detail="Horario no encontrado")

    await db.users.update_one({"user_id": user_id}, {"$set": {"schedule_id": schedule_id or None}})
    u = await db.users.find_one({"user_id": user_id}, {"password_hash": 0, "pin_code_hash": 0})
    return strip_mongo_id(u)


# ==================================================================
# SCHEDULE ASSIGNMENTS — planificación diaria para personal sin horario fijo.
# Usada para turnos rotativos (Monitoreo, guardias, etc.) y novedades masivas.
# Colección: schedule_assignments · unique index (user_id, date).
# ==================================================================
# Tipos de novedad admitidos por el módulo de Asignación de Horarios.
# Coinciden con los códigos internos usados por las novedades regulares para que
# el motor del Reporte Matricial las contabilice sin cambios adicionales.
#   remote     → Trabajo Remoto
#   vacation   → Vacaciones
#   leave      → Reposo
#   permission → Permiso (día completo cuando se asigna aquí)
_VALID_ASSIGN_NOVELTIES = {"remote", "vacation", "leave", "permission"}


async def _ensure_assignments_index() -> None:
    try:
        await db.schedule_assignments.create_index(
            [("user_id", 1), ("date", 1)], unique=True, name="uq_user_date"
        )
    except Exception:
        pass


class AssignmentCell(BaseModel):
    """Par exacto (usuario, fecha). Permite persistir selecciones no
    rectangulares sin inflar el conjunto con el producto cartesiano."""
    user_id: str
    date: str  # YYYY-MM-DD


class AssignmentBulkIn(BaseModel):
    user_ids: List[str]
    dates: List[str]                        # ["YYYY-MM-DD", ...]
    kind: str                               # "shift" | "novelty"
    schedule_id: Optional[str] = None       # required if kind='shift'
    novelty_type: Optional[str] = None      # required if kind='novelty'
    # Adenda (sep-2026): si viene poblado, se persiste EXACTAMENTE ese conjunto
    # de celdas (modo "selección exacta") en lugar del producto cartesiano
    # user_ids × dates. Corrige los marcajes fantasma al guardar planificaciones
    # con selecciones no rectangulares.
    cells: Optional[List[AssignmentCell]] = None


class AssignmentClearIn(BaseModel):
    user_ids: List[str]
    dates: List[str]
    # Igual que en bulk: lista de pares exactos a eliminar.
    cells: Optional[List[AssignmentCell]] = None


class AssignmentEntryIn(BaseModel):
    """Celda asignada dentro de una planificación (turno o novedad)."""
    user_id: str
    date: str  # YYYY-MM-DD
    kind: str  # "shift" | "novelty"
    schedule_id: Optional[str] = None
    novelty_type: Optional[str] = None


class AssignmentPlanIn(BaseModel):
    name: str
    from_date: str
    to_date: str
    user_ids: List[str] = []
    # Orden manual de las filas tal como las dejó el planificador (flechas ↑↓).
    row_order: List[str] = []
    overwrite: bool = False  # Si True, elimina planes previos con rango solapado.
    # Adenda (sep-2026): matriz completa de asignaciones. El guardado es
    # TRANSACCIONAL a nivel lógico: primero se valida el solapamiento (409 sin
    # escribir nada) y sólo si pasa se persiste plan + asignaciones. Así un
    # intento rechazado NUNCA corrompe la planificación original.
    assignments: Optional[List[AssignmentEntryIn]] = None


def _plan_public(doc: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "plan_id": doc.get("plan_id"),
        "name": doc.get("name"),
        "from_date": doc.get("from_date"),
        "to_date": doc.get("to_date"),
        "user_ids": doc.get("user_ids") or [],
        "row_order": doc.get("row_order") or [],
    }


async def _prune_out_of_range_assignments(user_ids: List[str], from_date: str, to_date: str) -> int:
    """Elimina asignaciones de los usuarios del plan que queden FUERA del rango
    [from_date, to_date] tras guardar/actualizar la planificación.

    Regla de negocio (Adenda sep-2026): la planificación es la fuente de verdad.
    Si el usuario edita el plan y acorta el rango, los días eliminados deben
    desaparecer también de la Matriz de Asistencia — de lo contrario quedan
    datos huérfanos desfasados.
    """
    if not user_ids:
        return 0
    result = await db.schedule_assignments.delete_many({
        "user_id": {"$in": user_ids},
        "$or": [{"date": {"$lt": from_date}}, {"date": {"$gt": to_date}}],
    })
    return result.deleted_count


async def _validate_plan_assignments(entries: List[AssignmentEntryIn]) -> None:
    """Valida las celdas de la matriz enviada con el plan (mismas reglas que bulk)."""
    sch_cache: Dict[str, bool] = {}
    for e in entries:
        if e.kind == "shift":
            if not e.schedule_id:
                raise HTTPException(status_code=400, detail="schedule_id es obligatorio para celdas de turno")
            if e.schedule_id not in sch_cache:
                sch_cache[e.schedule_id] = bool(await db.schedules.find_one({"schedule_id": e.schedule_id}))
            if not sch_cache[e.schedule_id]:
                raise HTTPException(status_code=404, detail=ERR_SCHEDULE_NOT_FOUND)
        elif e.kind == "novelty":
            if e.novelty_type not in _VALID_ASSIGN_NOVELTIES:
                raise HTTPException(status_code=400, detail=f"novelty_type inválido: {e.novelty_type}")
        else:
            raise HTTPException(status_code=400, detail=f"kind inválido: {e.kind}")


async def _replace_plan_assignments(user_ids: List[str], from_date: str, to_date: str,
                                    entries: List[AssignmentEntryIn], actor_id: str,
                                    extra_user_ids: Optional[List[str]] = None) -> int:
    """Reemplazo exacto de las asignaciones del plan dentro de su rango.

    Borra todas las asignaciones de los usuarios involucrados dentro de
    [from_date, to_date] y luego inserta las enviadas. Garantiza que lo
    guardado sea IDÉNTICO a lo maquetado en pantalla (Adenda sep-2026).

    `extra_user_ids`: usuarios removidos del plan (PUT) — sus asignaciones en
    el rango también se eliminan para no dejar líneas huérfanas.
    """
    universe = set(user_ids or []) | {e.user_id for e in entries} | set(extra_user_ids or [])
    if not universe:
        return 0
    await _ensure_assignments_index()
    await db.schedule_assignments.delete_many({
        "user_id": {"$in": list(universe)},
        "date": {"$gte": from_date, "$lte": to_date},
    })
    if not entries:
        return 0
    now = now_utc()
    docs = [{
        "assignment_id": new_id("asg", 10),
        "user_id": e.user_id,
        "date": e.date,
        "kind": e.kind,
        "schedule_id": e.schedule_id if e.kind == "shift" else None,
        "novelty_type": e.novelty_type if e.kind == "novelty" else None,
        "created_at": now,
        "created_by": actor_id,
        "updated_at": now,
        "updated_by": actor_id,
    } for e in entries]
    await db.schedule_assignments.insert_many(docs)
    return len(docs)


async def _find_overlapping_plans(from_date: str, to_date: str,
                                  exclude_plan_id: Optional[str] = None,
                                  user_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """Planes cuyo rango intersecta con [from_date, to_date] (inclusive).

    Si se pasa `user_ids`, sólo se retornan planes que **compartan al menos un
    empleado** con el conjunto dado. Regla de negocio (feb-2026): las
    planificaciones pueden coexistir en el mismo rango siempre que involucren
    equipos disjuntos — sólo se marca conflicto cuando un mismo empleado queda
    asignado dos veces.
    """
    q: Dict[str, Any] = {
        "from_date": {"$lte": to_date},
        "to_date": {"$gte": from_date},
    }
    if exclude_plan_id:
        q["plan_id"] = {"$ne": exclude_plan_id}
    if user_ids:
        q["user_ids"] = {"$in": list(user_ids)}
    docs = await db.assignment_plans.find(q).sort("from_date", 1).to_list(50)
    return [_plan_public(d) for d in docs]


@api.get("/schedule-assignments/eligible-users")
async def eligible_users_for_assignments(_: Dict[str, Any] = Depends(_require_admin_or_assigner)) -> List[Dict[str, Any]]:
    """Lista de empleados sin horario fijo — candidatos a asignación de turnos rotativos."""
    q: Dict[str, Any] = {
        "role": {"$ne": "admin"},
        "$or": [{"schedule_id": None}, {"schedule_id": ""}, {"schedule_id": {"$exists": False}}],
    }
    docs = await db.users.find(q, {"password_hash": 0, "pin_code_hash": 0}).to_list(1000)
    docs.sort(key=lambda u: (u.get("name") or "").lower())
    return [strip_mongo_id(d) for d in docs]


@api.get("/schedule-assignments")
async def list_schedule_assignments(
    from_date: str,
    to_date: str,
    user_ids: Optional[str] = None,
    _: Dict[str, Any] = Depends(_require_admin_or_assigner),
) -> List[Dict[str, Any]]:
    """Lista asignaciones en la ventana [from_date, to_date] (ISO YYYY-MM-DD).
    user_ids: lista separada por comas (opcional)."""
    q: Dict[str, Any] = {"date": {"$gte": from_date, "$lte": to_date}}
    if user_ids:
        ids = [i.strip() for i in user_ids.split(",") if i.strip()]
        if ids:
            q["user_id"] = {"$in": ids}
    docs = await db.schedule_assignments.find(q).to_list(50000)
    return [strip_mongo_id(d) for d in docs]


async def _validate_bulk_payload(payload: AssignmentBulkIn) -> None:
    has_cells = bool(payload.cells)
    if not has_cells and (not payload.user_ids or not payload.dates):
        raise HTTPException(status_code=400, detail="Debes indicar user_ids y dates")
    if payload.kind == "shift":
        if not payload.schedule_id:
            raise HTTPException(status_code=400, detail="schedule_id es obligatorio para kind='shift'")
        sch = await db.schedules.find_one({"schedule_id": payload.schedule_id})
        if not sch:
            raise HTTPException(status_code=404, detail=ERR_SCHEDULE_NOT_FOUND)
    elif payload.kind == "novelty":
        if payload.novelty_type not in _VALID_ASSIGN_NOVELTIES:
            raise HTTPException(
                status_code=400,
                detail=f"novelty_type debe ser uno de {sorted(_VALID_ASSIGN_NOVELTIES)}",
            )
    else:
        raise HTTPException(status_code=400, detail="kind debe ser 'shift' o 'novelty'")


@api.post("/schedule-assignments/bulk")
async def bulk_assign(payload: AssignmentBulkIn,
                      current: Dict[str, Any] = Depends(_require_admin_or_assigner)) -> Dict[str, Any]:
    """Upsert masivo: asigna un turno o una novedad al conjunto de (user_id × date).

    Si el payload trae `cells`, se persiste EXACTAMENTE ese conjunto de pares
    (modo selección exacta — evita los marcajes fantasma del producto
    cartesiano cuando la selección no es rectangular)."""
    await _validate_bulk_payload(payload)
    await _ensure_assignments_index()

    # Pares (user_id, date) a escribir — exactos si vienen `cells`.
    if payload.cells:
        pairs = {(c.user_id, c.date) for c in payload.cells}
    else:
        pairs = {(uid, d) for uid in payload.user_ids for d in payload.dates}

    now = now_utc()
    ops = []
    for uid, d in pairs:
        doc: Dict[str, Any] = {
            "user_id": uid,
            "date": d,
            "kind": payload.kind,
            "schedule_id": payload.schedule_id if payload.kind == "shift" else None,
            "novelty_type": payload.novelty_type if payload.kind == "novelty" else None,
            "updated_at": now,
            "updated_by": current["user_id"],
        }
        ops.append(UpdateOne(
            {"user_id": uid, "date": d},
            {"$set": doc,
             "$setOnInsert": {
                 "assignment_id": new_id("asg", 10),
                 "created_at": now,
                 "created_by": current["user_id"],
             }},
            upsert=True,
        ))
    if not ops:
        return {"ok": True, "affected": 0}
    result = await db.schedule_assignments.bulk_write(ops, ordered=False)
    return {
        "ok": True,
        "upserted": len(result.upserted_ids or {}),
        "modified": result.modified_count,
        "affected": len(ops),
    }


@api.get("/schedule-assignment-plans")
async def list_assignment_plans(_: Dict[str, Any] = Depends(_require_admin_or_assigner)) -> List[Dict[str, Any]]:
    docs = await db.assignment_plans.find({}).sort("updated_at", -1).to_list(500)
    return [strip_mongo_id(d) for d in docs]


@api.post("/schedule-assignment-plans")
async def create_assignment_plan(payload: AssignmentPlanIn,
                                 current: Dict[str, Any] = Depends(_require_admin_or_assigner)) -> Dict[str, Any]:
    name = (payload.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="El nombre de la planificación es obligatorio")
    if len(name) > 80:
        raise HTTPException(status_code=400, detail="El nombre no puede exceder 80 caracteres")
    if payload.from_date > payload.to_date:
        raise HTTPException(status_code=400, detail="Rango de fechas inválido")
    if await db.assignment_plans.find_one({"name": name}):
        raise HTTPException(status_code=409, detail="Ya existe una planificación con ese nombre")

    # Validación: detectar planes previos cuyo rango se cruce con el nuevo
    # Y COMPARTAN AL MENOS UN EMPLEADO (regla feb-2026 — se permite coexistencia
    # de planes simultáneos con equipos disjuntos).
    overlapping = await _find_overlapping_plans(
        payload.from_date, payload.to_date, user_ids=payload.user_ids,
    )
    if overlapping and not payload.overwrite:
        raise HTTPException(status_code=409, detail={
            "code": "plan_range_overlap",
            "message": "Ya existen planificaciones que solapan fechas y comparten empleados con el nuevo.",
            "conflicts": overlapping,
        })
    if overlapping and payload.overwrite:
        # El usuario confirmó "reescribir" → eliminamos los planes previos solapados.
        # Las asignaciones diarias (schedule_assignments) NO se tocan; se conservan.
        await db.assignment_plans.delete_many({
            "plan_id": {"$in": [p["plan_id"] for p in overlapping]}
        })

    # Validación de la matriz enviada (antes de escribir nada).
    if payload.assignments:
        await _validate_plan_assignments(payload.assignments)

    now = now_utc()
    doc = {
        "plan_id": new_id("plan", 10),
        "name": name,
        "from_date": payload.from_date,
        "to_date": payload.to_date,
        "user_ids": payload.user_ids,
        "row_order": payload.row_order or [],
        "created_by": current["user_id"],
        "created_at": now,
        "updated_at": now,
    }
    await db.assignment_plans.insert_one(doc)
    if payload.assignments is not None:
        await _replace_plan_assignments(
            payload.user_ids, payload.from_date, payload.to_date,
            payload.assignments, current["user_id"],
        )
    await _prune_out_of_range_assignments(payload.user_ids, payload.from_date, payload.to_date)
    return strip_mongo_id(doc)


@api.put("/schedule-assignment-plans/{plan_id}")
async def update_assignment_plan(plan_id: str, payload: AssignmentPlanIn,
                                 current: Dict[str, Any] = Depends(_require_admin_or_assigner)) -> Dict[str, Any]:
    name = (payload.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="El nombre es obligatorio")
    if len(name) > 80:
        raise HTTPException(status_code=400, detail="El nombre no puede exceder 80 caracteres")
    if payload.from_date > payload.to_date:
        raise HTTPException(status_code=400, detail="Rango de fechas inválido")
    dup = await db.assignment_plans.find_one({"name": name, "plan_id": {"$ne": plan_id}})
    if dup:
        raise HTTPException(status_code=409, detail="Ya existe otra planificación con ese nombre")

    # Validación de solape con OTROS planes (excluyendo el actual) que compartan empleados.
    overlapping = await _find_overlapping_plans(
        payload.from_date, payload.to_date,
        exclude_plan_id=plan_id, user_ids=payload.user_ids,
    )
    if overlapping and not payload.overwrite:
        raise HTTPException(status_code=409, detail={
            "code": "plan_range_overlap",
            "message": "El nuevo rango solapa a otras planificaciones que comparten empleados.",
            "conflicts": overlapping,
        })
    if overlapping and payload.overwrite:
        await db.assignment_plans.delete_many({
            "plan_id": {"$in": [p["plan_id"] for p in overlapping]}
        })

    # Validación de la matriz enviada (antes de escribir nada).
    if payload.assignments:
        await _validate_plan_assignments(payload.assignments)

    # Usuarios previos del plan (para limpiar líneas de empleados removidos).
    prev = await db.assignment_plans.find_one({"plan_id": plan_id})
    if not prev:
        raise HTTPException(status_code=404, detail="Planificación no encontrada")

    res = await db.assignment_plans.update_one(
        {"plan_id": plan_id},
        {"$set": {
            "name": name,
            "from_date": payload.from_date,
            "to_date": payload.to_date,
            "user_ids": payload.user_ids,
            "row_order": payload.row_order or [],
            "updated_at": now_utc(),
            "updated_by": current["user_id"],
        }},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Planificación no encontrada")
    if payload.assignments is not None:
        removed = [u for u in (prev.get("user_ids") or []) if u not in set(payload.user_ids)]
        await _replace_plan_assignments(
            payload.user_ids, payload.from_date, payload.to_date,
            payload.assignments, current["user_id"], extra_user_ids=removed,
        )
    await _prune_out_of_range_assignments(payload.user_ids, payload.from_date, payload.to_date)
    doc = await db.assignment_plans.find_one({"plan_id": plan_id})
    return strip_mongo_id(doc)


@api.delete("/schedule-assignment-plans/{plan_id}")
async def delete_assignment_plan(plan_id: str,
                                 _: Dict[str, Any] = Depends(_require_admin_or_assigner)) -> Dict[str, bool]:
    res = await db.assignment_plans.delete_one({"plan_id": plan_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Planificación no encontrada")
    return {"ok": True}


@api.post("/schedule-assignments/clear")
async def bulk_clear(payload: AssignmentClearIn,
                     _: Dict[str, Any] = Depends(_require_admin_or_assigner)) -> Dict[str, Any]:
    """Elimina asignaciones para el conjunto de (user_id × date).

    Si el payload trae `cells`, se borran EXACTAMENTE esos pares (modo
    selección exacta — evita eliminar celdas no seleccionadas cuando la
    selección no es rectangular)."""
    if payload.cells:
        result = await db.schedule_assignments.delete_many({
            "$or": [{"user_id": c.user_id, "date": c.date} for c in payload.cells],
        })
        return {"ok": True, "deleted": result.deleted_count}
    if not payload.user_ids or not payload.dates:
        raise HTTPException(status_code=400, detail="Debes indicar user_ids y dates")
    result = await db.schedule_assignments.delete_many({
        "user_id": {"$in": payload.user_ids},
        "date": {"$in": payload.dates},
    })
    return {"ok": True, "deleted": result.deleted_count}
