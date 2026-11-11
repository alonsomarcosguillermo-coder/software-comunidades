"""T2.4 — Identificadores SEPA como funciones puras: IBAN, identificador de acreedor, textos.

Todos los IBAN de los tests son ficticios: se construyen con `iban_ficticio`, que calcula
los dígitos de control de una cuenta inventada (entidad 9999).
"""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from cobros.sepa.identificadores import (
    IbanInvalido,
    construir_iban,
    iban_oculto,
    identificador_acreedor,
    normalizar_iban,
    texto_sepa,
    validar_iban,
)


def iban_ficticio(n: int = 1) -> str:
    """IBAN español válido pero inventado: entidad 9999, oficina 0000."""
    return construir_iban("ES", f"99990000{n:012d}")


# --- IBAN ---------------------------------------------------------------------------------


def test_construir_iban_calcula_los_digitos_de_control():
    iban = iban_ficticio(1)
    assert len(iban) == 24
    assert iban.startswith("ES") and iban[4:] == "99990000" + "000000000001"
    validar_iban(iban)  # no lanza


def test_normalizar_quita_espacios_y_pasa_a_mayusculas():
    iban = iban_ficticio(7)
    con_espacios = " ".join(iban[i : i + 4] for i in range(0, 24, 4)).lower()
    assert normalizar_iban(con_espacios) == iban


def test_iban_con_digito_cambiado_es_invalido():
    iban = iban_ficticio(1)
    estropeado = iban[:-1] + ("0" if iban[-1] != "0" else "1")
    with pytest.raises(IbanInvalido, match="control"):
        validar_iban(estropeado)


def test_iban_espanol_con_longitud_incorrecta():
    with pytest.raises(IbanInvalido, match="24"):
        validar_iban(construir_iban("ES", "9999000000000000001"))


@pytest.mark.parametrize("texto", ["", "ES", "1234567890", "ES12 ÑÑÑÑ", "XX!!"])
def test_iban_con_formato_imposible(texto):
    with pytest.raises(IbanInvalido):
        validar_iban(texto)


@given(st.integers(min_value=0, max_value=10**12 - 1))
def test_propiedad_todo_iban_construido_es_valido(n):
    validar_iban(iban_ficticio(n))


@given(st.integers(min_value=0, max_value=10**12 - 1), st.integers(min_value=4, max_value=23))
def test_propiedad_cambiar_un_digito_lo_invalida(n, posicion):
    iban = iban_ficticio(n)
    otro = str((int(iban[posicion]) + 1) % 10)
    with pytest.raises(IbanInvalido):
        validar_iban(iban[:posicion] + otro + iban[posicion + 1 :])


def test_iban_oculto_solo_deja_ver_pais_y_ultimos_digitos():
    iban = iban_ficticio(1234)
    oculto = iban_oculto(iban)
    assert oculto.startswith("ES") and oculto.endswith("1234")
    assert "99990000" not in oculto.replace(" ", "")


# --- Identificador de acreedor (AT-02) ------------------------------------------------------


def test_identificador_acreedor_ejemplo_del_epc():
    # Ejemplo de la documentación del EPC (Alemania): DE98ZZZ09999999999.
    assert identificador_acreedor("09999999999", pais="DE", sufijo="ZZZ") == "DE98ZZZ09999999999"


def test_identificador_acreedor_espanol_con_nif_ficticio():
    identificador = identificador_acreedor("H00000000")
    assert identificador.startswith("ES") and identificador.endswith("000H00000000")
    assert len(identificador) == 16


def test_identificador_acreedor_no_depende_del_sufijo():
    # El sufijo (código de negocio) no entra en los dígitos de control.
    assert (
        identificador_acreedor("H00000000", sufijo="001")[2:4]
        == (identificador_acreedor("H00000000")[2:4])
    )


def test_identificador_acreedor_sin_nif():
    with pytest.raises(ValueError):
        identificador_acreedor("")


# --- Textos con el juego de caracteres SEPA ------------------------------------------------


def test_texto_sepa_quita_tildes_y_enes():
    assert texto_sepa("Comunidad Peñalara, cuota 1º", 70) == "Comunidad Penalara, cuota 1o"


def test_texto_sepa_sustituye_caracteres_no_permitidos_y_recorta():
    assert texto_sepa("A & B  <C>", 70) == "A B C"
    assert texto_sepa("x" * 200, 140) == "x" * 140


@given(st.text(max_size=300))
def test_propiedad_texto_sepa_solo_usa_caracteres_permitidos(texto):
    resultado = texto_sepa(texto, 70)
    assert len(resultado) <= 70
    permitidos = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789/-?:().,'+ ")
    assert set(resultado) <= permitidos
    assert resultado == resultado.strip()
