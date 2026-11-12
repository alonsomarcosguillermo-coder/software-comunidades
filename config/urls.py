"""Rutas del proyecto. Cada app tiene su propio `urls.py`, que se incluye aquí."""

from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="fincas:lista_comunidades"), name="inicio"),
    path("entrar/", auth_views.LoginView.as_view(), name="login"),
    path("salir/", auth_views.LogoutView.as_view(), name="logout"),
    path("comunidades/", include("fincas.urls")),
    path("comunidades/", include("cobros.urls")),
    path("comunidades/", include("bancos.urls")),
    path("admin/", admin.site.urls),
]
