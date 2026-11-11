from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator
from django.db import models
from django.db.models import Q, Sum

from cobros.sepa.identificadores import IbanInvalido, identificador_acreedor, validar_iban
from core.models import Despacho

from .servicios import (
    SUMA_COEFICIENTES,
    CoeficientesInvalidos,
    coeficientes_de_grupo,
    comprobar_coeficientes,
)


def validar_mayor_que_cero(valor: Decimal) -> None:
    if valor is not None and valor <= 0:
        raise ValidationError("Debe ser mayor que 0.", code="no_positivo")


def validar_campo_iban(valor: str) -> None:
    """Validador de formularios: IBAN con dígitos de control correctos."""
    if valor:
        try:
            validar_iban(valor)
        except IbanInvalido as error:
            raise ValidationError(str(error), code="iban_invalido") from error


class Comunidad(models.Model):
    """Comunidad de propietarios. Pertenece a un despacho (ver ADR 002)."""

    despacho = models.ForeignKey(Despacho, on_delete=models.PROTECT, related_name="comunidades")
    nombre = models.CharField(max_length=200)
    nif = models.CharField("NIF", max_length=9, blank=True)
    direccion = models.CharField("dirección", max_length=300, blank=True)
    # T2.4 — Cobros SEPA. Cuenta en la que la comunidad recibe los adeudos domiciliados.
    iban_cobros = models.CharField(
        "IBAN de cobro", max_length=34, blank=True, validators=[validar_campo_iban]
    )
    # Parte del identificador de acreedor SEPA (AT-02); "000" salvo que el banco diga otra cosa.
    sufijo_acreedor = models.CharField("sufijo de acreedor SEPA", max_length=3, default="000")

    class Meta:
        verbose_name = "comunidad"
        verbose_name_plural = "comunidades"
        ordering = ["nombre"]

    def __str__(self) -> str:
        return self.nombre

    def save(self, *args, **kwargs):
        self.iban_cobros = "".join(self.iban_cobros.split()).upper()
        super().save(*args, **kwargs)

    def identificador_acreedor(self) -> str:
        """Identificador de acreedor SEPA (AT-02), calculado a partir del NIF. Sin NIF: ""."""
        if not self.nif:
            return ""
        return identificador_acreedor(self.nif, sufijo=self.sufijo_acreedor)

    def suma_coeficientes(self) -> Decimal:
        return self.inmuebles.aggregate(suma=Sum("coeficiente"))["suma"] or Decimal("0")

    def coeficientes_cuadran(self) -> bool:
        """R-COEF-01: ¿los coeficientes de sus inmuebles suman exactamente 100 %?"""
        try:
            comprobar_coeficientes(self.inmuebles.values_list("coeficiente", flat=True))
        except CoeficientesInvalidos:
            return False
        return True


