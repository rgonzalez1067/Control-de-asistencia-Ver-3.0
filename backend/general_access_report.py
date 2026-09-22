"""Reporte General de Accesos — Relación diaria de asistencia (sep-2026).

Consolida los marcajes de entrada/salida de todo el personal visible según la
jerarquía de visualización, agrupados por empleado y día:

- Una fila por (empleado, fecha) con al menos un marcaje en el periodo.
- Columnas: Cédula, Nombre y Apellido, Departamento, Cargo, Fecha, E1, S1, E2, S2.
- Filtros: rango de fechas (obligatorio), departamentos (multi, vacío=todos),
  sede (acota los marcajes por `site_id` del registro; sin sede = todas).
- PDF institucional: logo arriba a la izquierda, paginador "n/m" arriba a la
  derecha, título "Reporte General de Accesos" y subtítulo "Periodo: ...".
"""
import base64
from datetime import date as _date, datetime, time as _time, timedelta
from io import BytesIO
from typing import Any, Dict, List, Optional

from deps import APP_TZ, now_utc


def _day_bounds_utc(from_date: str, to_date: str) -> tuple:
    start = datetime.combine(_date.fromisoformat(from_date), _time.min, tzinfo=APP_TZ).astimezone(tz=None)
    end = (datetime.combine(_date.fromisoformat(to_date), _time.min, tzinfo=APP_TZ)
           + timedelta(days=1)).astimezone(tz=None)
    from datetime import timezone as _tz
    return (start.astimezone(_tz.utc), end.astimezone(_tz.utc))


def _hm(ts: Optional[datetime]) -> str:
    if not ts:
        return ""
    return ts.astimezone(APP_TZ).strftime("%H:%M")


