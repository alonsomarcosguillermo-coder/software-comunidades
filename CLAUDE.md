# Comunidades — gestión de comunidades de vecinos (proyecto de aprendizaje)

El usuario está aprendiendo desarrollo web con este proyecto: explica brevemente el "por qué"
de cada decisión nueva (sin sermones). Idioma: español, en código, commits y documentación.

Documentación que debes conocer:
- `docs/SPEC.md` — qué hace el sistema y qué NO hace (alcance), glosario.
- `docs/PLAN.md` — tareas numeradas con su estado y criterio de "terminado".
- `docs/DOMINIO.md` — reglas legales (LPH) y de negocio, cada una con un ID (`R-XXX-NN`).
- `docs/decisiones/` — decisiones de arquitectura (ADR).

## Stack
Django 5.2 + HTMX + PostgreSQL 16 (en Docker). Python 3.13. Tests: pytest + pytest-django. Lint: ruff.
Entorno virtual en `.venv` (Windows: `.venv\Scripts\python.exe`).

## Comandos
- Arrancar la base de datos: `docker compose up -d db`
- Tests: `.venv\Scripts\python.exe -m pytest` — deben pasar antes de dar una tarea por terminada
- Servidor: `.venv\Scripts\python.exe manage.py runserver`
- Migraciones: `.venv\Scripts\python.exe manage.py makemigrations` y luego `migrate`
- Lint y formato: `.venv\Scripts\ruff.exe check .` y `.venv\Scripts\ruff.exe format .`

## Arquitectura
Apps de Django por área de negocio: `core` (despacho, usuarios, permisos), `fincas`, `contabilidad`,
`cobros`, `bancos`, `juntas`, `portal`. Se crean cuando las pide una tarea del plan, no antes.
La lógica de negocio (repartos, mayorías, conciliación) va en `servicios.py` de cada app como
funciones puras, testeables sin web ni base de datos. Las vistas solo orquestan.
Tests en `tests/<app>/`.

## Reglas no negociables
- **Dinero**: siempre `Decimal` (en BD `DecimalField(max_digits=12, decimal_places=2)`), nunca `float`.
  Redondeo `ROUND_HALF_UP` a céntimos. En repartos, los céntimos sobrantes se asignan de forma
  determinista (ver `R-REP-02`) para que la suma cuadre exactamente.
- **Contabilidad de partida doble**: los asientos son inmutables; un error se corrige con un
  contra-asiento. No existe un campo "saldo" editable: el saldo se calcula a partir de los apuntes.
- **Multi-comunidad**: toda consulta se filtra por despacho/comunidad del usuario. Cada vista nueva
  lleva un test que comprueba que un usuario de otro despacho NO puede ver ni modificar los datos.
- **Reglas legales**: implementa solo las de `docs/DOMINIO.md`, citando su ID en el código
  (comentario) y en el nombre o docstring del test. Si una regla no está ahí, pregunta; no la inventes.
- **Datos personales** (IBAN, DNI, emails): nunca en logs; en tests y fixtures, solo datos ficticios.

## Cómo trabajar
- Trabaja en UNA tarea de `docs/PLAN.md`. Al terminar, marca su estado y resume qué cambió.
- Escribe primero el test de la regla de negocio, luego el código.
- Cambios pequeños; no refactorices fuera del alcance de la tarea. Si ves algo mejorable, anótalo
  en "Ideas / deuda técnica" de `docs/PLAN.md`.
- Una decisión de arquitectura nueva → ADR breve en `docs/decisiones/NNN-titulo.md`.
- Commits pequeños, en español, en imperativo ("Añade modelo Inmueble").
- No hagas `git push` ni borres ramas sin preguntar.
