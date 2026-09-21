"""Endpoints del Reporte General de Accesos (sep-2026).

Acceso: RBAC `reporte_general_accesos`. Admin siempre pasa.
Jerarquía de visualización (misma regla global): admin y director ven toda la
nómina; gerente y coordinador ven su equipo a 2 niveles; otros roles con el
permiso solo se ven a sí mismos.
"""
from typing import List, Optional, Set
from deps import (
    api, db, get_current_user, enrich_user_with_permissions,
    supervisor_scope_ids, LEADER_ROLES,
    HTTPException, Depends, Query,
    Any, Dict,
)
from fastapi.responses import StreamingResponse

from general_access_report import build_general_access_report, export_general_access_pdf

ERR_NO_PERM = "No tienes permiso para consultar el Reporte General de Accesos"


async def _require_perm(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    if user.get("role") == "admin":
        return user
    enriched = await enrich_user_with_permissions(user)
    if (enriched.get("effective_permissions") or {}).get("reporte_general_accesos"):
        return user
    raise HTTPException(status_code=403, detail=ERR_NO_PERM)


async def _apply_scope(user: Dict[str, Any]) -> Optional[List[str]]:
    """None = sin límite (admin). Lista (posiblemente vacía) = scope restringido."""
    if user.get("role") == "admin":
        return None
    if user.get("role") in LEADER_ROLES:
        scope: Set[str] = set(await supervisor_scope_ids(user))
        return list(scope)
    return [user["user_id"]]


def _validate_range(from_date: Optional[str], to_date: Optional[str]) -> None:
    if not from_date or not to_date:
        raise HTTPException(status_code=400, detail="El rango de fechas (Desde/Hasta) es obligatorio")


@api.get("/reports/general-access")
async def reports_general_access(from_date: Optional[str] = Query(None),
                                 to_date: Optional[str] = Query(None),
                                 department_ids: Optional[List[str]] = Query(None),
                                 site_id: Optional[str] = Query(None),
                                 user: Dict[str, Any] = Depends(_require_perm)) -> Dict[str, Any]:
    _validate_range(from_date, to_date)
    scope = await _apply_scope(user)
    return await build_general_access_report(db, from_date, to_date,
                                             department_ids=department_ids or None,
                                             site_id=site_id or None,
                                             scope_user_ids=scope)


@api.get("/reports/general-access/export.pdf")
async def reports_general_access_pdf(from_date: Optional[str] = Query(None),
                                     to_date: Optional[str] = Query(None),
                                     department_ids: Optional[List[str]] = Query(None),
                                     site_id: Optional[str] = Query(None),
                                     user: Dict[str, Any] = Depends(_require_perm)) -> StreamingResponse:
    _validate_range(from_date, to_date)
    scope = await _apply_scope(user)
    report = await build_general_access_report(db, from_date, to_date,
                                               department_ids=department_ids or None,
                                               site_id=site_id or None,
                                               scope_user_ids=scope)
    settings = await db.settings.find_one({"_id": "company"}) or {}
    pdf_bytes = export_general_access_pdf(
        report,
        company_name=settings.get("company_name") or settings.get("name") or "Mega Soft",
        logo_base64=settings.get("logo_base64"),
    )
    filename = f"reporte_general_accesos_{from_date}_a_{to_date}.pdf"
    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
