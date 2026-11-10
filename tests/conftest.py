import pytest


@pytest.fixture(autouse=True)
def _claves_rapidas_en_tests(settings):
    """Cifrar contraseñas es lento a propósito (para frenar ataques de fuerza bruta).
    En los tests no aporta nada y multiplica su duración, así que usamos un algoritmo
    rápido. Solo afecta a los tests, nunca a la aplicación real."""
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
