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
- ✅ **T2.2** 🔀 Emisión de cuotas ordinarias por periodo (usa T1.3), con asientos contables.
  Hecho: `Presupuesto.periodos` (anual/semestral/trimestral/mensual, fija al aprobar);
  `cobros.servicios.plan_de_cuotas` (R-REP-02 en dos pasos: inmuebles y luego periodos;
  hypothesis: cuadra al céntimo y cada inmueble paga su parte anual exacta);
  `cobros.emision.emitir_cuotas` crea `Emision` + `Cuota` (inmutables) y el asiento
  430 / 705 + fondo de reserva (desglose sobre lo acumulado: el fondo recibe la aportación
  exacta). Se niega sin aprobación (R-PRE-01), sin R-COEF-01, periodo repetido o sin cuenta
  de fondo; con cuotas emitidas no se puede quitar la aprobación. Botón "Emitir" por
  periodo en la página de presupuestos (permiso `cobros.add_emision`, PRG con mensajes).
  `cargar_demo` emite el primer trimestre. ADR 005.
- ✅ **T2.3** 🔀 Derramas (importe total, plazos, grupo de reparto).
  Hecho: grupos de reparto R-REP-01 en `fincas` (`GrupoReparto`, `MiembroGrupo` con
  coeficiente propio opcional, todos o ninguno: `servicios.coeficientes_de_grupo`).
  `cobros.Derrama` (importe, plazos, vencimientos, grupo, fecha de acuerdo) y
  `CuotaDerrama` (inmueble × plazo, inmutable). `cobros.derramas.emitir_derrama` exige
  acuerdo y R-COEF-01, fija las cuotas y registra un asiento (430 por inmueble / 706). Cálculo
  puro `servicios.plan_de_derrama` (R-REP-02 en dos pasos, hypothesis) y `vencimientos`.
  Página `/comunidades/<id>/derramas/` (reparto previsto o emitido), admin con acción
  "Emitir", `cargar_demo` con un grupo y dos derramas. ADR 006.
- ✅ **T2.4** Recibos y mandatos SEPA `R-SEPA-01`.
  Hecho: `cobros.Recibo` (uno por cuota ordinaria o de derrama, nº correlativo por
  comunidad, inmutable, sin asiento) con `cobros.recibos.generar_recibos` (repetible; pagador
  = titular en el vencimiento, `elegir_pagador` puro; inmuebles sin titular se avisan).
  `cobros.Mandato` (referencia única, titular de la cuenta, IBAN validado, firma, baja; uno
  activo por propietario; inmutable salvo la baja). `Comunidad.iban_cobros` y
  `sufijo_acreedor`; `cobros.sepa.identificadores` (IBAN mod-97, identificador de acreedor
  AT-02 con el ejemplo del EPC, `iban_oculto`, `texto_sepa`). Página
  `/comunidades/<id>/recibos/` (IBAN siempre oculto) con botón "Generar recibos"
  (`cobros.add_recibo`). Admin de mandatos y recibos. `cargar_demo` con NIF/IBAN ficticios,
  3 mandatos y recibos. ADR 007.
- ✅ **T2.5** Generación de remesa pain.008 `R-SEPA-02`, validada contra el esquema XSD.
  Hecho: `cobros.sepa.pain008` (puro: dataclasses → XML pain.008.001.02, un bloque por
  FRST/RCUR, textos SEPA) y `validar_pain008` con `lxml` contra el XSD oficial
  (`cobros/sepa/pain.008.001.02.xsd`); hypothesis: siempre valida y la suma cuadra.
  `cobros.Remesa` inmutable con el XML exacto; `cobros.remesas.crear_remesa` (recibos
  pendientes que vencen hasta el cobro con mandato vigente; si el XML no valida, no se
  guarda nada; recibo ↔ remesa + mandato + secuencia, restricción en la BD). En la página de
  recibos: estado, "Crear remesa" (`cobros.add_remesa`) y descarga (`cobros.view_remesa`).
  Nueva dependencia `lxml`. ADR 008.

