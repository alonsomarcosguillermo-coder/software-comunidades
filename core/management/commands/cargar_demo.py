"""`manage.py cargar_demo`: carga datos de ejemplo FICTICIOS para desarrollo.

Crea dos despachos (Fincas Alfa, con 2 comunidades, y Fincas Beta, con 1, para poder ver
el aislamiento entre despachos), grupos con permisos, usuarios, inmuebles, propietarios,
titularidades y algo de contabilidad.

Es idempotente: se puede ejecutar varias veces sin duplicar nada. Solo funciona con
DEBUG activo, para no crear nunca usuarios con una clave conocida en producción.
"""

from datetime import date
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from contabilidad.models import Cuenta
from contabilidad.registro import anular_asiento, registrar_asiento
from contabilidad.servicios import Linea
from core.models import Despacho, Usuario
from fincas.models import Comunidad, Inmueble, Propietario, Titularidad
from fincas.servicios import comprobar_coeficientes

CLAVE_DEMO = "demo-comunidades-2026"


def _todos(app: str, modelo: str) -> list[str]:
    return [f"{app}.{accion}_{modelo}" for accion in ("view", "add", "change", "delete")]


# Roles de ejemplo. Los definitivos (y quién puede qué) se decidirán más adelante.
GRUPOS = {
    "Administrador de fincas": [
        "core.view_despacho",
        "core.view_usuario",
        "core.add_usuario",
        "core.change_usuario",
        *_todos("fincas", "comunidad"),
        *_todos("fincas", "inmueble"),
        *_todos("fincas", "propietario"),
        *_todos("fincas", "titularidad"),
        *_todos("contabilidad", "cuenta"),
        "contabilidad.view_asiento",
        "contabilidad.view_apunte",
    ],
    "Empleado del despacho": [
        "fincas.view_comunidad",
        "fincas.view_inmueble",
        "fincas.view_propietario",
        "fincas.add_propietario",
        "fincas.change_propietario",
        "fincas.view_titularidad",
        "fincas.add_titularidad",
        "fincas.change_titularidad",
        "contabilidad.view_cuenta",
        "contabilidad.view_asiento",
        "contabilidad.view_apunte",
    ],
    "Vecino": [],  # el portal del vecino llega en la Fase 5
}

# (usuario, nombre, despacho, grupo, entra al admin)
USUARIOS = [
    ("admin.alfa", "Ana Alfa", "Fincas Alfa", "Administrador de fincas", True),
    ("empleado.alfa", "Emilio Alfa", "Fincas Alfa", "Empleado del despacho", True),
    ("admin.beta", "Bea Beta", "Fincas Beta", "Administrador de fincas", True),
    ("vecino.lucia", "Lucía Vecina", None, "Vecino", False),
]

P, L, G, T = Inmueble.Tipo.PISO, Inmueble.Tipo.LOCAL, Inmueble.Tipo.GARAJE, Inmueble.Tipo.TRASTERO

# despacho -> comunidad -> [(tipo, referencia, coeficiente %, propietario)]
COMUNIDADES = {
    "Fincas Alfa": {
        "CP Calle Ficticia 1": [
            (P, "1A", "22.5000", "Carmen Ejemplo"),
            (P, "1B", "22.5000", "Pablo Prueba"),
            (P, "2A", "22.5000", "Marta Inventada"),
            (P, "2B", "22.5000", "Jorge Ficticio"),
            (L, "Local 1", "8.0000", "Bar Ejemplo SL"),
            (G, "Plaza 1", "2.0000", "Pablo Prueba"),
        ],
        "CP Plaza Imaginaria 7": [
            (P, "Bajo", "33.3333", "Rosa Supuesta"),
            (P, "1º", "33.3333", "Carmen Ejemplo"),
            (P, "2º", "33.3334", "Luis Hipotético"),
        ],
    },
    "Fincas Beta": {
        "CP Avenida Inventada 2": [
            (P, "A", "45.0000", "Mario Prueba"),
            (P, "B", "45.0000", "Elena Ficticia"),
            (T, "T1", "10.0000", "Mario Prueba"),
        ],
    },
}

COMUNIDAD_CON_CONTABILIDAD = "CP Calle Ficticia 1"
CUENTAS = [
    ("572", "Banco"),
    ("430", "Propietarios"),
    ("622", "Limpieza"),
    ("628", "Suministros (luz)"),
    ("705", "Cuotas ordinarias"),
]


def _email(texto: str) -> str:
    """Email ficticio en example.com (dominio reservado para ejemplos)."""
    limpio = texto.lower().replace(" ", ".")
    for origen, destino in zip("áéíóúñ", "aeioun", strict=True):
        limpio = limpio.replace(origen, destino)
    return f"{limpio}@example.com"


