"""T4.1 — Convocar una junta: plazos, citaciones, relación de morosos y emails."""

from datetime import date
from decimal import Decimal

import pytest
from django.core import mail

from cobros.morosidad import InformeMorosos, Moroso
from juntas.convocatoria import convocar
from juntas.models import Citacion, Junta, JuntaConvocada, PuntoOrden
from juntas.servicios import ConvocatoriaInvalida

from .conftest import aware

pytestmark = pytest.mark.django_db

CITACION = date(2026, 3, 1)  # 8 días antes: cumple R-JUN-02


def test_cita_a_los_titulares_actuales_y_envia_un_email_a_cada_uno(junta):
    resultado = convocar(junta, CITACION)

    citados = sorted(c.propietario.nombre for c in Citacion.objects.filter(junta=junta))
    assert citados == ["Ana", "Benito", "Berta", "Luis"]  # Carlos vendió: no se le cita
    assert sorted(m.to[0] for m in mail.outbox) == [
        "ana@example.com",
        "benito@example.com",
        "berta@example.com",
    ]
    assert all(len(m.to) == 1 for m in mail.outbox)  # nadie ve el email de otro
    assert [c.propietario.nombre for c in resultado.sin_email] == ["Luis"]
    assert all(c.enviada_en for c in resultado.enviadas)
    junta.refresh_from_db()
    assert junta.convocada_el == CITACION


def test_el_email_lleva_lo_que_exige_la_ley(junta):
    convocar(junta, CITACION)
    mensaje = mail.outbox[0]
    assert mensaje.subject == "Convocatoria de junta ordinaria · CP Calle Ficticia 1"
    texto = mensaje.body
    assert "La presidenta, Ana convoca" in texto
    assert "el portal del edificio" in texto
    assert "10 de marzo de 2026, a las 19:00" in texto
    assert "Segunda convocatoria: martes 10 de marzo de 2026, a las 19:30" in texto
    assert "1. Aprobación de las cuentas de 2025" in texto
    assert "2. Presupuesto de 2026" in texto
    assert "Incluye la aportación al fondo de reserva." in texto
    assert "NO ESTÁN AL CORRIENTE" not in texto  # nadie debe nada


def test_r_vot_01_la_convocatoria_lleva_la_relacion_de_morosos(junta, monkeypatch):
    """Art. 16.2 LPH: relación de quienes no están al corriente y advertencia de R-VOT-01."""
    luis = junta.comunidad.inmuebles.get(referencia="L1").titularidades.get().propietario
    informe = InformeMorosos(
        fecha=CITACION,
        morosos=(Moroso(propietario_id=luis.pk, propietario="Luis", recibos=()),),
    )
    monkeypatch.setattr("juntas.convocatoria.informe_morosos_de", lambda comunidad, f: informe)

    convocar(junta, CITACION)

    texto = mail.outbox[0].body
    assert "NO ESTÁN AL CORRIENTE DE PAGO (art. 16.2 LPH)" in texto
    assert "- Luis" in texto
    assert "no votar (art. 15.2 LPH)" in texto
    assert Citacion.objects.get(propietario=luis).moroso
    assert not Citacion.objects.filter(moroso=True).exclude(propietario=luis).exists()


def test_r_jun_02_se_niega_sin_la_antelacion_de_la_ordinaria(junta):
    with pytest.raises(ConvocatoriaInvalida, match="R-JUN-02"):
        convocar(junta, date(2026, 3, 4))
    assert not Citacion.objects.exists()
    assert not mail.outbox
    junta.refresh_from_db()
    assert not junta.esta_convocada


def test_extraordinaria_con_poca_antelacion(comunidad, junta):
    extra = Junta.objects.create(
        comunidad=comunidad,
        tipo=Junta.Tipo.EXTRAORDINARIA,
        primera_convocatoria=aware(2026, 3, 5, 19, 0),
        lugar="el portal",
        convoca="La presidenta, Ana",
    )
    PuntoOrden.objects.create(junta=extra, orden=1, titulo="Avería del ascensor")
    convocar(extra, date(2026, 3, 3))
    assert "junta extraordinaria" in mail.outbox[0].subject


