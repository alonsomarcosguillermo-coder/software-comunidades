# 013 — Convocatoria de juntas

**Fecha:** 2026-11-12 · **Estado:** aceptada

## Contexto
T4.1: preparar y convocar juntas de propietarios (orden del día, plazos R-JUN-02 y R-JUN-03,
envío por email). Se ha leído el texto consolidado de la LPH en el BOE (actualizado el
03/10/2026), arts. 15, 16 y 17, para concretar las reglas; ver `DOMINIO.md`.

## Decisión
- **Nueva app `juntas`**. `Junta` (tipo, primera y segunda convocatoria, lugar, quién
  convoca), `PuntoOrden` (asunto, detalle, mayoría que necesita y si computa ausentes) y
  `Citacion` (un propietario citado, el email al que se envió y si estaba en la relación de
  morosos).
- **Borrador → convocada**: `juntas.convocatoria.convocar` es la única forma. Desde entonces
  la junta y su orden del día no cambian (lo impiden `save()` y `delete()` del modelo, también
  desde el admin): es lo que se comunicó. Si hay que cambiarla, se convoca otra.
- **Plazos puros** (`juntas.servicios`): R-JUN-02 con días naturales completos (lectura
  prudente) y R-JUN-03 con media hora mínima entre convocatorias.
- **A quién se cita**: a todos los titulares (también cotitulares) de algún inmueble de la
  comunidad el día de la citación.
- **Relación de morosos** (art. 16.2 LPH): sale de `cobros.deudas.informe_morosos_de` (T3.4)
  en la fecha de la citación, va en el texto con la advertencia de R-VOT-01 y queda marcada
  en cada citación. Que voten o no se decide al iniciarse la junta (T4.3).
- **Email**: un mensaje por propietario (nadie ve las direcciones de los demás), con el texto
  de una plantilla (`juntas/convocatoria.txt`), que también se ve como vista previa antes de
  convocar. En desarrollo los emails salen por consola (`EMAIL_BACKEND`); en producción se
  configura SMTP con variables de entorno. Los propietarios sin email se listan para citarlos
  por otro medio (art. 9 LPH).
- **Todo en una transacción**: si el envío falla, no queda nada convocado.

## Consecuencias
- Si el servidor de correo acepta unos mensajes y falla con otros, la transacción se deshace
  aunque algunos emails ya hayan salido. Con volumen real convendría una cola de envíos.
- No hay acuse de recibo ni registro de la citación por otros medios (tablón, domicilio).
- Mandar por email la relación de morosos a todos los vecinos lo exige el art. 16.2, pero
  conviene revisarlo con protección de datos (AEPD) antes de un uso real.
- R-JUN-01 (al menos una ordinaria al año) no se controla todavía.
- Las juntas telemáticas (R-JUN-04) no están modeladas.
