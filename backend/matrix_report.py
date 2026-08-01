"""Reporte matricial de asistencia y novedades.

Construye una matriz (usuarios × días) con horas de entrada/salida, estatus
diario (normal, tarde justificada, tarde no justificada, vacaciones/reposo/
permiso/remoto, falta no justificada) y totales por empleado.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone, date as dtdate
from typing import Any, Dict, List, Optional, Iterable
from zoneinfo import ZoneInfo

APP_TZ = ZoneInfo("America/Caracas")

# Nombres humanos por tipo de novedad
NOVELTY_LABEL = {
    "vacation":   "Vacaciones",
    "leave":      "Reposo",
    "medical":    "Cita médica",
    "permission": "Permiso",
    "remote":     "Trabajo remoto",
    "other":      "Novedad",
}

# Estatus de celda
STATUS_NORMAL = "normal"
STATUS_LATE_JUST = "late_justified"
STATUS_LATE_UNJUST = "late_unjustified"
STATUS_NOVELTY = "novelty"        # se acompaña de novelty_type
STATUS_ABSENT = "absent"
STATUS_FUTURE = "future"          # fecha aún no ocurrida
STATUS_NON_WORKING = "non_working"  # sábado/domingo


def _iter_dates(from_d: str, to_d: str) -> List[str]:
    d1 = dtdate.fromisoformat(from_d)
    d2 = dtdate.fromisoformat(to_d)
    if d2 < d1:
        return []
    out = []
    while d1 <= d2:
        out.append(d1.isoformat())
        d1 += timedelta(days=1)
    return out


def _is_working_day(iso_date: str) -> bool:
    """Simple: L-V son laborables. (Puede evolucionar a partir del schedule)."""
    d = dtdate.fromisoformat(iso_date)
    return d.weekday() < 5


def _in_range(day: str, start: Optional[str], end: Optional[str]) -> bool:
    if not start or not end:
        return False
    return start <= day <= end


async def build_matrix(
    db,
    from_date: str,
    to_date: str,
    scope_user_ids: Optional[List[str]] = None,
    department_ids: Optional[List[str]] = None,
    user_ids: Optional[List[str]] = None,
    site_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Devuelve:
      {
        "from_date": ..., "to_date": ..., "days": ["YYYY-MM-DD", ...],
        "rows": [
          {
            "user_id", "name", "cedula", "department", "position", "site",
            "cells": {"YYYY-MM-DD": {
                "check_in": "HH:MM" | None,
                "check_out": "HH:MM" | None,
                "status": <STATUS_*>,
                "late_minutes": int,
                "novelty_type": <str> | None,
                "novelty_label": <str> | None,
                "reason": <str> | None,
            }},
            "totals": {
              "lost_minutes": int, "late_justified": int, "late_unjustified": int,
              "vacation_days": int, "leave_days": int, "remote_days": int,
              "permission_days": int, "absent_days": int,
            }
          }, ...
        ]
      }
    """
    days = _iter_dates(from_date, to_date)
    if not days:
        return {"from_date": from_date, "to_date": to_date, "days": [], "rows": []}

    # 1) Filtro base de usuarios
    uq: Dict[str, Any] = {}
    if scope_user_ids is not None:
        uq["user_id"] = {"$in": scope_user_ids}
    if user_ids:
        # intersección con scope
        allowed = set(scope_user_ids) if scope_user_ids is not None else None
        picked = [u for u in user_ids if (allowed is None or u in allowed)]
        uq["user_id"] = {"$in": picked}
    if department_ids:
        uq["department_id"] = {"$in": department_ids}
    if site_id:
        uq["site_id"] = site_id

    users = await db.users.find(uq, {
        "user_id": 1, "name": 1, "cedula": 1, "email": 1,
        "department_id": 1, "position": 1, "site_id": 1,
    }).sort("name", 1).to_list(5000)

    if not users:
        return {"from_date": from_date, "to_date": to_date, "days": days, "rows": []}

    uid_list = [u["user_id"] for u in users]

    # 2) Cache de departamentos y sedes
    dept_map = {d["department_id"]: d["name"]
                async for d in db.departments.find({}, {"department_id": 1, "name": 1})}
    site_map = {s["site_id"]: s["name"]
                async for s in db.sites.find({}, {"site_id": 1, "name": 1})}

    # 3) Attendance en rango
    d1 = datetime.fromisoformat(from_date).replace(tzinfo=APP_TZ).astimezone(timezone.utc)
    d2 = (datetime.fromisoformat(to_date) + timedelta(days=1)).replace(tzinfo=APP_TZ).astimezone(timezone.utc)
    att_docs = await db.attendance.find({
        "user_id": {"$in": uid_list},
        "timestamp": {"$gte": d1, "$lt": d2},
    }, {"selfie_base64": 0}).to_list(20000)

    # agrupa por user × fecha (yyyy-mm-dd en TZ Caracas)
    att_by_user_day: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for a in att_docs:
        ts = a.get("timestamp")
        if not isinstance(ts, datetime):
            continue
        local = ts.astimezone(APP_TZ)
        day = local.strftime("%Y-%m-%d")
        bucket = att_by_user_day.setdefault(a["user_id"], {}).setdefault(day, {
            "in": None, "out": None, "in_doc": None, "out_doc": None,
        })
        atype = a.get("type")
        if atype == "in":
            if bucket["in"] is None or local < bucket["in"]:
                bucket["in"] = local
                bucket["in_doc"] = a
        elif atype == "out":
            if bucket["out"] is None or local > bucket["out"]:
                bucket["out"] = local
                bucket["out_doc"] = a

    # 4) Novelties aprobadas que solapan con el rango
    nov_docs = await db.novelties.find({
        "user_id": {"$in": uid_list},
        "status": "approved",
        "start_date": {"$lte": to_date},
        "end_date": {"$gte": from_date},
    }).to_list(10000)
    novs_by_user: Dict[str, List[Dict[str, Any]]] = {}
    for n in nov_docs:
        novs_by_user.setdefault(n["user_id"], []).append(n)

    # 5) Construye filas
    rows: List[Dict[str, Any]] = []
    for u in users:
        uid = u["user_id"]
        att_days = att_by_user_day.get(uid, {})
        novs = novs_by_user.get(uid, [])

        totals = {
            "lost_minutes": 0, "late_justified": 0, "late_unjustified": 0,
            "vacation_days": 0, "leave_days": 0, "remote_days": 0,
            "permission_days": 0, "medical_days": 0, "absent_days": 0,
        }
        cells: Dict[str, Any] = {}

        for day in days:
            cell = {
                "check_in": None, "check_out": None,
                "status": STATUS_NORMAL, "late_minutes": 0,
                "novelty_type": None, "novelty_label": None, "reason": None,
            }

            # ¿día futuro?
            if day > datetime.now(APP_TZ).strftime("%Y-%m-%d"):
                cell["status"] = STATUS_FUTURE
                cells[day] = cell
                continue

            # ¿coincide novedad aprobada?
            active_nov = next((n for n in novs if _in_range(day, n.get("start_date"), n.get("end_date"))), None)

            # datos de asistencia del día
            day_att = att_days.get(day)
            check_in_dt = day_att.get("in") if day_att else None
            check_out_dt = day_att.get("out") if day_att else None
            if check_in_dt:
                cell["check_in"] = check_in_dt.strftime("%H:%M")
            if check_out_dt:
                cell["check_out"] = check_out_dt.strftime("%H:%M")

            # 1) Novedad aprobada tiene prioridad para marcar el estatus del día,
            #    salvo que además haya marcaje (se mostrará ambos)
            if active_nov:
                cell["status"] = STATUS_NOVELTY
                cell["novelty_type"] = active_nov.get("type")
                cell["novelty_label"] = NOVELTY_LABEL.get(active_nov.get("type"), "Novedad")
                cell["reason"] = active_nov.get("reason")
                key = f"{active_nov.get('type')}_days"
                if key in totals:
                    totals[key] += 1
                cells[day] = cell
                continue

            # 2) Sin marcaje ni novedad
            if not check_in_dt:
                if _is_working_day(day):
                    cell["status"] = STATUS_ABSENT
                    totals["absent_days"] += 1
                else:
                    cell["status"] = STATUS_NON_WORKING
                cells[day] = cell
                continue

            # 3) Hay marcaje → evaluar tardanza
            in_doc = day_att["in_doc"] or {}
            is_late = bool(in_doc.get("is_late"))
            late_min = int(in_doc.get("late_minutes") or 0)
            has_just = bool((in_doc.get("justification") or "").strip())
            if is_late:
                if has_just:
                    cell["status"] = STATUS_LATE_JUST
                    totals["late_justified"] += 1
                else:
                    cell["status"] = STATUS_LATE_UNJUST
                    totals["late_unjustified"] += 1
                    totals["lost_minutes"] += late_min
                cell["late_minutes"] = late_min
                cell["reason"] = in_doc.get("justification") or None
            else:
                cell["status"] = STATUS_NORMAL

            cells[day] = cell

        rows.append({
            "user_id": uid,
            "name": u.get("name"),
            "cedula": u.get("cedula") or "",
            "email": u.get("email"),
            "department": dept_map.get(u.get("department_id")) or "",
            "position": u.get("position") or "",
            "site": site_map.get(u.get("site_id")) or "",
            "cells": cells,
            "totals": totals,
        })

    return {"from_date": from_date, "to_date": to_date, "days": days, "rows": rows}


