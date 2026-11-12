# 011 — Devoluciones de recibos

**Fecha:** 2026-11-12 · **Estado:** aceptada

## Contexto
T3.3: un recibo domiciliado se cobra con la remesa (T2.5, T3.2), pero el banco del
propietario puede devolverlo días o semanas después (falta de fondos, cuenta cancelada,
orden del deudor...). En el extracto llega como un **cargo**, normalmente con concepto común
14 ("Devoluciones e impagados") y con la referencia del recibo (el `EndToEndId` de la
remesa). El recibo vuelve a ser deuda del propietario (base de T3.4 y de R-VOT-01). No es una
regla legal: no hay ID en `DOMINIO.md`.

## Decisión
- **Una devolución es la conciliación de un cargo** (`bancos.conciliacion.conciliar_devolucion`):
  asiento **430 Propietarios (Debe, un apunte por recibo) / 572 Banco (Haber)**. Es el
  asiento del cobro al revés: sale dinero del banco y el propietario vuelve a deberlo.
- **Modelo `Devolucion`**: recibo + conciliación del cargo + conciliación del **cobro** que se
  deshace. Al crearla **se borra el `CobroRecibo`** del recibo. Así:
  - "Sin cobrar" sigue siendo `cobro__isnull=True` (la misma consulta de T3.2): un recibo
    devuelto cuenta como deuda sin que nadie más tenga que saber de devoluciones.
  - El recibo se puede volver a cobrar (p. ej. por transferencia) con otro movimiento.
  - Estado `Recibo.estado == "devuelto"`: sin cobro ahora, con alguna devolución.
- **Solo se devuelven recibos cobrados**, y el importe del cargo tiene que ser exactamente la
  suma de los recibos. Si el banco mete su comisión en el mismo cargo, no cuadra: se concilia
  contra una cuenta y la devolución se registra aparte. (Normalmente la comisión va en un
  cargo propio, que se concilia contra 626.)
- **Automática**, mismo criterio que T3.2 con el signo al revés: el cargo menciona las
  referencias de recibos cobrados e importe exacto; ante dudas, nada. Un solo botón concilia
  primero los cobros y después las devoluciones, así que el abono de una remesa y la
  devolución de uno de sus recibos pueden llegar en el mismo extracto.
- **Deshacer**:
  - Un cobro con recibos devueltos no se puede deshacer (primero la devolución); además
    `Devolucion.cobro` es PROTECT.
  - Deshacer una devolución: contra-asiento y se restaura el `CobroRecibo` original. Si el
    recibo ya se ha vuelto a cobrar, primero hay que deshacer ese cobro.

## Consecuencias
- Los gastos de la devolución (comisión del banco) los paga la comunidad. Repercutirlos al
  propietario depende de estatutos o acuerdos: pregunta pendiente para `DOMINIO.md`.
- Un recibo devuelto no vuelve a entrar en una remesa (`crear_remesa` solo coge recibos sin
  remesa). Volver a presentarlo al cobro queda pendiente.
- El motivo de la devolución (códigos SEPA como AM04 o MD06) no se guarda aparte: queda en
  los conceptos del movimiento.
