"""Endpoints del Reporte Regulatorio de Visitas (Auditoría de Control de Acceso).

Sep-2026. Acceso gobernado por la clave RBAC `visitas_reporte_regulatorio`
(grilla de Perfiles de Acceso). Admin siempre pasa (safety net).
"""
from deps import (
    api, db, get_current_user, enrich_user_with_permissions,
    HTTPException, Depends, Query,
    Any, Dict, Optional,
)
from fastapi.responses import StreamingResponse

from visits_report import build_visits_report, export_visits_xlsx, export_visits_pdf

ERR_NO_PERM = "No tienes permiso para generar el Reporte de Visitas Realizadas"


async def _require_visits_report_perm(
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    if user.get("role") == "admin":
        return user
    enriched = await enrich_user_with_permissions(user)
    if (enriched.get("effective_permissions") or {}).get("visitas_reporte_regulatorio"):
        return user
    raise HTTPException(status_code=403, detail=ERR_NO_PERM)


def _validate_range(from_date: Optional[str], to_date: Optional[str]) -> None:
    if not from_date or not to_date:
        raise HTTPException(status_code=400, detail="El rango de fechas (Desde/Hasta) es obligatorio")


@api.get("/reports/visits")
async def reports_visits(from_date: Optional[str] = Query(None),
                         to_date: Optional[str] = Query(None),
                         visit_type: Optional[str] = Query(None),
                         site_id: Optional[str] = Query(None),
                         host_user_id: Optional[str] = Query(None),
                         user: Dict[str, Any] = Depends(_require_visits_report_perm)) -> Dict[str, Any]:
    _validate_range(from_date, to_date)
    return await build_visits_report(db, from_date, to_date,
                                     visit_type=visit_type, site_id=site_id,
                                     host_user_id=host_user_id, selfies="thumb")


@api.get("/reports/visits/export.pdf")
async def reports_visits_pdf(from_date: Optional[str] = Query(None),
                             to_date: Optional[str] = Query(None),
                             visit_type: Optional[str] = Query(None),
                             site_id: Optional[str] = Query(None),
                             host_user_id: Optional[str] = Query(None),
                             user: Dict[str, Any] = Depends(_require_visits_report_perm)) -> StreamingResponse:
    _validate_range(from_date, to_date)
    report = await build_visits_report(db, from_date, to_date,
                                       visit_type=visit_type, site_id=site_id,
                                       host_user_id=host_user_id, selfies="full")
    settings = await db.settings.find_one({"_id": "company"}) or {}
    pdf_bytes = export_visits_pdf(report,
                                  company_name=settings.get("company_name") or "Mega Soft",
                                  logo_base64=settings.get("logo_base64"))
    filename = f"reporte_visitas_{from_date}_a_{to_date}.pdf"
    return StreamingResponse(
        iter([pdf_bytes]), media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@api.get("/reports/visits/export.xlsx")
async def reports_visits_xlsx(from_date: Optional[str] = Query(None),
                              to_date: Optional[str] = Query(None),
                              visit_type: Optional[str] = Query(None),
                              site_id: Optional[str] = Query(None),
                              host_user_id: Optional[str] = Query(None),
                              user: Dict[str, Any] = Depends(_require_visits_report_perm)) -> StreamingResponse:
    _validate_range(from_date, to_date)
    report = await build_visits_report(db, from_date, to_date,
                                       visit_type=visit_type, site_id=site_id,
                                       host_user_id=host_user_id, selfies="full")
    xlsx_bytes = export_visits_xlsx(report)
    filename = f"reporte_visitas_{from_date}_a_{to_date}.xlsx"
    return StreamingResponse(
        iter([xlsx_bytes]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
