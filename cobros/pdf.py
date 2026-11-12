"""T3.4 — PDF del informe de morosos y del certificado de deuda (R-DEU-01), con ReportLab.

Solo presenta: los datos llegan ya calculados (`cobros.morosidad`, `cobros.deudas`). Se usa
la parte "platypus" de ReportLab, que maqueta párrafos y tablas y salta de página sola
(ADR 011). Las fuentes son las estándar del PDF (Helvetica), que incluyen tildes, ñ y €.
"""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from io import BytesIO
from xml.sax.saxutils import escape

from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from fincas.models import Comunidad

from .deudas import DatosCertificado
from .morosidad import InformeMorosos, ReciboDeuda

CENTIMO = Decimal("0.01")


def formato_euros(importe: Decimal) -> str:
    """1234.5 → "1.234,50 €" (formato español)."""
    texto = f"{importe.quantize(CENTIMO, rounding=ROUND_HALF_UP):,.2f}"
    return texto.replace(",", "_").replace(".", ",").replace("_", ".") + " €"


def formato_fecha(fecha: date) -> str:
    return f"{fecha:%d/%m/%Y}"


# --- Estilos ------------------------------------------------------------------------------

_base = getSampleStyleSheet()
TITULO = ParagraphStyle("titulo", parent=_base["Title"], fontSize=16, spaceAfter=6)
SUBTITULO = ParagraphStyle("subtitulo", parent=_base["Heading2"], fontSize=12, spaceBefore=10)
TEXTO = ParagraphStyle("texto", parent=_base["BodyText"], fontSize=10, leading=14)
PEQUENO = ParagraphStyle("pequeno", parent=TEXTO, fontSize=8, leading=10, textColor=colors.grey)
CELDA = ParagraphStyle("celda", parent=TEXTO, fontSize=8.5, leading=10.5)
CELDA_NUM = ParagraphStyle("celda_num", parent=CELDA, alignment=TA_RIGHT)

ESTILO_TABLA = TableStyle(
    [
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8edf5")),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.HexColor("#8a99ad")),
        ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.HexColor("#d9dee4")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (-1, 0), (-1, -1), "RIGHT"),  # la última columna es siempre un importe
    ]
)


def _p(texto: str, estilo=TEXTO) -> Paragraph:
    """Párrafo con el texto escapado: un nombre con "&" o "<" no rompe el PDF. El espacio
    antes de "€" no se parte al final de una línea."""
    return Paragraph(escape(texto).replace(" €", "&nbsp;€"), estilo)


def _tabla(cabecera: list[str], filas: list[list], anchos: list[float], total=None) -> Table:
    datos = [cabecera] + [
        [_p(c, CELDA) if isinstance(c, str) else c for c in fila] for fila in filas
    ]
    estilo = TableStyle(ESTILO_TABLA.getCommands())
    if total is not None:
        datos.append(total)
        estilo.add("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold")
        estilo.add("LINEABOVE", (0, -1), (-1, -1), 0.6, colors.HexColor("#8a99ad"))
    tabla = Table(datos, colWidths=anchos, repeatRows=1)
    tabla.setStyle(estilo)
    return tabla


def _importe(importe: Decimal) -> Paragraph:
    return _p(formato_euros(importe), CELDA_NUM)


def _cabecera_comunidad(comunidad: Comunidad) -> list:
    datos = [comunidad.nombre]
    if comunidad.nif:
        datos.append(f"NIF {comunidad.nif}")
    if comunidad.direccion:
        datos.append(comunidad.direccion)
    return [_p(" · ".join(datos))]


def _construir(historia: list, titulo: str, pie: str, comprimir: bool = True) -> bytes:
    """Maqueta `historia` en un PDF A4 con un pie de página (texto y nº de página)."""
    salida = BytesIO()
    documento = SimpleDocTemplate(
        salida,
        pagesize=A4,
        title=titulo,
        author="Comunidades",
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        # Sin comprimir, el texto se lee tal cual dentro del fichero (lo usan los tests).
        pageCompression=1 if comprimir else 0,
    )

    def dibujar_pie(lienzo, doc):
        lienzo.saveState()
        lienzo.setFont("Helvetica", 7.5)
        lienzo.setFillColor(colors.grey)
        lienzo.drawString(2 * cm, 1.2 * cm, pie)
        lienzo.drawRightString(A4[0] - 2 * cm, 1.2 * cm, f"Página {doc.page}")
        lienzo.restoreState()

    documento.build(historia, onFirstPage=dibujar_pie, onLaterPages=dibujar_pie)
    return salida.getvalue()


def _generado() -> str:
    return f"Generado el {timezone.localtime():%d/%m/%Y %H:%M}"


def _estado_recibo(recibo: ReciboDeuda) -> str:
    # Un recibo remesado puede estar pendiente de que el banco lo cobre: se avisa.
    return "Remesado, sin cobro" if recibo.remesado else "Pendiente"


# --- Informe de morosos -------------------------------------------------------------------


