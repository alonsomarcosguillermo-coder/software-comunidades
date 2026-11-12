# 016 — Portal del vecino

**Fecha:** 2026-11-12 · **Estado:** aceptada

## Contexto
T5.1: que cada propietario consulte sus recibos, su deuda y los documentos de su comunidad.
Hasta ahora solo entraban los usuarios del despacho, y todo se aislaba por despacho (ADR
002). Un vecino no es del despacho: hace falta otra regla de aislamiento, más estricta.

## Decisión
- **Nueva app `portal`**. Un vecino es un `Usuario` sin despacho enlazado a una o varias
  fichas de `Propietario` (`Propietario.usuario`): una misma persona puede tener inmuebles en
  comunidades de distintos despachos, y cada despacho tiene su ficha.
- **Aislamiento del portal: por usuario**, no por despacho. Todas las consultas salen de
  `portal.consultas`, que parte siempre de `request.user`:
  - recibos: los suyos como pagador (también de inmuebles ya vendidos);
  - deuda: sus recibos vencidos e impagados, con el cálculo de T3.4;
  - convocatorias y actas cerradas: solo de las comunidades donde es titular HOY.
  Un vecino no entra en las páginas del despacho: no tiene despacho, así que el filtro de
  ADR 002 no le deja ver nada (404).
- **Alta sin contraseñas compartidas**: el despacho pulsa "Invitar al portal"; se crea el
  usuario (nombre de usuario = email) sin contraseña usable y se le envía el enlace de
  "restablecer contraseña" de Django, que lleva un token firmado, caduca y solo sirve una vez.
  Así nadie del despacho conoce la clave del vecino. "¿Olvidaste tu contraseña?" usa el mismo
  mecanismo (y responde igual exista o no el email). Una invitación nunca reutiliza un usuario
  del despacho.
- **Tras entrar** (`inicio`): el despacho va a sus comunidades; el vecino, a su portal. El
  menú se adapta con el procesador de contexto `portal.contexto` (`es_vecino`).
- Permiso para invitar: `core.add_usuario`.

## Consecuencias
- Los cotitulares ven los recibos de los que son pagadores (T2.4: el titular con mandato o el
  primero), no los de su cotitular: pregunta pendiente ya anotada en `DOMINIO.md`.
- No hay más "documentos" que convocatorias y actas (ni presupuestos, ni cuentas anuales, ni
  ficheros subidos). Se añadirán si se piden.
- La invitación depende del correo: hasta tener SMTP real (T6.3), los enlaces salen por la
  consola del servidor.
