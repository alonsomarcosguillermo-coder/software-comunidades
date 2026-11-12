"""T5.1 — Invitar a un vecino al portal y que elija su contraseña con el enlace del email."""

import re

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core import mail
from django.urls import reverse

from fincas.models import Propietario
from portal.invitacion import InvitacionInvalida, invitar

pytestmark = pytest.mark.django_db

BASE = "http://testserver/"


def _enlace(mensaje) -> str:
    return re.search(r"http://testserver(/entrar/clave/\S+)", mensaje.body).group(1)


def _usuario(username, despacho, *permisos):
    usuario = get_user_model().objects.create_user(username=username, despacho=despacho)
    for codigo in permisos:
        app, codename = codigo.split(".")
        usuario.user_permissions.add(
            Permission.objects.get(content_type__app_label=app, codename=codename)
        )
    return usuario


# --- Servicio --------------------------------------------------------------------------------


def test_invitar_crea_un_usuario_sin_clave_y_envia_el_enlace(pablo, comunidad):
    usuario = invitar(pablo, BASE)
    pablo.refresh_from_db()
    assert pablo.usuario == usuario
    assert usuario.username == "pablo@example.com"
    assert not usuario.has_usable_password()  # la elige él
    assert usuario.despacho is None  # es vecino, no del despacho
    [mensaje] = mail.outbox
    assert mensaje.to == ["pablo@example.com"]
    assert "Fincas Alfa" in mensaje.body
    assert "/entrar/clave/" in mensaje.body


def test_con_el_enlace_elige_su_clave_y_entra_al_portal(client, pablo, comunidad):
    invitar(pablo, BASE)
    enlace = _enlace(mail.outbox[0])
    # Django redirige a una URL sin el token (para que no quede en el historial).
    formulario = client.get(enlace, follow=True)
    assert "Elige tu contraseña" in formulario.content.decode()
    respuesta = client.post(
        formulario.redirect_chain[-1][0],
        {"new_password1": "una-clave-larga-2026", "new_password2": "una-clave-larga-2026"},
    )
    assert respuesta["Location"] == reverse("password_reset_complete")
    client.post(
        reverse("login"), {"username": "pablo@example.com", "password": "una-clave-larga-2026"}
    )
    assert client.get(reverse("portal:recibos")).status_code == 200


def test_el_enlace_solo_sirve_una_vez(client, pablo, comunidad):
    invitar(pablo, BASE)
    enlace = _enlace(mail.outbox[0])
    formulario = client.get(enlace, follow=True)
    datos = {"new_password1": "una-clave-larga-2026", "new_password2": "una-clave-larga-2026"}
    client.post(formulario.redirect_chain[-1][0], datos)
    otra_vez = client.get(enlace, follow=True).content.decode()
    assert "ya se ha usado o ha caducado" in otra_vez


def test_sin_email_no_se_invita(pablo, comunidad):
    pablo.email = ""
    pablo.save()
    with pytest.raises(InvitacionInvalida, match="no tiene email"):
        invitar(pablo, BASE)


def test_no_convierte_en_vecino_a_un_usuario_del_despacho(pablo, comunidad, despacho_a):
    get_user_model().objects.create_user(username="pablo@example.com", despacho=despacho_a)
    with pytest.raises(InvitacionInvalida, match="usuario de despacho"):
        invitar(pablo, BASE)


def test_la_misma_persona_en_otro_despacho_reutiliza_su_usuario(pablo, comunidad, despacho_b):
    usuario = invitar(pablo, BASE)
    otra_ficha = Propietario.objects.create(
        despacho=despacho_b, nombre="Pablo Prueba", email="Pablo@Example.com"
    )
    assert invitar(otra_ficha, BASE) == usuario


def test_olvide_mi_clave(client, marta, comunidad):
    respuesta = client.post(reverse("password_reset"), {"email": "marta@example.com"})
    assert respuesta["Location"] == reverse("password_reset_done")
    [mensaje] = mail.outbox
    assert "/entrar/clave/" in mensaje.body
    assert mensaje.subject == "Elige tu contraseña de Comunidades"


# --- Página del despacho ----------------------------------------------------------------------


def _vecinos(comunidad):
    return reverse("portal:vecinos_comunidad", args=[comunidad.pk])


def _invitar(comunidad, propietario):
    return reverse("portal:invitar_vecino", args=[comunidad.pk, propietario.pk])


def test_pagina_de_vecinos(client, despacho_a, marta, pablo, comunidad):
    client.force_login(_usuario("ana", despacho_a, "core.add_usuario"))
    html = client.get(_vecinos(comunidad)).content.decode()
    assert "Marta Inventada" in html and "Tiene acceso" in html
    assert "Pablo Prueba" in html and "Invitar al portal" in html


def test_invitar_desde_la_web(client, despacho_a, pablo, comunidad):
    client.force_login(_usuario("ana", despacho_a, "core.add_usuario"))
    respuesta = client.post(_invitar(comunidad, pablo), follow=True)
    assert "Invitación enviada a Pablo Prueba" in respuesta.content.decode()
    assert len(mail.outbox) == 1


def test_sin_permiso_no_invita(client, despacho_a, pablo, comunidad):
    client.force_login(_usuario("emilio", despacho_a))
    assert client.post(_invitar(comunidad, pablo)).status_code == 403
    assert _invitar(comunidad, pablo) not in client.get(_vecinos(comunidad)).content.decode()
    assert not mail.outbox


def test_aislamiento_otro_despacho_no_ve_ni_invita(client, despacho_b, pablo, comunidad):
    client.force_login(_usuario("berta", despacho_b, "core.add_usuario"))
    assert client.get(_vecinos(comunidad)).status_code == 404
    assert client.post(_invitar(comunidad, pablo)).status_code == 404
    assert not mail.outbox


def test_solo_se_invita_a_titulares_de_esa_comunidad(client, despacho_a, comunidad, otra_comunidad):
    ajeno = otra_comunidad.inmuebles.get().titularidades.get().propietario
    client.force_login(_usuario("ana", despacho_a, "core.add_usuario"))
    assert client.post(_invitar(comunidad, ajeno)).status_code == 404


def test_enlace_desde_la_comunidad(client, despacho_a, comunidad):
    client.force_login(_usuario("ana", despacho_a))
    html = client.get(reverse("cobros:presupuestos_comunidad", args=[comunidad.pk]))
    assert _vecinos(comunidad) in html.content.decode()
