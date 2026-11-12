"""T4.2 — Cálculo de mayorías de la junta de propietarios. Funciones puras, sin Django.

Reglas (ver `docs/DOMINIO.md`, pendientes de validar con un profesional; texto de la LPH
consultado en el BOE, versión del 03/10/2026):

- R-MAY-01: doble mayoría. Todo acuerdo se cuenta a la vez por número de propietarios y por
  suma de cuotas de participación; tienen que cumplirse las dos condiciones.
- R-MAY-02 (art. 17.7): mayoría simple.
  - 1ª convocatoria: más de la mitad del TOTAL de propietarios, que representen más de la
    mitad del total de las cuotas.
  - 2ª convocatoria: más de la mitad de los ASISTENTES, siempre que representen más de la
    mitad de las cuotas de los presentes. Las abstenciones están presentes: cuentan en la
    base pero no a favor.
- R-MAY-03 (art. 17.3): al menos tres quintos del total de propietarios y de las cuotas.
- R-MAY-04 (art. 17.6): unanimidad del total de propietarios y de las cuotas.
- R-MAY-05 (art. 17.8): en las mayorías que se cuentan sobre el total (todas salvo la simple
  en 2ª convocatoria), los ausentes debidamente citados que, informados del acuerdo, no
  manifiestan su discrepancia en 30 días naturales se computan a favor. Quien llama decide
  si se aplica (`computar_ausentes`): pasado el plazo y si el punto no es una excepción.
- R-VOT-01 (art. 15.2): un propietario privado del derecho de voto no se computa, ni su
  persona ni su cuota, a efectos de alcanzar las mayorías: no está en la base.
- R-JUN-03 (art. 16.2): quórum de 1ª convocatoria = asisten la mayoría de los propietarios
  que representan la mayoría de las cuotas. Los privados de voto pueden asistir: cuentan.

"Más de la mitad" y "tres quintos" se comparan con aritmética exacta (enteros y Decimal),
sin redondeos: 3/5 de 7 propietarios exige 5 (4,2 → hay que llegar a 4,2, o sea 5).
"""

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

CERO = Decimal("0")


class Sentido(StrEnum):
    FAVOR = "favor"
    CONTRA = "contra"
    ABSTENCION = "abstencion"
    AUSENTE = "ausente"  # ni presente ni representado


class Mayoria(StrEnum):
    # Mismos valores que `juntas.models.PuntoOrden.Mayoria`.
    SIMPLE = "simple"
    TRES_QUINTOS = "tres_quintos"
    UNANIMIDAD = "unanimidad"


@dataclass(frozen=True)
class Voto:
    """El voto de un propietario (o del representante de un inmueble) en un punto."""

    votante: int
    cuota: Decimal  # suma de las cuotas de participación que representa (%)
    sentido: Sentido
    privado_de_voto: bool = False  # R-VOT-01
    discrepa: bool = False  # R-MAY-05: ausente que manifestó su discrepancia en plazo

    def __post_init__(self):
        if self.cuota < 0:
            raise ValueError("La cuota de participación no puede ser negativa.")


@dataclass(frozen=True)
class Recuento:
    propietarios: int = 0
    cuotas: Decimal = CERO

    def __add__(self, otro: "Recuento") -> "Recuento":
        return Recuento(self.propietarios + otro.propietarios, self.cuotas + otro.cuotas)


def _recuento(votos: Iterable[Voto]) -> Recuento:
    votos = list(votos)
    return Recuento(len(votos), sum((v.cuota for v in votos), CERO))


@dataclass(frozen=True)
class Resultado:
    mayoria: Mayoria
    segunda_convocatoria: bool
    aprobado: bool
    # Votos emitidos o ausencias de quienes SÍ pueden votar.
    favor: Recuento
    contra: Recuento
    abstencion: Recuento
    ausentes: Recuento
    ausentes_a_favor: Recuento  # R-MAY-05: ausentes computados a favor (si se aplica)
    privados: Recuento  # R-VOT-01: fuera del cómputo
    base: Recuento  # sobre qué se calcula la mayoría (total o presentes)
    a_favor: Recuento  # lo que cuenta a favor (presentes a favor + ausentes computados)
    explicacion: str


def _mas_de_la_mitad(parte, todo) -> bool:
    return parte * 2 > todo


def _tres_quintos(parte, todo) -> bool:
    return parte * 5 >= todo * 3


