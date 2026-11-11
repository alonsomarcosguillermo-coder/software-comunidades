from django.contrib import admin

from .models import Partida, Presupuesto
from .servicios import total_partidas

# Nota (ADR 002): el admin de Django NO filtra por despacho. Es solo para el superusuario.


def _aprobado(presupuesto: Presupuesto | None) -> bool:
    return presupuesto is not None and presupuesto.esta_aprobado


class PartidaInline(admin.TabularInline):
    model = Partida
    fields = ["concepto", "importe"]
    extra = 0

    # Presupuesto aprobado: sus partidas solo se ven (el modelo también lo impide).
    def has_add_permission(self, request, obj=None):
        return not _aprobado(obj) and super().has_add_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        return not _aprobado(obj) and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return not _aprobado(obj) and super().has_delete_permission(request, obj)


@admin.register(Presupuesto)
class PresupuestoAdmin(admin.ModelAdmin):
    list_display = [
        "ejercicio",
        "comunidad",
        "fecha_aprobacion",
        "total_gastos",
        "aportacion_fondo_reserva",
        "total",
    ]
    list_filter = ["comunidad__despacho", "comunidad", "ejercicio"]
    search_fields = ["comunidad__nombre"]
    inlines = [PartidaInline]

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("partidas")

    def get_readonly_fields(self, request, obj=None):
        if _aprobado(obj):
            return ["comunidad", "ejercicio", "aportacion_fondo_reserva"]
        return []

    def has_delete_permission(self, request, obj=None):
        return not _aprobado(obj) and super().has_delete_permission(request, obj)

    def get_actions(self, request):
        # "Borrar seleccionados" no pasa por has_delete_permission(obj): fuera.
        acciones = super().get_actions(request)
        acciones.pop("delete_selected", None)
        return acciones

    # Si en el mismo formulario se añaden partidas Y se pone la fecha de aprobación, Django
    # guarda primero el presupuesto (ya aprobado) y luego las partidas, que el modelo
    # rechazaría. Por eso la aprobación se guarda al final, después de las partidas.
    def save_model(self, request, obj, form, change):
        obj._aprobar_el = None
        if obj.fecha_aprobacion and not (change and form.initial.get("fecha_aprobacion")):
            obj._aprobar_el, obj.fecha_aprobacion = obj.fecha_aprobacion, None
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        presupuesto = form.instance
        if presupuesto._aprobar_el:
            presupuesto.fecha_aprobacion = presupuesto._aprobar_el
            presupuesto.save(update_fields=["fecha_aprobacion"])

    def _gastos(self, presupuesto):
        return total_partidas(p.importe for p in presupuesto.partidas.all())

    @admin.display(description="gastos")
    def total_gastos(self, presupuesto):
        return self._gastos(presupuesto)

    @admin.display(description="total a cobrar")
    def total(self, presupuesto):
        return self._gastos(presupuesto) + presupuesto.aportacion_fondo_reserva
