"""Juntas de propietarios (Fase 4).

T4.1 — Una `Junta` se prepara (fechas, lugar, orden del día) y se convoca con
`juntas.convocatoria.convocar`, que crea una `Citacion` por propietario y envía los
emails. Desde que está convocada no cambia: es lo que se comunicó a los propietarios.
"""

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from fincas.models import Comunidad, Propietario


class JuntaConvocada(ValidationError):
    """Se ha intentado cambiar una junta (o su orden del día) ya convocada."""

    def __init__(self):
        super().__init__(
            "La junta ya está convocada: no se puede cambiar lo que se ha comunicado a los "
            "propietarios. Si hace falta, convoca otra.",
            code="junta_convocada",
        )


class Junta(models.Model):
    class Tipo(models.TextChoices):
        ORDINARIA = "ordinaria", "Ordinaria"
        EXTRAORDINARIA = "extraordinaria", "Extraordinaria"

    comunidad = models.ForeignKey(Comunidad, on_delete=models.PROTECT, related_name="juntas")
    tipo = models.CharField(max_length=15, choices=Tipo.choices)
    primera_convocatoria = models.DateTimeField("primera convocatoria")
    # R-JUN-03: opcional; en el mismo lugar, al menos media hora después de la primera.
    segunda_convocatoria = models.DateTimeField("segunda convocatoria", null=True, blank=True)
    lugar = models.CharField(max_length=200)
    # Art. 16.2 LPH: convoca el presidente (o los promotores de la reunión).
    convoca = models.CharField(
        "convoca", max_length=200, help_text="Quién convoca, p. ej. «El presidente, Ana Pérez»."
    )
    # Día de la citación. Vacío = borrador (todavía se puede cambiar).
    convocada_el = models.DateField("convocada el", null=True, blank=True)
    creada_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "junta"
        verbose_name_plural = "juntas"
        ordering = ["comunidad", "-primera_convocatoria"]
        constraints = [
            models.CheckConstraint(
                condition=Q(segunda_convocatoria__isnull=True)
                | Q(segunda_convocatoria__gt=models.F("primera_convocatoria")),
                name="junta_segunda_despues_de_la_primera",
            ),
        ]

    def __str__(self) -> str:
        tipo = self.get_tipo_display().lower()
        return f"Junta {tipo} · {self.comunidad} · {self.primera_convocatoria:%d/%m/%Y}"

    def save(self, *args, **kwargs):
        # Solo `convocar` pasa de borrador a convocada; después, nada cambia.
        if self.pk and Junta.objects.filter(pk=self.pk, convocada_el__isnull=False).exists():
            raise JuntaConvocada()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.esta_convocada:
            raise JuntaConvocada()
        return super().delete(*args, **kwargs)

    @property
    def esta_convocada(self) -> bool:
        return self.convocada_el is not None

    @property
    def es_ordinaria(self) -> bool:
        return self.tipo == self.Tipo.ORDINARIA


class PuntoOrden(models.Model):
    """Un punto del orden del día y la mayoría que necesita (T4.2 la calcula)."""

    class Mayoria(models.TextChoices):
        # R-MAY-02: art. 17.7 LPH (los "demás acuerdos").
        SIMPLE = "simple", "Simple (art. 17.7)"
        # R-MAY-03: art. 17.3 LPH.
        TRES_QUINTOS = "tres_quintos", "Tres quintos (art. 17.3)"
        # R-MAY-04: art. 17.6 LPH (título constitutivo o estatutos).
        UNANIMIDAD = "unanimidad", "Unanimidad (art. 17.6)"
        # Puntos sin votación: informes, ruegos y preguntas.
        SIN_VOTACION = "sin_votacion", "Sin votación"

    junta = models.ForeignKey(Junta, on_delete=models.CASCADE, related_name="puntos")
    orden = models.PositiveSmallIntegerField()
    titulo = models.CharField("asunto", max_length=300)
    descripcion = models.TextField("detalle", blank=True)
    mayoria = models.CharField(max_length=15, choices=Mayoria.choices, default=Mayoria.SIMPLE)
    # R-MAY-05: los ausentes que no discrepan cuentan a favor, salvo las excepciones del
    # art. 17.8 LPH (p. ej. servicios cuyo coste no se puede repercutir a quien no votó a
    # favor). Lo marca quien prepara la junta.
    computa_ausentes = models.BooleanField(
        "computa ausentes (R-MAY-05)",
        default=True,
        help_text="Desmárcalo en las excepciones del art. 17.8 LPH.",
    )

    class Meta:
        verbose_name = "punto del orden del día"
        verbose_name_plural = "puntos del orden del día"
        ordering = ["junta", "orden"]
        constraints = [
            models.UniqueConstraint(fields=["junta", "orden"], name="punto_orden_unico"),
        ]

    def __str__(self) -> str:
        return f"{self.orden}. {self.titulo}"

    def save(self, *args, **kwargs):
        self._comprobar_borrador()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        self._comprobar_borrador()
        return super().delete(*args, **kwargs)

    def _comprobar_borrador(self):
        if Junta.objects.filter(pk=self.junta_id, convocada_el__isnull=False).exists():
            raise JuntaConvocada()


class Citacion(models.Model):
    """Un propietario citado a la junta (titular de algún inmueble el día de la citación).

    Guarda el email al que se envió (puede cambiar después en la ficha del propietario) y si
    estaba en la relación de morosos de la convocatoria (art. 16.2 LPH, ver R-VOT-01).
    """

    junta = models.ForeignKey(Junta, on_delete=models.CASCADE, related_name="citaciones")
    propietario = models.ForeignKey(Propietario, on_delete=models.PROTECT, related_name="+")
    email = models.EmailField(blank=True)
    enviada_en = models.DateTimeField("email enviado", null=True, blank=True)
    moroso = models.BooleanField("en la relación de morosos", default=False)

    class Meta:
        verbose_name = "citación"
        verbose_name_plural = "citaciones"
        ordering = ["junta", "propietario__nombre"]
        constraints = [
            models.UniqueConstraint(fields=["junta", "propietario"], name="citacion_unica"),
        ]

    def __str__(self) -> str:
        return f"Citación de {self.propietario} a {self.junta}"


# Camino desde cada modelo hasta su despacho (ver core.aislamiento y ADR 002).
CAMPO_DESPACHO = {
    Junta: "comunidad__despacho",
    PuntoOrden: "junta__comunidad__despacho",
    Citacion: "junta__comunidad__despacho",
}
