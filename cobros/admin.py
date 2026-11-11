from django.contrib import admin, messages
from django.utils import timezone

from .derramas import DerramaInvalida, emitir_derrama
from .models import (
    Cuota,
    CuotaDerrama,
    Derrama,
    Emision,
    Mandato,
    Partida,
    Presupuesto,
    Recibo,
    Remesa,
)
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
        "periodos",
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
            return ["comunidad", "ejercicio", "aportacion_fondo_reserva", "periodos"]
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


class SoloLecturaMixin:
    """Emisiones y cuotas se crean con `cobros.emision.emitir_cuotas` y son inmutables."""

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class CuotaInline(SoloLecturaMixin, admin.TabularInline):
    model = Cuota
    fields = ["inmueble", "importe"]
    extra = 0


@admin.register(Emision)
class EmisionAdmin(SoloLecturaMixin, admin.ModelAdmin):
    list_display = ["presupuesto", "periodo", "fecha", "asiento"]
    list_filter = ["presupuesto__comunidad__despacho", "presupuesto__comunidad"]
    date_hierarchy = "fecha"
    inlines = [CuotaInline]


class CuotaDerramaInline(admin.TabularInline):
    """Cuotas de una derrama emitida: solo se ven (son inmutables)."""

    model = CuotaDerrama
    fields = ["plazo", "vencimiento", "inmueble", "importe"]
    readonly_fields = fields
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Derrama)
class DerramaAdmin(admin.ModelAdmin):
    list_display = [
        "concepto",
        "comunidad",
        "importe",
        "grupo",
        "plazos",
        "primer_vencimiento",
        "fecha_acuerdo",
        "emitida",
    ]
    list_filter = ["comunidad__despacho", "comunidad"]
    search_fields = ["concepto", "comunidad__nombre"]
    inlines = [CuotaDerramaInline]
    actions = ["emitir"]

    def get_readonly_fields(self, request, obj=None):
        if obj is not None and obj.esta_emitida:
            return [f.name for f in Derrama._meta.fields if f.editable and f.name != "id"]
        return []

    def has_delete_permission(self, request, obj=None):
        emitida = obj is not None and obj.esta_emitida
        return not emitida and super().has_delete_permission(request, obj)

    def get_actions(self, request):
        # "Borrar seleccionados" no pasa por has_delete_permission(obj): fuera.
        acciones = super().get_actions(request)
        acciones.pop("delete_selected", None)
        return acciones

    @admin.display(description="emitida", boolean=True)
    def emitida(self, derrama):
        return derrama.esta_emitida

    @admin.action(description="Emitir las derramas seleccionadas (asiento y cuotas)")
    def emitir(self, request, queryset):
        hoy = timezone.localdate()
        for derrama in queryset:
            try:
                emitir_derrama(derrama, hoy)
            except DerramaInvalida as error:
                self.message_user(request, f"{derrama}: {error}", messages.ERROR)
            else:
                self.message_user(request, f"{derrama}: emitida.", messages.SUCCESS)


# --- Mandatos y recibos (T2.4) ------------------------------------------------------------


@admin.register(Mandato)
class MandatoAdmin(admin.ModelAdmin):
    """Alta de mandatos y baja (fecha de baja). Un mandato firmado no se modifica."""

    list_display = ["referencia", "propietario", "comunidad", "cuenta", "fecha_firma", "fecha_baja"]
    list_filter = ["comunidad__despacho", "comunidad"]
    search_fields = ["referencia", "propietario__nombre", "titular_cuenta"]
    autocomplete_fields = ["propietario"]

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return []
        return ["comunidad", "propietario", "referencia", "titular_cuenta", "iban", "fecha_firma"]

    @admin.display(description="cuenta")
    def cuenta(self, mandato):
        return mandato.iban_oculto  # el IBAN completo, solo en la ficha


@admin.register(Recibo)
class ReciboAdmin(SoloLecturaMixin, admin.ModelAdmin):
    list_display = ["numero", "comunidad", "inmueble", "propietario", "vencimiento", "importe"]
    list_filter = ["comunidad__despacho", "comunidad"]
    search_fields = ["concepto", "propietario__nombre", "inmueble__referencia"]
    date_hierarchy = "vencimiento"


@admin.register(Remesa)
class RemesaAdmin(SoloLecturaMixin, admin.ModelAdmin):
    """Remesas: solo lectura. El fichero se descarga desde la página de recibos."""

    list_display = ["numero", "comunidad", "fecha_cobro", "num_recibos", "total", "creada_en"]
    list_filter = ["comunidad__despacho", "comunidad"]
    exclude = ["xml"]  # lleva IBAN completos; no hace falta enseñarlo aquí
