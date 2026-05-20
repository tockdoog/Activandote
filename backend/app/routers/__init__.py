# backend/app/routers/__init__.py
# Exportación centralizada de todos los routers de la aplicación

from app.routers import auth, patients, evaluations, dashboard

__all__ = ["auth", "patients", "evaluations", "dashboard"]