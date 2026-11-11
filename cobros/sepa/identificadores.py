"""Identificadores y textos SEPA, como funciones puras (sin base de datos ni web).

- IBAN: validación con el algoritmo mod-97 (ISO 13616).
- Identificador de acreedor (AT-02 del EPC): el que identifica a la comunidad como
  "cobradora" de adeudos. En España: país + dígitos de control + sufijo + NIF.
- Textos: SEPA solo garantiza un juego de caracteres latino básico.

Los IBAN son datos personales: nunca a logs. Para mostrarlos, `iban_oculto`.
"""

import re
import unicodedata


class IbanInvalido(ValueError):
    """El IBAN no tiene un formato o unos dígitos de control válidos."""


# Longitud del IBAN en algunos países SEPA (la de los demás solo se comprueba por rango).
LONGITUD_IBAN = {"ES": 24, "PT": 25, "FR": 27, "IT": 27, "DE": 22, "BE": 16, "NL": 18, "AD": 24}

_FORMATO_IBAN = re.compile(r"[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}")


def _a_numero(texto: str) -> int:
    """Letras a números (A=10 ... Z=35), como piden ISO 13616 y el identificador de acreedor."""
    return int("".join(str(int(caracter, 36)) for caracter in texto))


def normalizar_iban(iban: str) -> str:
    return "".join(iban.split()).upper()


def construir_iban(pais: str, bban: str) -> str:
    """IBAN a partir del código de país y la cuenta nacional (BBAN), con sus dígitos de control."""
    control = 98 - _a_numero(bban + pais + "00") % 97
    return f"{pais}{control:02d}{bban}"


def validar_iban(iban: str) -> str:
    """Devuelve el IBAN normalizado o lanza `IbanInvalido` con el motivo.

    El mensaje nunca incluye el IBAN (es un dato personal y puede acabar en un log).
    """
    iban = normalizar_iban(iban)
    if not _FORMATO_IBAN.fullmatch(iban):
        raise IbanInvalido("El IBAN no tiene un formato válido.")
    longitud = LONGITUD_IBAN.get(iban[:2])
    if longitud is not None and len(iban) != longitud:
        raise IbanInvalido(f"Un IBAN de {iban[:2]} debe tener {longitud} caracteres.")
    if _a_numero(iban[4:] + iban[:4]) % 97 != 1:
        raise IbanInvalido("Los dígitos de control del IBAN no son correctos.")
    return iban


def iban_oculto(iban: str) -> str:
    """Para mostrar en pantalla: "ES12 •••• 1234"."""
    iban = normalizar_iban(iban)
    return f"{iban[:4]} •••• {iban[-4:]}" if len(iban) > 8 else "••••"


def identificador_acreedor(nif: str, *, pais: str = "ES", sufijo: str = "000") -> str:
    """Identificador de acreedor SEPA (AT-02): país + control + sufijo + identificador nacional.

    Los dígitos de control se calculan como en el IBAN, sobre el identificador nacional (el NIF
    en España) seguido del país y "00"; el sufijo (código de negocio, "000" por defecto) no
    interviene. Ejemplo del EPC: DE98ZZZ09999999999.
    """
    nif = "".join(nif.split()).upper()
    if not nif or not nif.isalnum():
        raise ValueError("Para el identificador de acreedor hace falta el NIF de la comunidad.")
    control = 98 - _a_numero(nif + pais + "00") % 97
    return f"{pais}{control:02d}{sufijo}{nif}"


# Caracteres que todos los bancos SEPA aceptan (juego latino básico del EPC).
_NO_PERMITIDOS = re.compile(r"[^A-Za-z0-9/\-?:().,'+ ]")


def texto_sepa(texto: str, maximo: int) -> str:
    """`texto` sin tildes ni caracteres no admitidos por SEPA, recortado a `maximo`."""
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    limpio = " ".join(_NO_PERMITIDOS.sub(" ", sin_tildes).split())
    return limpio[:maximo].rstrip()
