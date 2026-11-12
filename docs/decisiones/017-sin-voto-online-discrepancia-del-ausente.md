# 017 — Sin voto online: discrepancia del ausente desde el portal

**Fecha:** 2026-11-12 · **Estado:** aceptada

## Contexto
T5.2 se planteó como "votación online del vecino". Antes de programarla se consultó el texto
consolidado de la LPH en el BOE (actualizado el 03/10/2026): no menciona juntas telemáticas,
videoconferencia, medios electrónicos ni voto anticipado o a distancia. Solo prevé asistir en
persona o representado (art. 15.1), votar en la junta, y que los ausentes comuniquen su
discrepancia en 30 días naturales "por cualquier medio que permita tener constancia de la
recepción" (art. 17.8). La regla R-JUN-04 de `DOMINIO.md` decía lo contrario y se ha
corregido. Un voto online con efectos legales sería inventar una regla (CLAUDE.md), así que
se ha preguntado al usuario.

## Decisión
- **No hay voto online.** T5.2 implementa lo que la ley sí ampara: la **discrepancia online
  del ausente** (R-MAY-05).
- En el portal, en la junta a la que no asistió, el vecino ve los acuerdos notificados, el
  plazo (30 días naturales desde la notificación) y, en cada acuerdo que computa ausentes, el
  botón "No estoy de acuerdo".
- **Constancia de la recepción**: `Discrepancia` guarda el canal (`portal` o `despacho`) y la
  fecha y hora de recepción, y se envía al vecino un acuse por email que sirve de
  justificante. El despacho ve el canal y la hora en la página de la celebración.
- Las reglas de fondo (ausente, notificado, en plazo, sin repetir) son las de
  `juntas.celebracion.registrar_discrepancia` (T4.3); el portal solo añade quién es el usuario
  y que el punto admita discrepancia. El resultado de R-MAY-05 se recalcula solo.

## Consecuencias
- Si en el futuro un profesional confirma una vía para la participación telemática (estatutos,
  normativa autonómica, reforma legal), habrá que añadir la regla a `DOMINIO.md` antes de
  programarla.
- Pregunta abierta: ¿basta el registro + acuse como constancia, o hay que notificarlo además
  al secretario de la comunidad?
- La notificación de los acuerdos a los ausentes sigue siendo manual (se anota la fecha); no se
  envía por email desde la aplicación.
