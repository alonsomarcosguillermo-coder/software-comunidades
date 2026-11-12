from django.urls import path

from . import views

app_name = "bancos"

urlpatterns = [
    path("<int:pk>/extractos/", views.ExtractosComunidad.as_view(), name="extractos_comunidad"),
    path(
        "<int:pk>/extractos/importar/",
        views.ImportarExtracto.as_view(),
        name="importar_extracto",
    ),
    path(
        "<int:pk>/extractos/<int:extracto_pk>/",
        views.DetalleExtracto.as_view(),
        name="detalle_extracto",
    ),
    # T3.2 — Conciliación
    path(
        "<int:pk>/extractos/conciliar/",
        views.ConciliarAutomaticamente.as_view(),
        name="conciliar_automaticamente",
    ),
    path(
        "<int:pk>/movimientos/<int:movimiento_pk>/conciliar/",
        views.ConciliarMovimiento.as_view(),
        name="conciliar_movimiento",
    ),
    path(
        "<int:pk>/movimientos/<int:movimiento_pk>/deshacer/",
        views.DeshacerConciliacion.as_view(),
        name="deshacer_conciliacion",
    ),
]
