"""`manage.py cargar_demo`: carga datos de ejemplo FICTICIOS para desarrollo.

Crea dos despachos (Fincas Alfa, con 2 comunidades, y Fincas Beta, con 1, para poder ver
el aislamiento entre despachos), grupos con permisos, usuarios, inmuebles, propietarios,
titularidades, algo de contabilidad (con una cuenta de fondo de reserva) y presupuestos.

Es idempotente: se puede ejecutar varias veces sin duplicar nada. Solo funciona con
DEBUG activo, para no crear nunca usuarios con una clave conocida en producción.
"""

from datetime import date
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from cobros.derramas import emitir_derrama
from cobros.emision import emitir_cuotas
from cobros.models import Derrama, Mandato, Partida, Presupuesto
from cobros.recibos import generar_recibos
from cobros.sepa.identificadores import construir_iban
from contabilidad.models import Cuenta
from contabilidad.registro import anular_asiento, registrar_asiento
from contabilidad.servicios import Linea
from core.models import Despacho, Usuario
from fincas.models import (
    Comunidad,
    GrupoReparto,
    Inmueble,
    MiembroGrupo,
    Propietario,
    Titularidad,
)
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
        *_todos("cobros", "presupuesto"),
        *_todos("cobros", "partida"),
        "cobros.view_emision",
        "cobros.add_emision",
        "cobros.view_cuota",
        *_todos("fincas", "gruporeparto"),
        *_todos("fincas", "miembrogrupo"),
        *_todos("cobros", "derrama"),
        "cobros.view_cuotaderrama",
        *_todos("cobros", "mandato"),
        "cobros.view_recibo",
        "cobros.add_recibo",
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
        "cobros.view_presupuesto",
        "cobros.view_partida",
        "cobros.view_emision",
        "cobros.view_cuota",
        "fincas.view_gruporeparto",
        "fincas.view_miembrogrupo",
        "cobros.view_derrama",
        "cobros.view_cuotaderrama",
        "cobros.view_mandato",
        "cobros.view_recibo",
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
    ("113", "Fondo de reserva"),  # código de ejemplo; lo que cuenta es `es_fondo_reserva`
]
CUENTA_FONDO_RESERVA = "113"

# comunidad -> [(ejercicio, fecha de aprobación o None, aportación al fondo, partidas)]
# Con el fondo de demo (350 € + 125 € del primer trimestre emitido), "CP Calle Ficticia 1"
# NO cumple R-RES-01 con su presupuesto aprobado de 2026 (mínimo 491 €).
PRESUPUESTOS = {
    "CP Calle Ficticia 1": [
        (
            2026,
            date(2025, 12, 15),
            "500.00",
            [
                ("Limpieza", "2160.00"),
                ("Luz", "900.00"),
                ("Seguro", "650.00"),
                ("Mantenimiento del ascensor", "1200.00"),
            ],
        ),
        (
            2027,
            None,
            "300.00",
            [
                ("Limpieza", "2200.00"),
                ("Luz", "950.00"),
                ("Seguro", "680.00"),
                ("Mantenimiento del ascensor", "1250.00"),
            ],
        ),
    ],
    "CP Avenida Inventada 2": [
        (2026, date(2026, 1, 20), "100.00", [("Limpieza", "600.00"), ("Luz", "300.00")]),
    ],
}

# R-REP-01: comunidad -> {grupo de reparto: [referencias]} (con sus coeficientes generales).
GRUPOS_REPARTO = {
    "CP Calle Ficticia 1": {"Ascensor": ["1A", "1B", "2A", "2B"]},  # sin local ni garaje
}

# comunidad -> [(concepto, importe, grupo o None, plazos, primer vencimiento,
#                fecha de acuerdo o None, fecha de emisión o None)]
DERRAMAS = {
    "CP Calle Ficticia 1": [
        (
            "Arreglo de la fachada",
            "6000.00",
            None,
            3,
            date(2026, 4, 1),
            date(2026, 2, 20),
            date(2026, 3, 1),
        ),
        # Propuesta para la próxima junta: solo la pagarían los pisos (grupo "Ascensor").
        (
            "Cambio de la cabina del ascensor",
            "4800.00",
            "Ascensor",
            6,
            date(2026, 9, 1),
            None,
            None,
        ),
    ],
}


