"""Reporte matricial de asistencia y novedades (v2).

Cambios vs v1:
- Soporta filtro por `schedule_id` (tipo de horario).
- Cada día se representa con una lista de BLOQUES de marcaje según el horario:
    · Horarios con 2 bloques (Día Completo) → 4 casillas (E1, S1, E2, S2)
    · Horarios con 1 bloque (Turno Corrido/Nocturno) → 2 casillas (E, S)
- Novedades de "día completo" (vacation, leave, remote) fusionan las casillas.
- Novedades parciales (medical, permission) NO reemplazan los marcajes; se devuelven en
  `partial_novelties` (una lista por empleado) para render como sub-fila.
- Cada marcaje "in" incluye `late` (True si el timestamp > horario_inicio + tolerancia).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone, date as dtdate
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

APP_TZ = ZoneInfo("America/Caracas")

FULL_DAY_TYPES = {"vacation", "leave", "remote"}
PARTIAL_TYPES = {"medical", "permission", "client_visit"}

NOVELTY_LABEL = {
    "vacation":     "VACACIONES",
    "leave":        "REPOSO",
    "medical":      "Cita médica",
    "permission":   "Permiso",
    "remote":       "TRABAJO REMOTO",
    "client_visit": "Visita a Clientes/Integradores",
    "other":        "Novedad",
}

STATUS_NORMAL = "normal"
STATUS_ABSENT = "absent"
STATUS_FUTURE = "future"
STATUS_NON_WORKING = "non_working"
STATUS_FULL_NOVELTY = "novelty_full"  # cubre todo el día (vacation/leave/remote)


def _iter_dates(from_d: str, to_d: str) -> List[str]:
    d1 = dtdate.fromisoformat(from_d)
    d2 = dtdate.fromisoformat(to_d)
    out = []
    while d1 <= d2:
        out.append(d1.isoformat())
        d1 += timedelta(days=1)
    return out


def _is_working_day(iso: str) -> bool:
    return dtdate.fromisoformat(iso).weekday() < 5


def _in_range(day: str, start: Optional[str], end: Optional[str]) -> bool:
    return bool(start and end and start <= day <= end)


def _to_minutes(hhmm: str) -> Optional[int]:
    """Convierte '08:00' o '8:00am'/'8:00pm' a minutos desde medianoche."""
    if not hhmm:
        return None
    s = hhmm.strip().lower().replace(" ", "")
    ampm = None
    if s.endswith("am"): ampm, s = "am", s[:-2]
    elif s.endswith("pm"): ampm, s = "pm", s[:-2]
    try:
        h, m = s.split(":")
        h = int(h); m = int(m)
    except Exception:
        return None
    if ampm == "pm" and h < 12: h += 12
    if ampm == "am" and h == 12: h = 0
    return h * 60 + m


SPECIAL_SCHEDULE_ID = "__special"


async def build_matrix(
    db,
    from_date: str,
    to_date: str,
    scope_user_ids: Optional[List[str]] = None,
    department_ids: Optional[List[str]] = None,
    user_ids: Optional[List[str]] = None,
    site_id: Optional[str] = None,
    schedule_id: Optional[str] = None,
) -> Dict[str, Any]:
    days = _iter_dates(from_date, to_date)
    if not days:
        return {"from_date": from_date, "to_date": to_date, "days": days,
                "schedule": None, "blocks_per_day": 1, "rows": []}

    # Modo especial: usuarios SIN horario fijo — sus bloques/tolerancia vienen
    # del turno asignado en Planificación (schedule_assignments) por día.
    is_special = schedule_id == SPECIAL_SCHEDULE_ID
    if is_special:
        schedule_id = None  # No filtramos por schedule_id fijo

    # ---- Determinar horario y # de bloques ----
    schedule: Optional[Dict[str, Any]] = None
    blocks_per_day = 1  # default → 1 bloque, 2 casillas por día (E, S)
    if is_special:
        blocks_per_day = 2  # reserva espacio para turnos rotativos de hasta 2 bloques
    if schedule_id:
        schedule = await db.schedules.find_one({"schedule_id": schedule_id})
        if schedule:
            blocks_per_day = max(1, len(schedule.get("blocks") or []))

    tolerance = int((schedule or {}).get("tolerance_minutes") or 10)
    just_tolerance = int((schedule or {}).get("justification_tolerance_minutes") or 0)

    # bloques en minutos (para determinar tardanza y agrupar marcajes)
    block_mins: List[Dict[str, Optional[int]]] = []
    for b in (schedule or {}).get("blocks", []):
        block_mins.append({"start": _to_minutes(b.get("start", "")),
                           "end": _to_minutes(b.get("end", ""))})
    if not block_mins:
        block_mins = [{"start": None, "end": None}]

    # ---- Filtro de usuarios ----
    uq: Dict[str, Any] = {}
    if scope_user_ids is not None:
        uq["user_id"] = {"$in": scope_user_ids}
    if user_ids:
        allowed = set(scope_user_ids) if scope_user_ids is not None else None
        picked = [u for u in user_ids if (allowed is None or u in allowed)]
        uq["user_id"] = {"$in": picked}
    if department_ids:
        uq["department_id"] = {"$in": department_ids}
    if site_id:
        uq["site_id"] = site_id

    # ---- Schedule Assignments (planificación diaria para personal rotativo) ----
    # Se cargan siempre para poder mostrar novedades asignadas y — cuando hay filtro
    # de schedule_id — incluir en la matriz a los empleados sin horario fijo que
    # tienen turno asignado para ese horario dentro del rango.
    assignments_map: Dict[str, Dict[str, Dict[str, Any]]] = {}
    if is_special:
        # Modo "Horario Especial": TODOS los empleados sin horario fijo.
        uq["$or"] = [{"schedule_id": None}, {"schedule_id": ""}, {"schedule_id": {"$exists": False}}]
    elif schedule_id:
        # Empleados con turno asignado para el schedule_id filtrado en la ventana
        matching_asg = await db.schedule_assignments.find({
            "kind": "shift",
            "schedule_id": schedule_id,
            "date": {"$gte": from_date, "$lte": to_date},
        }, {"user_id": 1}).to_list(50000)
        extra_uids = list({a["user_id"] for a in matching_asg})
        if extra_uids:
            existing_or = uq.pop("user_id", None)
            base_filter = {"schedule_id": schedule_id}
            if existing_or:
                base_filter["user_id"] = existing_or
            uq["$or"] = [base_filter, {"user_id": {"$in": extra_uids}}]
        else:
            uq["schedule_id"] = schedule_id
    users = await db.users.find(uq, {
        "user_id": 1, "name": 1, "cedula": 1, "email": 1,
        "department_id": 1, "position": 1, "site_id": 1, "schedule_id": 1,
    }).sort("name", 1).to_list(5000)

    if not users:
        return {"from_date": from_date, "to_date": to_date, "days": days,
                "schedule": _schedule_dto(schedule), "blocks_per_day": blocks_per_day, "rows": []}

    uid_list = [u["user_id"] for u in users]
    dept_map = {d["department_id"]: d["name"]
                async for d in db.departments.find({}, {"department_id": 1, "name": 1})}
    site_map = {s["site_id"]: s["name"]
                async for s in db.sites.find({}, {"site_id": 1, "name": 1})}

    # ---- Attendance ----
    d1 = datetime.fromisoformat(from_date).replace(tzinfo=APP_TZ).astimezone(timezone.utc)
    d2 = (datetime.fromisoformat(to_date) + timedelta(days=1)).replace(tzinfo=APP_TZ).astimezone(timezone.utc)
    att_docs = await db.attendance.find({
        "user_id": {"$in": uid_list},
        "timestamp": {"$gte": d1, "$lt": d2},
    }, {"selfie_base64": 0}).to_list(20000)

    # user × day → {ins: [{ts, site}, ...], outs: [{ts, site}, ...]}
    att_map: Dict[str, Dict[str, Dict[str, List[Any]]]] = {}
    for a in att_docs:
        ts = a.get("timestamp")
        if not isinstance(ts, datetime):
            continue
        local = ts.astimezone(APP_TZ)
        day = local.strftime("%Y-%m-%d")
        bucket = att_map.setdefault(a["user_id"], {}).setdefault(day, {"ins": [], "outs": []})
        entry = {"ts": local, "site": a.get("site_id")}
        if a.get("type") == "in":
            bucket["ins"].append(entry)
        elif a.get("type") == "out":
            bucket["outs"].append(entry)

    # ---- Novedades aprobadas ----
    nov_docs = await db.novelties.find({
        "user_id": {"$in": uid_list},
        "status": "approved",
        "start_date": {"$lte": to_date},
        "end_date": {"$gte": from_date},
    }).to_list(10000)
    novs_by_user: Dict[str, List[Dict[str, Any]]] = {}
    for n in nov_docs:
        novs_by_user.setdefault(n["user_id"], []).append(n)

    # ---- Cargar asignaciones diarias (turnos rotativos + novedades) ----
    asg_docs = await db.schedule_assignments.find({
        "user_id": {"$in": uid_list},
        "date": {"$gte": from_date, "$lte": to_date},
    }).to_list(50000)
    for a in asg_docs:
        assignments_map.setdefault(a["user_id"], {})[a["date"]] = a

    # ---- Cache de todos los horarios (necesario en modo especial para
    # resolver el turno asignado por día en cada usuario) ----
    schedules_by_id: Dict[str, Dict[str, Any]] = {}
    if is_special:
        async for s in db.schedules.find({}):
            bm = []
            for b in s.get("blocks") or []:
                bm.append({"start": _to_minutes(b.get("start", "")),
                           "end": _to_minutes(b.get("end", ""))})
            if not bm:
                bm = [{"start": None, "end": None}]
            schedules_by_id[s["schedule_id"]] = {
                "name": s.get("name"),
                "block_mins": bm,
                "tolerance": int(s.get("tolerance_minutes") or 10),
                "just_tolerance": int(s.get("justification_tolerance_minutes") or 0),
                "blocks_len": len(s.get("blocks") or []) or 1,
            }

    today_iso = datetime.now(APP_TZ).strftime("%Y-%m-%d")

    rows: List[Dict[str, Any]] = []
    for u in users:
        uid = u["user_id"]
        att_days = att_map.get(uid, {})
        novs = novs_by_user.get(uid, [])

        totals = {
            "lost_minutes": 0, "late_justified": 0, "late_unjustified": 0,
            "vacation_days": 0, "leave_days": 0, "remote_days": 0,
            "permission_days": 0, "medical_days": 0, "client_visit_days": 0,
            "absent_days": 0,
        }
        partial_novelties: List[Dict[str, Any]] = []
        cells: Dict[str, Any] = {}

        for day in days:
            cell = {"blocks": [], "status": STATUS_NORMAL, "novelty_type": None,
                    "novelty_label": None, "reason": None}

            # Asignación diaria (turno rotativo o novedad planificada) para este día.
            # Se verifica ANTES del filtro de futuro para poder previsualizar el plan.
            day_asg = assignments_map.get(uid, {}).get(day)

            # Efectivo por día: en modo "Horario Especial" cada día usa el turno
            # asignado en Planificación. Fuera de ese modo, siempre usa el horario global.
            eff_block_mins = block_mins
            eff_tolerance = tolerance
            eff_has_schedule = bool(schedule) if not is_special else False
            if is_special:
                if day_asg and day_asg.get("kind") == "shift":
                    sinfo = schedules_by_id.get(day_asg.get("schedule_id"))
                    if sinfo:
                        eff_block_mins = sinfo["block_mins"]
                        eff_tolerance = sinfo["tolerance"]
                        eff_has_schedule = True

            # Novedad asignada — se comporta como novedad aprobada de día completo,
            # incluso para fechas futuras (permite planificar vacaciones/reposos).
            if day_asg and day_asg.get("kind") == "novelty":
                nt = day_asg.get("novelty_type")
                cell["status"] = STATUS_FULL_NOVELTY
                cell["novelty_type"] = nt
                cell["novelty_label"] = NOVELTY_LABEL.get(nt, "Novedad")
                cell["reason"] = "Asignada en Planificación"
                key = f"{nt}_days"
                if key in totals:
                    totals[key] += 1
                cells[day] = cell
                continue

            if day > today_iso:
                cell["status"] = STATUS_FUTURE
                cells[day] = cell
                continue

            # Novedades del día
            day_novs = [n for n in novs if _in_range(day, n.get("start_date"), n.get("end_date"))]
            full_nov = next((n for n in day_novs if n.get("type") in FULL_DAY_TYPES), None)
            partial_novs = [n for n in day_novs if n.get("type") in PARTIAL_TYPES]

            # Marcajes crudos (cada uno: {ts, site})
            ins  = sorted(att_days.get(day, {}).get("ins", []),  key=lambda x: x["ts"])
            outs = sorted(att_days.get(day, {}).get("outs", []), key=lambda x: x["ts"])

            # Novedad de día completo → no muestro marcajes
            if full_nov:
                cell["status"] = STATUS_FULL_NOVELTY
                cell["novelty_type"] = full_nov.get("type")
                cell["novelty_label"] = NOVELTY_LABEL.get(full_nov.get("type"), "Novedad")
                cell["reason"] = full_nov.get("reason")
                key = f"{full_nov.get('type')}_days"
                if key in totals:
                    totals[key] += 1
                cells[day] = cell
                continue

            # Emparejar por bloques
            user_site = u.get("site_id")
            block_records = []
            for i, bm in enumerate(eff_block_mins):
                rec = {"in": None, "out": None, "in_late": False,
                       "late_minutes": 0, "reason": None, "just": False,
                       "break_over": False, "break_excess_minutes": 0,
                       "in_site_mismatch": False, "out_site_mismatch": False}
                # in
                if i < len(ins):
                    dt_in = ins[i]["ts"]
                    rec["in"] = dt_in.strftime("%H:%M")
                    in_site = ins[i].get("site")
                    if user_site and in_site and in_site != user_site:
                        rec["in_site_mismatch"] = True
                    # La tardanza por "horario de inicio + tolerancia" SOLO aplica a
                    # la primera entrada del día (E1). Para E2+, la marcación en rojo
                    # depende exclusivamente de la regla de exceso de descanso
                    # (break_over cuando el gap S1→E2 supera 60 min).
                    if i == 0 and bm.get("start") is not None:
                        in_min = dt_in.hour * 60 + dt_in.minute
                        delta = in_min - int(bm["start"])
                        if delta > eff_tolerance:
                            rec["in_late"] = True
                            rec["late_minutes"] = max(0, delta - eff_tolerance)
                # out
                if i < len(outs):
                    rec["out"] = outs[i]["ts"].strftime("%H:%M")
                    out_site = outs[i].get("site")
                    if user_site and out_site and out_site != user_site:
                        rec["out_site_mismatch"] = True
                block_records.append(rec)

            # === Regla 3: exceso de descanso entre S1 y E2 (solo 2 bloques) ===
            if len(eff_block_mins) >= 2 and len(block_records) >= 2:
                b1, b2 = block_records[0], block_records[1]
                # Necesita S1 (b1.out) y E2 (b2.in) reales
                if b1.get("out") and b2.get("in"):
                    try:
                        s1h, s1m = map(int, b1["out"].split(":"))
                        e2h, e2m = map(int, b2["in"].split(":"))
                        gap = (e2h * 60 + e2m) - (s1h * 60 + s1m)
                        if gap > 60:
                            excess = gap - 60
                            b2["break_over"] = True
                            b2["break_excess_minutes"] = excess
                            totals["lost_minutes"] += excess
                    except Exception:
                        pass

            # === Regla 4: cierre automático S2 a las 23:59 si es día pasado ===
            # Aplica solo si el turno es de 2 bloques Y el día ya pasó Y el último
            # marcaje fue una entrada (E2 sin S2, o solo E1 sin salidas).
            if len(eff_block_mins) >= 2 and day < today_iso:
                last_block = block_records[-1]
                any_out = any(b.get("out") for b in block_records)
                # Caso: hay E2 sin S2 (o E1 y no hay ninguna salida)
                needs_auto_close = (
                    (last_block.get("in") and not last_block.get("out"))
                    or (block_records[0].get("in") and not any_out)
                )
                if needs_auto_close:
                    last_block["out"] = "23:59"
                    last_block["auto_closed"] = True

            # Si hay más marcajes que bloques, los últimos se concatenan al último bloque
            if len(ins) > len(eff_block_mins):
                extra_in = ins[len(eff_block_mins)]["ts"]
                block_records[-1]["in"] = block_records[-1]["in"] or extra_in.strftime("%H:%M")
            if len(outs) > len(eff_block_mins):
                block_records[-1]["out"] = outs[-1]["ts"].strftime("%H:%M")

            # Justificación / totales sobre el primer bloque tardío
            first_late = next((b for b in block_records if b["in_late"]), None)
            if first_late:
                # Busca justificación en attendance doc del "in" correspondiente
                # (Aproximación: revisamos si hay algún doc "in" del día con justification)
                has_just = any(
                    (a.get("justification") or "").strip()
                    for a in att_docs
                    if a.get("user_id") == uid and a.get("type") == "in"
                    and isinstance(a.get("timestamp"), datetime)
                    and a["timestamp"].astimezone(APP_TZ).strftime("%Y-%m-%d") == day
                )
                if has_just:
                    totals["late_justified"] += 1
                    first_late["just"] = True
                else:
                    totals["late_unjustified"] += 1
                    totals["lost_minutes"] += int(first_late["late_minutes"])

            # ¿Ausente? Sin marcajes en absoluto y día laboral
            if not ins and not outs:
                # En modo "Horario Especial" sin turno asignado para el día,
                # el empleado NO tiene obligación de marcar → no cuenta como falta.
                if is_special and not eff_has_schedule:
                    cell["status"] = STATUS_NON_WORKING
                elif _is_working_day(day):
                    cell["status"] = STATUS_ABSENT
                    totals["absent_days"] += 1
                else:
                    cell["status"] = STATUS_NON_WORKING
                cells[day] = cell
                # Novedades parciales igualmente se registran
                for pn in partial_novs:
                    partial_novelties.append({
                        "date": day, "type": pn.get("type"),
                        "label": NOVELTY_LABEL.get(pn.get("type"), "Novedad"),
                        "start_time": pn.get("start_time"), "end_time": pn.get("end_time"),
                        "reason": pn.get("reason"),
                    })
                continue

            cell["blocks"] = block_records
            cells[day] = cell

            # Novedades parciales (adicionales)
            for pn in partial_novs:
                partial_novelties.append({
                    "date": day, "type": pn.get("type"),
                    "label": NOVELTY_LABEL.get(pn.get("type"), "Novedad"),
                    "start_time": pn.get("start_time"), "end_time": pn.get("end_time"),
                    "reason": pn.get("reason"),
                })
                k = f"{pn.get('type')}_days"
                if k in totals:
                    totals[k] += 1

        rows.append({
            "user_id": uid,
            "name": u.get("name"),
            "cedula": u.get("cedula") or "",
            "email": u.get("email"),
            "department": dept_map.get(u.get("department_id")) or "",
            "position": u.get("position") or "",
            "site": site_map.get(u.get("site_id")) or "",
            "schedule_id": u.get("schedule_id"),
            "cells": cells,
            "partial_novelties": partial_novelties,
            "totals": totals,
        })

    return {
        "from_date": from_date, "to_date": to_date, "days": days,
        "schedule": _schedule_dto(schedule),
        "blocks_per_day": blocks_per_day,
        "tolerance_minutes": tolerance,
        "justification_tolerance_minutes": just_tolerance,
        "rows": rows,
    }


def _schedule_dto(s: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not s:
        return None
    return {
        "schedule_id": s.get("schedule_id"),
        "name": s.get("name"),
        "blocks": s.get("blocks") or [],
        "tolerance_minutes": s.get("tolerance_minutes"),
    }


# ==============================================================
# EXPORTS
# ==============================================================
def _day_headers(blocks_per_day: int) -> List[str]:
    if blocks_per_day >= 2:
        return ["E1", "S1", "E2", "S2"]
    return ["E1", "S1"]


def export_xlsx(matrix: Dict[str, Any]) -> bytes:
    from io import BytesIO
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    wb = Workbook()
    ws = wb.active
    ws.title = "Matriz asistencia"

    days = matrix.get("days", [])
    bpd = matrix.get("blocks_per_day", 1)
    per_day = 2 * bpd  # 2 casillas por bloque (in/out)
    day_labels = _day_headers(bpd)

    thin = Side(border_style="thin", color="D1D5DB")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    hdr_fill = PatternFill("solid", fgColor="0F172A")
    hdr_font = Font(bold=True, color="FFFFFF")
    tot_fill = PatternFill("solid", fgColor="F1F5F9")

    static_headers = ["Empleado", "Cédula", "Depto", "Cargo", "Sede"]
    for col_idx, h in enumerate(static_headers, start=1):
        c = ws.cell(row=1, column=col_idx, value=h)
        c.font = hdr_font; c.fill = hdr_fill; c.border = border
        c.alignment = Alignment(horizontal="left", vertical="center")
        ws.cell(row=2, column=col_idx, value="").fill = hdr_fill
        ws.merge_cells(start_row=1, start_column=col_idx, end_row=2, end_column=col_idx)

    col = len(static_headers) + 1
    day_start = col
    for day in days:
        cc = ws.cell(row=1, column=col, value=day)
        cc.font = hdr_font; cc.fill = hdr_fill; cc.border = border
        cc.alignment = Alignment(horizontal="center")
        ws.merge_cells(start_row=1, start_column=col, end_row=1, end_column=col + per_day - 1)
        for i, sub in enumerate(day_labels):
            c = ws.cell(row=2, column=col + i, value=sub)
            c.font = hdr_font; c.fill = hdr_fill; c.border = border
            c.alignment = Alignment(horizontal="center")
        col += per_day

    tot_headers = ["Min. perd.", "T-J", "T-NJ", "Vac", "Rep", "Rem", "Perm", "Faltas"]
    tot_start = col
    for h in tot_headers:
        c = ws.cell(row=1, column=col, value=h)
        c.font = hdr_font; c.fill = hdr_fill; c.border = border
        c.alignment = Alignment(horizontal="center")
        ws.cell(row=2, column=col, value="").fill = hdr_fill
        ws.merge_cells(start_row=1, start_column=col, end_row=2, end_column=col)
        col += 1

    row_idx = 3
    for r in matrix.get("rows", []):
        ws.cell(row=row_idx, column=1, value=r["name"])
        ws.cell(row=row_idx, column=2, value=r["cedula"])
        ws.cell(row=row_idx, column=3, value=r["department"])
        ws.cell(row=row_idx, column=4, value=r["position"])
        ws.cell(row=row_idx, column=5, value=r["site"])
        c = day_start
        for day in days:
            cd = r["cells"].get(day, {})
            status = cd.get("status")
            if status == "novelty_full":
                # Fusiona todas las casillas del día con el texto de la novedad
                label = cd.get("novelty_label") or "Novedad"
                cell = ws.cell(row=row_idx, column=c, value=label)
                cell.alignment = Alignment(horizontal="center", vertical="center")
                cell.fill = PatternFill("solid", fgColor="DBEAFE")
                cell.font = Font(bold=True, color="1E40AF")
                ws.merge_cells(start_row=row_idx, start_column=c, end_row=row_idx, end_column=c + per_day - 1)
            elif status == "absent":
                cell = ws.cell(row=row_idx, column=c, value="FALTA")
                cell.alignment = Alignment(horizontal="center")
                cell.fill = PatternFill("solid", fgColor="FEE2E2")
                cell.font = Font(bold=True, color="991B1B")
                ws.merge_cells(start_row=row_idx, start_column=c, end_row=row_idx, end_column=c + per_day - 1)
            else:
                blocks = cd.get("blocks", [])
                offset = 0
                for i in range(bpd):
                    b = blocks[i] if i < len(blocks) else {}
                    in_val = b.get("in") or ""
                    out_val = b.get("out") or ""
                    cin = ws.cell(row=row_idx, column=c + offset, value=in_val)
                    cin.alignment = Alignment(horizontal="center")
                    if b.get("in_late") or b.get("break_over"):
                        cin.font = Font(color="B91C1C", bold=True)
                    cout = ws.cell(row=row_idx, column=c + offset + 1, value=out_val)
                    cout.alignment = Alignment(horizontal="center")
                    if b.get("auto_closed"):
                        cout.font = Font(color="B45309", italic=True)
                    offset += 2
            c += per_day
        # Totales
        t = r["totals"]
        vals = [t["lost_minutes"], t["late_justified"], t["late_unjustified"],
                t["vacation_days"], t["leave_days"], t["remote_days"],
                t["permission_days"], t["absent_days"]]
        tc = tot_start
        for v in vals:
            cell = ws.cell(row=row_idx, column=tc, value=v)
            cell.alignment = Alignment(horizontal="center")
            cell.fill = tot_fill
            tc += 1
        row_idx += 1

        # Sub-fila de novedades parciales
        if r.get("partial_novelties"):
            ws.cell(row=row_idx, column=1, value="↳ Novedades parciales").font = Font(italic=True, color="6B7280", size=9)
            for pn in r["partial_novelties"]:
                # Ubica columnas del día
                if pn["date"] in days:
                    d_idx = days.index(pn["date"])
                    c0 = day_start + d_idx * per_day
                    txt = f"{pn['label']} {pn.get('start_time') or ''}–{pn.get('end_time') or ''}"
                    cell = ws.cell(row=row_idx, column=c0, value=txt)
                    cell.font = Font(italic=True, size=9, color="1E40AF")
                    cell.alignment = Alignment(horizontal="center")
                    cell.fill = PatternFill("solid", fgColor="EFF6FF")
                    ws.merge_cells(start_row=row_idx, start_column=c0, end_row=row_idx, end_column=c0 + per_day - 1)
            row_idx += 1

    ws.freeze_panes = ws.cell(row=3, column=6)
    ws.column_dimensions["A"].width = 28
    for letter in ["B", "C", "D", "E"]:
        ws.column_dimensions[letter].width = 16

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def export_pdf(matrix: Dict[str, Any], company_name: str = "MegaSoft", logo_base64: Optional[str] = None) -> bytes:
    from io import BytesIO
    from reportlab.lib.pagesizes import landscape, A3
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
    import base64

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A3),
                            leftMargin=8 * mm, rightMargin=8 * mm,
                            topMargin=8 * mm, bottomMargin=8 * mm,
                            title="Reporte matricial de asistencia")

    styles = getSampleStyleSheet()
    h_title = ParagraphStyle("t", parent=styles["Title"], fontSize=15, textColor=colors.HexColor("#0F172A"))
    h_sub = ParagraphStyle("s", parent=styles["Normal"], fontSize=8, textColor=colors.HexColor("#64748B"))

    story: List[Any] = []
    if logo_base64 and "," in logo_base64:
        try:
            _, b64 = logo_base64.split(",", 1)
            img_bytes = BytesIO(base64.b64decode(b64))
            story.append(Image(img_bytes, width=32 * mm, height=12 * mm, hAlign="LEFT"))
        except Exception:
            pass
    sched_name = (matrix.get("schedule") or {}).get("name") or "Todos los horarios"
    story.append(Paragraph(f"{company_name} · Reporte matricial de asistencia", h_title))
    story.append(Paragraph(
        f"Rango: {matrix['from_date']} — {matrix['to_date']} · Horario: {sched_name} · "
        f"{len(matrix['rows'])} empleados · gen. {datetime.now(APP_TZ).strftime('%Y-%m-%d %H:%M')}", h_sub))
    story.append(Spacer(1, 3 * mm))

    days = matrix["days"]
    bpd = matrix.get("blocks_per_day", 1)
    per_day = 2 * bpd
    day_labels = _day_headers(bpd)

    header_top = ["Empleado", "Cédula", "Depto"]
    header_bot = ["", "", ""]
    for d in days:
        header_top.extend([d] + [""] * (per_day - 1))
        header_bot.extend(day_labels)
    tot_labels = ["Min", "T-J", "T-NJ", "Vac", "Rep", "Rem", "Perm", "Falt"]
    for tl in tot_labels:
        header_top.append(tl)
        header_bot.append("")

    data = [header_top, header_bot]
    row_style_extras: List[Any] = []

    n_static = 3
    day_start_col = n_static
    # 1 bloque (2 casillas): más ancho para aprovechar espacio horizontal.
    # 2 bloques (4 casillas): compacto para caber en la página.
    day_col_width_mm = 7 if bpd >= 2 else 13

    for r in matrix["rows"]:
        row = [r["name"], r["cedula"], r["department"]]
        row_i = len(data)
        for d_idx, day in enumerate(days):
            cd = r["cells"].get(day, {})
            status = cd.get("status")
            if status == "novelty_full":
                row.append(cd.get("novelty_label") or "Novedad")
                row.extend([""] * (per_day - 1))
                col0 = day_start_col + d_idx * per_day
                row_style_extras.append(("SPAN", (col0, row_i), (col0 + per_day - 1, row_i)))
                row_style_extras.append(("BACKGROUND", (col0, row_i), (col0 + per_day - 1, row_i),
                                         colors.HexColor("#DBEAFE")))
                row_style_extras.append(("TEXTCOLOR", (col0, row_i), (col0 + per_day - 1, row_i),
                                         colors.HexColor("#1E40AF")))
                row_style_extras.append(("FONTNAME", (col0, row_i), (col0 + per_day - 1, row_i), "Helvetica-Bold"))
            elif status == "absent":
                row.append("FALTA"); row.extend([""] * (per_day - 1))
                col0 = day_start_col + d_idx * per_day
                row_style_extras.append(("SPAN", (col0, row_i), (col0 + per_day - 1, row_i)))
                row_style_extras.append(("BACKGROUND", (col0, row_i), (col0 + per_day - 1, row_i),
                                         colors.HexColor("#FEE2E2")))
                row_style_extras.append(("TEXTCOLOR", (col0, row_i), (col0 + per_day - 1, row_i),
                                         colors.HexColor("#991B1B")))
                row_style_extras.append(("FONTNAME", (col0, row_i), (col0 + per_day - 1, row_i), "Helvetica-Bold"))
            else:
                blocks = cd.get("blocks", [])
                for i in range(bpd):
                    b = blocks[i] if i < len(blocks) else {}
                    in_val = b.get("in") or "-"
                    out_val = b.get("out") or "-"
                    row.append(in_val); row.append(out_val)
                    if b.get("in_late") or b.get("break_over"):
                        col_in = day_start_col + d_idx * per_day + i * 2
                        row_style_extras.append(("TEXTCOLOR", (col_in, row_i), (col_in, row_i),
                                                 colors.HexColor("#B91C1C")))
                        row_style_extras.append(("FONTNAME", (col_in, row_i), (col_in, row_i), "Helvetica-Bold"))
                    if b.get("auto_closed"):
                        col_out = day_start_col + d_idx * per_day + i * 2 + 1
                        row_style_extras.append(("TEXTCOLOR", (col_out, row_i), (col_out, row_i),
                                                 colors.HexColor("#B45309")))
                        row_style_extras.append(("FONTNAME", (col_out, row_i), (col_out, row_i), "Helvetica-Oblique"))
        t = r["totals"]
        row.extend([t["lost_minutes"], t["late_justified"], t["late_unjustified"],
                    t["vacation_days"], t["leave_days"], t["remote_days"],
                    t["permission_days"], t["absent_days"]])
        data.append(row)

        # Sub-fila de novedades parciales
        if r.get("partial_novelties"):
            sub_row = ["", "", "↳ " + r["name"]]
            sub_row.extend([""] * per_day * len(days))
            sub_row.extend([""] * len(tot_labels))
            sub_row_i = len(data)
            for pn in r["partial_novelties"]:
                if pn["date"] not in days:
                    continue
                d_idx = days.index(pn["date"])
                c0 = day_start_col + d_idx * per_day
                txt = f"{pn['label']} {pn.get('start_time') or ''}–{pn.get('end_time') or ''}"
                sub_row[c0] = txt
                for k in range(1, per_day):
                    sub_row[c0 + k] = ""
                row_style_extras.append(("SPAN", (c0, sub_row_i), (c0 + per_day - 1, sub_row_i)))
                row_style_extras.append(("BACKGROUND", (c0, sub_row_i), (c0 + per_day - 1, sub_row_i),
                                         colors.HexColor("#EFF6FF")))
                row_style_extras.append(("TEXTCOLOR", (c0, sub_row_i), (c0 + per_day - 1, sub_row_i),
                                         colors.HexColor("#1E40AF")))
                row_style_extras.append(("FONTNAME", (c0, sub_row_i), (c0 + per_day - 1, sub_row_i), "Helvetica-Oblique"))
            data.append(sub_row)

    col_widths = ([28 * mm, 20 * mm, 22 * mm]
                  + [day_col_width_mm * mm] * (per_day * len(days))
                  + [10 * mm] * len(tot_labels))
    table = Table(data, colWidths=col_widths, repeatRows=2)

    style = TableStyle([
        ("FONTNAME", (0, 0), (-1, 1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 6.2),
        ("BACKGROUND", (0, 0), (-1, 1), colors.HexColor("#0F172A")),
        ("TEXTCOLOR", (0, 0), (-1, 1), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D1D5DB")),
        ("ALIGN", (n_static, 0), (-1, -1), "CENTER"),
        ("ALIGN", (0, 2), (n_static - 1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ])
    for i, _d in enumerate(days):
        c = n_static + i * per_day
        style.add("SPAN", (c, 0), (c + per_day - 1, 0))
    for c in range(n_static):
        style.add("SPAN", (c, 0), (c, 1))
    for c in range(n_static + per_day * len(days),
                   n_static + per_day * len(days) + len(tot_labels)):
        style.add("SPAN", (c, 0), (c, 1))
    for extra in row_style_extras:
        style.add(*extra)

    table.setStyle(style)
    story.append(table)

    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(
        "<b>Leyenda:</b> hora en <b>negro</b>=dentro de tolerancia · "
        "<font color='#B91C1C'><b>rojo</b>=tardanza no justificada</font> · "
        "<font color='#1E40AF'>Vacaciones / Reposo / Trabajo Remoto</font> = día completo · "
        "<font color='#991B1B'>Falta</font> = día laboral sin marcaje. "
        "Novedades parciales (Cita médica / Permiso) se muestran en la sub-fila debajo del empleado.",
        h_sub))
    doc.build(story)
    return buf.getvalue()
