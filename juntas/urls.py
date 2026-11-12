from django.urls import path

from . import views

app_name = "juntas"

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
]
