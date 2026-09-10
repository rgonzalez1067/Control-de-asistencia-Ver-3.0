"""Endpoints de asistencia (marcaje) y justificaciones.

Migrado desde server.py (líneas 2556-2787) durante la Fase A del refactor
(feb-2026). No cambia comportamiento — sólo reubica el código.
"""
from deps import (
    api, db, get_current_user, require_roles, LEADER_ROLES,
    now_utc, new_id, strip_mongo_id, supervisor_scope_ids, APP_TZ,
    AttendanceCheckIn, JustifyIn, JustifyDecideIn,
    datetime, timezone, timedelta,
    HTTPException, Depends,
    Any, Dict, List, Optional,
)


# ------------------------------------------------------------------
# Helper — usado por endpoints de attendance y por kiosk.
# ------------------------------------------------------------------
async def _compute_checkin_lateness(sched: Dict[str, Any], user_id: str, local_now: datetime, day_start_utc: datetime, day_end_utc: datetime):
    tol_general = int(sched.get("tolerance_minutes", 10))
    tol_justif = int(sched.get("justification_tolerance_minutes", 20))
    prior_ins = await db.attendance.count_documents({
        "user_id": user_id,
        "type": "in",
        "timestamp": {"$gte": day_start_utc, "$lt": day_end_utc},
    })
    is_late, late_min, late_severity, requires_justification = False, 0, "on_time", False

    if prior_ins == 0:
        first_block = sched["blocks"][0]
        hh, mm = map(int, first_block["start"].split(":"))
        expected = local_now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        delta = int((local_now - expected).total_seconds() // 60)
        if delta > tol_general:
            is_late, late_min = True, delta
            if delta > (tol_general + tol_justif):
                late_severity, requires_justification = "late_major", True
            else:
                late_severity = "late_minor"
    else:
        last_out = await db.attendance.find_one(
            {"user_id": user_id, "type": "out", "timestamp": {"$gte": day_start_utc, "$lt": day_end_utc}},
            sort=[("timestamp", -1)],
        )
        if last_out and last_out.get("timestamp"):
            s1_local = last_out["timestamp"].astimezone(APP_TZ)
            gap = int((local_now - s1_local).total_seconds() // 60)
            if gap > 60:
                is_late, late_min = True, gap - 60
                if late_min > tol_justif:
                    late_severity, requires_justification = "late_major", True
                else:
                    late_severity = "late_minor"

    return is_late, late_min, late_severity, requires_justification, prior_ins


async def _register_attendance(user: Dict[str, Any], type_: str,
                                latitude: Optional[float], longitude: Optional[float],
                                site_id: Optional[str], selfie_base64: Optional[str],
                                method: str = "web") -> Dict[str, Any]:
    site = None
    if site_id:
        site = await db.sites.find_one({"site_id": site_id})
    elif user.get("site_id"):
        site = await db.sites.find_one({"site_id": user["site_id"]})

    within = None
    is_late, late_min, late_severity, requires_justification = False, 0, "on_time", False
    entry_index = None

    if type_ == "in":
        local_now = now_utc().astimezone(APP_TZ)
        day_start_local = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
        day_start_utc = day_start_local.astimezone(timezone.utc)
        day_end_utc = (day_start_local + timedelta(days=1)).astimezone(timezone.utc)

        if user.get("schedule_id"):
            sched = await db.schedules.find_one({"schedule_id": user["schedule_id"]})
            if sched and sched.get("blocks"):
                is_late, late_min, late_severity, requires_justification, entry_index = await _compute_checkin_lateness(
                    sched, user["user_id"], local_now, day_start_utc, day_end_utc
                )
        else:
            entry_index = await db.attendance.count_documents({
                "user_id": user["user_id"],
                "type": "in",
                "timestamp": {"$gte": day_start_utc, "$lt": day_end_utc},
        })

    doc = {
        "record_id": new_id("att", 12),
        "user_id": user["user_id"],
        "type": type_,
        "timestamp": now_utc(),
        "latitude": latitude,
        "longitude": longitude,
        "site_id": site["site_id"] if site else site_id,
        "within_geofence": within,
        "is_late": is_late,
        "late_minutes": late_min,
        "late_severity": late_severity,
        "requires_justification": requires_justification,
        "justification": None,
        "justification_status": "none",
        "rejection_reason": None,
        "decided_by": None,
        "decided_at": None,
        "entry_index": entry_index,
        "method": method,
    }
    if selfie_base64:
        doc["selfie_base64"] = selfie_base64
    await db.attendance.insert_one(doc)
    return strip_mongo_id(doc)


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------
@api.post("/attendance/check")
async def attendance_check(payload: AttendanceCheckIn,
                           user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    return await _register_attendance(user, payload.type, payload.latitude, payload.longitude,
                                      payload.site_id, payload.selfie_base64, method="web")


@api.get("/attendance/me")
async def attendance_me(limit: int = 100,
                        user: Dict[str, Any] = Depends(get_current_user)) -> List[Dict[str, Any]]:
    docs = await db.attendance.find(
        {"user_id": user["user_id"]},
        {"selfie_base64": 0},
    ).sort("timestamp", -1).limit(limit).to_list(limit)
    return [strip_mongo_id(d) for d in docs]


@api.get("/attendance/today")
async def attendance_today(user: Dict[str, Any] = Depends(get_current_user)) -> List[Dict[str, Any]]:
    local_now = now_utc().astimezone(APP_TZ)
    start = local_now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    end = start + timedelta(days=1)
    docs = await db.attendance.find(
        {"user_id": user["user_id"], "timestamp": {"$gte": start, "$lt": end}},
        {"selfie_base64": 0},
    ).sort("timestamp", 1).to_list(50)
    return [strip_mongo_id(d) for d in docs]


@api.get("/attendance/team")
async def attendance_team(days: int = 7,
                          user: Dict[str, Any] = Depends(require_roles("admin", "coordinador", "gerente", "director"))) -> List[Dict[str, Any]]:
    query: Dict[str, Any] = {"timestamp": {"$gte": now_utc() - timedelta(days=days)}}
    if user["role"] in LEADER_ROLES:
        team = await db.users.find({"supervisor_id": user["user_id"]}, {"user_id": 1}).to_list(1000)
        team_ids = [t["user_id"] for t in team]
        query["user_id"] = {"$in": team_ids}
    docs = await db.attendance.find(query, {"selfie_base64": 0}).sort("timestamp", -1).limit(1000).to_list(1000)
    return [strip_mongo_id(d) for d in docs]


@api.post("/attendance/justify")
async def attendance_justify(payload: JustifyIn,
                             user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, bool]:
    query = {"record_id": payload.record_id}
    if user["role"] == "employee":
        query["user_id"] = user["user_id"]
    elif user["role"] in LEADER_ROLES:
        query["user_id"] = {"$in": await supervisor_scope_ids(user)}
    res = await db.attendance.update_one(
        query,
        {"$set": {
            "justification": payload.justification,
            "justification_status": "pending",
            "rejection_reason": None,
            "decided_by": None,
            "decided_at": None,
            "requires_justification": False,
        }},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Registro no encontrado")
    return {"ok": True}


@api.post("/attendance/justify/decide")
async def attendance_justify_decide(
    payload: JustifyDecideIn,
    user: Dict[str, Any] = Depends(require_roles("admin", "coordinador", "gerente", "director")),
) -> Dict[str, Any]:
    """Aprobar o rechazar la justificación de un empleado.
    - approved  → 'Retraso Justificado' (minutos NO penalizan en reportes)
    - rejected  → 'Retraso Injustificado' (minutos SÍ suman a "Minutos Perdidos")
    """
    rec = await db.attendance.find_one({"record_id": payload.record_id})
    if not rec:
        raise HTTPException(status_code=404, detail="Registro no encontrado")

    if user["role"] in LEADER_ROLES:
        team_ids = await supervisor_scope_ids(user)
        if rec.get("user_id") not in team_ids:
            raise HTTPException(status_code=403, detail="Fuera de tu equipo")

    if not rec.get("justification"):
        raise HTTPException(status_code=400,
                            detail="El registro no tiene justificación enviada por el empleado")

    if payload.decision == "rejected":
        reason = (payload.rejection_reason or "").strip()
        if len(reason) < 3:
            raise HTTPException(status_code=400, detail="La razón del rechazo es obligatoria")
        upd = {
            "justification_status": "rejected",
            "rejection_reason": reason,
            "decided_by": user["user_id"],
            "decided_at": now_utc(),
        }
    else:
        upd = {
            "justification_status": "approved",
            "rejection_reason": None,
            "decided_by": user["user_id"],
            "decided_at": now_utc(),
        }

    await db.attendance.update_one({"record_id": payload.record_id}, {"$set": upd})
    return {"ok": True, "status": upd["justification_status"]}