## Fase 3 — Bancos y morosidad
- ✅ **T3.1** 🔀 Importar extractos Norma 43.
  Hecho: app `bancos`. Lector puro `bancos.norma43.leer_norma43` (registros 11/22/23/24/33/88,
  CRLF/LF/sin saltos, latin-1; comprueba nº de apuntes, totales, saldo final y nº de
  registros, y si algo no cuadra rechaza el fichero entero con el nº de línea) y escritor
  `escribir_norma43` para tests y demo (hypothesis: ida y vuelta). `bancos.Extracto` (un
  bloque 11…33, con sus registros originales) y `bancos.Movimiento` (+ abono / − cargo),
  inmutables. `bancos.importacion.importar_norma43`: todo o nada; la cuenta debe ser la del
  IBAN de cobro, solo euros, sin solapes de fechas con lo ya importado. Páginas
  `/comunidades/<id>/extractos/` (subida con `bancos.add_extracto`) y detalle de movimientos.
  Admin de solo lectura. `cargar_demo` importa un extracto con el pago por transferencia de
  un recibo (referencia del recibo), una luz y una comisión. ADR 009.
- ✅ **T3.2** Conciliación automática (importe + referencia) y manual.
  Hecho: `bancos.Conciliacion` (movimiento ↔ asiento; remesa o cuenta) y `CobroRecibo`
  (recibo cobrado una sola vez, restricción en la BD). Propuesta pura
  `bancos.servicios.proponer_conciliaciones`: abonos que mencionan `REC-…` (palabra completa)
  con importe exacto, o el `MsgId` de una remesa con su total; ante cualquier ambigüedad no
  propone (hypothesis: cada propuesta cuadra y no repite recibos). `bancos.conciliacion`:
  con recibos (asiento 572 / 430 por recibo), con otra cuenta (no 572 ni 430), automática y
  deshacer (contra-asiento + borra la conciliación). `Recibo.estado` = "cobrado". Web:
  botón "Conciliar automáticamente", pendientes por extracto, estado y "Deshacer" por
  movimiento, página de conciliación manual (recibos del importe exacto primero, o cuenta).
  Admin de solo lectura. `cargar_demo`: permisos y cuenta 626; el extracto se deja sin
  conciliar para probarlo. ADR 010.
- ✅ **T3.3** 🔀 Devoluciones de recibos → deuda del propietario.
  Hecho: `bancos.Devolucion` (recibo + conciliación del cargo + conciliación del cobro que
  deshace). `bancos.conciliacion.conciliar_devolucion`: solo recibos cobrados, importe exacto,
  asiento 430 / 572 por recibo, y borra el `CobroRecibo`: el recibo vuelve a estar sin cobrar
  (deuda, misma consulta `cobro__isnull=True`) y se puede volver a cobrar. Estado
  `Recibo.estado == "devuelto"`. Automática (pura, `proponer_devoluciones`, hypothesis): cargos
  con la referencia de recibos cobrados e importe exacto, después de los cobros. Deshacer: un
  cobro con devoluciones no se deshace; deshacer la devolución restaura el cobro (salvo que el
  recibo se haya vuelto a cobrar). Web: la página manual de un cargo ofrece los recibos
  cobrados; detalle y página de recibos muestran las devoluciones. Admin. ADR 011.
- ✅ **T3.4** 🔀 Informe de morosos y certificado de deuda `R-DEU-01` (PDF).
  Hecho: la deuda se calcula a una fecha, no se guarda. Cálculo puro `cobros.morosidad`
  (`ReciboDeuda` → `informe_morosos` por propietario y `estado_deuda` por inmueble; vencido =
  vencimiento anterior a la fecha; cobrado = conciliado con un movimiento de esa fecha o
  anterior; hypothesis: el informe cuadra con la deuda y cobrar nunca la aumenta).
  `cobros.deudas` lee los recibos en una consulta (fecha de cobro por la relación `cobro`).
  PDF con ReportLab en `cobros.pdf` (nueva dependencia `reportlab`): informe de morosos con
  detalle de recibos y certificado R-DEU-01 por inmueble (deuda vencida, también de
  titulares anteriores, y recibos por vencer aparte; firma en blanco). Página
  `/comunidades/<id>/morosos/?fecha=` con enlaces a los dos PDF (`cobros.view_recibo`; fecha
  futura no admitida). Con T3.3: un recibo devuelto es deuda desde la fecha del cargo de
  la devolución (los periodos "cobrado → devuelto" cuentan como pagados). ADR 012.

