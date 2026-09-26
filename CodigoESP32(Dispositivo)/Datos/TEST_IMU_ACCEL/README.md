# SENTINELDRIVE - IMU Test Code (TEST_IMU_ACCEL_100_200HZ)

> Caracteristicas del firmware de prueba IMU
> Fecha: 2026-06-28

---

## Hardware

| Componente | Modelo | I2C |
|------------|--------|-----|
| Microcontrolador | ESP32 | - |
| IMU | MPU6050 | SDA=21, SCL=22, 400kHz |
| GPS | NEO-6M | - |

---

## Muestreo

| Parametro | Valor |
|-----------|-------|
| Sample rate | 100 Hz (cada muestra) |
| Display consola | 1 Hz (solo visualizacion) |
| Deteccion eventos | 100 Hz (cada muestra) |
| Plot mode | 20 Hz (CSV) |

**Regla**: Todo el procesamiento (filtro, compensacion de gravedad, deteccion de eventos) corre a 100Hz. Solo la impresion en consola es a 1Hz.

---

## Filtro

| Parametro | Valor |
|-----------|-------|
| Libreria | SimpleFusion (complementario) |
| Alpha gyro | 0.98 |
| Alpha accel | 0.98 |
| Salida | Pitch y Roll (grados) |

---

## Compensacion de Gravedad

```cpp
pitchRad = -lastPitch * DEG2RAD;   // invertido por SimpleFusion
rollRad  = -lastRoll  * DEG2RAD;
g_body_x =  G * sin(pitchRad);
g_body_y = -G * sin(rollRad) * cos(pitchRad);
g_body_z =  G * cos(rollRad) * cos(pitchRad);
```

---

## Orientacion del Sensor

| ID | Orientacion | Mapeo LONG/LAT/VERT |
|----|-------------|----------------------|
| 0 | Plano (Z arriba) | X->LONG, Y->LAT, Z->VERT |
| 1 | Vertical (X abajo) | Z->LONG, Y->LAT, X->VERT |
| 2 | Vertical (X arriba) | -Z->LONG, Y->LAT, -X->VERT |
| 3 | Vertical (Y abajo) | X->LONG, Z->LAT, Y->VERT |
| 4 | Vertical (Y arriba) | X->LONG, -Z->LAT, -Y->VERT |
| 5 | Invertido (Z abajo) | -X->LONG, Y->LAT, -Z->VERT |

---

## Calibracion

| Parametro | Valor |
|-----------|-------|
| Metodo | Software (offsets) |
| Muestras | 2000 |
| Requisito | Sensor QUIETO sobre superficie nivelada |
| Gyro offsets | deg/s |
| Acc offsets | m/s2 (Az ajustado -9.80665) |

---

## Deteccion de Eventos

| Parametro | Valor |
|-----------|-------|
| Evento | frenado_brusco |
| Variable | a_long (LONG) |
| Umbral | -2.94 m/s2 (-0.3g) |
| Ventana | 50 muestras (0.5s @100Hz) |
| Condicion | >= 80% de muestras superan umbral |
| Cooldown | 3 segundos |

**JSON de evento:**
```json
{"type":"event","event":"frenado_brusco","value1":-4.80}
```

`value1` = promedio de la ventana de deteccion (m/s2)

---

## Modo Plot - Columnas CSV

| Columnas | Contenido | Unidad |
|----------|-----------|--------|
| 1-3 | Acc RAW (sin offsets) | m/s2 |
| 4-6 | Acc FILTRADO (con offsets) | m/s2 |
| 7-9 | Acc LINEAL (sin gravedad) | m/s2 |
| 10-12 | Gyro RAW (sin offsets) | deg/s |
| 13-15 | Gyro FILTRADO (con offsets) | deg/s |
| 16 | Pitch | deg |
| 17 | Roll | deg |

**Frecuencia de muestreo del plot**: 20 Hz (cada 50ms)

### Orden exacto de columnas

```
axRaw, ayRaw, azRaw, ax, ay, az, linX, linY, linZ, gxRaw, gyRaw, gzRaw, gx, gy, gz, pitch, roll
```

---

## Comandos Serial

| Comando | Descripcion |
|---------|-------------|
| run | Inicia streaming a 100Hz |
| pause | Pausa streaming |
| console | Modo consola (calibrado, 1Hz display) |
| raw | Modo consola (sin calibrar, 1Hz) |
| linear | Aceleracion sin gravedad + eventos (1Hz display) |
| plot | CSV 20Hz para Serial Plotter (17 columnas) |
| cal | Recalibrar sensor |
| orient | Detectar orientacion del sensor |
| events | Ver config de deteccion de eventos |
| offsets | Exportar offsets como codigo C para otro sketch |
| status | Ver configuracion actual |
| help | Lista de comandos |

---

## Offsets Exportables

El comando `offsets` imprime constantes C listas para copiar/pegar:

```cpp
const float OFFSET_GX = 0.123456;
const float OFFSET_GY = -0.078901;
const float OFFSET_GZ = 0.034567;
const float OFFSET_AX = 0.012345;
const float OFFSET_AY = -0.023456;
const float OFFSET_AZ = 0.001234;
const int SENSOR_ORIENTATION = 0;
const float ALPHA_G = 0.98;
const float ALPHA_A = 0.98;
```

---

## Visualizador 3D (Python - VisPy)

Script Python que visualiza el sensor IMU en 3D en tiempo real via serial. Usa VisPy (OpenGL) + PyQt5.

### Dependencias

```bash
pip install vispy pyqt5 pyserial numpy
```

### Ejecutar

```bash
cd docs/TEST_IMU_ACCEL
python imu_vispy.py
```

### Funcionalidades

| Panel | Descripcion |
|-------|-------------|
| Caja 3D | Caja rotando segun pitch/roll con OpenGL |
| Acelerometro | LONG, LAT, VERT en tiempo real (lineal, sin gravedad) |
| Giroscoop | Gx, Gy, Gz filtrado en tiempo real |
| Buffer | Ventana de 10 segundos, 2000 muestras a 100Hz |

### Orientacion del IMU

| Eje | Direccion | Dimension |
|-----|-----------|-----------|
| X | Frontal del vehiculo | Largo |
| Y | Lateral (izq/der) | Ancho |
| Z | Vertical (arriba) | Alto |

---

*SENTINELDRIVE - Universidad Nacional de Loja*
