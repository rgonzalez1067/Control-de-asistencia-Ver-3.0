"""Endpoints RBAC: gestión de Perfiles de Acceso (Access Profiles).

Migrado desde server.py durante la Fase A · Iteración 3 (feb-2026).
"""
from deps import (
    api, db, require_roles,
    now_utc, new_id, strip_mongo_id,
    MENU_CATALOG, MENU_KEYS,
    AccessProfileIn, AssignProfileIn, AssignProfileToDeptIn,
    HTTPException, Depends, Request,
    Any, Dict, List,
    audit_entity,
)

ERR_PROFILE_NOT_FOUND = "Perfil no encontrado"


def _access_profile_to_public(p: Dict[str, Any]) -> Dict[str, Any]:
    p = strip_mongo_id(dict(p))
    perms = p.get("permissions", {}) or {}
    p["permissions"] = {k: bool(perms.get(k, False)) for k in MENU_KEYS}
    return p


@api.get("/access-profiles/catalog")
async def access_profiles_catalog(_: Dict[str, Any] = Depends(require_roles("admin"))) -> Dict[str, Any]:
    """Catálogo canónico de opciones que se pueden gobernar por perfil."""
    return {"items": MENU_CATALOG, "keys": MENU_KEYS}


@api.get("/access-profiles")
async def access_profiles_list(_: Dict[str, Any] = Depends(require_roles("admin"))) -> List[Dict[str, Any]]:
    docs = await db.access_profiles.find({}).sort("name", 1).to_list(1000)
    return [_access_profile_to_public(d) for d in docs]


@api.post("/access-profiles")
async def access_profiles_create(request: Request, payload: AccessProfileIn,
                                 actor: Dict[str, Any] = Depends(require_roles("admin"))) -> Dict[str, Any]:
    if await db.access_profiles.find_one({"name": payload.name.strip()}):
        raise HTTPException(status_code=409, detail=f"Ya existe un perfil con el nombre '{payload.name}'")
    doc = {
        "profile_id": new_id("prof"),
        "name": payload.name.strip(),
        "description": (payload.description or "").strip() or None,
        "permissions": {k: bool(payload.permissions.get(k, False)) for k in MENU_KEYS},
        "is_system": False,
        "created_at": now_utc(),
        "updated_at": now_utc(),
    }
    await db.access_profiles.insert_one(doc)
    await audit_entity(request, "CREATE", "access_profiles", doc["profile_id"], after=doc, actor=actor)
    return _access_profile_to_public(doc)


@api.put("/access-profiles/{profile_id}")
async def access_profiles_update(request: Request, profile_id: str, payload: AccessProfileIn,
                                 actor: Dict[str, Any] = Depends(require_roles("admin"))) -> Dict[str, Any]:
    existing = await db.access_profiles.find_one({"profile_id": profile_id})
    if not existing:
        raise HTTPException(status_code=404, detail=ERR_PROFILE_NOT_FOUND)
    dupe = await db.access_profiles.find_one({
        "name": {"$regex": f"^{payload.name.strip()}$", "$options": "i"},
        "profile_id": {"$ne": profile_id},
    })
    if dupe:
        raise HTTPException(status_code=409, detail=f"Ya existe otro perfil con el nombre '{payload.name}'")
    updates = {
        "name": payload.name.strip(),
        "description": (payload.description or "").strip() or None,
        "permissions": {k: bool(payload.permissions.get(k, False)) for k in MENU_KEYS},
        "updated_at": now_utc(),
    }
    await db.access_profiles.update_one({"profile_id": profile_id}, {"$set": updates})
    doc = await db.access_profiles.find_one({"profile_id": profile_id})
    await audit_entity(request, "UPDATE", "access_profiles", profile_id, before=existing, after=doc, actor=actor)
    return _access_profile_to_public(doc)


@api.delete("/access-profiles/{profile_id}")
async def access_profiles_delete(request: Request, profile_id: str,
                                 actor: Dict[str, Any] = Depends(require_roles("admin"))) -> Dict[str, bool]:
    prof = await db.access_profiles.find_one({"profile_id": profile_id})
    if not prof:
        raise HTTPException(status_code=404, detail=ERR_PROFILE_NOT_FOUND)
    if prof.get("is_system"):
        raise HTTPException(status_code=400, detail="Los perfiles del sistema no se pueden eliminar")
    in_use = await db.users.count_documents({"access_profile_id": profile_id})
    if in_use:
        await db.users.update_many(
            {"access_profile_id": profile_id},
            {"$set": {"access_profile_id": None}},
        )
    await db.access_profiles.delete_one({"profile_id": profile_id})
    await audit_entity(request, "DELETE", "access_profiles", profile_id, before=prof, actor=actor,
                        extra={"users_detached": in_use})
    return {"ok": True}


@api.put("/users/{user_id}/access-profile")
async def user_set_access_profile(user_id: str, payload: AssignProfileIn,
                                  _: Dict[str, Any] = Depends(require_roles("admin"))) -> Dict[str, Any]:
    if payload.profile_id:
        prof = await db.access_profiles.find_one({"profile_id": payload.profile_id})
        if not prof:
            raise HTTPException(status_code=404, detail=ERR_PROFILE_NOT_FOUND)
    res = await db.users.update_one(
        {"user_id": user_id},
        {"$set": {"access_profile_id": payload.profile_id}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return {"ok": True, "user_id": user_id, "profile_id": payload.profile_id}


@api.post("/access-profiles/assign-department")
async def access_profile_assign_department(payload: AssignProfileToDeptIn,
                                           _: Dict[str, Any] = Depends(require_roles("admin"))) -> Dict[str, Any]:
    """Aplica un perfil a TODOS los usuarios de un departamento en batch."""
    if payload.profile_id:
        prof = await db.access_profiles.find_one({"profile_id": payload.profile_id})
        if not prof:
            raise HTTPException(status_code=404, detail=ERR_PROFILE_NOT_FOUND)
    q = {
        "department_id": payload.department_id,
        "role": {"$nin": ["admin", "kiosk"]},
    }
    res = await db.users.update_many(q, {"$set": {"access_profile_id": payload.profile_id}})
    return {"ok": True, "matched": res.matched_count, "modified": res.modified_count}
