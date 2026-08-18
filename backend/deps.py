"""Dependencias/helpers compartidos entre server.py y los routers.

Este módulo es intencionalmente delgado: re-exporta los símbolos que los routers
necesitan de ``server.py``. La técnica evita mover cientos de líneas de código
en un solo commit y elimina el riesgo de circular imports: los routers hacen
``from deps import api, db, ...`` sin conocer server.py directamente.

server.py sigue siendo la fuente de verdad de los helpers. En una segunda fase
podremos mover las implementaciones acá y dejar server.py sólo con el
bootstrap.
"""
from server import (  # noqa: F401
    # Core
    app, api, db, logger,
    APP_TZ, MONGO_URL, DB_NAME,
    # Auth deps
    get_current_user, require_roles,
    # Constants
    LEADER_ROLES, LEADER_OR_ADMIN_ROLES,
    # Helpers
    now_utc, new_id, strip_mongo_id, sanitize_user,
    enrich_user_with_permissions, supervisor_scope_ids,
    hash_password, verify_password, create_access_token,
    haversine_m, normalize_role, validate_password_policy,
    # Pydantic models (moved as they get referenced by routers)
    LoginIn, RegisterIn, ChangePasswordIn, ChangePinIn, ResetPasswordIn,
    AttendanceCheckIn, JustifyIn, JustifyDecideIn,
    NoveltyIn, NoveltyDecideIn, NoveltyPatchIn,
    UserPermissionsIn,
)

from datetime import datetime, timezone, timedelta  # noqa: F401
from typing import Any, Dict, List, Optional  # noqa: F401
from fastapi import HTTPException, Depends, Query  # noqa: F401
