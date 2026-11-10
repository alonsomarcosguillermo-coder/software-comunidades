"""T1.4 — Asientos y apuntes en la base de datos.

Reglas de CLAUDE.md (contabilidad de partida doble):
- Debe = Haber en cada asiento.
- Los asientos son inmutables; un error se corrige con un contra-asiento.
- No hay campo "saldo": se calcula a partir de los apuntes.

Cada regla se comprueba en dos niveles: el código Python (errores claros) y los triggers
de PostgreSQL (segunda barrera, por si alguien se salta el código). Ver ADR 003.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.db import DatabaseError, connection, transaction

from contabilidad.models import Apunte, Asiento, ContabilidadInmutable, Cuenta
from contabilidad.registro import anular_asiento, registrar_asiento
from contabilidad.servicios import AsientoInvalido, Linea


def D(valor: str) -> Decimal:
    return Decimal(valor)


@pytest.fixture
def cobro(comunidad, banco, propietarios):
    """Un vecino paga 100 € de cuota: entra en el banco y baja lo que deben los propietarios."""
    return registrar_asiento(
        comunidad,
        date(2026, 1, 10),
        "Cobro cuota enero 1A",
        [Linea(banco, debe=D("100.00")), Linea(propietarios, haber=D("100.00"))],
    )


# --- Registrar ---------------------------------------------------------------------


@pytest.mark.django_db
def test_registrar_asiento_crea_sus_apuntes(cobro, banco, propietarios):
    assert cobro.apuntes.count() == 2
    assert cobro.total_debe() == cobro.total_haber() == D("100.00")


@pytest.mark.django_db
def test_asientos_numerados_correlativamente_por_comunidad(
    cobro, comunidad, otra_comunidad, banco, propietarios
):
    segundo = registrar_asiento(
        comunidad,
        date(2026, 1, 11),
        "Otro cobro",
        [Linea(banco, debe=D("5.00")), Linea(propietarios, haber=D("5.00"))],
    )
    banco_b = Cuenta.objects.create(comunidad=otra_comunidad, codigo="572", nombre="Banco")
    caja_b = Cuenta.objects.create(comunidad=otra_comunidad, codigo="570", nombre="Caja")
    de_otra = registrar_asiento(
        otra_comunidad,
        date(2026, 1, 11),
        "Traspaso",
        [Linea(banco_b, debe=D("5.00")), Linea(caja_b, haber=D("5.00"))],
    )
    assert (cobro.numero, segundo.numero, de_otra.numero) == (1, 2, 1)


@pytest.mark.django_db
def test_no_se_registra_un_asiento_descuadrado(comunidad, banco, propietarios):
    with pytest.raises(AsientoInvalido, match="descuadrado"):
        registrar_asiento(
            comunidad,
            date(2026, 1, 10),
            "Mal",
            [Linea(banco, debe=D("100.00")), Linea(propietarios, haber=D("90.00"))],
        )
    assert not Asiento.objects.exists()
    assert not Apunte.objects.exists()


@pytest.mark.django_db
def test_no_se_mezclan_cuentas_de_otra_comunidad(comunidad, otra_comunidad, banco):
    ajena = Cuenta.objects.create(comunidad=otra_comunidad, codigo="430", nombre="Ajena")
    with pytest.raises(AsientoInvalido, match="otra comunidad"):
        registrar_asiento(
            comunidad,
            date(2026, 1, 10),
            "Mezcla",
            [Linea(banco, debe=D("1.00")), Linea(ajena, haber=D("1.00"))],
        )
    assert not Asiento.objects.exists()


# --- Inmutabilidad (Python) --------------------------------------------------------


@pytest.mark.django_db
def test_un_asiento_no_se_puede_modificar(cobro):
    cobro.concepto = "Cambiado"
    with pytest.raises(ContabilidadInmutable):
        cobro.save()


@pytest.mark.django_db
def test_un_asiento_no_se_puede_borrar(cobro):
    with pytest.raises(ContabilidadInmutable):
        cobro.delete()
    with pytest.raises(ContabilidadInmutable):
        Asiento.objects.all().delete()


@pytest.mark.django_db
def test_un_apunte_no_se_puede_modificar_ni_borrar(cobro):
    apunte = cobro.apuntes.first()
    apunte.debe = D("1.00")
    with pytest.raises(ContabilidadInmutable):
        apunte.save()
    with pytest.raises(ContabilidadInmutable):
        apunte.delete()
    with pytest.raises(ContabilidadInmutable):
        Apunte.objects.update(concepto="x")


# --- Inmutabilidad y cuadre (PostgreSQL, segunda barrera) --------------------------


def _sql(sentencia, parametros=()):
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(sentencia, parametros)
        # Los triggers de cuadre son diferidos (se comprueban al confirmar la transacción);
        # esto los fuerza a comprobarse ya, dentro del test.
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")


@pytest.mark.django_db
def test_postgresql_impide_modificar_apuntes(cobro):
    with pytest.raises(DatabaseError, match="inmutables"):
        _sql("UPDATE contabilidad_apunte SET debe = debe + 1 WHERE asiento_id = %s", [cobro.pk])


@pytest.mark.django_db
def test_postgresql_impide_borrar_asientos(cobro):
    with pytest.raises(DatabaseError, match="inmutables"):
        _sql("DELETE FROM contabilidad_asiento WHERE id = %s", [cobro.pk])


@pytest.mark.django_db
def test_postgresql_impide_asientos_descuadrados(comunidad, banco):
    asiento = Asiento.objects.create(
        comunidad=comunidad, numero=99, fecha=date(2026, 1, 1), concepto="A mano"
    )
    with pytest.raises(DatabaseError, match="descuadrado"):
        _sql(
            "INSERT INTO contabilidad_apunte (asiento_id, cuenta_id, debe, haber, concepto) "
            "VALUES (%s, %s, 10, 0, '')",
            [asiento.pk, banco.pk],
        )


@pytest.mark.django_db
def test_postgresql_impide_apunte_en_el_debe_y_el_haber_a_la_vez(cobro, banco):
    with pytest.raises(DatabaseError):
        _sql(
            "INSERT INTO contabilidad_apunte (asiento_id, cuenta_id, debe, haber, concepto) "
            "VALUES (%s, %s, 5, 5, '')",
            [cobro.pk, banco.pk],
        )


# --- Contra-asiento ----------------------------------------------------------------


@pytest.mark.django_db
def test_anular_crea_un_contra_asiento_con_debe_y_haber_invertidos(cobro, banco, propietarios):
    contra = anular_asiento(cobro, date(2026, 1, 15))
    assert contra.anula == cobro
    assert contra.numero == 2
    assert "Anulación del asiento 1" in contra.concepto
    lineas = {(a.cuenta, a.debe, a.haber) for a in contra.apuntes.all()}
    assert lineas == {(banco, D("0.00"), D("100.00")), (propietarios, D("100.00"), D("0.00"))}
    # El original sigue intacto: no se modifica ni se borra.
    cobro.refresh_from_db()
    assert cobro.apuntes.count() == 2
    assert cobro.esta_anulado()


@pytest.mark.django_db
def test_tras_anular_los_saldos_vuelven_a_cero(cobro, banco, propietarios):
    anular_asiento(cobro, date(2026, 1, 15))
    assert banco.saldo() == propietarios.saldo() == D("0.00")


@pytest.mark.django_db
def test_no_se_anula_dos_veces(cobro):
    anular_asiento(cobro, date(2026, 1, 15))
    with pytest.raises(AsientoInvalido, match="ya está anulado"):
        anular_asiento(cobro, date(2026, 1, 16))


@pytest.mark.django_db
def test_no_se_anula_un_contra_asiento(cobro):
    contra = anular_asiento(cobro, date(2026, 1, 15))
    with pytest.raises(AsientoInvalido, match="contra-asiento"):
        anular_asiento(contra, date(2026, 1, 16))


# --- Saldo calculado ---------------------------------------------------------------


@pytest.mark.django_db
def test_saldo_se_calcula_a_partir_de_los_apuntes(comunidad, cobro, banco, propietarios, limpieza):
    registrar_asiento(
        comunidad,
        date(2026, 2, 1),
        "Factura limpieza enero",
        [Linea(limpieza, debe=D("30.00")), Linea(banco, haber=D("30.00"))],
    )
    # Saldo = Debe - Haber (positivo = deudor, negativo = acreedor).
    assert banco.saldo() == D("70.00")
    assert propietarios.saldo() == D("-100.00")
    assert limpieza.saldo() == D("30.00")


@pytest.mark.django_db
def test_saldo_a_una_fecha(comunidad, cobro, banco, limpieza):
    registrar_asiento(
        comunidad,
        date(2026, 2, 1),
        "Factura limpieza enero",
        [Linea(limpieza, debe=D("30.00")), Linea(banco, haber=D("30.00"))],
    )
    assert banco.saldo(hasta=date(2026, 1, 31)) == D("100.00")
    assert banco.saldo(hasta=date(2026, 2, 1)) == D("70.00")


@pytest.mark.django_db
def test_cuenta_sin_movimientos_tiene_saldo_cero(banco):
    assert banco.saldo() == D("0.00")


@pytest.mark.django_db
def test_la_suma_de_todos_los_saldos_de_una_comunidad_es_cero(comunidad, cobro, banco, limpieza):
    # Consecuencia de la partida doble: si cada asiento cuadra, el total también.
    registrar_asiento(
        comunidad,
        date(2026, 2, 1),
        "Factura limpieza",
        [Linea(limpieza, debe=D("30.00")), Linea(banco, haber=D("30.00"))],
    )
    assert sum(c.saldo() for c in comunidad.cuentas.all()) == D("0.00")


@pytest.mark.django_db
def test_codigo_de_cuenta_unico_en_la_comunidad(comunidad, banco, otra_comunidad):
    from django.db import IntegrityError

    Cuenta.objects.create(comunidad=otra_comunidad, codigo="572", nombre="Banco")  # otra: vale
    with pytest.raises(IntegrityError), transaction.atomic():
        Cuenta.objects.create(comunidad=comunidad, codigo="572", nombre="Repetida")
