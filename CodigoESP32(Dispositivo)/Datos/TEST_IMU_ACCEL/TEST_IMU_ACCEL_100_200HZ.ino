/*
 * SENTINELDRIVE - IMU + Filtro Complementario (SimpleFusion) + Madgwick (Cuaterniones)
 * Calibracion automatica obligatoria al arrancar.
 * Pitch y Roll calculados en cada muestra a 100Hz.
 * Aceleracion lineal calculada por ambos metodos en paralelo para comparacion.
 *
 * Comandos Serial:
 *   run      - Inicia streaming
 *   pause    - Pausa streaming
 *   console  - Modo consola (calibrado)
 *   raw      - Modo consola (datos SIN calibrar)
 *   linear   - Aceleracion lineal (sin gravedad)
 *   plot     - Modo grafica (CSV para Serial Plotter)
 *   ntp      - Modo NTP (CSV con hora ISO @100Hz)
 *   cal      - Recalibrar sensor (10s, deja quieto)
 *   orient   - Detectar orientacion del sensor
 *   alpha    - Cambiar alpha del filtro
 *   hz       - Cambiar frecuencia de muestreo
 *   offsets  - Exportar offsets para otro codigo
 *   status   - Muestra configuracion actual
 *   help     - Lista de comandos
 */

#include <Wire.h>
#include <math.h>
#include <simpleFusion.h>
#include <WiFi.h>
#include <time.h>
#include <Adafruit_AHRS_Madgwick.h>

#define I2C_SDA   21
#define I2C_SCL   22
#define MPU_ADDR  0x68

const uint32_t SERIAL_BAUD = 115200;

// --- WiFi/NTP ---
const char* WIFI_SSID = "Sent";
const char* WIFI_PASS = "12345678";
const char* NTP_SERVER = "pool.ntp.org";
const long GMT_OFFSET_SEC = -5 * 3600;  // Ecuador UTC-5
const int DST_OFFSET_SEC = 0;
bool ntpSynced = false;

// --- Configuracion de muestreo ---
uint16_t sampleRateHz = 100;
uint32_t sampleIntervalUs = 1000000UL / 100;
uint32_t nextSampleUs = 0;

// --- Offsets (hardcodeados de calibracion previa) ---
float offsetGx = -3.950943f;
float offsetGy = 0.676909f;
float offsetGz = 0.634480f;
float offsetAx = 0.101762f;
float offsetAy = 0.131929f;
float offsetAz = 0.613355f;

// --- Orientacion del sensor en el vehículo ---
// 0=plano(Z arriba), 1=X abajo, 2=X arriba, 3=Y abajo, 4=Y arriba, 5=Z abajo
int sensorOrientation = 0;

// --- Filtro complementario ---
SimpleFusion fuser;
float filterAlpha = 0.98f;   // Gyro weight (1-alpha = accel weight)

// --- Constantes ---
const float DEG2RAD = 0.01745329252f;
const float RAD2DEG = 57.29577951f;

// --- Modo de salida ---
enum OutputMode { MODE_CONSOLE, MODE_PLOT, MODE_RAW, MODE_LINEAR, MODE_NTP };
OutputMode outputMode = MODE_CONSOLE;
bool streaming = false;

// --- Timers ---
uint32_t lastConsoleMs = 0;
uint32_t lastPlotMs = 0;

// --- Ultimos valores fusionados ---
float lastPitch = 0, lastRoll = 0;

// --- Filtro Madgwick (paralelo) ---
Adafruit_Madgwick madgwickFilter;
float madg_q0, madg_q1, madg_q2, madg_q3;
float madg_gravity_x, madg_gravity_y, madg_gravity_z;
float madg_lin_x, madg_lin_y, madg_lin_z;
float madg_pitch = 0, madg_roll = 0;

// --- Aceleracion lineal (Complementary) ---
float comp_lin_x, comp_lin_y, comp_lin_z;

// --- Gravedad proyectada (para comparacion) ---
float comp_grav_x, comp_grav_y, comp_grav_z;
float madg_grav_x, madg_grav_y, madg_grav_z;

// --- Estadisticas ---
uint32_t sampleCount = 0;
uint32_t errorCount = 0;
uint32_t startMs = 0;

