# 004 — Presupuesto ordinario y fondo de reserva (app `cobros`)

**Fecha:** 2026-11-11 · **Estado:** aceptada

## Contexto
T2.1 pide el presupuesto anual por comunidad con sus partidas y la regla R-RES-01 (fondo de
reserva ≥ 10 % del último presupuesto ordinario). Del presupuesto saldrán las cuotas (T2.2),
así que una vez aprobado no debe cambiar a escondidas. El saldo del fondo no puede guardarse
en un campo (CLAUDE.md: los saldos se calculan a partir de los apuntes).

## Decisión
- **App `cobros`** (prevista en CLAUDE.md para la Fase 2): `Presupuesto` (comunidad,
  ejercicio, fecha de aprobación, aportación al fondo de reserva) y `Partida` (concepto,
  importe). Un presupuesto por comunidad y ejercicio.
- **Aprobado = tiene fecha de aprobación** (R-PRE-01; la junta llegará en la Fase 4). Aprobado,
  sus importes son fijos: `save()`/`delete()` de presupuesto y partidas lo impiden, y el admin
  los muestra en solo lectura. Se permite quitar la fecha para corregir un error.
- **Fondo de reserva = saldo acreedor de una cuenta contable marcada** con
  `Cuenta.es_fondo_reserva` (como mucho una por comunidad, restricción en la BD). Se marca en
  vez de fijar un código porque los códigos de cuenta son texto libre.
- **R-RES-01 como función pura** (`cobros.servicios.estado_fondo_reserva`). El mínimo se
  redondea **hacia arriba** al céntimo, no con ROUND_HALF_UP: es un mínimo legal y redondear
  hacia abajo lo incumpliría. Base: la suma de las partidas (sin la aportación al fondo);
  pendiente de validar (ver DOMINIO.md).
- "Último presupuesto ordinario" = el aprobado del ejercicio más reciente.

## Alternativas descartadas
- Campo `saldo_fondo_reserva` en la comunidad: es un saldo guardado, prohibido.
- Fijar el código de cuenta (p. ej. 113): sin un plan de cuentas por defecto sería inventar.
- Inmutabilidad con triggers de PostgreSQL, como en contabilidad: aquí basta Python; la
  contabilidad es la que no puede descuadrarse.

## Consecuencias
- La protección de presupuestos aprobados es solo en Python: un `QuerySet.update()` de
  partidas o SQL a mano la esquivan (el borrado masivo de presupuestos sí está cubierto).
- T2.2 deberá impedir quitar la aprobación a un presupuesto del que ya se emitieron cuotas.
