"""T1.2 — Modelos de fincas: Comunidad, Inmueble, Propietario y Titularidad."""

from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.models.deletion import ProtectedError

from fincas.models import Inmueble, Propietario, Titularidad

# --- Comunidad e inmuebles ---------------------------------------------------


@pytest.mark.django_db
def test_r_coef_01_comunidad_cuyos_coeficientes_suman_100(comunidad_a, piso_a, local_a):
    assert comunidad_a.suma_coeficientes() == Decimal("100")
    assert comunidad_a.coeficientes_cuadran()


@pytest.mark.django_db
def test_r_coef_01_comunidad_incompleta_no_cuadra(comunidad_a, piso_a):
    assert comunidad_a.suma_coeficientes() == Decimal("60")
    assert not comunidad_a.coeficientes_cuadran()


@pytest.mark.django_db
def test_r_coef_01_comunidad_sin_inmuebles_no_cuadra(comunidad_a):
    assert comunidad_a.suma_coeficientes() == Decimal("0")
    assert not comunidad_a.coeficientes_cuadran()


@pytest.mark.django_db
@pytest.mark.parametrize("malo", ["0", "-1", "100.0001"])
def test_r_coef_01_coeficiente_fuera_de_rango_no_valida(comunidad_a, malo):
    inmueble = Inmueble(
        comunidad=comunidad_a, tipo=Inmueble.Tipo.PISO, referencia="2B", coeficiente=Decimal(malo)
    )
    with pytest.raises(ValidationError) as error:
        inmueble.full_clean()
    assert "coeficiente" in error.value.message_dict


@pytest.mark.django_db
def test_coeficiente_se_guarda_con_4_decimales(comunidad_a):
    inmueble = Inmueble.objects.create(
        comunidad=comunidad_a, tipo=Inmueble.Tipo.PISO, referencia="2B", coeficiente="12.3456"
    )
    inmueble.refresh_from_db()
    assert inmueble.coeficiente == Decimal("12.3456")


@pytest.mark.django_db
def test_referencia_unica_dentro_de_la_comunidad(comunidad_a, piso_a):
    with pytest.raises(IntegrityError):
        Inmueble.objects.create(
            comunidad=comunidad_a, tipo=Inmueble.Tipo.PISO, referencia="1A", coeficiente=1
        )


@pytest.mark.django_db
def test_misma_referencia_en_otra_comunidad_es_valida(piso_a, piso_b):
    assert piso_a.referencia == piso_b.referencia


@pytest.mark.django_db
def test_no_se_borra_una_comunidad_con_inmuebles(comunidad_a, piso_a):
    with pytest.raises(ProtectedError):
        comunidad_a.delete()


@pytest.mark.django_db
def test_no_se_borra_un_despacho_con_comunidades(despacho_a, comunidad_a):
    with pytest.raises(ProtectedError):
        despacho_a.delete()


# --- Propietarios ------------------------------------------------------------


@pytest.mark.django_db
def test_nif_unico_dentro_del_despacho(despacho_a, propietaria_a):
    with pytest.raises(IntegrityError):
        Propietario.objects.create(despacho=despacho_a, nombre="Otra", nif="00000000T")


@pytest.mark.django_db
def test_mismo_nif_en_otro_despacho_es_valido(despacho_b, propietaria_a):
    # Cada despacho tiene su propia ficha del propietario; no se comparten datos.
    Propietario.objects.create(despacho=despacho_b, nombre="Lucía Ejemplo", nif="00000000T")


@pytest.mark.django_db
def test_varios_propietarios_sin_nif(despacho_a):
    Propietario.objects.create(despacho=despacho_a, nombre="Sin NIF 1")
    Propietario.objects.create(despacho=despacho_a, nombre="Sin NIF 2")


@pytest.mark.django_db
def test_str_del_propietario_no_muestra_el_nif(propietaria_a):
    # Datos personales: que el NIF no acabe en logs o mensajes por la vía de __str__.
    assert "00000000T" not in str(propietaria_a)


# --- Titularidad ---------------------------------------------------------------


@pytest.mark.django_db
def test_titularidad_vigente(titularidad_a, piso_a, propietaria_a):
    assert list(piso_a.propietarios_en(date(2025, 6, 1))) == [propietaria_a]
    assert list(piso_a.propietarios_en(date(2019, 12, 31))) == []


@pytest.mark.django_db
def test_titularidad_terminada_no_esta_vigente(titularidad_a, piso_a, propietaria_a):
    titularidad_a.fecha_fin = date(2024, 12, 31)
    titularidad_a.save()
    assert list(piso_a.propietarios_en(date(2024, 12, 31))) == [propietaria_a]
    assert list(piso_a.propietarios_en(date(2025, 1, 1))) == []


@pytest.mark.django_db
def test_cotitulares(piso_a, propietaria_a, despacho_a):
    # Un inmueble puede tener varios propietarios a la vez (p. ej. un matrimonio).
    otro = Propietario.objects.create(despacho=despacho_a, nombre="Pablo Ejemplo")
    for propietario in (propietaria_a, otro):
        Titularidad.objects.create(
            inmueble=piso_a, propietario=propietario, fecha_inicio=date(2020, 1, 1)
        )
    assert set(piso_a.propietarios_en(date(2025, 1, 1))) == {propietaria_a, otro}


@pytest.mark.django_db
def test_titularidad_con_fin_anterior_al_inicio_no_valida(piso_a, propietaria_a):
    titularidad = Titularidad(
        inmueble=piso_a,
        propietario=propietaria_a,
        fecha_inicio=date(2020, 1, 1),
        fecha_fin=date(2019, 1, 1),
    )
    with pytest.raises(ValidationError) as error:
        titularidad.full_clean()
    assert "fecha_fin" in error.value.message_dict


@pytest.mark.django_db
def test_titularidad_solapada_del_mismo_propietario_no_valida(titularidad_a, piso_a, propietaria_a):
    repetida = Titularidad(
        inmueble=piso_a, propietario=propietaria_a, fecha_inicio=date(2022, 1, 1)
    )
    with pytest.raises(ValidationError, match="solapa"):
        repetida.full_clean()


@pytest.mark.django_db
def test_titularidad_consecutiva_del_mismo_propietario_es_valida(titularidad_a, piso_a):
    titularidad_a.fecha_fin = date(2021, 12, 31)
    titularidad_a.save()
    nueva = Titularidad(
        inmueble=piso_a, propietario=titularidad_a.propietario, fecha_inicio=date(2022, 1, 1)
    )
    nueva.full_clean()


@pytest.mark.django_db
def test_titularidad_no_puede_mezclar_despachos(piso_a, propietario_b):
    # Aislamiento: un propietario del despacho B no puede ser titular en una comunidad de A.
    titularidad = Titularidad(
        inmueble=piso_a, propietario=propietario_b, fecha_inicio=date(2020, 1, 1)
    )
    with pytest.raises(ValidationError, match="despacho"):
        titularidad.full_clean()


@pytest.mark.django_db
def test_no_se_borra_un_inmueble_con_titulares(titularidad_a, piso_a):
    with pytest.raises(ProtectedError):
        piso_a.delete()
