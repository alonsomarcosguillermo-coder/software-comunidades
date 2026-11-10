from django.urls import path

from . import views

app_name = "fincas"

urlpatterns = [
    path("", views.ListaComunidades.as_view(), name="lista_comunidades"),
]