// --- Ultimos valores RAW (sin calibrar) ---
int16_t lastAxRaw, lastAyRaw, lastAzRaw;
int16_t lastGxRaw, lastGyRaw, lastGzRaw;
int16_t lastTempRaw;

// --- Funciones I2C ---

bool writeMPURegister(uint8_t reg, uint8_t value) {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(reg);
  Wire.write(value);
  return Wire.endTransmission(true) == 0;
}

bool setupMPU() {
  if (!writeMPURegister(0x6B, 0x00)) return false;
  delay(100);
  if (!writeMPURegister(0x1B, 0x00)) return false;
  if (!writeMPURegister(0x1C, 0x00)) return false;
  return true;
}

bool readMPUAll(int16_t& ax, int16_t& ay, int16_t& az,
                int16_t& temp, int16_t& gx, int16_t& gy, int16_t& gz) {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x3B);
  if (Wire.endTransmission(false) != 0) return false;
  if (Wire.requestFrom(MPU_ADDR, 14, true) != 14) return false;

  ax   = (int16_t)((Wire.read() << 8) | Wire.read());
  ay   = (int16_t)((Wire.read() << 8) | Wire.read());
  az   = (int16_t)((Wire.read() << 8) | Wire.read());
  temp = (int16_t)((Wire.read() << 8) | Wire.read());
  gx   = (int16_t)((Wire.read() << 8) | Wire.read());
  gy   = (int16_t)((Wire.read() << 8) | Wire.read());
  gz   = (int16_t)((Wire.read() << 8) | Wire.read());
  return true;
}

// --- Calibracion OBLIGATORIA al inicio ---

void calibrateMPU() {
  Serial.println("\n========================================");
  Serial.println("  CALIBRACION OBLIGATORIA (10 segundos)");
  Serial.println("  Deja el sensor COMPLETAMENTE QUIETO");
  Serial.println("  sobre una superficie nivelada...");
  Serial.println("  Esperando 2 segundos para estabilizar");
  Serial.println("========================================\n");

  delay(2000);

  const int samples = 10000;
  float sumGx = 0, sumGy = 0, sumGz = 0;
  float sumAx = 0, sumAy = 0, sumAz = 0;
  int validSamples = 0;

  Serial.print("Muestreando: ");
  for (int i = 0; i < samples; i++) {
    int16_t axRaw, ayRaw, azRaw, tempRaw, gxRaw, gyRaw, gzRaw;
    if (!readMPUAll(axRaw, ayRaw, azRaw, tempRaw, gxRaw, gyRaw, gzRaw)) {
      errorCount++;
      continue;
    }
    sumGx += gxRaw / 131.0f;
    sumGy += gyRaw / 131.0f;
    sumGz += gzRaw / 131.0f;
    sumAx += axRaw / 16384.0f * 9.80665f;
    sumAy += ayRaw / 16384.0f * 9.80665f;
    sumAz += azRaw / 16384.0f * 9.80665f;
    validSamples++;
    delayMicroseconds(500);

    if (i % 2000 == 0) Serial.print(".");
  }
  Serial.println(" OK");

  if (validSamples < 1000) {
    Serial.printf("# ERROR: Solo %d muestras validas de %d\n", validSamples, samples);
    Serial.println("# Reintentando...");
    calibrateMPU();
    return;
  }

  offsetGx = sumGx / validSamples;
  offsetGy = sumGy / validSamples;
  offsetGz = sumGz / validSamples;
  offsetAx = sumAx / validSamples;
  offsetAy = sumAy / validSamples;
  offsetAz = (sumAz / validSamples) - 9.80665f;

  Serial.println("\n>>> Calibracion COMPLETADA <<<");
  Serial.printf("  Gyro offsets: Gx=%.4f  Gy=%.4f  Gz=%.4f (deg/s)\n",
                offsetGx, offsetGy, offsetGz);
  Serial.printf("  Acc offsets:  Ax=%.4f  Ay=%.4f  Az=%.4f (m/s2)\n\n",
                offsetAx, offsetAy, offsetAz);
}

// --- Deteccion automatica de orientacion ---

