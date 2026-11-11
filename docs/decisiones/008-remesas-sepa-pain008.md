# 008 — Remesas SEPA: pain.008.001.02 validado contra el XSD

**Fecha:** 2026-11-11 · **Estado:** aceptada

## Contexto
T2.5: generar el fichero de adeudos directos que el administrador sube a la banca online
(R-SEPA-02). DOMINIO.md deja abiertas la versión del formato y los plazos. Un fichero mal
formado lo rechaza el banco, a veces días después; un fichero bien formado pero con datos
equivocados cobra dinero a quien no debe.

## Decisión
- **Versión pain.008.001.02** (ISO 20022, 2009): es la base del "Cuaderno 19.14 XML" de la
  banca española y la que aceptan todos los bancos. Las versiones nuevas (p. ej. .001.08) se
  podrán añadir si el banco las pide. Esquema CORE, `ChrgBr` SLEV, bancos sin BIC
  ("NOTPROVIDED": basta el IBAN desde 2016).
- **XSD oficial en el repositorio** (`cobros/sepa/pain.008.001.02.xsd`, sacado del paquete
  `sepaxml` 2.6.1; es el generado por SWIFTStandards en 2009, sin cambios). **Cada remesa se
  valida con `lxml` antes de guardarse**: si no cumple el esquema, no se crea nada. Nueva
  dependencia: `lxml`.
- **Generación pura** (`cobros.sepa.pain008`): dataclasses → bytes. Un bloque `PmtInf` por tipo
  de secuencia: **FRST** si es el primer cobro con ese mandato, **RCUR** después. Textos
  pasados al juego de caracteres SEPA (`texto_sepa`).
- **`Remesa` inmutable que guarda el XML exacto**: se puede volver a descargar idéntico y queda
  constancia de lo que se envió. `MsgId` único (`REM<com>-<nº>-<fecha y hora>`); cada recibo
  va con su referencia como `EndToEndId`, para conciliar después (T3.2).
- **Qué entra**: recibos pendientes que vencen hasta la fecha de cobro y cuyo pagador tiene un
  mandato vigente **en la fecha de cobro** (R-SEPA-01). El recibo guarda la remesa, el mandato
  usado y la secuencia (restricción en la BD: los tres o ninguno).
- La fecha de cobro debe ser posterior a hoy. Los plazos exactos (antelación mínima de
  presentación) quedan pendientes de la documentación del banco.
- Descargar el fichero exige el permiso `cobros.view_remesa`: lleva los IBAN completos.

## Consecuencias
- No hay forma de anular una remesa (p. ej. si el banco la rechaza entera): habría que
  desmarcar sus recibos. Las devoluciones de recibos sueltos son la T3.3.
- La remesa no genera asiento; el cobro se contabiliza al conciliar el extracto (T3.2).
- El XSD solo comprueba la forma; las reglas del EPC (p. ej. un mandato no puede ir dos veces
  como FRST) dependen de nuestra lógica y de los tests.
