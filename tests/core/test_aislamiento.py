"""T1.1 — Aislamiento entre despachos.

Un usuario del despacho A nunca debe ver ni modificar datos del despacho B.
Usamos el propio `Usuario` (que tiene `despacho`) como modelo de prueba: es el único
modelo con despacho que existe todavía. Cuando lleguen `Comunidad` y compañía (T1.2),
sus vistas tendrán su propio test de aislamiento usando el mismo mixin.
"""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.db.models.deletion import ProtectedError
from django.http import Http404
from django.test import RequestFactory
from django.views.generic import DetailView, ListView

from core.aislamiento import FiltradoPorDespachoMixin, filtrar_por_despacho
from core.models import Despacho

Usuario = get_user_model()


@pytest.fixture
def despacho_a():
    return Despacho.objects.create(nombre="Fincas Alfa")


@pytest.fixture
def despacho_b():
    return Despacho.objects.create(nombre="Fincas Beta")


@pytest.fixture
def ana(despacho_a):
    return Usuario.objects.create_user(username="ana", despacho=despacho_a)


@pytest.fixture
def alberto(despacho_a):
    return Usuario.objects.create_user(username="alberto", despacho=despacho_a)


@pytest.fixture
def berta(despacho_b):
    return Usuario.objects.create_user(username="berta", despacho=despacho_b)


@pytest.fixture
def sin_despacho():
    return Usuario.objects.create_user(username="suelto")


# --- Modelo ------------------------------------------------------------------


@pytest.mark.django_db
def test_usuario_pertenece_a_un_despacho(ana, despacho_a):
    assert ana.despacho == despacho_a
    assert list(despacho_a.usuarios.all()) == [ana]


@pytest.mark.django_db
def test_no_se_puede_borrar_un_despacho_con_usuarios(ana, despacho_a):
    # PROTECT: borrar un despacho no debe arrastrar en cascada a sus usuarios (ni,
    # más adelante, a sus comunidades y su contabilidad).
    with pytest.raises(ProtectedError):
        despacho_a.delete()


# --- Helper filtrar_por_despacho ---------------------------------------------


@pytest.mark.django_db
def test_usuario_de_a_solo_ve_datos_de_a(ana, alberto, berta):
    visibles = filtrar_por_despacho(Usuario.objects.all(), ana)
    assert set(visibles) == {ana, alberto}
    assert berta not in visibles


@pytest.mark.django_db
def test_usuario_de_b_no_ve_datos_de_a(ana, alberto, berta):
    assert list(filtrar_por_despacho(Usuario.objects.all(), berta)) == [berta]


@pytest.mark.django_db
def test_usuario_sin_despacho_no_ve_nada(ana, berta, sin_despacho):
    # Falla "cerrado": si falta el despacho, no se muestra nada (en vez de todo).
    assert not filtrar_por_despacho(Usuario.objects.all(), sin_despacho).exists()


@pytest.mark.django_db
def test_anonimo_no_ve_nada(ana):
    assert not filtrar_por_despacho(Usuario.objects.all(), AnonymousUser()).exists()


@pytest.mark.django_db
def test_superusuario_sin_despacho_tampoco_ve_nada_en_la_aplicacion(ana):
    # El superusuario trabaja desde /admin; en las vistas de la aplicación no es excepción.
    jefe = Usuario.objects.create_superuser(username="jefe", password="clave-de-prueba-123")
    assert not filtrar_por_despacho(Usuario.objects.all(), jefe).exists()


@pytest.mark.django_db
def test_filtro_por_campo_relacionado(ana, alberto, berta, despacho_a):
    # Modelos que llegan al despacho a través de otra relación (p. ej. un Inmueble
    # vía `comunidad__despacho`) indican el camino con `campo`. Aquí lo simulamos
    # filtrando despachos por su clave primaria.
    visibles = filtrar_por_despacho(Despacho.objects.all(), ana, campo="pk")
    assert list(visibles) == [despacho_a]


# --- Mixin para vistas ---------------------------------------------------------


class ListaUsuarios(FiltradoPorDespachoMixin, ListView):
    model = Usuario


class DetalleUsuario(FiltradoPorDespachoMixin, DetailView):
    model = Usuario


def _peticion(usuario):
    peticion = RequestFactory().get("/")
    peticion.user = usuario
    return peticion


@pytest.mark.django_db
def test_mixin_lista_solo_datos_del_despacho(ana, alberto, berta):
    respuesta = ListaUsuarios.as_view()(_peticion(ana))
    assert set(respuesta.context_data["object_list"]) == {ana, alberto}


@pytest.mark.django_db
def test_mixin_detalle_de_otro_despacho_da_404(ana, berta):
    # Un 404 (y no un 403) para no revelar siquiera que el objeto existe. Como
    # UpdateView y DeleteView también usan get_object(), esto impide modificarlo.
    with pytest.raises(Http404):
        DetalleUsuario.as_view()(_peticion(ana), pk=berta.pk)


@pytest.mark.django_db
def test_mixin_detalle_del_propio_despacho_funciona(ana, alberto):
    respuesta = DetalleUsuario.as_view()(_peticion(ana), pk=alberto.pk)
    assert respuesta.context_data["object"] == alberto


@pytest.mark.django_db
def test_mixin_exige_iniciar_sesion(ana):
    respuesta = ListaUsuarios.as_view()(_peticion(AnonymousUser()))
    assert respuesta.status_code == 302
    assert "login" in respuesta.url