void detectOrientation() {
  Serial.println("\n# Detectando orientacion del sensor...");
  Serial.println("# Deja el sensor QUIETO en su posicion de montaje");

  delay(2000);

  const int samples = 500;
  float sumAx = 0, sumAy = 0, sumAz = 0;

  for (int i = 0; i < samples; i++) {
    int16_t axRaw, ayRaw, azRaw, tempRaw, gxRaw, gyRaw, gzRaw;
    if (!readMPUAll(axRaw, ayRaw, azRaw, tempRaw, gxRaw, gyRaw, gzRaw)) continue;
    sumAx += (axRaw / 16384.0f * 9.80665f) - offsetAx;
    sumAy += (ayRaw / 16384.0f * 9.80665f) - offsetAy;
    sumAz += (azRaw / 16384.0f * 9.80665f) - offsetAz;
    delayMicroseconds(1000);
  }

  float ax = sumAx / samples;
  float ay = sumAy / samples;
  float az = sumAz / samples;

  Serial.printf("# Acc promedio: AX=%.2f  AY=%.2f  AZ=%.2f\n", ax, ay, az);

  float absAx = fabs(ax);
  float absAy = fabs(ay);
  float absAz = fabs(az);
  const float G = 9.8f;

  // Detectar qué eje tiene la gravedad
  if (absAz > G * 0.8) {
    sensorOrientation = (az > 0) ? 0 : 5;  // Z up o Z down
  } else if (absAx > G * 0.8) {
    sensorOrientation = (ax > 0) ? 1 : 2;  // X down o X up
  } else if (absAy > G * 0.8) {
    sensorOrientation = (ay > 0) ? 3 : 4;  // Y down o Y up
  } else {
    Serial.println("# WARNING: No se pudo detectar orientacion clara");
    sensorOrientation = 0;  // Asumir plano
  }

  const char* orientNames[] = {
    "PLANO (Z arriba)",
    "VERTICAL (X abajo)",
    "VERTICAL (X arriba)",
    "VERTICAL (Y abajo)",
    "VERTICAL (Y arriba)",
    "INVERTIDO (Z abajo)"
  };
  Serial.printf("# Orientacion detectada: %s [%d]\n\n", orientNames[sensorOrientation], sensorOrientation);
}



// --- Comandos seriales ---

