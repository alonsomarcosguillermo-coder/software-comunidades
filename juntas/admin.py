from django.contrib import admin

from .models import Asistente, Celebracion, Citacion, Junta, PuntoOrden

# Nota (ADR 002): el admin de Django NO filtra por despacho. Es solo para el superusuario.
# Las juntas se preparan y convocan desde la web; una vez convocadas, el modelo impide
# cambiarlas (también desde aquí).


class PuntoOrdenInline(admin.TabularInline):
    model = PuntoOrden
    fields = ["orden", "titulo", "mayoria", "computa_ausentes"]
    extra = 0


class CitacionInline(admin.TabularInline):
    model = Citacion
    fields = ["propietario", "email", "enviada_en", "moroso"]
    readonly_fields = fields
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Junta)
class JuntaAdmin(admin.ModelAdmin):
    list_display = ["comunidad", "tipo", "primera_convocatoria", "convocada_el"]
    list_filter = ["comunidad__despacho", "tipo"]
    inlines = [PuntoOrdenInline, CitacionInline]

    def has_change_permission(self, request, obj=None):
        if obj is not None and obj.esta_convocada:
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.esta_convocada:
            return False
        return super().has_delete_permission(request, obj)


# --- T4.3 ---------------------------------------------------------------------------------


class AsistenteInline(admin.TabularInline):
    model = Asistente
    fields = ["propietario", "cuota", "asistencia", "representante", "deuda", "deuda_impugnada"]
    readonly_fields = fields
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Celebracion)
class CelebracionAdmin(admin.ModelAdmin):
    """Solo lectura: se celebra desde la web (los votos dependen de R-VOT-01 y del acta)."""

    list_display = ["junta", "iniciada_en", "convocatoria", "cerrada_en"]
    inlines = [AsistenteInline]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
