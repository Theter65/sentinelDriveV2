# =============================================================================
# app/config.py - Configuración centralizada de la aplicación
#
# Usa .env para valores sensibles (SECRET_KEY, MQTT_PASSWORD, etc.)
# No se sube a git. Valores por defecto solo para desarrollo.
# =============================================================================

import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Seguridad básica (obligatorio en producción)
    SECRET_KEY = os.getenv('SECRET_KEY')
    if not SECRET_KEY:
        raise ValueError("SECRET_KEY no está definido en .env")

    # Base de datos (SQLite por defecto, PostgreSQL en producción)
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL') or 'sqlite:///sentinldrive.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = os.getenv('SQLALCHEMY_ECHO', 'False').lower() == 'true'  # Logs SQL (solo dev)

    # MQTT (valores sensibles desde .env)
    MQTT_BROKER = os.getenv('MQTT_BROKER', "006b41188f8e4c48ad4936cbef2e695a.s1.eu.hivemq.cloud")
    MQTT_PORT = int(os.getenv('MQTT_PORT', 8883))
    MQTT_USERNAME = os.getenv('MQTT_USERNAME', "CajaN3gr4")
    MQTT_PASSWORD = os.getenv('MQTT_PASSWORD')
    if not MQTT_PASSWORD:
        raise ValueError("MQTT_PASSWORD no está definido en .env - obligatorio")

    # Otros ajustes útiles
    DEBUG = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    TESTING = False

    # En config.py (solo para pruebas rápidas)
    WTF_CSRF_ENABLED = False