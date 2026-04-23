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


def _load_or_create_secret_key() -> str:
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
    SECRET_KEY = _load_or_create_secret_key()

    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL") or "sqlite:///sentinldrive.db"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = os.getenv("SQLALCHEMY_ECHO", "False").lower() == "true"

    MQTT_BROKER = os.getenv("MQTT_BROKER", "006b41188f8e4c48ad4936cbef2e695a.s1.eu.hivemq.cloud")
    MQTT_PORT = int(os.getenv("MQTT_PORT", "8883"))
    MQTT_USERNAME = os.getenv("MQTT_USERNAME", "CajaN3gr4")
    MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "")
    MQTT_TOPIC_GPS = os.getenv("MQTT_TOPIC_GPS", "flota/ecuador/buses/+/gps")
    MQTT_TOPIC_EVENT = os.getenv("MQTT_TOPIC_EVENT", "flota/ecuador/buses/+/event")

    DEBUG = os.getenv("FLASK_DEBUG", "False").lower() == "true"
    TESTING = False
    WTF_CSRF_ENABLED = os.getenv("WTF_CSRF_ENABLED", "True").lower() == "true"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "False").lower() == "true"
    PERMANENT_SESSION_LIFETIME = timedelta(
        minutes=int(os.getenv("SESSION_LIFETIME_MINUTES", 120))
    )
