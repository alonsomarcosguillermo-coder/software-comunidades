# Comunidades

Gestión de comunidades de vecinos para administradores de fincas (proyecto de aprendizaje).
Django + HTMX + PostgreSQL. Ver `docs/SPEC.md` y `docs/PLAN.md`.

## Puesta en marcha (Windows)
Requisitos: Python 3.13, Git y Docker Desktop.

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
docker compose up -d db
.venv\Scripts\python.exe manage.py migrate
.venv\Scripts\python.exe manage.py createsuperuser
.venv\Scripts\python.exe manage.py cargar_demo   # datos de ejemplo ficticios (opcional)
.venv\Scripts\python.exe manage.py runserver
```
- Aplicación: http://127.0.0.1:8000/ (entra con un usuario de demo, p. ej. `admin.beta`)
- Admin de Django: http://127.0.0.1:8000/admin/ (superusuario)

`cargar_demo` crea los despachos Fincas Alfa y Fincas Beta, sus comunidades y los usuarios
`admin.alfa`, `empleado.alfa`, `admin.beta` y `vecino.lucia` con la clave
`demo-comunidades-2026`. Solo funciona con `DEBUG` activo y se puede repetir sin duplicar datos.

## Tests
```powershell
.venv\Scripts\python.exe -m pytest
.venv\Scripts\ruff.exe check .
```
