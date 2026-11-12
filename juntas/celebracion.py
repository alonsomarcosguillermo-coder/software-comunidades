"""T4.3 — Celebrar la junta: asistencia, votos, resultados y acta.

Orquesta con la base de datos lo que es puro en `juntas.servicios` (votantes, convocatoria
aplicable, plazo de R-MAY-05) y en `juntas.mayorias` (el cálculo de cada acuerdo). Ver
ADR 015.

Flujo:
1. `iniciar_junta`: se registra quién está (presente, representado o ausente). Al
   iniciarse se fija la deuda vencida de cada votante (R-VOT-01, con `cobros.deudas` de T3.4)
   y la convocatoria en que se celebra (R-JUN-03: 1ª si hay quórum).
2. `registrar_votos` por punto, mientras el acta esté abierta.
3. `resultado`: el cálculo de T4.2 con los votos guardados.
4. `cerrar_acta`; después `notificar_ausentes` y, en 30 días, `registrar_discrepancia`
   (R-MAY-05).
"""

from dataclasses import dataclass
from datetime import date, datetime

from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from cobros.deudas import informe_morosos_de
from fincas.models import Propietario, Titularidad

from .mayorias import Mayoria, Resultado, Sentido, Voto, calcular, hay_quorum_primera
from .models import (
    ActaCerrada,
    Asistente,
    Celebracion,
    Discrepancia,
    Junta,
    PuntoOrden,
    VotoEmitido,
)
from .servicios import (
    PLAZO_DISCREPANCIA,
    ConvocatoriaInvalida,
    InmuebleConTitulares,
    convocatoria_aplicable,
    plazo_ausentes_vencido,
    votantes,
)


class CelebracionInvalida(ValueError):
    """No se puede hacer eso con la junta en su estado actual."""


# --- Votantes ------------------------------------------------------------------------------


def inmuebles_con_titulares(junta: Junta, fecha: date) -> list[InmuebleConTitulares]:
    """Los inmuebles de la comunidad con sus titulares en `fecha`, ordenados por nombre (el
    primero representa a los cotitulares, salvo que se elija otro)."""
    titularidades = (
        Titularidad.objects.vigentes(fecha)
        .filter(inmueble__comunidad=junta.comunidad)
        .select_related("inmueble", "propietario")
        .order_by("inmueble__referencia", "propietario__nombre", "propietario_id")
    )
    por_inmueble: dict[int, InmuebleConTitulares] = {}
    for t in titularidades:
        actual = por_inmueble.get(t.inmueble_id)
        titulares = (actual.titulares if actual else ()) + (t.propietario_id,)
        por_inmueble[t.inmueble_id] = InmuebleConTitulares(
            t.inmueble_id, t.inmueble.coeficiente, titulares
        )
    return list(por_inmueble.values())


def votantes_de(junta: Junta, fecha: date, representantes: dict | None = None):
    """[(propietario, cuota)] de quienes votan en la junta, por nombre."""
    cuotas = votantes(inmuebles_con_titulares(junta, fecha), representantes)
    propietarios = Propietario.objects.in_bulk(cuotas.keys())
    return sorted(
        ((propietarios[pid], cuota) for pid, cuota in cuotas.items()),
        key=lambda par: (par[0].nombre, par[0].pk),
    )


# --- Iniciar -------------------------------------------------------------------------------


@dataclass(frozen=True)
class DatosAsistencia:
    asistencia: str  # Asistente.Asistencia
    representante: str = ""


