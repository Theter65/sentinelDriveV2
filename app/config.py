"""Configuracion central de entorno, base de datos, sesiones y MQTT."""

import os
import secrets
from pathlib import Path
from datetime import timedelta
import logging

from dotenv import load_dotenv


load_dotenv()
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
INSTANCE_DIR = BASE_DIR / "instance"
SECRET_KEY_FILE = INSTANCE_DIR / ".secret_key"
DEFAULT_MQTT_PORT = 8883
DEFAULT_MQTT_TOPIC_GPS = "flota/ecuador/buses/+/gps"
DEFAULT_MQTT_TOPIC_EVENT = "flota/ecuador/buses/+/event"


def _database_url() -> str:
    """Resuelve la URL de base de datos desde entorno o SQLite local."""
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        if database_url.startswith("postgres://"):
            return database_url.replace("postgres://", "postgresql://", 1)
        return database_url
    return "sqlite:///sentinldrive.db"


def _env_int(name: str, default: int) -> int:
    """Lee enteros de entorno con valor seguro por defecto."""
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        logger.warning("%s invalido. Se usara %s.", name, default)
        return default


def _env_bool(name: str, default: bool) -> bool:
    """Convierte flags de entorno a booleanos consistentes."""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _load_or_create_secret_key() -> str:
    """Obtiene o crea una clave secreta local fuera del repositorio."""
    secret_key = os.getenv("SECRET_KEY")
    if secret_key:
        return secret_key

    try:
        INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
        if SECRET_KEY_FILE.exists():
            stored_key = SECRET_KEY_FILE.read_text(encoding="utf-8").strip()
            if stored_key:
                logger.warning("SECRET_KEY no encontrado en .env. Se usara la clave local de instance/.secret_key.")
                return stored_key

        generated_key = secrets.token_urlsafe(48)
        SECRET_KEY_FILE.write_text(generated_key, encoding="utf-8")
        logger.warning("SECRET_KEY no encontrado en .env. Se creo una clave local en %s.", SECRET_KEY_FILE)
        return generated_key
    except OSError:
        logger.warning("No se pudo leer ni guardar instance/.secret_key. Se usara una clave temporal para esta ejecucion.")
        return secrets.token_urlsafe(48)


class Config:
    """Valores de configuracion usados por Flask y los servicios internos."""
    SECRET_KEY = _load_or_create_secret_key()
    IS_RENDER = bool(os.getenv("RENDER")) or bool(os.getenv("RENDER_EXTERNAL_URL"))

    SQLALCHEMY_DATABASE_URI = _database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = os.getenv("SQLALCHEMY_ECHO", "False").lower() == "true"

    MQTT_BROKER = os.getenv("MQTT_BROKER", "")
    MQTT_PORT = _env_int("MQTT_PORT", DEFAULT_MQTT_PORT)
    MQTT_USERNAME = os.getenv("MQTT_USERNAME", "")
    MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "")
    MQTT_TOPIC_GPS = os.getenv("MQTT_TOPIC_GPS", DEFAULT_MQTT_TOPIC_GPS)
    MQTT_TOPIC_EVENT = os.getenv("MQTT_TOPIC_EVENT", DEFAULT_MQTT_TOPIC_EVENT)

    DEBUG = os.getenv("FLASK_DEBUG", "False").lower() == "true"
    TESTING = False
    WTF_CSRF_ENABLED = os.getenv("WTF_CSRF_ENABLED", "True").lower() == "true"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
    SESSION_COOKIE_SECURE = _env_bool("SESSION_COOKIE_SECURE", IS_RENDER)
    PREFERRED_URL_SCHEME = os.getenv("PREFERRED_URL_SCHEME", "https" if IS_RENDER else "http")
    USE_PROXY_FIX = _env_bool("USE_PROXY_FIX", IS_RENDER)
    PERMANENT_SESSION_LIFETIME = timedelta(
        minutes=int(os.getenv("SESSION_LIFETIME_MINUTES", 120))
    )
