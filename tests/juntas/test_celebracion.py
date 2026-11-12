"""T4.3 — Celebrar una junta: asistencia, R-VOT-01, votos, resultados, acta y R-MAY-05.

Comunidad de las fixtures: 1A de Ana (30 %), 1B de Benito y Berta (30 %, vota Benito por
defecto), L1 de Luis (40 %). Junta ordinaria el 10/3/2026 a las 19:00; segunda a las 19:30.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from cobros.morosidad import InformeMorosos, Moroso
from juntas.celebracion import (
    CelebracionInvalida,
    DatosAsistencia,
    cambiar_impugnacion,
    cerrar_acta,
    iniciar_junta,
    notificar_ausentes,
    registrar_discrepancia,
    registrar_votos,
    resultado,
    texto_acta,
    votantes_de,
)
from juntas.convocatoria import convocar
from juntas.models import ActaCerrada, Asistente, PuntoOrden

from .conftest import aware

pytestmark = pytest.mark.django_db

PRESENTE = DatosAsistencia(Asistente.Asistencia.PRESENTE)
HOY = date(2026, 3, 10)


@pytest.fixture
def convocada(junta):
    # El punto 2 necesita unanimidad (para probar R-MAY-05); se cambia en borrador.
    punto = junta.puntos.get(orden=2)
    punto.mayoria = PuntoOrden.Mayoria.UNANIMIDAD
    punto.save()
    PuntoOrden.objects.create(
        junta=junta, orden=3, titulo="Ruegos y preguntas", mayoria=PuntoOrden.Mayoria.SIN_VOTACION
    )
    convocar(junta, date(2026, 3, 1))
    return junta


def _ids(junta):
    return {p.nombre: p.pk for p, _ in votantes_de(junta, HOY)}


def _iniciar(junta, *, hora=(19, 5), **asistencias):
    ids = _ids(junta)
    return iniciar_junta(
        junta,
        inicio=aware(2026, 3, 10, *hora),
        presidente="Ana",
        secretario="El administrador",
        asistencias={ids[nombre]: datos for nombre, datos in asistencias.items()},
    )


def _asistente(celebracion, nombre):
    return celebracion.asistentes.get(propietario__nombre=nombre)


def _votar(punto, celebracion, **sentidos):
    registrar_votos(
        punto, {_asistente(celebracion, nombre).pk: s for nombre, s in sentidos.items()}
    )


def _sin_morosos(monkeypatch):
    informe = InformeMorosos(fecha=HOY, morosos=())
    monkeypatch.setattr("juntas.celebracion.informe_morosos_de", lambda c, f: informe)


@pytest.fixture(autouse=True)
def _nadie_debe(monkeypatch):
    _sin_morosos(monkeypatch)


# --- Votantes ------------------------------------------------------------------------------


def test_votantes_con_sus_cuotas(convocada):
    assert [(p.nombre, c) for p, c in votantes_de(convocada, HOY)] == [
        ("Ana", Decimal("30.0000")),
        ("Benito", Decimal("30.0000")),  # representa el 1B (cotitular con Berta)
        ("Luis", Decimal("40.0000")),
    ]


# --- Iniciar -------------------------------------------------------------------------------


def test_r_jun_03_con_quorum_se_celebra_en_primera(convocada):
    representado = DatosAsistencia(Asistente.Asistencia.REPRESENTADO, "Su hija, Lucía")
    celebracion = _iniciar(convocada, Ana=PRESENTE, Luis=representado)
    assert celebracion.convocatoria == 1
    assert _asistente(celebracion, "Benito").asistencia == "ausente"  # no figura: ausente
    assert _asistente(celebracion, "Luis").representante == "Su hija, Lucía"


def test_r_jun_03_sin_quorum_hay_que_esperar_a_la_segunda(convocada):
    with pytest.raises(CelebracionInvalida, match="segunda convocatoria"):
        _iniciar(convocada, Ana=PRESENTE)  # 1 de 3 propietarios


def test_r_jun_03_sin_quorum_a_la_hora_de_la_segunda(convocada):
    celebracion = _iniciar(convocada, hora=(19, 30), Ana=PRESENTE)
    assert celebracion.convocatoria == 2


def test_representado_sin_representante(convocada):
    with pytest.raises(CelebracionInvalida, match="art. 15.1"):
        _iniciar(convocada, Ana=PRESENTE, Luis=DatosAsistencia("representado", " "))


def test_no_se_inicia_dos_veces(convocada):
    _iniciar(convocada, Ana=PRESENTE, Luis=PRESENTE)
    with pytest.raises(CelebracionInvalida, match="ya se ha iniciado"):
        _iniciar(convocada, Ana=PRESENTE, Luis=PRESENTE)


def test_no_se_inicia_una_junta_sin_convocar(junta):
    with pytest.raises(CelebracionInvalida, match="no está convocada"):
        _iniciar(junta, Ana=PRESENTE)


def test_otro_representante_para_los_cotitulares(convocada):
    berta = convocada.comunidad.inmuebles.get(referencia="1B").titularidades.get(
        propietario__nombre="Berta"
    )
    nombres = [
        p.nombre for p, _ in votantes_de(convocada, HOY, {berta.inmueble_id: berta.propietario_id})
    ]
    assert nombres == ["Ana", "Berta", "Luis"]


# --- R-VOT-01 ------------------------------------------------------------------------------


@pytest.fixture
def luis_moroso(convocada, monkeypatch):
    luis = _ids(convocada)["Luis"]
    informe = InformeMorosos(
        fecha=HOY, morosos=(Moroso(propietario_id=luis, propietario="Luis", recibos=()),)
    )
    monkeypatch.setattr(Moroso, "total", property(lambda self: Decimal("120.00")))
    monkeypatch.setattr("juntas.celebracion.informe_morosos_de", lambda c, f: informe)


def test_r_vot_01_el_moroso_asiste_pero_no_vota(convocada, luis_moroso):
    celebracion = _iniciar(convocada, Ana=PRESENTE, Luis=PRESENTE)
    luis = _asistente(celebracion, "Luis")
    assert luis.deuda == Decimal("120.00") and luis.privado_de_voto
    with pytest.raises(CelebracionInvalida, match="R-VOT-01"):
        _votar(convocada.puntos.get(orden=1), celebracion, Luis="favor")


def test_r_vot_01_su_cuota_no_cuenta_en_la_mayoria(convocada, luis_moroso):
    celebracion = _iniciar(convocada, Ana=PRESENTE, Benito=PRESENTE, Luis=PRESENTE)
    punto = convocada.puntos.get(orden=1)
    _votar(punto, celebracion, Ana="favor", Benito="contra")
    r = resultado(punto, HOY)
    assert (r.base.propietarios, r.base.cuotas) == (2, Decimal("60.0000"))
    assert r.privados.propietarios == 1
    assert not r.aprobado  # 1 de 2: no es más de la mitad


def test_r_vot_01_si_impugno_o_consigno_la_deuda_vota(convocada, luis_moroso):
    celebracion = _iniciar(convocada, Ana=PRESENTE, Luis=PRESENTE)
    luis = _asistente(celebracion, "Luis")
    cambiar_impugnacion(luis, True)
    _votar(convocada.puntos.get(orden=1), celebracion, Luis="favor")
    cambiar_impugnacion(luis, False)  # vuelve a estar privado: su voto se borra
    assert not luis.votos.exists()


def test_r_vot_01_la_deuda_real_de_t3_4_se_usa(convocada, monkeypatch):
    """Integración: sin sustituir el informe de morosos, nadie debe nada → nadie privado."""
    monkeypatch.undo()
    celebracion = _iniciar(convocada, Ana=PRESENTE, Luis=PRESENTE)
    assert not any(a.privado_de_voto for a in celebracion.asistentes.all())


# --- Votos y resultados --------------------------------------------------------------------


def test_votacion_simple_en_primera(convocada):
    celebracion = _iniciar(convocada, Ana=PRESENTE, Luis=PRESENTE)
    punto = convocada.puntos.get(orden=1)
    _votar(punto, celebracion, Ana="favor", Luis="favor")
    r = resultado(punto, HOY)
    assert r.aprobado
    assert (r.favor.propietarios, r.favor.cuotas) == (2, Decimal("70.0000"))
    assert r.ausentes.propietarios == 1


def test_presente_sin_voto_cuenta_como_abstencion(convocada):
    celebracion = _iniciar(convocada, Ana=PRESENTE, Luis=PRESENTE)
    punto = convocada.puntos.get(orden=1)
    _votar(punto, celebracion, Ana="favor")
    assert resultado(punto, HOY).abstencion.propietarios == 1


def test_votar_de_nuevo_sustituye_los_votos(convocada):
    celebracion = _iniciar(convocada, Ana=PRESENTE, Luis=PRESENTE)
    punto = convocada.puntos.get(orden=1)
    _votar(punto, celebracion, Ana="favor", Luis="favor")
    _votar(punto, celebracion, Ana="contra", Luis="contra")
    assert punto.votos.count() == 2
    assert not resultado(punto, HOY).aprobado


def test_un_ausente_no_vota_en_la_junta(convocada):
    celebracion = _iniciar(convocada, Ana=PRESENTE, Luis=PRESENTE)
    with pytest.raises(CelebracionInvalida, match="ausente"):
        _votar(convocada.puntos.get(orden=1), celebracion, Benito="favor")


def test_un_punto_sin_votacion(convocada):
    celebracion = _iniciar(convocada, Ana=PRESENTE, Luis=PRESENTE)
    ruegos = convocada.puntos.get(orden=3)
    assert resultado(ruegos, HOY) is None
    with pytest.raises(CelebracionInvalida, match="no se vota"):
        _votar(ruegos, celebracion, Ana="favor")


def test_segunda_convocatoria_cuenta_sobre_los_asistentes(convocada):
    celebracion = _iniciar(convocada, hora=(19, 30), Ana=PRESENTE)
    punto = convocada.puntos.get(orden=1)
    _votar(punto, celebracion, Ana="favor")
    assert resultado(punto, HOY).aprobado  # 1 de 1 asistentes


# --- Acta ----------------------------------------------------------------------------------


def test_con_el_acta_cerrada_no_se_vota(convocada):
    celebracion = _iniciar(convocada, Ana=PRESENTE, Luis=PRESENTE)
    cerrar_acta(celebracion)
    with pytest.raises(ActaCerrada):
        _votar(convocada.puntos.get(orden=1), celebracion, Ana="favor")
    with pytest.raises(ActaCerrada):
        cerrar_acta(celebracion)


def test_texto_del_acta(convocada, luis_moroso):
    representado = DatosAsistencia(Asistente.Asistencia.REPRESENTADO, "Su hija, Lucía")
    celebracion = _iniciar(convocada, Ana=PRESENTE, Benito=PRESENTE, Luis=representado)
    _votar(convocada.puntos.get(orden=1), celebracion, Ana="favor", Benito="favor")
    texto = texto_acta(celebracion, HOY)
    assert "BORRADOR DEL ACTA DE LA JUNTA ORDINARIA" in texto
    assert "primera convocatoria" in texto
    assert "Preside: Ana. Secretario: El administrador." in texto
    assert "- Ana (30 %), presente." in texto
    assert "- Luis (40 %), representado por Su hija, Lucía." in texto
    assert "PRIVADOS DEL DERECHO DE VOTO (art. 15.2 LPH)" in texto
    assert "1. Aprobación de las cuentas de 2025" in texto
    assert "Aprobado. R-MAY-02 (1ª convocatoria)" in texto
    assert "3. Ruegos y preguntas" in texto and "sin votación" in texto
    assert "el acta no está cerrada" in texto


# --- R-MAY-05: ausentes --------------------------------------------------------------------


@pytest.fixture
def unanimidad_con_un_ausente(convocada):
    """Ana y Luis votan a favor del punto 2 (unanimidad); Benito no fue."""
    celebracion = _iniciar(convocada, Ana=PRESENTE, Luis=PRESENTE)
    punto = convocada.puntos.get(orden=2)
    _votar(punto, celebracion, Ana="favor", Luis="favor")
    cerrar_acta(celebracion)
    return celebracion, punto


def test_r_may_05_hasta_que_pasa_el_plazo_no_hay_unanimidad(unanimidad_con_un_ausente):
    celebracion, punto = unanimidad_con_un_ausente
    assert not resultado(punto, HOY).aprobado
    notificar_ausentes(celebracion, date(2026, 3, 15))
    assert not resultado(punto, date(2026, 4, 14)).aprobado  # día 30: todavía en plazo


def test_r_may_05_pasado_el_plazo_el_ausente_cuenta_a_favor(unanimidad_con_un_ausente):
    celebracion, punto = unanimidad_con_un_ausente
    notificar_ausentes(celebracion, date(2026, 3, 15))
    r = resultado(punto, date(2026, 4, 15))
    assert r.aprobado and r.ausentes_a_favor.propietarios == 1
    assert "computados a favor (R-MAY-05)" in texto_acta(celebracion, date(2026, 4, 15))


def test_r_may_05_si_discrepa_en_plazo_no(unanimidad_con_un_ausente):
    celebracion, punto = unanimidad_con_un_ausente
    notificar_ausentes(celebracion, date(2026, 3, 15))
    registrar_discrepancia(punto, _asistente(celebracion, "Benito"), date(2026, 4, 1))
    assert not resultado(punto, date(2026, 4, 15)).aprobado


def test_r_may_05_excepcion_del_17_8(convocada):
    punto = convocada.puntos.get(orden=2)
    PuntoOrden.objects.filter(pk=punto.pk).update(computa_ausentes=False)  # marcado así
    celebracion = _iniciar(convocada, Ana=PRESENTE, Luis=PRESENTE)
    punto.refresh_from_db()
    _votar(punto, celebracion, Ana="favor", Luis="favor")
    cerrar_acta(celebracion)
    notificar_ausentes(celebracion, date(2026, 3, 15))
    assert not resultado(punto, date(2026, 6, 1)).aprobado


def test_r_may_05_discrepancia_fuera_de_plazo(unanimidad_con_un_ausente):
    celebracion, punto = unanimidad_con_un_ausente
    notificar_ausentes(celebracion, date(2026, 3, 15))
    benito = _asistente(celebracion, "Benito")
    with pytest.raises(CelebracionInvalida, match="30 días"):
        registrar_discrepancia(punto, benito, date(2026, 3, 15) + timedelta(days=31))


def test_r_may_05_solo_discrepan_los_ausentes(unanimidad_con_un_ausente):
    celebracion, punto = unanimidad_con_un_ausente
    notificar_ausentes(celebracion, date(2026, 3, 15))
    with pytest.raises(CelebracionInvalida, match="ausentes"):
        registrar_discrepancia(punto, _asistente(celebracion, "Ana"), date(2026, 3, 20))


def test_r_may_05_sin_notificar_no_se_registran_discrepancias(unanimidad_con_un_ausente):
    celebracion, punto = unanimidad_con_un_ausente
    with pytest.raises(CelebracionInvalida, match="notificar"):
        registrar_discrepancia(punto, _asistente(celebracion, "Benito"), date(2026, 3, 20))


def test_notificar_exige_el_acta_cerrada(convocada):
    celebracion = _iniciar(convocada, Ana=PRESENTE, Luis=PRESENTE)
    with pytest.raises(CelebracionInvalida, match="Cierra antes el acta"):
        notificar_ausentes(celebracion, date(2026, 3, 15))
