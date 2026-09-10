"""Endpoints de estadísticas y reportes (executive summary, dashboard, CSV export).

Migrado desde server.py durante la Fase A · Iteración 2 (feb-2026).
"""
import io
import csv
from deps import (
    api, db, get_current_user, require_roles,
    LEADER_ROLES, APP_TZ,
    now_utc, strip_mongo_id, supervisor_scope_ids, _parse_date_range,
    HTTPException, Depends, Query,
    Any, Dict, List, Optional,
    datetime, timezone, timedelta,
)
from fastapi.responses import StreamingResponse


def _process_late_record(r: Dict[str, Any], u_info: Dict[str, Any], depts: Dict[str, str], per_user: Dict[str, Dict[str, Any]]) -> int:
    minutes = int(r.get("late_minutes") or 0)
    uid = r.get("user_id", "")
    u = per_user.setdefault(uid, {
        "user_id": uid,
        "name": u_info.get("name", uid),
        "cedula": u_info.get("cedula"),
        "position": u_info.get("position"),
        "department_name": depts.get(u_info.get("department_id") or "", "Sin departamento"),
        "late_count": 0,
        "total_minutes": 0,
    })
    u["late_count"] += 1
    u["total_minutes"] += minutes
    return minutes


def _build_dept_ranking(per_dept_total: Dict[str, int], per_dept_late: Dict[str, int], depts: Dict[str, str]) -> List[Dict[str, Any]]:
    dept_ranking = []
    for dept_id, total in per_dept_total.items():
        late = per_dept_late.get(dept_id, 0)
        dept_ranking.append({
            "department_id": None if dept_id == "__none" else dept_id,
            "department_name": depts.get(dept_id, "Sin departamento"),
            "total_ins": total,
            "late": late,
            "late_pct": round((late / total) * 100, 1) if total else 0,
        })
    dept_ranking.sort(key=lambda x: x["late_pct"], reverse=True)
    return dept_ranking


@api.get("/stats/executive")
async def stats_executive(days: int = 30,
                          user: Dict[str, Any] = Depends(require_roles("admin", "coordinador", "gerente", "director"))) -> Dict[str, Any]:
    """Métricas ejecutivas: top tardanzas, ranking por depto, promedio minutos tarde."""
    since = now_utc() - timedelta(days=days)
    q: Dict[str, Any] = {"timestamp": {"$gte": since}, "type": "in"}
    scope_users_q: Dict[str, Any] = {}

    if user["role"] in LEADER_ROLES:
        team_ids = await supervisor_scope_ids(user)
        q["user_id"] = {"$in": team_ids}
        scope_users_q = {"user_id": {"$in": team_ids}}

    users = {u["user_id"]: u async for u in db.users.find(scope_users_q, {
        "user_id": 1, "name": 1, "email": 1, "cedula": 1,
        "department_id": 1, "position": 1, "picture": 1, "_id": 0,
    })}
    depts = {d["department_id"]: d["name"] async for d in db.departments.find({}, {"department_id": 1, "name": 1, "_id": 0})}

    per_user: Dict[str, Dict[str, Any]] = {}
    per_dept_late: Dict[str, int] = {}
    per_dept_total: Dict[str, int] = {}
    total_ins = total_late = total_late_minor = total_late_major = total_late_major_pending = total_late_minutes = 0

    async for r in db.attendance.find(q, {
        "user_id": 1, "is_late": 1, "late_minutes": 1, "late_severity": 1,
        "requires_justification": 1, "justification": 1, "justification_status": 1, "_id": 0,
    }):
        total_ins += 1
        uid = r.get("user_id", "")
        u_info = users.get(uid, {})
        dept_id = u_info.get("department_id") or "__none"
        per_dept_total[dept_id] = per_dept_total.get(dept_id, 0) + 1

        if not r.get("is_late") or r.get("justification_status") == "approved":
            continue

        total_late += 1
        total_late_minutes += _process_late_record(r, u_info, depts, per_user)
        per_dept_late[dept_id] = per_dept_late.get(dept_id, 0) + 1

        sev = r.get("late_severity") or ("late_major" if int(r.get("late_minutes") or 0) > 30 else "late_minor")
        if sev == "late_major":
            total_late_major += 1
            if (r.get("justification_status") or "none") in ("none", "pending"):
                total_late_major_pending += 1
        else:
            total_late_minor += 1

    top_late = sorted(per_user.values(), key=lambda x: (x["late_count"], x["total_minutes"]), reverse=True)[:5]
    dept_ranking = _build_dept_ranking(per_dept_total, per_dept_late, depts)

    return {
        "days": days,
        "since": since.isoformat(),
        "generated_at": now_utc().isoformat(),
        "total_check_ins": total_ins,
        "total_late": total_late,
        "total_late_minor": total_late_minor,
        "total_late_major": total_late_major,
        "total_late_major_pending": total_late_major_pending,
        "late_pct": round((total_late / total_ins) * 100, 1) if total_ins else 0,
        "avg_late_minutes": round(total_late_minutes / total_late, 1) if total_late else 0,
        "top_late": top_late,
        "department_ranking": dept_ranking[:8],
    }


