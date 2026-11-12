"""T5.2 — Discrepancia online del ausente (R-MAY-05, art. 17.8 LPH).

No hay voto a distancia (R-JUN-04: la LPH no lo regula). Lo que sí se puede hacer desde el
portal es que un ausente, notificado de los acuerdos, diga en 30 días naturales que no está de
acuerdo, con constancia de la recepción (fecha, hora y acuse por email).

Escenario: Marta y Pablo (50 % cada uno). Junta en 2ª convocatoria (sin quórum en 1ª) con un
acuerdo de unanimidad: Pablo asiste y vota a favor; Marta no asiste.
"""

from datetime import date, datetime, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.urls import reverse
from django.utils import timezone

from juntas.celebracion import (
    DatosAsistencia,
    cambiar_impugnacion,
    cerrar_acta,
    iniciar_junta,
    notificar_ausentes,
    registrar_votos,
    resultado,
)
from juntas.convocatoria import convocar
from juntas.models import Discrepancia, Junta, PuntoOrden
from portal.discrepancias import discrepar_online

pytestmark = pytest.mark.django_db

NOTIFICADOS = date(2026, 3, 15)


def _aware(*args):
    return timezone.make_aware(datetime(*args))


@pytest.fixture
def celebrada(comunidad, marta, pablo):
    junta = Junta.objects.create(
        comunidad=comunidad,
        tipo=Junta.Tipo.EXTRAORDINARIA,
        primera_convocatoria=_aware(2026, 3, 10, 19, 0),
        segunda_convocatoria=_aware(2026, 3, 10, 19, 30),
        lugar="el portal",
        convoca="El presidente",
    )
    PuntoOrden.objects.create(
        junta=junta, orden=1, titulo="Cambiar los estatutos", mayoria=PuntoOrden.Mayoria.UNANIMIDAD
    )
    PuntoOrden.objects.create(
        junta=junta,
        orden=2,
        titulo="Servicio de conserjería",
        mayoria=PuntoOrden.Mayoria.TRES_QUINTOS,
        computa_ausentes=False,  # excepción del art. 17.8
    )
    convocar(junta, date(2026, 3, 1))
    celebracion = iniciar_junta(
        junta,
        inicio=_aware(2026, 3, 10, 19, 30),
        presidente="Pablo",
        secretario="El administrador",
        asistencias={pablo.pk: DatosAsistencia("presente")},
    )
    pablo_asistente = celebracion.asistentes.get(propietario=pablo)
    # El fixture deja a todos con el recibo de enero sin pagar (R-VOT-01). Pablo acredita
    # que lo ha consignado, así que vota: aquí interesa la discrepancia de Marta.
    cambiar_impugnacion(pablo_asistente, True)
    # Marta también: si estuviera privada de voto, su cuota no contaría (R-VOT-01) y su
    # discrepancia no cambiaría nada.
    cambiar_impugnacion(celebracion.asistentes.get(propietario=marta), True)
    for punto in junta.puntos.all():
        registrar_votos(punto, {pablo_asistente.pk: "favor"})
    cerrar_acta(celebracion)
    mail.outbox.clear()  # los emails de la convocatoria no interesan aquí
    return junta


@pytest.fixture
def notificada(celebrada):
    notificar_ausentes(celebrada.celebracion, NOTIFICADOS)
    return celebrada


def _en(dia):
    return _aware(dia.year, dia.month, dia.day, 10, 0)


def _url_junta(junta):
    return reverse("portal:junta", args=[junta.pk])


def _url_discrepar(junta, punto):
    return reverse("portal:discrepar", args=[junta.pk, punto.pk])


# --- Servicio --------------------------------------------------------------------------------


def test_r_may_05_la_discrepancia_online_impide_contar_al_ausente_a_favor(marta, notificada):
    punto = notificada.puntos.get(orden=1)
    despues_del_plazo = NOTIFICADOS + timedelta(days=31)
    assert resultado(punto, despues_del_plazo).aprobado  # sin discrepancia: unanimidad

    discrepancia = discrepar_online(
        marta.usuario, punto, ahora=_en(NOTIFICADOS + timedelta(days=3))
    )

    assert discrepancia.canal == Discrepancia.Canal.PORTAL
    assert discrepancia.recibida_en == _en(NOTIFICADOS + timedelta(days=3))
    assert discrepancia.fecha == NOTIFICADOS + timedelta(days=3)
    assert not resultado(punto, despues_del_plazo).aprobado


def test_constancia_de_recepcion_acuse_por_email(marta, notificada):
    discrepar_online(marta.usuario, notificada.puntos.get(orden=1), ahora=_en(date(2026, 3, 20)))
    [acuse] = mail.outbox
    assert acuse.to == ["marta@example.com"]
    assert "1. Cambiar los estatutos" in acuse.body
    assert "20/3/2026 a las 10:00" in acuse.body
    assert "justificante" in acuse.body


def test_r_may_05_fuera_de_plazo_no(marta, notificada):
    from juntas.celebracion import CelebracionInvalida

    with pytest.raises(CelebracionInvalida, match="30 días"):
        discrepar_online(
            marta.usuario,
            notificada.puntos.get(orden=1),
            ahora=_en(NOTIFICADOS + timedelta(days=31)),
        )
    assert not mail.outbox


def test_antes_de_notificar_no(marta, celebrada):
    from juntas.celebracion import CelebracionInvalida

    with pytest.raises(CelebracionInvalida, match="notificar"):
        discrepar_online(marta.usuario, celebrada.puntos.get(orden=1), ahora=_en(NOTIFICADOS))