@transaction.atomic
def iniciar_junta(
    junta: Junta,
    *,
    inicio: datetime,
    presidente: str,
    secretario: str,
    asistencias: dict[int, DatosAsistencia],
    representantes: dict[int, int] | None = None,
) -> Celebracion:
    """Abre la junta. `asistencias` va por id de propietario; quien no esté, ausente."""
    junta = Junta.objects.select_for_update().select_related("comunidad").get(pk=junta.pk)
    if not junta.esta_convocada:
        raise CelebracionInvalida("La junta no está convocada.")
    if Celebracion.objects.filter(junta=junta).exists():
        raise CelebracionInvalida("La junta ya se ha iniciado.")
    if not presidente.strip() or not secretario.strip():
        raise CelebracionInvalida("Indica quién preside la junta y quién actúa de secretario.")

    fecha = timezone.localdate(inicio)
    try:
        lista = votantes_de(junta, fecha, representantes)
    except ValueError as error:
        raise CelebracionInvalida(str(error)) from error
    ids = {p.pk for p, _ in lista}
    if extraños := set(asistencias) - ids:
        raise CelebracionInvalida(f"Hay asistentes que no votan en esta junta: {sorted(extraños)}.")
    for datos in asistencias.values():
        if (
            datos.asistencia == Asistente.Asistencia.REPRESENTADO
            and not datos.representante.strip()
        ):
            raise CelebracionInvalida(
                "Indica quién representa a cada propietario representado (art. 15.1 LPH)."
            )

    # R-VOT-01: deuda vencida e impagada "en el momento de iniciarse la junta".
    deudas = {m.propietario_id: m.total for m in informe_morosos_de(junta.comunidad, fecha).morosos}
    ausente = DatosAsistencia(Asistente.Asistencia.AUSENTE)
    filas = [(p, cuota, asistencias.get(p.pk, ausente)) for p, cuota in lista]

    # R-JUN-03: quórum de primera (todos los que asisten, también los privados de voto).
    quorum = hay_quorum_primera(
        Voto(
            votante=p.pk,
            cuota=cuota,
            sentido=Sentido.AUSENTE
            if datos.asistencia == Asistente.Asistencia.AUSENTE
            else Sentido.ABSTENCION,
        )
        for p, cuota, datos in filas
    )

    def local(momento):
        return timezone.localtime(momento).replace(tzinfo=None) if momento else None

    try:
        convocatoria = convocatoria_aplicable(
            local(inicio),
            local(junta.primera_convocatoria),
            local(junta.segunda_convocatoria),
            hay_quorum=quorum,
        )
    except ConvocatoriaInvalida as error:
        raise CelebracionInvalida(str(error)) from error

    celebracion = Celebracion.objects.create(
        junta=junta,
        iniciada_en=inicio,
        convocatoria=convocatoria,
        presidente=presidente.strip(),
        secretario=secretario.strip(),
    )
    Asistente.objects.bulk_create(
        Asistente(
            celebracion=celebracion,
            propietario=p,
            cuota=cuota,
            asistencia=datos.asistencia,
            representante=datos.representante.strip()
            if datos.asistencia == Asistente.Asistencia.REPRESENTADO
            else "",
            deuda=deudas.get(p.pk, 0),
        )
        for p, cuota, datos in filas
    )
    return celebracion


# --- Durante la junta ----------------------------------------------------------------------


def _abierta(celebracion: Celebracion) -> Celebracion:
    celebracion = Celebracion.objects.select_for_update().get(pk=celebracion.pk)
    if celebracion.esta_cerrada:
        raise ActaCerrada()
    return celebracion


@transaction.atomic
def cambiar_impugnacion(asistente: Asistente, impugnada: bool) -> None:
    """R-VOT-01: si el propietario acredita que ha impugnado o consignado la deuda, vota."""
    _abierta(asistente.celebracion)
    asistente.deuda_impugnada = impugnada
    asistente.save(update_fields=["deuda_impugnada"])
    if asistente.privado_de_voto:
        asistente.votos.all().delete()  # vuelve a estar privado: sus votos no valen


@transaction.atomic
def registrar_votos(punto: PuntoOrden, votos: dict[int, str]) -> None:
    """Guarda (o sustituye) los votos de un punto: {id de asistente: sentido}.

    Solo votan los asistentes presentes o representados que no están privados de voto. Un
    asistente presente sin voto registrado cuenta como abstención.
    """
    celebracion = _abierta(Celebracion.objects.get(junta_id=punto.junta_id))
    if punto.mayoria == PuntoOrden.Mayoria.SIN_VOTACION:
        raise CelebracionInvalida("Este punto no se vota.")
    asistentes = {a.pk: a for a in celebracion.asistentes.all()}
    for asistente_id, sentido in votos.items():
        asistente = asistentes.get(asistente_id)
        if asistente is None:
            raise CelebracionInvalida("Hay votos de alguien que no está en esta junta.")
        if not asistente.asiste:
            raise CelebracionInvalida(
                f"{asistente.propietario} está ausente: no vota en la junta (ver R-MAY-05)."
            )
        if asistente.privado_de_voto:
            raise CelebracionInvalida(
                f"R-VOT-01: {asistente.propietario} no está al corriente de pago y no puede votar."
            )
        if sentido not in VotoEmitido.Sentido.values:
            raise CelebracionInvalida(f"Sentido de voto desconocido: {sentido}.")
    VotoEmitido.objects.filter(punto=punto).delete()
    VotoEmitido.objects.bulk_create(
        VotoEmitido(punto=punto, asistente_id=aid, sentido=s) for aid, s in votos.items()
    )


