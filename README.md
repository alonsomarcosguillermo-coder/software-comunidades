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
.venv\Scripts\python.exe manage.py runserver
```
Abre http://127.0.0.1:8000/admin/

## Tests
```powershell
.venv\Scripts\python.exe -m pytest
.venv\Scripts\ruff.exe check .
```
