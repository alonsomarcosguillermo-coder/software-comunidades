# 010 — Conciliación bancaria: importe + referencia, y manual

**Fecha:** 2026-11-12 · **Estado:** aceptada

## Contexto
T3.2: explicar en la contabilidad cada movimiento importado del banco (T3.1) y saber qué
recibos están cobrados. Es la base de la morosidad (T3.3, T3.4) y de R-VOT-01. No es una
regla legal (no hay ID en `DOMINIO.md`), pero un error aquí da por pagado a quien debe.

## Decisión
- **Conciliar = registrar el asiento del movimiento** y enlazarlo:
  - Abono que paga recibos: **572 Banco al Debe / 430 Propietarios al Haber**, un apunte
    por recibo (con su referencia). Los recibos pasan a **cobrados**.
  - Cualquier otro movimiento: asiento entre 572 y la cuenta que elija la persona (gasto,
    comisión, intereses...). No se permite contra 572 ni contra 430: lo que deben los
    propietarios solo baja cobrando recibos concretos (si no, la morosidad no cuadraría).
  - El asiento lleva la fecha de operación del movimiento.
- **Automática solo si no hay dudas** (`bancos.servicios.proponer_conciliaciones`, pura):
  - Recibos: el movimiento menciona sus referencias `REC-<comunidad>-<nº>` (en las
    referencias o en los conceptos, como palabra completa: `REC-1-1` no casa con `REC-1-12`)
    y el importe es exactamente su suma.
  - Remesa: el movimiento menciona su identificador (`MsgId`) y el importe es exactamente el
    total de la remesa, con todos sus recibos aún sin cobrar.
  - Si un movimiento encaja de dos formas o dos movimientos reclaman el mismo recibo, no se
    concilia ninguno. Solo abonos. Importe distinto (pago parcial, remesa con rechazos) →
    manual. Conciliar mal es peor que dejar un movimiento pendiente.
- **Manual**: la persona elige los recibos (la suma debe cuadrar al céntimo) o una cuenta.
- **Modelos**: `Conciliacion` (movimiento ↔ asiento, uno a uno; remesa o cuenta opcionales;
  automática sí/no; quién) y `CobroRecibo` (recibo ↔ conciliación). La BD impide conciliar
  dos veces un movimiento o cobrar dos veces un recibo. `Movimiento` y `Recibo` no cambian:
  el estado "cobrado" sale de la relación (`Recibo.esta_cobrado`), sin que `cobros`
  importe `bancos`.
- **Deshacer**: contra-asiento fechado hoy (la contabilidad conserva los dos asientos) y se
  borra la conciliación, con lo que el movimiento y sus recibos vuelven a pendientes. El
  rastro queda en los asientos; la tabla de conciliaciones refleja solo el estado actual.
- Permisos: `bancos.add_conciliacion` (conciliar) y `bancos.delete_conciliacion` (deshacer).

## Consecuencias
- Sin pagos parciales: un recibo está cobrado entero o no. Un vecino que paga de menos se
  queda pendiente (o se concilia contra otra cuenta, que no reduce su deuda).
- `CobroRecibo.recibo` es único: las devoluciones (T3.3) tendrán que permitir un recibo
  cobrado, devuelto y vuelto a cobrar.
- Que el banco ponga el `MsgId` de la remesa en el concepto del abono es lo habitual pero
  no está garantizado; si no lo pone, la remesa se concilia a mano.
- Se depende de que el vecino escriba la referencia del recibo en la transferencia. Más
  adelante se podría proponer (no conciliar) por importe + nombre del ordenante.
