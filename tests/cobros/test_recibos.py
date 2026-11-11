"""T2.4 — Mandatos SEPA (R-SEPA-01) y recibos."""

from datetime import date

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from cobros.derramas import emitir_derrama
from cobros.emision import emitir_cuotas
from cobros.models import DatosInmutables, Mandato, Recibo
from cobros.recibos import elegir_pagador, generar_recibos
from fincas.models import Propietario, Titularidad

from .conftest import D
from .test_sepa_identificadores import iban_ficticio

pytestmark = pytest.mark.django_db


# --- Datos ------------------------------------------------------------------------------


@pytest.fixture
def vecinos_a(despacho_a, inmuebles_a):
    """Un titular por inmueble desde 2020 (nombres y NIF ficticios)."""
    vecinos = {}
    for referencia in ["1A", "1B", "L1"]:
        vecino = Propietario.objects.create(despacho=despacho_a, nombre=f"Vecino {referencia}")
        Titularidad.objects.create(
            inmueble=inmuebles_a[referencia], propietario=vecino, fecha_inicio=date(2020, 1, 1)
        )
        vecinos[referencia] = vecino
    return vecinos


def _mandato(comunidad, propietario, n=1, **campos):
    datos = {
        "referencia": f"MANDATO-{n}",
        "titular_cuenta": propietario.nombre,
        "iban": iban_ficticio(n),
        "fecha_firma": date(2025, 6, 1),
    } | campos
    return Mandato.objects.create(comunidad=comunidad, propietario=propietario, **datos)


@pytest.fixture
def con_cuotas(aprobado_a, fondo_a, vecinos_a):
    """Primer trimestre de 2026 emitido el 5/1/2026: una cuota por inmueble."""
    emitir_cuotas(aprobado_a, 1, date(2026, 1, 5))
    return aprobado_a.comunidad


# --- Elegir pagador (puro) -------------------------------------------------------------


def test_elegir_pagador_un_solo_titular():
    assert elegir_pagador([(7, False)]) == 7


def test_elegir_pagador_sin_titulares():
    assert elegir_pagador([]) is None


def test_elegir_pagador_cotitulares_gana_el_que_tiene_mandato():
    assert elegir_pagador([(3, False), (9, True), (12, True)]) == 9


def test_elegir_pagador_cotitulares_sin_mandato_el_primero():
    assert elegir_pagador([(12, False), (3, False)]) == 3


# --- Mandatos (R-SEPA-01) -------------------------------------------------------------


def test_r_sepa_01_mandato_vigente_desde_la_firma_hasta_la_baja(comunidad_a, vecinos_a):
    mandato = _mandato(comunidad_a, vecinos_a["1A"], fecha_baja=date(2026, 3, 1))
    assert not mandato.vigente_en(date(2025, 5, 31))
    assert mandato.vigente_en(date(2025, 6, 1))
    assert mandato.vigente_en(date(2026, 2, 28))
    assert not mandato.vigente_en(date(2026, 3, 1))
    assert list(Mandato.objects.vigentes(date(2026, 1, 1))) == [mandato]
    assert not Mandato.objects.vigentes(date(2026, 3, 1)).exists()


def test_r_sepa_01_un_solo_mandato_activo_por_propietario(comunidad_a, vecinos_a):
    _mandato(comunidad_a, vecinos_a["1A"], 1)
    with pytest.raises(IntegrityError), transaction.atomic():
        _mandato(comunidad_a, vecinos_a["1A"], 2)


def test_r_sepa_01_tras_la_baja_se_puede_firmar_otro(comunidad_a, vecinos_a):
    viejo = _mandato(comunidad_a, vecinos_a["1A"], 1)
    viejo.fecha_baja = date(2026, 1, 1)
    viejo.save()
    _mandato(comunidad_a, vecinos_a["1A"], 2, fecha_firma=date(2026, 1, 1))
    assert Mandato.objects.filter(propietario=vecinos_a["1A"]).count() == 2


def test_r_sepa_01_referencia_unica_en_la_comunidad(comunidad_a, vecinos_a):
    _mandato(comunidad_a, vecinos_a["1A"], 1)
    with pytest.raises(IntegrityError), transaction.atomic():
        _mandato(comunidad_a, vecinos_a["1B"], 2, referencia="MANDATO-1")