## Fase 4 — Juntas
- ✅ **T4.1** Convocatoria (orden del día, plazos `R-JUN-02`, envío por email).
  Hecho: app `juntas` con `Junta`, `PuntoOrden` (mayoría y excepción R-MAY-05 por punto) y
  `Citacion`. Plazos puros en `juntas.servicios` (R-JUN-02 en días completos, R-JUN-03
  media hora). `juntas.convocatoria.convocar`: cita a los titulares del día, relación de
  morosos del art. 16.2 (con `cobros.deudas`, T3.4), un email por propietario (plantilla
  `convocatoria.txt`) y lista de quienes no tienen email; convocada = inmutable. Web: lista,
  preparar/editar con formset del orden del día, detalle con vista previa y "Convocar".
  `EMAIL_BACKEND` por consola en desarrollo. Admin. `cargar_demo`: junta en borrador a 3
  semanas. Interpretaciones en DOMINIO.md (BOE consultado). ADR 013.
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
  7xx...) y el tipo de cuenta (activo, pasivo, gasto, ingreso) para informes. T2.1 solo
  añadió la marca `es_fondo_reserva` y T2.2 crea 430/705 si faltan; sigue sin haber plan
  completo ni subcuentas 430 por propietario.
- Contabilidad: no hay ejercicios ni cierre; no se impide registrar asientos con fecha pasada.
- `config/urls.py` conserva el docstring en inglés generado por Django.
- R-COEF-01 solo se exige al editar la comunidad en el admin (y al emitir cuotas). Cuando haya
  vistas o importación de inmuebles, usar `comprobar_coeficientes` también ahí.
- Pregunta pendiente para `DOMINIO.md`: ¿la titularidad necesita % de propiedad (proindiviso)
  y un representante por inmueble para votar (art. 15.1 LPH)? De momento no se modela.
- Validación de formato del NIF/NIE (letra de control): no implementada.
- Los grupos (roles) y sus permisos solo existen en `cargar_demo`. Cuando se definan los roles
  reales, crearlos con una migración de datos y que `cargar_demo` los reutilice.
- La lista de comunidades no tiene paginación (hará falta con muchas comunidades).
- Presupuestos: se crean y editan solo en el admin (sin filtro por despacho). Falta una vista
  propia de alta/edición para el administrador de fincas.
- Presupuestos aprobados: la protección es solo en Python (`QuerySet.update()` de partidas la
  esquiva).
- Partidas sin grupo de reparto (R-REP-01) ni cuenta de gasto asociada. Los grupos ya existen
  (T2.3); falta que una partida pueda repartirse solo entre un grupo en las cuotas ordinarias.
- `cobros.emision.cuenta_por_codigo` crea las cuentas 430/705/706 con código fijo; cuando
  haya un plan de cuentas por defecto, llevarlo a `contabilidad`.
- Derramas: no se pueden anular una vez emitidas (faltan contra-asiento y anular cuotas). Se
  crean y emiten solo en el admin (sin filtro por despacho); la acción "Emitir" fecha el
  asiento con el día de hoy.
- Admin de grupos de reparto: el buscador de inmuebles ofrece los de todas las comunidades
  (el modelo rechaza los de otra comunidad al guardar).
- El saldo del fondo de reserva cuenta todos los apuntes, también los de fecha futura.
- Pregunta pendiente para `DOMINIO.md`: base del 10 % de R-RES-01 (ver nota bajo R-PRE-01).
- Emisiones: no se pueden anular (haría falta contra-asiento + marca de anulada). Tampoco hay
  vista con el detalle de cuotas por inmueble (solo el admin).
