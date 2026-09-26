# SENTINELDRIVE - GPS Test Code (TEST_GPS_SERIAL)

> Caracteristicas del firmware de prueba GPS
> Fecha: 2026-06-30

---

## Hardware

| Componente | Modelo | Configuracion |
|------------|--------|---------------|
| Microcontrolador | ESP32 | - |
| GPS | NEO-6M (GY-GPS6MV2) | RX=16, TX=17, 9600 baud |
| Bateria backup | ML1220 (recargable) | RTC + ephemeris ~4h |

---

## Muestreo

| Parametro | Valor |
|-----------|-------|
| GPS update rate | 1 Hz (1 vez por segundo) |
| Baud GPS | 9600 |
| Baud Serial | 115200 |
| Deteccion velocidad | 1 Hz (cada muestra GPS) |

---

## Precision

| Parametro | Valor |
|-----------|-------|
| Formula | HDOP x 2.5 metros |
| HDOP ideal | < 2.0 (precision < 5m) |
| HDOP aceptable | < 5.0 (precision < 12.5m) |

---

## EEPROM - Warm Start

Guarda la ultima posicion conocida para reducir tiempo de fix al reiniciar.

| Campo | Tipo | Tamano | Descripcion |
|-------|------|--------|-------------|
| magic | uint8 | 1 byte | 0xA5 = datos validos |
| lat | double | 8 bytes | Latitud |
| lon | double | 8 bytes | Longitud |
| alt | float | 4 bytes | Altitud (metros) |
| speed | float | 4 bytes | Velocidad (km/h) |
| course | float | 4 bytes | Curso (grados) |
| year | uint16 | 2 bytes | Ano UTC |
| month | uint8 | 1 byte | Mes UTC |
| day | uint8 | 1 byte | Dia UTC |
| hour | uint8 | 1 byte | Hora UTC |
| minute | uint8 | 1 byte | Minuto UTC |
| second | uint8 | 1 byte | Segundo UTC |
| savedAtMs | uint32 | 4 bytes | millis() al guardar |
| saveCount | uint32 | 4 bytes | Veces que se ha guardado |
| satsAtSave | uint8 | 1 byte | Satelites visibles |
| hdopX10 | uint8 | 1 byte | HDOP x 10 |
| **Total** | | **~64 bytes** | |

### Tipos de start

| Tipo | Tiempo fix | Condicion |
|------|-----------|-----------|
| Hot Start | < 5 segundos | Bateria buena + < 4 horas apagado |
| Warm Start | 15-30 segundos | EEPROM con posicion valida |
| Cold Start | 2-17 minutos | Sin bateria ni EEPROM |

---

## Deteccion Exceso de Velocidad

| Parametro | Valor |
|-----------|-------|
| Umbral | 90 km/h (Art. 191 LOTTTSV Ecuador) |
| Ventana | 5 segundos continuos |
| Condicion | TODOS los valores > 90 km/h durante 5s |
| Cooldown | 30 segundos entre eventos |

### Logica

```
Cada segundo (1 Hz GPS):
  1. Si speed > 90 → Iniciar ventana
  2. Si speed <= 90 → Cancelar ventana
  3. Si ventana > 5s continua → Evento (si cooldown listo)
```

---

## Monitoreo Bateria Backup

El modulo GY-GPS6MV2 tiene bateria ML1220 recargable que:
- Se carga automaticamente cuando el modulo esta encendido
- Mantiene RTC y ephemeris GPS por ~4 horas
- Permite hot start si se reinicia antes de 4 horas

### Diagnostico

| Start type | Estado bateria | Accion |
|------------|---------------|--------|
| Hot Start (< 5s) | EXCELENTE | Bateria funciona perfecto |
| Warm Start (< 30s) | BUENA | Bateria retiene posicion |
| Cold Start (> 30s) | REGULAR/MALA | Revisar bateria o soldadura |

---

## Comandos Serial

| Comando | Descripcion |
|---------|-------------|
| **Control** | |
| run | Inicia streaming GPS |
| pause | Pausa streaming |
| **Modos de salida** | |
| console | Datos parseados cada 1s (lat, lon, sats, hdop, speed, etc) |
| raw | Tramas NMEA crudas completas |
| plot | CSV para Serial Plotter (6 columnas) |
| sats | Monitoreo de satelites cada 500ms |
| **GPS** | |
| warm | Warm start con posicion guardada en EEPROM |
| cold | Cold start (borrar memoria GPS) |
| **EEPROM** | |
| save | Guardar posicion actual en EEPROM |
| saved | Ver posicion guardada con todos los campos |
| clear | Borrar posicion de EEPROM |
| **Bateria** | |
| battery | Estado bateria backup + tipo de start |
| **Velocidad** | |
| speed | Config y estado deteccion exceso velocidad |
| **Info** | |
| diag | Diagnostico detallado del modulo GPS |
| status | Ver configuracion actual completa |
| help | Lista de comandos |

---

## Formato Console (1 Hz)

```
ms=12345, sats=8, valid=1, lat=-4.0123456, lon=-79.2123456, hdop=1.20, precision_m=3.0, speed_kmh=85.3, course=180.0, date=2026-06-30, time=20:45:07, chars=203, chk_ok=168, chk_err=0
```

| Campo | Descripcion |
|-------|-------------|
| ms | Tiempo desde inicio (ms) |
| sats | Satelites visibles |
| valid | 1=fix valido, 0=sin fix |
| lat | Latitud (7 decimales) |
| lon | Longitud (7 decimales) |
| hdop | Horizontal Dilution of Precision |
| precision_m | Estimacion metros (HDOP x 2.5) |
| speed_kmh | Velocidad en km/h |
| course | Direccion en grados (0=N, 90=E, 180=S, 270=W) |
| date | Fecha UTC (YYYY-MM-DD) |
| time | Hora UTC (HH:MM:SS) |
| chars | Bytes recibidos este segundo |
| chk_ok | Checksums NMEA exitosos |
| chk_err | Checksums NMEA fallidos |

---

## Formato Plot (CSV, 1 Hz)

```
lat,lon,sats,hdop,speed,course
```

---

## Formato SATS (500 ms)

```
sats=8 | hdop=1.20 | fix=SI | age=1000ms | max_sats=12 | min_hdop=0.80 | max_speed=95.3 km/h | fix_since=120s
```

---

## Tramas NMEA

El GPS envia tramas en formato texto por UART:

| Trama | Contenido |
|-------|-----------|
| $GPRMC | Posicion, velocidad, curso, fecha/hora |
| $GPGGA | Posicion, sats, HDOP, altitud |
| $GPGSA | Dilucion de precisión (PDOP, HDOP, VDOP) |
| $GPGSV | Satelites visibles |

Usar comando `raw on` para ver tramas crudas.

---

## Diagnostico

El comando `diag` muestra:

| Seccion | Info |
|---------|------|
| UART | Chars, checksums, tiempo ultimo char |
| GPS | Location, sats, HDOP, speed, date, time |
| Rendimiento | Max sats, min HDOP, max speed, tiempo al fix |
| Diagnostico | Problema detectado + recomendacion |

### Problemas comunes

| Sintoma | Causa | Solucion |
|---------|-------|----------|
| No llegan bytes | Sin alimentacion o RX/TX cruzado | Verificar cables |
| Checksum falla | Baud incorrecto o ruido | Verificar baud 9600 |
| Sin fix | Dentro de edificio | Sacar al aire libre |
| Cold start siempre | Bateria backup agotada | Reemplazar ML1220 |

---

*SENTINELDRIVE - Universidad Nacional de Loja*
