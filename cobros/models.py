"""Presupuesto ordinario anual de una comunidad y sus partidas (T2.1).

Un presupuesto en borrador se edita libremente. Una vez aprobado (R-PRE-01: en la junta
ordinaria; mientras no exista la app de juntas, se anota la fecha a mano) sus importes
quedan fijos, porque de él saldrán las cuotas (T2.2).
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q

from fincas.models import Comunidad

from .servicios import CERO, total_partidas


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
        ):
            raise PresupuestoAprobado()
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


# Camino desde cada modelo hasta su despacho (ver core.aislamiento y ADR 002).
CAMPO_DESPACHO = {
    Presupuesto: "comunidad__despacho",
    Partida: "presupuesto__comunidad__despacho",
}