@api.get("/stats/dashboard")
async def stats_dashboard(user: Dict[str, Any] = Depends(require_roles("admin", "coordinador", "gerente", "director"))) -> Dict[str, Any]:
    since = now_utc().replace(hour=0, minute=0, second=0, microsecond=0)
    q: Dict[str, Any] = {"timestamp": {"$gte": since}}
    if user["role"] in LEADER_ROLES:
        team_ids = await supervisor_scope_ids(user)
        q["user_id"] = {"$in": team_ids}

    ins = await db.attendance.count_documents({**q, "type": "in"})
    outs = await db.attendance.count_documents({**q, "type": "out"})
    late = await db.attendance.count_documents({**q, "type": "in", "is_late": True, "justification_status": {"$ne": "approved"}})

    novelties_q: Dict[str, Any] = {"status": "approved"}
    today_str = since.strftime("%Y-%m-%d")
    novelties_q["start_date"] = {"$lte": today_str}
    novelties_q["end_date"] = {"$gte": today_str}
    if user["role"] in LEADER_ROLES:
        team_ids = await supervisor_scope_ids(user)
        novelties_q["user_id"] = {"$in": team_ids}

    active_novelties = await db.novelties.count_documents(novelties_q)

    # NUEVO: Calcular empleados totales y empleados con rostro registrado.
    user_q: Dict[str, Any] = {}
    if user["role"] in LEADER_ROLES:
        team_ids = await supervisor_scope_ids(user)
        user_q["user_id"] = {"$in": team_ids}

    total_users = await db.users.count_documents(user_q)
    onboarded_users = await db.users.count_documents({**user_q, "onboarded": True})

    return {
        "date": today_str,
        "check_ins_today": ins,
        "check_outs_today": outs,
        "late_today": late,
        "active_novelties_today": active_novelties,
        "total_users": total_users,
        "onboarded_users": onboarded_users,
    }

@api.get("/reports/export-csv")
async def reports_export_csv(start_date: Optional[str] = Query(None),
                             end_date: Optional[str] = Query(None),
                             user: Dict[str, Any] = Depends(require_roles("admin", "coordinador", "gerente", "director"))) -> StreamingResponse:
    start_dt, end_dt = _parse_date_range(start_date, end_date)
    q: Dict[str, Any] = {"timestamp": {"$gte": start_dt, "$lte": end_dt}}

    if user["role"] in LEADER_ROLES:
        team_ids = await supervisor_scope_ids(user)
        q["user_id"] = {"$in": team_ids}

    docs = await db.attendance.find(q).sort("timestamp", -1).to_list(50000)
    u_ids = list({d["user_id"] for d in docs if "user_id" in d})
    users_map = {u["user_id"]: u async for u in db.users.find({"user_id": {"$in": u_ids}}, {
        "user_id": 1, "name": 1, "cedula": 1, "email": 1,
        "department_id": 1, "site_id": 1, "position": 1, "_id": 0,
    })}
    depts_map = {d["department_id"]: d["name"] async for d in db.departments.find({}, {"department_id": 1, "name": 1, "_id": 0})}
    sites_map = {s["site_id"]: s["name"] async for s in db.sites.find({}, {"site_id": 1, "name": 1, "_id": 0})}

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Fecha/Hora", "ID Usuario", "Nombre", "Cédula", "Email",
        "Departamento", "Sede", "Cargo", "Tipo", "Método",
        "Tardanza", "Minutos Tarde", "Gravedad", "Estado Justificación", "Justificación",
    ])

    for d in docs:
        u_info = users_map.get(d.get("user_id"), {})
        ts = d.get("timestamp")
        local_ts = ts.astimezone(APP_TZ).strftime("%Y-%m-%d %H:%M:%S") if ts else ""
        writer.writerow([
            local_ts, d.get("user_id"), u_info.get("name"), u_info.get("cedula"), u_info.get("email"),
            depts_map.get(u_info.get("department_id"), ""), sites_map.get(u_info.get("site_id"), ""),
            u_info.get("position"), d.get("type"), d.get("method"),
            "Sí" if d.get("is_late") else "No", d.get("late_minutes") or 0,
            d.get("late_severity") or "", d.get("justification_status") or "", d.get("justification") or "",
        ])

    output.seek(0)
    filename = f"asistencia_{start_date or 'inicio'}_a_{end_date or 'fin'}.csv"
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode("utf-8-sig")),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