class Command(BaseCommand):
    help = "Carga datos de ejemplo ficticios (solo con DEBUG activo). Idempotente."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError(
                "cargar_demo solo se ejecuta con DEBUG activo: crea usuarios con una clave "
                "conocida y nunca debe usarse en producción."
            )
        with transaction.atomic():
            self._grupos()
            despachos = {n: Despacho.objects.get_or_create(nombre=n)[0] for n in COMUNIDADES}
            self._usuarios(despachos)
            self._fincas(despachos)
            self._contabilidad()

        self.stdout.write(self.style.SUCCESS("Datos de demo cargados."))
        self.stdout.write(f"Usuarios (clave «{CLAVE_DEMO}» si se acaban de crear):")
        for username, _, despacho, grupo, _ in USUARIOS:
            self.stdout.write(f"  - {username:<14} {despacho or '(sin despacho)':<16} {grupo}")

    def _grupos(self):
        for nombre, codigos in GRUPOS.items():
            grupo, _ = Group.objects.get_or_create(name=nombre)
            permisos = []
            for codigo in codigos:
                app, codename = codigo.split(".")
                permisos.append(
                    Permission.objects.get(content_type__app_label=app, codename=codename)
                )
            grupo.permissions.set(permisos)

    def _usuarios(self, despachos):
        for username, nombre, despacho, grupo, staff in USUARIOS:
            usuario, creado = Usuario.objects.get_or_create(
                username=username,
                defaults={
                    "first_name": nombre,
                    "email": f"{username}@example.com",
                    "despacho": despachos.get(despacho),
                    "is_staff": staff,
                },
            )
            if creado:
                # Solo al crearlo: si alguien cambió después la clave, se respeta.
                usuario.set_password(CLAVE_DEMO)
                usuario.save()
            usuario.groups.set([Group.objects.get(name=grupo)])

    def _fincas(self, despachos):
        for nombre_despacho, comunidades in COMUNIDADES.items():
            despacho = despachos[nombre_despacho]
            for nombre, inmuebles in comunidades.items():
                # R-COEF-01: comprobamos los datos de demo antes de guardarlos.
                comprobar_coeficientes([Decimal(coef) for _, _, coef, _ in inmuebles])
                comunidad, _ = Comunidad.objects.get_or_create(despacho=despacho, nombre=nombre)
                for tipo, referencia, coeficiente, titular in inmuebles:
                    inmueble, _ = Inmueble.objects.get_or_create(
                        comunidad=comunidad,
                        referencia=referencia,
                        defaults={"tipo": tipo, "coeficiente": Decimal(coeficiente)},
                    )
                    propietario, _ = Propietario.objects.get_or_create(
                        despacho=despacho, nombre=titular, defaults={"email": _email(titular)}
                    )
                    Titularidad.objects.get_or_create(
                        inmueble=inmueble,
                        propietario=propietario,
                        defaults={"fecha_inicio": date(2020, 1, 1)},
                    )

    def _contabilidad(self):
        comunidad = Comunidad.objects.get(nombre=COMUNIDAD_CON_CONTABILIDAD)
        cuentas = {
            codigo: Cuenta.objects.get_or_create(
                comunidad=comunidad, codigo=codigo, defaults={"nombre": nombre}
            )[0]
            for codigo, nombre in CUENTAS
        }
        if comunidad.asientos.exists():
            return  # los asientos son inmutables: si ya hay, no se tocan

        def D(valor: str) -> Decimal:
            return Decimal(valor)

        registrar_asiento(
            comunidad,
            date(2026, 1, 1),
            "Cuotas de enero emitidas",
            [Linea(cuentas["430"], debe=D("600.00")), Linea(cuentas["705"], haber=D("600.00"))],
        )
        registrar_asiento(
            comunidad,
            date(2026, 1, 10),
            "Cobro de cuotas de enero por banco",
            [Linea(cuentas["572"], debe=D("540.00")), Linea(cuentas["430"], haber=D("540.00"))],
        )
        registrar_asiento(
            comunidad,
            date(2026, 1, 31),
            "Factura limpieza y luz de enero",
            [
                Linea(cuentas["622"], debe=D("180.00")),
                Linea(cuentas["628"], debe=D("75.30")),
                Linea(cuentas["572"], haber=D("255.30")),
            ],
        )
        duplicado = registrar_asiento(
            comunidad,
            date(2026, 2, 3),
            "Factura limpieza (duplicada por error)",
            [Linea(cuentas["622"], debe=D("180.00")), Linea(cuentas["572"], haber=D("180.00"))],
        )
        anular_asiento(duplicado, date(2026, 2, 4))
