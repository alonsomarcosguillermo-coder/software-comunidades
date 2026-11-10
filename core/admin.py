from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Despacho, Usuario


@admin.register(Despacho)
class DespachoAdmin(admin.ModelAdmin):
    list_display = ["nombre", "creado_en"]
    search_fields = ["nombre"]


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    list_display = [*UserAdmin.list_display, "despacho"]
    list_filter = [*UserAdmin.list_filter, "despacho"]
    fieldsets = [*UserAdmin.fieldsets, ("Despacho", {"fields": ["despacho"]})]
    add_fieldsets = [*UserAdmin.add_fieldsets, ("Despacho", {"fields": ["despacho"]})]