# T2.4 — Datos SEPA FICTICIOS: NIF de comunidad inventado e IBAN de una entidad inexistente
# (9999), con dígitos de control válidos para que pasen la validación.
NIF_DEMO = "H00000000"
IBAN_COBROS_DEMO = construir_iban("ES", "99990000" + "100000000001")
# Propietarios de la comunidad con contabilidad que han firmado un mandato SEPA.
MANDATOS = ["Carmen Ejemplo", "Pablo Prueba", "Jorge Ficticio"]


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
            self._presupuestos()
            self._derramas()
            self._recibos()

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
                comunidad=comunidad,
                codigo=codigo,
                defaults={"nombre": nombre, "es_fondo_reserva": codigo == CUENTA_FONDO_RESERVA},
            )[0]
            for codigo, nombre in CUENTAS
        }

        def D(valor: str) -> Decimal:
            return Decimal(valor)

        # Los asientos son inmutables: cada bloque solo se registra si aún no existe.
        if not cuentas[CUENTA_FONDO_RESERVA].apuntes.exists():
            # R-RES-01: el fondo de reserva es el saldo acreedor de su cuenta.
            registrar_asiento(
                comunidad,
                date(2026, 1, 2),
                "Saldo inicial del fondo de reserva",
                [
                    Linea(cuentas["572"], debe=D("350.00")),
                    Linea(cuentas[CUENTA_FONDO_RESERVA], haber=D("350.00")),
                ],
            )
        if comunidad.asientos.filter(concepto="Cuotas de enero emitidas").exists():
            return

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

    def _presupuestos(self):
        for nombre, presupuestos in PRESUPUESTOS.items():
            comunidad = Comunidad.objects.get(nombre=nombre)
            for ejercicio, aprobado_el, aportacion, partidas in presupuestos:
                presupuesto, creado = Presupuesto.objects.get_or_create(
                    comunidad=comunidad,
                    ejercicio=ejercicio,
                    defaults={"aportacion_fondo_reserva": Decimal(aportacion)},
                )
                if not creado:
                    continue  # si ya existe (quizá aprobado), no se toca
                for concepto, importe in partidas:
                    Partida.objects.create(
                        presupuesto=presupuesto, concepto=concepto, importe=Decimal(importe)
                    )
                # R-PRE-01: se aprueba después de añadir las partidas (luego quedan fijas).
                if aprobado_el:
                    presupuesto.fecha_aprobacion = aprobado_el
                    presupuesto.save()
        # T2.2: el primer trimestre de 2026 ya emitido en la comunidad con contabilidad.
        presupuesto = Presupuesto.objects.get(
            comunidad__nombre=COMUNIDAD_CON_CONTABILIDAD, ejercicio=2026
        )
        if not presupuesto.emisiones.filter(periodo=1).exists():
            emitir_cuotas(presupuesto, 1, date(2026, 1, 5))

    def _derramas(self):
        for nombre, grupos in GRUPOS_REPARTO.items():
            comunidad = Comunidad.objects.get(nombre=nombre)
            for nombre_grupo, referencias in grupos.items():
                grupo, _ = GrupoReparto.objects.get_or_create(
                    comunidad=comunidad, nombre=nombre_grupo
                )
                for referencia in referencias:
                    MiembroGrupo.objects.get_or_create(
                        grupo=grupo, inmueble=comunidad.inmuebles.get(referencia=referencia)
                    )
        for nombre, derramas in DERRAMAS.items():
            comunidad = Comunidad.objects.get(nombre=nombre)
            for concepto, importe, grupo, plazos, vence, acordada, emitir_el in derramas:
                derrama, creada = Derrama.objects.get_or_create(
                    comunidad=comunidad,
                    concepto=concepto,
                    defaults={
                        "importe": Decimal(importe),
                        "grupo": grupo and comunidad.grupos_reparto.get(nombre=grupo),
                        "plazos": plazos,
                        "primer_vencimiento": vence,
                        "fecha_acuerdo": acordada,
                    },
                )
                # Si ya existía, no se toca (quizá ya está emitida y es inmutable).
                if creada and emitir_el:
                    emitir_derrama(derrama, emitir_el)

    def _recibos(self):
        comunidad = Comunidad.objects.get(nombre=COMUNIDAD_CON_CONTABILIDAD)
        if not comunidad.nif:
            comunidad.nif = NIF_DEMO
            comunidad.iban_cobros = IBAN_COBROS_DEMO
            comunidad.save()
        for n, nombre in enumerate(MANDATOS, start=1):
            propietario = Propietario.objects.get(despacho=comunidad.despacho, nombre=nombre)
            Mandato.objects.get_or_create(
                comunidad=comunidad,
                referencia=f"DEMO-{comunidad.pk}-{n:03d}",
                defaults={
                    "propietario": propietario,
                    "titular_cuenta": nombre,
                    "iban": construir_iban("ES", f"99990000{n:012d}"),
                    "fecha_firma": date(2025, 6, 1),
                },
            )
        generar_recibos(comunidad)  # solo crea los que falten
