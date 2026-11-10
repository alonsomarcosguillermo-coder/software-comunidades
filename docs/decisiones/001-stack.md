# 001 — Stack: Django + HTMX + PostgreSQL

**Fecha:** 2026-11-09 · **Estado:** aceptada

## Contexto
Aplicación con mucho CRUD, reglas de negocio, usuarios y permisos. Un solo desarrollador que
conoce Python y está aprendiendo desarrollo web.

## Decisión
- **Django 5.2** (LTS): ORM, migraciones, admin, autenticación y formularios incluidos.
- **HTMX** para interactividad sin escribir una SPA en JavaScript.
- **PostgreSQL 16** en Docker: la misma base de datos que se usaría en producción.
- Modelo de usuario propio (`core.Usuario`) desde la primera migración.

## Alternativas descartadas
- FastAPI + React: más flexible, pero dos ecosistemas que aprender y mucho que construir a mano
  (auth, admin). Si hace falta una API más adelante, Django puede exponerla.
- SQLite: más simple, pero distinto de producción (tipos, concurrencia, funciones).

## Consecuencias
- Hace falta Docker Desktop en desarrollo.
- Los tests que usan base de datos necesitan PostgreSQL arrancado.
