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
]