async def build_general_access_report(db, from_date: str, to_date: str,
                                      department_ids: Optional[List[str]] = None,
                                      site_id: Optional[str] = None,
                                      user_ids: Optional[List[str]] = None,
                                      scope_user_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    start_utc, end_utc = _day_bounds_utc(from_date, to_date)

    uq: Dict[str, Any] = {"role": {"$ne": "kiosk"}}
    # None = sin límite (admin/director); [] = scope vacío → cero filas.
    if scope_user_ids is not None:
        uq["user_id"] = {"$in": scope_user_ids}
    if department_ids:
        uq["department_id"] = {"$in": department_ids}
    if user_ids:
        # Intersecta con el scope si ya lo hay.
        existing = uq.get("user_id", {}).get("$in") if isinstance(uq.get("user_id"), dict) else None
        if existing is not None:
            uq["user_id"] = {"$in": [uid for uid in user_ids if uid in existing]}
        else:
            uq["user_id"] = {"$in": user_ids}
    users = await db.users.find(uq, {
        "user_id": 1, "cedula": 1, "name": 1, "first_name": 1, "last_name": 1,
        "department_id": 1, "position": 1, "_id": 0,
    }).sort("name", 1).to_list(10000)
    uids = [u["user_id"] for u in users]

    depts = {d["department_id"]: d["name"] async for d in db.departments.find({}, {"department_id": 1, "name": 1, "_id": 0})}
    site_doc = await db.sites.find_one({"site_id": site_id}, {"name": 1, "_id": 0}) if site_id else None

    aq: Dict[str, Any] = {
        "user_id": {"$in": uids},
        "timestamp": {"$gte": start_utc, "$lt": end_utc},
    }
    if site_id:
        aq["site_id"] = site_id
    marks = await db.attendance.find(aq, {
        "user_id": 1, "type": 1, "timestamp": 1, "_id": 0,
    }).sort("timestamp", 1).to_list(200000)

    by_user_day: Dict[str, Dict[str, Dict[str, List[datetime]]]] = {}
    for m in marks:
        ts = m.get("timestamp")
        if not isinstance(ts, datetime):
            continue
        day = ts.astimezone(APP_TZ).strftime("%Y-%m-%d")
        slot = by_user_day.setdefault(m["user_id"], {}).setdefault(day, {"in": [], "out": []})
        if m.get("type") in ("in", "out"):
            slot[m["type"]].append(ts)

    rows: List[Dict[str, Any]] = []
    for u in users:
        uid = u["user_id"]
        nombre = u.get("name") or f"{u.get('first_name', '')} {u.get('last_name', '')}".strip()
        for day in sorted((by_user_day.get(uid) or {}).keys()):
            slot = by_user_day[uid][day]
            ins, outs = slot["in"], slot["out"]
            rows.append({
                "user_id": uid,
                "cedula": u.get("cedula") or "",
                "nombre": nombre,
                "departamento": depts.get(u.get("department_id") or "", "—"),
                "cargo": u.get("position") or "—",
                "fecha": day,
                "e1": _hm(ins[0]) if len(ins) > 0 else "",
                "s1": _hm(outs[0]) if len(outs) > 0 else "",
                "e2": _hm(ins[1]) if len(ins) > 1 else "",
                "s2": _hm(outs[1]) if len(outs) > 1 else "",
            })

    rows.sort(key=lambda r: (r["fecha"], r["nombre"]))

    return {
        "from_date": from_date,
        "to_date": to_date,
        "site_name": (site_doc or {}).get("name") if site_id else None,
        "generated_at": now_utc().isoformat(),
        "rows_count": len(rows),
        "employees_count": len({r["user_id"] for r in rows}),
        "rows": rows,
    }


def export_general_access_pdf(report: Dict[str, Any], company_name: str = "Mega Soft",
                              logo_base64: Optional[str] = None) -> bytes:
    from reportlab.lib.pagesizes import landscape, A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
    from reportlab.pdfgen import canvas as _canvas

    PAGE = landscape(A4)
    title_text = "Reporte General de Accesos"
    subtitle_text = f"Periodo: {report['from_date']} - {report['to_date']}"
    meta_text = (
        f"Sede: {report.get('site_name') or 'Todas las Sedes'} · "
        f"{report['employees_count']} empleados · {report['rows_count']} registros · "
        f"Generado: {datetime.now(APP_TZ).strftime('%d/%m/%Y %H:%M')}"
    )

    logo_reader = None
    if logo_base64 and "," in logo_base64:
        try:
            _, b64 = logo_base64.split(",", 1)
            logo_reader = ImageReader(BytesIO(base64.b64decode(b64)))
        except Exception:
            logo_reader = None

    class NumberedCanvas(_canvas.Canvas):
        """Canvas de 2 pasadas: dibuja cabecera institucional + paginador n/m
        en TODAS las páginas al cerrar el documento."""

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._saved_states = []

        def showPage(self):
            self._saved_states.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._saved_states)
            for state in self._saved_states:
                self.__dict__.update(state)
                self._draw_header(total)
                _canvas.Canvas.showPage(self)
            _canvas.Canvas.save(self)

        def _draw_header(self, total: int) -> None:
            w, h = self._pagesize
            if logo_reader is not None:
                try:
                    self.drawImage(logo_reader, 8 * mm, h - 16 * mm,
                                   width=30 * mm, height=11 * mm,
                                   preserveAspectRatio=True, mask="auto")
                except Exception:
                    pass
            self.setFont("Helvetica-Bold", 13)
            self.setFillColor(colors.HexColor("#0F172A"))
            self.drawCentredString(w / 2, h - 10 * mm, title_text)
            self.setFont("Helvetica", 8.5)
            self.setFillColor(colors.HexColor("#64748B"))
            self.drawCentredString(w / 2, h - 15 * mm, subtitle_text)
            self.drawCentredString(w / 2, h - 19.5 * mm, meta_text)
            self.setFont("Helvetica-Bold", 9)
            self.setFillColor(colors.HexColor("#0F172A"))
            self.drawRightString(w - 8 * mm, h - 10 * mm, f"{self._pageNumber}/{total}")
            self.setStrokeColor(colors.HexColor("#CBD5E1"))
            self.setLineWidth(0.6)
            self.line(8 * mm, h - 22 * mm, w - 8 * mm, h - 22 * mm)

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=PAGE,
                            leftMargin=8 * mm, rightMargin=8 * mm,
                            topMargin=26 * mm, bottomMargin=10 * mm,
                            title=title_text)

    styles = getSampleStyleSheet()
    p_cell = ParagraphStyle("c", parent=styles["Normal"], fontSize=7, leading=9,
                            textColor=colors.HexColor("#111827"))
    p_head = ParagraphStyle("h", parent=styles["Normal"], fontSize=7, leading=9,
                            textColor=colors.white, fontName="Helvetica-Bold")

    headers = ["Cédula", "Nombre y Apellido", "Departamento", "Cargo",
               "Fecha", "E1", "S1", "E2", "S2"]
    col_widths = [22 * mm, 55 * mm, 40 * mm, 45 * mm, 22 * mm, 17 * mm, 17 * mm, 17 * mm, 17 * mm]

    data = [[Paragraph(h, p_head) for h in headers]]
    for r in report["rows"]:
        data.append([
            Paragraph(str(r["cedula"]), p_cell),
            Paragraph(str(r["nombre"]), p_cell),
            Paragraph(str(r["departamento"]), p_cell),
            Paragraph(str(r["cargo"]), p_cell),
            Paragraph(r["fecha"], p_cell),
            Paragraph(r["e1"], p_cell),
            Paragraph(r["s1"], p_cell),
            Paragraph(r["e2"], p_cell),
            Paragraph(r["s2"], p_cell),
        ])
    if len(data) == 1:
        data.append([Paragraph("Sin marcajes en el periodo seleccionado.", p_cell)] + [""] * (len(headers) - 1))

    tbl = Table(data, colWidths=col_widths, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (4, 1), (-1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))

    doc.build([tbl], canvasmaker=NumberedCanvas)
    return buf.getvalue()
