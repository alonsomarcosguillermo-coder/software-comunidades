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

from datetime import date, datetime, timedelta

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
