# SENTINELDRIVE - Firmware Principal ESP32

> Firmware completo del dispositivo SentnlDrive + scripts de validacion
> Fecha: 2026-07

---

## Contenido

```
SentnlDrive_ESP32_V2/
├── SentnlDrive_ESP32_V2.ino          # Firmware principal
├── SentnlDrive_ESP32_V2punsub/       # Backup (version original esp-mqtt)
└── Compartion/                       # Scripts y datos de validacion
    ├── validacion_tesis.py           # Script principal de validacion
    ├── APP y Dispositivo_*.xlsx      # Datos de campo
    ├── *.png                         # Graficas generadas
    ├── *.tex                         # Tablas LaTeX
    └── *.txt                         # Resumenes de texto
```

---

## Firmware: SentnlDrive_ESP32_V2.ino

### Hardware

| Componente | Modelo | Configuracion |
|------------|--------|---------------|
| Microcontrolador | ESP32 | - |
| GPS | NEO-6M | RX=16, TX=17, 9600 baud |
| IMU | MPU6050 | SDA=21, SCL=22, 400kHz I2C |
| SD Card | MicroSD | CS=5 |
| Buzzer | Piezo | GPIO=4 |
| OLED | SSD1306 | I2C (misma bus que IMU) |

### Conectividad

| Parametro | Valor |
|-----------|-------|
| WiFi | WPA2, reconexion automatica con backoff |
| MQTT Broker | HiveMQ Cloud |
| Puerto | 8883 (TLS) |
| Topics | `flota/ecuador/buses/{id}/gps`, `/event` |
| Libreria MQTT | PubSubClient + WiFiClientSecure |
| TLS | `setInsecure()` (sin verificacion de certificado) |

### Sensores y muestreo

| Sensor | Frecuencia | Uso |
|--------|-----------|-----|
| GPS | 1 Hz | Posicion, velocidad, curso |
| IMU | 100 Hz | Aceleracion, orientacion |
| Deteccion eventos | 100 Hz | Frenado brusco, exceso velocidad, curva peligrosa |

### Eventos detectados

| Evento | Umbral | Variable | Condicion |
|--------|--------|----------|-----------|
| frenado_brusco | -2.94 m/s2 (-0.3g) | a_long | >=80% muestras en ventana 50 |
| exceso_velocidad | 90 km/h | speed | 5 segundos continuos |
| curva_peligrosa | 0.4g lateral | a_lat | >=80% muestras en ventana 50 |

### JSON enviado via MQTT

```json
{
  "lat": -4.0123456,
  "lon": -79.2123456,
  "speed": 85.3,
  "alt": 2500.0,
  "sats": 8,
  "hdop": 1.2,
  "event": "frenado_brusco",
  "event_value": -4.80,
  "ts": "2026-07-01T12:00:00Z"
}
```

---

## Compartion/ - Validacion de tesis

### Script: validacion_tesis.py

Genera graficas y tablas comparativas entre Dispositivo (ESP32) y Aplicacion (Android).

```bash
pip install pandas numpy matplotlib openpyxl
python validacion_tesis.py
```

### Datos de entrada

| Archivo | Descripcion |
|---------|-------------|
| `APP y Dispositivo_LojaAlamor.csv.xlsx` | Viaje ida (Loja a Alamor) |
| `APP y Dispositivo_AlamorLoja.xlsx` | Viaje vuelta (Alamor a Loja) |

### Figuras generadas (10+)

| Archivo | Descripcion |
|---------|-------------|
| `eventos_ida.png` | Comparativa barras de eventos (ida) |
| `eventos_vuelta.png` | Comparativa barras de eventos (vuelta) |
| `evento_exceso_de_velocidad_ida.png` | Detalle exceso velocidad (ida) |
| `evento_frenado_brusco_vuelta.png` | Detalle frenado brusco (vuelta) |
| `evento_curva_peligrosa_vuelta.png` | Detalle curva peligrosa (vuelta) |
| `ruta_gps_ida.png` | Ruta GPS scatter plot |
| `mapa_ruta_ida.png` | Mapa con OpenStreetMap |
| `comparacion_gps_ida.png` | Lat, Lon, Vel vs tiempo (3 subplots) |
| `velocidad_comparacion_ida.png` | Velocidad con area sombreada |
| `haversine_ida.png` | Distancia Haversine vs tiempo |

### Tablas LaTeX

| Archivo | Contenido |
|---------|-----------|
| `tabla_eventos_ida.tex` | Eventos pareados con MAE, RMSE |
| `tabla_eventos_vuelta.tex` | Mismo formato para vuelta |
| `tabla_metricas_gps.tex` | Metricas GPS: MAE, RMSE, Maximo |

---

## SentnlDrive_ESP32_V2punsub/

Backup del firmware original usando esp-mqtt (antes de migrar a PubSubClient). Mantiene la configuracion original del broker y topics.

---

*SENTINELDRIVE - Universidad Nacional de Loja*
