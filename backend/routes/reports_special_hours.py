"""Endpoints del Reporte de Horas · Turnos Especiales (sep-2026).

Acceso: RBAC `reporte_horas_turnos_especiales`. Admin siempre pasa.
"""
from typing import List, Optional
from deps import (
    api, db, get_current_user, enrich_user_with_permissions,
    HTTPException, Depends, Query,
    Any, Dict,
)
from fastapi.responses import StreamingResponse

from special_hours_report import build_special_hours_report, export_special_hours_xlsx

ERR_NO_PERM = "No tienes permiso para consultar el Reporte de Horas de Turnos Especiales"


async def _require_perm(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    if user.get("role") == "admin":
        return user
    enriched = await enrich_user_with_permissions(user)
    if (enriched.get("effective_permissions") or {}).get("reporte_horas_turnos_especiales"):
        return user
    raise HTTPException(status_code=403, detail=ERR_NO_PERM)


def _validate_range(from_date: Optional[str], to_date: Optional[str]) -> None:
    if not from_date or not to_date:
        raise HTTPException(status_code=400, detail="El rango de fechas (Desde/Hasta) es obligatorio")


@api.get("/reports/special-hours")
async def reports_special_hours(from_date: Optional[str] = Query(None),
                                 to_date: Optional[str] = Query(None),
                                 user_ids: Optional[List[str]] = Query(None),
                                 department_ids: Optional[List[str]] = Query(None),
                                 user: Dict[str, Any] = Depends(_require_perm)) -> Dict[str, Any]:
    _validate_range(from_date, to_date)
    return await build_special_hours_report(db, from_date, to_date,
                                            user_ids=user_ids or None,
                                            department_ids=department_ids or None)


@api.get("/reports/special-hours/export.xlsx")
async def reports_special_hours_xlsx(from_date: Optional[str] = Query(None),
                                      to_date: Optional[str] = Query(None),
                                      user_ids: Optional[List[str]] = Query(None),
                                      department_ids: Optional[List[str]] = Query(None),
                                      user: Dict[str, Any] = Depends(_require_perm)) -> StreamingResponse:
    _validate_range(from_date, to_date)
    report = await build_special_hours_report(db, from_date, to_date,
                                              user_ids=user_ids or None,
                                              department_ids=department_ids or None)
    settings = await db.settings.find_one({"_id": "company"}) or {}
    xlsx_bytes = export_special_hours_xlsx(
        report,
        company_name=settings.get("company_name") or "Mega Soft",
        logo_base64=settings.get("logo_base64"),
    )
    filename = f"horas_turnos_especiales_{from_date}_a_{to_date}.xlsx"
    return StreamingResponse(
        iter([xlsx_bytes]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
