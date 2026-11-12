"""Importar extractos Norma 43 (T3.1). `importar_norma43` es la ÚNICA forma prevista de
crear extractos.

El fichero se lee y se comprueba con funciones puras (`bancos.norma43`); aquí solo se
orquesta: comprobar que es de la comunidad y que no repite días ya importados, y guardar.
Todo en una transacción: o se importan todas las cuentas del fichero o ninguna.

Importar no contabiliza nada: los cobros y pagos se contabilizarán al conciliar (T3.2).
"""

from decimal import Decimal

from django.db import transaction
from django.db.models import Q

from fincas.models import Comunidad

from .models import Extracto, Movimiento
from .norma43 import EUROS, ExtractoCuenta, FicheroNorma43Invalido, cuenta_de_iban, leer_norma43

# Lo que cabe en un DecimalField(max_digits=12, decimal_places=2).
MAXIMO = Decimal("9999999999.99")


class ImportacionInvalida(ValueError):
    """No se puede importar el fichero."""


def _comprobar_importes(extracto: ExtractoCuenta) -> None:
    importes = [extracto.saldo_inicial, extracto.saldo_final]
    importes += [m.importe for m in extracto.movimientos]
    if any(abs(importe) > MAXIMO for importe in importes):
        raise ImportacionInvalida(
            f"El extracto del {extracto.fecha_inicial:%d/%m/%Y} trae un importe demasiado grande."
        )


def _solapan(a: ExtractoCuenta, b: ExtractoCuenta) -> bool:
    return a.fecha_inicial <= b.fecha_final and b.fecha_inicial <= a.fecha_final


@transaction.atomic
def importar_norma43(
    comunidad: Comunidad, contenido: bytes, *, nombre_fichero: str, usuario=None
) -> list[Extracto]:
    """Guarda las cuentas del fichero como extractos de `comunidad` y devuelve los creados.

    Se rechaza el fichero entero si no cumple la Norma 43 o sus totales no cuadran, si
    alguna cuenta no es la de la comunidad, si no está en euros o si sus fechas se solapan
    con un extracto ya importado (los movimientos de esos días estarían dos veces).
    """
    # Bloquea la comunidad: dos importaciones a la vez no pueden colar el mismo periodo.
    comunidad = Comunidad.objects.select_for_update().get(pk=comunidad.pk)
    cuenta = cuenta_de_iban(comunidad.iban_cobros)
    if cuenta is None:
        raise ImportacionInvalida(
            "La comunidad no tiene un IBAN español de cobro: hace falta para saber que el "
            "extracto es de su cuenta."
        )
    try:
        extractos = leer_norma43(contenido)
    except FicheroNorma43Invalido as error:
        raise ImportacionInvalida(f"El fichero no es un Norma 43 válido. {error}") from error

    for i, extracto in enumerate(extractos):
        if (extracto.entidad, extracto.oficina, extracto.cuenta) != cuenta:
            raise ImportacionInvalida(
                f"La cuenta {extracto.entidad} {extracto.oficina} ****{extracto.cuenta[-4:]} "
                "del fichero no es la de la comunidad (su IBAN de cobro)."
            )
        if extracto.divisa != EUROS:
            raise ImportacionInvalida(
                f"El extracto está en otra divisa (código {extracto.divisa}); solo se admiten "
                "euros."
            )
        _comprobar_importes(extracto)
        if any(_solapan(extracto, otro) for otro in extractos[:i]):
            raise ImportacionInvalida("Dos cuentas del fichero se solapan en fechas.")
        anterior = (
            comunidad.extractos.filter(
                entidad=extracto.entidad, oficina=extracto.oficina, cuenta=extracto.cuenta
            )
            .filter(
                Q(fecha_inicial__lte=extracto.fecha_final)
                & Q(fecha_final__gte=extracto.fecha_inicial)
            )
            .first()
        )
        if anterior is not None:
            raise ImportacionInvalida(
                f"Ya hay un extracto de esta cuenta del {anterior.fecha_inicial:%d/%m/%Y} al "
                f"{anterior.fecha_final:%d/%m/%Y}, que se solapa con el del fichero "
                f"({extracto.fecha_inicial:%d/%m/%Y} – {extracto.fecha_final:%d/%m/%Y})."
            )

    creados = []
    for extracto in extractos:
        guardado = Extracto.objects.create(
            comunidad=comunidad,
            entidad=extracto.entidad,
            oficina=extracto.oficina,
            cuenta=extracto.cuenta,
            fecha_inicial=extracto.fecha_inicial,
            fecha_final=extracto.fecha_final,
            saldo_inicial=extracto.saldo_inicial,
            saldo_final=extracto.saldo_final,
            nombre_fichero=nombre_fichero[:255],
            registros="\n".join(r.rstrip() for r in extracto.registros),
            importado_por=usuario,
        )
        Movimiento.objects.bulk_create(
            Movimiento(
                extracto=guardado,
                orden=orden,
                fecha_operacion=m.fecha_operacion,
                fecha_valor=m.fecha_valor,
                concepto_comun=m.concepto_comun,
                concepto_propio=m.concepto_propio,
                importe=m.importe,
                oficina_origen=m.oficina_origen,
                documento=m.documento,
                referencia_1=m.referencia_1,
                referencia_2=m.referencia_2,
                conceptos="\n".join(m.conceptos),
            )
            for orden, m in enumerate(extracto.movimientos, start=1)
        )
        creados.append(guardado)
    return creados
