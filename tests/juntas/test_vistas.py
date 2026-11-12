"""T4.1 — Páginas de juntas: lista, preparar/editar con orden del día, detalle y convocar.

Regla de CLAUDE.md: un usuario de otro despacho NO puede ver ni modificar los datos.
"""

from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core import mail
from django.urls import reverse
from django.utils import timezone

from juntas.convocatoria import convocar
from juntas.models import Junta

pytestmark = pytest.mark.django_db

PERMISOS = ("add_junta", "change_junta", "add_citacion")


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


def _lista(comunidad):
    return reverse("juntas:juntas_comunidad", args=[comunidad.pk])


def _nueva(comunidad):
    return reverse("juntas:nueva_junta", args=[comunidad.pk])


def _detalle(junta):
    return reverse("juntas:detalle_junta", args=[junta.comunidad_id, junta.pk])


def _editar(junta):
    return reverse("juntas:editar_junta", args=[junta.comunidad_id, junta.pk])


def _convocar(junta):
    return reverse("juntas:convocar_junta", args=[junta.comunidad_id, junta.pk])


def _datos(**extra):
    datos = {
        "tipo": "ordinaria",
        "primera_convocatoria": "2026-03-10T19:00",
        "segunda_convocatoria": "2026-03-10T19:30",
        "lugar": "el portal",
        "convoca": "La presidenta, Ana",
        "puntos-TOTAL_FORMS": "3",
        "puntos-INITIAL_FORMS": "0",
        "puntos-MIN_NUM_FORMS": "0",
        "puntos-MAX_NUM_FORMS": "1000",
        "puntos-0-titulo": "Cuentas de 2025",
        "puntos-0-mayoria": "simple",
        "puntos-1-titulo": "Cambiar los estatutos",
        "puntos-1-mayoria": "unanimidad",
        "puntos-1-excepcion_ausentes": "on",
        "puntos-2-mayoria": "simple",  # fila vacía: se ignora
    }
    return datos | extra


# --- Lista ---------------------------------------------------------------------------------


def test_lista(client, ana, junta):
    client.force_login(ana)
    html = client.get(_lista(junta.comunidad)).content.decode()
    assert _detalle(junta) in html
    assert "Borrador" in html
    assert _nueva(junta.comunidad) in html


def test_aislamiento_otro_despacho_no_ve_la_lista(client, berta, junta):
    client.force_login(berta)
    assert client.get(_lista(junta.comunidad)).status_code == 404


def test_enlace_desde_la_comunidad(client, ana, comunidad):
    client.force_login(ana)
    html = client.get(reverse("cobros:presupuestos_comunidad", args=[comunidad.pk]))
    assert _lista(comunidad) in html.content.decode()


# --- Preparar y editar ---------------------------------------------------------------------


def test_prepara_una_junta_con_su_orden_del_dia(client, ana, comunidad):
    client.force_login(ana)
    respuesta = client.post(_nueva(comunidad), _datos())
    junta = Junta.objects.get()
    assert respuesta.status_code == 302 and respuesta["Location"] == _detalle(junta)
    assert junta.comunidad == comunidad
    assert timezone.localtime(junta.primera_convocatoria).hour == 19
    puntos = list(junta.puntos.all())
    assert [(p.orden, p.titulo, p.mayoria) for p in puntos] == [
        (1, "Cuentas de 2025", "simple"),
        (2, "Cambiar los estatutos", "unanimidad"),
    ]
    assert puntos[0].computa_ausentes and not puntos[1].computa_ausentes


def test_formulario_con_errores_se_vuelve_a_mostrar(client, ana, comunidad):
    client.force_login(ana)
    respuesta = client.post(_nueva(comunidad), _datos(lugar=""))
    assert respuesta.status_code == 200
    assert not Junta.objects.exists()


def test_editar_rehace_el_orden_del_dia(client, ana, junta):
    client.force_login(ana)
    get = client.get(_editar(junta)).content.decode()
    assert "Aprobación de las cuentas de 2025" in get  # puntos actuales precargados
    client.post(_editar(junta), _datos(**{"puntos-0-titulo": "Solo este punto"}))
    assert [p.titulo for p in junta.puntos.all()] == ["Solo este punto", "Cambiar los estatutos"]


def test_una_junta_convocada_no_se_edita(client, ana, junta):
    convocar(junta, date(2026, 3, 1))
    client.force_login(ana)
    assert client.get(_editar(junta)).status_code == 302
    client.post(_editar(junta), _datos(lugar="otro"))
    junta.refresh_from_db()
    assert junta.lugar == "el portal del edificio"


def test_sin_permiso_no_prepara(client, despacho_a, comunidad):
    client.force_login(_usuario("emilio", despacho_a))
    assert client.get(_nueva(comunidad)).status_code == 403
    assert client.post(_nueva(comunidad), _datos()).status_code == 403
    assert not Junta.objects.exists()


def test_aislamiento_otro_despacho_no_prepara_ni_edita(client, berta, junta):
    client.force_login(berta)
    assert client.post(_nueva(junta.comunidad), _datos()).status_code == 404
    assert client.get(_editar(junta)).status_code == 404
    assert client.post(_editar(junta), _datos(lugar="hackeado")).status_code == 404
    junta.refresh_from_db()
    assert junta.lugar == "el portal del edificio"


# --- Detalle y convocar --------------------------------------------------------------------


def test_detalle_en_borrador_con_vista_previa(client, ana, junta):
    client.force_login(ana)
    html = client.get(_detalle(junta)).content.decode()
    assert "Vista previa de la convocatoria" in html
    assert "1. Aprobación de las cuentas de 2025" in html
    assert _convocar(junta) in html


def test_convocar_desde_la_web(client, ana, junta):
    client.force_login(ana)
    respuesta = client.post(_convocar(junta), {"citacion": "2026-03-01"}, follow=True)
    assert respuesta.redirect_chain == [(_detalle(junta), 302)]
    html = respuesta.content.decode()
    assert "Junta convocada: 3 emails enviados" in html
    assert "cítalos por otro medio" in html and "Luis" in html
    assert len(mail.outbox) == 3
    assert "Convocatoria enviada" in html


def test_convocar_fuera_de_plazo_muestra_el_motivo(client, ana, junta):
    client.force_login(ana)
    html = client.post(_convocar(junta), {"citacion": "2026-03-05"}, follow=True)
    assert "R-JUN-02" in html.content.decode()
    assert not mail.outbox


def test_sin_permiso_no_convoca(client, despacho_a, junta):
    client.force_login(_usuario("emilio", despacho_a))
    assert client.post(_convocar(junta), {"citacion": "2026-03-01"}).status_code == 403
    assert "Convocar y enviar" not in client.get(_detalle(junta)).content.decode()
    assert not mail.outbox


def test_aislamiento_otro_despacho_no_ve_ni_convoca(client, berta, junta):
    client.force_login(berta)
    assert client.get(_detalle(junta)).status_code == 404
    assert client.post(_convocar(junta), {"citacion": "2026-03-01"}).status_code == 404
    assert not mail.outbox


def test_junta_con_otra_comunidad_en_la_url(client, ana, junta, despacho_a):
    from fincas.models import Comunidad

    otra = Comunidad.objects.create(despacho=despacho_a, nombre="CP Plaza Imaginaria 7")
    client.force_login(ana)
    url = reverse("juntas:detalle_junta", args=[otra.pk, junta.pk])
    assert client.get(url).status_code == 404
