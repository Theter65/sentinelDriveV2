# =============================================================================
# EXTENSIONS - Extensiones globales de Flask
#
# Este archivo centraliza la inicialización de extensiones como SQLAlchemy,
# CSRFProtect, etc. para evitar importaciones circulares y facilitar
# la configuración en diferentes entornos (dev/prod).
# =============================================================================

from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect


# Instancias globales (se inicializan en app/__init__.py)
db = SQLAlchemy()
csrf = CSRFProtect()

# Opcional: si más adelante agregas Flask-Login, Mail, etc., aquí van
# from flask_login import LoginManager
# login_manager = LoginManager()