void handleSerialCommand() {
  if (!Serial.available()) return;
  String cmd = Serial.readStringUntil('\n');
  cmd.trim();
  cmd.toLowerCase();

  if (cmd == "run") {
    streaming = true;
    nextSampleUs = micros();
    lastConsoleMs = millis();
    lastPlotMs = millis();
    startMs = millis();
    sampleCount = 0;
    errorCount = 0;
    Serial.println("# RUN - Streaming activado");

  } else if (cmd == "pause") {
    streaming = false;
    uint32_t elapsed = (millis() - startMs) / 1000;
    Serial.printf("# PAUSED - %lu segundos, %lu muestras, %lu errores\n",
                  elapsed, sampleCount, errorCount);

  } else if (cmd == "console") {
    outputMode = MODE_CONSOLE;
    Serial.println("# MODO: CONSOLE (calibrado)");

  } else if (cmd == "raw") {
    outputMode = MODE_RAW;
    Serial.println("# MODO: RAW (sin calibrar)");

  } else if (cmd == "linear") {
    outputMode = MODE_LINEAR;
    Serial.println("# MODO: LINEAR (aceleracion sin gravedad)");

  } else if (cmd == "plot") {
    outputMode = MODE_PLOT;
    Serial.println("# MODO: PLOT (28 columnas CSV @20Hz)");
    Serial.println("# Orden columnas:");
    Serial.println("#  1-3  Acc RAW (m/s2)          : axRaw, ayRaw, azRaw");
    Serial.println("#  4-6  Acc FILTRADO (m/s2)     : ax, ay, az");
    Serial.println("#  7-9  Acc s/gravedad COMP (m/s2)  : comp_linX, comp_linY, comp_linZ");
    Serial.println("# 10-12 Gravedad COMP (m/s2)    : comp_gravX, comp_gravY, comp_gravZ");
    Serial.println("# 13-15 Acc s/gravedad MADG (m/s2)  : madg_linX, madg_linY, madg_linZ");
    Serial.println("# 16-18 Gravedad MADG (m/s2)    : madg_gravX, madg_gravY, madg_gravZ");
    Serial.println("# 19-21 Gyro RAW (deg/s)        : gxRaw, gyRaw, gzRaw");
    Serial.println("# 22-24 Gyro FILTRADO (deg/s)   : gx, gy, gz");
    Serial.println("# 25-26 Pitch/Roll COMP (deg)   : pitch, roll");
    Serial.println("# 27-28 Pitch/Roll MADG (deg)   : madg_pitch, madg_roll");

  } else if (cmd == "cal") {
    streaming = false;
    calibrateMPU();
    Serial.println("# Envia 'run' para comenzar");

  } else if (cmd == "orient") {
    streaming = false;
    detectOrientation();
    Serial.println("# Envia 'run' para comenzar");

  } else if (cmd == "status") {
    const char* modeStr = "CONSOLE";
    if (outputMode == MODE_PLOT) modeStr = "PLOT";
    else if (outputMode == MODE_RAW) modeStr = "RAW";
    else if (outputMode == MODE_LINEAR) modeStr = "LINEAR";
    else if (outputMode == MODE_NTP) modeStr = "NTP";
    const char* orientNames[] = {
      "PLANO (Z arriba)", "VERTICAL (X abajo)", "VERTICAL (X arriba)",
      "VERTICAL (Y abajo)", "VERTICAL (Y arriba)", "INVERTIDO (Z abajo)"
    };
    const char* orientStr = (sensorOrientation >= 0) ? orientNames[sensorOrientation] : "NO DETECTADA";
    Serial.println("\n--- STATUS ---");
    Serial.printf("  Sample rate:  %u Hz\n", sampleRateHz);
    Serial.printf("  Alpha:        %.2f (gyro) / %.2f (accel)\n", filterAlpha, 1.0f - filterAlpha);
    Serial.printf("  Madgwick beta: %.4f\n", madgwickFilter.getBeta());
    Serial.printf("  Modo:         %s\n", modeStr);
    Serial.printf("  Orientacion:  %s\n", orientStr);
    Serial.printf("  Streaming:    %s\n", streaming ? "SI" : "NO");
    Serial.printf("  Comp Pitch:   %.2f deg\n", lastPitch);
    Serial.printf("  Comp Roll:    %.2f deg\n", lastRoll);
    Serial.printf("  Madg Pitch:   %.2f deg\n", madg_pitch);
    Serial.printf("  Madg Roll:    %.2f deg\n", madg_roll);
    Serial.printf("  Muestras:     %lu\n", sampleCount);
    Serial.printf("  Errores:      %lu\n", errorCount);
    Serial.printf("  Gyro offsets: %.4f %.4f %.4f\n", offsetGx, offsetGy, offsetGz);
    Serial.printf("  Acc offsets:  %.4f %.4f %.4f\n", offsetAx, offsetAy, offsetAz);
    Serial.println("---------------\n");

  } else if (cmd == "events") {
    Serial.println("\n--- EVENTOS ---");
    Serial.println("  Deteccion de eventos DESHABILITADA (modo test)");
    Serial.println("  Este firmware es solo para probar el sensor IMU");
    Serial.println("----------------\n");

  } else if (cmd == "offsets") {
    Serial.println("\n// === OFFSETS PARA OTRO CODIGO ===");
    Serial.printf("// Copiar estas lineas al inicio de tu codigo\n");
    Serial.printf("// Gyro (deg/s):\n");
    Serial.printf("const float OFFSET_GX = %.6f;\n", offsetGx);
    Serial.printf("const float OFFSET_GY = %.6f;\n", offsetGy);
    Serial.printf("const float OFFSET_GZ = %.6f;\n", offsetGz);
    Serial.printf("// Accel (m/s2):\n");
    Serial.printf("const float OFFSET_AX = %.6f;\n", offsetAx);
    Serial.printf("const float OFFSET_AY = %.6f;\n", offsetAy);
    Serial.printf("const float OFFSET_AZ = %.6f;\n", offsetAz);
    Serial.printf("// Orientacion: %d\n", sensorOrientation);
    Serial.printf("const int SENSOR_ORIENTATION = %d;\n", sensorOrientation);
    Serial.printf("// Alpha:\n");
    Serial.printf("const float ALPHA = %.2f;\n", filterAlpha);
    Serial.println("// =================================\n");

  } else if (cmd.startsWith("alpha")) {
    // alpha         → muestra valor actual
    // alpha 0.95    → cambia alpha (gyro=0.95, accel=0.05)
    int spaceIdx1 = cmd.indexOf(' ');
    if (spaceIdx1 < 0) {
      Serial.printf("# Alpha actual: %.3f (gyro) / %.3f (accel)\n", filterAlpha, 1.0f - filterAlpha);
      Serial.println("# Uso: alpha <valor>");
      Serial.println("# Rango: 0.0 a 1.0 (mayor = mas gyro, menor = mas accel)");
    } else {
      float newAlpha = cmd.substring(spaceIdx1 + 1).toFloat();
      if (newAlpha < 0.0f || newAlpha > 1.0f) {
        Serial.println("# ERROR: Alpha debe estar entre 0.0 y 1.0");
      } else {
        filterAlpha = newAlpha;
        fuser.init(sampleRateHz, filterAlpha, filterAlpha);
        Serial.printf("# Alpha actualizado: %.3f (gyro) / %.3f (accel)\n", filterAlpha, 1.0f - filterAlpha);
      }
    }

  } else if (cmd.startsWith("beta")) {
    int spaceIdx = cmd.indexOf(' ');
    if (spaceIdx < 0) {
      Serial.printf("# Madgwick beta actual: %.4f\n", madgwickFilter.getBeta());
      Serial.println("# Uso: beta <0.0-1.0> (menor = mas suave, mayor = mas rapido)");
    } else {
      float newBeta = cmd.substring(spaceIdx + 1).toFloat();
      if (newBeta < 0.0f || newBeta > 1.0f) {
        Serial.println("# ERROR: Beta debe estar entre 0.0 y 1.0");
      } else {
        madgwickFilter.setBeta(newBeta);
        Serial.printf("# Madgwick beta actualizado: %.4f\n", newBeta);
      }
    }

  } else if (cmd.startsWith("hz")) {
    // hz         → muestra valor actual
    // hz 50      → cambia sample rate
    int spaceIdx = cmd.indexOf(' ');
    if (spaceIdx < 0) {
      Serial.printf("# Sample rate actual: %u Hz (intervalo: %lu us)\n", sampleRateHz, sampleIntervalUs);
      Serial.println("# Uso: hz <10-500>");
    } else {
      int newHz = cmd.substring(spaceIdx + 1).toInt();
      if (newHz < 10 || newHz > 500) {
        Serial.println("# ERROR: Hz debe estar entre 10 y 500");
      } else {
        sampleRateHz = newHz;
        sampleIntervalUs = 1000000UL / sampleRateHz;
        fuser.init(sampleRateHz, filterAlpha, filterAlpha);
        Serial.printf("# Sample rate actualizado: %u Hz (intervalo: %lu us)\n", sampleRateHz, sampleIntervalUs);
      }
    }

  } else if (cmd == "ntp") {
    outputMode = MODE_NTP;
    streaming = true;
    lastPlotMs = millis();
    startMs = millis();
    Serial.println("# MODO: NTP (CSV con hora ISO @100Hz, 28 columnas + 1 timestamp)");
    Serial.println("# Orden columnas (,):");
    Serial.println("#  1      Timestamp (ISO YYYY-MM-DDTHH:MM:SS)");
    Serial.println("#  2-4    Accel RAW (m/s2): axRaw, ayRaw, azRaw");
    Serial.println("#  5-7    Accel FILTRADO (m/s2): ax, ay, az");
    Serial.println("#  8-10   Accel s/gravedad COMP (m/s2): comp_linX, comp_linY, comp_linZ");
    Serial.println("# 11-13   Gravedad COMP (m/s2): comp_gravX, comp_gravY, comp_gravZ");
    Serial.println("# 14-16   Accel s/gravedad MADG (m/s2): madg_linX, madg_linY, madg_linZ");
    Serial.println("# 17-19   Gravedad MADG (m/s2): madg_gravX, madg_gravY, madg_gravZ");
    Serial.println("# 20-22   Gyro RAW (deg/s): gxRaw, gyRaw, gzRaw");
    Serial.println("# 23-25   Gyro FILTRADO (deg/s): gx, gy, gz");
    Serial.println("# 26-27   Pitch/Roll COMP (deg): pitch, roll");
    Serial.println("# 28-29   Pitch/Roll MADG (deg): madg_pitch, madg_roll");

  } else if (cmd == "help") {
    Serial.println("\n--- COMANDOS ---");
    Serial.println("  run      - Inicia streaming");
    Serial.println("  pause    - Pausa streaming");
    Serial.println("  console  - Modo consola (calibrado)");
    Serial.println("  raw      - Modo consola (sin calibrar)");
    Serial.println("  linear   - Aceleracion sin gravedad");
    Serial.println("  plot     - Modo grafica (CSV)");
    Serial.println("  ntp      - Modo NTP (CSV con hora ISO @100Hz)");
    Serial.println("  cal      - Recalibrar sensor (10s)");
    Serial.println("  orient   - Detectar orientacion del sensor");
    Serial.println("  alpha    - Cambiar alpha del filtro complementario");
    Serial.println("  beta     - Cambiar beta del filtro Madgwick");
    Serial.println("  hz       - Cambiar frecuencia de muestreo");
    Serial.println("  events   - Ver config de deteccion (deshabilitado)");
    Serial.println("  offsets  - Exportar offsets para otro codigo");
    Serial.println("  status   - Ver configuracion");
    Serial.println("  help     - Esta ayuda");
    Serial.println("----------------\n");

  } else if (cmd.length() > 0) {
    Serial.println("# Comando no valido. Envia 'help'");
  }
}

