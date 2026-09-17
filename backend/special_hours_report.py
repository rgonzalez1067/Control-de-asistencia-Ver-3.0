"""Reporte Consolidado de Horas y Conceptos para Turnos Especiales (sep-2026).

Solo empleados con Horario Especial (rotativos/monitoreo, sin schedule_id fijo).
Conceptos:
- dias_total = (to - from) + 1
- dias_trabajados = días con turno asignado (kind=shift) O novedad remote aprobada
- horas_diurnas / horas_nocturnas = horas del turno del día, en días trabajados
  ordinarios (NO domingo ni festivo)
- feriadas_diurnas / feriadas_nocturnas = horas del turno del día en días
  trabajados que sean domingo o festivo del calendario
- horas_descanso = (dias_total - dias_trabajados) × horas_diurnas del turno
  más frecuente asignado al empleado en el periodo (0 si nunca tuvo turno)

Salida: matriz JSON + XLSX oficial.
"""
import base64
from collections import Counter
from datetime import date as _date, datetime, timedelta
from io import BytesIO
from typing import Any, Dict, List, Optional

from deps import APP_TZ, now_utc


def _iter_dates(from_date: str, to_date: str) -> List[str]:
    a = _date.fromisoformat(from_date)
    b = _date.fromisoformat(to_date)
    if b < a:
        return []
    return [(a + timedelta(days=i)).strftime("%Y-%m-%d") for i in range((b - a).days + 1)]


def _in_range(day: str, start: Optional[str], end: Optional[str]) -> bool:
    if not start:
        return False
    if not end:
        end = start
    return start <= day <= end


