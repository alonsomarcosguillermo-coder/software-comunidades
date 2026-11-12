"""T3.4 — Cálculo puro de la deuda: informe de morosos y estado de deuda de un inmueble
(base del certificado R-DEU-01). Sin base de datos."""

from datetime import date, timedelta
from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from cobros.morosidad import (
    ReciboDeuda,
    estado_deuda,
    informe_morosos,
    recibos_impagados,
)

HOY = date(2026, 6, 1)


def recibo(
    id,
    importe="100.00",
    vencimiento=date(2026, 1, 5),
    cobro=None,
    inmueble=(1, "1A"),
    propietario=(1, "Vecino Uno"),
):
    return ReciboDeuda(
        id=id,
        referencia=f"REC-1-{id}",
        concepto=f"Cuota {id}",
        inmueble_id=inmueble[0],
        inmueble=inmueble[1],
        propietario_id=propietario[0],
        propietario=propietario[1],
        importe=Decimal(importe),
        vencimiento=vencimiento,
        fecha_cobro=cobro,
    )


# --- Qué es deuda ------------------------------------------------------------------------


def test_recibo_vencido_y_sin_cobrar_es_deuda():
    assert recibos_impagados([recibo(1)], HOY) == [recibo(1)]


def test_recibo_cobrado_antes_de_la_fecha_no_es_deuda():
    assert recibos_impagados([recibo(1, cobro=date(2026, 1, 20))], HOY) == []


def test_recibo_cobrado_despues_de_la_fecha_era_deuda_en_esa_fecha():
    """La deuda se calcula a una fecha: lo que se cobró después todavía se debía."""
    cobrado_tarde = recibo(1, cobro=date(2026, 7, 1))
    assert recibos_impagados([cobrado_tarde], HOY) == [cobrado_tarde]


def test_recibo_devuelto_es_deuda_desde_la_devolucion():
    """T3.3: cobrado el 20/1 y devuelto el 5/2 → pagado entre esas fechas, deuda después."""
    devuelto = ReciboDeuda(
        **{**recibo(1).__dict__, "devoluciones": ((date(2026, 1, 20), date(2026, 2, 5)),)}
    )
    assert recibos_impagados([devuelto], date(2026, 1, 19)) == [devuelto]
    assert recibos_impagados([devuelto], date(2026, 2, 1)) == []
    assert recibos_impagados([devuelto], date(2026, 2, 5)) == [devuelto]
    assert devuelto.devuelto_en(date(2026, 2, 5))
    assert not devuelto.devuelto_en(date(2026, 1, 19))


def test_recibo_devuelto_y_cobrado_otra_vez_no_es_deuda():
    recobrado = ReciboDeuda(
        **{
            **recibo(1, cobro=date(2026, 3, 1)).__dict__,
            "devoluciones": ((date(2026, 1, 20), date(2026, 2, 5)),),
        }
    )
    assert recibos_impagados([recobrado], date(2026, 2, 20)) == [recobrado]
    assert recibos_impagados([recobrado], date(2026, 3, 1)) == []


def test_recibo_que_vence_ese_dia_aun_no_esta_vencido():
    """El día del vencimiento todavía se puede pagar: vence, pero no está vencido."""
    estado = estado_deuda([recibo(1, vencimiento=HOY)], HOY)
    assert estado.vencidos == ()
    assert estado.por_vencer == (recibo(1, vencimiento=HOY),)


# --- Informe de morosos ------------------------------------------------------------------


def test_informe_agrupa_por_propietario_y_ordena_de_mayor_a_menor_deuda():
    ana, bea = (1, "Ana Ficticia"), (2, "Bea Inventada")
    recibos = [
        recibo(1, "50.00", propietario=ana),
        recibo(2, "80.00", propietario=bea, inmueble=(2, "1B")),
        recibo(3, "40.00", propietario=ana, vencimiento=date(2026, 4, 5)),
        recibo(4, "999.00", propietario=ana, cobro=date(2026, 2, 1)),  # pagado
        recibo(5, "300.00", propietario=bea, vencimiento=date(2026, 7, 5)),  # no vencido
    ]
    informe = informe_morosos(recibos, HOY)
    assert [m.propietario for m in informe.morosos] == ["Ana Ficticia", "Bea Inventada"]
    ana_m, bea_m = informe.morosos
    assert ana_m.total == Decimal("90.00")
    assert [r.id for r in ana_m.recibos] == [1, 3]
    assert ana_m.mas_antiguo == date(2026, 1, 5)
    assert ana_m.inmuebles == ("1A",)
    assert bea_m.total == Decimal("80.00")
    assert informe.total == Decimal("170.00")
    assert informe.num_recibos == 3


