"""T2.1 — Aislamiento: un usuario del despacho A no ve presupuestos ni partidas del B."""

import pytest
from django.contrib.auth import get_user_model

from cobros.models import CAMPO_DESPACHO, Cuota, Emision, Partida, Presupuesto
from core.aislamiento import filtrar_por_despacho


@pytest.mark.django_db
@pytest.mark.parametrize("modelo", [Presupuesto, Partida])
def test_usuario_de_a_no_ve_presupuestos_de_b(modelo, presupuesto_a, presupuesto_b):
    de_a = {Presupuesto: {presupuesto_a}, Partida: set(presupuesto_a.partidas.all())}[modelo]
    usuaria = get_user_model().objects.create_user(
        username="ana", despacho=presupuesto_a.comunidad.despacho
    )
    visibles = set(filtrar_por_despacho(modelo.objects.all(), usuaria, CAMPO_DESPACHO[modelo]))
    assert visibles == de_a


@pytest.mark.django_db
@pytest.mark.parametrize("modelo", [Emision, Cuota])
def test_usuario_de_a_no_ve_emisiones_de_b(modelo, despacho_a, despacho_b):
    from datetime import date

    from cobros.emision import emitir_cuotas
    from cobros.models import Partida, Presupuesto
    from fincas.models import Comunidad, Inmueble

    emisiones = {}
    for despacho in (despacho_a, despacho_b):
        comunidad = Comunidad.objects.create(despacho=despacho, nombre=f"CP {despacho}")
        Inmueble.objects.create(comunidad=comunidad, tipo="piso", referencia="1", coeficiente=100)
        presupuesto = Presupuesto.objects.create(comunidad=comunidad, ejercicio=2026)
        Partida.objects.create(presupuesto=presupuesto, concepto="Luz", importe=400)
        presupuesto.fecha_aprobacion = date(2026, 1, 1)
        presupuesto.save()
        emisiones[despacho] = emitir_cuotas(presupuesto, 1, date(2026, 1, 5))
    de_a = {Emision: {emisiones[despacho_a]}, Cuota: set(emisiones[despacho_a].cuotas.all())}
    usuaria = get_user_model().objects.create_user(username="ana", despacho=despacho_a)
    visibles = set(filtrar_por_despacho(modelo.objects.all(), usuaria, CAMPO_DESPACHO[modelo]))
    assert visibles == de_a[modelo]
