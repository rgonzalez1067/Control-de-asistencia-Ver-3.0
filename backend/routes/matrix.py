"""Endpoints del Reporte Matricial (JSON, XLSX, PDF).

Migrado desde server.py durante la Fase A · Iteración 2 (feb-2026).
Adenda feb-2026: soporte para "Horario Especial" (1 bloque E1/S1) y
`sort_by` (name | entry_asc | entry_desc).
"""
from deps import (
    api, db, get_current_user, LEADER_ROLES,
    supervisor_scope_ids,
    HTTPException, Depends, Query,
    Any, Dict, List, Optional,
)
from fastapi.responses import StreamingResponse
from matrix_report import build_matrix, export_xlsx, export_pdf

# ==================================================================
# REPORTE MATRICIAL (3 endpoints)
# ==================================================================

_VALID_SORT_BY = {"name", "entry_asc", "entry_desc"}


def _normalize_sort_by(v: Optional[str]) -> str:
    """Sanea el parámetro para evitar variantes inesperadas."""
    if not v:
        return "name"
    v = v.strip().lower()
    return v if v in _VALID_SORT_BY else "name"


async def _matrix_scope_ids(user: Dict[str, Any]) -> Optional[List[str]]:
    role = user.get("role")
    if role == "employee":
        return [user["user_id"]]
    if role in LEADER_ROLES:
        return await supervisor_scope_ids(user)
    return None  # admin → sin restricción


def _parse_list_query(val: Optional[str]) -> Optional[List[str]]:
    if not val:
        return None
    out = [v for v in val.split(",") if v.strip()]
    return out or None


@api.get("/reports/matrix")
async def reports_matrix(from_date: str = Query(...),
                         to_date: str = Query(...),
                         department_ids: Optional[str] = Query(None),
                         user_ids: Optional[str] = Query(None),
                         site_id: Optional[str] = Query(None),
                         schedule_id: Optional[str] = Query(None),
                         sort_by: Optional[str] = Query(None),
                         user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    scope = await _matrix_scope_ids(user)
    return await build_matrix(
        db, from_date, to_date,
        scope_user_ids=scope,
        department_ids=_parse_list_query(department_ids),
        user_ids=_parse_list_query(user_ids),
        site_id=site_id or None,
        schedule_id=schedule_id or None,
        sort_by=_normalize_sort_by(sort_by),
    )


@api.get("/reports/matrix/export.xlsx")
async def reports_matrix_xlsx(from_date: str = Query(...),
                              to_date: str = Query(...),
                              department_ids: Optional[str] = Query(None),
                              user_ids: Optional[str] = Query(None),
                              site_id: Optional[str] = Query(None),
                              schedule_id: Optional[str] = Query(None),
                              sort_by: Optional[str] = Query(None),
                              user: Dict[str, Any] = Depends(get_current_user)) -> StreamingResponse:
    scope = await _matrix_scope_ids(user)
    matrix = await build_matrix(
        db, from_date, to_date,
        scope_user_ids=scope,
        department_ids=_parse_list_query(department_ids),
        user_ids=_parse_list_query(user_ids),
        site_id=site_id or None,
        schedule_id=schedule_id or None,
        sort_by=_normalize_sort_by(sort_by),
    )
    xlsx_bytes = export_xlsx(matrix)
    filename = f"matriz_asistencia_{from_date}_a_{to_date}.xlsx"
    return StreamingResponse(
        iter([xlsx_bytes]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@api.get("/reports/matrix/export.pdf")
async def reports_matrix_pdf(from_date: str = Query(...),
                             to_date: str = Query(...),
                             department_ids: Optional[str] = Query(None),
                             user_ids: Optional[str] = Query(None),
                             site_id: Optional[str] = Query(None),
                             schedule_id: Optional[str] = Query(None),
                             sort_by: Optional[str] = Query(None),
                             user: Dict[str, Any] = Depends(get_current_user)) -> StreamingResponse:
    scope = await _matrix_scope_ids(user)
    matrix = await build_matrix(
        db, from_date, to_date,
        scope_user_ids=scope,
        department_ids=_parse_list_query(department_ids),
        user_ids=_parse_list_query(user_ids),
        site_id=site_id or None,
        schedule_id=schedule_id or None,
        sort_by=_normalize_sort_by(sort_by),
    )
    settings = await db.settings.find_one({"_id": "company"}) or {}
    pdf_bytes = export_pdf(matrix,
                           company_name=settings.get("company_name") or "Mega Soft",
                           logo_base64=settings.get("logo_base64"))
    filename = f"matriz_asistencia_{from_date}_a_{to_date}.pdf"
    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
