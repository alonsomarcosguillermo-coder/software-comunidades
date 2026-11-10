# 003 — Contabilidad inmutable con doble barrera (Python + PostgreSQL)

**Fecha:** 2026-11-10 · **Estado:** aceptada

## Contexto
CLAUDE.md fija tres reglas no negociables: Debe = Haber en cada asiento, asientos inmutables
(se corrigen con contra-asiento) y saldo calculado, nunca guardado. Django ofrece muchas
formas de saltarse un `save()`: `QuerySet.update()`, `bulk_update()`, el admin, la shell o SQL
a mano. Un fallo aquí descuadra la contabilidad de una comunidad sin que nadie lo note.

## Decisión
- **Única puerta de entrada**: `contabilidad.registro.registrar_asiento` (valida con la
  función pura `servicios.comprobar_cuadre`, numera y guarda en una transacción) y
  `anular_asiento` (contra-asiento con Debe y Haber invertidos, enlazado con `anula`).
- **Barrera en Python**: `Asiento` y `Apunte` lanzan `ContabilidadInmutable` al modificar o
  borrar, también con `update()`/`delete()` masivos. Mensajes de error claros.
- **Barrera en PostgreSQL** (migración `contabilidad/0002`): triggers que rechazan todo
  UPDATE/DELETE de asientos y apuntes, y un trigger diferido que, al confirmar la
  transacción, rechaza asientos con Debe ≠ Haber. `CHECK`: cada apunte va al Debe o al Haber.
- Numeración correlativa por comunidad, serializada con `SELECT ... FOR UPDATE` sobre la
  comunidad para que dos registros simultáneos no repitan número.
- Saldo = Debe − Haber de los apuntes (positivo deudor, negativo acreedor), calculado al vuelo.

## Alternativas descartadas
- Solo validación en Python: más simple, pero cualquier `update()` o script lo esquiva.
- Guardar saldos en la cuenta para ir más rápido: lo prohíbe CLAUDE.md, y si se necesita
  rendimiento se puede añadir un cierre por ejercicio más adelante.

## Consecuencias
- Hay lógica en SQL (plpgsql), que vive en una migración: hay que saber que existe al depurar.
- Los tests del trigger diferido necesitan `SET CONSTRAINTS ALL IMMEDIATE`, porque los tests
  de pytest-django nunca hacen COMMIT.
- `TRUNCATE` (lo usa `manage.py flush`) no dispara los triggers: borrar toda la base de datos
  de desarrollo sigue siendo posible.
