"""Procesador de contexto: variables que llegan a TODAS las plantillas (ver settings).

`es_vecino` decide si el menú enseña "Mi portal". Se calcula una vez por petición, en vez
de que la plantilla consulte la base de datos cada vez que lo necesite.
"""

from .consultas import es_vecino


def portal(request):
    usuario = getattr(request, "user", None)
    return {"es_vecino": bool(usuario and usuario.is_authenticated and es_vecino(usuario))}