class Inmueble(models.Model):
    """Elemento privativo de una comunidad: piso, local, garaje o trastero."""

    class Tipo(models.TextChoices):
        PISO = "piso", "Piso"
        LOCAL = "local", "Local"
        GARAJE = "garaje", "Garaje"
        TRASTERO = "trastero", "Trastero"

    comunidad = models.ForeignKey(Comunidad, on_delete=models.PROTECT, related_name="inmuebles")
    tipo = models.CharField(max_length=10, choices=Tipo.choices)
    # Cómo se le conoce dentro de la comunidad: "1ºA", "Local 2", "Plaza 14"...
    referencia = models.CharField(max_length=50)
    # R-COEF-01: cuota de participación en %, con 4 decimales (p. ej. 3,4567 %), que es la
    # precisión habitual en los títulos constitutivos. La suma de la comunidad (= 100) no se
    # puede comprobar inmueble a inmueble; se comprueba en bloque (ver fincas/admin.py).
    coeficiente = models.DecimalField(
        "coeficiente (%)",
        max_digits=7,
        decimal_places=4,
        validators=[validar_mayor_que_cero, MaxValueValidator(SUMA_COEFICIENTES)],
    )

    class Meta:
        verbose_name = "inmueble"
        verbose_name_plural = "inmuebles"
        ordering = ["comunidad", "referencia"]
        constraints = [
            models.UniqueConstraint(
                fields=["comunidad", "referencia"], name="inmueble_referencia_unica_en_comunidad"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.comunidad} · {self.referencia}"

    def propietarios_en(self, fecha: date):
        """Propietarios con titularidad vigente en `fecha`."""
        return Propietario.objects.filter(
            titularidades__in=Titularidad.objects.vigentes(fecha).filter(inmueble=self)
        ).distinct()


class Propietario(models.Model):
    """Persona física o jurídica propietaria de inmuebles en comunidades del despacho.

    Cuelga del despacho (no de una comunidad) porque una misma persona puede tener
    inmuebles en varias comunidades del mismo despacho.
    """

    despacho = models.ForeignKey(Despacho, on_delete=models.PROTECT, related_name="propietarios")
    # Nombre completo o razón social.
    nombre = models.CharField(max_length=200)
    # Datos personales: nunca en logs. En tests, solo NIF ficticios.
    nif = models.CharField("NIF/NIE", max_length=9, blank=True)
    email = models.EmailField(blank=True)
    telefono = models.CharField("teléfono", max_length=20, blank=True)

    class Meta:
        verbose_name = "propietario"
        verbose_name_plural = "propietarios"
        ordering = ["nombre"]
        constraints = [
            # Sin NIF puede haber varios (aún no se conoce); con NIF, uno por despacho.
            models.UniqueConstraint(
                fields=["despacho", "nif"],
                condition=~Q(nif=""),
                name="propietario_nif_unico_en_despacho",
            ),
        ]

    def __str__(self) -> str:
        # Sin NIF ni email a propósito: __str__ acaba en logs, mensajes y desplegables.
        return self.nombre


class TitularidadQuerySet(models.QuerySet):
    def vigentes(self, fecha: date):
        return self.filter(fecha_inicio__lte=fecha).filter(
            Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=fecha)
        )


class Titularidad(models.Model):
    """Un propietario es titular de un inmueble durante un periodo.

    Se guarda el histórico (en vez de un simple "propietario actual") porque las deudas y
    los votos dependen de quién era el dueño en cada fecha. Puede haber varios cotitulares
    a la vez. `fecha_fin` vacía = titularidad vigente.
    """

    inmueble = models.ForeignKey(Inmueble, on_delete=models.PROTECT, related_name="titularidades")
    propietario = models.ForeignKey(
        Propietario, on_delete=models.PROTECT, related_name="titularidades"
    )
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField(null=True, blank=True)

    objects = TitularidadQuerySet.as_manager()

    class Meta:
        verbose_name = "titularidad"
        verbose_name_plural = "titularidades"
        ordering = ["inmueble", "fecha_inicio"]
        constraints = [
            models.CheckConstraint(
                condition=Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=models.F("fecha_inicio")),
                name="titularidad_fin_posterior_al_inicio",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.propietario} → {self.inmueble}"

    def clean(self) -> None:
        if self.fecha_fin and self.fecha_inicio and self.fecha_fin < self.fecha_inicio:
            raise ValidationError(
                {"fecha_fin": "La fecha de fin no puede ser anterior a la de inicio."}
            )
        if self.inmueble_id is None or self.propietario_id is None or self.fecha_inicio is None:
            return  # los errores de campos obligatorios ya los da Django
        # Aislamiento (ADR 002): propietario e inmueble deben ser del mismo despacho.
        if self.propietario.despacho_id != self.inmueble.comunidad.despacho_id:
            raise ValidationError("El propietario y el inmueble pertenecen a despachos distintos.")
        # El mismo propietario no puede tener dos titularidades solapadas del mismo inmueble.
        solapadas = Titularidad.objects.filter(
            inmueble_id=self.inmueble_id, propietario_id=self.propietario_id
        ).exclude(pk=self.pk)
        if self.fecha_fin:
            solapadas = solapadas.filter(fecha_inicio__lte=self.fecha_fin)
        solapadas = solapadas.filter(
            Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=self.fecha_inicio)
        )
        if solapadas.exists():
            raise ValidationError(
                "Este propietario ya tiene una titularidad de este inmueble que se solapa "
                "con estas fechas."
            )


