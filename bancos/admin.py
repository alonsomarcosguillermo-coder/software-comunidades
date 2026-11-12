from django.contrib import admin

from .models import Extracto, Movimiento

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
