"""Endpoints de catálogos maestros: Settings, Sites, Departments + Docs (manuales).

Migrado desde server.py durante la Fase A · Iteración 3 (feb-2026).
"""
from deps import (
    api, db, get_current_user, require_roles,
    now_utc, new_id, strip_mongo_id,
    SettingsIn, SiteIn, SiteResolveIn, DepartmentIn,
    HTTPException, Depends,
    Any, Dict, List,
    FileResponse,
)


# ==================================================================
# SETTINGS
# ==================================================================
@api.get("/settings")
async def settings_get() -> Dict[str, Any]:
    doc = await db.settings.find_one({"_id": "company"}) or {"_id": "company"}
    doc["id"] = str(doc.pop("_id"))
    return doc


@api.put("/settings")
async def settings_put(payload: SettingsIn,
                       _: Dict[str, Any] = Depends(require_roles("admin"))) -> Dict[str, Any]:
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    updates["updated_at"] = now_utc()
    await db.settings.update_one({"_id": "company"}, {"$set": updates}, upsert=True)
    doc = await db.settings.find_one({"_id": "company"})
    doc["id"] = str(doc.pop("_id"))
    return doc


# ==================================================================
# DOCS (Manuales de usuario)
# ==================================================================
@api.get("/docs/manual-usuario", include_in_schema=False)
async def manual_usuario():
    """Descarga el manual de usuario legado (retro-compatibilidad)."""
    return FileResponse(
        "/app/manual/manual-usuario-megasoft.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename="manual-usuario-megasoft.docx",
    )


@api.get("/docs/manual-empleado", include_in_schema=False)
async def manual_empleado():
    """Descarga el manual del empleado (inicio, cambio de contraseña, registro de rostro)."""
    return FileResponse(
        "/app/manual/manual-empleado-megasoft.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename="manual-empleado-megasoft.docx",
    )


@api.get("/docs/manual-supervisor", include_in_schema=False)
async def manual_supervisor():
    """Descarga el manual del supervisor (Mi equipo, Novedades, Matriz, Horarios, Reportes)."""
    return FileResponse(
        "/app/manual/manual-supervisor-megasoft.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename="manual-supervisor-megasoft.docx",
    )


# ==================================================================
# SITES
# ==================================================================
@api.get("/sites")
async def sites_list(_: Dict[str, Any] = Depends(get_current_user)) -> List[Dict[str, Any]]:
    docs = await db.sites.find({}).to_list(500)
    return [strip_mongo_id(d) for d in docs]


@api.post("/sites")
async def sites_create(payload: SiteIn,
                       _: Dict[str, Any] = Depends(require_roles("admin"))) -> Dict[str, Any]:
    doc = payload.model_dump()
    doc["site_id"] = new_id("site")
    doc["created_at"] = now_utc()
    await db.sites.insert_one(doc)
    return strip_mongo_id(doc)


@api.put("/sites/{site_id}")
async def sites_update(site_id: str, payload: SiteIn,
                       _: Dict[str, Any] = Depends(require_roles("admin"))) -> Dict[str, Any]:
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="Sin cambios")
    res = await db.sites.update_one({"site_id": site_id}, {"$set": updates})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Sede no encontrada")
    doc = await db.sites.find_one({"site_id": site_id})
    return strip_mongo_id(doc)


@api.delete("/sites/{site_id}")
async def sites_delete(site_id: str,
                       _: Dict[str, Any] = Depends(require_roles("admin"))) -> Dict[str, bool]:
    res = await db.sites.delete_one({"site_id": site_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Sede no encontrada")
    return {"ok": True}


@api.post("/sites/resolve-link")
async def sites_resolve_link(payload: SiteResolveIn,
                             _: Dict[str, Any] = Depends(require_roles("admin"))) -> Dict[str, Any]:
    """Intenta extraer lat/lng de un link de Google Maps."""
    import re
    link = payload.link
    m = re.search(r"@(-?\d+\.\d+),(-?\d+\.\d+)", link)
    if not m:
        m = re.search(r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)", link)
    if not m:
        m = re.search(r"[?&]q=(-?\d+\.\d+),(-?\d+\.\d+)", link)
    if not m:
        m = re.search(r"(-?\d+\.\d+),\s*(-?\d+\.\d+)", link)
    if not m:
        raise HTTPException(status_code=400, detail="No se pudo extraer lat/lng del link")
    return {"latitude": float(m.group(1)), "longitude": float(m.group(2))}


# ==================================================================
# DEPARTMENTS
# ==================================================================
@api.get("/departments")
async def departments_list(_: Dict[str, Any] = Depends(get_current_user)) -> List[Dict[str, Any]]:
    docs = await db.departments.find({}).sort("name", 1).to_list(500)
    return [strip_mongo_id(d) for d in docs]


@api.post("/departments")
async def departments_create(payload: DepartmentIn,
                             _: Dict[str, Any] = Depends(require_roles("admin"))) -> Dict[str, Any]:
    doc = payload.model_dump()
    doc["department_id"] = new_id("dept", 10)
    doc["created_at"] = now_utc()
    await db.departments.insert_one(doc)
    return strip_mongo_id(doc)


@api.put("/departments/{department_id}")
async def departments_update(department_id: str, payload: DepartmentIn,
                             _: Dict[str, Any] = Depends(require_roles("admin"))) -> Dict[str, Any]:
    updates = payload.model_dump(exclude_unset=True)
    res = await db.departments.update_one({"department_id": department_id}, {"$set": updates})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Departamento no encontrado")
    doc = await db.departments.find_one({"department_id": department_id})
    return strip_mongo_id(doc)


@api.delete("/departments/{department_id}")
async def departments_delete(department_id: str,
                             _: Dict[str, Any] = Depends(require_roles("admin"))) -> Dict[str, bool]:
    res = await db.departments.delete_one({"department_id": department_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Departamento no encontrado")
    return {"ok": True}
