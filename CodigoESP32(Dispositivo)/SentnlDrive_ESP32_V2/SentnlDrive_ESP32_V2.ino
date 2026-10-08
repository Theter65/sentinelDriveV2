/*
 * ================================================================
 * SENTNLDRIVE — CODIGO PRINCIPAL V2 (FreeRTOS)
 * ================================================================
 * Sistema autonomo de deteccion de eventos via IMU + GPS.
 * Envia telemetria y eventos por MQTT. Si no hay conexion,
 * guarda en SD para envio posterior.
 *
 * Arquitectura FreeRTOS:
 *   Core 0, PRI 3: tareaIMU  — MPU6050 100 Hz + filtro + eventos (TAREA_IMU_STACK)
 *   Core 0, PRI 2: tareaGPS  — parseo NMEA continuo (TAREA_GPS_STACK)
 *   Core 1, PRI 1: tareaComms — WiFi/NTP/MQTT/SD/display/serial (TAREA_COMMS_STACK)
 *
 * Stack: tareaIMU=8192 (uso ~700 extra para buffers JSON durante eventos)
 *
 * Componentes:
 *   - MPU6050 (IMU): acelerometro + giroscopio a 100 Hz
 *   - u-blox NEO-6M / NEO-M8N: coordenadas + velocidad a 1 Hz
 *   - SD Card: cola offline para mensajes MQTT
 *   - SSD1306 (OLED): pantalla 128x32 I2C
 *   - Buzzer: alertas sonoras en eventos (NO bloqueante)
 *
 * Eventos detectados:
 *   - Frenada brusca: linX < -2.94 m/s^2, ventana 0.5s, >=80% de capacidad bajo umbral
 *   - Curva peligrosa: |linY| > 3.92 m/s^2, ventana 3.0s, >=80% bajo umbral y misma direccion
 *   - Exceso velocidad: > 90 km/h sostenido 5.0s
 *   - Cooldown global de 30s desde la deteccion de cualquier evento automatico
 *
 * Pines:
 *   GPS: RX=16, TX=17
 *   SD:  CS=5, SCK=18, MISO=19, MOSI=23
 *   IMU: SDA=21, SCL=22
 *   OLED: SDA=21, SCL=22 (mismo bus I2C, 400 kHz)
 *   Buzzer: GPIO 4
 *
 * Fixes aplicados (Jul 2026):
 *   - Stack tareaIMU 4096->8192 (evita reset por overflow en eventos)
 *   - enviarMsgCola: sin vTaskDelay(50) (bloqueaba IMU 5 ciclos)
 *   - myGpsWarmup: copia local en tareaIMU (consistencia)
 *   - EEPROM_ADDR_CALIB movido a 64 (no solapa GPS)
 *   - GPS init: espera charsProcessed()>10, no SerialGPS.available()
 *   - Timestamp fuera del lambda evaluarVentana
 *   - mostrarBootPaso: "..." en progreso, no "FALLO"
 *   - Curva: ventana unica con doble check 80% (umbral + direccion)
 *   - DMP eliminado, filtro Madgwick (cuaterniones) beta=0.04
 *   - Offsets fisicos hardcodeados (ax=0.102, ay=0.132, az=0.613, gx=-3.951, gy=0.677, gz=0.634)
 * ================================================================
 */

// ─────────────────────────────────────────────────────────────────
//  INCLUDES
// ─────────────────────────────────────────────────────────────────
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include "time.h"
#include <Wire.h>
#include <TinyGPS++.h>
#include <SPI.h>
#include <SD.h>
#include <math.h>
#include <Adafruit_AHRS_Madgwick.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <EEPROM.h>
#include <esp_timer.h>
#include "EventSampleClock.h"

// FreeRTOS
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <freertos/queue.h>
#include <freertos/semphr.h>

// Stack sizes para tareas FreeRTOS (usar constantes evita desincronizacion)
#define TAREA_IMU_STACK   8192
#define TAREA_GPS_STACK   4096
#define TAREA_COMMS_STACK 16384  // TLS necesita ~10KB para handshake MQTT

// ─────────────────────────────────────────────────────────────────
//  PINES
// ─────────────────────────────────────────────────────────────────
#define SD_CS_PIN    5
#define GPS_RX      16
#define GPS_TX      17
#define I2C_SDA     21
#define I2C_SCL     22
#define MPU_ADDR    0x68
#define BUZZER_PIN   4

#define SCREEN_WIDTH  128
#define SCREEN_HEIGHT  32
#define OLED_ADDR    0x3C

// ─────────────────────────────────────────────────────────────────
//  RED / MQTT
// ─────────────────────────────────────────────────────────────────
const char* WIFI_SSID   = "************";
const char* WIFI_PASS   = "***************";
const char* MQTT_BROKER = "***************.hivemq.cloud";
const int   MQTT_PORT   = *************;
const char* MQTT_USER   = "***********";
const char* MQTT_PASS   = "***********";
const char* BASE_TOPIC  = "flota/ecuador/buses";
const int   DEVICE_ID   = 5;

// ─────────────────────────────────────────────────────────────────
//  UMBRALES DE EVENTOS
// ─────────────────────────────────────────────────────────────────
const float BRAKE_THRESHOLD_MS2 = -2.94f;
const float CURVE_THRESHOLD_MS2 =  3.92f;  // 0.4g
const float EVENT_THRESHOLD_PCT = 0.80f;   // 80% (sync Android)

#define FRENO_WINDOW_MS    500     // 0.5s (pruebas) — cambiar libremente
#define CURVA_WINDOW_MS    3000    // 3s
#define MUESTRA_PERIODO_MS 10      // 100Hz
#define FRENO_N  (FRENO_WINDOW_MS / MUESTRA_PERIODO_MS)
#define CURVA_N  (CURVA_WINDOW_MS / MUESTRA_PERIODO_MS)

// Minimo muestras antes de evaluar (% de la ventana, se ajusta solo al cambiar WINDOW_MS)
const int MIN_MUESTRAS_FRENO = (int)(FRENO_N * 0.6f);
const int MIN_MUESTRAS_CURVA = (int)(CURVA_N * 0.9f);

const int   IMU_RATE_HZ         = 100;
const float SPEED_THRESHOLD_KMH = 90.0f;
const unsigned long SPEED_MIN_SUSTAIN_MS = 5000;  // 5s (sync Android)
const int   TELEMETRY_INTERVAL_MS = 10000;
// Se publica tan pronto TinyGPSPlus entrega una ubicacion valida y reciente.
const unsigned long GPS_STALE_MS = 3000;

// ─────────────────────────────────────────────────────────────────
//  FREERTOS: COLA, MUTEX, TAREAS
// ─────────────────────────────────────────────────────────────────
#define MSG_JSON_MAX  350
#define QUEUE_LENGTH  50
#define DISPLAY_QUEUE_LENGTH 20
#define BUZZER_QUEUE_LENGTH 20

enum MsgTipo { MSG_EVENTO = 0, MSG_TELEMETRIA = 1 };

struct MsgPacket {
  int tipo;
  char json[MSG_JSON_MAX];
};

QueueHandle_t       xQueueComms    = NULL;
QueueHandle_t       xQueueDisplay  = NULL;
QueueHandle_t       xQueueBuzzer   = NULL;
SemaphoreHandle_t   xMutexSD       = NULL;
SemaphoreHandle_t   xMutexI2C      = NULL;
SemaphoreHandle_t   xMutexGPSData  = NULL;
SemaphoreHandle_t   xMutexGPSObj   = NULL;
SemaphoreHandle_t   xMutexIMUData  = NULL;

TaskHandle_t xHandleIMU    = NULL;
TaskHandle_t xHandleGPS    = NULL;
TaskHandle_t xHandleComms  = NULL;

#define DISPLAY_JSON_MAX 64
enum DisplayMsgTipo { DISPLAY_IDLE = 0, DISPLAY_EVENTO = 1 };
struct DisplayMsg {
  int tipo;
  char linea1[32];
  float valor;
};

// ─────────────────────────────────────────────────────────────────
//  COLA OFFLINE (SD)
// ─────────────────────────────────────────────────────────────────
#define QUEUE_FILE  "/queue.txt"
#define QHEAD_FILE  "/qhead.txt"
#define QUEUE_MAX   1200
int  queueHead  = 0;
int  queueTotal = 0;
unsigned long queueReadOffset = 0;
bool sdReady    = false;

// ─────────────────────────────────────────────────────────────────
//  OBJETOS GLOBALES
// ─────────────────────────────────────────────────────────────────
TinyGPSPlus        gps;
HardwareSerial     SerialGPS(2);
WiFiClientSecure   espClient;
PubSubClient       mqttClient(espClient);
Adafruit_SSD1306   display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);

bool displayReady = false;
unsigned long lastDisplayRefreshMs = 0;
unsigned long displayEventUntilMs = 0;
bool displayShowingEvent = false;
const unsigned long DISPLAY_REFRESH_MS = 5000;

// EEPROM
#define EEPROM_SIZE       128
#define EEPROM_ADDR_GPS   0
#define EEPROM_MAGIC      0xA5

struct GpsPosition {
  uint8_t magic;
  double lat;
  double lon;
  float alt;
  float speed;
  float course;
  uint16_t year;
  uint8_t month;
  uint8_t day;
  uint8_t hour;
  uint8_t minute;
  uint8_t second;
  uint32_t savedAtMs;
  uint32_t saveCount;
  uint8_t satsAtSave;
  uint8_t hdopX10;
};

GpsPosition savedPos;
bool hadFirstFix = false;

// ─────────────────────────────────────────────────────────────────
//  MPU6050 - Filtro Madgwick (cuaterniones)
// ─────────────────────────────────────────────────────────────────
// Offsets de fabrica por defecto (MPU6050 DMP no soportado)
// Offsets en unidades fisicas (m/s^2 para accel, deg/s para gyro)
// Valores calibrados para este sensor — siempre se usan como base
const float FACTORY_AX_OFF = 0.101762f;
const float FACTORY_AY_OFF = 0.131929f;
const float FACTORY_AZ_OFF = 0.613355f;
const float FACTORY_GX_OFF = -3.950943f;
const float FACTORY_GY_OFF = 0.676909f;
const float FACTORY_GZ_OFF = 0.634480f;

// Offsets activos (pueden sobrescribirse via calibracion en EEPROM)
float ax_offset = FACTORY_AX_OFF;
float ay_offset = FACTORY_AY_OFF;
float az_offset = FACTORY_AZ_OFF;
float gx_offset = FACTORY_GX_OFF;
float gy_offset = FACTORY_GY_OFF;
float gz_offset = FACTORY_GZ_OFF;
bool calibFuente = false; // true = EEPROM, false = fabrica

// Orientacion del sensor (X adelante)
const uint8_t SENSOR_ORIENTATION = 0;

// Filtro Madgwick
Adafruit_Madgwick madgwickFilter;
float madg_q0, madg_q1, madg_q2, madg_q3;
bool madgInitOK = false;
uint64_t lastMadgwickSampleUs = 0;
bool madgSampleReady = false;

