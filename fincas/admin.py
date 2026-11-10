from decimal import Decimal

from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db.models import Count, Sum
from django.forms.models import BaseInlineFormSet

from .models import Comunidad, Inmueble, Propietario, Titularidad
from .servicios import SUMA_COEFICIENTES, CoeficientesInvalidos, comprobar_coeficientes

# Nota (ADR 002): el admin de Django NO filtra por despacho. Es solo para el superusuario.


class InmueblesFormSet(BaseInlineFormSet):
    """R-COEF-01: al guardar la comunidad, los coeficientes de todos sus inmuebles deben
    sumar exactamente 100 %. Se comprueba sobre el conjunto del formulario (no inmueble a
    inmueble) para poder repartir coeficientes entre varios inmuebles en una sola edición."""

    def clean(self):
        super().clean()
        if any(self.errors):
            return  # primero que se corrijan los errores de cada fila
        coeficientes = [
            form.cleaned_data["coeficiente"]
            for form in self.forms
            if form.cleaned_data and not form.cleaned_data.get("DELETE")
        ]
        if not coeficientes and not self.instance.pk:
            return  # se puede crear la comunidad y añadir los inmuebles después
        try:
            comprobar_coeficientes(coeficientes)
        except CoeficientesInvalidos as error:
            raise ValidationError(str(error)) from error


class InmuebleInline(admin.TabularInline):
    model = Inmueble
    formset = InmueblesFormSet
    extra = 0
    fields = ["tipo", "referencia", "coeficiente"]
    show_change_link = True


@admin.register(Comunidad)
class ComunidadAdmin(admin.ModelAdmin):
    list_display = ["nombre", "despacho", "num_inmuebles", "suma_coeficientes", "cuadran"]
    list_filter = ["despacho"]
    search_fields = ["nombre", "nif", "direccion"]
    inlines = [InmuebleInline]

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .annotate(_num=Count("inmuebles"), _suma=Sum("inmuebles__coeficiente"))
        )

    @admin.display(description="inmuebles", ordering="_num")
    def num_inmuebles(self, comunidad):
        return comunidad._num

    @admin.display(description="suma coef. (%)", ordering="_suma")
    def suma_coeficientes(self, comunidad):
        return comunidad._suma or Decimal("0")

    @admin.display(description="R-COEF-01", boolean=True)
    def cuadran(self, comunidad):
        return comunidad._suma == SUMA_COEFICIENTES


class TitularidadInline(admin.TabularInline):
    model = Titularidad
    extra = 0
    autocomplete_fields = ["inmueble", "propietario"]


@admin.register(Inmueble)
class InmuebleAdmin(admin.ModelAdmin):
    list_display = ["referencia", "tipo", "comunidad", "coeficiente"]
    list_filter = ["tipo", "comunidad__despacho", "comunidad"]
    search_fields = ["referencia", "comunidad__nombre"]
    # Los inmuebles y sus coeficientes se dan de alta y se editan desde la comunidad, para
    # comprobar R-COEF-01 sobre el conjunto. Aquí solo se gestionan sus titulares.
    readonly_fields = ["comunidad", "tipo", "referencia", "coeficiente"]
    inlines = [TitularidadInline]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Propietario)
class PropietarioAdmin(admin.ModelAdmin):
    list_display = ["nombre", "despacho"]
    list_filter = ["despacho"]
    search_fields = ["nombre", "nif", "email"]
    inlines = [TitularidadInline]