# ==============================================================
# EXPORTS
# ==============================================================
def _status_short(status: str, novelty_label: Optional[str]) -> str:
    if status == STATUS_NOVELTY:
        return novelty_label or "Novedad"
    return {
        STATUS_NORMAL: "OK",
        STATUS_LATE_JUST: "Tarde-J",
        STATUS_LATE_UNJUST: "Tarde-NJ",
        STATUS_ABSENT: "Falta",
        STATUS_NON_WORKING: "—",
        STATUS_FUTURE: "",
    }.get(status, "")


def export_xlsx(matrix: Dict[str, Any]) -> bytes:
    from io import BytesIO
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    wb = Workbook()
    ws = wb.active
    ws.title = "Matriz asistencia"

    days = matrix.get("days", [])
    thin = Side(border_style="thin", color="D1D5DB")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    hdr_fill = PatternFill("solid", fgColor="0F172A")
    hdr_font = Font(bold=True, color="FFFFFF")
    tot_fill = PatternFill("solid", fgColor="F1F5F9")

    # Encabezados (fila 1 = grupos día, fila 2 = subcolumnas)
    static_headers = ["Empleado", "Cédula", "Depto", "Cargo", "Sede"]
    for col_idx, h in enumerate(static_headers, start=1):
        cell = ws.cell(row=1, column=col_idx, value=h)
        cell.font = hdr_font
        cell.fill = hdr_fill
        cell.alignment = Alignment(horizontal="left", vertical="center")
        cell.border = border
        ws.cell(row=2, column=col_idx, value="").fill = hdr_fill
        ws.merge_cells(start_row=1, start_column=col_idx, end_row=2, end_column=col_idx)

    col = len(static_headers) + 1
    day_cols_start = col
    for day in days:
        ws.cell(row=1, column=col, value=day).font = hdr_font
        ws.cell(row=1, column=col).fill = hdr_fill
        ws.cell(row=1, column=col).alignment = Alignment(horizontal="center")
        ws.cell(row=1, column=col).border = border
        ws.merge_cells(start_row=1, start_column=col, end_row=1, end_column=col + 2)
        for sub_i, sub in enumerate(["Entrada", "Salida", "Estatus"]):
            c = ws.cell(row=2, column=col + sub_i, value=sub)
            c.font = hdr_font
            c.fill = hdr_fill
            c.alignment = Alignment(horizontal="center")
            c.border = border
        col += 3

    tot_headers = [
        "Min. perdidos", "Tardes-J", "Tardes-NJ",
        "Vacaciones", "Reposo", "Remoto", "Permiso", "Faltas",
    ]
    tot_cols_start = col
    for h in tot_headers:
        ws.cell(row=1, column=col, value=h).font = hdr_font
        ws.cell(row=1, column=col).fill = hdr_fill
        ws.cell(row=1, column=col).alignment = Alignment(horizontal="center")
        ws.cell(row=1, column=col).border = border
        ws.cell(row=2, column=col, value="").fill = hdr_fill
        ws.merge_cells(start_row=1, start_column=col, end_row=2, end_column=col)
        col += 1

    # Filas de datos
    row_idx = 3
    for r in matrix.get("rows", []):
        ws.cell(row=row_idx, column=1, value=r["name"])
        ws.cell(row=row_idx, column=2, value=r["cedula"])
        ws.cell(row=row_idx, column=3, value=r["department"])
        ws.cell(row=row_idx, column=4, value=r["position"])
        ws.cell(row=row_idx, column=5, value=r["site"])
        c = day_cols_start
        for day in days:
            cell = r["cells"].get(day, {})
            ws.cell(row=row_idx, column=c, value=cell.get("check_in") or "").alignment = Alignment(horizontal="center")
            ws.cell(row=row_idx, column=c + 1, value=cell.get("check_out") or "").alignment = Alignment(horizontal="center")
            estat = _status_short(cell.get("status", ""), cell.get("novelty_label"))
            sc = ws.cell(row=row_idx, column=c + 2, value=estat)
            sc.alignment = Alignment(horizontal="center")
            # colorear estatus problemáticos
            if cell.get("status") == STATUS_LATE_UNJUST or cell.get("status") == STATUS_ABSENT:
                sc.fill = PatternFill("solid", fgColor="FEE2E2")
                sc.font = Font(bold=True, color="991B1B")
            elif cell.get("status") == STATUS_LATE_JUST:
                sc.fill = PatternFill("solid", fgColor="FEF9C3")
                sc.font = Font(color="854D0E")
            elif cell.get("status") == STATUS_NOVELTY:
                sc.fill = PatternFill("solid", fgColor="DBEAFE")
                sc.font = Font(color="1E40AF")
            c += 3
        # totales
        t = r["totals"]
        vals = [t["lost_minutes"], t["late_justified"], t["late_unjustified"],
                t["vacation_days"], t["leave_days"], t["remote_days"],
                t["permission_days"], t["absent_days"]]
        tc = tot_cols_start
        for v in vals:
            cell = ws.cell(row=row_idx, column=tc, value=v)
            cell.alignment = Alignment(horizontal="center")
            cell.fill = tot_fill
            tc += 1
        row_idx += 1

    # Freeze panes en encabezados y primera columna
    ws.freeze_panes = ws.cell(row=3, column=6)

    # Anchos
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
                            leftMargin=10 * mm, rightMargin=10 * mm,
                            topMargin=10 * mm, bottomMargin=10 * mm,
                            title="Reporte matricial de asistencia")

    styles = getSampleStyleSheet()
    h_title = ParagraphStyle("t", parent=styles["Title"], fontSize=16, textColor=colors.HexColor("#0F172A"))
    h_sub = ParagraphStyle("s", parent=styles["Normal"], fontSize=9, textColor=colors.HexColor("#64748B"))

    story: List[Any] = []
    # Header con logo
    if logo_base64 and "," in logo_base64:
        try:
            _, b64 = logo_base64.split(",", 1)
            img_bytes = BytesIO(base64.b64decode(b64))
            story.append(Image(img_bytes, width=35 * mm, height=13 * mm, hAlign="LEFT"))
        except Exception:
            pass
    story.append(Paragraph(f"{company_name} · Reporte matricial de asistencia", h_title))
    story.append(Paragraph(
        f"Rango: {matrix['from_date']} — {matrix['to_date']} · {len(matrix['rows'])} empleados · "
        f"generado {datetime.now(APP_TZ).strftime('%Y-%m-%d %H:%M')}", h_sub))
    story.append(Spacer(1, 4 * mm))

    days = matrix["days"]

    # Encabezado
    header_row_top = ["Empleado", "Cédula", "Depto"]
    header_row_bot = ["", "", ""]
    for d in days:
        header_row_top.append(d)
        header_row_top.append("")
        header_row_top.append("")
        header_row_bot.append("Ent.")
        header_row_bot.append("Sal.")
        header_row_bot.append("Est.")
    total_labels = ["Min. perd.", "T-J", "T-NJ", "Vac", "Rep", "Rem", "Perm", "Falt"]
    for tl in total_labels:
        header_row_top.append(tl)
        header_row_bot.append("")

    data = [header_row_top, header_row_bot]
    row_style_extras: List[Any] = []

    for i, r in enumerate(matrix["rows"], start=2):
        row = [r["name"], r["cedula"], r["department"]]
        for day in days:
            c = r["cells"].get(day, {})
            row.append(c.get("check_in") or "-")
            row.append(c.get("check_out") or "-")
            row.append(_status_short(c.get("status", ""), c.get("novelty_label")))
            # coloring per status
            col_status = 3 + days.index(day) * 3 + 2
            if c.get("status") == STATUS_LATE_UNJUST:
                row_style_extras.append(("BACKGROUND", (col_status, i), (col_status, i), colors.HexColor("#FEE2E2")))
                row_style_extras.append(("TEXTCOLOR", (col_status, i), (col_status, i), colors.HexColor("#991B1B")))
            elif c.get("status") == STATUS_ABSENT:
                row_style_extras.append(("BACKGROUND", (col_status, i), (col_status, i), colors.HexColor("#FEE2E2")))
            elif c.get("status") == STATUS_LATE_JUST:
                row_style_extras.append(("BACKGROUND", (col_status, i), (col_status, i), colors.HexColor("#FEF9C3")))
            elif c.get("status") == STATUS_NOVELTY:
                row_style_extras.append(("BACKGROUND", (col_status, i), (col_status, i), colors.HexColor("#DBEAFE")))
                row_style_extras.append(("TEXTCOLOR", (col_status, i), (col_status, i), colors.HexColor("#1E40AF")))
        t = r["totals"]
        row.extend([t["lost_minutes"], t["late_justified"], t["late_unjustified"],
                    t["vacation_days"], t["leave_days"], t["remote_days"],
                    t["permission_days"], t["absent_days"]])
        data.append(row)

    n_static = 3
    n_day_cols = len(days) * 3
    n_tot = len(total_labels)

    # Column widths compactos
    col_widths = [30 * mm, 20 * mm, 25 * mm] + [8 * mm] * n_day_cols + [12 * mm] * n_tot
    table = Table(data, colWidths=col_widths, repeatRows=2)

    style = TableStyle([
        ("FONTNAME", (0, 0), (-1, 1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 6.5),
        ("BACKGROUND", (0, 0), (-1, 1), colors.HexColor("#0F172A")),
        ("TEXTCOLOR", (0, 0), (-1, 1), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D1D5DB")),
        ("ALIGN", (n_static, 0), (-1, -1), "CENTER"),
        ("ALIGN", (0, 2), (n_static - 1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 2), (-1, -1), [colors.white, colors.HexColor("#F9FAFB")]),
    ])
    # merges de fecha (span de 3 col en fila 0)
    for i, _d in enumerate(days):
        c = n_static + i * 3
        style.add("SPAN", (c, 0), (c + 2, 0))
    # merges columnas estáticas + totales (span vertical filas 0-1)
    for c in range(n_static):
        style.add("SPAN", (c, 0), (c, 1))
    for c in range(n_static + n_day_cols, n_static + n_day_cols + n_tot):
        style.add("SPAN", (c, 0), (c, 1))
    for extra in row_style_extras:
        style.add(*extra)

    table.setStyle(style)
    story.append(table)

    story.append(Spacer(1, 6 * mm))
    legend = Paragraph(
        "<b>Leyenda:</b> OK · Tarde-J (justificada) · <font color='#991B1B'>Tarde-NJ (no justificada)</font> · "
        "Vacaciones / Reposo / Remoto / Permiso · <font color='#991B1B'>Falta (día laboral sin marcaje)</font> · "
        "— (día no laboral)", h_sub)
    story.append(legend)

    doc.build(story)
    return buf.getvalue()