// EEPROM
#define EEPROM_ADDR_CALIB  64  // despues de GpsPosition (~46 bytes)
#define CALIB_MAGIC 0x4D50
struct CalibData {
  uint16_t magic;
  float ax_off, ay_off, az_off;
  float gx_off, gy_off, gz_off;
};

// ─────────────────────────────────────────────────────────────────
//  ESTADO DEL SISTEMA
// ─────────────────────────────────────────────────────────────────
bool wifiReady   = false;
bool ntpReady    = false;
bool imuReady    = false;
volatile bool gpsReady = false;
bool mqttReady   = false;
bool coordsReady = false;

unsigned long bootMs = 0;
unsigned long lastTelemetry = 0;
unsigned long lastNtpSync = 0;
unsigned long mqttBackoffMs = 2000;
unsigned long lastMqttAttempt = 0;

const long GMT_OFFSET_SEC = -18000;
const char* NTP1 = "pool.ntp.org";
const char* NTP2 = "time.google.com";
const char* NTP3 = "time.cloudflare.com";

// ─────────────────────────────────────────────────────────────────
//  IMU - ESTADO COMPARTIDO (protegido por xMutexIMUData)
// ─────────────────────────────────────────────────────────────────
// Estas variables son escritas por tareaIMU y leidas por tareaComms.
// Se protegen con xMutexIMUData para lectura atomica.
float accelX_ms2 = 0, accelY_ms2 = 0, accelZ_ms2 = 0;
float pitchDeg = 0, rollDeg = 0;
float linX_ms2 = 0, linY_ms2 = 0, linZ_ms2 = 0;
float gyroX_dps = 0, gyroY_dps = 0, gyroZ_dps = 0;
const float GYRO_SENS_LSB  = 131.0f;
const float ACCEL_SENS_LSB = 16384.0f;
volatile unsigned long imuReadCount = 0;
int imuFallos = 0;

// GPS data copiada atomicamente para uso en eventos
volatile float gpsLat = 0, gpsLon = 0, gpsSpeed = 0;
volatile bool  gpsLocationValid = false;
volatile bool  gpsWarmupComplete = false;
bool gpsImmediateTelemetry = false;  // protegida por xMutexGPSData
uint8_t gpsSatelliteCount = 0;
float gpsHdopValue = 99.9f;
bool gpsHdopValid = false;
bool gpsNmeaSeen = false;

// ─────────────────────────────────────────────────────────────────
//  DETECCION DE EVENTOS
// ─────────────────────────────────────────────────────────────────
// ─────────────────────────────────────────────────────────────────
//  VENTANA DESLIZANTE (eventos IMU)
// ─────────────────────────────────────────────────────────────────
// ─────────────────────────────────────────────────────────────────
//  VENTANA DESLIZANTE (eventos IMU) — template por tamaño
// ─────────────────────────────────────────────────────────────────

template<int N>
struct VentanaDeslizante {
  float buf[N];
  bool  sobreBuf[N];
  int8_t signoSobreBuf[N];
  int   idx = 0;
  int   count = 0;
  int   sobreCount = 0;
  int   sobrePosCount = 0;
  int   sobreNegCount = 0;
  float suma = 0.0f;
  bool  estadoAnterior = false;
};

VentanaDeslizante<FRENO_N> vFreno;   // 50 muestras  = 0.5s
VentanaDeslizante<CURVA_N> vCurva;   // 300 muestras = 3s

unsigned long speedSobreDesdeMs = 0;
bool speedSustainActive = false;
EventSampleClock eventSampleClock;
// Cooldown compartido: evita que una misma maniobra dispare eventos de
// distintos tipos (por ejemplo frenado y curva) casi simultáneamente.
unsigned long lastAnyEventMs = 0;
bool hasAnyEvent = false;
const unsigned long EVENT_COOLDOWN_MS = 30000;

bool enviarMsgCola(int tipo, const char* json);
void enviarDisplayEvento(const DisplayMsg* msg);
void beepEvento(int repeticiones);
void getTimestamp(char* buf, size_t bufLen);

template<int N>
void empujarMuestra(VentanaDeslizante<N>& v, float valor, bool sobre) {
  int8_t signoSobre = sobre ? ((valor >= 0) ? 1 : -1) : 0;
  if (v.count == N) {
    v.suma -= v.buf[v.idx];
    if (v.sobreBuf[v.idx]) v.sobreCount--;
    if (v.signoSobreBuf[v.idx] > 0) v.sobrePosCount--;
    else if (v.signoSobreBuf[v.idx] < 0) v.sobreNegCount--;
  } else {
    v.count++;
  }
  v.buf[v.idx]      = valor;
  v.sobreBuf[v.idx] = sobre;
  v.signoSobreBuf[v.idx] = signoSobre;
  v.suma += valor;
  if (sobre) {
    v.sobreCount++;
    if (signoSobre > 0) v.sobrePosCount++;
    else v.sobreNegCount++;
  }
  v.idx = (v.idx + 1) % N;
}

template<int N>
float promedioMuestrasSobreUmbral(const VentanaDeslizante<N>& v, int8_t direccion = 0) {
  // El 80 % decide la activacion; el valor promedia TODAS las muestras que
  // superaron el umbral en la direccion del evento. Solo se calcula al disparar.
  double sumaCalificadas = 0.0;
  int cantidadCalificadas = 0;
  for (int i = 0; i < v.count; ++i) {
    if (v.sobreBuf[i] && (direccion == 0 || v.signoSobreBuf[i] == direccion)) {
      sumaCalificadas += v.buf[i];
      ++cantidadCalificadas;
    }
  }
  return cantidadCalificadas > 0 ? sumaCalificadas / cantidadCalificadas : 0.0f;
}

template<int N>
void evaluarVentanaDeslizante(VentanaDeslizante<N>& v, int minMuestras, const char* tipo, const char* etiqueta,
                               int beeps, bool checkDir,
                               unsigned long nowMs, bool myGpsWarmup, bool myGpsValid,
                               float myLat, float myLon) {
  // Evalúa porcentajes contra la ventana configurada, no contra el arranque
  // parcial del buffer. Así 80% significa 80% de los N puntos de la ventana.
  const int muestrasUmbral = (int)ceilf(EVENT_THRESHOLD_PCT * N);
  bool pasaAbs = v.count >= minMuestras && v.sobreCount >= muestrasUmbral;
  bool pasaDir = true;
  if (checkDir) {
    // Dirección se calcula solo entre muestras que también superaron umbral.
    int maxDirSobreUmbral = max(v.sobrePosCount, v.sobreNegCount);
    pasaDir = maxDirSobreUmbral >= muestrasUmbral;
  }
  bool activaAhora = pasaAbs && pasaDir;
  const bool cooldownCumplido = !hasAnyEvent ||
      nowMs - lastAnyEventMs >= EVENT_COOLDOWN_MS;
  if (activaAhora && !v.estadoAnterior && cooldownCumplido) {
    // El periodo empieza al detectar el evento, no depende de GPS ni de que
    // MQTT tenga espacio en la cola. Así tampoco repite alertas locales.
    lastAnyEventMs = nowMs;
    hasAnyEvent = true;
    const int8_t direccion = checkDir ? (v.sobrePosCount >= muestrasUmbral ? 1 : -1) : 0;
    float avg = promedioMuestrasSobreUmbral(v, direccion);
    if (myGpsWarmup && myGpsValid) {
      char evtBuf[MSG_JSON_MAX];
      char tsEvt[30];
      getTimestamp(tsEvt, sizeof(tsEvt));
      int n = snprintf(evtBuf, sizeof(evtBuf),
        "{\"bus_id\":%d,\"type\":\"event\",\"event\":\"%s\","
        "\"lat\":%.7f,\"lon\":%.7f,\"value\":%.2f,\"timestamp\":\"%s\"}",
        DEVICE_ID, tipo, (double)myLat, (double)myLon, avg, tsEvt);
      if (n < 0 || n >= (int)sizeof(evtBuf)) {
        Serial.println("[WARN] evtBuf truncado; evento no encolado");
      } else if (!enviarMsgCola(MSG_EVENTO, evtBuf)) {
        Serial.printf("[EVENTO] %s detectado; cola de mensajes llena\n", tipo);
      } else {
        Serial.printf("[EVENTO] %s avg=%.2f encolado\n", tipo, avg);
      }
    } else {
      Serial.printf("[EVENTO] %s detectado pero falta ubicacion GPS reciente (ready=%d valid=%d)\n",
                    tipo, myGpsWarmup, myGpsValid);
    }
    DisplayMsg dmsg;
    dmsg.tipo = DISPLAY_EVENTO;
    strncpy(dmsg.linea1, etiqueta, 31);
    dmsg.linea1[31] = '\0';
    dmsg.valor = avg;
    enviarDisplayEvento(&dmsg);
    beepEvento(beeps);
  } else if (activaAhora && !v.estadoAnterior && !cooldownCumplido) {
    Serial.printf("[EVENTO] %s bloqueado por cooldown (%lu ms restantes)\n",
                  tipo, (unsigned long)(EVENT_COOLDOWN_MS - (nowMs - lastAnyEventMs)));
  }
  v.estadoAnterior = activaAhora;
}

void enviarDisplayEvento(const DisplayMsg* msg) {
  if (!xQueueDisplay || !msg) return;
  if (xQueueSend(xQueueDisplay, msg, 0) == pdTRUE) return;

  // Mantener la alerta más reciente si se acumularon más eventos que el buffer.
  DisplayMsg descartado;
  xQueueReceive(xQueueDisplay, &descartado, 0);
  if (xQueueSend(xQueueDisplay, msg, 0) != pdTRUE) {
    Serial.println("[DISPLAY] No se pudo encolar el evento");
  }
}

// Buzzer NO bloqueante: las solicitudes se reproducen en orden desde tareaComms.
uint8_t beepsPendientes = 0;
bool buzzerOn = false;
unsigned long buzzerNextMs = 0;

// Consola 1 Hz (en tareaComms)
unsigned long lastConsolePrint = 0;

// ─────────────────────────────────────────────────────────────────
//  FUNCIONES AUXILIARES (compartidas, sin estado critico)
// ─────────────────────────────────────────────────────────────────

bool verificarMPU() {
  xSemaphoreTake(xMutexI2C, portMAX_DELAY);
  Wire.beginTransmission(MPU_ADDR);
  bool ok = Wire.endTransmission() == 0;
  xSemaphoreGive(xMutexI2C);
  return ok;
}

