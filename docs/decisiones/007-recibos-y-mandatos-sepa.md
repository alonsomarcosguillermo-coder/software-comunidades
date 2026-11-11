# 007 — Recibos y mandatos SEPA

**Fecha:** 2026-11-11 · **Estado:** aceptada

## Contexto
T2.4: de las cuotas emitidas (T2.2, T2.3) hay que sacar recibos para cobrarlos, y para
domiciliarlos hace falta un mandato SEPA firmado (R-SEPA-01). Las cuotas son del inmueble;
el recibo lo paga una persona. Los IBAN son datos personales.

## Decisión
- **`Recibo`**: uno por cuota ordinaria o de derrama (`OneToOne`, exactamente una de las dos,
  comprobado en la BD), con número correlativo por comunidad y referencia `REC-<com>-<nº>`
  (será el EndToEndId de la remesa). Inmutable una vez creado. No genera asiento: la deuda ya
  está en la 430 desde la emisión. Única puerta: `cobros.recibos.generar_recibos`, que se
  puede repetir sin duplicar.
- **Pagador** = titular del inmueble en la fecha de vencimiento. Con cotitulares, el primero
  que tenga mandato vigente; si ninguno, el primero (`elegir_pagador`, función pura). Sin
  titular, no hay recibo: se avisa y se recoge en la siguiente generación.
- **`Mandato`**: comunidad + propietario + referencia única (UMR) + titular de la cuenta +
  IBAN + fecha de firma; baja con `fecha_baja`. Como mucho uno activo por propietario y
  comunidad (restricción en la BD). Firmado, no se modifica: si cambia la cuenta, se da de baja
  y se firma otro (así no hace falta gestionar "modificaciones de mandato" en la remesa).
- **Comunidad acreedora**: `iban_cobros` y `sufijo_acreedor` en `Comunidad`; el identificador
  de acreedor (AT-02) se calcula del NIF (`cobros.sepa.identificadores`, puro, probado con el
  ejemplo oficial del EPC). `fincas` importa ese módulo puro de `cobros` para validar el IBAN.
- **IBAN**: validación mod-97; se guarda normalizado; nunca en `__str__`, mensajes de error ni
  pantallas (solo `ES12 •••• 1234`). El completo solo se ve en la ficha del admin.

## Consecuencias
- El estado del recibo (pendiente, remesado, cobrado, devuelto) no es un campo editable: sale
  de sus relaciones (remesa en T2.5; cobros y devoluciones en la Fase 3).
- Las reglas de cotitulares y "deudor = titular de la cuenta" son interpretaciones pendientes
  de validar (ver DOMINIO.md).