def test_informe_sin_deuda_esta_vacio():
    informe = informe_morosos([recibo(1, cobro=date(2026, 1, 6))], HOY)
    assert informe.morosos == ()
    assert informe.total == Decimal("0.00")


def test_informe_empate_de_deuda_se_ordena_por_nombre():
    recibos = [
        recibo(1, propietario=(2, "Zoe")),
        recibo(2, propietario=(1, "Ana"), inmueble=(2, "1B")),
    ]
    assert [m.propietario for m in informe_morosos(recibos, HOY).morosos] == ["Ana", "Zoe"]


# --- Estado de deuda de un inmueble (certificado R-DEU-01) -------------------------------


def test_estado_deuda_separa_vencidos_y_por_vencer():
    recibos = [
        recibo(2, "30.00", vencimiento=date(2026, 4, 5)),
        recibo(1, "20.00", vencimiento=date(2026, 1, 5)),
        recibo(3, "25.00", vencimiento=date(2026, 7, 5)),
        recibo(4, "99.00", cobro=date(2026, 1, 10)),
    ]
    estado = estado_deuda(recibos, HOY)
    assert [r.id for r in estado.vencidos] == [1, 2]  # por vencimiento
    assert [r.id for r in estado.por_vencer] == [3]
    assert estado.total_vencido == Decimal("50.00")
    assert estado.total_por_vencer == Decimal("25.00")
    assert not estado.al_corriente


def test_estado_deuda_sin_recibos_pendientes_esta_al_corriente():
    estado = estado_deuda([recibo(1, cobro=date(2026, 1, 10))], HOY)
    assert estado.al_corriente
    assert estado.total_vencido == Decimal("0.00")


def test_estado_deuda_al_corriente_aunque_haya_recibos_por_vencer():
    """Al corriente = sin deudas vencidas; un recibo que aún no vence no es una deuda."""
    assert estado_deuda([recibo(1, vencimiento=date(2026, 9, 1))], HOY).al_corriente


# --- Propiedades (hypothesis) ------------------------------------------------------------

importes = st.decimals(min_value="0.01", max_value="5000", places=2)
fechas = st.dates(min_value=date(2025, 1, 1), max_value=date(2027, 12, 31))


@st.composite
def lista_recibos(draw):
    n = draw(st.integers(min_value=0, max_value=25))
    recibos = []
    for i in range(1, n + 1):
        vencimiento = draw(fechas)
        cobro = draw(st.one_of(st.none(), st.integers(0, 400)))
        propietario = draw(st.integers(1, 4))
        recibos.append(
            recibo(
                i,
                str(draw(importes)),
                vencimiento=vencimiento,
                cobro=None if cobro is None else vencimiento + timedelta(days=cobro),
                propietario=(propietario, f"Vecino {propietario}"),
                inmueble=(propietario, f"P{propietario}"),
            )
        )
    return recibos


@given(lista_recibos(), fechas)
def test_propiedad_informe_cuadra_con_la_deuda_vencida(recibos, fecha):
    informe = informe_morosos(recibos, fecha)
    vencidos = estado_deuda(recibos, fecha).vencidos
    assert informe.total == sum((r.importe for r in vencidos), Decimal("0.00"))
    assert informe.total == sum((m.total for m in informe.morosos), Decimal("0.00"))
    # Cada recibo vencido aparece exactamente una vez, con su propietario.
    en_informe = [r for m in informe.morosos for r in m.recibos]
    assert sorted(r.id for r in en_informe) == sorted(r.id for r in vencidos)
    assert all(r.propietario_id == m.propietario_id for m in informe.morosos for r in m.recibos)
    assert all(m.total > 0 for m in informe.morosos)


@given(lista_recibos(), fechas)
def test_propiedad_vencidos_y_por_vencer_son_los_impagados(recibos, fecha):
    estado = estado_deuda(recibos, fecha)
    assert sorted(r.id for r in estado.vencidos + estado.por_vencer) == sorted(
        r.id for r in recibos_impagados(recibos, fecha)
    )
    assert all(r.vencimiento < fecha for r in estado.vencidos)
    assert all(r.vencimiento >= fecha for r in estado.por_vencer)


@given(lista_recibos(), fechas, st.data())
def test_propiedad_cobrar_un_recibo_nunca_aumenta_la_deuda(recibos, fecha, data):
    if not recibos:
        return
    i = data.draw(st.integers(0, len(recibos) - 1))
    antes = informe_morosos(recibos, fecha).total
    pagado = list(recibos)
    pagado[i] = recibo(
        pagado[i].id,
        str(pagado[i].importe),
        vencimiento=pagado[i].vencimiento,
        cobro=fecha,
        propietario=(pagado[i].propietario_id, pagado[i].propietario),
        inmueble=(pagado[i].inmueble_id, pagado[i].inmueble),
    )
    assert informe_morosos(pagado, fecha).total <= antes
