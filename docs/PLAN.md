# Plan de trabajo

Estados: ⬜ pendiente · 🔄 en curso · ✅ hecha · ⏸️ bloqueada
Cada tarea es una sesión de Claude Code. Criterio general de "terminado": tests nuevos que cubren la
tarea + `pytest` en verde + `ruff check` sin errores + `docs/PLAN.md` actualizado.
🔀 = se puede hacer en paralelo con otras tareas 🔀 de la misma fase (cada una en su worktree).

## Fase 0 — Arranque
- ✅ **T0.1** Proyecto Django (`config/`), app `core` con modelo `Usuario` propio, settings con
  PostgreSQL por variables de entorno, idioma es-es.
- ✅ **T0.2** pytest + pytest-django + ruff configurados (`pyproject.toml`); tests de humo.
- ✅ **T0.3** `docker-compose.yml` con PostgreSQL 16.
- ✅ **T0.4** `CLAUDE.md`, `docs/SPEC.md`, `docs/DOMINIO.md`, `docs/PLAN.md`, ADR 001, subagentes.
- ✅ **T0.5** `git init` (rama `main`) y primer commit.
- ✅ **T0.6** PostgreSQL en Docker arrancado, migraciones aplicadas, tests contra la BD en verde.
  Pendiente del usuario: `manage.py createsuperuser` (pide contraseña) y entrar en `/admin`.

## Fase 1 — Núcleo (secuencial: todo lo demás depende de esto)
- ✅ **T1.1** `Despacho` y relación `Usuario` → `Despacho`. Helper/mixin que filtra por despacho.
  Terminado: test de aislamiento (usuario del despacho A no ve datos de B).
  Hecho: `core.Despacho`, `Usuario.despacho` (FK opcional, PROTECT), `core/aislamiento.py`
  (`filtrar_por_despacho` + `FiltradoPorDespachoMixin`, fallan cerradas), admin, ADR 002.
- ✅ **T1.2** App `fincas`: `Comunidad` (pertenece a un despacho), `Inmueble` (tipo, referencia,
  coeficiente), `Propietario`, titularidad. Validación `R-COEF-01`. Admin de Django configurado.
  Hecho: coeficiente en % con 4 decimales; `fincas.servicios.comprobar_coeficientes` (pura);
  la suma = 100 se exige en bloque al guardar la comunidad en el admin (inmuebles en línea).
  `Propietario` cuelga del despacho (NIF único por despacho). `Titularidad` con fechas
  (histórico, cotitulares, sin solapes, mismo despacho). `fincas.models.CAMPO_DESPACHO`.
- ✅ **T1.3** Servicio de reparto `repartir(importe, coeficientes)` con `R-REP-02`. Tests con
  hypothesis: la suma siempre cuadra al céntimo.
  Hecho: `fincas.servicios.repartir` (resto mayor, cuentas exactas con `Fraction`, empates por
  clave, admite coeficientes que no suman 100 e importes negativos). Propiedades con
  hypothesis: suma exacta, error < 1 céntimo, monotonía, determinismo y simetría de signo.
- ✅ **T1.4** App `contabilidad`: `Cuenta`, `Asiento`, `Apunte`. Debe = Haber en cada asiento;
  asientos inmutables; saldo calculado. Contra-asiento para anular.
  Hecho: `contabilidad.registro.registrar_asiento` / `anular_asiento` (numeración correlativa
  por comunidad); cuadre puro en `servicios.comprobar_cuadre`; inmutabilidad en Python y con
  triggers de PostgreSQL (migración 0002, ADR 003); `Cuenta.saldo(hasta=)`. Admin: cuentas con
  saldo; asientos solo lectura.
- ✅ **T1.5** Plantilla base HTML + HTMX + login. Lista de comunidades del despacho.
  Hecho: `templates/base.html` (HTMX 2.0.4 en `static/js/`, CSRF en `hx-headers`), login y
  logout en `/entrar/` y `/salir/`, `/comunidades/` con `FiltradoPorDespachoMixin`, búsqueda
  HTMX que devuelve solo `_tabla_comunidades.html`, estado R-COEF-01 por comunidad.
- ✅ **T1.6** Datos de ejemplo: comando `manage.py cargar_demo` con un despacho, 2 comunidades
  y vecinos ficticios.
  Hecho: `core/management/commands/cargar_demo.py`, idempotente y solo con DEBUG. Añade un
  segundo despacho (Fincas Beta) para poder ver el aislamiento, grupos con permisos, usuarios
  de demo y algo de contabilidad (con un contra-asiento). No cambia la clave de usuarios que
  ya existen. Tests con hasher rápido (`tests/conftest.py`).