bool leerMPURaw(float& ax, float& ay, float& az, float& gx, float& gy, float& gz) {
  if (xSemaphoreTake(xMutexI2C, pdMS_TO_TICKS(2)) != pdTRUE) return false;
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x3B);
  if (Wire.endTransmission(false) != 0) { xSemaphoreGive(xMutexI2C); return false; }
  Wire.requestFrom(MPU_ADDR, 14, true);
  if (Wire.available() < 14) { xSemaphoreGive(xMutexI2C); return false; }
  int16_t rawAx = Wire.read() << 8 | Wire.read();
  int16_t rawAy = Wire.read() << 8 | Wire.read();
  int16_t rawAz = Wire.read() << 8 | Wire.read();
  int16_t rawT  = Wire.read() << 8 | Wire.read();
  int16_t rawGx = Wire.read() << 8 | Wire.read();
  int16_t rawGy = Wire.read() << 8 | Wire.read();
  int16_t rawGz = Wire.read() << 8 | Wire.read();
  xSemaphoreGive(xMutexI2C);
  ax = rawAx / ACCEL_SENS_LSB * 9.81f - ax_offset;
  ay = rawAy / ACCEL_SENS_LSB * 9.81f - ay_offset;
  az = rawAz / ACCEL_SENS_LSB * 9.81f - az_offset;
  gx = rawGx / GYRO_SENS_LSB - gx_offset;
  gy = rawGy / GYRO_SENS_LSB - gy_offset;
  gz = rawGz / GYRO_SENS_LSB - gz_offset;
  return true;
}

void aplicarOrientacion(float& ax, float& ay, float& az, float& gx, float& gy, float& gz) {
  if (SENSOR_ORIENTATION == 0) return;
}

bool despertarMPU() {
  if (xSemaphoreTake(xMutexI2C, pdMS_TO_TICKS(10)) != pdTRUE) return false;
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x6B);
  Wire.write(0x00);
  bool ok = Wire.endTransmission(true) == 0;
  if (ok) {
    Wire.beginTransmission(MPU_ADDR);
    Wire.write(0x1C);
    Wire.write(0x00);
    Wire.endTransmission(true);
    Wire.beginTransmission(MPU_ADDR);
    Wire.write(0x1B);
    Wire.write(0x00);
    Wire.endTransmission(true);
    Wire.beginTransmission(MPU_ADDR);
    Wire.write(0x1A);
    Wire.write(0x04);
    Wire.endTransmission(true);
  }
  xSemaphoreGive(xMutexI2C);
  return ok;
}

void actualizarFiltroMadgwick(float ax, float ay, float az, float gx, float gy, float gz) {
  if (!madgInitOK) return;
  const uint64_t nowUs = (uint64_t)esp_timer_get_time();
  float dt = !madgSampleReady ? 0.01f : (nowUs - lastMadgwickSampleUs) / 1000000.0f;
  madgSampleReady = true;
  lastMadgwickSampleUs = nowUs;
  dt = fminf(0.05f, fmaxf(0.0001f, dt));
  madgwickFilter.updateIMU(gx, gy, gz, ax, ay, az, dt);
  madgwickFilter.getQuaternion(&madg_q0, &madg_q1, &madg_q2, &madg_q3);
  float grav_x = 9.81f * 2.0f * (madg_q1 * madg_q3 - madg_q0 * madg_q2);
  float grav_y = 9.81f * 2.0f * (madg_q0 * madg_q1 + madg_q2 * madg_q3);
  float grav_z = 9.81f * (madg_q0 * madg_q0 - madg_q1 * madg_q1 - madg_q2 * madg_q2 + madg_q3 * madg_q3);
  // Ejes del vehiculo: X adelante, Y izquierda, Z arriba. Bajar el frente
  // debe dar pitch positivo con la convencion solicitada.
  float pitch = -asinf(fmaxf(-1.0f, fminf(1.0f, 2.0f * (madg_q1 * madg_q3 - madg_q0 * madg_q2)))) * 180.0f / (float)M_PI;
  float roll  = atan2f(2.0f * (madg_q0 * madg_q1 + madg_q2 * madg_q3),
                       madg_q0 * madg_q0 - madg_q1 * madg_q1 - madg_q2 * madg_q2 + madg_q3 * madg_q3) * 180.0f / (float)M_PI;
  xSemaphoreTake(xMutexIMUData, portMAX_DELAY);
  pitchDeg = pitch;
  rollDeg  = roll;
  linX_ms2 = ax - grav_x;
  linY_ms2 = ay - grav_y;
  linZ_ms2 = az - grav_z;
  accelX_ms2 = ax; accelY_ms2 = ay; accelZ_ms2 = az;
  gyroX_dps  = gx; gyroY_dps  = gy; gyroZ_dps  = gz;
  xSemaphoreGive(xMutexIMUData);
}

bool leerMPU() {
  float ax, ay, az, gx, gy, gz;
  if (!leerMPURaw(ax, ay, az, gx, gy, gz)) return false;
  aplicarOrientacion(ax, ay, az, gx, gy, gz);
  actualizarFiltroMadgwick(ax, ay, az, gx, gy, gz);
  return true;
}

void loadCalib() {
  CalibData cd;
  EEPROM.get(EEPROM_ADDR_CALIB, cd);
  if (cd.magic == CALIB_MAGIC) {
    ax_offset = cd.ax_off; ay_offset = cd.ay_off; az_offset = cd.az_off;
    gx_offset = cd.gx_off; gy_offset = cd.gy_off; gz_offset = cd.gz_off;
    calibFuente = true;
    Serial.println("[CALIB] Cargados de EEPROM");
  } else {
    ax_offset = FACTORY_AX_OFF; ay_offset = FACTORY_AY_OFF; az_offset = FACTORY_AZ_OFF;
    gx_offset = FACTORY_GX_OFF; gy_offset = FACTORY_GY_OFF; gz_offset = FACTORY_GZ_OFF;
    calibFuente = false;
    Serial.println("[CALIB] Usando offsets de fabrica");
  }
}

void saveCalib() {
  CalibData cd;
  cd.magic = CALIB_MAGIC;
  cd.ax_off = ax_offset; cd.ay_off = ay_offset; cd.az_off = az_offset;
  cd.gx_off = gx_offset; cd.gy_off = gy_offset; cd.gz_off = gz_offset;
  EEPROM.put(EEPROM_ADDR_CALIB, cd);
  EEPROM.commit();
  Serial.println("[CALIB] Guardado en EEPROM");
}

void calibrarIMUYGuardar() {
  Serial.println("\n[CALIB] Iniciando calibracion (mantener quieto)...");
  float sumGx = 0, sumGy = 0, sumGz = 0;
  float sumAx = 0, sumAy = 0, sumAz = 0;
  int muestras = 0;
  for (int i = 0; i < 200; i++) {
    float ax, ay, az, gx, gy, gz;
    if (leerMPURaw(ax, ay, az, gx, gy, gz)) {
      sumAx += ax; sumAy += ay; sumAz += az;
      sumGx += gx; sumGy += gy; sumGz += gz;
      muestras++;
    }
    delay(5);
  }
  if (muestras == 0) { Serial.println("[CALIB] Error: no se pudo leer IMU"); return; }
  float avgAx = sumAx / muestras, avgAy = sumAy / muestras, avgAz = sumAz / muestras;
  float avgGx = sumGx / muestras, avgGy = sumGy / muestras, avgGz = sumGz / muestras;
  // Acumular residuos sobre los offsets actuales
  ax_offset += avgAx;
  ay_offset += avgAy;
  az_offset += (avgAz - 9.81f);
  gx_offset += avgGx;
  gy_offset += avgGy;
  gz_offset += avgGz;
  saveCalib();
  Serial.println("[CALIB] Calibracion completada");
  Serial.printf("  Accel offsets: %.6f %.6f %.6f\n", ax_offset, ay_offset, az_offset);
  Serial.printf("  Gyro  offsets: %.6f %.6f %.6f\n", gx_offset, gy_offset, gz_offset);
}

bool gpsFixDisponible() {
  return gps.location.isValid() && gps.location.age() <= GPS_STALE_MS;
}

void sendWarmStart() {
  if (savedPos.magic != EEPROM_MAGIC) {
    Serial.println("[GPS] Sin posicion guardada, cold start...");
    SerialGPS.println("$PMTK104*37");  // Comando que ya usaba la version previa
    return;
  }
  SerialGPS.println("$PMTK102*31");
  SerialGPS.println("$PMTK220,1000*1F");  // 1 Hz
  Serial.printf("[GPS] Warm start: %.7f, %.7f\n", savedPos.lat, savedPos.lon);
}

void beepEvento(int repeticiones) {
  if (!xQueueBuzzer || repeticiones <= 0) return;
  uint8_t solicitud = (uint8_t)min(repeticiones, 10);
  if (xQueueSend(xQueueBuzzer, &solicitud, 0) != pdTRUE) {
    Serial.println("[BUZZER] Cola llena; aviso sonoro descartado");
  }
}

void tickBuzzer(unsigned long nowMs) {
  if (beepsPendientes == 0 && xQueueBuzzer) {
    uint8_t solicitud = 0;
    if (xQueueReceive(xQueueBuzzer, &solicitud, 0) == pdTRUE) {
      beepsPendientes = solicitud * 2;
      buzzerNextMs = nowMs;
    }
  }
  if (beepsPendientes == 0) return;
  if ((long)(nowMs - buzzerNextMs) < 0) return;
  buzzerOn = !buzzerOn;
  digitalWrite(BUZZER_PIN, buzzerOn ? HIGH : LOW);
  beepsPendientes--;
  buzzerNextMs = nowMs + 100;
  if (beepsPendientes == 0) {
    digitalWrite(BUZZER_PIN, LOW);
    buzzerOn = false;
  }
}

// ─────────────────────────────────────────────────────────────────
//  COLA OFFLINE (SD) — protegidas por xMutexSD
// ─────────────────────────────────────────────────────────────────

// ─────────────────────────────────────────────────────────────────
//  CRASH LOG — registrar razón de reinicio en SD
// ─────────────────────────────────────────────────────────────────
#define CRASH_LOG_FILE "/crash.log"

const char* resetReasonStr(esp_reset_reason_t reason) {
  switch (reason) {
    case ESP_RST_POWERON:   return "POWER_ON";
    case ESP_RST_EXT:       return "EXTERNAL_PIN";
    case ESP_RST_SW:        return "SOFTWARE";
    case ESP_RST_PANIC:     return "PANIC";
    case ESP_RST_INT_WDT:   return "INT_WATCHDOG";
    case ESP_RST_TASK_WDT:  return "TASK_WATCHDOG";
    case ESP_RST_WDT:       return "OTHER_WATCHDOG";
    case ESP_RST_BROWNOUT:  return "BROWNOUT";
    case ESP_RST_SDIO:      return "SDIO";
    case ESP_RST_UNKNOWN:
    default:                return "UNKNOWN";
  }
}

void logCrashReason() {
  esp_reset_reason_t reason = esp_reset_reason();
  if (reason == ESP_RST_POWERON) return;  // primer encendido, no loguear

  if (!sdReady) return;
  File f = SD.open(CRASH_LOG_FILE, FILE_APPEND);
  if (!f) return;

  struct tm t;
  char ts[20] = "??";
  if (getLocalTime(&t, 10)) {
    strftime(ts, sizeof(ts), "%Y-%m-%d %H:%M:%S", &t);
  }

  f.printf("[%s] REINICIO: %s (code=%d) uptime_prev=%lu ms\n",
           ts, resetReasonStr(reason), reason, bootMs);
  f.close();
  Serial.printf("[CRASH] %s registrado en SD\n", resetReasonStr(reason));
}

