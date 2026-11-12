# 015 — Celebración de la junta: asistencia, votos y borrador del acta

**Fecha:** 2026-11-12 · **Estado:** aceptada

## Contexto
T4.3: registrar quién asiste, quién puede votar (R-VOT-01), los votos de cada punto y sacar
el resultado (T4.2) y un borrador del acta. Las mayorías se calculan con
`juntas.mayorias.calcular`; aquí se decide con qué datos.

## Decisión
- **Modelos**: `Celebracion` (inicio, convocatoria 1ª/2ª, presidente, secretario, acta cerrada,
  fecha de notificación a los ausentes), `Asistente` (un votante: propietario, cuota,
  presente/representado/ausente, representante, deuda al iniciar y si está impugnada o
  consignada), `VotoEmitido` (asistente × punto) y `Discrepancia` (R-MAY-05).
- **Votantes** (puro, `juntas.servicios.votantes`): cada inmueble vota una vez con su
  coeficiente; con cotitulares vota un representante (art. 15.1), por defecto el primero por
  nombre. Un propietario con varios inmuebles es un votante con la suma de sus cuotas.
- **Al iniciar** (`juntas.celebracion.iniciar_junta`):
  - Se fija la deuda vencida de cada votante con `cobros.deudas` (T3.4): R-VOT-01 se mira
    "en el momento de iniciarse la junta". Se guarda la cifra: la deuda puede cambiar luego,
    el derecho de voto en esa junta no. Si acredita impugnación o consignación, se marca y
    vota.
  - Quórum de 1ª (R-JUN-03) con todos los asistentes; sin quórum, solo se puede iniciar a la
    hora de la segunda convocatoria (`convocatoria_aplicable`, puro).
- **Votos**: solo de asistentes presentes o representados con derecho a voto; un presente sin
  voto cuenta como abstención; volver a votar un punto sustituye sus votos.
- **R-MAY-05**: tras cerrar el acta se anota la fecha de notificación a los ausentes; los
  ausentes pueden discrepar en 30 días naturales; pasado el plazo, el resultado de los puntos
  que lo permiten computa a favor a quienes no discreparon. El resultado se recalcula siempre
  con la fecha de hoy: la misma junta puede pasar de "no aprobado" a "aprobado" el día 31.
- **Acta**: borrador en texto (página y descarga .txt) con lugar, fecha, convocatoria,
  presidente y secretario, asistentes y representados con su cuota, ausentes, **privados de
  voto** (lo exige el art. 15.2) y cada punto con su recuento y la explicación de T4.2.
  "Cerrar el acta" congela asistencia y votos (art. 19: se cierra con las firmas).
- Permisos: `juntas.add_celebracion` (iniciar), `juntas.add_votoemitido` (votar,
  impugnación, discrepancias), `juntas.change_celebracion` (cerrar, notificar).

## Consecuencias
- El contenido del art. 19 se ha tomado de un resumen, no del texto literal: revisar el
  borrador del acta con el BOE y un profesional antes de usarlo.
- Elegir otro representante para los cotitulares existe en el servicio, pero no en la web.
- No hay libro de actas, firma electrónica ni envío del acta por email a los propietarios.
- La asistencia no se puede corregir una vez iniciada la junta (habría que repetir el inicio).
