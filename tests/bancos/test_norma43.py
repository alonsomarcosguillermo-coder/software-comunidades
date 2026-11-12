"""T3.1 — Lector (y escritor) de extractos Norma 43. Funciones puras: sin web ni BD.

El fichero de ejemplo se construye a mano, campo a campo, para que los tests del lector no
dependan del escritor (si los dos compartieran un error, el test de ida y vuelta no lo vería).
Todos los datos son ficticios (entidad 9999, que no existe).
"""

from datetime import date
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from bancos.norma43 import (
    ExtractoCuenta,
    FicheroNorma43Invalido,
    Movimiento,
    cuenta_de_iban,
    escribir_norma43,
    leer_norma43,
    nombre_concepto_comun,
)
from cobros.sepa.identificadores import construir_iban


def D(valor: str) -> Decimal:
    return Decimal(valor)


def _r11(saldo="00000000150000", clave_saldo="2", divisa="978", inicio="260401"):
    return (
        "11"
        + "9999"
        + "0000"
        + "0100000001"
        + inicio
        + "260430"
        + clave_saldo
        + saldo
        + divisa
        + "3"
        + "CP CALLE FICTICIA 1".ljust(26)
        + "   "
    )


def _r22(clave, importe, concepto="02", ref1="", ref2="", fecha="260405"):
    return (
        "22"
        + "    "
        + "1234"
        + fecha
        + fecha
        + concepto
        + "000"
        + clave
        + importe
        + "0000000123"
        + ref1.ljust(12)
        + ref2.ljust(16)
    )


def _r23(codigo, texto1, texto2=""):
    return "23" + codigo + texto1.ljust(38) + texto2.ljust(38)


def _r33(
    n_debe="00001",
    debe="00000000002000",
    n_haber="00001",
    haber="00000000004550",
    clave_saldo="2",
    saldo="00000000152550",
):
    return (
        "33"
        + "9999"
        + "0000"
        + "0100000001"
        + n_debe
        + debe
        + n_haber
        + haber
        + clave_saldo
        + saldo
        + "978"
        + "    "
    )


def _r88(registros="000005"):
    return "88" + "9" * 18 + registros + " " * 54


def _fichero(*registros: str, fin="\r\n") -> bytes:
    return "".join(r + fin for r in registros).encode("latin-1")


def _ejemplo() -> list[str]:
    """Saldo inicial 1.500,00; abono de 45,50 y cargo de 20,00 → saldo final 1.525,50."""
    return [
        _r11(),
        _r22("2", "00000000004550", ref1="REC-1-7"),
        _r23("01", "TRANSFERENCIA DE MARTA INVENTADA", "CUOTA ABRIL"),
        _r22("1", "00000000002000", concepto="17", fecha="260410"),
        _r33(),
        _r88("000005"),
    ]


def test_los_registros_de_ejemplo_miden_80_caracteres():
    # Comprobación del propio test: si un registro no mide 80, el ejemplo está mal hecho.
    assert all(len(r) == 80 for r in _ejemplo())


# --- Lectura ------------------------------------------------------------------------------


def test_lee_la_cabecera_y_el_final_de_la_cuenta():
    [extracto] = leer_norma43(_fichero(*_ejemplo()))
    assert (extracto.entidad, extracto.oficina, extracto.cuenta) == ("9999", "0000", "0100000001")
    assert extracto.fecha_inicial == date(2026, 4, 1)
    assert extracto.fecha_final == date(2026, 4, 30)
    assert extracto.saldo_inicial == D("1500.00")
    assert extracto.saldo_final == D("1525.50")
    assert extracto.divisa == "978"
    assert extracto.titular == "CP CALLE FICTICIA 1"


def test_lee_los_movimientos_con_signo():
    [extracto] = leer_norma43(_fichero(*_ejemplo()))
    abono, cargo = extracto.movimientos
    # Haber (clave 2) = entra dinero: positivo. Debe (clave 1) = sale: negativo.
    assert abono.importe == D("45.50")
    assert cargo.importe == D("-20.00")
    assert abono.fecha_operacion == date(2026, 4, 5)
    assert abono.fecha_valor == date(2026, 4, 5)
    assert (abono.concepto_comun, abono.concepto_propio) == ("02", "000")
    assert abono.oficina_origen == "1234"
    assert abono.documento == "0000000123"
    assert abono.referencia_1 == "REC-1-7"
    assert abono.referencia_2 == ""
    assert cargo.concepto_comun == "17"


def test_lee_los_conceptos_complementarios():
    [extracto] = leer_norma43(_fichero(*_ejemplo()))
    abono, cargo = extracto.movimientos
    assert abono.conceptos == ("TRANSFERENCIA DE MARTA INVENTADA", "CUOTA ABRIL")
    assert cargo.conceptos == ()