void initQueue() {
  if (!sdReady) return;
  File f = SD.open(QHEAD_FILE, FILE_READ);
  if (f) {
    char s[16];
    int len = f.readBytesUntil('\n', s, sizeof(s) - 1);
    s[len] = '\0';
    queueHead = atoi(s);
    f.close();
  } else {
    queueHead = 0;
  }
  queueTotal = 0;
  queueReadOffset = 0;
  File q = SD.open(QUEUE_FILE, FILE_READ);
  if (q) {
    unsigned long off = 0;
    int linesRead = 0;
    while (linesRead < queueHead && q.available()) {
      if (q.read() == '\n') { linesRead++; off = q.position(); }
    }
    queueReadOffset = off;
    int restantes = 0;
    while (q.available()) { if (q.read() == '\n') restantes++; }
    queueTotal = queueHead + restantes;
    q.close();
  }
  Serial.printf("[QUEUE] Head=%d Total=%d Pendientes=%d Offset=%lu\n",
                queueHead, queueTotal, max(0, queueTotal - queueHead), queueReadOffset);
}

void guardarCabeza() {
  if (!sdReady) return;
  SD.remove(QHEAD_FILE);
  File f = SD.open(QHEAD_FILE, FILE_WRITE);
  if (f) { f.print(queueHead); f.close(); }
}

void encolarPaquete(const char* json) {
  if (!sdReady || !json) return;
  xSemaphoreTake(xMutexSD, portMAX_DELAY);
  if ((queueTotal - queueHead) >= QUEUE_MAX) {
    // Avanzar el offset de lectura antes de incrementar queueHead
    File f = SD.open(QUEUE_FILE, FILE_READ);
    if (f) {
      f.seek(queueReadOffset);
      char dummy[MSG_JSON_MAX];
      f.readBytesUntil('\n', dummy, sizeof(dummy));
      queueReadOffset = f.position();
      f.close();
    }
    queueHead++;
    guardarCabeza();
  }
  File f = SD.open(QUEUE_FILE, FILE_APPEND);
  if (f) {
    f.println(json);
    f.close();
    queueTotal++;
  }
  xSemaphoreGive(xMutexSD);
}

int pendientesEnCola() {
  xSemaphoreTake(xMutexSD, portMAX_DELAY);
  int p = max(0, queueTotal - queueHead);
  xSemaphoreGive(xMutexSD);
  return p;
}

bool drenarUno() {
  xSemaphoreTake(xMutexSD, portMAX_DELAY);
  if (max(0, queueTotal - queueHead) == 0) { xSemaphoreGive(xMutexSD); return false; }
  if (!mqttClient.connected()) { xSemaphoreGive(xMutexSD); return false; }

  File f = SD.open(QUEUE_FILE, FILE_READ);
  if (!f) { xSemaphoreGive(xMutexSD); return false; }

  f.seek(queueReadOffset);
  char paquete[MSG_JSON_MAX + 100];
  int len = f.readBytesUntil('\n', paquete, sizeof(paquete) - 1);
  paquete[len] = '\0';
  unsigned long nextReadOffset = f.position();
  f.close();

  if (len <= 0) {
    Serial.printf("[QUEUE] Linea vacia/corrupta en pos %d, saltando\n", queueHead);
    queueHead++;
    queueReadOffset = nextReadOffset;
    guardarCabeza();
    xSemaphoreGive(xMutexSD);
    return true;
  }

  // Trim whitespace
  char* start = paquete;
  while (*start == ' ' || *start == '\t') start++;
  char* end = paquete + len - 1;
  while (end > start && (*end == ' ' || *end == '\t' || *end == '\r' || *end == '\n')) end--;
  *(end + 1) = '\0';

  if (strlen(start) < 10) {
    Serial.printf("[QUEUE] Linea corrupta en pos %d, saltando\n", queueHead);
    queueHead++;
    queueReadOffset = nextReadOffset;
    guardarCabeza();
    xSemaphoreGive(xMutexSD);
    return true;
  }

  // Liberar mutex ANTES de publish
  xSemaphoreGive(xMutexSD);

  char topic[80];
  if (strstr(start, "\"type\":\"event\"") != NULL) {
    snprintf(topic, sizeof(topic), "%s/%d/event", BASE_TOPIC, DEVICE_ID);
  } else {
    snprintf(topic, sizeof(topic), "%s/%d/gps", BASE_TOPIC, DEVICE_ID);
  }

  bool ok = mqttClient.publish(topic, start);
  if (ok) {
    xSemaphoreTake(xMutexSD, portMAX_DELAY);
    queueHead++;
    queueReadOffset = nextReadOffset;
    guardarCabeza();
    xSemaphoreGive(xMutexSD);
    return true;
  }
  return false;
}

void limpiarColaSiVacia() {
  if (!sdReady) return;
  xSemaphoreTake(xMutexSD, portMAX_DELAY);
  if (max(0, queueTotal - queueHead) == 0 && queueTotal > 0) {
    SD.remove(QUEUE_FILE);
    SD.remove(QHEAD_FILE);
    queueHead = 0;
    queueTotal = 0;
    queueReadOffset = 0;
    Serial.println("[QUEUE] Cola limpiada.");
  }
  xSemaphoreGive(xMutexSD);
}

// ─────────────────────────────────────────────────────────────────
//  EEPROM FUNCIONES
// ─────────────────────────────────────────────────────────────────

void loadSavedPosition() {
  EEPROM.get(EEPROM_ADDR_GPS, savedPos);
  if (savedPos.magic == EEPROM_MAGIC) {
    Serial.println("[EEPROM] Posicion guardada encontrada:");
    Serial.printf("  Lat: %.7f, Lon: %.7f\n", savedPos.lat, savedPos.lon);
    Serial.printf("  Guardada %lu veces | sats=%d hdop=%.1f\n",
                  (unsigned long)savedPos.saveCount,
                  savedPos.satsAtSave, savedPos.hdopX10 / 10.0f);
  } else {
    Serial.println("[EEPROM] Sin posicion guardada");
  }
}

void savePositionToEEPROM() {
  if (!gps.location.isValid() || !gps.date.isValid() || !gps.time.isValid()) {
    Serial.println("[EEPROM] No hay fix valido para guardar");
    return;
  }
  savedPos.magic = EEPROM_MAGIC;
  savedPos.lat = gps.location.lat();
  savedPos.lon = gps.location.lng();
  savedPos.alt = gps.altitude.isValid() ? gps.altitude.meters() : 0.0f;
  savedPos.speed = gps.speed.isValid() ? gps.speed.kmph() : 0.0f;
  savedPos.course = gps.course.isValid() ? gps.course.deg() : 0.0f;
  savedPos.year = gps.date.year();
  savedPos.month = gps.date.month();
  savedPos.day = gps.date.day();
  savedPos.hour = gps.time.hour();
  savedPos.minute = gps.time.minute();
  savedPos.second = gps.time.second();
  savedPos.savedAtMs = millis();
  savedPos.saveCount++;
  savedPos.satsAtSave = gps.satellites.isValid() ? gps.satellites.value() : 0;
  savedPos.hdopX10 = gps.hdop.isValid() ? (uint8_t)(gps.hdop.hdop() * 10) : 255;
  EEPROM.put(EEPROM_ADDR_GPS, savedPos);
  EEPROM.commit();
  Serial.println("[EEPROM] Posicion guardada para warm start:");
  Serial.printf("  Lat: %.7f, Lon: %.7f\n", savedPos.lat, savedPos.lon);
  Serial.printf("  Guardada %lu veces\n", (unsigned long)savedPos.saveCount);
}



// ─────────────────────────────────────────────────────────────────
//  DISPLAY OLED (solo en tareaComms, protegido por xMutexI2C)
// ─────────────────────────────────────────────────────────────────

void initDisplay() {
  if (!display.begin(SSD1306_SWITCHCAPVCC, OLED_ADDR)) {
    Serial.println("[DISPLAY] FALLO");
    return;
  }
  displayReady = true;
  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);
  display.setTextSize(1);
  display.setCursor(0, 0);
  display.println("SENTNLDRIVE");
  display.println("Iniciando...");
  display.display();
  Serial.println("[DISPLAY] OK");
}

void mostrarBootPaso(int paso, const char* texto, bool ok) {
  if (!ok) {
    Serial.printf("[BOOT] Paso %d: %s - ...\n", paso, texto);
    if (!displayReady) return;
    if (xSemaphoreTake(xMutexI2C, pdMS_TO_TICKS(5)) != pdTRUE) return;
    display.clearDisplay();
    display.setCursor(0, 0);
    display.print("P"); display.print(paso); display.print(": ");
    display.println(texto);
    display.println("...");
    display.display();
    xSemaphoreGive(xMutexI2C);
    return;
  }
  Serial.printf("[BOOT] Paso %d: %s - OK\n", paso, texto);
  if (!displayReady) return;
  if (xSemaphoreTake(xMutexI2C, pdMS_TO_TICKS(5)) != pdTRUE) return;
  display.clearDisplay();
  display.setCursor(0, 0);
  display.print("P"); display.print(paso); display.print(": ");
  display.println(texto);
  display.println("OK");
  display.display();
  xSemaphoreGive(xMutexI2C);
}

void mostrarBootMsg(int paso, const char* linea1, const char* linea2) {
  Serial.printf("[BOOT] Paso %d: %s - %s\n", paso, linea1, linea2);
  if (!displayReady) return;
  if (xSemaphoreTake(xMutexI2C, pdMS_TO_TICKS(5)) != pdTRUE) return;
  display.clearDisplay();
  display.setCursor(0, 0);
  display.println(linea1);
  display.println(linea2);
  display.display();
  xSemaphoreGive(xMutexI2C);
}

bool mostrarEventos(const char* evento, float valor) {
  if (!displayReady) {
    Serial.printf("[EVENTO DISPLAY] %s: %.2f (OLED no disponible)\n", evento, valor);
    return true;
  }
  // Si el bus está ocupado, conservar el mensaje al frente de la cola y reintentar.
  if (xSemaphoreTake(xMutexI2C, pdMS_TO_TICKS(10)) != pdTRUE) return false;
  display.clearDisplay();
  display.setCursor(0, 0);
  display.println(evento);
  display.print(valor, 2);
  display.display();
  xSemaphoreGive(xMutexI2C);
  lastDisplayRefreshMs = millis();
  displayEventUntilMs = lastDisplayRefreshMs + DISPLAY_REFRESH_MS;
  displayShowingEvent = true;
  Serial.printf("[EVENTO DISPLAY] %s: %.2f\n", evento, valor);
  return true;
}

