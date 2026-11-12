"""T4.3 — Páginas de la celebración y del acta.

Regla de CLAUDE.md: un usuario de otro despacho NO puede ver ni modificar los datos.
"""

from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.urls import reverse

from juntas.celebracion import DatosAsistencia, cerrar_acta, iniciar_junta, votantes_de
from juntas.convocatoria import convocar
from juntas.models import Celebracion, VotoEmitido

from .conftest import aware

pytestmark = pytest.mark.django_db

PERMISOS = ("add_celebracion", "change_celebracion", "add_votoemitido")


def _usuario(username, despacho, *permisos):
    usuario = get_user_model().objects.create_user(username=username, despacho=despacho)
    for codename in permisos:
        usuario.user_permissions.add(
            Permission.objects.get(content_type__app_label="juntas", codename=codename)
        )
    return usuario


@pytest.fixture
def ana(despacho_a):
    return _usuario("ana", despacho_a, *PERMISOS)


@pytest.fixture
def berta(despacho_b):
    return _usuario("berta", despacho_b, *PERMISOS)


@pytest.fixture
def convocada(junta):
    convocar(junta, date(2026, 3, 1))
    return junta


def _ids(junta):
    return {p.nombre: p.pk for p, _ in votantes_de(junta, date(2026, 3, 10))}


@pytest.fixture
def iniciada(convocada):
    ids = _ids(convocada)
    presente = DatosAsistencia("presente")
    return iniciar_junta(
        convocada,
        inicio=aware(2026, 3, 10, 19, 5),
        presidente="Ana",
        secretario="El administrador",
        asistencias={ids["Ana"]: presente, ids["Luis"]: presente},
    )


def _url(nombre, junta, *extra):
    return reverse(f"juntas:{nombre}", args=[junta.comunidad_id, junta.pk, *extra])


def test_formulario_de_asistencia(client, ana, convocada):
    client.force_login(ana)
    html = client.get(_url("celebracion", convocada)).content.decode()
    assert "Iniciar la junta" in html
    for nombre in ("Ana", "Benito", "Luis"):
        assert nombre in html


def test_sin_convocar_redirige_al_detalle(client, ana, junta):
    client.force_login(ana)
    assert client.get(_url("celebracion", junta)).status_code == 302


def test_iniciar_desde_la_web(client, ana, convocada):
    ids = _ids(convocada)
    client.force_login(ana)
    respuesta = client.post(
        _url("iniciar_junta", convocada),
        {
            "presidente": "Ana",
            "secretario": "El administrador",
            "inicio": "2026-03-10T19:05",
            f"asistencia-{ids['Ana']}": "presente",
            f"asistencia-{ids['Luis']}": "representado",
            f"representante-{ids['Luis']}": "Su hija, Lucía",
        },
        follow=True,
    )
    assert "Junta iniciada en primera convocatoria" in respuesta.content.decode()
    celebracion = Celebracion.objects.get()
    assert celebracion.asistentes.get(propietario_id=ids["Luis"]).representante == "Su hija, Lucía"


def test_iniciar_sin_quorum_muestra_el_motivo(client, ana, convocada):
    client.force_login(ana)
    html = client.post(
        _url("iniciar_junta", convocada),
        {"presidente": "Ana", "secretario": "S", "inicio": "2026-03-10T19:05"},
        follow=True,
    ).content.decode()
    assert "R-JUN-03" in html
    assert not Celebracion.objects.exists()


def test_votar_y_ver_el_resultado(client, ana, convocada, iniciada):
    punto = convocada.puntos.get(orden=1)
    asistentes = {a.propietario.nombre: a.pk for a in iniciada.asistentes.all()}
    client.force_login(ana)
    html = client.post(
        _url("votar_punto", convocada, punto.pk),
        {f"voto-{asistentes['Ana']}": "favor", f"voto-{asistentes['Luis']}": "favor"},
        follow=True,
    ).content.decode()
    assert "Votos del punto 1 guardados" in html
    assert "Aprobado" in html
    assert VotoEmitido.objects.filter(punto=punto).count() == 2


