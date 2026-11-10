"""Segunda barrera en PostgreSQL para las reglas de la contabilidad (ver ADR 003).

Aunque alguien se salte el código Python (SQL a mano, `bulk_update`, un script...), la base
de datos:
1. Rechaza cualquier UPDATE o DELETE de asientos y apuntes (son inmutables).
2. Rechaza confirmar una transacción que deje un asiento con Debe ≠ Haber. Es un trigger
   DIFERIDO: se comprueba al hacer COMMIT, porque mientras se insertan los apuntes uno a
   uno el asiento está, lógicamente, a medias.
"""

from django.db import migrations

CREAR = """
CREATE FUNCTION contabilidad_inmutable() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'Los asientos y apuntes contables son inmutables: corrige con un contra-asiento.';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER asiento_inmutable
    BEFORE UPDATE OR DELETE ON contabilidad_asiento
    FOR EACH ROW EXECUTE FUNCTION contabilidad_inmutable();

CREATE TRIGGER apunte_inmutable
    BEFORE UPDATE OR DELETE ON contabilidad_apunte
    FOR EACH ROW EXECUTE FUNCTION contabilidad_inmutable();

CREATE FUNCTION contabilidad_comprobar_cuadre() RETURNS trigger AS $$
DECLARE
    total_debe numeric;
    total_haber numeric;
BEGIN
    SELECT COALESCE(SUM(debe), 0), COALESCE(SUM(haber), 0)
      INTO total_debe, total_haber
      FROM contabilidad_apunte
     WHERE asiento_id = NEW.asiento_id;
    IF total_debe <> total_haber THEN
        RAISE EXCEPTION 'Asiento % descuadrado: Debe % <> Haber %',
            NEW.asiento_id, total_debe, total_haber;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE CONSTRAINT TRIGGER apunte_cuadre
    AFTER INSERT ON contabilidad_apunte
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION contabilidad_comprobar_cuadre();
"""

BORRAR = """
DROP TRIGGER IF EXISTS apunte_cuadre ON contabilidad_apunte;
DROP FUNCTION IF EXISTS contabilidad_comprobar_cuadre();
DROP TRIGGER IF EXISTS apunte_inmutable ON contabilidad_apunte;
DROP TRIGGER IF EXISTS asiento_inmutable ON contabilidad_asiento;
DROP FUNCTION IF EXISTS contabilidad_inmutable();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("contabilidad", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(CREAR, reverse_sql=BORRAR),
    ]