// --- WiFi/NTP ---

void connectWiFi() {
  Serial.print("# Conectando WiFi: ");
  Serial.println(WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  uint32_t startAttempt = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - startAttempt < 10000) {
    delay(500);
    Serial.print(".");
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println(" OK");
    configTime(GMT_OFFSET_SEC, DST_OFFSET_SEC, NTP_SERVER);
    ntpSynced = true;
    Serial.println("# NTP sincronizado (UTC-5)");
  } else {
    Serial.println(" FAIL");
    Serial.println("# Sin WiFi - timestamps deshabilitados");
  }
}

String getNtpTime() {
  if (!ntpSynced) return "1970-01-01T00:00:00";
  time_t now = time(NULL);
  struct tm* t = localtime(&now);
  char buf[30];
  snprintf(buf, sizeof(buf), "%04d-%02d-%02dT%02d:%02d:%02d",
           t->tm_year + 1900, t->tm_mon + 1, t->tm_mday,
           t->tm_hour, t->tm_min, t->tm_sec);
  return String(buf);
}

// --- Setup ---

void setup() {
  Serial.begin(SERIAL_BAUD);
  delay(1000);

  connectWiFi();

  Wire.begin(I2C_SDA, I2C_SCL);
  Wire.setClock(400000);

  Serial.println("\n# ======================================");
  Serial.println("# SENTINELDRIVE - IMU + SimpleFusion");
  Serial.println("# ======================================");
  Serial.println("# Envia 'help' para ver comandos");

  if (!setupMPU()) {
    Serial.println("# ERROR CRITICO: MPU6050 no responde en 0x68");
    while (true) delay(1000);
  }

  fuser.init(sampleRateHz, filterAlpha, filterAlpha);

  madgwickFilter.begin(sampleRateHz);
  madgwickFilter.setBeta(0.04f);

  // Offsets hardcodeados, sin calibrar
  Serial.println("# Offsets cargados:");
  Serial.printf("  Gyro: %.6f %.6f %.6f deg/s\n", offsetGx, offsetGy, offsetGz);
  Serial.printf("  Acc:  %.6f %.6f %.6f m/s2\n", offsetAx, offsetAy, offsetAz);
  Serial.printf("  Orientacion: %d\n", sensorOrientation);
  Serial.println("# Usa 'cal' para recalibrar si es necesario");

  Serial.println("# Sistema listo. Envia 'run' para comenzar.\n");
  streaming = false;
}

