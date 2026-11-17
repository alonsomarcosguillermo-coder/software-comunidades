# 018 — Integración continua con GitHub Actions

**Fecha:** 2026-11-17 · **Estado:** aceptada

## Contexto
T5.3: hasta ahora los tests, el lint y las migraciones se comprobaban a mano en el ordenador
del desarrollador. Con el código en GitHub, cada cambio debe comprobarse solo y en un entorno
limpio, para que "en mi máquina funciona" no baste. Es también el requisito para el despliegue
automático de T6.3.

## Decisión
- **GitHub Actions**, un único workflow (`.github/workflows/ci.yml`) que se lanza en cada push
  y en cada pull request, sobre Ubuntu con Python 3.13.
- **PostgreSQL 16 como servicio** del job (contenedor de usar y tirar), con los mismos datos de
  conexión que `docker-compose.yml`. Los tests usan triggers y restricciones de PostgreSQL
  (ADR 003): probarlos con SQLite no valdría.
- **Pasos**, los mismos que pide CLAUDE.md antes de dar una tarea por terminada:
  `ruff check`, `ruff format --check`, `makemigrations --check` (no falta ninguna migración) y
  `pytest`.
- **DEBUG desactivado y clave de prueba** por variables de entorno: así se prueba con una
  configuración más parecida a la de producción. Ninguna variable es secreta.
- **ruff con versión fija** (`ruff==0.17.4`): otra versión podría formatear distinto o traer
  reglas nuevas y hacer fallar la CI sin cambios en el código. El resto de dependencias
  siguen con rangos (`>=`).
- Si llegan dos pushes seguidos a la misma rama, se cancela la ejecución anterior
  (`concurrency`). Permisos mínimos (`contents: read`).

## Consecuencias
- Un push con un test roto, un fichero sin formatear o una migración olvidada sale en rojo en
  GitHub (y en el pull request).
- Las dependencias con rangos pueden traer una versión nueva que rompa algo; si pasa a
  menudo, se fijarán todas (por ejemplo con un fichero de versiones bloqueadas).
- Los tests tardan alrededor de un minuto en local; en GitHub, unos minutos más por la
  instalación.
