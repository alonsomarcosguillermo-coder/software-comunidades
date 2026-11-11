"""T2.3 — Derramas: grupos de reparto (R-REP-01), emisión con asiento y cuotas por plazo.

El cálculo puro está probado en `test_derramas_servicios.py`; aquí, lo que toca la base de
datos: validaciones, el asiento contable y que una derrama emitida no cambia.
"""

from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from cobros.derramas import DerramaInvalida, emitir_derrama, reparto_previsto
from cobros.models import CAMPO_DESPACHO, CuotaDerrama, Derrama, DerramaEmitida
from contabilidad.models import Asiento, ContabilidadInmutable, Cuenta
from core.aislamiento import filtrar_por_despacho
from fincas.models import CAMPO_DESPACHO as CAMPO_DESPACHO_FINCAS
from fincas.models import GrupoReparto, MiembroGrupo
from fincas.servicios import GrupoInvalido

from .conftest import D

pytestmark = pytest.mark.django_db

EMISION = date(2026, 1, 25)


def _cuotas(derrama):
    """{(referencia, plazo): importe} de las cuotas guardadas."""
    return {
        (c.inmueble.referencia, c.plazo): c.importe
        for c in derrama.cuotas.select_related("inmueble")
    }


# --- Grupos de reparto (R-REP-01) -----------------------------------------------------


def test_r_rep_01_grupo_con_coeficientes_generales(grupo_ascensor_a, inmuebles_a):
    assert grupo_ascensor_a.coeficientes() == {
        inmuebles_a["1A"].pk: D("30.0000"),
        inmuebles_a["1B"].pk: D("30.0000"),
    }


def test_r_rep_01_grupo_con_coeficientes_propios(grupo_ascensor_a, inmuebles_a):
    grupo_ascensor_a.miembros.filter(inmueble=inmuebles_a["1A"]).update(coeficiente=D("75"))
    grupo_ascensor_a.miembros.filter(inmueble=inmuebles_a["1B"]).update(coeficiente=D("25"))
    assert grupo_ascensor_a.coeficientes() == {
        inmuebles_a["1A"].pk: D("75.0000"),
        inmuebles_a["1B"].pk: D("25.0000"),
    }


def test_r_rep_01_grupo_mezclado_no_sirve(grupo_ascensor_a, inmuebles_a):
    grupo_ascensor_a.miembros.filter(inmueble=inmuebles_a["1A"]).update(coeficiente=D("75"))
    with pytest.raises(GrupoInvalido):
        grupo_ascensor_a.coeficientes()


def test_miembro_de_grupo_debe_ser_de_la_misma_comunidad(grupo_ascensor_a, derrama_b):
    inmueble_b = derrama_b.comunidad.inmuebles.get()
    miembro = MiembroGrupo(grupo=grupo_ascensor_a, inmueble=inmueble_b)
    with pytest.raises(ValidationError, match="otra comunidad"):
        miembro.full_clean()


def test_miembro_de_grupo_nuevo_se_valida_antes_de_guardar_el_grupo(inmuebles_a, derrama_b):
    # Como en el admin: el grupo aún no tiene id cuando se validan sus inmuebles.
    grupo = GrupoReparto(comunidad=inmuebles_a["1A"].comunidad, nombre="Garaje")
    inmueble_b = derrama_b.comunidad.inmuebles.get()
    with pytest.raises(ValidationError, match="otra comunidad"):
        MiembroGrupo(grupo=grupo, inmueble=inmueble_b).clean()
    MiembroGrupo(grupo=grupo, inmueble=inmuebles_a["1A"]).clean()  # misma comunidad: bien


def test_aislamiento_grupos_de_otro_despacho_no_se_ven(grupo_ascensor_a, derrama_b):
    grupo_b = GrupoReparto.objects.create(comunidad=derrama_b.comunidad, nombre="Tejado")
    MiembroGrupo.objects.create(grupo=grupo_b, inmueble=derrama_b.comunidad.inmuebles.get())
    ana = get_user_model().objects.create_user(
        username="ana", despacho=grupo_ascensor_a.comunidad.despacho
    )
    for modelo, de_a in (
        (GrupoReparto, {grupo_ascensor_a}),
        (MiembroGrupo, set(grupo_ascensor_a.miembros.all())),
    ):
        visibles = filtrar_por_despacho(modelo.objects.all(), ana, CAMPO_DESPACHO_FINCAS[modelo])
        assert set(visibles) == de_a


