"""T5.1 — Dar acceso al portal a un propietario.

El administrador pulsa "Invitar al portal": se crea (o se reutiliza) un usuario con el email
del propietario como nombre de usuario y SIN contraseña, y se le envía un email con un enlace
para elegirla. El enlace es el de "restablecer contraseña" de Django: lleva un token firmado
que caduca (PASSWORD_RESET_TIMEOUT) y deja de valer en cuanto se usa. Así nadie (ni el
despacho) conoce la contraseña del vecino.
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.db import transaction
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from fincas.models import Propietario


class InvitacionInvalida(ValueError):
    """No se puede invitar a este propietario."""


def enlace_para_elegir_clave(usuario, base_url: str) -> str:
    uid = urlsafe_base64_encode(force_bytes(usuario.pk))
    token = default_token_generator.make_token(usuario)
    ruta = reverse("password_reset_confirm", kwargs={"uidb64": uid, "token": token})
    return base_url.rstrip("/") + ruta


@transaction.atomic
def invitar(propietario: Propietario, base_url: str):
    """Crea o enlaza el usuario del portal y le envía la invitación. Devuelve el usuario."""
    email = propietario.email.strip().lower()
    if not email:
        raise InvitacionInvalida(f"{propietario} no tiene email: añádelo antes de invitarle.")
    Usuario = get_user_model()
    usuario = propietario.usuario or Usuario.objects.filter(username=email).first()
    if usuario is None:
        usuario = Usuario(username=email, email=email, first_name=propietario.nombre[:150])
        usuario.set_unusable_password()  # la elige el vecino con el enlace
        usuario.save()
    elif usuario.despacho_id is not None or usuario.is_staff:
        # Un usuario de trabajo no se convierte en vecino por una invitación.
        raise InvitacionInvalida(
            f"Ya existe un usuario de despacho con el email de {propietario}: no se reutiliza."
        )
    propietario.usuario = usuario
    propietario.save(update_fields=["usuario"])

    texto = render_to_string(
        "portal/email_invitacion.txt",
        {
            "propietario": propietario,
            "usuario": usuario,
            "enlace": enlace_para_elegir_clave(usuario, base_url),
            "despacho": propietario.despacho,
        },
    )
    send_mail(
        "Tu acceso al portal de tu comunidad",
        texto,
        settings.DEFAULT_FROM_EMAIL,
        [email],
    )
    return usuario
