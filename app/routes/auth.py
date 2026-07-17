# app/routes/auth.py - Autenticación y configuración inicial
#
# Gestiona el login de usuarios, el wizard de primera configuración
# (creación del admin inicial + setup MQTT) y el cierre de sesión.
# La ruta /setup solo está disponible cuando no hay administradores.
# =============================================================================

import time
import threading
from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from werkzeug.security import generate_password_hash

from app.decorators import login_required
from app.extensions import db
from app.models.system_setting import SystemSetting
from app.models.user import User
from app.mqtt.subscriber import request_mqtt_reload, test_mqtt_connection
from app.utils.logging import get_logger
from app.utils.system_settings import get_mqtt_form_defaults, get_runtime_mqtt_settings, has_admin_user


logger = get_logger(__name__)

auth_bp = Blueprint("auth", __name__)

# Rate limiter para login: {ip: [timestamp1, timestamp2, ...]}
_login_attempts: dict[str, list[float]] = {}
_login_lock = threading.Lock()
MAX_LOGIN_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 300  # 5 minutos


def _setup_form_state() -> dict:
    mqtt_defaults = get_mqtt_form_defaults(current_app.config)
    return {
        "admin_username": (request.form.get("admin_username") or "").strip() or "admin",
        "configure_mqtt_now": request.form.get("configure_mqtt_now") == "on",
        "mqtt_broker": (request.form.get("mqtt_broker") or str(mqtt_defaults["mqtt_broker"])).strip(),
        "mqtt_port": (request.form.get("mqtt_port") or str(mqtt_defaults["mqtt_port"])).strip(),
        "mqtt_username": (request.form.get("mqtt_username") or str(mqtt_defaults["mqtt_username"])).strip(),
        "mqtt_topic_gps": (request.form.get("mqtt_topic_gps") or str(mqtt_defaults["mqtt_topic_gps"])).strip(),
        "mqtt_topic_event": (request.form.get("mqtt_topic_event") or str(mqtt_defaults["mqtt_topic_event"])).strip(),
        "mqtt_password_saved": bool(mqtt_defaults["mqtt_password_saved"]),
    }


def _save_mqtt_settings(form_data: dict, mqtt_password: str):
    """Persiste la configuracion MQTT inicial cuando el asistente la valida."""
    SystemSetting.set_value("mqtt_broker", form_data["mqtt_broker"])
    SystemSetting.set_value("mqtt_port", form_data["mqtt_port"])
    SystemSetting.set_value("mqtt_username", form_data["mqtt_username"])
    SystemSetting.set_value("mqtt_topic_gps", form_data["mqtt_topic_gps"])
    SystemSetting.set_value("mqtt_topic_event", form_data["mqtt_topic_event"])
    SystemSetting.set_value("mqtt_password", mqtt_password)


@auth_bp.route("/", methods=["GET", "POST"])
def login():
    """Pagina de inicio de sesion."""
    if not has_admin_user():
        return redirect(url_for("auth.initial_setup"))

    if request.method == "POST":
        client_ip = request.remote_addr or "unknown"
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""

        # Rate limit: bloquear IP después de MAX_LOGIN_ATTEMPTS en LOGIN_WINDOW_SECONDS
        now = time.time()
        with _login_lock:
            attempts = _login_attempts.get(client_ip, [])
            # Limpiar intentos fuera de la ventana
            attempts = [t for t in attempts if now - t < LOGIN_WINDOW_SECONDS]
            if len(attempts) >= MAX_LOGIN_ATTEMPTS:
                _login_attempts[client_ip] = attempts
                logger.warning("Login bloqueado por rate limit: IP=%s intentos=%d", client_ip, len(attempts))
                return render_template("login.html", error="Demasiados intentos. Espera 5 minutos.")
            _login_attempts[client_ip] = attempts

        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            # Limpiar intentos exitosos
            with _login_lock:
                _login_attempts.pop(client_ip, None)
            session.clear()
            session["user"] = user.username
            session["role"] = user.role.lower()
            session.permanent = True
            logger.info("Login exitoso: %s (role=%s)", username, session["role"])
            if session["role"] == "admin" and not get_runtime_mqtt_settings(current_app.config)["ready"]:
                flash("Configura MQTT para empezar a recibir ubicaciones y alertas.", "warning")
                return redirect(url_for("admin.admin_panel"))
            return redirect(url_for("dashboard.dashboard"))

        # Registrar intento fallido
        with _login_lock:
            _login_attempts.setdefault(client_ip, []).append(now)

        logger.warning("Intento de login fallido para usuario: %s IP: %s", username or "<vacio>", client_ip)
        return render_template("login.html", error="Credenciales incorrectas")
    return render_template("login.html")


