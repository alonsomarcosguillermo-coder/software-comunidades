"""T3.1 — Importar un fichero Norma 43 en una comunidad (`bancos.importacion`)."""

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from bancos.importacion import ImportacionInvalida, importar_norma43
from bancos.models import Extracto, Movimiento
from contabilidad.models import ContabilidadInmutable

from .conftest import CUENTA, extracto, fichero

pytestmark = pytest.mark.django_db


def _importar(comunidad, contenido=None, **kwargs):
    return importar_norma43(comunidad, contenido or fichero(), nombre_fichero="abril.n43", **kwargs)


def test_guarda_el_extracto_y_sus_movimientos(comunidad):
    usuario = get_user_model().objects.create_user(username="ana")
    [guardado] = _importar(comunidad, usuario=usuario)
    assert guardado.comunidad == comunidad
    assert (guardado.entidad, guardado.oficina, guardado.cuenta) == ("9999", "0000", CUENTA)
    assert (guardado.fecha_inicial, guardado.fecha_final) == (date(2026, 4, 1), date(2026, 4, 30))
    assert guardado.saldo_inicial == Decimal("1500.00")
    assert guardado.saldo_final == Decimal("1525.50")
    assert guardado.nombre_fichero == "abril.n43"
    assert guardado.importado_por == usuario

    abono, cargo = guardado.movimientos.order_by("orden")
    assert (abono.orden, abono.importe, abono.referencia_1) == (1, Decimal("45.50"), "REC-1-7")
    assert abono.conceptos == "TRANSFERENCIA DE MARTA INVENTADA\nCUOTA ABRIL"
    assert abono.concepto_comun == "04"
    assert (cargo.orden, cargo.importe, cargo.concepto_comun) == (2, Decimal("-20.00"), "17")


def test_guarda_los_registros_originales_de_la_cuenta(comunidad):
    # Como la remesa con su XML: queda constancia exacta de lo que dio el banco.
    [guardado] = _importar(comunidad)
    lineas = guardado.registros.splitlines()
    assert lineas[0].startswith("11") and lineas[-1].startswith("33")
    assert len(lineas) == 5  # 11, 22, 23, 22, 33 (sin el 88, que es del fichero)


def test_varias_cuentas_del_mismo_fichero(comunidad):
    mayo = extracto(desde=date(2026, 5, 1), hasta=date(2026, 5, 31), saldo="1525.50")
    guardados = _importar(comunidad, fichero(extracto(), mayo))
    assert [e.fecha_inicial.month for e in guardados] == [4, 5]
    assert Movimiento.objects.count() == 4


def test_fichero_invalido_no_guarda_nada(comunidad):
    with pytest.raises(ImportacionInvalida, match="fin de fichero"):
        _importar(comunidad, fichero()[: -(80 + 2)])  # sin el registro 88
    assert not Extracto.objects.exists()


def test_rechaza_una_cuenta_que_no_es_la_de_la_comunidad(comunidad):
    with pytest.raises(ImportacionInvalida, match="no es la de la comunidad"):
        _importar(comunidad, fichero(extracto(cuenta="0100000002")))
    assert not Extracto.objects.exists()


def test_si_una_cuenta_falla_no_se_guarda_ninguna(comunidad):
    mayo = extracto(desde=date(2026, 5, 1), hasta=date(2026, 5, 31), cuenta="0100000002")
    with pytest.raises(ImportacionInvalida):
        _importar(comunidad, fichero(extracto(), mayo))
    assert not Extracto.objects.exists()


def test_rechaza_si_la_comunidad_no_tiene_iban(comunidad):
    comunidad.iban_cobros = ""
    comunidad.save()
    with pytest.raises(ImportacionInvalida, match="IBAN"):
        _importar(comunidad)


def test_rechaza_otra_divisa(comunidad):
    with pytest.raises(ImportacionInvalida, match="euros"):
        _importar(comunidad, fichero(extracto(divisa="840")))


@pytest.mark.parametrize(
    ("desde", "hasta"),
    [
        (date(2026, 4, 1), date(2026, 4, 30)),  # el mismo
        (date(2026, 4, 30), date(2026, 5, 31)),  # comparte un día
        (date(2026, 3, 1), date(2026, 4, 1)),  # comparte el primer día
        (date(2026, 4, 10), date(2026, 4, 12)),  # dentro
        (date(2026, 3, 1), date(2026, 6, 30)),  # lo contiene
    ],
)
def test_rechaza_periodos_que_se_solapan(comunidad, desde, hasta):
    # Si se aceptaran, los movimientos de los días comunes estarían dos veces.
    _importar(comunidad)
    with pytest.raises(ImportacionInvalida, match="Ya hay un extracto"):
        _importar(comunidad, fichero(extracto(desde=desde, hasta=hasta, movimientos=())))
    assert Extracto.objects.count() == 1


def test_rechaza_solapes_dentro_del_mismo_fichero(comunidad):
    with pytest.raises(ImportacionInvalida, match="se solapan"):
        _importar(comunidad, fichero(extracto(), extracto(saldo="1525.50")))
    assert not Extracto.objects.exists()


def test_acepta_periodos_consecutivos(comunidad):
    _importar(comunidad)
    _importar(comunidad, fichero(extracto(date(2026, 5, 1), date(2026, 5, 31), "1525.50")))
    assert Extracto.objects.count() == 2


def test_el_mismo_periodo_en_otra_comunidad_no_cuenta_como_solape(comunidad, despacho_b):
    from fincas.models import Comunidad

    otra = Comunidad.objects.create(
        despacho=despacho_b, nombre="CP Avenida Inventada 2", iban_cobros=comunidad.iban_cobros
    )
    _importar(comunidad)
    _importar(otra)
    assert Extracto.objects.count() == 2


def test_importe_demasiado_grande_para_la_base_de_datos(comunidad):
    enorme = extracto(saldo="99999999999.00", movimientos=())
    with pytest.raises(ImportacionInvalida, match="demasiado grande"):
        _importar(comunidad, fichero(enorme))


def test_extracto_y_movimientos_son_inmutables(comunidad):
    [guardado] = _importar(comunidad)
    movimiento = guardado.movimientos.first()
    guardado.nombre_fichero = "otro.n43"
    with pytest.raises(ContabilidadInmutable):
        guardado.save()
    with pytest.raises(ContabilidadInmutable):
        guardado.delete()
    with pytest.raises(ContabilidadInmutable):
        Movimiento.objects.filter(pk=movimiento.pk).update(importe=Decimal("1.00"))
    with pytest.raises(ContabilidadInmutable):
        Extracto.objects.all().delete()


def test_numero_de_cuenta_oculto(comunidad):
    [guardado] = _importar(comunidad)
    assert guardado.cuenta_oculta == "9999 0000 ****0001"