- Emisiones: el plan se recalcula con los coeficientes del momento; si cambian a mitad de
  año, la parte anual de un inmueble deja de ser exacta (ver ADR 005).
- Cuotas: todo el presupuesto se reparte por coeficiente general; los grupos de reparto
  (R-REP-01) ya existen (T2.3) pero las cuotas ordinarias aún no los usan.
- `cargar_demo` mantiene un asiento manual "Cuotas de enero emitidas" de T1.6 que ahora
  convive con la emisión real del primer trimestre.
- Recibos: la página no tiene paginación ni filtros (por estado, vencimiento, propietario).
- Mandatos: se dan de alta solo en el admin (sin filtro por despacho); el buscador de
  propietarios ofrece los de todos los despachos (el modelo rechaza los ajenos al validar).
- Recibos: si un recibo se generó para el titular equivocado (titularidad mal cargada), no hay
  forma de anularlo y volver a generarlo.
- Remesas: no se pueden anular (si el banco rechaza el fichero entero, habría que devolver
  sus recibos a pendientes). Sin plazos de presentación ni días hábiles (ver R-SEPA-02).
- Remesas: solo pain.008.001.02; si un banco exige una versión nueva (.001.08), añadirla.
- Mandatos: no se controla la caducidad por falta de uso (36 meses, EPC) ni el preaviso.
- Extractos: solo la cuenta de cobro de la comunidad (`iban_cobros`); falta un modelo de
  cuentas bancarias si una comunidad tiene varias (y enlazarlas con su cuenta 572).
- Extractos: no se pueden anular si se importan por error (inmutables). Tampoco se avisa de
  huecos entre extractos (saldo inicial ≠ saldo final del anterior, o días sin extracto).
- Extractos: los registros 24 (equivalencia en otra divisa) se admiten pero no se guardan.
- Extractos: la página de movimientos no tiene paginación ni filtros.
- Conciliación: sin pagos parciales de recibos ni cobros a cuenta (un vecino que paga de
  menos sigue debiendo todo el recibo). La página manual lista todos los recibos
  pendientes sin paginar ni buscar; tampoco suma en vivo los marcados.
- Conciliación: no propone por importe + nombre del ordenante cuando falta la referencia.
- Devoluciones: un recibo devuelto no se puede volver a presentar en otra remesa (solo
  cobrarlo por otro medio). Tampoco se guarda el motivo SEPA (AM04, MD06...) aparte.
- Pregunta pendiente para `DOMINIO.md`: ¿se pueden repercutir al propietario los gastos
  bancarios de la devolución (estatutos, acuerdo de junta)? Hoy los paga la comunidad.
- `cargar_demo` no tiene remesa ni devolución de ejemplo (para verlo en la web hay que crear
  una remesa e importar un extracto con su abono y su devolución).
- Conciliación: al deshacer se borra la fila de `Conciliacion`; el rastro queda solo en los
  asientos (original y contra-asiento), no en quién concilió y quién deshizo.
- Morosidad: no hay registro de certificados de deuda emitidos (número, fecha, solicitante);
  se generan al vuelo. Tampoco se envía el informe ni el certificado por email.
- Morosidad: la deuda no se cruza con la contabilidad (saldo de la 430); si algún día hay
  cobros fuera de la conciliación, el informe y el saldo contable podrían no coincidir.
- Morosidad: la página de morosos no tiene paginación ni búsqueda de inmuebles; el informe
  se calcula en Python con todos los recibos vencidos de la comunidad (bien para cientos).
- Juntas: el envío de emails va dentro de la transacción de `convocar`; si el SMTP falla a
  medias, la junta queda sin convocar aunque algunos emails hayan salido. Con volumen real,
  una cola de envíos. Sin registro de citaciones por tablón o domicilio, ni acuse de recibo.
- Juntas: R-JUN-01 (una ordinaria al año) no se avisa. El formset del orden del día solo
  añade 3 filas por guardado y no permite reordenar arrastrando.
- Juntas: revisar con protección de datos el envío por email de la relación de morosos.
