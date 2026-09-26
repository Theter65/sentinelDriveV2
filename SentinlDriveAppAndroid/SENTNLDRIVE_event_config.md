# SENTNLDRIVE — Especificaciones técnicas de detección de eventos
> Referencia para configuración del firmware ESP32  
> Fuente: Tesis V2 — Sección 5.3.3.6

---

## 1. Principio general de detección

Cada evento se evalúa dentro de una **ventana temporal mínima** antes de ser confirmado.  
Esto reduce falsas detecciones por ruido de sensores, errores momentáneos del GPS o variaciones transitorias.

```
REGLA GENERAL:
  La variable debe superar (o mantenerse bajo) el umbral
  de forma CONTINUA durante todo el intervalo [t0, t0 + Δt]
  para que el evento sea confirmado y registrado.
```

---

## 2. Eventos implementados

### 2.1 Exceso de velocidad

| Parámetro        | Valor              | Unidad  |
|------------------|--------------------|---------|
| Fuente de dato   | GPS NEO-6M         | —       |
| Variable         | v(t) — velocidad sobre el suelo | km/h |
| Umbral (V_lim)   | **90**             | km/h    |
| Ventana (Δt)     | **5**              | segundos|
| Condición        | v(t) > V_lim durante todo Δt | — |

**Condición lógica:**
```
v(t) > 90 km/h   ∀ t ∈ [t0, t0 + 5s]
```

**Justificación del umbral:**  
Art. 191 del Reglamento General a la LOTTTSV (Ecuador, 2012).  
Límite máximo para transporte público de pasajeros en carretera (rectas): **90 km/h**.

**Tabla de referencia normativa:**
| Tipo de vía         | Límite máximo (buses) |
|---------------------|-----------------------|
| Urbana              | 40 km/h               |
| Perimetral          | 70 km/h               |
| Carretera (rectas)  | **90 km/h** ← umbral  |
| Carretera (curvas)  | 50 km/h               |

**Sugerencia de implementación:**
```cpp
// Pseudocódigo ESP32
#define SPEED_LIMIT_KMH     90.0
#define SPEED_WINDOW_MS     5000   // 5 segundos

float gpsSpeed = getGPSSpeed();    // km/h desde NEO-6M

if (gpsSpeed > SPEED_LIMIT_KMH) {
    speedExcessStart = millis();   // inicio de ventana
} else {
    speedExcessStart = 0;
}

if (speedExcessStart > 0 &&
    (millis() - speedExcessStart) >= SPEED_WINDOW_MS) {
    triggerEvent("EXCESO_VELOCIDAD", gpsSpeed);
    speedExcessStart = 0;
}
```

---

### 2.2 Frenado brusco

| Parámetro        | Valor              | Unidad  |
|------------------|--------------------|---------|
| Fuente de dato   | IMU MPU6050        | —       |
| Variable         | a_x — aceleración longitudinal | m/s² |
| Umbral (a_th)    | **-2.94**          | m/s²    |
| Equivalente en g | **-0.3 g**         | —       |
| Ventana (Δt)     | **0.5 a 1.0**      | segundos|
| Condición        | a_x < -a_th durante todo Δt | — |

**Condición lógica:**
```
a_x < -2.94 m/s²   ∀ t ∈ [t0, t0 + Δt]
     donde Δt ∈ [0.5s, 1.0s]
```

**Justificación del umbral:**  
Federal Transit Administration — FTA (2022), Pierce Transit Project.  
Umbral de 0.3g definido como condición potencialmente peligrosa para pasajeros de pie en buses.  
La mayoría de frenadas normales se mantienen por debajo de 0.3g.

**Sugerencia de implementación:**
```cpp
// Pseudocódigo ESP32
#define BRAKE_THRESHOLD_MS2   -2.94   // -0.3g en m/s²
#define BRAKE_WINDOW_MS        500    // 0.5 segundos (mínimo)

float ax = getMPU6050_AccelX();      // m/s² eje longitudinal

if (ax < BRAKE_THRESHOLD_MS2) {
    if (brakeStart == 0) brakeStart = millis();
} else {
    brakeStart = 0;
}

if (brakeStart > 0 &&
    (millis() - brakeStart) >= BRAKE_WINDOW_MS) {
    triggerEvent("FRENADO_BRUSCO", ax);
    brakeStart = 0;
}
```

> ⚠️ **Nota de orientación del sensor:**  
> El eje X del MPU6050 debe estar alineado con el eje longitudinal del vehículo  
> (dirección de avance). Una desaceleración produce valores negativos en a_x.  
> Verificar signo según montaje físico del dispositivo.