void mostrarIdle() {
  if (!displayReady) return;
  unsigned long now = millis();
  if (now - lastDisplayRefreshMs < DISPLAY_REFRESH_MS) return;
  float mySpd = 0, myLat = 0, myLon = 0;
  bool myValid = false;
  uint8_t mySats = 0;
  float myHdop = 99.9f;
  bool myHdopValid = false;
  bool myNmeaSeen = false;
  xSemaphoreTake(xMutexGPSData, portMAX_DELAY);
  mySpd = gpsSpeed; myLat = gpsLat; myLon = gpsLon; myValid = gpsLocationValid;
  mySats = gpsSatelliteCount; myHdop = gpsHdopValue;
  myHdopValid = gpsHdopValid; myNmeaSeen = gpsNmeaSeen;
  xSemaphoreGive(xMutexGPSData);
  if (xSemaphoreTake(xMutexI2C, pdMS_TO_TICKS(2)) != pdTRUE) return;
  display.clearDisplay();
  display.setCursor(0, 0);
  display.print("SENTNLDRIVE");
  display.setCursor(0, 10);
  if (myValid) {
    display.printf("Spd:%.0f km/h", (double)mySpd);
  } else if (!myNmeaSeen) {
    display.print("GPS sin datos NMEA");
  } else if (myHdopValid) {
    display.printf("GPS:%u sat HDOP:%.1f", (unsigned)mySats, (double)myHdop);
  } else {
    display.printf("GPS:%u sat HDOP:--", (unsigned)mySats);
  }
  display.setCursor(0, 20);
  if (myValid) {
    display.printf("%.4f,%.4f", (double)myLat, (double)myLon);
  } else {
    display.print("Esperando fix GPS");
  }
  display.display();
  xSemaphoreGive(xMutexI2C);
  lastDisplayRefreshMs = now;
}

void procesarDisplay() {
  unsigned long now = millis();
  if (displayShowingEvent && (long)(now - displayEventUntilMs) < 0) return;

  DisplayMsg dmsg;
  if (xQueueDisplay && xQueuePeek(xQueueDisplay, &dmsg, 0) == pdTRUE) {
    if (dmsg.tipo == DISPLAY_EVENTO) {
      // No retirar el aviso hasta haberlo dibujado; así un fallo transitorio de I2C
      // no hace que se pierda justo el evento que se quiere mostrar.
      if (!mostrarEventos(dmsg.linea1, dmsg.valor)) return;
    }
    xQueueReceive(xQueueDisplay, &dmsg, 0);
    return;
  }

  displayShowingEvent = false;
  mostrarIdle();
}

// ─────────────────────────────────────────────────────────────────
//  WIFI / NTP / MQTT (en tareaComms)
// ─────────────────────────────────────────────────────────────────

enum WifiState { WIFI_IDLE, WIFI_CONNECTING, WIFI_WAIT_RECONNECT };
WifiState wifiState = WIFI_IDLE;
unsigned long wifiConnectStart = 0;

bool connectWiFiNonBlocking() {
  switch (wifiState) {
    case WIFI_IDLE:
      Serial.print("[WiFi] Conectando a "); Serial.println(WIFI_SSID);
      WiFi.mode(WIFI_OFF);
      delay(50);
      WiFi.mode(WIFI_STA);
      WiFi.setSleep(WIFI_PS_NONE);
      WiFi.begin(WIFI_SSID, WIFI_PASS);
      wifiState = WIFI_CONNECTING;
      wifiConnectStart = millis();
      return false;
    case WIFI_CONNECTING:
      if (WiFi.status() == WL_CONNECTED) {
        Serial.printf("[WiFi] OK - RSSI:%d dBm IP:%s\n",
                      WiFi.RSSI(), WiFi.localIP().toString().c_str());
        wifiState = WIFI_IDLE;
        return true;
      }
      if (millis() - wifiConnectStart > 10000) {
        Serial.println("[WiFi] Timeout, reintento en 30s");
        WiFi.mode(WIFI_OFF);
        wifiState = WIFI_WAIT_RECONNECT;
        wifiConnectStart = millis();
      }
      return false;
    case WIFI_WAIT_RECONNECT:
      if (millis() - wifiConnectStart >= 30000) {
        wifiState = WIFI_IDLE;
      }
      return false;
  }
  return false;
}

bool conectarWiFiBloqueante() {
  // Solo para boot inicial
  Serial.print("[WiFi] Conectando a "); Serial.println(WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(WIFI_PS_NONE);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  int i = 0;
  while (WiFi.status() != WL_CONNECTED && i < 40) {  // 20s max
    delay(500); Serial.print("."); i++;
  }
  Serial.println();
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("[WiFi] OK - RSSI:%d dBm IP:%s\n",
                  WiFi.RSSI(), WiFi.localIP().toString().c_str());
    return true;
  }
  Serial.println("[WiFi] FALLO");
  return false;
}

bool sincronizarNTP() {
  if (WiFi.status() != WL_CONNECTED) return false;
  configTime(GMT_OFFSET_SEC, 0, NTP1, NTP2, NTP3);
  unsigned long inicio = millis();
  struct tm tinfo;
  while (millis() - inicio < 10000) {
    if (getLocalTime(&tinfo, 1000)) {
      lastNtpSync = millis();
      char tbuf[30];
      strftime(tbuf, sizeof(tbuf), "%Y-%m-%d %H:%M:%S", &tinfo);
      Serial.printf("[NTP] OK - %s\n", tbuf);
      return true;
    }
    delay(500);
  }
  Serial.println("[NTP] Timeout");
  return false;
}

void checkNTPLoop(unsigned long nowMs) {
  if (ntpReady) {
    if (nowMs - lastNtpSync > 6UL * 3600UL * 1000UL) {
      configTime(GMT_OFFSET_SEC, 0, NTP1, NTP2, NTP3);
      lastNtpSync = nowMs;
    }
    return;
  }
  static unsigned long lastTry = 0;
  if (nowMs - lastTry > 60000) {
    lastTry = nowMs;
    configTime(GMT_OFFSET_SEC, 0, NTP1, NTP2, NTP3);
  }
  struct tm t;
  if (getLocalTime(&t, 5)) {
    ntpReady = true;
    lastNtpSync = nowMs;
    Serial.println("[NTP] OK (sincronizado en loop)");
  }
}

void getTimestamp(char* buf, size_t bufLen) {
  struct tm t;
  if (getLocalTime(&t, 10)) {
    strftime(buf, bufLen, "%Y-%m-%dT%H:%M:%S", &t);
    return;
  }
  xSemaphoreTake(xMutexGPSObj, portMAX_DELAY);
  bool dateValid = gps.date.isValid();
  bool timeValid = gps.time.isValid();
  int age = gps.time.age();
  unsigned int y = gps.date.year();
  unsigned int mo = gps.date.month();
  unsigned int d = gps.date.day();
  unsigned int h = gps.time.hour();
  unsigned int mi = gps.time.minute();
  unsigned int s = gps.time.second();
  xSemaphoreGive(xMutexGPSObj);
  if (dateValid && timeValid && age < 5000) {
    snprintf(buf, bufLen, "%04u-%02u-%02dT%02u:%02u:%02uZ",
             y, mo, d, h, mi, s);
    return;
  }
  strncpy(buf, "1970-01-01T00:00:00", bufLen);
}

// ─────────────────────────────────────────────────────────────────
//  MQTT RECONNECT (PubSubClient, exponencial backoff)
// ─────────────────────────────────────────────────────────────────
void reconnectMQTT() {
  if (WiFi.status() != WL_CONNECTED) return;
  if (mqttClient.connected()) return;
  espClient.setInsecure();
  mqttClient.setServer(MQTT_BROKER, MQTT_PORT);
  char id[24];
  snprintf(id, sizeof(id), "SDrive-%x", random(0xffff));
  Serial.printf("[MQTT] Conectando como %s...\n", id);
  if (mqttClient.connect(id, MQTT_USER, MQTT_PASS)) {
    mqttReady = true;
    mqttBackoffMs = 2000;
    Serial.println("[MQTT] OK");
  } else {
    mqttReady = false;
    int rc = mqttClient.state();
    Serial.printf("[MQTT] FALLO cod=%d backoff=%lums\n", rc, mqttBackoffMs);
    mqttBackoffMs = min(mqttBackoffMs * 2, (unsigned long)30000);
  }
}

// ─────────────────────────────────────────────────────────────────
//  COLA DE MENSAJES: ENVIAR (desde tareaIMU/tareaGPS)
// ─────────────────────────────────────────────────────────────────

bool enviarMsgCola(int tipo, const char* json) {
  if (!json || !xQueueComms) return false;
  MsgPacket pkt;
  pkt.tipo = tipo;
  strncpy(pkt.json, json, MSG_JSON_MAX - 1);
  pkt.json[MSG_JSON_MAX - 1] = '\0';
  if (xQueueSend(xQueueComms, &pkt, 0) != pdTRUE) {
    Serial.printf("[QUEUE] Cola llena, mensaje descartado: %.40s...\n", json);
    return false;
  }
  return true;
}

// ─────────────────────────────────────────────────────────────────
//  TAREA IMU — Core 0, Prioridad 3
//  Muestreo MPU6050 a 100 Hz + filtro Madgwick + deteccion
// ─────────────────────────────────────────────────────────────────

// BEGIN EVENT SAMPLE PROCESSING (also exercised by the native replay tests)
void limpiarVentanasEventos() {
  vFreno = VentanaDeslizante<FRENO_N>{};
  vCurva = VentanaDeslizante<CURVA_N>{};
  speedSobreDesdeMs = 0;
  speedSustainActive = false;
  // Se conserva el cooldown aunque falle el sensor.
}

