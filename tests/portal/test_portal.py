"""T5.1 — Portal del vecino: ve SOLO lo suyo (recibos, deuda, documentos de sus comunidades).

Regla del portal (ADR 016) y de CLAUDE.md: nadie ve datos que no le corresponden. Aquí, un
vecino no ve los de otro vecino ni los de otras comunidades; tampoco entra en las páginas del
despacho.
"""

from datetime import date, datetime

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from fincas.models import Titularidad
from juntas.celebracion import DatosAsistencia, cerrar_acta, iniciar_junta
from juntas.convocatoria import convocar
from juntas.models import Junta, PuntoOrden
from portal.consultas import comunidades_de, deuda_de, juntas_de, recibos_de

pytestmark = pytest.mark.django_db

HOY = timezone.localdate()


def _junta(comunidad, dia=date(2026, 3, 10)):
    junta = Junta.objects.create(
        comunidad=comunidad,
        tipo=Junta.Tipo.EXTRAORDINARIA,
        primera_convocatoria=timezone.make_aware(datetime(dia.year, dia.month, dia.day, 19)),
        lugar="el portal",
        convoca="El presidente",
    )
    PuntoOrden.objects.create(junta=junta, orden=1, titulo="Pintar la escalera")
    convocar(junta, date(2026, 3, 1))
    return junta


# --- Consultas -----------------------------------------------------------------------------


def test_solo_sus_recibos(marta, comunidad, otra_comunidad):
    recibos = list(recibos_de(marta.usuario))
    assert recibos and all(r.propietario == marta for r in recibos)


def test_su_deuda(marta, comunidad):
    deuda = deuda_de(marta.usuario, HOY)
    assert not deuda.al_corriente  # el recibo del 5/1/2026 sigue sin pagar
    assert deuda.total_vencido == sum(r.importe for r in recibos_de(marta.usuario))


def test_si_vende_deja_de_ver_la_comunidad_pero_no_sus_recibos(marta, comunidad):
    Titularidad.objects.filter(propietario=marta).update(fecha_fin=date(2026, 2, 1))
    assert not comunidades_de(marta.usuario, HOY).exists()
    assert not juntas_de(marta.usuario, HOY).exists()
    assert recibos_de(marta.usuario).exists()


def test_un_usuario_con_fichas_en_dos_despachos(marta, comunidad, otra_comunidad, despacho_b):
    from fincas.models import Propietario

    otra_ficha = Propietario.objects.create(
        despacho=despacho_b, nombre="Marta Inventada", usuario=marta.usuario
    )
    Titularidad.objects.create(
        inmueble=otra_comunidad.inmuebles.get(),
        propietario=otra_ficha,
        fecha_inicio=date(2025, 1, 1),
    )
    nombres = {c.nombre for c in comunidades_de(marta.usuario, HOY)}
    assert nombres == {"CP Calle Ficticia 1", "CP Avenida Inventada 2"}


# --- Entrar: cada uno a lo suyo ------------------------------------------------------------


def test_el_vecino_entra_a_su_portal(client, marta, comunidad):
    respuesta = client.post(
        reverse("login"), {"username": "marta@example.com", "password": "clave-de-prueba-123"}
    )
    assert respuesta["Location"] == reverse("inicio")
    assert client.get(reverse("inicio"))["Location"] == reverse("portal:inicio")


def test_el_despacho_entra_a_sus_comunidades(client, despacho_a):
    usuario = get_user_model().objects.create_user(username="ana", despacho=despacho_a)
    client.force_login(usuario)
    assert client.get(reverse("inicio"))["Location"] == reverse("fincas:lista_comunidades")


def test_menu_del_vecino(client, marta, comunidad):
    client.force_login(marta.usuario)
    html = client.get(reverse("portal:inicio")).content.decode()
    assert reverse("portal:inicio") in html
    assert reverse("fincas:lista_comunidades") not in html
    assert "no está asignado a ningún despacho" not in html


# --- Páginas del portal --------------------------------------------------------------------


def test_resumen(client, marta, comunidad):
    _junta(comunidad, dia=HOY.replace(year=HOY.year + 1))
    client.force_login(marta.usuario)
    html = client.get(reverse("portal:inicio")).content.decode()
    assert "CP Calle Ficticia 1" in html and "1A" in html
    assert "vencido" in html and "no podrás votar" in html  # R-VOT-01, en su lenguaje
    assert "Próximas juntas" in html and "Pintar" not in html  # el orden del día, dentro


def test_aislamiento_mis_recibos_no_muestra_los_de_otro_vecino(client, marta, pablo, comunidad):
    client.force_login(marta.usuario)
    html = client.get(reverse("portal:recibos")).content.decode()
    [propio] = comunidad.recibos.filter(propietario=marta)
    [ajeno] = comunidad.recibos.filter(propietario=pablo)
    assert propio.referencia in html
    assert ajeno.referencia not in html
    assert "Vencido, sin pagar" in html


def test_documentos_de_la_junta(client, marta, comunidad):
    junta = _junta(comunidad)
    client.force_login(marta.usuario)
    html = client.get(reverse("portal:juntas")).content.decode()
    assert reverse("portal:junta", args=[junta.pk]) in html
    detalle = client.get(reverse("portal:junta", args=[junta.pk])).content.decode()
    assert "1. Pintar la escalera" in detalle
    assert "El acta todavía no está disponible" in detalle


def test_el_acta_cerrada_se_ve(client, marta, pablo, comunidad):
    junta = _junta(comunidad)
    presente = DatosAsistencia("presente")
    celebracion = iniciar_junta(
        junta,
        inicio=junta.primera_convocatoria,
        presidente="El presidente",
        secretario="El administrador",
        asistencias={marta.pk: presente, pablo.pk: presente},  # quórum de primera
    )
    cerrar_acta(celebracion)
    client.force_login(marta.usuario)
    html = client.get(reverse("portal:junta", args=[junta.pk])).content.decode()
    assert "BORRADOR DEL ACTA" in html


# --- Aislamiento ---------------------------------------------------------------------------


def test_aislamiento_no_ve_juntas_de_otras_comunidades(client, marta, comunidad, otra_comunidad):
    ajena = _junta(otra_comunidad)
    client.force_login(marta.usuario)
    assert client.get(reverse("portal:junta", args=[ajena.pk])).status_code == 404
    assert (
        reverse("portal:junta", args=[ajena.pk])
        not in client.get(reverse("portal:juntas")).content.decode()
    )


def test_aislamiento_el_vecino_no_entra_en_las_paginas_del_despacho(client, marta, comunidad):
    client.force_login(marta.usuario)
    for url in [
        reverse("cobros:recibos_comunidad", args=[comunidad.pk]),
        reverse("cobros:morosos_comunidad", args=[comunidad.pk]),
        reverse("juntas:juntas_comunidad", args=[comunidad.pk]),
        reverse("portal:vecinos_comunidad", args=[comunidad.pk]),
    ]:
        assert client.get(url).status_code in (403, 404), url  # 403: además exige permiso


def test_sin_ficha_de_propietario_no_hay_portal(client, despacho_a):
    usuario = get_user_model().objects.create_user(username="ana", despacho=despacho_a)
    client.force_login(usuario)
    for nombre in ["inicio", "recibos", "juntas"]:
        assert client.get(reverse(f"portal:{nombre}")).status_code == 404


def test_sin_sesion_al_login(client, comunidad):
    assert client.get(reverse("portal:inicio")).status_code == 302
