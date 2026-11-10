"""Contabilidad de partida doble por comunidad.

Reglas (CLAUDE.md, ADR 003):
- Debe = Haber en cada asiento.
- Asientos y apuntes inmutables: se crean con `contabilidad.registro` y nunca se modifican
  ni se borran. Un error se corrige con un contra-asiento (`anular_asiento`).
- No hay campo "saldo": se calcula a partir de los apuntes (`Cuenta.saldo`).

Además de las comprobaciones en Python, PostgreSQL tiene triggers que impiden modificar o
borrar asientos/apuntes y guardar asientos descuadrados (migración 0002).
"""

from datetime import date
from decimal import Decimal

from django.db import models
from django.db.models import Q, Sum

from fincas.models import Comunidad


class ContabilidadInmutable(Exception):
    """Se ha intentado modificar o borrar un asiento o apunte."""

    def __init__(self, mensaje: str = ""):
        super().__init__(
            mensaje or "Los asientos y apuntes son inmutables: corrige con un contra-asiento."
        )


class InmutableQuerySet(models.QuerySet):
    """Impide `.update()` y `.delete()` masivos, que no pasan por `save()`/`delete()`."""

    def update(self, **kwargs):
        raise ContabilidadInmutable()

    def delete(self):
        raise ContabilidadInmutable()


class ModeloInmutable(models.Model):
    """Se puede crear, pero no modificar ni borrar."""

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ContabilidadInmutable()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ContabilidadInmutable()


class Cuenta(models.Model):
    """Cuenta contable de una comunidad (banco, propietarios, limpieza...).

    El código sigue la costumbre del Plan General Contable (572 bancos, 430 clientes /
    propietarios, 6xx gastos, 7xx ingresos), pero de momento es texto libre.
    """

    comunidad = models.ForeignKey(Comunidad, on_delete=models.PROTECT, related_name="cuentas")
    codigo = models.CharField("código", max_length=20)
    nombre = models.CharField(max_length=200)

    class Meta:
        verbose_name = "cuenta"
        verbose_name_plural = "cuentas"
        ordering = ["comunidad", "codigo"]
        constraints = [
            models.UniqueConstraint(
                fields=["comunidad", "codigo"], name="cuenta_codigo_unico_en_comunidad"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.codigo} {self.nombre}"

    def saldo(self, hasta: date | None = None) -> Decimal:
        """Debe − Haber de todos sus apuntes (hasta la fecha indicada, incluida).

        Positivo = saldo deudor; negativo = saldo acreedor.
        """
        apuntes = self.apuntes.all()
        if hasta is not None:
            apuntes = apuntes.filter(asiento__fecha__lte=hasta)
        totales = apuntes.aggregate(debe=Sum("debe"), haber=Sum("haber"))
        return (totales["debe"] or Decimal("0.00")) - (totales["haber"] or Decimal("0.00"))


class Asiento(ModeloInmutable):
    """Anotación contable: una fecha, un concepto y varios apuntes que cuadran."""

    comunidad = models.ForeignKey(Comunidad, on_delete=models.PROTECT, related_name="asientos")
    # Correlativo dentro de la comunidad (1, 2, 3...). Lo asigna `registrar_asiento`.
    numero = models.PositiveIntegerField("número")
    fecha = models.DateField()
    concepto = models.CharField(max_length=300)
    # Si este asiento es un contra-asiento, el asiento que anula. OneToOne: un asiento solo
    # se puede anular una vez (lo garantiza también la base de datos).
    anula = models.OneToOneField(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="anulado_por"
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    objects = InmutableQuerySet.as_manager()

    class Meta:
        verbose_name = "asiento"
        verbose_name_plural = "asientos"
        ordering = ["comunidad", "numero"]
        constraints = [
            models.UniqueConstraint(
                fields=["comunidad", "numero"], name="asiento_numero_unico_en_comunidad"
            ),
        ]

    def __str__(self) -> str:
        return f"Asiento {self.numero} · {self.concepto}"

    def total_debe(self) -> Decimal:
        return self.apuntes.aggregate(t=Sum("debe"))["t"] or Decimal("0.00")

    def total_haber(self) -> Decimal:
        return self.apuntes.aggregate(t=Sum("haber"))["t"] or Decimal("0.00")

    def esta_anulado(self) -> bool:
        return Asiento.objects.filter(anula=self).exists()


class Apunte(ModeloInmutable):
    """Una línea de un asiento: un importe al Debe o al Haber de una cuenta."""

    asiento = models.ForeignKey(Asiento, on_delete=models.PROTECT, related_name="apuntes")
    cuenta = models.ForeignKey(Cuenta, on_delete=models.PROTECT, related_name="apuntes")
    debe = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    haber = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    concepto = models.CharField(max_length=300, blank=True)

    objects = InmutableQuerySet.as_manager()

    class Meta:
        verbose_name = "apunte"
        verbose_name_plural = "apuntes"
        ordering = ["asiento", "id"]
        constraints = [
            # Cada apunte va al Debe O al Haber, nunca a los dos ni a ninguno, y sin negativos.
            models.CheckConstraint(
                condition=(Q(debe__gt=0) & Q(haber=0)) | (Q(debe=0) & Q(haber__gt=0)),
                name="apunte_debe_o_haber",
            ),
        ]

    def __str__(self) -> str:
        lado = f"Debe {self.debe}" if self.debe else f"Haber {self.haber}"
        return f"{self.cuenta} · {lado}"


# Camino desde cada modelo hasta su despacho (ver core.aislamiento y ADR 002).
CAMPO_DESPACHO = {
    Cuenta: "comunidad__despacho",
    Asiento: "comunidad__despacho",
    Apunte: "asiento__comunidad__despacho",
}
