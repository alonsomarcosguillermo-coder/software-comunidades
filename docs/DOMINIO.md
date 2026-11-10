# Reglas de dominio

Cada regla tiene un ID que se cita en el código y en los tests. Estado:
- ✅ **validada** con un profesional (administrador de fincas / abogado)
- ⚠️ **verificar**: redactada a partir de la LPH, pendiente de validar. Se puede implementar para
  aprender, pero no usar con dinero o comunidades reales sin validarla.

Ninguna regla está validada todavía. Antes de cualquier uso real, revisar todas.

## Coeficientes y repartos
- **R-COEF-01** ⚠️ Cada inmueble tiene una cuota de participación (coeficiente) fijada en el título
  constitutivo (art. 5 LPH). Los coeficientes de una comunidad suman exactamente 100 %.
- **R-REP-01** ⚠️ Los gastos generales se reparten según el coeficiente, salvo que los estatutos o un
  acuerdo excluyan a ciertos inmuebles de ciertos gastos (p. ej. locales sin acceso al ascensor).
  Art. 9.1.e LPH. El sistema debe permitir "grupos de reparto" con sus propios coeficientes.
- **R-REP-02** (regla técnica, no legal) Al repartir un importe, se redondea cada parte a céntimos y
  los céntimos sobrantes se asignan uno a uno a los inmuebles con mayor parte decimal descartada
  (método del resto mayor). Empates: por orden de identificador. La suma siempre cuadra.

## Presupuesto y fondo de reserva
- **R-RES-01** ⚠️ La comunidad debe tener un fondo de reserva no inferior al 10 % de su último
  presupuesto ordinario (art. 9.1.f LPH).
- **R-PRE-01** ⚠️ El presupuesto ordinario se aprueba en la junta ordinaria anual (art. 16.1 LPH).

## Juntas y votaciones
- **R-JUN-01** ⚠️ Junta ordinaria al menos una vez al año (art. 16.1 LPH).
- **R-JUN-02** ⚠️ Convocatoria de junta ordinaria con al menos 6 días de antelación; extraordinarias
  con la antelación suficiente para que llegue a todos (art. 16.3 LPH).
- **R-JUN-03** ⚠️ Primera y segunda convocatoria: reglas de quórum distintas (art. 16.2 LPH).
- **R-VOT-01** ⚠️ Un propietario que no esté al corriente de pago de las deudas vencidas con la
  comunidad puede asistir pero no votar, salvo que haya impugnado judicialmente o consignado la
  deuda (art. 15.2 LPH).
- **R-MAY-01** ⚠️ Doble mayoría: los acuerdos se cuentan por número de propietarios Y por suma de
  coeficientes; ambas condiciones deben cumplirse.
- **R-MAY-02** ⚠️ Mayoría simple de presentes en segunda convocatoria para acuerdos ordinarios
  (art. 17.7 LPH), siempre que representen más de la mitad del valor de las cuotas de los presentes.
- **R-MAY-03** ⚠️ Mayorías reforzadas (3/5 de propietarios y cuotas) para ciertos asuntos (art. 17.3 LPH).
- **R-MAY-04** ⚠️ Unanimidad para modificar el título constitutivo o los estatutos (art. 17.6 LPH).
- **R-MAY-05** ⚠️ Los propietarios ausentes debidamente citados, a los que se notifique el acuerdo
  y no manifiesten su discrepancia en el plazo legal (30 días naturales), se computan como votos
  favorables (art. 17.8 LPH).
- **R-JUN-04** ⚠️ Juntas y votaciones telemáticas: permitidas tras la reforma de 2022 bajo ciertas
  condiciones. Requisitos exactos pendientes de documentar antes de la Fase 4.

## Morosidad
- **R-DEU-01** ⚠️ En la venta de un inmueble, el vendedor debe aportar certificado de la comunidad
  sobre el estado de deudas (art. 9.1.e LPH). El sistema genera ese certificado.
- **R-DEU-02** ⚠️ La deuda puede reclamarse por procedimiento monitorio con certificado del acuerdo
  de liquidación (art. 21 LPH). El sistema prepara la documentación, no la presenta.

## Cobros SEPA (pendiente de detallar en la Fase 2)
- **R-SEPA-01** ⚠️ Domiciliar un recibo exige un mandato SEPA firmado (identificador de mandato y
  fecha de firma) por cada titular de cuenta.
- **R-SEPA-02** ⚠️ La remesa se genera en formato ISO 20022 pain.008 (esquema básico CORE).
  Detalle de versión y plazos de presentación a definir con la documentación del banco.
