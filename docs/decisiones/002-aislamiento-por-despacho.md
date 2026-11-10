# 002 — Aislamiento entre despachos por filtrado en la aplicación

**Fecha:** 2026-11-10 · **Estado:** aceptada

## Contexto
Varios despachos comparten la misma aplicación y la misma base de datos. Un despacho nunca
debe ver ni modificar datos de otro (SPEC, punto 1).

## Decisión
- Modelo `core.Despacho`; `Usuario.despacho` es una FK opcional (`PROTECT`). Los datos de
  negocio cuelgan del despacho directamente (`Comunidad.despacho`) o a través de otra
  relación (`Inmueble` → `comunidad__despacho`).
- Una sola base de datos y un solo esquema; el aislamiento se hace filtrando en la aplicación
  con `core.aislamiento.filtrar_por_despacho` y `FiltradoPorDespachoMixin` en las vistas.
- Falla cerrada: usuario sin despacho (o anónimo) → queryset vacío. Un objeto de otro despacho
  da 404, no 403, para no revelar que existe.
- Cada vista nueva lleva un test de "otro despacho no puede verlo ni modificarlo".

## Alternativas descartadas
- Un esquema de PostgreSQL por despacho (django-tenants): aislamiento más fuerte, pero
  migraciones y tests bastante más complejos para un proyecto de aprendizaje.
- Row Level Security de PostgreSQL: robusto, pero esconde la lógica fuera de Django y
  complica depurar. Se puede añadir más adelante como segunda barrera.

## Consecuencias
- El aislamiento depende de no olvidar el filtro: por eso el mixin, el test obligatorio por
  vista y el subagente `revisor`.
- El admin de Django NO filtra por despacho: queda solo para el superusuario técnico.