void procesarMuestraEventos(float myLinX, float myLinY, uint32_t nowMs,
                           bool myGpsWarmup, bool myGpsValid,
                           float myLat, float myLon, float mySpeed) {
  empujarMuestra(vFreno, myLinX, myLinX < BRAKE_THRESHOLD_MS2);
  empujarMuestra(vCurva, myLinY, fabsf(myLinY) > CURVE_THRESHOLD_MS2);
  
  evaluarVentanaDeslizante(vFreno, MIN_MUESTRAS_FRENO, "frenado_brusco", "FRENADO", 2, false,
                           nowMs, myGpsWarmup, myGpsValid, myLat, myLon);
  evaluarVentanaDeslizante(vCurva, MIN_MUESTRAS_CURVA, "curva_peligrosa", "CURVA", 2, true,
                           nowMs, myGpsWarmup, myGpsValid, myLat, myLon);
  
  // Velocidad (GPS 1 Hz, regla aparte)
  if (myGpsValid && mySpeed > SPEED_THRESHOLD_KMH) {
    if (!speedSustainActive) { speedSobreDesdeMs = nowMs; speedSustainActive = true; }
    if (nowMs - speedSobreDesdeMs >= SPEED_MIN_SUSTAIN_MS &&
               (!hasAnyEvent || nowMs - lastAnyEventMs >= EVENT_COOLDOWN_MS)) {
      lastAnyEventMs = nowMs;
      hasAnyEvent = true;
      if (myGpsWarmup) {
        char evtBuf[MSG_JSON_MAX];
        char tsEvt[30];
        getTimestamp(tsEvt, sizeof(tsEvt));
        int n = snprintf(evtBuf, sizeof(evtBuf),
          "{\"bus_id\":%d,\"type\":\"event\",\"event\":\"exceso_velocidad\","
          "\"lat\":%.7f,\"lon\":%.7f,\"value\":%.2f,\"timestamp\":\"%s\"}",
          DEVICE_ID, (double)myLat, (double)myLon, mySpeed, tsEvt);
        if (n < 0 || n >= (int)sizeof(evtBuf)) {
          Serial.println("[WARN] evtBuf truncado; evento no encolado");
        } else if (enviarMsgCola(MSG_EVENTO, evtBuf)) {
          Serial.printf("[EVENTO] exceso_velocidad %.2f km/h encolado\n", mySpeed);
        }
      } else {
        Serial.println("[EVENTO] exceso_velocidad detectado pero GPS warmup no completado");
      }
  
      DisplayMsg dmsg;
      dmsg.tipo = DISPLAY_EVENTO;
      strncpy(dmsg.linea1, "VELOCIDAD", 31);
      dmsg.linea1[31] = '\0';
      dmsg.valor = mySpeed;
      enviarDisplayEvento(&dmsg);
      beepEvento(3);
      speedSobreDesdeMs = 0;
      speedSustainActive = false;
    } else if (nowMs - speedSobreDesdeMs >= SPEED_MIN_SUSTAIN_MS &&
               hasAnyEvent && nowMs - lastAnyEventMs < EVENT_COOLDOWN_MS) {
      Serial.printf("[EVENTO] exceso_velocidad bloqueado por cooldown (%lu ms restantes)\n",
                    (unsigned long)(EVENT_COOLDOWN_MS - (nowMs - lastAnyEventMs)));
      speedSobreDesdeMs = 0;
      speedSustainActive = false;
    }
  } else {
    speedSobreDesdeMs = 0;
    speedSustainActive = false;
  }
}
// END EVENT SAMPLE PROCESSING

void tareaIMU(void* pvParameters) {
  TickType_t xLastWakeTime = xTaskGetTickCount();
  const TickType_t xIMUPeriod = pdMS_TO_TICKS(10);  // 100Hz = 10ms
  static unsigned long lastDiagPrint = 0;

  for (;;) {
    if (leerMPU()) {
      imuFallos = 0;
      imuReadCount++;

      // Stack watermark check cada 10s
      if (millis() - lastDiagPrint > 10000) {
        lastDiagPrint = millis();
        UBaseType_t hwm = uxTaskGetStackHighWaterMark(NULL);
        Serial.printf("[IMU] Stack HWM: %u bytes (%.1f%% used)\n", hwm, (TAREA_IMU_STACK - (float)hwm) * 100.0f / TAREA_IMU_STACK);
      }

      // Copy GPS data atomically for event enrichment
      float myLat = 0, myLon = 0, mySpeed = 0;
      bool myGpsValid = false;
      bool myGpsWarmup = gpsWarmupComplete;  // copia atomica (volatile bool)
      xSemaphoreTake(xMutexGPSData, portMAX_DELAY);
      myLat = gpsLat;
      myLon = gpsLon;
      mySpeed = gpsSpeed;
      myGpsValid = gpsLocationValid;
      xSemaphoreGive(xMutexGPSData);

      // Read accel sin gravedad under mutex for consistent snapshot
      float myLinX, myLinY;
      xSemaphoreTake(xMutexIMUData, portMAX_DELAY);
      myLinX = linX_ms2;
      myLinY = linY_ms2;
      xSemaphoreGive(xMutexIMUData);

      eventSampleClock.push(myLinX, myLinY, lastMadgwickSampleUs,
          []() { limpiarVentanasEventos(); },
          [&](float sampleX, float sampleY, uint32_t sampleMs) {
            procesarMuestraEventos(sampleX, sampleY, sampleMs, myGpsWarmup,
                                   myGpsValid, myLat, myLon, mySpeed);
          });
    } else {
      imuFallos++;
      if (imuFallos >= 100) {
        imuFallos = 0;
        Serial.println("[IMU] Fallos seguidos, re-despertando MPU...");
        despertarMPU();
      }
    }
    vTaskDelayUntil(&xLastWakeTime, xIMUPeriod);
  }
}

// ─────────────────────────────────────────────────────────────────
//  TAREA GPS — Core 0, Prioridad 3
//  Parseo NMEA continuo + copia atomica de datos GPS
// ─────────────────────────────────────────────────────────────────

void tareaGPS(void* pvParameters) {
  static unsigned long lastGpsWaitLogMs = 0;
  static bool previousFixAvailable = false;
  for (;;) {
    xSemaphoreTake(xMutexGPSObj, portMAX_DELAY);
    while (SerialGPS.available() > 0) {
      gps.encode(SerialGPS.read());
    }

    bool fixDisponible = gpsFixDisponible();
    bool newFixAvailable = fixDisponible && !previousFixAvailable;
    previousFixAvailable = fixDisponible;
    bool hdopValidNow = gps.hdop.isValid();
    uint8_t satsNow = gps.satellites.isValid() ?
      (uint8_t)min((unsigned long)gps.satellites.value(), 255UL) : 0;
    float hdopNow = hdopValidNow ? (float)gps.hdop.hdop() : 99.9f;
    bool nmeaSeenNow = gps.passedChecksum() > 0;

    // Copiar datos GPS de forma atomica para uso por tareaIMU/tareaComms
    xSemaphoreTake(xMutexGPSData, portMAX_DELAY);
    gpsSatelliteCount = satsNow;
    gpsHdopValue = hdopNow;
    gpsHdopValid = hdopValidNow;
    gpsNmeaSeen = nmeaSeenNow;
    if (fixDisponible) {
      gpsLat = gps.location.lat();
      gpsLon = gps.location.lng();
      gpsSpeed = gps.speed.isValid() && gps.speed.age() <= GPS_STALE_MS ? gps.speed.kmph() : 0.0f;
      gpsLocationValid = true;
      if (newFixAvailable) {
        gpsWarmupComplete = true;
        gpsImmediateTelemetry = true;
      }
    } else {
      gpsLocationValid = false;
    }
    xSemaphoreGive(xMutexGPSData);
    gpsReady = nmeaSeenNow;
    if (newFixAvailable) Serial.println("[GPS] Ubicacion disponible/restablecida; iniciando envios.");

    if (!hadFirstFix && fixDisponible && gps.date.isValid() && gps.time.isValid()) {
      hadFirstFix = true;
      coordsReady = true;
      Serial.println("[GPS] Ubicacion GPS obtenida");
      savePositionToEEPROM();
    }

    if (!fixDisponible && millis() - lastGpsWaitLogMs >= 5000) {
      lastGpsWaitLogMs = millis();
      unsigned long ageMs = gps.location.isValid() ? gps.location.age() : 0xFFFFFFFFUL;
      if (hdopValidNow) {
        Serial.printf("[GPS] Esperando ubicacion: NMEA=%d loc=%d age=%lu ms sats=%u HDOP=%.1f\n",
                      nmeaSeenNow, gps.location.isValid(), ageMs, (unsigned)satsNow, (double)hdopNow);
      } else {
        Serial.printf("[GPS] Esperando ubicacion: NMEA=%d loc=%d age=%lu ms sats=%u HDOP=no reportado\n",
                      nmeaSeenNow, gps.location.isValid(), ageMs, (unsigned)satsNow);
      }
    }

    xSemaphoreGive(xMutexGPSObj);

    vTaskDelay(1);  // ceder CPU (~1 ms)
  }
}

// ─────────────────────────────────────────────────────────────────
//  TAREA COMMS — Core 1, Prioridad 1
//  WiFi, NTP, MQTT, drenar cola, telemetria, display, serial
// ─────────────────────────────────────────────────────────────────