def _cumple(regla, a_favor: Recuento, base: Recuento) -> tuple[bool, bool]:
    return regla(a_favor.propietarios, base.propietarios), regla(a_favor.cuotas, base.cuotas)


def calcular(
    votos: Iterable[Voto],
    mayoria: Mayoria,
    *,
    segunda_convocatoria: bool,
    computar_ausentes: bool,
) -> Resultado:
    """¿Se aprueba el acuerdo con estos votos? Devuelve el recuento y por qué."""
    votos = list(votos)
    con_voto = [v for v in votos if not v.privado_de_voto]  # R-VOT-01
    por_sentido = {s: [v for v in con_voto if v.sentido == s] for s in Sentido}
    favor = _recuento(por_sentido[Sentido.FAVOR])
    ausentes = por_sentido[Sentido.AUSENTE]
    presentes = [v for v in con_voto if v.sentido != Sentido.AUSENTE]

    sobre_presentes = mayoria == Mayoria.SIMPLE and segunda_convocatoria
    if sobre_presentes:
        # R-MAY-02 en 2ª: solo cuentan los asistentes; R-MAY-05 no interviene.
        base, ausentes_a_favor = _recuento(presentes), Recuento()
    else:
        base = _recuento(con_voto)
        ausentes_a_favor = (
            _recuento(v for v in ausentes if not v.discrepa) if computar_ausentes else Recuento()
        )
    a_favor = favor + ausentes_a_favor

    if mayoria == Mayoria.UNANIMIDAD:
        propietarios_ok = a_favor.propietarios == base.propietarios
        cuotas_ok = a_favor.cuotas == base.cuotas
        regla = "R-MAY-04: unanimidad del total de propietarios y de cuotas"
    elif mayoria == Mayoria.TRES_QUINTOS:
        propietarios_ok, cuotas_ok = _cumple(_tres_quintos, a_favor, base)
        regla = "R-MAY-03: tres quintos del total de propietarios y de cuotas"
    elif sobre_presentes:
        propietarios_ok, cuotas_ok = _cumple(_mas_de_la_mitad, a_favor, base)
        regla = (
            "R-MAY-02 (2ª convocatoria): más de la mitad de los asistentes, que representen "
            "más de la mitad de las cuotas presentes"
        )
    else:
        propietarios_ok, cuotas_ok = _cumple(_mas_de_la_mitad, a_favor, base)
        regla = (
            "R-MAY-02 (1ª convocatoria): más de la mitad del total de propietarios, que "
            "representen más de la mitad del total de las cuotas"
        )
    # Sin nadie que pueda votar (o sin cuotas) no hay acuerdo.
    aprobado = propietarios_ok and cuotas_ok and base.propietarios > 0 and base.cuotas > 0

    if aprobado:
        explicacion = f"Aprobado. {regla} (R-MAY-01: doble mayoría)."
    else:
        faltan = [
            texto
            for texto, ok in [("propietarios", propietarios_ok), ("cuotas", cuotas_ok)]
            if not ok
        ] or ["votantes"]
        explicacion = (
            f"No aprobado: no se alcanza la mayoría en {' ni en '.join(faltan)}. {regla} "
            "(R-MAY-01: doble mayoría)."
        )

    return Resultado(
        mayoria=mayoria,
        segunda_convocatoria=segunda_convocatoria,
        aprobado=aprobado,
        favor=favor,
        contra=_recuento(por_sentido[Sentido.CONTRA]),
        abstencion=_recuento(por_sentido[Sentido.ABSTENCION]),
        ausentes=_recuento(ausentes),
        ausentes_a_favor=ausentes_a_favor,
        privados=_recuento(v for v in votos if v.privado_de_voto),
        base=base,
        a_favor=a_favor,
        explicacion=explicacion,
    )


def hay_quorum_primera(votos: Iterable[Voto]) -> bool:
    """R-JUN-03: ¿asisten en 1ª convocatoria la mayoría de los propietarios que representan la
    mayoría de las cuotas? (incluidos los privados de voto, que pueden asistir)."""
    votos = list(votos)
    todos = _recuento(votos)
    asistentes = _recuento(v for v in votos if v.sentido != Sentido.AUSENTE)
    return _mas_de_la_mitad(asistentes.propietarios, todos.propietarios) and _mas_de_la_mitad(
        asistentes.cuotas, todos.cuotas
    )