def test_quien_asistio_no_discrepa_despues(pablo, notificada):
    from juntas.celebracion import CelebracionInvalida

    pablo.usuario = get_user_model().objects.create_user(username="pablo@example.com")
    pablo.save()
    with pytest.raises(CelebracionInvalida, match="no asistió"):
        discrepar_online(pablo.usuario, notificada.puntos.get(orden=1), ahora=_en(NOTIFICADOS))


def test_en_las_excepciones_del_17_8_no_se_discrepa(marta, notificada):
    from juntas.celebracion import CelebracionInvalida

    with pytest.raises(CelebracionInvalida, match="no cuenta"):
        discrepar_online(marta.usuario, notificada.puntos.get(orden=2), ahora=_en(NOTIFICADOS))


def test_no_se_discrepa_dos_veces(marta, notificada):
    from juntas.celebracion import CelebracionInvalida

    punto = notificada.puntos.get(orden=1)
    discrepar_online(marta.usuario, punto, ahora=_en(NOTIFICADOS))
    with pytest.raises(CelebracionInvalida, match="ya está registrada"):
        discrepar_online(marta.usuario, punto, ahora=_en(NOTIFICADOS))


# --- Portal ----------------------------------------------------------------------------------


def test_el_ausente_ve_los_acuerdos_y_el_plazo(client, marta, notificada, monkeypatch):
    monkeypatch.setattr(timezone, "localdate", lambda *a, **k: NOTIFICADOS + timedelta(days=2))
    client.force_login(marta.usuario)
    html = client.get(_url_junta(notificada)).content.decode()
    assert "No asististe a esta junta" in html
    assert "Tienes hasta el <strong>14/4/2026</strong>" in html
    assert _url_discrepar(notificada, notificada.puntos.get(orden=1)) in html
    # El punto 2 es una excepción del 17.8: no aparece para discrepar.
    assert _url_discrepar(notificada, notificada.puntos.get(orden=2)) not in html
    assert "Aquí no se vota" in html


def test_discrepar_desde_la_web(client, marta, notificada, monkeypatch):
    hoy = NOTIFICADOS + timedelta(days=2)
    monkeypatch.setattr(timezone, "localdate", lambda *a, **k: hoy)
    monkeypatch.setattr(timezone, "now", lambda: _en(hoy))
    client.force_login(marta.usuario)
    punto = notificada.puntos.get(orden=1)
    respuesta = client.post(_url_discrepar(notificada, punto), follow=True)
    html = respuesta.content.decode()
    assert respuesta.redirect_chain == [(_url_junta(notificada), 302)]
    assert "Discrepancia recibida el 17/03/2026 a las 10:00" in html
    assert "No estás de acuerdo" in html
    assert Discrepancia.objects.get().canal == "portal"


def test_antes_de_la_notificacion_lo_explica(client, marta, celebrada):
    client.force_login(marta.usuario)
    html = client.get(_url_junta(celebrada)).content.decode()
    assert "Cuando el administrador te notifique los acuerdos" in html


def test_error_de_negocio_como_mensaje(client, marta, notificada):
    # Hoy (fecha real) el plazo de marzo de 2026 ya ha terminado.
    client.force_login(marta.usuario)
    html = client.post(
        _url_discrepar(notificada, notificada.puntos.get(orden=1)), follow=True
    ).content.decode()
    assert "30 días" in html
    assert not Discrepancia.objects.exists()


def test_aislamiento_no_discrepa_en_juntas_de_otras_comunidades(
    client, marta, notificada, otra_comunidad
):
    ajena = Junta.objects.create(
        comunidad=otra_comunidad,
        tipo=Junta.Tipo.EXTRAORDINARIA,
        primera_convocatoria=_aware(2026, 3, 10, 19, 0),
        lugar="x",
        convoca="x",
    )
    punto = PuntoOrden.objects.create(junta=ajena, orden=1, titulo="Ajeno")
    client.force_login(marta.usuario)
    assert client.post(_url_discrepar(ajena, punto)).status_code == 404


def test_aislamiento_un_punto_de_otra_junta_da_404(client, marta, notificada, comunidad):
    otra = Junta.objects.create(
        comunidad=comunidad,
        tipo=Junta.Tipo.EXTRAORDINARIA,
        primera_convocatoria=_aware(2026, 4, 10, 19, 0),
        lugar="x",
        convoca="x",
    )
    punto_ajeno = PuntoOrden.objects.create(junta=otra, orden=1, titulo="Otro")
    client.force_login(marta.usuario)
    assert client.post(_url_discrepar(notificada, punto_ajeno)).status_code == 404


def test_sin_ficha_de_vecino_no_hay_discrepancia(client, despacho_a, notificada):
    usuario = get_user_model().objects.create_user(username="ana", despacho=despacho_a)
    client.force_login(usuario)
    punto = notificada.puntos.get(orden=1)
    assert client.post(_url_discrepar(notificada, punto)).status_code == 404


def test_discrepar_solo_por_post(client, marta, notificada):
    client.force_login(marta.usuario)
    assert client.get(_url_discrepar(notificada, notificada.puntos.get(orden=1))).status_code == 405


def test_el_despacho_ve_el_canal(client, despacho_a, marta, notificada):
    from django.contrib.auth.models import Permission

    discrepar_online(marta.usuario, notificada.puntos.get(orden=1), ahora=_en(NOTIFICADOS))
    usuario = get_user_model().objects.create_user(username="ana", despacho=despacho_a)
    usuario.user_permissions.add(Permission.objects.get(codename="add_votoemitido"))
    client.force_login(usuario)
    url = reverse("juntas:celebracion", args=[notificada.comunidad_id, notificada.pk])
    assert "Portal del vecino (recibida 15/3/2026 10:00)" in client.get(url).content.decode()