def test_saldo_deudor_es_negativo():
    registros = [
        _r11(saldo="00000000001000", clave_saldo="1"),  # -10,00 (en descubierto)
        _r22("2", "00000000003000"),
        _r33(n_debe="00000", debe="0" * 14, haber="00000000003000", saldo="00000000002000"),
        _r88("000003"),
    ]
    [extracto] = leer_norma43(_fichero(*registros))
    assert extracto.saldo_inicial == D("-10.00")
    assert extracto.saldo_final == D("20.00")


def test_cuenta_sin_movimientos():
    registros = [
        _r11(),
        _r33(
            n_debe="00000", debe="0" * 14, n_haber="00000", haber="0" * 14, saldo="00000000150000"
        ),
        _r88("000002"),
    ]
    [extracto] = leer_norma43(_fichero(*registros))
    assert extracto.movimientos == ()
    assert extracto.saldo_final == extracto.saldo_inicial


def test_varias_cuentas_en_un_fichero():
    cuenta = [
        _r11(),
        _r33(
            n_debe="00000", debe="0" * 14, n_haber="00000", haber="0" * 14, saldo="00000000150000"
        ),
    ]
    extractos = leer_norma43(_fichero(*cuenta, *cuenta, _r88("000004")))
    assert len(extractos) == 2


def test_acepta_saltos_de_linea_unix_y_registros_sin_espacios_finales():
    registros = [r.rstrip() for r in _ejemplo()]
    [extracto] = leer_norma43(_fichero(*registros, fin="\n"))
    assert len(extracto.movimientos) == 2


def test_acepta_un_fichero_sin_saltos_de_linea():
    # Algunos bancos entregan los registros de 80 caracteres seguidos, en una sola línea.
    [extracto] = leer_norma43("".join(_ejemplo()).encode("latin-1"))
    assert len(extracto.movimientos) == 2


def test_acepta_caracteres_latin1():
    registros = _ejemplo()
    registros[2] = _r23("01", "RECIBO DE LA SEÑORA PEÑA")
    contenido = _fichero(*registros)
    [extracto] = leer_norma43(contenido)
    assert extracto.movimientos[0].conceptos == ("RECIBO DE LA SEÑORA PEÑA",)


def test_ignora_lineas_vacias_al_final():
    [extracto] = leer_norma43(_fichero(*_ejemplo()) + b"\r\n\r\n")
    assert len(extracto.movimientos) == 2


def test_registro_24_de_equivalencia_de_divisa_se_admite():
    registros = _ejemplo()
    registros.insert(2, "24" + "01" + "840" + "00000000005000" + " " * 59)
    registros[-1] = _r88("000006")
    [extracto] = leer_norma43(_fichero(*registros))
    assert extracto.movimientos[0].importe == D("45.50")


# --- Ficheros que se rechazan ---------------------------------------------------------------


def _error(registros: list[str]) -> str:
    with pytest.raises(FicheroNorma43Invalido) as error:
        leer_norma43(_fichero(*registros))
    return str(error.value)


def test_fichero_vacio():
    with pytest.raises(FicheroNorma43Invalido, match="vacío"):
        leer_norma43(b"")


def test_registro_demasiado_largo():
    registros = _ejemplo()
    registros[1] += "X"
    assert "línea 2" in _error(registros).lower()


def test_tipo_de_registro_desconocido():
    registros = _ejemplo()
    registros[1] = "99" + registros[1][2:]
    mensaje = _error(registros).lower()
    assert "línea 2" in mensaje and "99" in mensaje


def test_movimiento_fuera_de_una_cuenta():
    assert "línea 1" in _error([_r22("2", "00000000004550"), _r88("000001")]).lower()


def test_concepto_complementario_sin_movimiento():
    registros = _ejemplo()
    registros.insert(1, _r23("01", "SUELTO"))
    assert "línea 2" in _error(registros).lower()


def test_mas_de_cinco_conceptos_complementarios():
    registros = _ejemplo()
    for n in range(2, 7):
        registros.insert(2 + n - 1, _r23(f"{n:02d}", "OTRO"))
    assert "complementarios" in _error(registros)


def test_cuenta_sin_registro_final():
    assert "33" in _error(_ejemplo()[:4] + [_r88("000004")])


def test_falta_el_registro_de_fin_de_fichero():
    assert "88" in _error(_ejemplo()[:-1])


def test_registros_despues_del_fin_de_fichero():
    assert "después" in _error([*_ejemplo(), _r11()])


def test_el_final_es_de_otra_cuenta():
    registros = _ejemplo()
    registros[4] = registros[4][:10] + "0100000002" + registros[4][20:]
    assert "otra cuenta" in _error(registros)


def test_numero_de_apuntes_no_cuadra():
    registros = _ejemplo()
    registros[4] = _r33(n_haber="00002")
    assert "apuntes" in _error(registros)