@auth_bp.route("/setup", methods=["GET", "POST"])
def initial_setup():
    """Wizard de primera configuracion para crear el administrador inicial."""
    if has_admin_user():
        if "user" in session:
            return redirect(url_for("dashboard.dashboard"))
        return redirect(url_for("auth.login"))

    form_state = _setup_form_state()

    if request.method == "POST":
        admin_username = form_state["admin_username"]
        admin_password = request.form.get("admin_password") or ""
        confirm_password = request.form.get("confirm_password") or ""
        mqtt_password = request.form.get("mqtt_password") or ""

        if len(admin_username) < 4:
            return render_template(
                "setup.html",
                error="El usuario administrador debe tener al menos 4 caracteres.",
                form_data=form_state,
            )
        if User.query.filter_by(username=admin_username).first():
            return render_template(
                "setup.html",
                error="Ese nombre de usuario ya existe.",
                form_data=form_state,
            )
        if len(admin_password) < 8:
            return render_template(
                "setup.html",
                error="La contrasena debe tener al menos 8 caracteres.",
                form_data=form_state,
            )
        if admin_password != confirm_password:
            return render_template(
                "setup.html",
                error="La confirmacion de contrasena no coincide.",
                form_data=form_state,
            )

        if form_state["configure_mqtt_now"]:
            try:
                mqtt_port = int(form_state["mqtt_port"])
            except ValueError:
                return render_template(
                    "setup.html",
                    error="El puerto MQTT debe ser numerico.",
                    form_data=form_state,
                )

            if mqtt_port <= 0:
                return render_template(
                    "setup.html",
                    error="El puerto MQTT debe ser mayor a cero.",
                    form_data=form_state,
                )
            if not mqtt_password:
                return render_template(
                    "setup.html",
                    error="Debes ingresar la clave del servidor MQTT.",
                    form_data=form_state,
                )
            if not all(
                [
                    form_state["mqtt_broker"],
                    form_state["mqtt_username"],
                    form_state["mqtt_topic_gps"],
                    form_state["mqtt_topic_event"],
                ]
            ):
                return render_template(
                    "setup.html",
                    error="Completa todos los datos de MQTT o desactiva esa opcion para configurarlo despues.",
                    form_data=form_state,
                )

            mqtt_ok, mqtt_message = test_mqtt_connection(
                form_state["mqtt_broker"],
                mqtt_port,
                form_state["mqtt_username"],
                mqtt_password,
                topics=[
                    (form_state["mqtt_topic_gps"], 0),
                    (form_state["mqtt_topic_event"], 1),
                ],
            )
            if not mqtt_ok:
                return render_template(
                    "setup.html",
                    error=f"{mqtt_message} Corrige los datos e intenta nuevamente.",
                    form_data=form_state,
                )

        try:
            admin_user = User(username=admin_username, role="admin")
            admin_user.set_password(admin_password)
            db.session.add(admin_user)

            if form_state["configure_mqtt_now"]:
                _save_mqtt_settings(form_state, mqtt_password)

            db.session.commit()
            session.clear()
            session["user"] = admin_user.username
            session["role"] = admin_user.role.lower()
            session.permanent = True

            if form_state["configure_mqtt_now"]:
                request_mqtt_reload()
                flash("Configuracion MQTT guardada. El suscriptor se reiniciara.", "success")
            else:
                flash("Administrador creado. Configura MQTT para recibir ubicaciones y alertas.", "warning")

            logger.info("Configuracion inicial completada con admin: %s", admin_username)
            if form_state["configure_mqtt_now"]:
                return redirect(url_for("dashboard.dashboard"))
            return redirect(url_for("admin.admin_panel"))
        except Exception as exc:
            db.session.rollback()
            logger.error("Error al guardar configuracion inicial: %s", exc, exc_info=True)
            return render_template(
                "setup.html",
                error="No se pudo guardar la configuracion inicial. Revisa los datos e intenta otra vez.",
                form_data=form_state,
            )

    return render_template("setup.html", form_data=form_state)


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    """Cerrar sesion y limpiar datos de sesion."""
    username = session.get("user")
    logger.info("Logout exitoso: %s", username)
    session.clear()
    return redirect(url_for("auth.login"), code=303)