async def build_special_hours_report(db, from_date: str, to_date: str,
                                     user_ids: Optional[List[str]] = None,
                                     department_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    days = _iter_dates(from_date, to_date)
    days_total = len(days)

    uq: Dict[str, Any] = {
        "$or": [{"schedule_id": None}, {"schedule_id": ""}, {"schedule_id": {"$exists": False}}],
    }
    if user_ids:
        uq["user_id"] = {"$in": user_ids}
    if department_ids:
        uq["department_id"] = {"$in": department_ids}

    users = await db.users.find(uq, {
        "user_id": 1, "cedula": 1, "name": 1, "first_name": 1, "last_name": 1,
        "department_id": 1, "_id": 0,
    }).sort("name", 1).to_list(5000)
    uid_list = [u["user_id"] for u in users]

    depts = {d["department_id"]: d["name"] async for d in db.departments.find({}, {"department_id": 1, "name": 1, "_id": 0})}

    schedules_by_id: Dict[str, Dict[str, Any]] = {
        s["schedule_id"]: s async for s in db.schedules.find({}, {
            "schedule_id": 1, "name": 1, "daytime_hours": 1, "nighttime_hours": 1, "_id": 0,
        })
    }

    asg_docs = await db.schedule_assignments.find({
        "user_id": {"$in": uid_list},
        "date": {"$gte": from_date, "$lte": to_date},
    }).to_list(50000)
    asg_by_user: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for a in asg_docs:
        asg_by_user.setdefault(a["user_id"], {})[a["date"]] = a

    nov_docs = await db.novelties.find({
        "user_id": {"$in": uid_list},
        "type": "remote",
        "status": "approved",
        "start_date": {"$lte": to_date},
        "end_date": {"$gte": from_date},
    }).to_list(10000)
    remote_by_user: Dict[str, List[Dict[str, Any]]] = {}
    for n in nov_docs:
        remote_by_user.setdefault(n["user_id"], []).append(n)

    holiday_docs = await db.holidays.find({}, {"date_str": 1, "is_recurrent": 1, "_id": 0}).to_list(5000)
    holiday_days = set()
    for h in holiday_docs:
        d = h.get("date_str") or ""
        if not d:
            continue
        if h.get("is_recurrent"):
            mmdd = d[5:]
            for day in days:
                if day[5:] == mmdd:
                    holiday_days.add(day)
        elif d in days:
            holiday_days.add(d)

    rows: List[Dict[str, Any]] = []
    for u in users:
        uid = u["user_id"]
        asg_map = asg_by_user.get(uid, {})
        remotes = remote_by_user.get(uid, [])

        # Turno más frecuente del empleado en el periodo (solo shifts) — base
        # para el cálculo de Descanso y para días remote sin turno del día.
        shift_ids = [a.get("schedule_id") for d, a in asg_map.items()
                     if a.get("kind") == "shift" and a.get("schedule_id")]
        top_sid = Counter(shift_ids).most_common(1)[0][0] if shift_ids else None
        top_sch = schedules_by_id.get(top_sid) if top_sid else None
        top_day_h = float((top_sch or {}).get("daytime_hours") or 0)
        top_night_h = float((top_sch or {}).get("nighttime_hours") or 0)

        dias_trabajados = 0
        horas_diurnas = 0.0
        horas_nocturnas = 0.0
        feriadas_diurnas = 0.0
        feriadas_nocturnas = 0.0

        for day in days:
            day_dt = _date.fromisoformat(day)
            is_sunday = day_dt.weekday() == 6
            is_holiday = day in holiday_days
            is_special_day = is_sunday or is_holiday

            asg = asg_map.get(day)
            has_shift = bool(asg and asg.get("kind") == "shift" and asg.get("schedule_id"))
            # Trabajo Remoto llega por dos vías: novedad aprobada (colección
            # `novelties`) o asignación planificada en la matriz
            # (`schedule_assignments` con kind=novelty / novelty_type=remote).
            has_remote = (
                any(_in_range(day, n.get("start_date"), n.get("end_date")) for n in remotes)
                or bool(asg and asg.get("kind") == "novelty" and asg.get("novelty_type") == "remote")
            )

            if not has_shift and not has_remote:
                continue  # día libre → contribuye a Descanso más abajo

            dias_trabajados += 1

            if has_shift:
                sinfo = schedules_by_id.get(asg["schedule_id"]) or {}
                day_h = float(sinfo.get("daytime_hours") or 0)
                night_h = float(sinfo.get("nighttime_hours") or 0)
            else:
                # Remote sin turno del día → usa turno más frecuente del periodo.
                day_h = top_day_h
                night_h = top_night_h

            if is_special_day:
                feriadas_diurnas += day_h
                feriadas_nocturnas += night_h
            else:
                horas_diurnas += day_h
                horas_nocturnas += night_h

        dias_libres = days_total - dias_trabajados
        # Descanso = días libres × total de horas del turno (diurnas + nocturnas
        # sin diferenciar). Turno base = el más frecuente asignado en el periodo.
        horas_descanso = dias_libres * (top_day_h + top_night_h)

        rows.append({
            "user_id": uid,
            "cedula": u.get("cedula") or "",
            "nombre": u.get("name") or f"{u.get('first_name','')} {u.get('last_name','')}".strip(),
            "departamento": depts.get(u.get("department_id") or "", "—"),
            "dias_total": days_total,
            "dias_trabajados": dias_trabajados,
            "horas_diurnas": round(horas_diurnas, 2),
            "horas_nocturnas": round(horas_nocturnas, 2),
            "feriadas_diurnas": round(feriadas_diurnas, 2),
            "feriadas_nocturnas": round(feriadas_nocturnas, 2),
            "horas_descanso": round(horas_descanso, 2),
            "turno_referencia": (top_sch or {}).get("name") or "—",
        })

    return {
        "from_date": from_date,
        "to_date": to_date,
        "days_total": days_total,
        "generated_at": now_utc().isoformat(),
        "rows_count": len(rows),
        "rows": rows,
    }


def export_special_hours_xlsx(report: Dict[str, Any],
                              company_name: str = "Mega Soft",
                              logo_base64: Optional[str] = None) -> bytes:
    from openpyxl import Workbook
    from openpyxl.drawing.image import Image as XLImage
    from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = "Horas · Turnos Especiales"

    thin = Side(style="thin", color="CBD5E1")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    dark_fill = PatternFill("solid", fgColor="0F172A")
    amber_fill = PatternFill("solid", fgColor="FEF3C7")
    ger_font = Font(bold=True, color="B45309", size=10)

    ws.merge_cells("A1:J1")
    ws["A1"] = f"{company_name} · Reporte de Horas Trabajadas — Turnos Especiales"
    ws["A1"].font = Font(bold=True, color="0F172A", size=14)
    ws["A1"].alignment = Alignment(vertical="center")
    ws.row_dimensions[1].height = 26

    ws.merge_cells("A2:J2")
    ws["A2"] = "Gerencia de Seguridad de la Información · Unidad generadora del reporte"
    ws["A2"].font = ger_font
    ws["A2"].alignment = Alignment(vertical="center")

    ws.merge_cells("A3:J3")
    ws["A3"] = (f"Período: {report['from_date']} — {report['to_date']} · "
                f"{report['days_total']} días · {report['rows_count']} empleados · "
                f"Generado: {datetime.now(APP_TZ).strftime('%d/%m/%Y %H:%M')}")
    ws["A3"].font = Font(size=9, color="64748B")

    if logo_base64 and "," in logo_base64:
        try:
            _, b64 = logo_base64.split(",", 1)
            img = XLImage(BytesIO(base64.b64decode(b64)))
            img.width, img.height = 90, 34
            img.anchor = "J1"
            ws.add_image(img)
        except Exception:
            pass

    headers = ["Cédula", "Nombre y Apellido", "Departamento",
               "Días Totales", "Días Trabajados",
               "Horas Diurnas", "Horas Nocturnas",
               "Feriadas Diurnas", "Feriadas Nocturnas", "Descanso (Horas)"]
    widths = [14, 32, 22, 10, 12, 12, 13, 14, 15, 14]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    hdr_row = 5
    for i, h in enumerate(headers, start=1):
        c = ws.cell(row=hdr_row, column=i, value=h)
        c.font = Font(bold=True, color="FFFFFF", size=9)
        c.fill = dark_fill
        c.alignment = Alignment(vertical="center", horizontal="center", wrap_text=True)
        c.border = border
    ws.row_dimensions[hdr_row].height = 28

    tot = {"trabajados": 0, "diurnas": 0.0, "nocturnas": 0.0, "fer_d": 0.0, "fer_n": 0.0, "desc": 0.0}
    for r_i, row in enumerate(report["rows"], start=hdr_row + 1):
        values = [
            row["cedula"], row["nombre"], row["departamento"],
            row["dias_total"], row["dias_trabajados"],
            row["horas_diurnas"], row["horas_nocturnas"],
            row["feriadas_diurnas"], row["feriadas_nocturnas"], row["horas_descanso"],
        ]
        for c_i, v in enumerate(values, start=1):
            cell = ws.cell(row=r_i, column=c_i, value=v)
            cell.font = Font(size=9)
            cell.border = border
            cell.alignment = Alignment(vertical="center",
                                       horizontal="left" if c_i <= 3 else "right")
            if c_i >= 6:
                cell.number_format = "#,##0.00"
        tot["trabajados"] += row["dias_trabajados"]
        tot["diurnas"] += row["horas_diurnas"]
        tot["nocturnas"] += row["horas_nocturnas"]
        tot["fer_d"] += row["feriadas_diurnas"]
        tot["fer_n"] += row["feriadas_nocturnas"]
        tot["desc"] += row["horas_descanso"]

    if report["rows"]:
        r_i = hdr_row + 1 + len(report["rows"])
        totals_row = ["", "TOTAL GENERAL", "",
                      report["days_total"], tot["trabajados"],
                      round(tot["diurnas"], 2), round(tot["nocturnas"], 2),
                      round(tot["fer_d"], 2), round(tot["fer_n"], 2), round(tot["desc"], 2)]
        for c_i, v in enumerate(totals_row, start=1):
            cell = ws.cell(row=r_i, column=c_i, value=v)
            cell.font = Font(bold=True, size=9, color="0F172A")
            cell.fill = amber_fill
            cell.border = border
            cell.alignment = Alignment(vertical="center",
                                       horizontal="left" if c_i <= 3 else "right")
            if c_i >= 6:
                cell.number_format = "#,##0.00"

    ws.freeze_panes = f"A{hdr_row + 1}"

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