def test_cerrar_el_acta_y_notificar(client, ana, convocada, iniciada):
    client.force_login(ana)
    assert (
        "Acta cerrada" in client.post(_url("cerrar_acta", convocada), follow=True).content.decode()
    )
    html = client.post(
        _url("notificar_ausentes", convocada), {"fecha": "2026-03-15"}, follow=True
    ).content.decode()
    assert "30 días para discrepar" in html
    iniciada.refresh_from_db()
    assert iniciada.ausentes_notificados_el == date(2026, 3, 15)


def test_con_el_acta_cerrada_no_se_vota(client, ana, convocada, iniciada):
    cerrar_acta(iniciada)
    punto = convocada.puntos.get(orden=1)
    ana_asistente = iniciada.asistentes.get(propietario__nombre="Ana")
    client.force_login(ana)
    html = client.post(
        _url("votar_punto", convocada, punto.pk), {f"voto-{ana_asistente.pk}": "favor"}, follow=True
    ).content.decode()
    assert "acta está cerrada" in html
    assert not VotoEmitido.objects.exists()


def test_registrar_discrepancia_desde_la_web(client, ana, convocada, iniciada):
    from juntas.celebracion import notificar_ausentes

    cerrar_acta(iniciada)
    notificar_ausentes(iniciada, date(2026, 3, 15))
    benito = iniciada.asistentes.get(propietario__nombre="Benito")
    punto = convocada.puntos.get(orden=1)
    client.force_login(ana)
    html = client.post(
        _url("registrar_discrepancia", convocada, punto.pk),
        {"asistente": benito.pk, "fecha": "2026-03-20"},
        follow=True,
    ).content.decode()
    assert "Discrepancia de Benito registrada" in html


def test_acta_en_pagina_y_descarga(client, ana, convocada, iniciada):
    client.force_login(ana)
    html = client.get(_url("acta_junta", convocada)).content.decode()
    assert "BORRADOR DEL ACTA" in html
    descarga = client.get(_url("acta_junta", convocada) + "?descargar=1")
    assert descarga["Content-Type"] == "text/plain; charset=utf-8"
    assert descarga["Content-Disposition"].startswith("attachment;")
    assert "BORRADOR DEL ACTA" in descarga.content.decode()


def test_enlace_desde_el_detalle_de_la_junta(client, ana, convocada):
    client.force_login(ana)
    html = client.get(_url("detalle_junta", convocada)).content.decode()
    assert _url("celebracion", convocada) in html


def test_sin_permisos_ve_pero_no_actua(client, despacho_a, convocada, iniciada):
    client.force_login(_usuario("emilio", despacho_a))
    html = client.get(_url("celebracion", convocada)).content.decode()
    assert "Guardar los votos" not in html and "Cerrar el acta" not in html
    punto = convocada.puntos.get(orden=1)
    assert client.post(_url("votar_punto", convocada, punto.pk), {}).status_code == 403
    assert client.post(_url("cerrar_acta", convocada)).status_code == 403
    assert client.post(_url("iniciar_junta", convocada), {}).status_code == 403


@pytest.mark.parametrize(
    ("nombre", "extra"),
    [
        ("celebracion", ()),
        ("acta_junta", ()),
    ],
)
def test_aislamiento_otro_despacho_no_ve(client, berta, convocada, iniciada, nombre, extra):
    client.force_login(berta)
    assert client.get(_url(nombre, convocada, *extra)).status_code == 404


def test_aislamiento_otro_despacho_no_actua(client, berta, convocada, iniciada):
    client.force_login(berta)
    punto = convocada.puntos.get(orden=1)
    ana_asistente = iniciada.asistentes.get(propietario__nombre="Ana")
    for url, datos in [
        (_url("votar_punto", convocada, punto.pk), {f"voto-{ana_asistente.pk}": "favor"}),
        (_url("cerrar_acta", convocada), {}),
        (_url("notificar_ausentes", convocada), {"fecha": "2026-03-15"}),
        (_url("cambiar_impugnacion", convocada, ana_asistente.pk), {"impugnada": "1"}),
        (_url("registrar_discrepancia", convocada, punto.pk), {"fecha": "2026-03-20"}),
        (_url("iniciar_junta", convocada), {"presidente": "x", "secretario": "y"}),
    ]:
        assert client.post(url, datos).status_code == 404, url
    iniciada.refresh_from_db()
    assert not iniciada.esta_cerrada
    assert not VotoEmitido.objects.exists()