def test_r_sepa_01_mandato_firmado_no_se_modifica(comunidad_a, vecinos_a):
    mandato = _mandato(comunidad_a, vecinos_a["1A"])
    mandato.iban = iban_ficticio(99)
    with pytest.raises(DatosInmutables):
        mandato.save()


def test_r_sepa_01_iban_invalido_no_pasa_la_validacion(comunidad_a, vecinos_a):
    iban = iban_ficticio(1)
    mandato = Mandato(
        comunidad=comunidad_a,
        propietario=vecinos_a["1A"],
        referencia="M-1",
        titular_cuenta="Vecino 1A",
        iban=iban[:-1] + ("0" if iban[-1] != "0" else "1"),
        fecha_firma=date(2025, 6, 1),
    )
    with pytest.raises(ValidationError) as error:
        mandato.full_clean()
    assert "iban" in error.value.message_dict
    assert iban[4:] not in str(error.value)  # el mensaje no repite el IBAN


def test_r_sepa_01_propietario_de_otro_despacho(comunidad_a, despacho_b):
    ajeno = Propietario.objects.create(despacho=despacho_b, nombre="Ajeno")
    mandato = Mandato(
        comunidad=comunidad_a,
        propietario=ajeno,
        referencia="M-1",
        titular_cuenta="Ajeno",
        iban=iban_ficticio(1),
        fecha_firma=date(2025, 6, 1),
    )
    with pytest.raises(ValidationError, match="despachos distintos"):
        mandato.full_clean()


def test_el_iban_no_aparece_en_str_y_se_muestra_oculto(comunidad_a, vecinos_a):
    mandato = _mandato(comunidad_a, vecinos_a["1A"], 4321)
    assert mandato.iban[4:] not in str(mandato)
    assert mandato.iban_oculto.endswith("4321") and "•" in mandato.iban_oculto


def test_el_iban_se_guarda_normalizado(comunidad_a, vecinos_a):
    iban = iban_ficticio(5)
    mandato = _mandato(comunidad_a, vecinos_a["1A"], iban=" ".join([iban[:4], iban[4:]]).lower())
    assert mandato.iban == iban


def test_identificador_de_acreedor_de_la_comunidad(comunidad_a):
    assert comunidad_a.identificador_acreedor() == ""  # sin NIF
    comunidad_a.nif = "H00000000"
    assert comunidad_a.identificador_acreedor().endswith("000H00000000")


# --- Generar recibos --------------------------------------------------------------------


def test_un_recibo_por_cuota_con_su_pagador(con_cuotas, vecinos_a):
    resultado = generar_recibos(con_cuotas)
    assert resultado.sin_titular == []
    recibos = {r.inmueble.referencia: r for r in resultado.creados}
    assert set(recibos) == {"1A", "1B", "L1"}
    assert recibos["1A"].propietario == vecinos_a["1A"]
    assert recibos["1A"].importe == recibos["1A"].cuota.importe
    assert recibos["1A"].vencimiento == date(2026, 1, 5)
    assert recibos["1A"].concepto == "Cuota ordinaria 2026, periodo 1/4 · 1A"
    assert sum(r.importe for r in recibos.values()) == D("1125.00")


def test_recibos_de_derrama_uno_por_plazo(derrama_a, vecinos_a):
    emitir_derrama(derrama_a, date(2026, 2, 1))
    recibos = generar_recibos(derrama_a.comunidad).creados
    assert len(recibos) == 9  # 3 inmuebles × 3 plazos
    assert sum(r.importe for r in recibos) == D("3000.00")
    assert {r.vencimiento for r in recibos} == {
        date(2026, 3, 1),
        date(2026, 4, 1),
        date(2026, 5, 1),
    }
    assert all(r.cuota_derrama is not None and r.cuota is None for r in recibos)
    assert "Derrama Fachada, plazo 1/3 · 1A" in {r.concepto for r in recibos}


def test_numeracion_correlativa_por_vencimiento(con_cuotas, derrama_a):
    emitir_derrama(derrama_a, date(2026, 2, 1))
    recibos = generar_recibos(con_cuotas).creados
    assert [r.numero for r in recibos] == list(range(1, 13))
    vencimientos = [r.vencimiento for r in recibos]
    assert vencimientos == sorted(vencimientos)
    assert recibos[0].referencia == f"REC-{con_cuotas.pk}-1"