## Fase 2 — Cobro
- ✅ **T2.1** Presupuesto anual por comunidad y partidas; fondo de reserva `R-RES-01`.
  Hecho: app `cobros` con `Presupuesto` (ejercicio, fecha de aprobación R-PRE-01, aportación
  al fondo) y `Partida`; aprobado ⇒ importes fijos (modelo + admin en solo lectura).
  `Cuenta.es_fondo_reserva` (una por comunidad); R-RES-01 puro en `cobros.servicios`
  (mínimo redondeado hacia arriba, hypothesis) y con la BD en `cobros.consultas`. Página
  `/comunidades/<id>/presupuestos/` con partidas, totales, estado del fondo y previsión.
  `cargar_demo` añade presupuestos y un fondo insuficiente. ADR 004.
- ⬜ **T2.2** 🔀 Emisión de cuotas ordinarias por periodo (usa T1.3), con asientos contables.
- ⬜ **T2.3** 🔀 Derramas (importe total, plazos, grupo de reparto).
- ⬜ **T2.4** Recibos y mandatos SEPA `R-SEPA-01`.
- ⬜ **T2.5** Generación de remesa pain.008 `R-SEPA-02`, validada contra el esquema XSD.

## Fase 3 — Bancos y morosidad
- ⬜ **T3.1** 🔀 Importar extractos Norma 43.
- ⬜ **T3.2** Conciliación automática (importe + referencia) y manual.
- ⬜ **T3.3** 🔀 Devoluciones de recibos → deuda del propietario.
- ⬜ **T3.4** 🔀 Informe de morosos y certificado de deuda `R-DEU-01` (PDF).

## Fase 4 — Juntas
- ⬜ **T4.1** Convocatoria (orden del día, plazos `R-JUN-02`, envío por email).
- ⬜ **T4.2** Servicio puro de cálculo de mayorías `R-MAY-01..05`, `R-VOT-01`. Muchos tests.
- ⬜ **T4.3** Registro de asistencia y votos; borrador de acta.

## Fase 5 — Portal del vecino y salida
- ⬜ **T5.1** Portal: recibos, deuda, documentos.
- ⬜ **T5.2** Votación online del vecino.
- ⬜ **T5.3** GitHub + CI (GitHub Actions con PostgreSQL de servicio).

## Ideas / deuda técnica
- El admin de Django no filtra por despacho: si algún día lo usan empleados (no solo el
  superusuario), habrá que restringir sus querysets o retirarles el acceso. Comprobado con
  usuarios de demo: `admin.alfa` ve las comunidades de Fincas Beta en el admin.
- Contabilidad: el trigger de cuadre no impide añadir, más tarde, un par de apuntes que
  cuadren a un asiento ya existente (los apuntes nuevos sí deben ir con `registrar_asiento`).
- Contabilidad: falta un plan de cuentas por defecto al crear una comunidad (572, 430, 6xx,
  7xx...) y el tipo de cuenta (activo, pasivo, gasto, ingreso) para informes. Probablemente
  en T2.1/T2.2.
- Contabilidad: no hay ejercicios ni cierre; no se impide registrar asientos con fecha pasada.
- `config/urls.py` conserva el docstring en inglés generado por Django.
- R-COEF-01 solo se exige al editar la comunidad en el admin. Cuando haya vistas o importación
  de inmuebles (T1.5, T1.6), usar `comprobar_coeficientes` también ahí; y T2.2 (emitir cuotas)
  debe negarse si `Comunidad.coeficientes_cuadran()` es falso.
- Pregunta pendiente para `DOMINIO.md`: ¿la titularidad necesita % de propiedad (proindiviso)
  y un representante por inmueble para votar (art. 15.1 LPH)? De momento no se modela.
- Validación de formato del NIF/NIE (letra de control): no implementada.
- Los grupos (roles) y sus permisos solo existen en `cargar_demo`. Cuando se definan los roles
  reales, crearlos con una migración de datos y que `cargar_demo` los reutilice.
- La lista de comunidades no tiene paginación (hará falta con muchas comunidades).
- Presupuestos: se crean y editan solo en el admin (sin filtro por despacho). Falta una vista
  propia de alta/edición para el administrador de fincas.
- Presupuestos aprobados: la protección es solo en Python (`QuerySet.update()` de partidas la
  esquiva). T2.2 debe impedir quitar la aprobación si ya hay cuotas emitidas.
- Partidas sin grupo de reparto (R-REP-01) ni cuenta de gasto asociada: probablemente T2.3.
- El saldo del fondo de reserva cuenta todos los apuntes, también los de fecha futura.
- Pregunta pendiente para `DOMINIO.md`: base del 10 % de R-RES-01 (ver nota bajo R-PRE-01).
