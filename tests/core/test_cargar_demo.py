"""T1.6 — Comando `manage.py cargar_demo`: datos de ejemplo ficticios para desarrollo."""

from decimal import Decimal

import pytest
from django.contrib.auth import authenticate
from django.contrib.auth.models import Group
from django.core.management import CommandError, call_command
from django.urls import reverse

from contabilidad.models import Apunte, Asiento, Cuenta
from core.management.commands.cargar_demo import CLAVE_DEMO
from core.models import Despacho, Usuario
from fincas.models import Comunidad, Inmueble, Propietario, Titularidad

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
