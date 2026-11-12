"""T1.5 — Login y lista de comunidades del despacho (con búsqueda por HTMX).

Regla de CLAUDE.md: cada vista lleva un test que comprueba que un usuario de otro despacho
NO puede ver los datos.
"""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from fincas.models import Comunidad

CLAVE = "clave-de-prueba-123"
URL_LISTA = reverse("fincas:lista_comunidades")


@pytest.fixture
def ana(despacho_a):
    return get_user_model().objects.create_user(username="ana", password=CLAVE, despacho=despacho_a)


@pytest.fixture
def berta(despacho_b):
    return get_user_model().objects.create_user(
        username="berta", password=CLAVE, despacho=despacho_b
    )


@pytest.fixture
def segunda_comunidad_a(despacho_a):
    return Comunidad.objects.create(despacho=despacho_a, nombre="CP Plaza Imaginaria 7")


# --- Login / logout ------------------------------------------------------------------


@pytest.mark.django_db
def test_la_pagina_de_login_carga(client):
    respuesta = client.get(reverse("login"))
    assert respuesta.status_code == 200
    assert 'name="username"' in respuesta.content.decode()


@pytest.mark.django_db
def test_login_correcto_lleva_a_la_lista_de_comunidades(client, ana):
    # T5.1: el login lleva a "/" (inicio), que manda al despacho a sus comunidades.
    respuesta = client.post(reverse("login"), {"username": "ana", "password": CLAVE}, follow=True)
    assert respuesta.redirect_chain[-1] == (URL_LISTA, 302)


@pytest.mark.django_db
def test_login_incorrecto_muestra_error(client, ana):
    respuesta = client.post(reverse("login"), {"username": "ana", "password": "mala"})
    assert respuesta.status_code == 200
    assert "no son correctos" in respuesta.content.decode()


@pytest.mark.django_db
def test_logout_por_post_cierra_la_sesion(client, ana):
    client.force_login(ana)
    respuesta = client.post(reverse("logout"))
    assert respuesta.status_code == 302
    assert client.get(URL_LISTA).status_code == 302  # ya no hay sesión


@pytest.mark.django_db
def test_la_portada_redirige_a_las_comunidades(client, ana):
    client.force_login(ana)
    respuesta = client.get("/")
    assert respuesta.status_code == 302
    assert respuesta.url == URL_LISTA


# --- Lista de comunidades ----------------------------------------------------------------


@pytest.mark.django_db
def test_sin_sesion_redirige_al_login(client, comunidad_a):
    respuesta = client.get(URL_LISTA)
    assert respuesta.status_code == 302
    assert respuesta.url.startswith(reverse("login"))


@pytest.mark.django_db
def test_lista_muestra_las_comunidades_del_despacho(
    client, ana, comunidad_a, segunda_comunidad_a, piso_a, local_a
):
    client.force_login(ana)
    respuesta = client.get(URL_LISTA)
    html = respuesta.content.decode()
    assert respuesta.status_code == 200
    assert "CP Calle Ficticia 1" in html
    assert "CP Plaza Imaginaria 7" in html
    assert "Fincas Alfa" in html  # el despacho del usuario, en la cabecera


@pytest.mark.django_db
def test_aislamiento_usuario_de_a_no_ve_comunidades_de_b(client, ana, comunidad_a, comunidad_b):
    client.force_login(ana)
    html = client.get(URL_LISTA).content.decode()
    assert "CP Avenida Inventada 2" not in html
    assert list(client.get(URL_LISTA).context["comunidades"]) == [comunidad_a]


@pytest.mark.django_db
def test_aislamiento_usuario_de_b_no_ve_comunidades_de_a(client, berta, comunidad_a, comunidad_b):
    client.force_login(berta)
    html = client.get(URL_LISTA).content.decode()
    assert "CP Calle Ficticia 1" not in html
    assert "CP Avenida Inventada 2" in html


@pytest.mark.django_db
def test_aislamiento_la_busqueda_no_encuentra_comunidades_de_otro_despacho(
    client, ana, comunidad_a, comunidad_b
):
    client.force_login(ana)
    respuesta = client.get(URL_LISTA, {"q": "Avenida"})
    assert list(respuesta.context["comunidades"]) == []


@pytest.mark.django_db
def test_usuario_sin_despacho_no_ve_nada_y_recibe_un_aviso(client, comunidad_a):
    get_user_model().objects.create_user(username="suelto", password=CLAVE)
    client.login(username="suelto", password=CLAVE)
    respuesta = client.get(URL_LISTA)
    assert list(respuesta.context["comunidades"]) == []
    assert "no está asignado a ningún despacho" in respuesta.content.decode()


@pytest.mark.django_db
def test_r_coef_01_la_lista_marca_si_los_coeficientes_cuadran(
    client, ana, comunidad_a, segunda_comunidad_a, piso_a, local_a
):
    client.force_login(ana)
    comunidades = {c.nombre: c for c in client.get(URL_LISTA).context["comunidades"]}
    assert comunidades["CP Calle Ficticia 1"].cuadran
    assert comunidades["CP Calle Ficticia 1"].num_inmuebles == 2
    assert not comunidades["CP Plaza Imaginaria 7"].cuadran  # sin inmuebles


# --- Búsqueda con HTMX ---------------------------------------------------------------------


@pytest.mark.django_db
def test_buscar_filtra_por_nombre(client, ana, comunidad_a, segunda_comunidad_a):
    client.force_login(ana)
    respuesta = client.get(URL_LISTA, {"q": "plaza"})
    assert list(respuesta.context["comunidades"]) == [segunda_comunidad_a]


@pytest.mark.django_db
def test_peticion_htmx_devuelve_solo_la_tabla(client, ana, comunidad_a):
    # HTMX manda la cabecera HX-Request; respondemos solo el trozo de HTML que cambia.
    client.force_login(ana)
    respuesta = client.get(URL_LISTA, {"q": "Ficticia"}, headers={"HX-Request": "true"})
    html = respuesta.content.decode()
    assert "CP Calle Ficticia 1" in html
    assert "<html" not in html
    assert 'id="tabla-comunidades"' in html


@pytest.mark.django_db
def test_peticion_normal_devuelve_la_pagina_completa_con_htmx(client, ana, comunidad_a):
    client.force_login(ana)
    html = client.get(URL_LISTA).content.decode()
    assert "<html" in html
    assert "htmx.min.js" in html
    assert 'hx-get="' in html