---

### 2.3 Curva agresiva (peligrosa)

| Parámetro        | Valor              | Unidad  |
|------------------|--------------------|---------|
| Fuente de dato   | IMU MPU6050        | —       |
| Variable         | a_y — aceleración lateral | m/s² |
| Umbral (a_lat)   | **2.45**           | m/s²    |
| Equivalente en g | **0.25 g**         | —       |
| Ventana (Δt)     | **0.5**            | segundos|
| Condición        | \|a_y\| > a_lat durante todo Δt | — |

**Condición lógica:**
```
|a_y| > 2.45 m/s²   ∀ t ∈ [t0, t0 + 0.5s]
```

**Justificación del umbral:**  
- Nguyen et al. (2019): nivel "muy incómodo" en buses urbanos de Singapur → 1.75 m/s²  
- García-Ramírez & Aguilar-Cárdenas (2021): estudio en vía Loja–Catamayo →  
  umbrales más altos que estándares AASHTO en carreteras andinas  
- **0.25g (2.45 m/s²)**: valor intermedio, calibrado al contexto de rutas  
  interprovinciales de Loja. Refleja comodidad/estabilidad percibida del pasajero,  
  no riesgo estructural de vuelco.

**Sugerencia de implementación:**
```cpp
// Pseudocódigo ESP32
#define CURVE_THRESHOLD_MS2   2.45   // 0.25g en m/s²
#define CURVE_WINDOW_MS        500   // 0.5 segundos

float ay = getMPU6050_AccelY();     // m/s² eje lateral

if (abs(ay) > CURVE_THRESHOLD_MS2) {
    if (curveStart == 0) curveStart = millis();
} else {
    curveStart = 0;
}

if (curveStart > 0 &&
    (millis() - curveStart) >= CURVE_WINDOW_MS) {
    triggerEvent("CURVA_AGRESIVA", ay);
    curveStart = 0;
}
```

> ⚠️ **Nota de orientación del sensor:**  
> El eje Y del MPU6050 debe estar alineado con el eje lateral del vehículo.  
> Se evalúa el valor absoluto para detectar curvas tanto a la izquierda como a la derecha.

---

## 3. Tabla resumen de eventos

| Evento             | Sensor    | Variable | Umbral       | Ventana Δt | Condición              |
|--------------------|-----------|----------|--------------|------------|------------------------|
| Exceso velocidad   | GPS NEO-6M| v(t)     | > 90 km/h    | 5 s        | Continua en Δt         |
| Frenado brusco     | MPU6050   | a_x      | < -2.94 m/s² | 0.5 – 1 s  | Continua en Δt         |
| Curva agresiva     | MPU6050   | \|a_y\|  | > 2.45 m/s²  | 0.5 s      | Continua en Δt         |

---

## 4. Formato de mensaje MQTT al confirmar evento

```json
{
  "bus_id": "BUS_001",
  "timestamp": "2025-10-15T14:32:10-05:00",
  "type": "event",
  "lat": -3.9985,
  "lon": -79.2047,
  "speed": 94.3,
  "event": "EXCESO_VELOCIDAD",
  "value1": 94.3,
  "value2": 90.0
}
```

| Campo    | Descripción                                      |
|----------|--------------------------------------------------|
| type     | Siempre `"event"` para eventos de riesgo         |
| event    | `EXCESO_VELOCIDAD` / `FRENADO_BRUSCO` / `CURVA_AGRESIVA` |
| value1   | Valor medido en el momento del evento            |
| value2   | Umbral configurado (referencia)                  |

---

## 5. Tópicos MQTT

```
/flota/ecuador/buses/{bus_id}/gps     ← telemetría periódica (cada 3s)
/flota/ecuador/buses/{bus_id}/event   ← eventos de riesgo confirmados
```

---

## 6. Parámetros de adquisición de referencia

| Variable          | Sensor    | Frecuencia    | Unidad  |
|-------------------|-----------|---------------|---------|
| Latitud / Longitud| NEO-6M    | cada 3 s      | °       |
| Velocidad GPS     | NEO-6M    | cada 3 s      | km/h    |
| Aceleración X/Y/Z | MPU6050   | continua      | m/s²    |
| Giroscopio R/P/Y  | MPU6050   | continua      | °/s     |
| HDOP              | NEO-6M    | cada 3 s      | —       |

---

*Generado desde Tesis_V2.docx — SENTNLDRIVE (Gonza & Romero, 2026)*  
*Universidad Nacional de Loja — Carrera de Ingeniería en Telecomunicaciones*
