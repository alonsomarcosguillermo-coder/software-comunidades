"""Juntas de propietarios: reglas puras (sin base de datos).

T4.1 — Plazos de la convocatoria (art. 16 LPH; ver `docs/DOMINIO.md`, pendiente de validar):
- R-JUN-02: la ordinaria se cita con al menos 6 días de antelación. Se cuentan días
  naturales COMPLETOS entre la citación y la junta (sin contar ninguno de los dos): citada
  el día 1, la junta puede ser el 8. Es la lectura más prudente: una junta mal convocada
  se puede impugnar. La extraordinaria no tiene plazo fijo ("la antelación posible para que
  llegue a conocimiento de todos"): se exige al menos que sea otro día posterior.
- R-JUN-03: la segunda convocatoria se celebra en el lugar de la primera y puede ser el
  mismo día si ha pasado al menos media hora.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

ANTELACION_ORDINARIA = 6  # días naturales completos (R-JUN-02, art. 16.3 LPH)
SEPARACION_SEGUNDA = timedelta(minutes=30)  # R-JUN-03, art. 16.2 LPH


class ConvocatoriaInvalida(ValueError):
    """La junta no se puede convocar así."""


def fecha_minima_ordinaria(citacion: date) -> date:
    """Primer día en que puede celebrarse una junta ordinaria citada en `citacion`."""
    return citacion + timedelta(days=ANTELACION_ORDINARIA + 1)


def comprobar_antelacion(*, ordinaria: bool, citacion: date, junta: date) -> None:
    """R-JUN-02. Lanza `ConvocatoriaInvalida` si la junta llega demasiado pronto."""
    if ordinaria:
        minima = fecha_minima_ordinaria(citacion)
        if junta < minima:
            raise ConvocatoriaInvalida(
                f"R-JUN-02: una junta ordinaria se cita con al menos {ANTELACION_ORDINARIA} "
                f"días completos de antelación. Citando el {citacion:%d/%m/%Y}, la junta no "
                f"puede ser antes del {minima:%d/%m/%Y}."
            )
    elif junta <= citacion:
        raise ConvocatoriaInvalida(
            "R-JUN-02: la junta extraordinaria tiene que ser posterior al día de la citación, "
            "con la antelación suficiente para que llegue a todos."
        )


def comprobar_segunda_convocatoria(primera: datetime, segunda: datetime | None) -> None:
    """R-JUN-03. `segunda` es opcional; si se indica, al menos media hora después."""
    if segunda is not None and segunda < primera + SEPARACION_SEGUNDA:
        raise ConvocatoriaInvalida(
            "R-JUN-03: la segunda convocatoria tiene que ser al menos media hora después de "
            "la primera."
        )


# --- T4.3: celebración ---------------------------------------------------------------------

PLAZO_DISCREPANCIA = timedelta(days=30)  # R-MAY-05, art. 17.8 LPH: 30 días naturales


@dataclass(frozen=True)
class InmuebleConTitulares:
    id: int
    coeficiente: Decimal
    titulares: tuple  # propietarios (ids o nombres), ordenados: el primero representa


def votantes(inmuebles: list[InmuebleConTitulares], representantes: dict | None = None) -> dict:
    """Quién vota y con qué cuota: {propietario: suma de coeficientes que representa}.

    Cada inmueble vota una vez, por su titular o, si hay cotitulares, por su representante
    (art. 15.1 LPH): el elegido en `representantes` o, si no, el primero de la lista. Un
    propietario con varios inmuebles es un solo votante con la suma de sus cuotas.
    """
    representantes = representantes or {}
    cuotas: dict = {}
    for inmueble in inmuebles:
        if not inmueble.titulares:
            continue  # sin titular, nadie vota por él
        quien = representantes.get(inmueble.id, inmueble.titulares[0])
        if quien not in inmueble.titulares:
            raise ValueError(f"El representante del inmueble {inmueble.id} no es su titular.")
        cuotas[quien] = cuotas.get(quien, Decimal("0")) + inmueble.coeficiente
    return cuotas


def convocatoria_aplicable(
    inicio: datetime, primera: datetime, segunda: datetime | None, *, hay_quorum: bool
) -> int:
    """R-JUN-03: 1 si hay quórum de primera; si no, 2 cuando ya es la hora de la segunda."""
    if inicio < primera:
        raise ConvocatoriaInvalida("No se puede iniciar la junta antes de la hora convocada.")
    if hay_quorum:
        return 1
    if segunda is None:
        raise ConvocatoriaInvalida(
            "R-JUN-03: no hay quórum en primera convocatoria y la junta no tenía segunda: "
            "hay que convocar otra."
        )
    if inicio < segunda:
        raise ConvocatoriaInvalida(
            "R-JUN-03: no hay quórum en primera convocatoria: espera a la hora de la segunda "
            f"convocatoria ({segunda:%H:%M})."
        )
    return 2


def plazo_ausentes_vencido(notificados: date | None, hoy: date) -> bool:
    """R-MAY-05: ¿han pasado los 30 días naturales que tienen los ausentes para discrepar?"""
    return notificados is not None and hoy > notificados + PLAZO_DISCREPANCIA
