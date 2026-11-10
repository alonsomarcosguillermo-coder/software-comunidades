"""T1.2 — Admin de fincas. Los coeficientes se editan en bloque desde la comunidad para que
R-COEF-01 (suma exacta de 100) se compruebe sobre el conjunto."""

import pytest
from django.contrib.auth import get_user_model

from fincas.models import Comunidad, Inmueble


@pytest.fixture
def cliente_admin(client):
    jefe = get_user_model().objects.create_superuser(username="jefe", password="clave-123-xyz")
    client.force_login(jefe)
    return client


@pytest.mark.django_db
@pytest.mark.parametrize(
    "url",
    [
        "/admin/fincas/comunidad/",
        "/admin/fincas/comunidad/add/",
        "/admin/fincas/inmueble/",
        "/admin/fincas/propietario/",
        "/admin/fincas/propietario/add/",
    ],
)
def test_paginas_del_admin_cargan(cliente_admin, url, piso_a, titularidad_a):
    assert cliente_admin.get(url).status_code == 200


@pytest.mark.django_db
def test_fichas_cargan(cliente_admin, comunidad_a, piso_a, titularidad_a, propietaria_a):
    for url in (
        f"/admin/fincas/comunidad/{comunidad_a.pk}/change/",
        f"/admin/fincas/inmueble/{piso_a.pk}/change/",
        f"/admin/fincas/propietario/{propietaria_a.pk}/change/",
    ):
        assert cliente_admin.get(url).status_code == 200, url


def _datos_comunidad(despacho, coeficientes, prefijo="inmuebles"):
    datos = {
        "despacho": despacho.pk,
        "nombre": "CP Calle Ficticia 9",
        "nif": "",
        "direccion": "",
        f"{prefijo}-TOTAL_FORMS": str(len(coeficientes)),
        f"{prefijo}-INITIAL_FORMS": "0",
        f"{prefijo}-MIN_NUM_FORMS": "0",
        f"{prefijo}-MAX_NUM_FORMS": "1000",
    }
    for i, coeficiente in enumerate(coeficientes):
        datos |= {
            f"{prefijo}-{i}-tipo": Inmueble.Tipo.PISO,
            f"{prefijo}-{i}-referencia": f"P{i}",
            f"{prefijo}-{i}-coeficiente": coeficiente,
        }
    return datos


@pytest.mark.django_db
def test_r_coef_01_admin_acepta_coeficientes_que_suman_100(cliente_admin, despacho_a):
    datos = _datos_comunidad(despacho_a, ["33.3333", "33.3333", "33.3334"])
    respuesta = cliente_admin.post("/admin/fincas/comunidad/add/", datos)
    assert respuesta.status_code == 302
    assert Comunidad.objects.get().coeficientes_cuadran()


@pytest.mark.django_db
def test_r_coef_01_admin_rechaza_coeficientes_que_no_suman_100(cliente_admin, despacho_a):
    datos = _datos_comunidad(despacho_a, ["33.3333", "33.3333", "33.3333"])
    respuesta = cliente_admin.post("/admin/fincas/comunidad/add/", datos)
    assert respuesta.status_code == 200  # vuelve a mostrar el formulario con el error
    assert "R-COEF-01" in respuesta.content.decode()
    assert not Comunidad.objects.exists()


@pytest.mark.django_db
def test_r_coef_01_admin_cuenta_los_borrados(cliente_admin, comunidad_a, piso_a, local_a):
    # Si se marca un inmueble para borrar, su coeficiente ya no cuenta en la suma.
    prefijo = "inmuebles"
    datos = {
        "despacho": comunidad_a.despacho_id,
        "nombre": comunidad_a.nombre,
        "nif": "",
        "direccion": "",
        f"{prefijo}-TOTAL_FORMS": "2",
        f"{prefijo}-INITIAL_FORMS": "2",
        f"{prefijo}-MIN_NUM_FORMS": "0",
        f"{prefijo}-MAX_NUM_FORMS": "1000",
    }
    for i, inmueble in enumerate((piso_a, local_a)):
        datos |= {
            f"{prefijo}-{i}-id": inmueble.pk,
            f"{prefijo}-{i}-comunidad": comunidad_a.pk,
            f"{prefijo}-{i}-tipo": inmueble.tipo,
            f"{prefijo}-{i}-referencia": inmueble.referencia,
            f"{prefijo}-{i}-coeficiente": str(inmueble.coeficiente),
        }
    datos[f"{prefijo}-1-DELETE"] = "on"
    respuesta = cliente_admin.post(f"/admin/fincas/comunidad/{comunidad_a.pk}/change/", datos)
    assert respuesta.status_code == 200
    assert "R-COEF-01" in respuesta.content.decode()
    assert comunidad_a.inmuebles.count() == 2


@pytest.mark.django_db
def test_admin_permite_crear_comunidad_aun_sin_inmuebles(cliente_admin, despacho_a):
    respuesta = cliente_admin.post("/admin/fincas/comunidad/add/", _datos_comunidad(despacho_a, []))
    assert respuesta.status_code == 302
    assert Comunidad.objects.exists()


@pytest.mark.django_db
def test_admin_no_permite_dar_de_alta_inmuebles_sueltos(cliente_admin):
    # Se dan de alta desde la comunidad, para comprobar la suma de coeficientes en bloque.
    assert cliente_admin.get("/admin/fincas/inmueble/add/").status_code == 403
