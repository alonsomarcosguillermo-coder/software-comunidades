"""Extractos bancarios en formato Norma 43 (AEB, "Cuaderno 43"). Funciones puras (T3.1).

Norma 43 es un fichero de texto con registros de 80 caracteres de ancho fijo. Cada
registro empieza por su tipo:

    11  cabecera de cuenta: entidad, oficina, cuenta, fechas y saldo inicial
    22  movimiento: fechas, conceptos, importe (debe/haber), referencias
    23  conceptos complementarios del movimiento anterior (hasta 5 registros)
    24  equivalencia en otra divisa del movimiento anterior (se admite y se ignora)
    33  final de cuenta: nº de apuntes y totales del debe y del haber, saldo final
    88  fin de fichero: nº de registros

Un fichero puede traer varias cuentas (varios bloques 11 … 33) y termina con un 88.

Los totales del 33 y del 88 sirven de control: si no cuadran con los movimientos leídos,
el fichero está incompleto o corrupto y se rechaza entero (`FicheroNorma43Invalido`).

Signo de los importes: desde el punto de vista del titular de la cuenta. "Haber" (abono,
entra dinero) es positivo; "debe" (cargo, sale dinero) es negativo. Un saldo "acreedor"
(la cuenta tiene dinero) es positivo; "deudor" (en descubierto), negativo.

`escribir_norma43` hace lo contrario. La aplicación no lo necesita (los ficheros los
genera el banco), pero sirve para los tests y para los datos de demo.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

LONGITUD = 80
# Codificación habitual de los ficheros de la banca española. latin-1 nunca falla al
# decodificar (cada byte es un carácter), así que un fichero raro no rompe la lectura: como
# mucho sale algún carácter extraño en un concepto.
CODIFICACION = "latin-1"
EUROS = "978"  # código ISO 4217 numérico
MAX_CONCEPTOS = 5  # registros 23 por movimiento
CERO = Decimal("0.00")

# Clave de concepto común (posiciones 23-24 del registro 22), igual en todos los bancos.
CONCEPTOS_COMUNES = {
    "01": "Talones, reintegros",
    "02": "Abonarés, entregas, ingresos",
    "03": "Domiciliados, recibos, letras, pagos por su cuenta",
    "04": "Giros, transferencias, traspasos, cheques",
    "05": "Amortizaciones de préstamos, créditos",
    "06": "Remesas de efectos",
    "07": "Suscripciones, dividendos pasivos, canjes",
    "08": "Dividendos, cupones, prima de junta, amortizaciones",
    "09": "Operaciones de bolsa, compraventa de valores",
    "10": "Cheques de gasolina",
    "11": "Cajero automático",
    "12": "Tarjetas de crédito y débito",
    "13": "Operaciones con el extranjero",
    "14": "Devoluciones e impagados",
    "15": "Nóminas, seguros sociales",
    "16": "Timbres, corretaje, póliza",
    "17": "Intereses, comisiones, custodia, gastos e impuestos",
    "98": "Anulaciones, correcciones de asiento",
    "99": "Varios",
}


class FicheroNorma43Invalido(ValueError):
    """El fichero no cumple la Norma 43 o sus totales de control no cuadran."""


@dataclass(frozen=True)
class Movimiento:
    fecha_operacion: date
    fecha_valor: date
    concepto_comun: str  # 2 cifras, ver CONCEPTOS_COMUNES
    importe: Decimal  # + abono (haber), − cargo (debe)
    concepto_propio: str = "000"  # 3 cifras, propio de cada banco
    oficina_origen: str = "0000"
    documento: str = ""
    referencia_1: str = ""
    referencia_2: str = ""
    conceptos: tuple[str, ...] = ()  # textos de los registros 23, en orden

    @property
    def nombre_concepto(self) -> str:
        return nombre_concepto_comun(self.concepto_comun)


@dataclass(frozen=True)
class ExtractoCuenta:
    """Un bloque 11 … 33: los movimientos de una cuenta entre dos fechas."""

    entidad: str  # 4 cifras
    oficina: str  # 4 cifras
    cuenta: str  # 10 cifras (sin los dígitos de control)
    fecha_inicial: date
    fecha_final: date
    saldo_inicial: Decimal
    movimientos: tuple[Movimiento, ...] = ()
    divisa: str = EUROS
    titular: str = ""  # "nombre abreviado" del registro 11
    # Al leer: los registros originales de la cuenta (del 11 al 33). No cuenta al comparar.
    registros: tuple[str, ...] = field(default=(), compare=False, repr=False)

    @property
    def saldo_final(self) -> Decimal:
        # No se guarda: se calcula. Al leer se comprueba que coincide con el del registro 33.
        return self.saldo_inicial + sum((m.importe for m in self.movimientos), CERO)


def nombre_concepto_comun(codigo: str) -> str:
    return CONCEPTOS_COMUNES.get(codigo, f"Concepto {codigo}")


def cuenta_de_iban(iban: str) -> tuple[str, str, str] | None:
    """(entidad, oficina, cuenta) de un IBAN español, para compararla con la del extracto.

    IBAN español: ES + 2 dígitos de control + entidad (4) + oficina (4) + DC (2) + cuenta
    (10). Norma 43 no trae ni el IBAN ni los dos DC de la cuenta. None si no es español.
    """
    iban = "".join(iban.split()).upper()
    if not iban.startswith("ES") or len(iban) != 24:
        return None
    return iban[4:8], iban[8:12], iban[14:24]


# --- Lectura ------------------------------------------------------------------------------


def _registros(contenido: bytes) -> list[tuple[int, str]]:
    """[(nº de línea, registro de 80 caracteres)]. Admite CRLF o LF, registros a los que el
    banco ha quitado los espacios finales y ficheros sin saltos de línea."""
    texto = contenido.decode(CODIFICACION)
    lineas = texto.splitlines()
    if len(lineas) == 1 and len(lineas[0]) > LONGITUD and len(lineas[0]) % LONGITUD == 0:
        lineas = [lineas[0][i : i + LONGITUD] for i in range(0, len(lineas[0]), LONGITUD)]
    registros = []
    for numero, linea in enumerate(lineas, start=1):
        if not linea.strip():
            continue  # líneas en blanco (sobre todo al final)
        if len(linea) > LONGITUD:
            raise FicheroNorma43Invalido(
                f"Línea {numero}: mide {len(linea)} caracteres y un registro mide {LONGITUD}."
            )
        registros.append((numero, linea.ljust(LONGITUD)))
    return registros


class _Lector:
    """Recorre los registros comprobando el orden y los totales de control."""

    def __init__(self, registros: list[tuple[int, str]]):
        self.registros = registros
        self.extractos: list[ExtractoCuenta] = []
        self.cabecera: dict | None = None  # cuenta abierta (registro 11 sin su 33)
        self.movimientos: list[dict] = []
        self.fin_de_fichero = False
        # Registro que se está leyendo: posición en `registros` y nº de línea del fichero.
        self.indice = 0
        self.linea = 0
        self.inicio = 0  # posición del registro 11 de la cuenta abierta

    def leer(self) -> list[ExtractoCuenta]:
        if not self.registros:
            raise FicheroNorma43Invalido("El fichero está vacío.")
        for indice, (linea, registro) in enumerate(self.registros):
            self.indice, self.linea = indice, linea
            if self.fin_de_fichero:
                raise FicheroNorma43Invalido(
                    f"Línea {self.linea}: hay registros después del fin de fichero (88)."
                )
            tipo = registro[:2]
            manejador = {
                "11": self._cabecera,
                "22": self._movimiento,
                "23": self._complementario,
                "24": self._equivalencia,
                "33": self._final_de_cuenta,
                "88": self._fin_de_fichero,
            }.get(tipo)
            if manejador is None:
                raise self._error(f"tipo de registro desconocido «{tipo}».")
            manejador(registro)
        if self.cabecera is not None:
            raise FicheroNorma43Invalido(
                "Falta el registro final de cuenta (33) de la última cuenta."
            )
        if not self.fin_de_fichero:
            raise FicheroNorma43Invalido(
                "Falta el registro de fin de fichero (88): el fichero puede estar incompleto."
            )
        return self.extractos

    # Campos ------------------------------------------------------------------------------

    def _error(self, mensaje: str) -> FicheroNorma43Invalido:
        return FicheroNorma43Invalido(f"Línea {self.linea}: {mensaje}")

    def _fecha(self, texto: str, campo: str) -> date:
        """AAMMDD. Norma 43 solo trae dos cifras de año: se entiende 20AA."""
        try:
            return date(2000 + int(texto[:2]), int(texto[2:4]), int(texto[4:6]))
        except ValueError:
            raise self._error(f"{campo}: la fecha «{texto}» no existe.") from None

    def _importe(self, texto: str, campo: str = "importe") -> Decimal:
        """14 cifras: 12 enteras y 2 decimales, sin coma."""
        if not (len(texto) == 14 and texto.isdigit()):
            raise self._error(f"{campo}: el importe «{texto}» no es numérico.")
        return Decimal(f"{texto[:12]}.{texto[12:]}")

    def _numero(self, texto: str, campo: str) -> int:
        if not texto.isdigit():
            raise self._error(f"{campo}: «{texto}» no es un número.")
        return int(texto)

    def _signo(self, clave: str, campo: str) -> int:
        # 1 = debe / deudor (negativo), 2 = haber / acreedor (positivo)
        if clave not in ("1", "2"):
            raise self._error(f"{campo}: la clave de debe o haber «{clave}» no es 1 ni 2.")
        return -1 if clave == "1" else 1

    # Registros -----------------------------------------------------------------------------

    def _cabecera(self, r: str) -> None:
        if self.cabecera is not None:
            raise self._error("empieza una cuenta (11) sin haber cerrado la anterior (33).")
        fecha_inicial = self._fecha(r[20:26], "fecha inicial")
        fecha_final = self._fecha(r[26:32], "fecha final")
        if fecha_inicial > fecha_final:
            raise self._error("la fecha inicial es posterior a la fecha final.")
        self.cabecera = {
            "entidad": r[2:6],
            "oficina": r[6:10],
            "cuenta": r[10:20],
            "fecha_inicial": fecha_inicial,
            "fecha_final": fecha_final,
            "saldo_inicial": self._signo(r[32], "saldo inicial")
            * self._importe(r[33:47], "saldo inicial"),
            "divisa": r[47:50],
            "titular": r[51:77].strip(),
        }
        self.movimientos = []
        self.inicio = self.indice

    def _movimiento(self, r: str) -> None:
        if self.cabecera is None:
            raise self._error("hay un movimiento (22) fuera de una cuenta (11 … 33).")
        signo = self._signo(r[27], "movimiento")
        self.movimientos.append(
            {
                "oficina_origen": r[6:10],
                "fecha_operacion": self._fecha(r[10:16], "fecha de operación"),
                "fecha_valor": self._fecha(r[16:22], "fecha valor"),
                "concepto_comun": r[22:24],
                "concepto_propio": r[24:27],
                "debe": signo < 0,
                "importe": signo * self._importe(r[28:42]),
                "documento": r[42:52].strip(),
                "referencia_1": r[52:64].strip(),
                "referencia_2": r[64:80].strip(),
                "registros_23": [],
            }
        )

    def _ultimo_movimiento(self, tipo: str) -> dict:
        if self.cabecera is None or not self.movimientos:
            raise self._error(f"el registro {tipo} no va detrás de un movimiento (22).")
        return self.movimientos[-1]

    def _complementario(self, r: str) -> None:
        movimiento = self._ultimo_movimiento("23")
        if len(movimiento["registros_23"]) == MAX_CONCEPTOS:
            raise self._error(
                f"un movimiento tiene más de {MAX_CONCEPTOS} registros de conceptos "
                "complementarios (23)."
            )
        movimiento["registros_23"].append((r[4:42].strip(), r[42:80].strip()))

    def _equivalencia(self, r: str) -> None:
        # Importe en la divisa de origen (p. ej. una transferencia en dólares). No se usa.
        self._ultimo_movimiento("24")

    def _final_de_cuenta(self, r: str) -> None:
        c = self.cabecera
        if c is None:
            raise self._error("hay un final de cuenta (33) sin su cabecera (11).")
        if (r[2:6], r[6:10], r[10:20]) != (c["entidad"], c["oficina"], c["cuenta"]):
            raise self._error("el final de cuenta (33) es de otra cuenta que su cabecera (11).")

        debe = [m for m in self.movimientos if m["debe"]]
        haber = [m for m in self.movimientos if not m["debe"]]
        controles = [
            ("nº de apuntes del debe", self._numero(r[20:25], "apuntes del debe"), len(debe)),
            (
                "total del debe",
                self._importe(r[25:39], "total del debe"),
                -sum((m["importe"] for m in debe), CERO),
            ),
            ("nº de apuntes del haber", self._numero(r[39:44], "apuntes del haber"), len(haber)),
            (
                "total del haber",
                self._importe(r[44:58], "total del haber"),
                sum((m["importe"] for m in haber), CERO),
            ),
        ]
        for nombre, declarado, calculado in controles:
            if declarado != calculado:
                raise self._error(
                    f"el {nombre} del registro final ({declarado}) no cuadra con los "
                    f"movimientos leídos ({calculado})."
                )

        extracto = ExtractoCuenta(
            entidad=c["entidad"],
            oficina=c["oficina"],
            cuenta=c["cuenta"],
            fecha_inicial=c["fecha_inicial"],
            fecha_final=c["fecha_final"],
            saldo_inicial=c["saldo_inicial"],
            divisa=c["divisa"],
            titular=c["titular"],
            movimientos=tuple(_movimiento(m) for m in self.movimientos),
            registros=tuple(r for _, r in self.registros[self.inicio : self.indice + 1]),
        )
        saldo_final = self._signo(r[58], "saldo final") * self._importe(r[59:73], "saldo final")
        if saldo_final != extracto.saldo_final:
            raise self._error(
                f"el saldo final del registro ({saldo_final}) no cuadra con el saldo inicial "
                f"más los movimientos ({extracto.saldo_final})."
            )
        self.extractos.append(extracto)
        self.cabecera = None

    def _fin_de_fichero(self, r: str) -> None:
        if self.cabecera is not None:
            raise self._error("el fin de fichero (88) llega sin cerrar la cuenta (33).")
        declarados = self._numero(r[20:26], "nº de registros")
        if declarados != self.indice:  # todos los registros anteriores al 88
            raise self._error(
                f"el fin de fichero dice {declarados} registros y hay {self.indice}: el fichero "
                "puede estar incompleto."
            )
        self.fin_de_fichero = True


def _movimiento(datos: dict) -> Movimiento:
    # Dos textos por registro 23; los huecos vacíos no se guardan.
    conceptos = tuple(t for par in datos["registros_23"] for t in par if t)
    return Movimiento(
        fecha_operacion=datos["fecha_operacion"],
        fecha_valor=datos["fecha_valor"],
        concepto_comun=datos["concepto_comun"],
        concepto_propio=datos["concepto_propio"],
        importe=datos["importe"],
        oficina_origen=datos["oficina_origen"],
        documento=datos["documento"],
        referencia_1=datos["referencia_1"],
        referencia_2=datos["referencia_2"],
        conceptos=conceptos,
    )


def leer_norma43(contenido: bytes) -> list[ExtractoCuenta]:
    """Lee un fichero Norma 43 completo. Si algo no cuadra, lo rechaza entero."""
    return _Lector(_registros(contenido)).leer()


# --- Escritura (tests y demo) -------------------------------------------------------------


def _aammdd(fecha: date) -> str:
    return f"{fecha:%y%m%d}"


def _cifras(importe: Decimal) -> str:
    """|importe| en 14 cifras sin coma (12 enteras + 2 decimales)."""
    return f"{int(abs(importe) * 100):014d}"


def _clave(importe: Decimal) -> str:
    return "1" if importe < 0 else "2"


def _texto(valor: str, ancho: int) -> str:
    if len(valor) > ancho:
        raise ValueError(f"«{valor}» no cabe en {ancho} caracteres.")
    return valor.ljust(ancho)


def _escribir_cuenta(e: ExtractoCuenta) -> list[str]:
    cuenta = e.entidad + e.oficina + e.cuenta
    registros = [
        "11"
        + cuenta
        + _aammdd(e.fecha_inicial)
        + _aammdd(e.fecha_final)
        + _clave(e.saldo_inicial)
        + _cifras(e.saldo_inicial)
        + e.divisa
        + "3"
        + _texto(e.titular, 26)
        + "   "
    ]
    for m in e.movimientos:
        registros.append(
            "22"
            + "    "
            + m.oficina_origen
            + _aammdd(m.fecha_operacion)
            + _aammdd(m.fecha_valor)
            + m.concepto_comun
            + m.concepto_propio
            + _clave(m.importe)
            + _cifras(m.importe)
            + _texto(m.documento, 10)
            + _texto(m.referencia_1, 12)
            + _texto(m.referencia_2, 16)
        )
        textos = list(m.conceptos)
        if len(textos) > 2 * MAX_CONCEPTOS:
            raise ValueError(f"Como mucho {2 * MAX_CONCEPTOS} conceptos por movimiento.")
        for n, i in enumerate(range(0, len(textos), 2), start=1):
            par = [*textos[i : i + 2], ""][:2]
            registros.append(f"23{n:02d}" + _texto(par[0], 38) + _texto(par[1], 38))
    debe = [m.importe for m in e.movimientos if m.importe < 0]
    haber = [m.importe for m in e.movimientos if m.importe >= 0]
    registros.append(
        "33"
        + cuenta
        + f"{len(debe):05d}"
        + _cifras(sum(debe, CERO))
        + f"{len(haber):05d}"
        + _cifras(sum(haber, CERO))
        + _clave(e.saldo_final)
        + _cifras(e.saldo_final)
        + e.divisa
        + "    "
    )
    return registros


def escribir_norma43(extractos: Iterable[ExtractoCuenta]) -> bytes:
    registros = [r for e in extractos for r in _escribir_cuenta(e)]
    registros.append("88" + "9" * 18 + f"{len(registros):06d}" + " " * 54)
    assert all(len(r) == LONGITUD for r in registros)
    return "".join(r + "\r\n" for r in registros).encode(CODIFICACION)