def test_total_no_cuadra():
    registros = _ejemplo()
    registros[4] = _r33(haber="00000000004551", saldo="00000000152551")
    assert "total" in _error(registros)


def test_saldo_final_no_cuadra_con_los_movimientos():
    registros = _ejemplo()
    registros[4] = _r33(saldo="00000000152551")
    assert "saldo final" in _error(registros)


def test_numero_de_registros_del_fin_de_fichero_no_cuadra():
    registros = _ejemplo()
    registros[-1] = _r88("000006")
    assert "registros" in _error(registros)


def test_fecha_imposible():
    registros = _ejemplo()
    registros[1] = _r22("2", "00000000004550", fecha="260231")
    assert "fecha" in _error(registros)


def test_importe_no_numerico():
    registros = _ejemplo()
    registros[1] = _r22("2", "0000000000455X")
    assert "importe" in _error(registros)


def test_clave_de_debe_o_haber_invalida():
    registros = _ejemplo()
    registros[1] = _r22("3", "00000000004550")
    assert "debe o haber" in _error(registros)


def test_fecha_inicial_posterior_a_la_final():
    registros = _ejemplo()
    registros[0] = _r11(inicio="260501")
    assert "fecha inicial" in _error(registros)


# --- Conceptos comunes y cuenta del IBAN ----------------------------------------------------


def test_nombre_del_concepto_comun():
    assert nombre_concepto_comun("14") == "Devoluciones e impagados"
    assert nombre_concepto_comun("17").startswith("Intereses")
    assert nombre_concepto_comun("55") == "Concepto 55"


def test_cuenta_de_un_iban_espanol():
    # ES + 2 dígitos de control + entidad (4) + oficina (4) + DC (2) + cuenta (10)
    iban = construir_iban("ES", "9999" + "0000" + "10" + "0100000001")
    assert cuenta_de_iban(iban) == ("9999", "0000", "0100000001")


def test_cuenta_de_un_iban_extranjero():
    assert cuenta_de_iban("DE89370400440532013000") is None


# --- Escritura (para tests y datos de demo) -------------------------------------------------


def test_el_escritor_genera_el_ejemplo_hecho_a_mano():
    extracto = ExtractoCuenta(
        entidad="9999",
        oficina="0000",
        cuenta="0100000001",
        fecha_inicial=date(2026, 4, 1),
        fecha_final=date(2026, 4, 30),
        saldo_inicial=D("1500.00"),
        titular="CP CALLE FICTICIA 1",
        movimientos=(
            Movimiento(
                fecha_operacion=date(2026, 4, 5),
                fecha_valor=date(2026, 4, 5),
                concepto_comun="02",
                importe=D("45.50"),
                oficina_origen="1234",
                documento="0000000123",
                referencia_1="REC-1-7",
                conceptos=("TRANSFERENCIA DE MARTA INVENTADA", "CUOTA ABRIL"),
            ),
            Movimiento(
                fecha_operacion=date(2026, 4, 10),
                fecha_valor=date(2026, 4, 10),
                concepto_comun="17",
                importe=D("-20.00"),
                oficina_origen="1234",
                documento="0000000123",
            ),
        ),
    )
    assert escribir_norma43([extracto]) == _fichero(*_ejemplo())


_importes = st.decimals(
    min_value=D("-99999.99"), max_value=D("99999.99"), places=2, allow_nan=False
).filter(lambda importe: importe != 0)
_textos = st.text(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZÑÇ0123456789 -./", max_size=38).map(str.strip)
_movimientos = st.builds(
    Movimiento,
    fecha_operacion=st.dates(date(2026, 1, 1), date(2026, 1, 31)),
    fecha_valor=st.dates(date(2026, 1, 1), date(2026, 2, 28)),
    concepto_comun=st.sampled_from(["01", "02", "03", "04", "14", "17", "99"]),
    importe=_importes,
    referencia_1=_textos.map(lambda t: t[:12].strip()),
    conceptos=st.lists(_textos.filter(bool), max_size=5).map(tuple),
)


@given(
    saldo=st.decimals(min_value=D("-9999.99"), max_value=D("999999.99"), places=2),
    movimientos=st.lists(_movimientos, max_size=20).map(tuple),
)
def test_ida_y_vuelta(saldo, movimientos):
    """Propiedad: lo que se escribe se vuelve a leer igual, y el saldo final cuadra."""
    extracto = ExtractoCuenta(
        entidad="9999",
        oficina="0000",
        cuenta="0100000001",
        fecha_inicial=date(2026, 1, 1),
        fecha_final=date(2026, 1, 31),
        saldo_inicial=saldo,
        movimientos=movimientos,
    )
    [leido] = leer_norma43(escribir_norma43([extracto]))
    assert leido == extracto
    assert leido.saldo_final == saldo + sum((m.importe for m in movimientos), D("0"))
