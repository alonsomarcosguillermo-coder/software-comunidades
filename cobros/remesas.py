"""Remesas SEPA (T2.5). `crear_remesa` es la ÚNICA forma prevista de crear remesas.

El fichero se genera y se valida con funciones puras (`cobros.sepa.pain008`); aquí solo se
orquesta: elegir los recibos, generar y validar el XML, guardarlo y marcar los recibos. Todo
en una transacción: si el XML no cumple el esquema, no se guarda nada.

La remesa no lleva asiento: el cobro se contabilizará al conciliar el extracto (T3.2).
"""

from datetime import date, datetime
from decimal import Decimal

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from fincas.models import Comunidad

from .models import Mandato, Recibo, Remesa
from .sepa.pain008 import (
    Acreedor,
    Adeudo,
    DatosRemesa,
    XmlInvalido,
    generar_pain008,
    validar_pain008,
)


class RemesaInvalida(ValueError):
    """No se puede crear la remesa."""


@transaction.atomic
def crear_remesa(
    comunidad: Comunidad, fecha_cobro: date, *, ahora: datetime | None = None
) -> Remesa:
    """Crea la remesa de los recibos domiciliables que vencen hasta `fecha_cobro`.

    Domiciliable (R-SEPA-01) = recibo pendiente cuyo pagador tiene un mandato vigente en la
    fecha de cobro. El resto se queda pendiente (se cobrará de otra forma o en otra remesa).
    """
    ahora = ahora or timezone.localtime()
    # Bloquea la comunidad: dos remesas a la vez no repiten número ni recibos.
    comunidad = Comunidad.objects.select_for_update().get(pk=comunidad.pk)

    if fecha_cobro <= ahora.date():
        raise RemesaInvalida("La fecha de cobro tiene que ser posterior a hoy.")
    if not comunidad.nif:
        raise RemesaInvalida(
            "Falta el NIF de la comunidad: sin él no hay identificador de acreedor SEPA."
        )
    if not comunidad.iban_cobros:
        raise RemesaInvalida("Falta el IBAN en el que la comunidad cobra los recibos.")

    pendientes = list(
        comunidad.recibos.filter(remesa__isnull=True, vencimiento__lte=fecha_cobro).order_by(
            "numero"
        )
    )
    mandatos = {
        m.propietario_id: m
        for m in Mandato.objects.vigentes(fecha_cobro).filter(
            comunidad=comunidad, propietario_id__in={r.propietario_id for r in pendientes}
        )
    }
    recibos = [r for r in pendientes if r.propietario_id in mandatos]
    if not recibos:
        raise RemesaInvalida(
            "No hay recibos domiciliables: ninguno pendiente que venza hasta esa fecha y cuyo "
            "pagador tenga un mandato SEPA vigente (R-SEPA-01)."
        )

    # FRST: primer cobro con ese mandato; RCUR: ya se usó en una remesa anterior.
    usados = set(
        Recibo.objects.filter(mandato__in=mandatos.values()).values_list("mandato_id", flat=True)
    )
    for recibo in recibos:
        recibo.mandato = mandatos[recibo.propietario_id]
        recibo.secuencia = "RCUR" if recibo.mandato.pk in usados else "FRST"

    numero = (comunidad.remesas.aggregate(n=Max("numero"))["n"] or 0) + 1
    datos = DatosRemesa(
        mensaje_id=f"REM{comunidad.pk}-{numero}-{ahora:%Y%m%d%H%M%S}",
        creada=ahora.replace(tzinfo=None),
        fecha_cobro=fecha_cobro,
        acreedor=Acreedor(
            nombre=comunidad.nombre,
            iban=comunidad.iban_cobros,
            identificador=comunidad.identificador_acreedor(),
        ),
        adeudos=[
            Adeudo(
                referencia=recibo.referencia,
                importe=recibo.importe,
                mandato=recibo.mandato.referencia,
                fecha_firma=recibo.mandato.fecha_firma,
                secuencia=recibo.secuencia,
                deudor=recibo.mandato.titular_cuenta,
                iban_deudor=recibo.mandato.iban,
                concepto=recibo.concepto,
            )
            for recibo in recibos
        ],
    )
    xml = generar_pain008(datos)
    try:
        validar_pain008(xml)  # R-SEPA-02: nunca se guarda un fichero que el banco rechazaría
    except XmlInvalido as error:
        raise RemesaInvalida(str(error)) from error

    remesa = Remesa.objects.create(
        comunidad=comunidad,
        numero=numero,
        fecha_cobro=fecha_cobro,
        mensaje_id=datos.mensaje_id,
        xml=xml.decode("utf-8"),
        num_recibos=len(recibos),
        total=sum((r.importe for r in recibos), Decimal("0")),
    )
    for recibo in recibos:
        recibo.remesa = remesa
    # bulk_update no pasa por Recibo.save() (que impide cambiar recibos): solo toca estos campos.
    Recibo.objects.bulk_update(recibos, ["remesa", "mandato", "secuencia"])
    return remesa
