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

Interpretación aplicada en T2.3 (pendiente de validar con un profesional):
- Un grupo de reparto usa los coeficientes generales de sus inmuebles (en proporción a lo que
  sumen entre ellos) o unos propios, que entonces se fijan para todos sus inmuebles.
- Una derrama se reparte por coeficiente entre todos los inmuebles o entre los de un grupo, y
  cada parte se divide en plazos iguales (R-REP-02 en los dos pasos).
- Preguntas: ¿qué mayoría hace falta para acordar una derrama, y debe constar el acuerdo antes
  de emitirla? ¿Puede repartirse de otra forma (p. ej. a partes iguales, sin coeficiente)?
  ¿Quién paga los plazos que vencen después de vender el inmueble?

## Presupuesto y fondo de reserva
- **R-RES-01** ⚠️ La comunidad debe tener un fondo de reserva no inferior al 10 % de su último
  presupuesto ordinario (art. 9.1.f LPH).
- **R-PRE-01** ⚠️ El presupuesto ordinario se aprueba en la junta ordinaria anual (art. 16.1 LPH).

Interpretación aplicada en T2.1 (pendiente de validar con un profesional):
- "Último presupuesto ordinario" = el aprobado del ejercicio más reciente; un borrador no cuenta.
- La base del 10 % es la suma de las partidas de gasto, SIN la aportación al fondo de reserva.
  Pregunta: ¿se incluye la aportación? ¿Y los ingresos que no son cuotas?
- El mínimo se redondea hacia arriba al céntimo (es un mínimo: "no inferior").
- El fondo es el saldo acreedor de la cuenta contable marcada como fondo de reserva.

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

Interpretación aplicada en T4.1 (texto consolidado de la LPH en el BOE, actualizado el
03/10/2026; pendiente de validar con un profesional):
- R-JUN-02: "con seis días de antelación" se cuenta en días naturales completos entre la
  citación y la junta, sin contar ninguno de los dos (citada el día 1, junta el 8 o después).
  Es la lectura más prudente. Pregunta: ¿basta con 6 días contando el de la junta?
- R-JUN-02: para la extraordinaria la ley pide "la antelación que sea posible para que pueda
  llegar a conocimiento de todos los interesados" (art. 16.3); el sistema solo exige que sea
  un día posterior a la citación.
- R-JUN-03: en primera convocatoria hace falta que asistan la mayoría de los propietarios que
  representen a su vez la mayoría de las cuotas; si no, segunda convocatoria sin quórum, en el
  mismo lugar, y puede ser el mismo día si ha pasado media hora (art. 16.2).
- La convocatoria la hace el presidente (o los promotores) e indica asuntos, lugar, día y hora
  (art. 16.2).
- Art. 16.2: la convocatoria debe incluir la relación de propietarios que no estén al
  corriente de pago y advertir de la privación del voto (R-VOT-01). Se calcula el día de la
  citación con el informe de morosos de T3.4. Pregunta: encaje con protección de datos al
  enviarla por email.
- Se cita a todos los titulares (y cotitulares) el día de la citación. La forma de citar es
  la del art. 9 (domicilio comunicado, el propio piso o el tablón): el sistema envía email a
  quien lo tiene y lista a los demás para citarlos a mano.
- R-JUN-04 (telemáticas) sigue sin documentar: la v1 no las contempla.

## Morosidad
- **R-DEU-01** ⚠️ En la venta de un inmueble, el vendedor debe aportar certificado de la comunidad
  sobre el estado de deudas (art. 9.1.e LPH). El sistema genera ese certificado.
- **R-DEU-02** ⚠️ La deuda puede reclamarse por procedimiento monitorio con certificado del acuerdo
  de liquidación (art. 21 LPH). El sistema prepara la documentación, no la presenta.

Interpretación aplicada en T3.4 (pendiente de validar con un profesional):
- Deuda en una fecha = recibos vencidos (vencimiento anterior a esa fecha; el mismo día aún se
  puede pagar) y no cobrados en ella. Cobrado = conciliado con un movimiento del banco de esa
  fecha o anterior. Un recibo remesado sin conciliar todavía cuenta como deuda.
- Moroso = propietario con deuda; cada recibo es deuda de su pagador (el titular en el
  vencimiento). El informe de morosos agrupa por propietario.
- El certificado R-DEU-01 es por inmueble: recoge toda la deuda vencida del inmueble, también
  la de titulares anteriores, y menciona aparte los recibos emitidos que aún no han vencido.
  No incluye el NIF de los titulares; deja en blanco la firma y el cargo.
- Preguntas: ¿quién firma el certificado (secretario con el visto bueno del presidente)?
  ¿Debe limitarse la deuda que afecta al inmueble a la del año en curso y los tres anteriores
  (afección real, art. 9.1.e LPH) o recoger toda? ¿Cuenta como deuda un recibo remesado cuyo
  cobro aún no consta? ¿Hay que llevar un registro numerado de certificados emitidos?

## Cobros SEPA (pendiente de detallar en la Fase 2)
- **R-SEPA-01** ⚠️ Domiciliar un recibo exige un mandato SEPA firmado (identificador de mandato y
  fecha de firma) por cada titular de cuenta.

Interpretación aplicada en T2.4 (pendiente de validar con un profesional):
- El deudor del mandato es el titular de la cuenta, que puede no ser el propietario. Un
  mandato por cuenta; si la cuenta tiene varios titulares, no se modela que firmen todos.
- Un recibo lo paga el titular del inmueble en la fecha de vencimiento. Con cotitulares,
  el que tenga mandato vigente (o el primero). Pregunta: ¿se emite a nombre de todos? Ver
  también la pregunta sobre representante del inmueble en `PLAN.md`.
- Un mandato firmado no se modifica: si cambia la cuenta, baja y mandato nuevo.
- Pendiente: caducidad del mandato sin uso (el EPC habla de 36 meses) y preaviso al deudor.
- **R-SEPA-02** ⚠️ La remesa se genera en formato ISO 20022 pain.008 (esquema básico CORE).
  Detalle de versión y plazos de presentación a definir con la documentación del banco.

Interpretación aplicada en T2.5 (pendiente de validar con la documentación del banco):
- Versión pain.008.001.02 (base del Cuaderno 19.14 XML de la AEB), validada contra su XSD.
- FRST para el primer cobro con un mandato y RCUR para los siguientes. Pregunta: ¿el banco
  acepta RCUR también en el primero (permitido por el EPC desde 2016)?
- Solo se exige que la fecha de cobro sea posterior a hoy. Pendiente: antelación mínima de
  presentación (D-1 hábil en CORE según el EPC) y calendario TARGET2 de días hábiles.
- Un recibo entra en la remesa si vence hasta la fecha de cobro y su pagador tiene mandato
  vigente en esa fecha.
