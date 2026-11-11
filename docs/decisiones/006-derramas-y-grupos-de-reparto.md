# 006 — Derramas y grupos de reparto

**Fecha:** 2026-11-11 · **Estado:** aceptada

(El número 005 lo usa la emisión de cuotas ordinarias, T2.2, hecha en paralelo.)

## Contexto
T2.3 pide derramas: un importe total, cobrado en plazos y repartido entre todos los inmuebles
o solo entre un grupo (R-REP-01: "grupos de reparto con sus propios coeficientes"). Hasta
ahora no existían los grupos. De las derramas saldrán recibos (T2.4), así que, igual que las
cuotas ordinarias, su reparto no debe cambiar una vez cobrado.

## Decisión
- **Grupos de reparto en `fincas`** (`GrupoReparto` + `MiembroGrupo`): son datos de la
  comunidad, no de cobros, y los podrán usar también las partidas del presupuesto. Cada
  miembro tiene un **coeficiente propio opcional**: vacío = su coeficiente general. Se
  rellena en todos o en ninguno (`fincas.servicios.coeficientes_de_grupo`), porque mezclar
  porcentajes del edificio con porcentajes del grupo no tiene sentido. Los coeficientes del
  grupo no tienen que sumar 100: `repartir` ya reparte en proporción a lo que sumen.
- **`Derrama` en `cobros`**: importe, plazos, primer vencimiento, meses entre plazos, grupo
  (vacío = todos) y fecha del acuerdo (vacía = propuesta). Se edita libremente hasta que se
  emite.
- **Emitir = fijar todo de una vez** (`cobros.derramas.emitir_derrama`): crea las
  `CuotaDerrama` (inmueble × plazo, con su vencimiento; inmutables) y un único asiento por el
  total: Debe 430 Propietarios (una línea por inmueble) / Haber 706 Derramas. La deuda nace
  del acuerdo; los plazos solo dicen cuándo vence cada parte. Así el reparto queda fijo
  aunque luego cambien el grupo o los coeficientes. Una derrama emitida no se cambia ni se
  borra.
- **Cálculo en dos pasos con R-REP-02** (`cobros.servicios.plan_de_derrama`): el importe
  entre los inmuebles por coeficiente; la parte de cada uno, en plazos iguales (los céntimos
  sobrantes, a los primeros plazos). Cada inmueble paga en total exactamente su parte.
- Para emitir se exige fecha de acuerdo y R-COEF-01 **también con grupo**: si los
  coeficientes generales están mal, cualquier reparto los arrastra.

## Alternativas descartadas
- Emitir plazo a plazo (como las cuotas ordinarias por periodo): habría que impedir que el
  grupo cambiase entre plazos, o los totales no cuadrarían. Fijándolo todo al emitir, no.
- Coeficientes propios obligatorios en los grupos: obligaría a copiar los coeficientes
  generales en el caso más común (excluir los locales de un gasto).
- Grupos dentro de `cobros`: los coeficientes son datos de la finca, no de un cobro.

## Consecuencias
- El código 706 "Derramas" es una convención (como 430 y 705 en T2.2) hasta que haya un plan
  de cuentas por defecto.
- Anular una derrama emitida (contra-asiento y cuotas anuladas) queda pendiente, como anular
  una emisión de cuotas ordinarias.
- `plan_de_derrama` y `plan_de_cuotas` (T2.2) son el mismo algoritmo: al fusionar las dos
  ramas, unificarlos.