# --- Derrama: validación y edición ----------------------------------------------------


def test_derrama_grupo_de_otra_comunidad_no_valida(derrama_a, derrama_b):
    grupo_b = GrupoReparto.objects.create(comunidad=derrama_b.comunidad, nombre="Tejado")
    derrama_a.grupo = grupo_b
    with pytest.raises(ValidationError, match="otra comunidad"):
        derrama_a.full_clean()


def test_vencimientos_de_la_derrama(derrama_a):
    assert derrama_a.vencimientos() == [date(2026, 3, 1), date(2026, 4, 1), date(2026, 5, 1)]


def test_derrama_sin_emitir_se_puede_cambiar_y_borrar(derrama_a):
    derrama_a.importe = D("3500.00")
    derrama_a.save()
    derrama_a.delete()
    assert not Derrama.objects.exists()


def test_aislamiento_derramas_y_cuotas_de_otro_despacho_no_se_ven(derrama_a, derrama_b):
    emitir_derrama(derrama_a, EMISION)
    emitir_derrama(derrama_b, EMISION)
    ana = get_user_model().objects.create_user(
        username="ana", despacho=derrama_a.comunidad.despacho
    )
    for modelo, de_a in (
        (Derrama, {derrama_a}),
        (CuotaDerrama, set(derrama_a.cuotas.all())),
    ):
        visibles = filtrar_por_despacho(modelo.objects.all(), ana, CAMPO_DESPACHO[modelo])
        assert set(visibles) == de_a


# --- Emisión --------------------------------------------------------------------------


def test_r_rep_02_emitir_derrama_entre_todos_por_coeficiente(derrama_a):
    emitir_derrama(derrama_a, EMISION)
    derrama_a.refresh_from_db()
    assert derrama_a.esta_emitida
    # 3.000 € → 1A y 1B 900 € (30 %), L1 1.200 € (40 %), en 3 plazos iguales.
    assert _cuotas(derrama_a) == {
        (ref, plazo): importe
        for plazo in (1, 2, 3)
        for ref, importe in (("1A", D("300.00")), ("1B", D("300.00")), ("L1", D("400.00")))
    }
    vencimientos = set(derrama_a.cuotas.values_list("plazo", "vencimiento"))
    assert vencimientos == {(1, date(2026, 3, 1)), (2, date(2026, 4, 1)), (3, date(2026, 5, 1))}


def test_emitir_derrama_registra_su_asiento(derrama_a):
    emitir_derrama(derrama_a, EMISION)
    asiento = Derrama.objects.get(pk=derrama_a.pk).asiento
    assert asiento.fecha == EMISION
    assert asiento.concepto == "Derrama: Fachada"
    assert asiento.total_debe() == asiento.total_haber() == D("3000.00")
    lineas = [
        (a.cuenta.codigo, a.debe, a.haber, a.concepto)
        for a in asiento.apuntes.select_related("cuenta")
    ]
    assert lineas == [
        ("430", D("900.00"), D("0.00"), "1A"),
        ("430", D("900.00"), D("0.00"), "1B"),
        ("430", D("1200.00"), D("0.00"), "L1"),
        ("706", D("0.00"), D("3000.00"), ""),
    ]
    # La deuda de los propietarios es el saldo deudor de la 430.
    assert Cuenta.objects.get(comunidad=derrama_a.comunidad, codigo="430").saldo() == D("3000")


def test_r_rep_01_emitir_derrama_solo_entre_el_grupo(derrama_a, grupo_ascensor_a):
    derrama_a.grupo = grupo_ascensor_a
    derrama_a.plazos = 1
    derrama_a.save()
    emitir_derrama(derrama_a, EMISION)
    # El local no paga: 3.000 € entre los dos pisos, 30 : 30.
    assert _cuotas(derrama_a) == {("1A", 1): D("1500.00"), ("1B", 1): D("1500.00")}


def test_r_rep_02_los_centimos_cuadran_en_la_emision(derrama_a):
    derrama_a.importe = D("100.00")
    derrama_a.save()
    emitir_derrama(derrama_a, EMISION)
    cuotas = _cuotas(derrama_a)
    assert sum(cuotas.values()) == D("100.00")
    # 1A y 1B: 30,00 € en 3 plazos → 10,00 cada uno; L1: 40,00 → 13,34 + 13,33 + 13,33.
    assert [cuotas[("L1", p)] for p in (1, 2, 3)] == [D("13.34"), D("13.33"), D("13.33")]


