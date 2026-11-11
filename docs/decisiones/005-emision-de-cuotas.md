# 005 — Emisión de cuotas ordinarias: reparto en dos pasos y asiento por emisión

**Fecha:** 2026-11-11 · **Estado:** aceptada

## Contexto
T2.2: del presupuesto aprobado (T2.1) salen las cuotas de cada periodo, con su asiento.
Hay que decidir cómo dividir el total entre inmuebles y periodos sin perder céntimos, y cómo
contabilizarlo, sabiendo que parte del dinero es aportación al fondo de reserva (R-RES-01).

## Decisión
- **Periodicidad en el presupuesto** (`periodos`: 1, 2, 4 o 12; por defecto trimestral). Se
  fija al aprobarlo, como los importes.
- **Reparto en dos pasos, ambos con R-REP-02** (`cobros.servicios.plan_de_cuotas`):
  1. total anual (gastos + aportación) entre inmuebles, por coeficiente;
  2. la parte anual de cada inmueble, a partes iguales entre los periodos (los céntimos
     sobrantes, a los primeros periodos).
  Así cada inmueble paga en el año exactamente su parte y el total cuadra al céntimo. Se
  descartó repartir primero entre periodos y luego entre inmuebles: el total también
  cuadraría, pero la suma anual de un inmueble podría desviarse unos céntimos de su parte.
- **Una emisión por periodo** (`Emision`, única por presupuesto y periodo) con una `Cuota`
  por inmueble. Las cuotas de 0 € (coeficientes diminutos) no se crean. Emisión y cuotas son
  inmutables, como su asiento.
- **Asiento de la emisión**: Debe 430 Propietarios (una línea por inmueble, con su referencia
  como concepto) / Haber 705 Cuotas ordinarias (parte de gastos) y Haber cuenta del fondo de
  reserva (parte de aportación). La separación se calcula sobre lo **acumulado** del año
  (`desglose_del_periodo`), para que al emitir todos los periodos el fondo reciba exactamente
  la aportación presupuestada.
- Las cuentas 430 y 705 se crean si la comunidad no las tiene (son las que ya usaba la demo).
  La del fondo debe estar marcada (`es_fondo_reserva`); si falta y hay aportación, no se emite.
- Única puerta de entrada: `cobros.emision.emitir_cuotas`, en una transacción, con
  `SELECT ... FOR UPDATE` sobre el presupuesto para que dos emisiones simultáneas del mismo
  periodo no se dupliquen (además de la restricción única en la BD).
- Se niega si el presupuesto no está aprobado (R-PRE-01) o si los coeficientes no suman 100 %
  (R-COEF-01). Con cuotas emitidas, el presupuesto ya no puede perder la aprobación.

## Consecuencias
- Las cuotas son del inmueble, no del propietario: quién paga (titular en la fecha) se
  resolverá al generar recibos (T2.4).
- El plan se recalcula en cada emisión con los coeficientes del momento: si cambian a mitad
  de año, la suma anual de un inmueble ya no será exactamente su parte.
- No hay todavía forma de anular una emisión (habría que hacer un contra-asiento y marcarla).
