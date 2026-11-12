"""T1.6 — Comando `manage.py cargar_demo`: datos de ejemplo ficticios para desarrollo."""

from decimal import Decimal

import pytest
from django.contrib.auth import authenticate
from django.contrib.auth.models import Group
from django.core.management import CommandError, call_command
from django.urls import reverse

from bancos.models import Extracto, Movimiento
from cobros.consultas import fondo_reserva_de
from cobros.models import (
    Cuota,
    CuotaDerrama,
    Derrama,
    Emision,
    Mandato,
    Partida,
    Presupuesto,
    Recibo,
)
from contabilidad.models import Apunte, Asiento, Cuenta
from core.management.commands.cargar_demo import CLAVE_DEMO
from core.models import Despacho, Usuario
from fincas.models import (
    Comunidad,
    GrupoReparto,
    Inmueble,
    MiembroGrupo,
    Propietario,
    Titularidad,
)
from juntas.models import Junta, PuntoOrden

MODELOS = [
    Despacho,
    Usuario,
    Group,
    Comunidad,
    Inmueble,
    Propietario,
    Titularidad,
    Cuenta,
    Asiento,
    Apunte,
    Presupuesto,
    Partida,
    Emision,
    Cuota,
    GrupoReparto,
    MiembroGrupo,
    Derrama,
    CuotaDerrama,
    Mandato,
    Recibo,
    Extracto,
    Movimiento,
    Junta,
    PuntoOrden,
]


def _cargar():
    call_command("cargar_demo", stdout=None)


@pytest.fixture
def demo(db, settings):
    settings.DEBUG = True
    _cargar()


@pytest.mark.django_db
def test_crea_un_despacho_con_dos_comunidades(demo):
    alfa = Despacho.objects.get(nombre="Fincas Alfa")
    assert alfa.comunidades.count() == 2


@pytest.mark.django_db
def test_crea_un_segundo_despacho_para_probar_el_aislamiento(demo):
    beta = Despacho.objects.get(nombre="Fincas Beta")
    assert beta.comunidades.count() == 1


@pytest.mark.django_db
def test_r_coef_01_todas_las_comunidades_de_demo_cuadran(demo):
    assert all(c.coeficientes_cuadran() for c in Comunidad.objects.all())


@pytest.mark.django_db
def test_todos_los_inmuebles_tienen_titular(demo):
    assert not Inmueble.objects.filter(titularidades__isnull=True).exists()


@pytest.mark.django_db
def test_hay_propietarios_con_varios_inmuebles(demo):
    # Caso realista: el mismo vecino con piso y plaza de garaje.
    assert any(p.titularidades.count() > 1 for p in Propietario.objects.all())


@pytest.mark.django_db
def test_la_contabilidad_de_demo_cuadra(demo):
    for comunidad in Comunidad.objects.filter(asientos__isnull=False).distinct():
        assert sum(c.saldo() for c in comunidad.cuentas.all()) == Decimal("0.00")
    assert Asiento.objects.filter(anula__isnull=False).exists()  # incluye un contra-asiento


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("usuario", "despacho", "grupo"),
    [
        ("admin.alfa", "Fincas Alfa", "Administrador de fincas"),
        ("empleado.alfa", "Fincas Alfa", "Empleado del despacho"),
        ("admin.beta", "Fincas Beta", "Administrador de fincas"),
    ],
)
def test_usuarios_de_demo_pueden_entrar(demo, usuario, despacho, grupo):
    u = authenticate(username=usuario, password=CLAVE_DEMO)
    assert u is not None
    assert u.despacho.nombre == despacho
    assert list(u.groups.values_list("name", flat=True)) == [grupo]
    assert not u.is_superuser


@pytest.mark.django_db
def test_permisos_de_los_grupos(demo):
    admin = authenticate(username="admin.alfa", password=CLAVE_DEMO)
    empleado = authenticate(username="empleado.alfa", password=CLAVE_DEMO)
    assert admin.has_perm("fincas.change_comunidad")
    assert admin.has_perm("contabilidad.view_asiento")
    assert empleado.has_perm("fincas.change_propietario")
    assert not empleado.has_perm("fincas.change_comunidad")
    assert not empleado.has_perm("fincas.delete_propietario")


@pytest.mark.django_db
def test_es_idempotente(demo):
    # Ejecutarlo dos veces no duplica nada.
    antes = {m: m.objects.count() for m in MODELOS}
    _cargar()
    assert {m: m.objects.count() for m in MODELOS} == antes


