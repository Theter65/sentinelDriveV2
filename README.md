# SentinelDrive

Sistema de monitoreo y gestión de flotas vehiculares con detección de eventos de riesgo en tiempo real.

## Descripción

SentinelDrive es una aplicación web desarrollada como proyecto de tesis para la **Universidad Nacional de Loja**. El sistema permite la gestión integral de flotas de transporte mediante:

- Recepción de telemetría GPS y eventos de riesgo desde dispositivos ESP32 vía MQTT (TLS)
- Detección en tiempo real de exceso de velocidad, frenado brusco y curva peligrosa
- Dashboard con métricas operativas y estado de la flota
- Mapa de seguimiento GPS con Leaflet
- Reportes estadísticos con gráficos interactivos (Chart.js)
- Gestión de mantenimientos preventivos y correctivos
- Panel de administración con configuración MQTT

## Arquitectura

```
ESP32 (IMU + GPS) → MQTT Broker (TLS 8883) → Flask Backend → PostgreSQL/SQLite → Web UI
```

- **Backend:** Flask 3.1, SQLAlchemy, MQTT Subscriber (paho-mqtt)
- **Frontend:** Bootstrap 5.3, Leaflet, Chart.js, glassmorphism CSS custom
- **Despliegue:** Render (gunicorn + PostgreSQL) o SQLite local
- **Firmware:** ESP32 con filtro Madgwick para orientación y detección de eventos

## Autor

**Gerardo Gonza**  
Universidad Nacional de Loja  
Loja, Ecuador

## Requisitos

- Python 3.8+
- pip

## Instalación

1. Clona el repositorio:
   ```bash
   git clone https://github.com/Theter65/sentinelDriveV2.git
   cd sentinelDriveV2
   ```

2. Crea y activa un entorno virtual:
   ```bash
   # Windows
   python -m venv venv
   venv\Scripts\activate

   # macOS/Linux
   python3 -m venv venv
   source venv/bin/activate
   ```

3. Instala las dependencias:
   ```bash
   pip install -r requirements.txt
   ```

4. Configura las variables de entorno:
   ```bash
   cp .env.example .env
   ```
   Edita `.env` con tu `SECRET_KEY` y, si usas MQTT, las credenciales del broker.

5. Ejecuta la aplicación:
   ```bash
   python run.py
   ```

6. Accede en `http://localhost:5000`

## Despliegue en Render

1. Crea un servicio Web en Render
2. Conecta el repositorio
3. Render detecta automáticamente el `Procfile` y `requirements.txt`
4. Configura las variables de entorno en el dashboard de Render:
   - `SECRET_KEY` (genera una con `python -c "import secrets; print(secrets.token_urlsafe(48))"`)
   - `DATABASE_URL` (PostgreSQL de Render)
   - `MQTT_BROKER`, `MQTT_USERNAME`, `MQTT_PASSWORD`

## Estructura del proyecto

```
sentinelDrive/
├── app/
│   ├── __init__.py          # Factory Flask
│   ├── config.py            # Configuración de entorno
│   ├── models/              # Modelos SQLAlchemy
│   ├── routes/              # Blueprints (10 módulos)
│   ├── mqtt/                # Subscriber MQTT + deduplicación
│   ├── services/            # Lógica de analytics
│   ├── templates/           # 14 templates Jinja2
│   └── utils/               # Utilidades (timezone, CSV, logging)
├── static/
│   ├── css/                 # style.css, theme.css, glass.css
│   ├── js/                  # app.js, chart-theme.js, theme-switcher.js
│   └── img/                 # logos e imágenes
├── docs/                    # Firmware ESP32 (no incluido en el repo)
├── run.py                   # Entry point desarrollo
├── wsgi.py                  # Entry point gunicorn
├── Procfile                 # Despliegue Render
├── requirements.txt         # Dependencias Python
└── .env.example             # Variables de entorno de ejemplo
```

## Todos los derechos reservados

Proyecto de tesis — Universidad Nacional de Loja, 2026.
