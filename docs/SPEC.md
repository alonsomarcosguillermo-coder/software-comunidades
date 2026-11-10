# Especificación — Comunidades (v1)

## Objetivo
Aplicación web para que un **administrador de fincas** gestione varias comunidades de propietarios:
quién es dueño de qué, cuánto paga cada uno, cobrar las cuotas por banco, saber quién debe dinero y
celebrar juntas con votaciones y actas. Proyecto de aprendizaje; más adelante se evaluará el mercado.

## Usuarios
- **Administrador de fincas** (rol principal): gestiona todas las comunidades de su despacho.
- **Empleado del despacho**: igual que el administrador, con permisos que se puedan limitar.
- **Vecino / propietario** (Fase 5): consulta sus recibos, documentos y vota en juntas.

## Qué hace la v1
1. Despachos, usuarios y permisos; un despacho nunca ve datos de otro.
2. Comunidades, inmuebles (pisos, locales, garajes, trasteros), propietarios y coeficientes.
3. Contabilidad de partida doble por comunidad.
4. Presupuesto anual → cuotas ordinarias por coeficiente; fondo de reserva; derramas.
5. Recibos y remesas SEPA de adeudo directo (fichero XML pain.008).
6. Importación de extractos bancarios (Norma 43) y conciliación con los recibos.
7. Devoluciones y morosidad; certificado de deuda.
8. Juntas: convocatoria, votación, cálculo de mayorías, acta.
9. Portal del vecino.

## Qué NO hace la v1
- Envío real al banco (se genera el fichero; el usuario lo sube a su banca online).
- Facturación electrónica / Verifactu, impuestos (modelo 347), nóminas de conserjes.
- App móvil, pagos con tarjeta, firma electrónica cualificada.
- Asesoramiento legal: las reglas de `DOMINIO.md` deben validarse con un profesional antes de uso real.

## Glosario
- **Comunidad de propietarios**: conjunto de propietarios de un edificio en régimen de propiedad horizontal.
- **Inmueble / elemento privativo**: piso, local, garaje o trastero con su propietario.
- **Coeficiente (cuota de participación)**: porcentaje que cada inmueble tiene en la comunidad;
  determina cuánto paga y cuánto pesa su voto.
- **Presupuesto ordinario**: gastos previstos del año (limpieza, luz, seguro, ascensor...).
- **Cuota ordinaria**: parte del presupuesto que paga cada inmueble cada periodo.
- **Derrama**: cobro extraordinario para un gasto no previsto (p. ej. arreglar la fachada).
- **Fondo de reserva**: dinero obligatorio apartado para imprevistos.
- **Remesa SEPA**: fichero con muchos recibos domiciliados que el banco cobra de una vez.
- **Mandato SEPA**: autorización del propietario para domiciliar recibos en su cuenta.
- **Norma 43**: formato estándar español de extracto bancario (movimientos de una cuenta).
- **Conciliación**: emparejar movimientos del banco con recibos/apuntes contables.
- **Moroso**: propietario con recibos vencidos sin pagar.
- **Junta**: reunión de propietarios (ordinaria anual o extraordinaria).
- **LPH**: Ley 49/1960, de Propiedad Horizontal.