void tareaComms(void* pvParameters) {
  for (;;) {
    unsigned long nowMs = millis();

    // ── WiFi reconexion NO bloqueante ────────────────────────────
    if (WiFi.status() != WL_CONNECTED) {
      wifiReady = false;
      connectWiFiNonBlocking();
    } else {
      if (!wifiReady) {
        Serial.println("[WiFi] Reconectado");
      }
      wifiReady = true;

      // Drenar cola offline
      if (mqttClient.connected()) {
        unsigned long t0 = millis();
        int enviados = 0;
        while (pendientesEnCola() > 0 && enviados < 3 && (millis() - t0) < 150) {
          if (drenarUno()) enviados++;
          else break;
        }
        if (enviados > 0) {
          Serial.printf("[QUEUE] Enviados %d, pendientes: %d\n", enviados, pendientesEnCola());
        }
        limpiarColaSiVacia();
      }

      checkNTPLoop(nowMs);

      // MQTT reconexion
      if (!mqttClient.connected() && nowMs - lastMqttAttempt > mqttBackoffMs) {
        lastMqttAttempt = nowMs;
        reconnectMQTT();
      }
      mqttClient.loop();
    }

    // ── Procesar mensajes de la cola y publicar ──
    MsgPacket pkt;
    while (xQueueReceive(xQueueComms, &pkt, 0) == pdTRUE) {
      char topic[80];
      if (pkt.tipo == MSG_EVENTO) {
        snprintf(topic, sizeof(topic), "%s/%d/event", BASE_TOPIC, DEVICE_ID);
      } else {
        snprintf(topic, sizeof(topic), "%s/%d/gps", BASE_TOPIC, DEVICE_ID);
      }

      bool sent = false;
      if (mqttClient.connected()) {
        sent = mqttClient.publish(topic, pkt.json);
      }
      if (!sent) {
        encolarPaquete(pkt.json);
      }
    }

    // Cada alerta conserva la pantalla 5 s; las siguientes esperan en orden.
    procesarDisplay();

    // Enviar al recuperar una ubicacion; luego continuar cada 10 s.
    float lat = 0, lon = 0, speed = 0;
    bool valid = false;
    bool sendTelemetryNow = false;
    xSemaphoreTake(xMutexGPSData, portMAX_DELAY);
    sendTelemetryNow = gpsWarmupComplete &&
      (gpsImmediateTelemetry || nowMs - lastTelemetry >= TELEMETRY_INTERVAL_MS);
    if (sendTelemetryNow) gpsImmediateTelemetry = false;
    if (sendTelemetryNow) {
      lat = gpsLat;
      lon = gpsLon;
      speed = gpsSpeed;
      valid = gpsLocationValid;
    }
    xSemaphoreGive(xMutexGPSData);

    if (sendTelemetryNow) {
      lastTelemetry = nowMs;
      if (valid) {
        char gpsBuf[MSG_JSON_MAX];
        char tsGps[30];
        getTimestamp(tsGps, sizeof(tsGps));
        int n = snprintf(gpsBuf, sizeof(gpsBuf),
          "{\"bus_id\":%d,\"type\":\"gps\",\"lat\":%.7f,\"lon\":%.7f,\"speed\":%.2f,\"timestamp\":\"%s\"}",
          DEVICE_ID, (double)lat, (double)lon, (double)speed, tsGps);
        if (n < 0 || n >= (int)sizeof(gpsBuf)) { Serial.println("[WARN] gpsBuf truncado"); }
        enviarMsgCola(MSG_TELEMETRIA, gpsBuf);
        Serial.printf("[GPS] %.7f,%.7f %.1fkm/h Cola:%d\n",
                      (double)lat, (double)lon, (double)speed, pendientesEnCola());
      } else {
        Serial.println("[GPS] Telemetria pendiente, esperando ubicacion...");
      }
    }

    // ── Consola + display 1 Hz ────────────────────────────────
    if (nowMs - lastConsolePrint >= 1000) {
      lastConsolePrint = nowMs;

      struct tm t;
      char timeBuf[20];
      if (getLocalTime(&t, 10)) {
        strftime(timeBuf, sizeof(timeBuf), "%H:%M:%S", &t);
      } else {
        snprintf(timeBuf, sizeof(timeBuf), "00:00:00");
      }

      float myLinX = 0, myLinY = 0, myLinZ = 0;
      float myPitch = 0, myRoll = 0;
      float myAx = 0, myAy = 0, myAz = 0;
      float myLat = 0, myLon = 0, mySpeed = 0;
      bool myGpsValid = false;

      xSemaphoreTake(xMutexGPSData, portMAX_DELAY);
      myLat = gpsLat; myLon = gpsLon; mySpeed = gpsSpeed; myGpsValid = gpsLocationValid;
      xSemaphoreGive(xMutexGPSData);

      xSemaphoreTake(xMutexIMUData, portMAX_DELAY);
      myLinX = linX_ms2; myLinY = linY_ms2; myLinZ = linZ_ms2;
      myPitch = pitchDeg; myRoll = rollDeg;
      myAx = accelX_ms2; myAy = accelY_ms2; myAz = accelZ_ms2;
      xSemaphoreGive(xMutexIMUData);

      Serial.printf("[%s] Ax:%.2f Ay:%.2f Az:%.2f | P:%.1f R:%.1f | Lx:%.2f Ly:%.2f Lz:%.2f | %.7f %.7f %.1fkm/h\n",
                    timeBuf,
                    myAx, myAy, myAz,
                    myPitch, myRoll,
                    myLinX, myLinY, myLinZ,
                    (double)myLat, (double)myLon, (double)mySpeed);

      // Stack HWM para tareaComms
      UBaseType_t commsHwm = uxTaskGetStackHighWaterMark(xHandleComms);
      if (commsHwm < 2048) {
        Serial.printf("[STACK WARNING] Comms HWM: %u bytes (%.1f%% used)\n",
                      commsHwm, (TAREA_COMMS_STACK - (float)commsHwm) * 100.0f / TAREA_COMMS_STACK);
      }

    }

    // ── Buzzer + serial ────────────────────────────────────────
    tickBuzzer(nowMs);
    handleSerialCommand();

    vTaskDelay(1);  // ceder CPU
  }
}

// ─────────────────────────────────────────────────────────────────
//  COMANDOS SERIALES
// ─────────────────────────────────────────────────────────────────

void handleSerialCommand() {
  if (!Serial.available()) return;

  char cmdBuf[32];
  int len = Serial.readBytesUntil('\n', cmdBuf, sizeof(cmdBuf) - 1);
  if (len <= 0) return;
  cmdBuf[len] = '\0';
  // Trim whitespace
  char* start = cmdBuf;
  while (*start == ' ' || *start == '\t') start++;
  char* end = cmdBuf + len - 1;
  while (end > start && (*end == ' ' || *end == '\t' || *end == '\r')) end--;
  *(end + 1) = '\0';
  // Lowercase
  for (char* p = start; *p; p++) { if (*p >= 'A' && *p <= 'Z') *p += 32; }

  if (strcmp(start, "status") == 0) {
    Serial.println("\n========== STATUS ==========");
    Serial.printf("  WiFi:   %s\n", wifiReady ? "OK" : "NO");
    Serial.printf("  NTP:    %s\n", ntpReady ? "OK" : "NO");
    Serial.printf("  IMU:    %s\n", imuReady ? "OK" : "NO");
    xSemaphoreTake(xMutexGPSObj, portMAX_DELAY);
    bool fixDisponible = gpsFixDisponible();
    xSemaphoreGive(xMutexGPSObj);
    Serial.printf("  GPS:    %s (ubicacion reciente: %s)\n", gpsReady ? "OK" : "NO",
                  fixDisponible ? "SI" : "NO");
    Serial.printf("  SD:     %s\n", sdReady ? "OK" : "NO");
    Serial.printf("  MQTT:   %s\n", mqttReady ? "OK" : "NO");
    Serial.printf("  Coords: %s\n", coordsReady ? "SI" : "NO");
    Serial.printf("  Cola:   %d pendientes\n", pendientesEnCola());
    float sLat = 0, sLon = 0, sSpd = 0;
    bool sValid = false;
    xSemaphoreTake(xMutexGPSData, portMAX_DELAY);
    sValid = gpsLocationValid; sLat = gpsLat; sLon = gpsLon; sSpd = gpsSpeed;
    xSemaphoreGive(xMutexGPSData);
    if (sValid) {
      Serial.printf("  Lat:    %.7f\n", (double)sLat);
      Serial.printf("  Lon:    %.7f\n", (double)sLon);
      Serial.printf("  Speed:  %.1f km/h\n", (double)sSpd);
    }
    xSemaphoreTake(xMutexIMUData, portMAX_DELAY);
    float lx = linX_ms2, ly = linY_ms2, lz = linZ_ms2;
    xSemaphoreGive(xMutexIMUData);
    Serial.printf("  Acc s/gravedad: X=%.2f Y=%.2f Z=%.2f m/s2\n", lx, ly, lz);
    Serial.println("===========================\n");

  } else if (strcmp(start, "diag") == 0) {
    Serial.println("\n========== DIAG ==========");
    Serial.printf("  Heap:      %u bytes\n", ESP.getFreeHeap());
    Serial.printf("  Uptime:    %lu ms\n", millis() - bootMs);
    Serial.printf("  GPS chars: %lu\n", (unsigned long)gps.charsProcessed());
    Serial.printf("  WiFi RSSI: %d dBm\n", WiFi.RSSI());
    Serial.printf("  MQTT state: %d\n", mqttClient.state());
    unsigned long up = millis() - bootMs;
    Serial.printf("  IMU reads: %lu (%.1f Hz promedio)\n",
                  imuReadCount, up > 0 ? imuReadCount * 1000.0f / up : 0.0f);
    Serial.printf("  Calib: %s\n", calibFuente ? "EEPROM" : "Fabrica");
    Serial.printf("  Cola FreeRTOS: %d/%d\n",
                  (int)uxQueueMessagesWaiting(xQueueComms), QUEUE_LENGTH);
    Serial.printf("  Cola Display: %d/10\n",
                  (int)uxQueueMessagesWaiting(xQueueDisplay));
    Serial.println("==========================\n");

  } else if (strcmp(start, "drain") == 0) {
    Serial.println("[DRAIN] Enviando cola...");
    int enviados = 0;
    while (mqttClient.connected() && pendientesEnCola() > 0) {
      if (drenarUno()) enviados++;
      else break;
      delay(100);
    }
    Serial.printf("[DRAIN] Enviados: %d, Pendientes: %d\n", enviados, pendientesEnCola());

  } else if (strcmp(start, "save") == 0) {
    xSemaphoreTake(xMutexGPSObj, portMAX_DELAY);
    savePositionToEEPROM();
    xSemaphoreGive(xMutexGPSObj);

  } else if (strcmp(start, "clear") == 0) {
    savedPos.magic = 0;
    EEPROM.put(EEPROM_ADDR_GPS, savedPos);
    EEPROM.commit();
    Serial.println("[EEPROM] Posicion borrada");

  } else if (strcmp(start, "calib") == 0) {
    calibrarIMUYGuardar();

  } else if (strcmp(start, "imu") == 0) {
    xSemaphoreTake(xMutexIMUData, portMAX_DELAY);
    Serial.printf("  Accel: %.2f %.2f %.2f ms2\n", accelX_ms2, accelY_ms2, accelZ_ms2);
    Serial.printf("  Gyro:  %.2f %.2f %.2f dps\n", gyroX_dps, gyroY_dps, gyroZ_dps);
    Serial.printf("  s/grav: %.2f %.2f %.2f ms2\n", linX_ms2, linY_ms2, linZ_ms2);
    Serial.printf("  Pitch: %.1f Roll: %.1f\n", pitchDeg, rollDeg);
    xSemaphoreGive(xMutexIMUData);

  } else if (strcmp(start, "help") == 0) {
    Serial.println("\n========== COMANDOS ==========");
    Serial.println("  status  - Estado del sistema");
    Serial.println("  diag    - Diagnostico detallado");
    Serial.println("  drain   - Enviar cola offline");
    Serial.println("  save    - Guardar posicion en EEPROM");
    Serial.println("  clear   - Borrar posicion de EEPROM");
    Serial.println("  calib   - Calibrar IMU (mantener quieto)");
    Serial.println("  imu     - Mostrar datos IMU en bruto");
    Serial.println("  help    - Esta ayuda");
    Serial.println("================================\n");

  } else if (strlen(start) > 0) {
    Serial.println("# Comando no valido. Envia 'help'");
  }
}

// ─────────────────────────────────────────────────────────────────
//  SETUP — inicializa hardware, crea tareas, termina
// ─────────────────────────────────────────────────────────────────

