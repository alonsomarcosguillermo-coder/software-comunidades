"""Rutas del proyecto. Cada app tiene su propio `urls.py`, que se incluye aquí."""

from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from portal.views import inicio

urlpatterns = [
    # Tras entrar, cada uno a lo suyo: el despacho a sus comunidades, el vecino a su portal.
    path("", inicio, name="inicio"),
    path("entrar/", auth_views.LoginView.as_view(), name="login"),
    path("salir/", auth_views.LogoutView.as_view(), name="logout"),
    # T5.1 — Elegir o recuperar la contraseña con un enlace por email (vistas de Django).
    path(
        "entrar/olvide/",
        auth_views.PasswordResetView.as_view(),
        name="password_reset",
    ),
    path(
        "entrar/olvide/enviado/",
        auth_views.PasswordResetDoneView.as_view(),
        name="password_reset_done",
    ),
    path(
        "entrar/clave/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    path(
        "entrar/clave/hecho/",
        auth_views.PasswordResetCompleteView.as_view(),
        name="password_reset_complete",
    ),
    path("comunidades/", include("fincas.urls")),
    path("comunidades/", include("cobros.urls")),
    path("comunidades/", include("bancos.urls")),
    path("comunidades/", include("juntas.urls")),
    path("", include("portal.urls")),
    path("admin/", admin.site.urls),
]
