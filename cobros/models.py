"""Presupuesto ordinario anual y sus partidas (T2.1); emisiones de cuotas (T2.2); derramas
(T2.3).

Un presupuesto en borrador se edita libremente. Una vez aprobado (R-PRE-01: en la junta
ordinaria; mientras no exista la app de juntas, se anota la fecha a mano) sus importes
quedan fijos, porque de él salen las cuotas. Con cuotas emitidas ya no se puede ni
quitar la aprobación.

Las emisiones y sus cuotas van unidas a un asiento contable y, como él, son inmutables.

Una derrama se edita libremente hasta que se emite (`cobros.derramas.emitir_derrama`): desde
entonces tiene asiento contable y cuotas, y no se puede cambiar ni borrar.

Recibos y mandatos SEPA (T2.4): de cada cuota (ordinaria o de derrama) sale un recibo, que
paga el titular del inmueble. Si ese propietario tiene un mandato SEPA vigente, el recibo
se puede domiciliar (cobrar por remesa).
"""

from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q

from contabilidad.models import Asiento, InmutableQuerySet, ModeloInmutable
from fincas.models import Comunidad, GrupoReparto, Inmueble, Propietario, validar_campo_iban

from .sepa.identificadores import iban_oculto
from .servicios import CERO, total_partidas, vencimientos


class PresupuestoAprobado(ValidationError):
    """Se ha intentado cambiar los importes de un presupuesto ya aprobado."""

    def __init__(self, mensaje: str = ""):
        super().__init__(
            mensaje
            or "El presupuesto ya está aprobado: sus importes no se pueden cambiar. "
            "Quita antes la fecha de aprobación si de verdad hay que corregirlo.",
            code="presupuesto_aprobado",
        )


class PresupuestoQuerySet(models.QuerySet):
    def aprobados(self):
        return self.filter(fecha_aprobacion__isnull=False)

    def ultimo_aprobado(self, comunidad: Comunidad) -> "Presupuesto | None":
        """R-RES-01: el "último presupuesto ordinario" de la comunidad, el aprobado del
        ejercicio más reciente. Un borrador todavía no cuenta."""
        return self.aprobados().filter(comunidad=comunidad).order_by("-ejercicio").first()

    def delete(self):
        # El borrado masivo (p. ej. la acción del admin) no pasa por `Presupuesto.delete()`.
        if self.aprobados().exists():
            raise PresupuestoAprobado("Un presupuesto aprobado no se puede borrar.")
        return super().delete()


