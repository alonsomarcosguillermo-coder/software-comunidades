from django.contrib.auth.models import AbstractUser
from django.db import models


class Despacho(models.Model):
    """Despacho de administración de fincas: la unidad de aislamiento del sistema.

    Todo dato de negocio (comunidades, contabilidad, recibos...) cuelga, directa o
    indirectamente, de un despacho. Un despacho nunca ve datos de otro (ver
    `core/aislamiento.py` y ADR 002).
    """

    nombre = models.CharField(max_length=200)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "despacho"
        verbose_name_plural = "despachos"
        ordering = ["nombre"]

    def __str__(self) -> str:
        return self.nombre


class Usuario(AbstractUser):
    """Usuario del sistema (administrador de fincas, empleado del despacho o vecino).

    Existe desde el principio porque cambiar AUTH_USER_MODEL después de la primera
    migración es muy costoso.
    """

    # Opcional porque hay usuarios sin despacho: el superusuario técnico y, en la
    # Fase 5, los vecinos del portal. Un usuario sin despacho no ve nada en las
    # vistas del despacho (ver core/aislamiento.py).
    # PROTECT: no se puede borrar un despacho que aún tiene usuarios.
    despacho = models.ForeignKey(
        Despacho,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="usuarios",
    )

    class Meta:
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"

    def __str__(self) -> str:
        return self.get_username()