def test_las_cuotas_de_0_euros_no_se_emiten(derrama_a):
    derrama_a.importe = D("0.01")
    derrama_a.save()
    emitir_derrama(derrama_a, EMISION)
    assert _cuotas(derrama_a) == {("L1", 1): D("0.01")}


def test_no_se_emite_una_derrama_sin_acordar(derrama_a):
    derrama_a.fecha_acuerdo = None
    derrama_a.save()
    with pytest.raises(DerramaInvalida, match="sin acordar"):
        emitir_derrama(derrama_a, EMISION)
    assert not Asiento.objects.exists()
    assert not CuotaDerrama.objects.exists()


def test_no_se_emite_dos_veces(derrama_a):
    emitir_derrama(derrama_a, EMISION)
    with pytest.raises(DerramaInvalida, match="ya está emitida"):
        emitir_derrama(derrama_a, EMISION)
    assert Asiento.objects.count() == 1


def test_r_coef_01_no_se_emite_si_los_coeficientes_no_suman_100(derrama_a, inmuebles_a):
    inmuebles_a["L1"].delete()  # quedan 60 %
    with pytest.raises(DerramaInvalida, match="R-COEF-01"):
        emitir_derrama(derrama_a, EMISION)
    assert not Asiento.objects.exists()


def test_r_rep_01_no_se_emite_con_un_grupo_vacio(derrama_a, inmuebles_a):
    derrama_a.grupo = GrupoReparto.objects.create(comunidad=derrama_a.comunidad, nombre="Vacío")
    derrama_a.save()
    with pytest.raises(DerramaInvalida, match="R-REP-01"):
        emitir_derrama(derrama_a, EMISION)
    assert not Asiento.objects.exists()


def test_reparto_previsto_coincide_con_lo_emitido(derrama_a, grupo_ascensor_a):
    derrama_a.grupo = grupo_ascensor_a
    derrama_a.importe = D("1000.01")
    derrama_a.save()
    previsto = reparto_previsto(derrama_a)
    emitir_derrama(derrama_a, EMISION)
    emitido = {
        (c.plazo, c.inmueble_id): c.importe for c in CuotaDerrama.objects.filter(derrama=derrama_a)
    }
    assert emitido == {(p, i): imp for p, cuotas in previsto.items() for i, imp in cuotas.items()}


# --- Una derrama emitida no cambia ----------------------------------------------------


def test_derrama_emitida_no_se_puede_cambiar(derrama_a):
    emitir_derrama(derrama_a, EMISION)
    derrama = Derrama.objects.get(pk=derrama_a.pk)
    derrama.importe = D("1.00")
    with pytest.raises(DerramaEmitida):
        derrama.save()


def test_derrama_emitida_no_se_puede_borrar(derrama_a):
    emitir_derrama(derrama_a, EMISION)
    derrama = Derrama.objects.get(pk=derrama_a.pk)
    with pytest.raises(DerramaEmitida):
        derrama.delete()
    with pytest.raises(DerramaEmitida):
        Derrama.objects.all().delete()
    assert Derrama.objects.filter(pk=derrama_a.pk).exists()


def test_cuotas_de_derrama_inmutables(derrama_a):
    emitir_derrama(derrama_a, EMISION)
    cuota = derrama_a.cuotas.first()
    cuota.importe = D("1.00")
    with pytest.raises(ContabilidadInmutable):
        cuota.save()
    with pytest.raises(ContabilidadInmutable):
        cuota.delete()
    with pytest.raises(ContabilidadInmutable):
        CuotaDerrama.objects.all().update(importe=D("1.00"))


def test_el_reparto_emitido_no_cambia_aunque_cambie_el_grupo(derrama_a, grupo_ascensor_a):
    derrama_a.grupo = grupo_ascensor_a
    derrama_a.save()
    emitir_derrama(derrama_a, EMISION)
    antes = _cuotas(derrama_a)
    grupo_ascensor_a.miembros.filter(inmueble__referencia="1B").delete()
    assert _cuotas(derrama_a) == antes
