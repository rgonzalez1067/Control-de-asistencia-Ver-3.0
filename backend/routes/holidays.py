"""Endpoints del Calendario de Días Festivos (feb-2026).

Cada festivo se persiste como un único documento. Si `is_recurrent=true`, la
fecha vale para el mismo (mes, día) en TODOS los años (cero mantenimiento).
La lógica de expansión ocurre en tiempo de consulta a través de `is_holiday()`
que llama la Matriz de Asistencia.
"""

from datetime import datetime, timezone
from deps import (
    api, db, get_current_user,
    now_utc, new_id, strip_mongo_id,
    HTTPException, Depends, Request,
    Any, Dict, List, Optional,
    audit_entity,
)
from pydantic import BaseModel, Field


# ------------------------------------------------------------------ Modelos
class HolidayIn(BaseModel):
    date: str                       # YYYY-MM-DD (año 0001 si is_recurrent y no interesa el año)
    name: str = Field(..., min_length=1, max_length=120)
    is_recurrent: bool = False


def _public(doc: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "holiday_id": doc.get("holiday_id"),
        "date": doc.get("date"),
        "name": doc.get("name"),
        "is_recurrent": bool(doc.get("is_recurrent")),
        "created_at": doc.get("created_at"),
        "created_by": doc.get("created_by"),
    }


def _validate_date(iso: str) -> None:
    try:
        datetime.strptime(iso, "%Y-%m-%d")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Fecha inválida (formato YYYY-MM-DD)") from exc


async def _require_admin(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Requiere permisos de administrador")
    return user


# ------------------------------------------------------------------ Endpoints
@api.get("/holidays")
async def holidays_list(_: Dict[str, Any] = Depends(get_current_user)) -> List[Dict[str, Any]]:
    """Lista TODOS los festivos (recurrentes + fijos)."""
    docs = await db.holidays.find({}).sort("date", 1).to_list(1000)
    return [_public(d) for d in docs]


@api.post("/holidays")
async def holidays_create(request: Request, payload: HolidayIn,
                          admin: Dict[str, Any] = Depends(_require_admin)) -> Dict[str, Any]:
    _validate_date(payload.date)
    # Deduplicar: mismo (mes, día) recurrente + mismo día no puede coexistir.
    if payload.is_recurrent:
        md = payload.date[5:]  # MM-DD
        clash = await db.holidays.find_one({"is_recurrent": True, "date": {"$regex": f"-{md}$"}})
        if clash:
            raise HTTPException(status_code=409, detail=f"Ya existe un feriado recurrente en {md}: {clash.get('name')}")
    else:
        clash = await db.holidays.find_one({"date": payload.date, "is_recurrent": False})
        if clash:
            raise HTTPException(status_code=409, detail=f"Ya existe un feriado el {payload.date}: {clash.get('name')}")
    doc = {
        "holiday_id": new_id("hd", 10),
        "date": payload.date,
        "name": payload.name.strip(),
        "is_recurrent": payload.is_recurrent,
        "created_by": admin["user_id"],
        "created_at": now_utc(),
    }
    await db.holidays.insert_one(doc)
    await audit_entity(request, "CREATE", "holidays", doc["holiday_id"], after=doc, actor=admin)
    return _public(doc)


@api.put("/holidays/{holiday_id}")
async def holidays_update(request: Request, holiday_id: str, payload: HolidayIn,
                          admin: Dict[str, Any] = Depends(_require_admin)) -> Dict[str, Any]:
    _validate_date(payload.date)
    before = await db.holidays.find_one({"holiday_id": holiday_id})
    if not before:
        raise HTTPException(status_code=404, detail="Feriado no encontrado")
    await db.holidays.update_one(
        {"holiday_id": holiday_id},
        {"$set": {
            "date": payload.date,
            "name": payload.name.strip(),
            "is_recurrent": payload.is_recurrent,
            "updated_at": now_utc(),
            "updated_by": admin["user_id"],
        }},
    )
    doc = await db.holidays.find_one({"holiday_id": holiday_id})
    await audit_entity(request, "UPDATE", "holidays", holiday_id, before=before, after=doc, actor=admin)
    return _public(doc)


@api.delete("/holidays/{holiday_id}")
async def holidays_delete(request: Request, holiday_id: str,
                          admin: Dict[str, Any] = Depends(_require_admin)) -> Dict[str, Any]:
    before = await db.holidays.find_one({"holiday_id": holiday_id})
    res = await db.holidays.delete_one({"holiday_id": holiday_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Feriado no encontrado")
    await audit_entity(request, "DELETE", "holidays", holiday_id, before=before, actor=admin)
    return {"ok": True}
