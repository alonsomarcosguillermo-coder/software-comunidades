from django.urls import path

from . import views

app_name = "cobros"

urlpatterns = [
    path(
        "<int:pk>/presupuestos/",
        views.PresupuestosComunidad.as_view(),
        name="presupuestos_comunidad",
    ),
    path(
        "<int:pk>/presupuestos/<int:presupuesto_pk>/emitir/",
        views.EmitirCuotas.as_view(),
        name="emitir_cuotas",
    ),
    path("<int:pk>/derramas/", views.DerramasComunidad.as_view(), name="derramas_comunidad"),
    path("<int:pk>/recibos/", views.RecibosComunidad.as_view(), name="recibos_comunidad"),
    path(
        "<int:pk>/recibos/generar/",
        views.GenerarRecibos.as_view(),
        name="generar_recibos",
    ),
    path("<int:pk>/remesas/crear/", views.CrearRemesa.as_view(), name="crear_remesa"),
    path(
        "<int:pk>/remesas/<int:remesa_pk>/fichero/",
        views.DescargarRemesa.as_view(),
        name="descargar_remesa",
    ),
]
