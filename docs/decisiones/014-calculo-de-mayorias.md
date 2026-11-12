# 014 — Cálculo de mayorías como función pura

**Fecha:** 2026-11-12 · **Estado:** aceptada

## Contexto
T4.2: decidir si un acuerdo se aprueba (R-MAY-01..05, R-VOT-01) y si hay quórum en primera
convocatoria (R-JUN-03). Es la regla legal más delicada del sistema: un acuerdo mal
proclamado se impugna. El cálculo tiene muchas combinaciones (convocatoria, tipo de mayoría,
ausentes, privados de voto), así que tiene que poder probarse a fondo sin web ni base de datos.

## Decisión
- **`juntas.mayorias.calcular(votos, mayoria, segunda_convocatoria=, computar_ausentes=)`**,
  pura, sobre una lista de `Voto` (votante, cuota, sentido, privado de voto, discrepa).
  Devuelve un `Resultado` con el recuento por sentido, la base del cálculo, lo que cuenta a
  favor y una **explicación** en texto con el ID de la regla, para poder enseñarla y llevarla
  al acta.
- **Aritmética exacta**: las comparaciones se hacen multiplicando (`a * 2 > b`,
  `a * 5 >= b * 3`) con enteros y `Decimal`, nunca con porcentajes redondeados.
- **Quién decide qué**: el cálculo no sabe de fechas. Quien llama (T4.3) decide si un
  propietario está privado de voto (R-VOT-01, con la deuda de T3.4) y si ya se pueden
  computar los ausentes (R-MAY-05: pasados 30 días desde la notificación y si el punto no es
  una excepción del art. 17.8).
- **`Mayoria`** tiene los mismos valores que `PuntoOrden.Mayoria` (un test lo comprueba).
- **Tests**: casos pequeños comprobables a mano para cada regla, y propiedades con
  hypothesis: jerarquía (unanimidad ⇒ 3/5 ⇒ simple), monotonía (pasar un voto de contra a
  favor no deshace una aprobación), el voto de un privado no influye, simple en 1ª ⇒ simple
  en 2ª, y los recuentos suman todas las cuotas.

## Consecuencias
- Las interpretaciones dudosas (abstenciones en 2ª, ámbito de R-MAY-05) están en un solo
  sitio y documentadas en `DOMINIO.md`; cambiarlas es tocar una función y sus tests.
- No se modelan las mayorías especiales del art. 17.1 y 17.2 (un tercio para
  infraestructuras de telecomunicaciones, mayoría simple para accesibilidad...): no están en
  `DOMINIO.md`. Si se añaden, son una regla más aquí.
