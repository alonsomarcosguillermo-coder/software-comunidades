from decimal import Decimal

from django.db.models import BooleanField, Count, DecimalField, ExpressionWrapper, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.views.generic import ListView

from core.aislamiento import FiltradoPorDespachoMixin

from .models import CAMPO_DESPACHO, Comunidad
from .servicios import SUMA_COEFICIENTES


class ListaComunidades(FiltradoPorDespachoMixin, ListView):
    """Comunidades del despacho del usuario, con búsqueda por nombre.

    Con HTMX: al escribir en el buscador, el navegador pide esta misma URL con la cabecera
    `HX-Request` y solo se devuelve (y se sustituye) la tabla, no la página entera.
    """

    model = Comunidad
    campo_despacho = CAMPO_DESPACHO[Comunidad]
    context_object_name = "comunidades"
    template_name = "fincas/lista_comunidades.html"
    plantilla_htmx = "fincas/_tabla_comunidades.html"

    def get_queryset(self):
        cero = Value(Decimal("0"), output_field=DecimalField(max_digits=7, decimal_places=4))
        comunidades = (
            super()  # ya filtrado por el despacho del usuario (FiltradoPorDespachoMixin)
            .get_queryset()
            .annotate(
                num_inmuebles=Count("inmuebles"),
                suma_coeficientes=Coalesce(Sum("inmuebles__coeficiente"), cero),
            )
            .annotate(
                # R-COEF-01: los coeficientes suman exactamente 100 %.
                cuadran=ExpressionWrapper(
                    Q(suma_coeficientes=SUMA_COEFICIENTES), output_field=BooleanField()
                )
            )
        )
        if busqueda := self.request.GET.get("q", "").strip():
            comunidades = comunidades.filter(nombre__icontains=busqueda)
        return comunidades

    def get_template_names(self):
        if self.request.headers.get("HX-Request"):
            return [self.plantilla_htmx]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        return super().get_context_data(busqueda=self.request.GET.get("q", ""), **kwargs)
