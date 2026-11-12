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


# --- T4.3: celebración, asistencia y votos --------------------------------------------------


class ActaCerrada(ValidationError):
    def __init__(self):
        super().__init__(
            "El acta está cerrada: la asistencia y los votos ya no se cambian.",
            code="acta_cerrada",
        )


class Celebracion(models.Model):
    """La junta celebrada: cuándo empezó, en qué convocatoria (R-JUN-03) y quién la presidió.

    Se crea con `juntas.celebracion.iniciar_junta`. Mientras el acta no esté cerrada se pueden
    registrar votos; al cerrarla (art. 19 LPH: firma del presidente y el secretario) quedan
    fijos. La notificación a los ausentes y sus discrepancias (R-MAY-05) llegan después.
    """

    junta = models.OneToOneField(Junta, on_delete=models.PROTECT, related_name="celebracion")
    iniciada_en = models.DateTimeField("inicio")
    convocatoria = models.PositiveSmallIntegerField(choices=[(1, "Primera"), (2, "Segunda")])
    presidente = models.CharField(max_length=200)
    secretario = models.CharField(max_length=200)
    cerrada_en = models.DateTimeField("acta cerrada", null=True, blank=True)
    # R-MAY-05: día en que se notificaron los acuerdos a los ausentes (art. 9 LPH).
    ausentes_notificados_el = models.DateField(
        "acuerdos notificados a los ausentes", null=True, blank=True
    )

    class Meta:
        verbose_name = "celebración de junta"
        verbose_name_plural = "celebraciones de juntas"

    def __str__(self) -> str:
        return f"Celebración de {self.junta}"

    @property
    def esta_cerrada(self) -> bool:
        return self.cerrada_en is not None

    @property
    def es_segunda(self) -> bool:
        return self.convocatoria == 2


class Asistente(models.Model):
    """Un votante en la junta: un propietario con las cuotas de los inmuebles que representa.

    R-VOT-01: la deuda vencida se fija al iniciar la junta. Si la ha impugnado judicialmente
    o consignado, recupera el voto (art. 15.2 LPH).
    """

    class Asistencia(models.TextChoices):
        PRESENTE = "presente", "Presente"
        REPRESENTADO = "representado", "Representado"
        AUSENTE = "ausente", "Ausente"

    celebracion = models.ForeignKey(
        Celebracion, on_delete=models.CASCADE, related_name="asistentes"
    )
    propietario = models.ForeignKey(Propietario, on_delete=models.PROTECT, related_name="+")
    cuota = models.DecimalField("cuota (%)", max_digits=7, decimal_places=4)
    asistencia = models.CharField(max_length=12, choices=Asistencia.choices)
    # Art. 15.1 LPH: quien le representa (con escrito firmado).
    representante = models.CharField(max_length=200, blank=True)
    # R-VOT-01: deuda vencida e impagada al iniciarse la junta.
    deuda = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    deuda_impugnada = models.BooleanField("deuda impugnada o consignada", default=False)

    class Meta:
        verbose_name = "asistente"
        verbose_name_plural = "asistentes"
        ordering = ["celebracion", "propietario__nombre"]
        constraints = [
            models.UniqueConstraint(fields=["celebracion", "propietario"], name="asistente_unico"),
            models.CheckConstraint(
                condition=~Q(asistencia="representado") | ~Q(representante=""),
                name="representado_con_representante",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.propietario} ({self.get_asistencia_display().lower()})"

    @property
    def asiste(self) -> bool:
        return self.asistencia != self.Asistencia.AUSENTE

    @property
    def privado_de_voto(self) -> bool:
        """R-VOT-01 (art. 15.2 LPH)."""
        return self.deuda > 0 and not self.deuda_impugnada


class VotoEmitido(models.Model):
    """El sentido del voto de un asistente (presente o representado) en un punto."""

    class Sentido(models.TextChoices):
        FAVOR = "favor", "A favor"
        CONTRA = "contra", "En contra"
        ABSTENCION = "abstencion", "Abstención"

    punto = models.ForeignKey(PuntoOrden, on_delete=models.PROTECT, related_name="votos")
    asistente = models.ForeignKey(Asistente, on_delete=models.CASCADE, related_name="votos")
    sentido = models.CharField(max_length=10, choices=Sentido.choices)

    class Meta:
        verbose_name = "voto"
        verbose_name_plural = "votos"
        constraints = [
            models.UniqueConstraint(fields=["punto", "asistente"], name="un_voto_por_punto"),
        ]

    def __str__(self) -> str:
        return f"{self.asistente.propietario}: {self.get_sentido_display()} ({self.punto})"


class Discrepancia(models.Model):
    """R-MAY-05: un ausente comunica que no está de acuerdo, dentro de los 30 días."""

    class Canal(models.TextChoices):
        DESPACHO = "despacho", "Registrada por el despacho"
        PORTAL = "portal", "Portal del vecino"

    punto = models.ForeignKey(PuntoOrden, on_delete=models.PROTECT, related_name="discrepancias")
    asistente = models.ForeignKey(Asistente, on_delete=models.CASCADE, related_name="discrepancias")
    fecha = models.DateField()
    # T5.2 — Constancia de la recepción (art. 17.8 LPH): cuándo y por dónde llegó.
    canal = models.CharField(max_length=10, choices=Canal.choices, default=Canal.DESPACHO)
    recibida_en = models.DateTimeField("recibida", null=True, blank=True)

    class Meta:
        verbose_name = "discrepancia de un ausente"
        verbose_name_plural = "discrepancias de ausentes"
        constraints = [
            models.UniqueConstraint(
                fields=["punto", "asistente"], name="una_discrepancia_por_punto"
            ),
        ]

    def __str__(self) -> str:
        return f"Discrepancia de {self.asistente.propietario} ({self.punto})"


# Camino desde cada modelo hasta su despacho (ver core.aislamiento y ADR 002).
CAMPO_DESPACHO = {
    Junta: "comunidad__despacho",
    PuntoOrden: "junta__comunidad__despacho",
    Citacion: "junta__comunidad__despacho",
    Celebracion: "junta__comunidad__despacho",
    Asistente: "celebracion__junta__comunidad__despacho",
    VotoEmitido: "asistente__celebracion__junta__comunidad__despacho",
    Discrepancia: "asistente__celebracion__junta__comunidad__despacho",
}