def test_generar_otra_vez_no_duplica_y_sigue_la_numeracion(con_cuotas, aprobado_a):
    generar_recibos(con_cuotas)
    assert generar_recibos(con_cuotas).creados == []
    emitir_cuotas(aprobado_a, 2, date(2026, 4, 5))
    nuevos = generar_recibos(con_cuotas).creados
    assert [r.numero for r in nuevos] == [4, 5, 6]
    assert Recibo.objects.count() == 6


def test_paga_el_titular_en_la_fecha_de_vencimiento(con_cuotas, vecinos_a, inmuebles_a):
    # 1A se vendió el 1/1/2026, antes del vencimiento (5/1/2026).
    Titularidad.objects.filter(propietario=vecinos_a["1A"]).update(fecha_fin=date(2025, 12, 31))
    comprador = Propietario.objects.create(despacho=vecinos_a["1A"].despacho, nombre="Comprador")
    Titularidad.objects.create(
        inmueble=inmuebles_a["1A"], propietario=comprador, fecha_inicio=date(2026, 1, 1)
    )
    recibo = Recibo.objects.get(
        pk__in=[r.pk for r in generar_recibos(con_cuotas).creados], inmueble=inmuebles_a["1A"]
    )
    assert recibo.propietario == comprador


def test_cotitulares_paga_el_que_tiene_mandato(con_cuotas, vecinos_a, inmuebles_a):
    pareja = Propietario.objects.create(despacho=vecinos_a["1A"].despacho, nombre="Pareja 1A")
    Titularidad.objects.create(
        inmueble=inmuebles_a["1A"], propietario=pareja, fecha_inicio=date(2020, 1, 1)
    )
    _mandato(con_cuotas, pareja)
    recibo = next(r for r in generar_recibos(con_cuotas).creados if r.inmueble == inmuebles_a["1A"])
    assert recibo.propietario == pareja


def test_inmueble_sin_titular_no_genera_recibo_y_se_avisa(con_cuotas, inmuebles_a):
    Titularidad.objects.filter(inmueble=inmuebles_a["L1"]).delete()
    resultado = generar_recibos(con_cuotas)
    assert {r.inmueble.referencia for r in resultado.creados} == {"1A", "1B"}
    assert resultado.sin_titular == [(inmuebles_a["L1"], date(2026, 1, 5))]
    # Cuando se corrige, la siguiente generación lo recoge.
    Titularidad.objects.create(
        inmueble=inmuebles_a["L1"],
        propietario=Propietario.objects.get(nombre="Vecino L1"),
        fecha_inicio=date(2020, 1, 1),
    )
    assert [r.inmueble for r in generar_recibos(con_cuotas).creados] == [inmuebles_a["L1"]]


def test_no_mezcla_comunidades(con_cuotas, derrama_b):
    emitir_derrama(derrama_b, date(2026, 2, 1))
    assert {r.comunidad for r in generar_recibos(con_cuotas).creados} == {con_cuotas}


# --- Restricciones --------------------------------------------------------------------


def test_un_recibo_no_se_modifica(con_cuotas):
    recibo = generar_recibos(con_cuotas).creados[0]
    recibo.importe = D("1.00")
    with pytest.raises(DatosInmutables):
        recibo.save()


def test_una_cuota_no_puede_tener_dos_recibos(con_cuotas):
    recibo = generar_recibos(con_cuotas).creados[0]
    with pytest.raises(IntegrityError), transaction.atomic():
        Recibo.objects.create(
            comunidad=con_cuotas,
            numero=99,
            inmueble=recibo.inmueble,
            propietario=recibo.propietario,
            cuota=recibo.cuota,
            concepto="Duplicado",
            importe=recibo.importe,
            vencimiento=recibo.vencimiento,
        )


def test_un_recibo_sale_de_una_sola_cuota(con_cuotas):
    recibo = generar_recibos(con_cuotas).creados[0]
    with pytest.raises(IntegrityError), transaction.atomic():
        Recibo.objects.create(
            comunidad=con_cuotas,
            numero=99,
            inmueble=recibo.inmueble,
            propietario=recibo.propietario,
            concepto="Sin origen",
            importe=recibo.importe,
            vencimiento=recibo.vencimiento,
        )
