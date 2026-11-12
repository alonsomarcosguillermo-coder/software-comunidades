"""Extractos bancarios importados (T3.1).

Un `Extracto` es una cuenta de un fichero Norma 43 (un bloque 11 … 33): los movimientos de
la cuenta de la comunidad entre dos fechas. Se crea con `bancos.importacion.importar_norma43`
y, como los asientos, es inmutable: es lo que dijo el banco y no se retoca. La conciliación
(T3.2) los enlazará con recibos y asientos desde otro modelo, sin modificarlos.
"""

from django.conf import settings
from django.db import models
from django.db.models import F, Q

from contabilidad.models import InmutableQuerySet, ModeloInmutable
from fincas.models import Comunidad

from .norma43 import nombre_concepto_comun


class Extracto(ModeloInmutable):
    comunidad = models.ForeignKey(Comunidad, on_delete=models.PROTECT, related_name="extractos")
    # Cuenta tal y como viene en Norma 43 (sin IBAN ni dígitos de control).
    entidad = models.CharField(max_length=4)
    oficina = models.CharField(max_length=4)
    cuenta = models.CharField(max_length=10)
    fecha_inicial = models.DateField("desde")
    fecha_final = models.DateField("hasta")
    saldo_inicial = models.DecimalField(max_digits=12, decimal_places=2)
    # Se guarda porque es dato del banco, pero se comprobó al importar que es igual al saldo
    # inicial más los movimientos (y ninguno de ellos puede cambiar después).
    saldo_final = models.DecimalField(max_digits=12, decimal_places=2)
    nombre_fichero = models.CharField("fichero", max_length=255)
    # Los registros de esta cuenta tal como venían (del 11 al 33): constancia de lo importado.
    registros = models.TextField("registros Norma 43")
    importado_en = models.DateTimeField(auto_now_add=True)
    importado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )

    objects = InmutableQuerySet.as_manager()

    class Meta:
        verbose_name = "extracto bancario"
        verbose_name_plural = "extractos bancarios"
        ordering = ["comunidad", "-fecha_inicial"]
        constraints = [
            models.CheckConstraint(
                condition=Q(fecha_inicial__lte=F("fecha_final")), name="extracto_fechas_en_orden"
            ),
        ]

    def __str__(self) -> str:
        return f"Extracto {self.fecha_inicial} – {self.fecha_final} · {self.comunidad}"

    @property
    def cuenta_oculta(self) -> str:
        """Entidad y oficina a la vista; de la cuenta, solo las 4 últimas cifras."""
        return f"{self.entidad} {self.oficina} ****{self.cuenta[-4:]}"


class Movimiento(ModeloInmutable):
    """Un apunte del extracto (registro 22 con sus conceptos complementarios 23)."""

    extracto = models.ForeignKey(Extracto, on_delete=models.PROTECT, related_name="movimientos")
    orden = models.PositiveIntegerField()  # posición dentro del extracto, desde 1
    fecha_operacion = models.DateField("fecha de operación")
    fecha_valor = models.DateField("fecha valor")
    concepto_comun = models.CharField("concepto común", max_length=2)
    concepto_propio = models.CharField("concepto propio", max_length=3)
    # + abono (entra dinero en la cuenta de la comunidad), − cargo (sale).
    importe = models.DecimalField(max_digits=12, decimal_places=2)
    oficina_origen = models.CharField(max_length=4, blank=True)
    documento = models.CharField("nº de documento", max_length=10, blank=True)
    referencia_1 = models.CharField(max_length=12, blank=True)
    referencia_2 = models.CharField(max_length=16, blank=True)
    # Textos de los registros 23 (hasta 10), uno por línea.
    conceptos = models.TextField(blank=True)

    objects = InmutableQuerySet.as_manager()

    class Meta:
        verbose_name = "movimiento bancario"
        verbose_name_plural = "movimientos bancarios"
        ordering = ["extracto", "orden"]
        constraints = [
            models.UniqueConstraint(fields=["extracto", "orden"], name="movimiento_orden_unico"),
        ]

    def __str__(self) -> str:
        return f"{self.fecha_operacion} · {self.importe} €"

    @property
    def nombre_concepto(self) -> str:
        return nombre_concepto_comun(self.concepto_comun)

    @property
    def es_abono(self) -> bool:
        return self.importe > 0


# Camino desde cada modelo hasta su despacho (ver core.aislamiento y ADR 002).
CAMPO_DESPACHO = {
    Extracto: "comunidad__despacho",
    Movimiento: "extracto__comunidad__despacho",
}
