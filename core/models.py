from django.contrib.auth.models import AbstractUser


class Usuario(AbstractUser):
    """Usuario del sistema (administrador de fincas, empleado del despacho o vecino).

    De momento es idéntico al usuario estándar de Django. Existe desde el principio
    porque cambiar AUTH_USER_MODEL después de la primera migración es muy costoso.
    La relación con Despacho y los roles se añaden en la Fase 1 (ver docs/PLAN.md).
    """

    class Meta:
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"

    def __str__(self) -> str:
        return self.get_username()