class GrupoReparto(models.Model):
    """R-REP-01: conjunto de inmuebles que comparten ciertos gastos (p. ej. "Ascensor", sin
    los locales), con los coeficientes generales de sus inmuebles o con unos propios.

    Lo usan las derramas (T2.3) para repartir solo entre esos inmuebles.
    """

    comunidad = models.ForeignKey(
        Comunidad, on_delete=models.PROTECT, related_name="grupos_reparto"
    )
    nombre = models.CharField(max_length=100)

    class Meta:
        verbose_name = "grupo de reparto"
        verbose_name_plural = "grupos de reparto"
        ordering = ["comunidad", "nombre"]
        constraints = [
            models.UniqueConstraint(
                fields=["comunidad", "nombre"], name="grupo_reparto_nombre_unico_en_comunidad"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.comunidad} · {self.nombre}"

    def coeficientes(self) -> dict[int, Decimal]:
        """R-REP-01: {id del inmueble: coeficiente con el que reparte este grupo}.

        Lanza `fincas.servicios.GrupoInvalido` si el grupo no sirve para repartir.
        """
        return coeficientes_de_grupo(
            (miembro.inmueble_id, miembro.inmueble.coeficiente, miembro.coeficiente)
            for miembro in self.miembros.select_related("inmueble")
        )


class MiembroGrupo(models.Model):
    """Un inmueble dentro de un grupo de reparto."""

    grupo = models.ForeignKey(GrupoReparto, on_delete=models.CASCADE, related_name="miembros")
    inmueble = models.ForeignKey(Inmueble, on_delete=models.PROTECT, related_name="grupos_reparto")
    # R-REP-01: vacío = se usa el coeficiente general del inmueble. Si se rellena, debe
    # rellenarse en todos los inmuebles del grupo (ver `coeficientes_de_grupo`).
    coeficiente = models.DecimalField(
        "coeficiente propio (%)",
        max_digits=7,
        decimal_places=4,
        null=True,
        blank=True,
        validators=[validar_mayor_que_cero, MaxValueValidator(SUMA_COEFICIENTES)],
        help_text="Vacío: el coeficiente general del inmueble.",
    )

    class Meta:
        verbose_name = "inmueble del grupo"
        verbose_name_plural = "inmuebles del grupo"
        ordering = ["grupo", "inmueble__referencia"]
        constraints = [
            models.UniqueConstraint(fields=["grupo", "inmueble"], name="miembro_grupo_unico"),
            models.CheckConstraint(
                condition=Q(coeficiente__isnull=True) | Q(coeficiente__gt=0),
                name="miembro_grupo_coeficiente_positivo",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.grupo.nombre} · {self.inmueble.referencia}"

    def clean(self) -> None:
        # En el admin, al crear un grupo junto con sus inmuebles, el grupo ya está asignado
        # pero aún no tiene id: por eso se mira también si está en memoria.
        tiene_grupo = self.grupo_id is not None or MiembroGrupo.grupo.is_cached(self)
        if not tiene_grupo or self.inmueble_id is None:
            return  # los errores de campos obligatorios ya los da Django
        if self.inmueble.comunidad_id != self.grupo.comunidad_id:
            raise ValidationError({"inmueble": "El inmueble es de otra comunidad que el grupo."})


# Camino desde cada modelo hasta su despacho, para `core.aislamiento.filtrar_por_despacho`
# y `FiltradoPorDespachoMixin.campo_despacho`.
CAMPO_DESPACHO = {
    Comunidad: "despacho",
    Inmueble: "comunidad__despacho",
    Propietario: "despacho",
    Titularidad: "inmueble__comunidad__despacho",
    GrupoReparto: "comunidad__despacho",
    MiembroGrupo: "grupo__comunidad__despacho",
}