def resultado(punto: PuntoOrden, hoy: date) -> Resultado | None:
    """El resultado del punto con los votos registrados (None si no se vota).

    R-MAY-05 se aplica si el punto lo permite y ya han pasado los 30 días desde que se
    notificaron los acuerdos a los ausentes.
    """
    if punto.mayoria == PuntoOrden.Mayoria.SIN_VOTACION:
        return None
    # Siempre de la base de datos: un objeto en caché podría no ver una notificación nueva.
    celebracion = Celebracion.objects.get(junta_id=punto.junta_id)
    sentidos = dict(VotoEmitido.objects.filter(punto=punto).values_list("asistente_id", "sentido"))
    discrepan = set(Discrepancia.objects.filter(punto=punto).values_list("asistente_id", flat=True))
    votos = []
    for a in celebracion.asistentes.all():
        if not a.asiste:
            sentido = Sentido.AUSENTE
        else:
            sentido = Sentido(sentidos.get(a.pk, Sentido.ABSTENCION))
        votos.append(
            Voto(
                votante=a.propietario_id,
                cuota=a.cuota,
                sentido=sentido,
                privado_de_voto=a.privado_de_voto,
                discrepa=a.pk in discrepan,
            )
        )
    computar = punto.computa_ausentes and plazo_ausentes_vencido(
        celebracion.ausentes_notificados_el, hoy
    )
    return calcular(
        votos,
        Mayoria(punto.mayoria),
        segunda_convocatoria=celebracion.es_segunda,
        computar_ausentes=computar,
    )


# --- Acta y ausentes -----------------------------------------------------------------------


@transaction.atomic
def cerrar_acta(celebracion: Celebracion, ahora: datetime | None = None) -> None:
    """Art. 19 LPH: el acta se cierra con las firmas del presidente y del secretario."""
    celebracion = _abierta(celebracion)
    celebracion.cerrada_en = ahora or timezone.now()
    celebracion.save(update_fields=["cerrada_en"])


@transaction.atomic
def notificar_ausentes(celebracion: Celebracion, fecha: date) -> None:
    """R-MAY-05: anota el día en que se comunicaron los acuerdos a los ausentes."""
    celebracion = Celebracion.objects.select_for_update().get(pk=celebracion.pk)
    if not celebracion.esta_cerrada:
        raise CelebracionInvalida("Cierra antes el acta: se notifican los acuerdos del acta.")
    if celebracion.ausentes_notificados_el is not None:
        raise CelebracionInvalida("Los acuerdos ya se notificaron a los ausentes.")
    if fecha < timezone.localdate(celebracion.iniciada_en):
        raise CelebracionInvalida("La notificación no puede ser anterior a la junta.")
    celebracion.ausentes_notificados_el = fecha
    celebracion.save(update_fields=["ausentes_notificados_el"])


@transaction.atomic
def registrar_discrepancia(punto: PuntoOrden, asistente: Asistente, fecha: date) -> Discrepancia:
    """R-MAY-05: un ausente manifiesta su discrepancia, dentro de los 30 días naturales."""
    # Siempre de la base de datos: un objeto en caché podría no ver una notificación nueva.
    celebracion = Celebracion.objects.get(junta_id=punto.junta_id)
    if asistente.celebracion_id != celebracion.pk:
        raise CelebracionInvalida("Ese propietario no es de esta junta.")
    if asistente.asiste:
        raise CelebracionInvalida("Solo los ausentes manifiestan su discrepancia después.")
    notificados = celebracion.ausentes_notificados_el
    if notificados is None:
        raise CelebracionInvalida("Primero hay que notificar los acuerdos a los ausentes.")
    if not notificados <= fecha <= notificados + PLAZO_DISCREPANCIA:
        raise CelebracionInvalida(
            "R-MAY-05: la discrepancia tiene que llegar en los 30 días naturales siguientes a "
            f"la notificación (hasta el {notificados + PLAZO_DISCREPANCIA:%d/%m/%Y})."
        )
    if Discrepancia.objects.filter(punto=punto, asistente=asistente).exists():
        raise CelebracionInvalida("Esa discrepancia ya está registrada.")
    return Discrepancia.objects.create(punto=punto, asistente=asistente, fecha=fecha)


def texto_acta(celebracion: Celebracion, hoy: date) -> str:
    """Borrador del acta (art. 19 LPH), en texto, con el resultado de cada punto."""
    junta = celebracion.junta
    asistentes = list(celebracion.asistentes.select_related("propietario"))
    puntos = [(p, resultado(p, hoy)) for p in junta.puntos.all()]
    return render_to_string(
        "juntas/acta.txt",
        {
            "junta": junta,
            "celebracion": celebracion,
            "presentes": [a for a in asistentes if a.asistencia == Asistente.Asistencia.PRESENTE],
            "representados": [
                a for a in asistentes if a.asistencia == Asistente.Asistencia.REPRESENTADO
            ],
            "ausentes": [a for a in asistentes if not a.asiste],
            "privados": [a for a in asistentes if a.privado_de_voto],
            "puntos": puntos,
            "hoy": hoy,
        },
    )
