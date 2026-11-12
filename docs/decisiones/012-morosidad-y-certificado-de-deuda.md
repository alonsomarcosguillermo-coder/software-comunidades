# 012 — Morosidad y certificado de deuda en PDF (ReportLab)

**Fecha:** 2026-11-12 · **Estado:** aceptada

## Contexto
T3.4: un informe de morosos y el certificado de deuda que pide el vendedor de un inmueble
(R-DEU-01, art. 9.1.e LPH), los dos en PDF. Hay que decidir qué es "deuda" con los datos que
ya existen (recibos, cobros conciliados en T3.2; las devoluciones son la T3.3, en paralelo) y
con qué generar los PDF.

## Decisión
- **La deuda se calcula, no se guarda**: igual que el saldo contable. Deuda en una fecha =
  recibos cuyo vencimiento es anterior a esa fecha y que no estaban cobrados en ella. Cobrado
  = un movimiento del banco conciliado lo paga, y cuenta la fecha de ese movimiento. Así se
  puede pedir el estado de deudas a cualquier fecha pasada.
- **Cálculo puro** en `cobros.morosidad` (dataclasses `ReciboDeuda` → informe / estado de
  deuda, con tests de propiedades); `cobros.deudas` lee la base de datos en una consulta (la
  fecha de cobro llega por la relación inversa `cobro`, sin importar la app `bancos`).
- **Informe de morosos por propietario** (el pagador del recibo); **certificado por inmueble**,
  con todos sus recibos aunque los pagara un titular anterior, y con los recibos emitidos que
  aún no vencen aparte (no son deuda, pero al comprador le interesa saberlo).
- **PDF con ReportLab** (nueva dependencia `reportlab`): se instala con pip en Windows sin
  nada más y maqueta tablas que saltan de página solas. Descartadas: WeasyPrint (HTML → PDF,
  muy cómodo, pero necesita las librerías nativas de GTK/Pango en Windows) y xhtml2pdf (usa
  ReportLab por debajo y entiende poco CSS). Fuente Helvetica estándar: tiene tildes, ñ y €.
- **Los PDF no se guardan**: se generan al pedirlos (`inline`, el navegador los abre). Ver
  y descargar exige `cobros.view_recibo` (son datos personales de deuda).
- Una fecha futura no se admite: la deuda de mañana aún no se conoce.

## Consecuencias
- Un recibo remesado cuyo extracto no se ha conciliado todavía sale como deuda (marcado como
  "remesado"). Es lo prudente, pero obliga a conciliar antes de certificar.
- Cuando llegue T3.3, un recibo devuelto tendrá que contar como no cobrado en
  `cobros.deudas.recibos_deuda` (hay un comentario en ese punto).
- No queda registro de los certificados emitidos (número, fecha, quién lo pidió). Si hace
  falta, se añadirá un modelo que guarde el PDF, como `Remesa` guarda su XML.
- El certificado deja en blanco la firma y el cargo: quién firma está pendiente de validar.
