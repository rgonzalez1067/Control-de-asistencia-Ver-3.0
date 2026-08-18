"""Paquete de routers de la API. Cada módulo registra endpoints sobre el
`api` (APIRouter) definido en server.py mediante side-effect al ser importado.

Uso desde server.py::

    from routes import attendance, novelties, visits  # noqa: F401
"""
