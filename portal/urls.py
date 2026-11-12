from django.urls import path

from . import views

app_name = "portal"

urlpatterns = [
    path("portal/", views.InicioPortal.as_view(), name="inicio"),
    path("portal/recibos/", views.RecibosPortal.as_view(), name="recibos"),
    path("portal/juntas/", views.JuntasPortal.as_view(), name="juntas"),
    path("portal/juntas/<int:pk>/", views.JuntaPortal.as_view(), name="junta"),
    # T5.2 — Discrepancia online del ausente (R-MAY-05)
    path(
        "portal/juntas/<int:pk>/puntos/<int:punto_pk>/discrepar/",
        views.DiscreparPortal.as_view(),
        name="discrepar",
    ),
    # Para el despacho
    path(
        "comunidades/<int:pk>/vecinos/",
        views.VecinosComunidad.as_view(),
        name="vecinos_comunidad",
    ),
    path(
        "comunidades/<int:pk>/vecinos/<int:propietario_pk>/invitar/",
        views.InvitarVecino.as_view(),
        name="invitar_vecino",
    ),
]
