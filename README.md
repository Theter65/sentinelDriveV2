# SentinelDrive

Sistema de monitoreo y gestión de flotas vehiculares con detección de eventos de riesgo en tiempo real.

## Descripción

SentinelDrive es una aplicación web desarrollada como proyecto de tesis para la **Universidad Nacional de Loja**. El sistema permite la gestión integral de flotas de transporte mediante:

- Recepción de telemetría GPS y eventos de riesgo desde dispositivos ESP32 y aplicación móvil de validación Android vía MQTT (TLS)
- Detección en tiempo real de exceso de velocidad, frenado brusco y curva peligrosa
- Dashboard con métricas operativas y estado de la flota
- Mapa de seguimiento GPS con Leaflet
- Reportes estadísticos con gráficos interactivos (Chart.js)
- Gestión de mantenimientos preventivos y correctivos
- Panel de administración con configuración MQTT

## Arquitectura

```
[Dispositivo ESP32 (IMU + GPS)] ──┐
                                  ├──► [MQTT Broker (TLS 8883)] ──► [Flask Backend] ──► [PostgreSQL/SQLite] ──► [Web UI]
[App Android (Sensores + GPS)]  ──┘
```

- **Backend:** Flask 3.1, SQLAlchemy, MQTT Subscriber (paho-mqtt)
- **Frontend:** Bootstrap 5.3, Leaflet, Chart.js, glassmorphism CSS custom
- **Despliegue:** Render (gunicorn + PostgreSQL) o SQLite local
- **Firmware ESP32:** FreeRTOS multicore, MPU6050 + NEO-6M, filtro Madgwick, cola SD offline
- **App Android (Validación):** Kotlin, Jetpack Compose, Madgwick AHRS, Foreground Service, Room (cola offline), Paho MQTT con TLS


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

## Aplicación Móvil de Validación (Android)
 
Ubicada en `SentinlDriveAppAndroid/`, esta aplicación nativa actúa como gemelo digital del dispositivo físico para validación y pruebas de campo en vehículos reales:
 
- **Lectura de Sensores:** Adquisición de acelerómetro y giroscopio del smartphone a alta frecuencia con filtro **Madgwick AHRS** para desacoplar la gravedad y obtener aceleraciones lineales (`linX`, `linY`, `linZ`) y ángulos pitch/roll.
- **Detección Cinemática de Eventos:** Réplica idéntica de los algoritmos de ventana deslizante del firmware ESP32 (frenadas bruscas, curvas peligrosas y excesos de velocidad sostenidos según normativa LOTTTSV).
- **Conectividad MQTT con TLS:** Conexión segura `ssl://broker:8883` mediante Eclipse Paho MQTT y autenticación gestionada desde la interfaz.
- **Resiliencia Offline:** Base de datos **Room** para encolar paquetes de telemetría y eventos si se pierde la cobertura celular, con reenvío automático al reconectar.
- **Servicio en Primer Plano:** `TelemetryForegroundService` con notificación persistente para operar en segundo plano sin interrupciones por optimización de batería (Android 14+ compatible).
- **Calibración y Logs:** Pantallas de calibración de offsets para el sensor y visualizadores de logs en tiempo real.

### Compilación de la App Android
 
1. Abrir la carpeta `SentinlDriveAppAndroid` en **Android Studio**.
2. Esperar a que Gradle sincronice las dependencias.
3. Compilar y desplegar en dispositivo físico o emulador:
   ```bash
   cd SentinlDriveAppAndroid
   ./gradlew assembleDebug
   ```

## Estructura del proyecto

```
sentinelDrive/
├── app/                             # Aplicación Web y API Flask
│   ├── __init__.py                  # Factory Flask
│   ├── config.py                    # Configuración de entorno y MQTT
│   ├── models/                      # Modelos SQLAlchemy (Bus, Event, Location, etc.)
│   ├── routes/                      # Blueprints y controladores web
│   ├── mqtt/                        # Subscriber MQTT en segundo plano + deduplicación
│   ├── services/                    # Lógica de analítica y métricas
│   ├── templates/                   # Templates Jinja2
│   └── utils/                       # Utilidades (timezone, logging, CSV)
├── static/                          # Recursos estáticos (CSS, JS, imágenes)
├── CodigoESP32(Dispositivo)/        # Firmware del hardware embebido (ESP32 Arduino/FreeRTOS)
├── SentinlDriveAppAndroid/          # Aplicación Android de validación (Kotlin + Jetpack Compose)
│   ├── app/                         # Módulo principal de la aplicación móvil
│   ├── gradle/                      # Configuración de Gradle Wrapper y catálogos de versiones
│   └── SENTNLDRIVE_event_config.md  # Especificaciones técnicas de eventos
├── run.py                           # Entry point desarrollo local
├── wsgi.py                          # Entry point producción (gunicorn)
├── Procfile                         # Configuración de despliegue en Render
├── requirements.txt                 # Dependencias Python
└── .env.example                     # Plantilla de variables de entorno
```

## Todos los derechos reservados

Proyecto de tesis — Universidad Nacional de Loja, 2026.