// --- Loop ---

void loop() {
  handleSerialCommand();
  if (!streaming) return;

  uint32_t nowUs = micros();
  if ((int32_t)(nowUs - nextSampleUs) < 0) return;

  if (nowUs - nextSampleUs > sampleIntervalUs) {
    nextSampleUs = nowUs;
  }
  nextSampleUs += sampleIntervalUs;

  int16_t axRaw, ayRaw, azRaw, tempRaw, gxRaw, gyRaw, gzRaw;
  if (!readMPUAll(axRaw, ayRaw, azRaw, tempRaw, gxRaw, gyRaw, gzRaw)) {
    errorCount++;
    return;
  }

  sampleCount++;

  lastAxRaw = axRaw;
  lastAyRaw = ayRaw;
  lastAzRaw = azRaw;
  lastGxRaw = gxRaw;
  lastGyRaw = gyRaw;
  lastGzRaw = gzRaw;
  lastTempRaw = tempRaw;

  float ax = (axRaw / 16384.0f * 9.80665f) - offsetAx;
  float ay = (ayRaw / 16384.0f * 9.80665f) - offsetAy;
  float az = (azRaw / 16384.0f * 9.80665f) - offsetAz;

  float gx = ((gxRaw / 131.0f) - offsetGx) * DEG2RAD;
  float gy = ((gyRaw / 131.0f) - offsetGy) * DEG2RAD;
  float gz = ((gzRaw / 131.0f) - offsetGz) * DEG2RAD;

  ThreeAxis accel = { ax, ay, az };
  ThreeAxis gyro  = { gx, gy, gz };
  FusedAngles angles;

  fuser.getFilteredAngles(accel, gyro, &angles, UNIT_DEGREES);

  lastPitch = angles.pitch;
  lastRoll  = angles.roll;

  // --- Calcular aceleracion lineal COMPLEMENTARY (misma logica que V2) ---
  const float G = 9.81f;
  float pitchRad = lastPitch * DEG2RAD;
  float rollRad  = lastRoll  * DEG2RAD;

  comp_grav_x = -G * sin(pitchRad);
  comp_grav_y =  G * sin(rollRad) * cos(pitchRad);
  comp_grav_z =  G * cos(rollRad) * cos(pitchRad);

  comp_lin_x = ax - comp_grav_x;
  comp_lin_y = ay - comp_grav_y;
  comp_lin_z = az - comp_grav_z;

  // --- MADGWICK: actualizar filtro y extraer aceleracion lineal ---
  float gx_deg = (gxRaw / 131.0f) - offsetGx;
  float gy_deg = (gyRaw / 131.0f) - offsetGy;
  float gz_deg = (gzRaw / 131.0f) - offsetGz;

  madgwickFilter.updateIMU(gx_deg, gy_deg, gz_deg, ax, ay, az);
  madgwickFilter.getQuaternion(&madg_q0, &madg_q1, &madg_q2, &madg_q3);

  madg_gravity_x = G * 2.0f * (madg_q1 * madg_q3 - madg_q0 * madg_q2);
  madg_gravity_y = G * 2.0f * (madg_q0 * madg_q1 + madg_q2 * madg_q3);
  madg_gravity_z = G * (madg_q0 * madg_q0 - madg_q1 * madg_q1 - madg_q2 * madg_q2 + madg_q3 * madg_q3);

  madg_grav_x = madg_gravity_x;
  madg_grav_y = madg_gravity_y;
  madg_grav_z = madg_gravity_z;

  madg_lin_x = ax - madg_gravity_x;
  madg_lin_y = ay - madg_gravity_y;
  madg_lin_z = az - madg_gravity_z;

  // Pitch/Roll de Madgwick (desde cuaternion)
  madg_pitch = asinf(-2.0f * (madg_q1 * madg_q3 - madg_q0 * madg_q2)) * RAD2DEG;
  madg_roll  = atan2f(2.0f * (madg_q0 * madg_q1 + madg_q2 * madg_q3),
                      madg_q0 * madg_q0 - madg_q1 * madg_q1 - madg_q2 * madg_q2 + madg_q3 * madg_q3) * RAD2DEG;

  // --- MODO CONSOLE: cada 1 segundo ---
  if (outputMode == MODE_CONSOLE) {
    uint32_t nowMs = millis();
    if ((nowMs - lastConsoleMs) >= 1000) {
      lastConsoleMs = nowMs;
      Serial.printf("PITCH:%7.2f  ROLL:%7.2f  |  MADG_PITCH:%7.2f MADG_ROLL:%7.2f  |  GYRO:%7.3f %7.3f %7.3f  |  ACC:%6.3f %6.3f %6.3f\n",
                    lastPitch, lastRoll,
                    madg_pitch, madg_roll,
                    gx * RAD2DEG, gy * RAD2DEG, gz * RAD2DEG,
                    ax, ay, az);
    }
  }

  // --- MODO RAW: cada 1 segundo ---
  if (outputMode == MODE_RAW) {
    uint32_t nowMs = millis();
    if ((nowMs - lastConsoleMs) >= 1000) {
      lastConsoleMs = nowMs;
      float tempC = lastTempRaw / 340.0f + 36.53f;
      float rawGx = lastGxRaw / 131.0f;
      float rawGy = lastGyRaw / 131.0f;
      float rawGz = lastGzRaw / 131.0f;
      float rawAx = lastAxRaw / 16384.0f * 9.80665f;
      float rawAy = lastAyRaw / 16384.0f * 9.80665f;
      float rawAz = lastAzRaw / 16384.0f * 9.80665f;
      Serial.printf("RAW gx:%7.2f gy:%7.2f gz:%7.2f deg/s  |  ax:%6.2f ay:%6.2f az:%6.2f m/s2  |  T:%5.1fC\n",
                    rawGx, rawGy, rawGz,
                    rawAx, rawAy, rawAz,
                    tempC);
    }
  }

  // --- MODO LINEAR: aceleracion sin gravedad, cada 1 segundo ---
  if (outputMode == MODE_LINEAR) {
    uint32_t nowMs = millis();
    if ((nowMs - lastConsoleMs) >= 1000) {
      lastConsoleMs = nowMs;
      Serial.printf("PITCH:%6.2f ROLL:%6.2f | COMP_LIN:%7.3f %7.3f %7.3f | MADG_LIN:%7.3f %7.3f %7.3f | ax:%6.3f ay:%6.3f az:%6.3f\n",
                    lastPitch, lastRoll,
                    comp_lin_x, comp_lin_y, comp_lin_z,
                    madg_lin_x, madg_lin_y, madg_lin_z,
                    ax, ay, az);
    }
  }

  // --- MODO PLOT: CSV a 20Hz ---
  // 28 columnas: rawAcc, filtAcc, compLin, compGrav, madgLin, madgGrav, rawGyro, filtGyro, pitchRoll
  if (outputMode == MODE_PLOT) {
    uint32_t nowMs = millis();
    if ((nowMs - lastPlotMs) >= 50) {
      lastPlotMs = nowMs;
      float rawAx = lastAxRaw / 16384.0f * 9.80665f;
      float rawAy = lastAyRaw / 16384.0f * 9.80665f;
      float rawAz = lastAzRaw / 16384.0f * 9.80665f;
      float rawGx = lastGxRaw / 131.0f;
      float rawGy = lastGyRaw / 131.0f;
      float rawGz = lastGzRaw / 131.0f;
      Serial.printf("%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f\n",
                    rawAx, rawAy, rawAz,
                    ax, ay, az,
                    comp_lin_x, comp_lin_y, comp_lin_z,
                    comp_grav_x, comp_grav_y, comp_grav_z,
                    madg_lin_x, madg_lin_y, madg_lin_z,
                    madg_grav_x, madg_grav_y, madg_grav_z,
                    rawGx, rawGy, rawGz,
                    gx * RAD2DEG, gy * RAD2DEG, gz * RAD2DEG,
                    lastPitch, lastRoll,
                    madg_pitch, madg_roll);
    }
  }

  // --- MODO NTP: CSV con hora a 100Hz (28 columnas + timestamp) ---
  if (outputMode == MODE_NTP) {
    uint32_t nowMs = millis();
    if ((nowMs - lastPlotMs) >= 10) {
      lastPlotMs = nowMs;
      String ntpTime = getNtpTime();
      float rawAx = lastAxRaw / 16384.0f * 9.80665f;
      float rawAy = lastAyRaw / 16384.0f * 9.80665f;
      float rawAz = lastAzRaw / 16384.0f * 9.80665f;
      float rawGx = lastGxRaw / 131.0f;
      float rawGy = lastGyRaw / 131.0f;
      float rawGz = lastGzRaw / 131.0f;
      Serial.printf("%s,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f\n",
                    ntpTime.c_str(),
                    rawAx, rawAy, rawAz,
                    ax, ay, az,
                    comp_lin_x, comp_lin_y, comp_lin_z,
                    comp_grav_x, comp_grav_y, comp_grav_z,
                    madg_lin_x, madg_lin_y, madg_lin_z,
                    madg_grav_x, madg_grav_y, madg_grav_z,
                    rawGx, rawGy, rawGz,
                    gx * RAD2DEG, gy * RAD2DEG, gz * RAD2DEG,
                    lastPitch, lastRoll,
                    madg_pitch, madg_roll);
    }
  }
}
