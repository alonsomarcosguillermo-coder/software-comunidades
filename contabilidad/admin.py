from decimal import Decimal

from django.contrib import admin
from django.db.models import DecimalField, Sum, Value
from django.db.models.functions import Coalesce

from .models import Apunte, Asiento, Cuenta

# Nota (ADR 002): el admin de Django NO filtra por despacho. Es solo para el superusuario.

CERO = Value(Decimal("0.00"), output_field=DecimalField(max_digits=12, decimal_places=2))


@admin.register(Cuenta)
class CuentaAdmin(admin.ModelAdmin):
    list_display = ["codigo", "nombre", "comunidad", "es_fondo_reserva", "saldo"]
    list_filter = ["comunidad__despacho", "comunidad", "es_fondo_reserva"]
    search_fields = ["codigo", "nombre", "comunidad__nombre"]

    def get_queryset(self, request):
        # El saldo se calcula (no se guarda): Debe − Haber de todos los apuntes de la cuenta.
        return (
            super()
            .get_queryset(request)
            .annotate(
                _saldo=Coalesce(Sum("apuntes__debe"), CERO) - Coalesce(Sum("apuntes__haber"), CERO)
            )
        )

    @admin.display(description="saldo (D − H)", ordering="_saldo")
    def saldo(self, cuenta):
        return cuenta._saldo


class SoloLecturaMixin:
    """Los asientos se crean con `contabilidad.registro` y son inmutables: aquí solo se ven."""

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class ApunteInline(SoloLecturaMixin, admin.TabularInline):
    model = Apunte
    fields = ["cuenta", "debe", "haber", "concepto"]
    extra = 0


@admin.register(Asiento)
class AsientoAdmin(SoloLecturaMixin, admin.ModelAdmin):
    list_display = ["numero", "fecha", "concepto", "comunidad", "anula"]
    list_filter = ["comunidad__despacho", "comunidad"]
    search_fields = ["concepto"]
    date_hierarchy = "fecha"
    inlines = [ApunteInline]
