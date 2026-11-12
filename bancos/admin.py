from django.contrib import admin

from .models import CobroRecibo, Conciliacion, Extracto, Movimiento

# Nota (ADR 002): el admin de Django NO filtra por despacho. Es solo para el superusuario.
# Los extractos se importan desde la página de extractos de la comunidad y son inmutables.


class SoloLecturaMixin:
    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class MovimientoInline(SoloLecturaMixin, admin.TabularInline):
    model = Movimiento
    fields = ["orden", "fecha_operacion", "concepto_comun", "importe", "referencia_1"]
    extra = 0


@admin.register(Extracto)
class ExtractoAdmin(SoloLecturaMixin, admin.ModelAdmin):
    list_display = ["comunidad", "fecha_inicial", "fecha_final", "saldo_final", "importado_en"]
    list_filter = ["comunidad__despacho", "comunidad"]
    exclude = ["registros"]
    inlines = [MovimientoInline]


class CobroReciboInline(SoloLecturaMixin, admin.TabularInline):
    model = CobroRecibo
    fields = ["recibo"]
    extra = 0


@admin.register(Conciliacion)
class ConciliacionAdmin(SoloLecturaMixin, admin.ModelAdmin):
    """Solo lectura: se concilia y se deshace desde el extracto (con su contra-asiento)."""

    list_display = ["movimiento", "asiento", "remesa", "cuenta", "automatica", "creada_en"]
    list_filter = ["automatica", "movimiento__extracto__comunidad"]
    inlines = [CobroReciboInline]