class Presupuesto(models.Model):
    """Presupuesto ordinario de una comunidad para un ejercicio (año natural).

    Total a cobrar = gastos previstos (suma de partidas) + aportación al fondo de reserva.
    Las derramas (gastos extraordinarios) no van aquí: son otra cosa (T2.3).
    """

    comunidad = models.ForeignKey(Comunidad, on_delete=models.PROTECT, related_name="presupuestos")
    ejercicio = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(2000), MaxValueValidator(2100)]
    )
    # R-PRE-01: el presupuesto ordinario se aprueba en la junta ordinaria anual.
    # Vacía = borrador. Cuando exista la app de juntas (Fase 4), enlazará con el acta.
    fecha_aprobacion = models.DateField("fecha de aprobación", null=True, blank=True)
    # R-RES-01: lo que se prevé recaudar este año para el fondo de reserva.
    aportacion_fondo_reserva = models.DecimalField(
        "aportación al fondo de reserva",
        max_digits=12,
        decimal_places=2,
        default=CERO,
        validators=[MinValueValidator(CERO)],
    )

    class Periodicidad(models.IntegerChoices):
        ANUAL = 1, "Anual"
        SEMESTRAL = 2, "Semestral"
        TRIMESTRAL = 4, "Trimestral"
        MENSUAL = 12, "Mensual"

    # En cuántos periodos (cuotas) se cobra el total del año.
    periodos = models.PositiveSmallIntegerField(
        "periodicidad de las cuotas",
        choices=Periodicidad.choices,
        default=Periodicidad.TRIMESTRAL,
    )

    objects = PresupuestoQuerySet.as_manager()

    class Meta:
        verbose_name = "presupuesto"
        verbose_name_plural = "presupuestos"
        ordering = ["comunidad", "-ejercicio"]
        constraints = [
            models.UniqueConstraint(
                fields=["comunidad", "ejercicio"], name="presupuesto_unico_por_ejercicio"
            ),
            models.CheckConstraint(
                condition=Q(aportacion_fondo_reserva__gte=0),
                name="presupuesto_aportacion_no_negativa",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.comunidad} · presupuesto {self.ejercicio}"

    def save(self, *args, **kwargs):
        # Aprobado: solo se puede cambiar la fecha de aprobación (o quitarla).
        if (guardado := self._guardado_aprobado()) is not None and (
            guardado.comunidad_id != self.comunidad_id
            or guardado.ejercicio != self.ejercicio
            or guardado.aportacion_fondo_reserva != self.aportacion_fondo_reserva
            or guardado.periodos != self.periodos
        ):
            raise PresupuestoAprobado()
        if guardado is not None and not self.esta_aprobado and guardado.emisiones.exists():
            raise PresupuestoAprobado(
                "Este presupuesto ya tiene cuotas emitidas: no se puede quitar su aprobación."
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self._guardado_aprobado() is not None:
            raise PresupuestoAprobado("Un presupuesto aprobado no se puede borrar.")
        return super().delete(*args, **kwargs)

    @property
    def esta_aprobado(self) -> bool:
        return self.fecha_aprobacion is not None

    def total_gastos(self) -> Decimal:
        """Suma de las partidas. Es la base del 10 % de R-RES-01 (ver DOMINIO.md)."""
        return total_partidas(self.partidas.values_list("importe", flat=True))

    def total(self) -> Decimal:
        """Lo que hay que repartir entre los inmuebles en cuotas: gastos + fondo de reserva."""
        return self.total_gastos() + self.aportacion_fondo_reserva

    def _guardado_aprobado(self) -> "Presupuesto | None":
        """La versión guardada en la base de datos, si estaba aprobada."""
        if self.pk is None:
            return None
        return Presupuesto.objects.aprobados().filter(pk=self.pk).first()


class Partida(models.Model):
    """Gasto previsto de un presupuesto: limpieza, luz, seguro, ascensor..."""

    presupuesto = models.ForeignKey(Presupuesto, on_delete=models.CASCADE, related_name="partidas")
    concepto = models.CharField(max_length=200)
    importe = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )

    class Meta:
        verbose_name = "partida"
        verbose_name_plural = "partidas"
        ordering = ["presupuesto", "id"]
        constraints = [
            models.CheckConstraint(condition=Q(importe__gt=0), name="partida_importe_positivo"),
            models.UniqueConstraint(
                fields=["presupuesto", "concepto"], name="partida_concepto_unico_en_presupuesto"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.concepto}: {self.importe} €"

    def save(self, *args, **kwargs):
        if self._presupuesto_aprobado():
            raise PresupuestoAprobado()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self._presupuesto_aprobado():
            raise PresupuestoAprobado()
        return super().delete(*args, **kwargs)

    def _presupuesto_aprobado(self) -> bool:
        # Se consulta la base de datos (no `self.presupuesto`, que podría estar desfasado).
        return Presupuesto.objects.aprobados().filter(pk=self.presupuesto_id).exists()


class Emision(ModeloInmutable):
    """Emisión de las cuotas ordinarias de un periodo de un presupuesto (T2.2).

    Se crea con `cobros.emision.emitir_cuotas`, junto con su asiento y sus cuotas. Es
    inmutable: un error se corregirá anulando la emisión con un contra-asiento.
    """

    presupuesto = models.ForeignKey(Presupuesto, on_delete=models.PROTECT, related_name="emisiones")
    periodo = models.PositiveSmallIntegerField()  # 1..presupuesto.periodos
    fecha = models.DateField()
    asiento = models.OneToOneField(Asiento, on_delete=models.PROTECT, related_name="emision")
    creado_en = models.DateTimeField(auto_now_add=True)

    objects = InmutableQuerySet.as_manager()

    class Meta:
        verbose_name = "emisión de cuotas"
        verbose_name_plural = "emisiones de cuotas"
        ordering = ["presupuesto", "periodo"]
        constraints = [
            # Un periodo se emite una sola vez (también si dos personas emiten a la vez).
            models.UniqueConstraint(
                fields=["presupuesto", "periodo"], name="emision_periodo_unico"
            ),
            models.CheckConstraint(condition=Q(periodo__gte=1), name="emision_periodo_positivo"),
        ]

    def __str__(self) -> str:
        return f"{self.presupuesto} · periodo {self.periodo}/{self.presupuesto.periodos}"

    def total(self) -> Decimal:
        return total_partidas(self.cuotas.values_list("importe", flat=True))


class Cuota(ModeloInmutable):
    """Lo que debe pagar un inmueble en una emisión. De ella saldrá el recibo (T2.4)."""

    emision = models.ForeignKey(Emision, on_delete=models.PROTECT, related_name="cuotas")
    inmueble = models.ForeignKey(Inmueble, on_delete=models.PROTECT, related_name="cuotas")
    importe = models.DecimalField(max_digits=12, decimal_places=2)

    objects = InmutableQuerySet.as_manager()

    class Meta:
        verbose_name = "cuota"
        verbose_name_plural = "cuotas"
        ordering = ["emision", "inmueble__referencia"]
        constraints = [
            models.UniqueConstraint(
                fields=["emision", "inmueble"], name="cuota_unica_por_inmueble"
            ),
            models.CheckConstraint(condition=Q(importe__gt=0), name="cuota_importe_positivo"),
        ]

    def __str__(self) -> str:
        return f"{self.inmueble} · {self.importe} €"


# --- Derramas (T2.3) ------------------------------------------------------------------


class DerramaEmitida(ValidationError):
    """Se ha intentado cambiar o borrar una derrama ya emitida."""

    def __init__(self, mensaje: str = ""):
        super().__init__(
            mensaje
            or "La derrama ya está emitida (tiene asiento y cuotas): no se puede cambiar. "
            "Un error se corregirá anulándola con un contra-asiento.",
            code="derrama_emitida",
        )


class DerramaQuerySet(models.QuerySet):
    def emitidas(self):
        return self.filter(asiento__isnull=False)

    def delete(self):
        # El borrado masivo (p. ej. la acción del admin) no pasa por `Derrama.delete()`.
        if self.emitidas().exists():
            raise DerramaEmitida("Una derrama emitida no se puede borrar.")
        return super().delete()


class Derrama(models.Model):
    """Cobro extraordinario para un gasto no previsto en el presupuesto (p. ej. la fachada).

    El importe total se reparte entre los inmuebles por coeficiente, o solo entre los de un
    grupo de reparto (R-REP-01), y se cobra en uno o varios plazos.
    """

    comunidad = models.ForeignKey(Comunidad, on_delete=models.PROTECT, related_name="derramas")
    concepto = models.CharField(max_length=200)
    importe = models.DecimalField(
        "importe total",
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    # R-REP-01: vacío = todos los inmuebles de la comunidad, por su coeficiente general.
    grupo = models.ForeignKey(
        GrupoReparto,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="derramas",
        verbose_name="grupo de reparto",
        help_text="Vacío: todos los inmuebles de la comunidad, por su coeficiente.",
    )
    plazos = models.PositiveSmallIntegerField(
        "número de plazos", default=1, validators=[MinValueValidator(1), MaxValueValidator(120)]
    )
    primer_vencimiento = models.DateField("vencimiento del primer plazo")
    meses_entre_plazos = models.PositiveSmallIntegerField(
        "meses entre plazos", default=1, validators=[MinValueValidator(1), MaxValueValidator(12)]
    )
    # Vacía = propuesta, todavía sin acordar. Hace falta para emitirla. Cuando exista la app
    # de juntas (Fase 4), enlazará con el acta.
    fecha_acuerdo = models.DateField("fecha del acuerdo", null=True, blank=True)
    # Lo pone `emitir_derrama`. Con asiento, la derrama está emitida y ya no cambia.
    asiento = models.OneToOneField(
        Asiento,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        editable=False,
        related_name="derrama",
    )

    objects = DerramaQuerySet.as_manager()

    class Meta:
        verbose_name = "derrama"
        verbose_name_plural = "derramas"
        ordering = ["comunidad", "-primer_vencimiento", "concepto"]
        constraints = [
            models.CheckConstraint(condition=Q(importe__gt=0), name="derrama_importe_positivo"),
            models.CheckConstraint(condition=Q(plazos__gte=1), name="derrama_plazos_positivo"),
            models.CheckConstraint(
                condition=Q(meses_entre_plazos__gte=1), name="derrama_meses_entre_plazos_positivo"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.comunidad} · derrama {self.concepto}"

    def save(self, *args, **kwargs):
        if self._guardada_emitida():
            raise DerramaEmitida()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self._guardada_emitida():
            raise DerramaEmitida("Una derrama emitida no se puede borrar.")
        return super().delete(*args, **kwargs)

    def clean(self) -> None:
        if self.grupo_id is not None and self.comunidad_id is not None:
            if self.grupo.comunidad_id != self.comunidad_id:
                raise ValidationError({"grupo": "El grupo de reparto es de otra comunidad."})

    @property
    def esta_emitida(self) -> bool:
        return self.asiento_id is not None

    @property
    def esta_acordada(self) -> bool:
        return self.fecha_acuerdo is not None

    def vencimientos(self) -> list[date]:
        """Fecha de vencimiento de cada plazo (el plazo 1 es el primero de la lista)."""
        return vencimientos(self.primer_vencimiento, self.plazos, self.meses_entre_plazos)

    def _guardada_emitida(self) -> bool:
        # Se consulta la base de datos: la versión en memoria podría estar desfasada.
        return self.pk is not None and Derrama.objects.emitidas().filter(pk=self.pk).exists()


class CuotaDerrama(ModeloInmutable):
    """Lo que paga un inmueble en un plazo de una derrama. De ella saldrá el recibo (T2.4).

    Se crea con `emitir_derrama` y no cambia: así el reparto queda fijo aunque luego cambien
    los coeficientes o el grupo de reparto.
    """

    derrama = models.ForeignKey(Derrama, on_delete=models.PROTECT, related_name="cuotas")
    inmueble = models.ForeignKey(Inmueble, on_delete=models.PROTECT, related_name="cuotas_derrama")
    plazo = models.PositiveSmallIntegerField()  # 1..derrama.plazos
    vencimiento = models.DateField()
    importe = models.DecimalField(max_digits=12, decimal_places=2)

    objects = InmutableQuerySet.as_manager()

    class Meta:
        verbose_name = "cuota de derrama"
        verbose_name_plural = "cuotas de derrama"
        ordering = ["derrama", "plazo", "inmueble__referencia"]
        constraints = [
            models.UniqueConstraint(
                fields=["derrama", "inmueble", "plazo"], name="cuota_derrama_unica"
            ),
            models.CheckConstraint(condition=Q(plazo__gte=1), name="cuota_derrama_plazo_positivo"),
            models.CheckConstraint(
                condition=Q(importe__gt=0), name="cuota_derrama_importe_positivo"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.inmueble} · plazo {self.plazo} · {self.importe} €"


class DatosInmutables(ValidationError):
    """Se ha intentado cambiar un dato que, una vez guardado, no puede cambiar."""


class MandatoQuerySet(models.QuerySet):
    def vigentes(self, fecha: date):
        """R-SEPA-01: firmados en o antes de `fecha` y sin baja en esa fecha."""
        return self.filter(fecha_firma__lte=fecha).filter(
            Q(fecha_baja__isnull=True) | Q(fecha_baja__gt=fecha)
        )


class Mandato(models.Model):
    """Mandato SEPA (esquema CORE): el titular de una cuenta autoriza a la comunidad a
    cobrarle en ella los recibos de un propietario (R-SEPA-01).

    El deudor es el titular de la cuenta, que puede no ser el propietario (p. ej. un
    familiar). Una vez creado, solo se le puede dar de baja: si cambia la cuenta, se firma
    un mandato nuevo. El IBAN es un dato personal: no aparece en `__str__` ni en logs.
    """

    comunidad = models.ForeignKey(Comunidad, on_delete=models.PROTECT, related_name="mandatos")
    propietario = models.ForeignKey(Propietario, on_delete=models.PROTECT, related_name="mandatos")
    # Referencia única del mandato (UMR): la que verá el banco del deudor. Hasta 35 caracteres.
    referencia = models.CharField("referencia del mandato", max_length=35)
    titular_cuenta = models.CharField("titular de la cuenta", max_length=70)
    iban = models.CharField("IBAN", max_length=34, validators=[validar_campo_iban])
    fecha_firma = models.DateField("fecha de firma")
    fecha_baja = models.DateField("fecha de baja", null=True, blank=True)

    objects = MandatoQuerySet.as_manager()

    class Meta:
        verbose_name = "mandato SEPA"
        verbose_name_plural = "mandatos SEPA"
        ordering = ["comunidad", "referencia"]
        constraints = [
            models.UniqueConstraint(
                fields=["comunidad", "referencia"], name="mandato_referencia_unica"
            ),
            # Como mucho un mandato sin baja por propietario y comunidad.
            models.UniqueConstraint(
                fields=["comunidad", "propietario"],
                condition=Q(fecha_baja__isnull=True),
                name="mandato_un_activo_por_propietario",
            ),
            models.CheckConstraint(
                condition=Q(fecha_baja__isnull=True) | Q(fecha_baja__gte=models.F("fecha_firma")),
                name="mandato_baja_posterior_a_firma",
            ),
        ]

    def __str__(self) -> str:
        return f"Mandato {self.referencia} ({self.propietario})"

    def save(self, *args, **kwargs):
        self.iban = "".join(self.iban.split()).upper()
        if self.pk is not None:
            guardado = Mandato.objects.get(pk=self.pk)
            campos = ["comunidad_id", "propietario_id", "referencia", "iban", "fecha_firma"]
            if any(getattr(guardado, c) != getattr(self, c) for c in campos):
                raise DatosInmutables(
                    "Un mandato firmado no se modifica: dale de baja y registra uno nuevo."
                )
        super().save(*args, **kwargs)

    def clean(self) -> None:
        if self.comunidad_id and self.propietario_id:
            if self.propietario.despacho_id != self.comunidad.despacho_id:
                raise ValidationError("El propietario y la comunidad son de despachos distintos.")

    @property
    def iban_oculto(self) -> str:
        return iban_oculto(self.iban)

    def vigente_en(self, fecha: date) -> bool:
        return self.fecha_firma <= fecha and (self.fecha_baja is None or self.fecha_baja > fecha)


class Recibo(models.Model):
    """Lo que un propietario debe pagar por una cuota (ordinaria o de derrama) de un inmueble.

    Se crea con `cobros.recibos.generar_recibos` y sus datos no cambian. El estado (pendiente,
    remesado...) lo dan sus relaciones, no un campo que se edite a mano.
    """

    comunidad = models.ForeignKey(Comunidad, on_delete=models.PROTECT, related_name="recibos")
    # Correlativo dentro de la comunidad (1, 2, 3...). Lo asigna `generar_recibos`.
    numero = models.PositiveIntegerField("número")
    inmueble = models.ForeignKey(Inmueble, on_delete=models.PROTECT, related_name="recibos")
    # Quien paga: el titular del inmueble en la fecha de vencimiento.
    propietario = models.ForeignKey(Propietario, on_delete=models.PROTECT, related_name="recibos")
    # De dónde sale: una cuota ordinaria O una cuota de derrama (exactamente una).
    cuota = models.OneToOneField(
        Cuota, on_delete=models.PROTECT, null=True, blank=True, related_name="recibo"
    )
    cuota_derrama = models.OneToOneField(
        CuotaDerrama, on_delete=models.PROTECT, null=True, blank=True, related_name="recibo"
    )
    concepto = models.CharField(max_length=140)
    importe = models.DecimalField(max_digits=12, decimal_places=2)
    vencimiento = models.DateField()
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "recibo"
        verbose_name_plural = "recibos"
        ordering = ["comunidad", "numero"]
        constraints = [
            models.UniqueConstraint(fields=["comunidad", "numero"], name="recibo_numero_unico"),
            models.CheckConstraint(condition=Q(importe__gt=0), name="recibo_importe_positivo"),
            models.CheckConstraint(
                condition=(Q(cuota__isnull=False) & Q(cuota_derrama__isnull=True))
                | (Q(cuota__isnull=True) & Q(cuota_derrama__isnull=False)),
                name="recibo_de_una_sola_cuota",
            ),
        ]

    def __str__(self) -> str:
        return f"Recibo {self.numero} · {self.inmueble.referencia} · {self.importe} €"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise DatosInmutables("Los datos de un recibo no se modifican una vez emitido.")
        super().save(*args, **kwargs)

    @property
    def referencia(self) -> str:
        """Identificador del recibo fuera de la aplicación (en la remesa, el EndToEndId)."""
        return f"REC-{self.comunidad_id}-{self.numero}"


# Camino desde cada modelo hasta su despacho (ver core.aislamiento y ADR 002).
CAMPO_DESPACHO = {
    Presupuesto: "comunidad__despacho",
    Partida: "presupuesto__comunidad__despacho",
    Emision: "presupuesto__comunidad__despacho",
    Cuota: "emision__presupuesto__comunidad__despacho",
    Derrama: "comunidad__despacho",
    CuotaDerrama: "derrama__comunidad__despacho",
    Mandato: "comunidad__despacho",
    Recibo: "comunidad__despacho",
}