def pdf_informe_morosos(
    comunidad: Comunidad, informe: InformeMorosos, *, comprimir: bool = True
) -> bytes:
    """Propietarios con recibos vencidos e impagados en `informe.fecha`, y su detalle."""
    fecha = formato_fecha(informe.fecha)
    historia: list = [
        _p("Informe de morosos", TITULO),
        *_cabecera_comunidad(comunidad),
        _p(f"Deuda vencida a {fecha}."),
        Spacer(1, 0.3 * cm),
    ]
    if not informe.morosos:
        historia.append(_p(f"A {fecha} no hay recibos vencidos pendientes de pago."))
    else:
        historia += [
            _p(
                f"{len(informe.morosos)} propietarios con deuda, {informe.num_recibos} "
                f"recibos, {formato_euros(informe.total)} en total."
            ),
            Spacer(1, 0.3 * cm),
            _tabla(
                ["Propietario", "Inmuebles", "Recibos", "Desde", "Deuda"],
                [
                    [
                        m.propietario,
                        ", ".join(m.inmuebles),
                        str(len(m.recibos)),
                        formato_fecha(m.mas_antiguo),
                        _importe(m.total),
                    ]
                    for m in informe.morosos
                ],
                [5.5 * cm, 3.5 * cm, 1.7 * cm, 2.3 * cm, 4 * cm],
                total=["Total", "", str(informe.num_recibos), "", _importe(informe.total)],
            ),
            _p("Detalle de recibos", SUBTITULO),
            _tabla(
                ["Propietario", "Recibo", "Concepto", "Vence", "Estado", "Importe"],
                [
                    [
                        m.propietario,
                        r.referencia,
                        r.concepto,
                        formato_fecha(r.vencimiento),
                        _estado_recibo(r),
                        _importe(r.importe),
                    ]
                    for m in informe.morosos
                    for r in m.recibos
                ],
                [3.4 * cm, 2.0 * cm, 4.6 * cm, 2.1 * cm, 2.4 * cm, 2.5 * cm],
            ),
        ]
    historia += [
        Spacer(1, 0.6 * cm),
        _p(
            "Contiene datos personales: solo para la gestión de la comunidad. Un recibo "
            "remesado puede estar ya cobrado por el banco aunque aún no se haya conciliado.",
            PEQUENO,
        ),
    ]
    return _construir(
        historia,
        titulo=f"Informe de morosos · {comunidad.nombre} · {fecha}",
        pie=f"Informe de morosos · {comunidad.nombre} · {_generado()}",
        comprimir=comprimir,
    )


# --- Certificado de deuda (R-DEU-01) ------------------------------------------------------


def _tabla_recibos(recibos: tuple[ReciboDeuda, ...], total: Decimal) -> Table:
    return _tabla(
        ["Recibo", "Concepto", "Pagador", "Vence", "Importe"],
        [
            [
                r.referencia,
                r.concepto,
                r.propietario,
                formato_fecha(r.vencimiento),
                _importe(r.importe),
            ]
            for r in recibos
        ],
        [2.3 * cm, 6 * cm, 3.7 * cm, 2 * cm, 3 * cm],
        total=["Total", "", "", "", _importe(total)],
    )


def pdf_certificado_deuda(datos: DatosCertificado, *, comprimir: bool = True) -> bytes:
    """R-DEU-01 — Certificado del estado de deudas de un inmueble con la comunidad (art. 9.1.e
    LPH: lo aporta el vendedor en la transmisión del inmueble)."""
    estado, inmueble = datos.estado, datos.inmueble
    fecha = formato_fecha(estado.fecha)
    coeficiente = f"{inmueble.coeficiente:.4f}".replace(".", ",")
    descripcion = (
        f"{inmueble.referencia} ({inmueble.get_tipo_display().lower()}, "
        f"coeficiente {coeficiente} %)"
    )
    titulares = ", ".join(p.nombre for p in datos.titulares) or "sin titular registrado"
    historia: list = [
        _p("Certificado de deuda", TITULO),
        *_cabecera_comunidad(datos.comunidad),
        Spacer(1, 0.4 * cm),
        _p(f"Inmueble: {descripcion}."),
        _p(f"Titulares a {fecha}: {titulares}."),
        Spacer(1, 0.3 * cm),
    ]
    if estado.al_corriente:
        historia.append(
            _p(
                f"Se certifica que, a {fecha}, el inmueble {inmueble.referencia} se encuentra "
                "al corriente de pago con la comunidad: no tiene recibos vencidos pendientes "
                "de pago."
            )
        )
    else:
        historia += [
            _p(
                f"Se certifica que, a {fecha}, el inmueble {inmueble.referencia} tiene una "
                f"deuda vencida con la comunidad de {formato_euros(estado.total_vencido)}, "
                "por los recibos siguientes:"
            ),
            Spacer(1, 0.2 * cm),
            _tabla_recibos(estado.vencidos, estado.total_vencido),
        ]
    if estado.por_vencer:
        historia += [
            Spacer(1, 0.4 * cm),
            _p(
                "Además, hay recibos emitidos que todavía no han vencido, por "
                f"{formato_euros(estado.total_por_vencer)}:"
            ),
            Spacer(1, 0.2 * cm),
            _tabla_recibos(estado.por_vencer, estado.total_por_vencer),
        ]
    historia += [
        Spacer(1, 0.4 * cm),
        _p(
            "Este certificado se expide a efectos del artículo 9.1.e de la Ley 49/1960, de "
            "Propiedad Horizontal (transmisión del inmueble)."
        ),
        Spacer(1, 1.2 * cm),
        _p("Firma: ______________________________"),
        Spacer(1, 0.3 * cm),
        _p("Nombre y cargo: ______________________________"),
        Spacer(1, 0.8 * cm),
        _p(
            "Documento generado con la aplicación Comunidades. Regla R-DEU-01 pendiente de "
            "validar con un profesional antes de su uso real.",
            PEQUENO,
        ),
    ]
    return _construir(
        historia,
        titulo=f"Certificado de deuda · {inmueble.referencia} · {fecha}",
        pie=f"Certificado de deuda · {datos.comunidad.nombre} · {inmueble.referencia} · "
        f"{_generado()}",
        comprimir=comprimir,
    )
