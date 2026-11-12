from django.urls import path

from . import views
from . import views_celebracion as celebracion

app_name = "juntas"

# T4.3 — Celebración: /comunidades/<pk>/juntas/<junta_pk>/celebracion/...
_C = "<int:pk>/juntas/<int:junta_pk>/celebracion/"

urlpatterns = [
    path("<int:pk>/juntas/", views.JuntasComunidad.as_view(), name="juntas_comunidad"),
    path("<int:pk>/juntas/nueva/", views.EditarJunta.as_view(), name="nueva_junta"),
    path("<int:pk>/juntas/<int:junta_pk>/", views.DetalleJunta.as_view(), name="detalle_junta"),
    path(
        "<int:pk>/juntas/<int:junta_pk>/editar/",
        views.EditarJunta.as_view(),
        name="editar_junta",
    ),
    path(
        "<int:pk>/juntas/<int:junta_pk>/convocar/",
        views.ConvocarJunta.as_view(),
        name="convocar_junta",
    ),
    path(_C, celebracion.CelebracionJunta.as_view(), name="celebracion"),
    path(_C + "iniciar/", celebracion.IniciarJunta.as_view(), name="iniciar_junta"),
    path(_C + "puntos/<int:punto_pk>/votar/", celebracion.VotarPunto.as_view(), name="votar_punto"),
    path(
        _C + "asistentes/<int:asistente_pk>/impugnacion/",
        celebracion.CambiarImpugnacion.as_view(),
        name="cambiar_impugnacion",
    ),
    path(_C + "cerrar/", celebracion.CerrarActa.as_view(), name="cerrar_acta"),
    path(_C + "notificar/", celebracion.NotificarAusentes.as_view(), name="notificar_ausentes"),
    path(
        _C + "puntos/<int:punto_pk>/discrepancia/",
        celebracion.RegistrarDiscrepancia.as_view(),
        name="registrar_discrepancia",
    ),
    path(
        "<int:pk>/juntas/<int:junta_pk>/acta/", celebracion.ActaJunta.as_view(), name="acta_junta"
    ),
]