@pytest.mark.django_db
def test_no_pisa_la_clave_si_el_usuario_de_demo_ya_existe(demo):
    # Si alguien cambió la clave de un usuario de demo, se respeta.
    usuario = Usuario.objects.get(username="admin.alfa")
    usuario.set_password("otra-clave-cualquiera")
    usuario.save()
    _cargar()
    assert authenticate(username="admin.alfa", password="otra-clave-cualquiera") is not None


@pytest.mark.django_db
def test_no_toca_usuarios_que_no_son_de_demo(demo):
    propio = Usuario.objects.create_user(username="mio", password="clave-propia-123")
    _cargar()
    propio.refresh_from_db()
    assert propio.check_password("clave-propia-123")
    assert propio.despacho is None


@pytest.mark.django_db
def test_se_niega_a_ejecutarse_sin_debug(db, settings):
    # Protección: nunca crear usuarios con clave conocida en producción.
    settings.DEBUG = False
    with pytest.raises(CommandError, match="DEBUG"):
        _cargar()
    assert not Despacho.objects.exists()


@pytest.mark.django_db
def test_datos_ficticios(demo):
    # Datos personales: solo emails de example.com (dominio reservado para ejemplos).
    emails = [e for e in Usuario.objects.values_list("email", flat=True) if e]
    emails += [e for e in Propietario.objects.values_list("email", flat=True) if e]
    assert emails
    assert all(e.endswith("@example.com") for e in emails)


@pytest.mark.django_db
def test_aislamiento_con_datos_de_demo(demo, client):
    client.login(username="admin.beta", password=CLAVE_DEMO)
    comunidades = client.get(reverse("fincas:lista_comunidades")).context["comunidades"]
    assert {c.despacho.nombre for c in comunidades} == {"Fincas Beta"}


@pytest.mark.django_db
def test_crea_presupuestos_aprobados_y_borradores(demo):
    assert Presupuesto.objects.aprobados().count() == 2
    assert Presupuesto.objects.filter(fecha_aprobacion__isnull=True).count() == 1
    assert not Presupuesto.objects.filter(partidas__isnull=True).exists()


@pytest.mark.django_db
def test_r_res_01_la_demo_muestra_un_fondo_de_reserva_insuficiente(demo):
    fondo = fondo_reserva_de(Comunidad.objects.get(nombre="CP Calle Ficticia 1"))
    assert fondo.saldo == Decimal("475.00")  # 350 iniciales + 125 del primer trimestre
    assert fondo.estado.minimo == Decimal("491.00")
    assert not fondo.estado.cumple


@pytest.mark.django_db
def test_la_demo_tiene_el_primer_trimestre_emitido(demo):
    emision = Emision.objects.get()
    assert emision.periodo == 1
    assert emision.total() == emision.asiento.total_debe()
    assert emision.cuotas.count() == 6  # un inmueble por cuota


def test_crea_un_grupo_de_reparto_y_derramas(demo):
    """T2.3 / R-REP-01: una derrama emitida entre todos y otra propuesta solo para un grupo."""
    grupo = GrupoReparto.objects.get(nombre="Ascensor")
    assert grupo.miembros.count() == 4
    emitida = Derrama.objects.get(concepto="Arreglo de la fachada")
    assert emitida.esta_emitida
    assert sum(emitida.cuotas.values_list("importe", flat=True)) == emitida.importe
    propuesta = Derrama.objects.get(grupo=grupo)
    assert not propuesta.esta_acordada and not propuesta.esta_emitida


@pytest.mark.django_db
def test_la_demo_tiene_mandatos_y_recibos(demo):
    comunidad = Comunidad.objects.get(nombre="CP Calle Ficticia 1")
    assert comunidad.identificador_acreedor()
    assert Mandato.objects.filter(comunidad=comunidad).count() == 3
    recibos = Recibo.objects.filter(comunidad=comunidad)
    assert recibos.exists()
    assert not recibos.filter(cuota__isnull=True, cuota_derrama__isnull=True).exists()