void setup() {
  bootMs = millis();
  Serial.begin(115200);
  delay(1500);

  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW);

  pinMode(2, OUTPUT);
  digitalWrite(2, LOW);

  Serial.println("\n========================================");
  Serial.println("    SENTNLDRIVE - SISTEMA PRINCIPAL V2");
  Serial.println("       (FreeRTOS - 3 Tareas)");
  Serial.println("========================================");

  // ── Crear recursos FreeRTOS ANTES de las tareas ─────────────
  xQueueComms   = xQueueCreate(QUEUE_LENGTH, sizeof(MsgPacket));
  xQueueDisplay = xQueueCreate(DISPLAY_QUEUE_LENGTH, sizeof(DisplayMsg));
  xQueueBuzzer  = xQueueCreate(BUZZER_QUEUE_LENGTH, sizeof(uint8_t));
  xMutexSD      = xSemaphoreCreateMutex();
  xMutexI2C     = xSemaphoreCreateMutex();
  xMutexGPSData = xSemaphoreCreateMutex();
  xMutexGPSObj  = xSemaphoreCreateMutex();
  xMutexIMUData = xSemaphoreCreateMutex();

  if (!xQueueComms || !xQueueDisplay || !xQueueBuzzer || !xMutexSD || !xMutexI2C || !xMutexGPSData || !xMutexGPSObj || !xMutexIMUData) {
    Serial.println("[FATAL] Error creando recursos FreeRTOS. Reiniciando...");
    delay(1500);
    ESP.restart();
  }

  // ── Display + I2C bus (compartido OLED + IMU SDA=21/SCL=22) ──
  Wire.begin(I2C_SDA, I2C_SCL);
  Wire.setClock(400000);
  initDisplay();
  mostrarBootPaso(1, "Display", displayReady);

  // ── PASO 2: SD ──────────────────────────────────────────────
  Serial.print("[P2] SD... ");
  mostrarBootPaso(2, "SD", false);
  SPI.begin(18, 19, 23, SD_CS_PIN);
  delay(500);
  {
    int intentos = 0;
    while (!SD.begin(SD_CS_PIN) && intentos < 5) {
      intentos++;
      SD.end();
      delay(800);
    }
    SD.end(); delay(200);
    if (SD.begin(SD_CS_PIN)) {
      sdReady = true;
      initQueue();
      logCrashReason();  // registrar razón del reinicio anterior
    }
  }
  Serial.println(sdReady ? "OK" : "FALLO");
  mostrarBootPaso(2, "SD", sdReady);
  delay(1500);
  if (!sdReady) {
    mostrarBootMsg(2, "SD", "FATAL: Sin SD. Reiniciando...");
    delay(2000);
    ESP.restart();
  }

  // ── PASO 3: IMU (MPU6050 - Filtro Madgwick) ────────────────
  Serial.print("[P3] IMU (MPU6050)... ");
  mostrarBootPaso(3, "IMU", false);
  EEPROM.begin(EEPROM_SIZE);
  loadCalib();
  imuReady = despertarMPU();
  if (!imuReady) {
    Serial.println("FALLO (sin conexion I2C)");
    mostrarBootMsg(3, "IMU", "FATAL: Sin IMU. Reiniciando...");
    delay(2000);
    ESP.restart();
  }
  Serial.println("OK");
  imuReady = true;
  mostrarBootPaso(3, "IMU", true);

  // ── Inicializar Madgwick ────────────────────────────────────
  madgwickFilter.begin(IMU_RATE_HZ);
  madgwickFilter.setBeta(0.04f);
  madgInitOK = true;
  Serial.println("[MADG] Filtro Madgwick iniciado (beta=0.04)");

  // ── PASO 4: GPS + EEPROM ───────────────────────────────────
  Serial.print("[P4] GPS (NEO-6M/M8N)... ");
  mostrarBootPaso(4, "GPS", false);
  loadSavedPosition();
  SerialGPS.begin(9600, SERIAL_8N1, GPS_RX, GPS_TX);
  // Esperar hasta 3s a que llegue una frase NMEA valida.
  unsigned long gpsEspera = millis();
  gpsReady = false;
  while (millis() - gpsEspera < 3000 && !gpsReady) {
    while (SerialGPS.available() > 0) gps.encode(SerialGPS.read());
    if (gps.passedChecksum() > 0) gpsReady = true;
    delay(10);
  }
  Serial.printf("[GPS] chars=%lu checksum_ok=%lu checksum_error=%lu ready=%d\n",
                (unsigned long)gps.charsProcessed(),
                (unsigned long)gps.passedChecksum(),
                (unsigned long)gps.failedChecksum(), gpsReady);
  if (savedPos.magic == EEPROM_MAGIC) {
    Serial.println("[GPS] Enviando warm start...");
    mostrarBootMsg(4, "GPS", "Warm start...");
    sendWarmStart();
    delay(1500);
  }
  Serial.println("OK (esperando fix)");
  mostrarBootPaso(4, "GPS", true);
  delay(1500);

  // ── PASO 5: WiFi ──────────────────────────────────────────
  Serial.print("[P5] WiFi... ");
  mostrarBootPaso(5, "WiFi", false);
  wifiReady = conectarWiFiBloqueante();
  Serial.println(wifiReady ? "OK" : "OFFLINE");
  mostrarBootPaso(5, "WiFi", wifiReady);
  delay(1500);
  if (!wifiReady) {
    mostrarBootMsg(5, "WiFi", "Sin WiFi - Modo offline");
    Serial.println("[WiFi] Sin conexion. Operando offline. Se reconectara en tareaComms.");
    delay(2000);
  }

  // ── PASO 6: NTP ──────────────────────────────────────────
  Serial.print("[P6] NTP... ");
  mostrarBootPaso(6, "NTP", false);
  ntpReady = sincronizarNTP();
  Serial.println(ntpReady ? "OK" : "PENDIENTE");
  mostrarBootPaso(6, "NTP", ntpReady);
  delay(1500);
  if (!ntpReady) {
    mostrarBootMsg(6, "NTP", "Sin NTP - Sincronizando despues");
    Serial.println("[NTP] Sin sincronizacion. checkNTPLoop() intentara cada 60s.");
    delay(2000);
  }

  // ── MQTT config (PubSubClient) ─────────────────────────────
  espClient.setInsecure();
  mqttClient.setKeepAlive(15);
  mqttClient.setSocketTimeout(2);
  mqttClient.setBufferSize(1400);

  // ── Esperar fix GPS DE CALIDAD (tolerante a fallo) ──────────
  Serial.println("\n[INIT] Esperando ubicacion GPS reciente (max 30 s; seguira buscando despues)...");
  unsigned long t0 = millis();
  bool fixOk = false;
  while (millis() - t0 < 30000) {
    while (SerialGPS.available() > 0) gps.encode(SerialGPS.read());
    if (gpsFixDisponible()) { fixOk = true; break; }


    if ((millis() - t0) % 2000 < 100) {
      unsigned long elapsed = (millis() - t0) / 1000;
      unsigned long sats = gps.satellites.isValid() ? gps.satellites.value() : 0;
      float hdop = gps.hdop.isValid() ? gps.hdop.hdop() : 99.9;
      char msg[40];
      snprintf(msg, sizeof(msg), "%lus sats:%lu hdop:%.1f", elapsed, sats, hdop);
      mostrarBootMsg(6, "GPS Fix...", msg);
    }
    delay(50);
  }

  if (fixOk) {
    coordsReady = true;
    gpsLocationValid = true;
    gpsLat = gps.location.lat();
    gpsLon = gps.location.lng();
    gpsSpeed = gps.speed.isValid() && gps.speed.age() <= GPS_STALE_MS ? gps.speed.kmph() : 0.0f;
    Serial.printf("[INIT] Fix GPS: %.7f, %.7f\n", (double)gpsLat, (double)gpsLon);
  } else {
    coordsReady = false;
    Serial.printf("[GPS] Sin ubicacion despues de 30s. Continuando y buscando en segundo plano. Sats=%lu chars=%lu\n",
                  gps.satellites.isValid() ? (unsigned long)gps.satellites.value() : 0UL,
                  (unsigned long)gps.charsProcessed());
    mostrarBootMsg(6, "GPS", "Sin fix - Operando sin GPS");
    delay(2000);
  }

  mostrarBootPaso(6, "MQTT", true);

  // ── Resumen ─────────────────────────────────────────────────
  Serial.println("\n========================================");
  Serial.println("  SISTEMA LISTO - OPERACION AUTONOMA");
  Serial.printf("  ID: %d | WiFi: %s | NTP: %s\n",
                DEVICE_ID, wifiReady ? "OK" : "OFFLINE", ntpReady ? "OK" : "PENDIENTE");
  Serial.printf("  IMU: %d Hz | Filtro Madgwick | Calib: %s\n", IMU_RATE_HZ, calibFuente ? "EEPROM" : "Fabrica");
  Serial.printf("  Frenado: < %.2f m/s2 (80%% ventana deslizante %d ms / %d muestras)\n", BRAKE_THRESHOLD_MS2, FRENO_WINDOW_MS, FRENO_N);
  Serial.printf("  Curva:   > %.2f m/s2 (80%% ventana deslizante %d ms / %d muestras + direccion)\n", CURVE_THRESHOLD_MS2, CURVA_WINDOW_MS, CURVA_N);
  Serial.printf("  Velocidad: > %.0f km/h sostenidos %.1f s\n",
                SPEED_THRESHOLD_KMH, SPEED_MIN_SUSTAIN_MS / 1000.0f);
  Serial.println("========================================\n");

  if (displayReady) {
    xSemaphoreTake(xMutexI2C, portMAX_DELAY);
    display.clearDisplay();
    display.setTextSize(1);
    display.setCursor(0, 0);
    display.println("SENTNLDRIVE");
    display.println();
    display.println("SISTEMA LISTO");
    display.printf("ID: %d\n", DEVICE_ID);
    display.display();
    xSemaphoreGive(xMutexI2C);
    delay(2000);
  }

  lastTelemetry = millis();

  mqttBackoffMs = 2000;
  lastMqttAttempt = 0;

  Serial.println("Envia 'help' para ver comandos\n");

  // ── Crear tareas FreeRTOS ───────────────────────────────────
  xTaskCreatePinnedToCore(
    tareaIMU,           // funcion
    "tareaIMU",         // nombre
    TAREA_IMU_STACK,    // stack
    NULL,               // parametro
    3,                  // prioridad (alta)
    &xHandleIMU,        // handle
    0                   // core 0
  );

  xTaskCreatePinnedToCore(
    tareaGPS,
    "tareaGPS",
    TAREA_GPS_STACK,
    NULL,
    2,                  // prioridad (baja que tareaIMU)
    &xHandleGPS,
    0                   // core 0
  );

  xTaskCreatePinnedToCore(
    tareaComms,
    "tareaComms",
    TAREA_COMMS_STACK,  // stack grande (TLS/MQTT)
    NULL,
    1,                  // prioridad (baja)
    &xHandleComms,
    1                   // core 1
  );

  Serial.println("[RTOS] 3 tareas creadas:");
  Serial.printf("  tareaIMU   -> Core 0, PRI 3, stack %d\n", TAREA_IMU_STACK);
  Serial.printf("  tareaGPS   -> Core 0, PRI 2, stack %d\n", TAREA_GPS_STACK);
  Serial.printf("  tareaComms -> Core 1, PRI 1, stack %d\n", TAREA_COMMS_STACK);
  Serial.printf("[RTOS] Recursos: xQueueComms(%d), xQueueDisplay(%d), xQueueBuzzer(%d), mutexes I2C/SD/GPS/IMU\n",
                QUEUE_LENGTH, DISPLAY_QUEUE_LENGTH, BUZZER_QUEUE_LENGTH);
  Serial.println("[RTOS] setup() completado. Borrando tarea init.\n");

  // Eliminar la tarea de setup — loop() queda vacio
  vTaskDelete(NULL);
}

// ─────────────────────────────────────────────────────────────────
//  LOOP — vacio (FreeRTOS maneja todo)
// ─────────────────────────────────────────────────────────────────

void loop() {
  vTaskDelay(portMAX_DELAY);
}