def test_r_jun_03_segunda_convocatoria_demasiado_pronto(junta):
    Junta.objects.filter(pk=junta.pk).update(segunda_convocatoria=aware(2026, 3, 10, 19, 15))
    with pytest.raises(ConvocatoriaInvalida, match="R-JUN-03"):
        convocar(junta, CITACION)


def test_sin_orden_del_dia(junta):
    junta.puntos.all().delete()
    with pytest.raises(ConvocatoriaInvalida, match="orden del día"):
        convocar(junta, CITACION)


def test_no_se_convoca_dos_veces(junta):
    convocar(junta, CITACION)
    with pytest.raises(ConvocatoriaInvalida, match="ya está convocada"):
        convocar(junta, CITACION)
    assert len(mail.outbox) == 3


def test_comunidad_sin_propietarios(despacho_a):
    from fincas.models import Comunidad

    vacia = Comunidad.objects.create(despacho=despacho_a, nombre="Solar")
    junta = Junta.objects.create(
        comunidad=vacia,
        tipo=Junta.Tipo.EXTRAORDINARIA,
        primera_convocatoria=aware(2026, 3, 10, 19, 0),
        lugar="x",
        convoca="x",
    )
    PuntoOrden.objects.create(junta=junta, orden=1, titulo="Constitución")
    with pytest.raises(ConvocatoriaInvalida, match="propietarios"):
        convocar(junta, CITACION)


# --- Una junta convocada no cambia --------------------------------------------------------


def test_junta_convocada_no_se_modifica(junta):
    convocar(junta, CITACION)
    junta.refresh_from_db()
    junta.lugar = "otro sitio"
    with pytest.raises(JuntaConvocada):
        junta.save()
    with pytest.raises(JuntaConvocada):
        junta.delete()


def test_orden_del_dia_de_una_junta_convocada_no_se_modifica(junta):
    convocar(junta, CITACION)
    punto = junta.puntos.first()
    punto.titulo = "Otra cosa"
    with pytest.raises(JuntaConvocada):
        punto.save()
    with pytest.raises(JuntaConvocada):
        punto.delete()
    with pytest.raises(JuntaConvocada):
        PuntoOrden.objects.create(junta=junta, orden=3, titulo="Punto añadido tarde")


def test_un_borrador_se_puede_cambiar(junta):
    junta.lugar = "la sala de la comunidad"
    junta.save()
    PuntoOrden.objects.create(junta=junta, orden=3, titulo="Ruegos y preguntas")
    assert junta.puntos.count() == 3


def test_morosos_reales_con_recibos_vencidos(junta):
    """Integración con T3.4: un recibo vencido y sin cobrar hace moroso a su pagador."""
    from cobros.emision import emitir_cuotas
    from cobros.models import Partida, Presupuesto
    from cobros.recibos import generar_recibos
    from contabilidad.models import Cuenta

    comunidad = junta.comunidad
    Cuenta.objects.create(comunidad=comunidad, codigo="113", nombre="F", es_fondo_reserva=True)
    presupuesto = Presupuesto.objects.create(comunidad=comunidad, ejercicio=2026)
    Partida.objects.create(presupuesto=presupuesto, concepto="Limpieza", importe=Decimal("1200"))
    presupuesto.fecha_aprobacion = date(2025, 12, 1)
    presupuesto.save()
    emitir_cuotas(presupuesto, 1, date(2026, 1, 5))
    generar_recibos(comunidad)  # nadie ha pagado: todos los pagadores deben

    convocar(junta, CITACION)
    assert Citacion.objects.filter(moroso=True).exists()
    assert "NO ESTÁN AL CORRIENTE" in mail.outbox[0].body