@pytest.mark.django_db
def test_con_la_demo_se_puede_crear_una_remesa_valida(demo):
    from datetime import timedelta

    from django.utils import timezone

    from cobros.remesas import crear_remesa
    from cobros.sepa.pain008 import validar_pain008

    comunidad = Comunidad.objects.get(nombre="CP Calle Ficticia 1")
    remesa = crear_remesa(comunidad, timezone.localdate() + timedelta(days=7))
    assert remesa.num_recibos > 0
    validar_pain008(remesa.xml.encode())


@pytest.mark.django_db
def test_la_demo_tiene_un_extracto_con_el_pago_de_un_recibo(demo):
    """T3.1: la vecina sin mandato paga por transferencia con la referencia del recibo."""
    comunidad = Comunidad.objects.get(nombre="CP Calle Ficticia 1")
    extracto = Extracto.objects.get(comunidad=comunidad)
    assert extracto.saldo_final == extracto.saldo_inicial + sum(
        extracto.movimientos.values_list("importe", flat=True)
    )
    recibo = Recibo.objects.filter(
        comunidad=comunidad, propietario__nombre="Marta Inventada"
    ).order_by("numero")[0]
    pago = extracto.movimientos.get(referencia_1=recibo.referencia)
    assert pago.importe == recibo.importe
    assert not Mandato.objects.filter(propietario=recibo.propietario).exists()


@pytest.mark.django_db
def test_con_la_demo_la_conciliacion_automatica_encuentra_el_pago(demo):
    """T3.2: el extracto de demo se deja sin conciliar para probarlo desde la web; la
    automática encuentra la transferencia con referencia y deja la luz y la comisión."""
    from bancos.conciliacion import conciliar_automaticamente, movimientos_pendientes

    comunidad = Comunidad.objects.get(nombre="CP Calle Ficticia 1")
    assert movimientos_pendientes(comunidad).count() == 3
    [hecha] = conciliar_automaticamente(comunidad)
    assert hecha.cobros.get().recibo.propietario.nombre == "Marta Inventada"
    assert movimientos_pendientes(comunidad).count() == 2
    assert comunidad.cuentas.filter(codigo="626").exists()  # para la comisión, a mano


@pytest.mark.django_db
def test_permisos_de_extractos(demo):
    admin = authenticate(username="admin.alfa", password=CLAVE_DEMO)
    empleado = authenticate(username="empleado.alfa", password=CLAVE_DEMO)
    assert admin.has_perm("bancos.add_extracto")
    assert empleado.has_perm("bancos.view_extracto")
    assert not empleado.has_perm("bancos.add_extracto")
    assert admin.has_perm("bancos.add_conciliacion")
    assert admin.has_perm("bancos.delete_conciliacion")
    assert not empleado.has_perm("bancos.add_conciliacion")


@pytest.mark.django_db
def test_la_demo_tiene_una_junta_en_borrador_que_se_puede_convocar_hoy(demo):
    """T4.1: R-JUN-02 se cumple citando hoy; se cita a los titulares y se envían emails."""
    from django.core import mail
    from django.utils import timezone

    from juntas.convocatoria import convocar

    junta = Junta.objects.get()
    assert not junta.esta_convocada
    assert junta.puntos.count() == 4
    resultado = convocar(junta, timezone.localdate())
    assert resultado.enviadas
    assert len(mail.outbox) == len(resultado.enviadas)


@pytest.mark.django_db
def test_permisos_de_juntas(demo):
    admin = authenticate(username="admin.alfa", password=CLAVE_DEMO)
    empleado = authenticate(username="empleado.alfa", password=CLAVE_DEMO)
    assert admin.has_perm("juntas.add_junta")
    assert admin.has_perm("juntas.add_citacion")
    assert empleado.has_perm("juntas.view_junta")
    assert not empleado.has_perm("juntas.add_citacion")
    assert admin.has_perm("juntas.add_celebracion")  # T4.3
    assert admin.has_perm("juntas.add_votoemitido")
    assert not empleado.has_perm("juntas.add_votoemitido")


@pytest.mark.django_db
def test_la_demo_tiene_una_vecina_con_portal(demo, client):
    """T5.1: vecina.marta entra a su portal y ve sus recibos (es Marta Inventada)."""
    usuario = authenticate(username="vecina.marta", password=CLAVE_DEMO)
    assert usuario is not None and usuario.despacho is None
    assert usuario.propietarios.get().nombre == "Marta Inventada"
    client.force_login(usuario)
    assert client.get(reverse("inicio"))["Location"] == reverse("portal:inicio")
    assert client.get(reverse("portal:recibos")).status_code == 200
