from django.urls import path

from . import views

app_name = "cobros"

urlpatterns = [
    path(
        "<int:pk>/presupuestos/",
        views.PresupuestosComunidad.as_view(),
        name="presupuestos_comunidad",
    ),
]
