# 009 — Extractos bancarios: importación de Norma 43

**Fecha:** 2026-11-12 · **Estado:** aceptada

## Contexto
T3.1: traer a la aplicación los movimientos de la cuenta bancaria de la comunidad, para
conciliarlos después con los recibos (T3.2) y detectar devoluciones (T3.3). La banca
española los entrega en Norma 43 (AEB, "Cuaderno 43"): texto de ancho fijo, registros de
80 caracteres. No es una regla legal, así que no hay ID en `DOMINIO.md`; es un formato.

## Decisión
- **Nueva app `bancos`**, como prevé `CLAUDE.md`.
- **Lector puro** (`bancos.norma43.leer_norma43`): bytes → dataclasses, sin BD. Admite CRLF o
  LF, registros sin los espacios finales y ficheros sin saltos de línea; decodifica en
  latin-1. Comprueba el orden de los registros (11 → 22/23/24 → 33, … , 88) y **todos los
  controles**: nº de apuntes y totales del debe y del haber (33), saldo final = saldo inicial
  + movimientos, y nº de registros (88). Si algo no cuadra, el fichero entero se rechaza con
  el número de línea: un extracto incompleto haría que la conciliación diera por pagado o
  impagado lo que no es.
- **Signo**: importes desde el punto de vista de la comunidad. Abono (haber) positivo, cargo
  (debe) negativo. Igual el saldo: acreedor positivo, deudor negativo.
- **Escritor** (`escribir_norma43`): la aplicación no lo necesita, pero sirve para los tests
  (propiedad con hypothesis: lo escrito se vuelve a leer igual) y para la demo. Los tests del
  lector usan un fichero construido a mano campo a campo, para no depender del escritor.
- **`Extracto` y `Movimiento` inmutables** (como los asientos, ADR 003): son lo que dijo el
  banco. Un extracto por bloque 11 … 33. Se guardan también los registros originales de la
  cuenta (constancia, como el XML de la remesa). La conciliación (T3.2) los enlazará con
  recibos y asientos desde un modelo propio, sin modificarlos.
- **Qué se acepta** (`bancos.importacion.importar_norma43`, todo o nada):
  - La cuenta del fichero (entidad, oficina, nº de cuenta) debe ser la del IBAN de cobro de
    la comunidad. Norma 43 no trae IBAN ni los dígitos de control: se comparan esas tres
    partes del IBAN español.
  - Solo euros (divisa 978).
  - **No se aceptan periodos que se solapen** con un extracto ya importado de esa cuenta (ni
    entre cuentas del mismo fichero): los movimientos de los días comunes estarían dos veces.
    Es más sencillo y seguro que intentar detectar movimientos repetidos uno a uno, que en
    Norma 43 no tienen un identificador único.
- Importar **no contabiliza** nada: eso lo hará la conciliación.
- Página `/comunidades/<id>/extractos/` (lista y subida, permiso `bancos.add_extracto`) y
  detalle con los movimientos. El nº de cuenta se muestra oculto salvo las 4 últimas cifras.
  Fichero máximo de 5 MB.

## Consecuencias
- Solo una cuenta bancaria por comunidad (la de cobro). Si una comunidad tiene varias, hará
  falta un modelo de cuentas bancarias.
- Si un banco entrega un fichero sin el registro 88 o con totales mal calculados, no se podrá
  importar. Mejor rechazar que importar a medias; si pasa con un banco real, se estudiará.
- Un extracto importado por error no se puede borrar (inmutable). Habrá que añadir una
  anulación si hace falta, igual que con remesas y emisiones.
- Los años vienen con dos cifras (AAMMDD): se entienden como 20AA.
