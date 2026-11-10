"""Aislamiento entre despachos (multi-tenant).

Regla del proyecto: toda consulta de datos de negocio se filtra por el despacho del
usuario. Aquí están las dos piezas para hacerlo siempre igual:

- `filtrar_por_despacho(queryset, usuario)`: para usar en cualquier sitio.
- `FiltradoPorDespachoMixin`: para vistas basadas en clase (ListView, DetailView,
  UpdateView...). Al filtrar `get_queryset()`, un objeto de otro despacho da 404.

Ambas fallan "cerradas": si el usuario no tiene despacho, no ve nada.
"""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import QuerySet


def filtrar_por_despacho[T: QuerySet](queryset: T, usuario, campo: str = "despacho") -> T:
    """Devuelve solo las filas del despacho de `usuario`.

    `campo` es el camino desde el modelo hasta el despacho, con la sintaxis de
    búsquedas de Django: "despacho" si el modelo tiene la FK directa, o p. ej.
    "comunidad__despacho" si llega a través de su comunidad.
    """
    despacho_id = getattr(usuario, "despacho_id", None)
    if despacho_id is None:
        return queryset.none()
    return queryset.filter(**{campo: despacho_id})


class FiltradoPorDespachoMixin(LoginRequiredMixin):
    """Exige sesión iniciada y limita el queryset de la vista al despacho del usuario.

    Va a la IZQUIERDA de la vista genérica: `class X(FiltradoPorDespachoMixin, ListView)`.
    Si el modelo llega al despacho por otra relación, sobrescribe `campo_despacho`.
    """

    campo_despacho = "despacho"

    def get_queryset(self):
        return filtrar_por_despacho(super().get_queryset(), self.request.user, self.campo_despacho)
