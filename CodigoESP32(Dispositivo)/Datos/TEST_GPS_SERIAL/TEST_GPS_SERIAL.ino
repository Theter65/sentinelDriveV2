/*
 * SENTINELDRIVE - Prueba de GPS por consola
 *
 * Comandos Serial:
 *   run      - Inicia streaming GPS
 *   pause    - Pausa streaming
 *   console  - Modo consola (datos parseados cada 1s)
 *   raw      - Modo crudo (tramas NMEA completas)
 *   diag     - Diagnostico inmediato del modulo
 *   plot     - Modo grafica (CSV para Serial Plotter)
 *   ntp      - Modo NTP (CSV con hora @1Hz)
 *   sats     - Monitoreo de satelites en tiempo real
 *   warm     - Warm start con posicion guardada
 *   cold     - Cold start (borrar memoria GPS)
 *   save     - Guardar posicion actual en EEPROM
 *   saved    - Ver posicion guardada
 *   clear    - Borrar posicion de EEPROM
 *   battery  - Ver estado de bateria (hot/warm/cold start)
 *   speed     - Configurar deteccion de exceso de velocidad
 *   status   - Muestra configuracion actual
 *   help     - Lista de comandos
 *
 * Precision estimada: precision_m = HDOP x 2.5
 *
 * EEPROM: Guarda ultima posicion para warm start rapido (~15-30s vs 2-5min)
 */

#include <TinyGPS++.h>
#include <EEPROM.h>
#include <WiFi.h>
#include <time.h>

#define GPS_RX 16
#define GPS_TX 17

const uint32_t SERIAL_BAUD = 115200;
const uint32_t GPS_BAUD = 9600;
const uint32_t PRINT_INTERVAL_MS = 1000;
const uint32_t NO_DATA_WARN_MS = 3000;
const float HDOP_TO_METERS = 2.5f;

// --- WiFi/NTP ---
const char* WIFI_SSID = "Sent";
const char* WIFI_PASS = "12345678";
const char* NTP_SERVER = "pool.ntp.org";
const long GMT_OFFSET_SEC = -5 * 3600;  // Ecuador UTC-5
const int DST_OFFSET_SEC = 0;
bool ntpSynced = false;

TinyGPSPlus gps;
HardwareSerial SerialGPS(2);

// --- Estado ---
enum OutputMode { MODE_CONSOLE, MODE_RAW, MODE_PLOT, MODE_SATS, MODE_NTP };
OutputMode outputMode = MODE_CONSOLE;
bool streaming = false;

// --- Timers ---
uint32_t lastPrintMs = 0;
uint32_t lastDiagMs = 0;
uint32_t lastSatsMs = 0;

// --- Estadisticas ---
uint32_t startMs = 0;
uint32_t totalCharsReceived = 0;
uint32_t totalPassedChecksum = 0;
uint32_t totalFailedChecksum = 0;
uint32_t gpsCharsThisSecond = 0;
uint32_t lastGpsCharMs = 0;
uint32_t lastTotalChars = 0;

// --- Tracking de satelites ---
int maxSatsSeen = 0;
float minHdopSeen = 99.99f;
float maxSpeedSeen = 0.0f;
uint32_t firstFixMs = 0;
bool hadFix = false;

// --- Monitoreo de bateria backup ---
uint32_t bootMs = 0;
uint32_t firstFixAfterBootMs = 0;
bool batteryStatusChecked = false;
enum StartType { START_UNKNOWN, START_HOT, START_WARM, START_COLD };
StartType lastStartType = START_UNKNOWN;
const char* startTypeNames[] = {"DESCONOCIDO", "HOT START", "WARM START", "COLD START"};

// --- Deteccion exceso de velocidad ---
const float SPEED_THRESHOLD_KMH = 90.0f;       // Umbral km/h
const uint32_t SPEED_WINDOW_MS = 5000;         // Ventana 5 segundos
const uint32_t SPEED_COOLDOWN_MS = 30000;      // Cooldown 30 segundos
uint32_t speedWindowStartMs = 0;                // Inicio de ventana actual
bool speedWindowActive = false;                 // Ventana activa
uint32_t lastSpeedEventMs = 0;                  // Ultimo evento enviado
uint32_t speedEventCount = 0;                   // Contador de eventos

// --- EEPROM para warm start ---
#define EEPROM_SIZE 128
#define EEPROM_MAGIC 0xA5  // Magico para saber si hay datos validos

struct GpsPosition {
  uint8_t magic;        // 0xA5 = datos validos
  double lat;           // Latitud
  double lon;           // Longitud
  float alt;            // Altitud en metros
  float speed;          // Velocidad en km/h
  float course;         // Curso en grados
  uint16_t year;        // Ano UTC
  uint8_t month;        // Mes UTC
  uint8_t day;          // Dia UTC
  uint8_t hour;         // Hora UTC
  uint8_t minute;       // Minuto UTC
  uint8_t second;       // Segundo UTC
  uint32_t savedAtMs;   // millis() cuando se guardo
  uint32_t saveCount;   // Cuantas veces se ha guardado
  uint8_t satsAtSave;   // Satelites visibles al guardar
  uint8_t hdopX10;      // HDOP x 10 (para guardar como uint8)
};

GpsPosition savedPos;

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
  if (!ntpSynced) return "00:00:00";
  time_t now = time(NULL);
  struct tm* t = localtime(&now);
  char buf[16];
  snprintf(buf, sizeof(buf), "%02d:%02d:%02d", t->tm_hour, t->tm_min, t->tm_sec);
  return String(buf);
}

float estimatedAccuracyMeters() {
  if (!gps.hdop.isValid()) return -1.0f;
  return gps.hdop.hdop() * HDOP_TO_METERS;
}

// --- Funciones EEPROM ---

void loadSavedPosition() {
  EEPROM.get(0, savedPos);
  if (savedPos.magic == EEPROM_MAGIC) {
    Serial.println("[EEPROM] Posicion guardada encontrada:");
    Serial.printf("  Lat: %.7f, Lon: %.7f\n", savedPos.lat, savedPos.lon);
    Serial.printf("  Alt: %.1f m, Speed: %.1f km/h, Course: %.1f deg\n",
                  savedPos.alt, savedPos.speed, savedPos.course);
    Serial.printf("  Sats: %d, HDOP: %.1f\n",
                  savedPos.satsAtSave, savedPos.hdopX10 / 10.0f);
    Serial.printf("  Fecha: %04d-%02d-%02d %02d:%02d:%02d UTC\n",
                  savedPos.year, savedPos.month, savedPos.day,
                  savedPos.hour, savedPos.minute, savedPos.second);
    uint32_t ageHrs = (millis() - savedPos.savedAtMs) / 3600000;
    Serial.printf("  Guardada hace: ~%lu horas\n", ageHrs);
    Serial.printf("  Guardada %lu veces\n", savedPos.saveCount);
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

  EEPROM.put(0, savedPos);
  EEPROM.commit();

  Serial.println("[EEPROM] Posicion guardada:");
  Serial.printf("  Lat: %.7f, Lon: %.7f\n", savedPos.lat, savedPos.lon);
  Serial.printf("  Alt: %.1f m, Speed: %.1f km/h, Course: %.1f deg\n",
                savedPos.alt, savedPos.speed, savedPos.course);
  Serial.printf("  Sats: %d, HDOP: %.1f\n",
                savedPos.satsAtSave, savedPos.hdopX10 / 10.0f);
  Serial.printf("  Fecha: %04d-%02d-%02d %02d:%02d:%02d UTC\n",
                savedPos.year, savedPos.month, savedPos.day,
                savedPos.hour, savedPos.minute, savedPos.second);
  Serial.printf("  Guardada %lu veces\n", savedPos.saveCount);
}

void clearSavedPosition() {
  savedPos.magic = 0;
  EEPROM.put(0, savedPos);
  EEPROM.commit();
  Serial.println("[EEPROM] Posicion borrada");
}

// --- Monitoreo de bateria ---

void detectStartType() {
  if (firstFixAfterBootMs > 0) return;  // Ya detectado

  uint32_t fixTimeMs = millis() - bootMs;

  if (fixTimeMs < 5000) {
    lastStartType = START_HOT;
    Serial.println("[BATERIA] HOT START detectado (< 5s) - Bateria OK, ephemeris valida");
  } else if (fixTimeMs < 30000) {
    lastStartType = START_WARM;
    Serial.println("[BATERIA] WARM START detectado (< 30s) - Bateria OK, posicion recordada");
  } else if (fixTimeMs < 120000) {
    lastStartType = START_COLD;
    Serial.println("[BATERIA] COLD START detectado (> 30s) - Bateria baja o sin datos");
  } else {
    lastStartType = START_COLD;
    Serial.println("[BATERIA] COLD START LENTO (> 2min) - Posible bateria agotada");
  }

  firstFixAfterBootMs = millis();
}

void printBatteryStatus() {
  Serial.println("\n========== BATERIA BACKUP ==========");
  Serial.println("  Modulo: GY-GPS6MV2 (NEO-6M)");
  Serial.println("  Bateria: Celda litio recargable (ML1220)");
  Serial.println("  Funcion: Mantiene RTC + ephemeris GPS");
  Serial.println("  Duracion: ~4 horas sin alimentacion");
  Serial.println("  Carga: Automatica cuando modulo encendido");
  Serial.println("------------------------------------");

  Serial.println("  --- Estado Actual ---");
  Serial.printf("  Uptime:          %lu ms\n", millis() - bootMs);

  if (hadFix) {
    Serial.printf("  Tiempo al fix:   %lu ms\n", firstFixAfterBootMs);
    Serial.printf("  Ultimo start:    %s\n", startTypeNames[lastStartType]);

    if (lastStartType == START_HOT) {
      Serial.println("  Estado bateria:  EXCELENTE");
      Serial.println("  → Bateria cargada, ephemeris valida");
      Serial.println("  → Hot start funcionando correctamente");
    } else if (lastStartType == START_WARM) {
      Serial.println("  Estado bateria:  BUENA");
      Serial.println("  → Bateria mantiene posicion, pero ephemeris expiro");
      Serial.println("  → Warm start, busca satelites rapido");
    } else {
      Serial.println("  Estado bateria:  REGULAR/MALA");
      Serial.println("  → Bateria no retuvo datos o se agoto");
      Serial.println("  → Cold start, tarda 2-5 minutos");
      Serial.println("  → Verificar: modulo con buen contacto, bateria no suelta");
    }
  } else {
    Serial.println("  Fix:             SIN FIX AUN");
    Serial.printf("  Tiempo esperando: %lu ms\n", millis() - bootMs);
    if (millis() - bootMs > 60000) {
      Serial.println("  Alerta:          > 1 min sin fix");
      Serial.println("  → Posible bateria backup agotada");
      Serial.println("  → O modulo sin vista al cielo");
    }
  }

  Serial.println("\n  --- EEPROM ---");
  if (savedPos.magic == EEPROM_MAGIC) {
    Serial.printf("  Posicion:       %.7f, %.7f\n", savedPos.lat, savedPos.lon);
    Serial.printf("  Altitud:        %.1f m\n", savedPos.alt);
    Serial.printf("  Velocidad:      %.1f km/h\n", savedPos.speed);
    Serial.printf("  Curso:          %.1f deg\n", savedPos.course);
    Serial.printf("  Sats al guardar:%d\n", savedPos.satsAtSave);
    Serial.printf("  HDOP al guardar:%.1f\n", savedPos.hdopX10 / 10.0f);
    uint32_t ageHrs = (millis() - savedPos.savedAtMs) / 3600000;
    Serial.printf("  Guardada hace:  ~%lu horas\n", ageHrs);
    Serial.printf("  Veces guardada: %lu\n", savedPos.saveCount);
    if (ageHrs < 4) {
      Serial.println("  Estado:         DENTRO DE VIDA UTIL");
    } else if (ageHrs < 24) {
      Serial.println("  Estado:         USABLE (menos preciso)");
    } else {
      Serial.println("  Estado:         ANTIGUA (puede fallar warm start)");
    }
  } else {
    Serial.println("  Posicion guardada: NO");
  }

  Serial.println("\n  --- Recomendaciones ---");
  Serial.println("  • Para HOT START: Apagar < 4 horas, bateria buena");
  Serial.println("  • Para WARM START: Apagar > 4 horas pero mantener bateria");
  Serial.println("  • Si siempre es COLD: Revisar soldadura bateria o reemplazar");
  Serial.println("  • EEPROM es respaldo si bateria falla");
  Serial.println("====================================\n");
}

void sendWarmStart() {
  if (savedPos.magic != EEPROM_MAGIC) {
    Serial.println("[GPS] No hay posicion guardada para warm start");
    Serial.println("[GPS] Usando cold start...");
    SerialGPS.println("$PMTK105*37");  // Cold start
    return;
  }

  // PMTK140: Warm start con posicion conocida
  // Formato: $PMTK140,lat,lon,alt*XX
  char cmd[80];
  snprintf(cmd, sizeof(cmd), "$PMTK140,%f,%f,%f",
           savedPos.lat, savedPos.lon, savedPos.alt);

  // Calcular checksum NMEA
  uint8_t checksum = 0;
  for (int i = 1; cmd[i] != '*' && cmd[i] != '\0'; i++) {
    checksum ^= cmd[i];
  }
  int len = strlen(cmd);
  snprintf(cmd + len, sizeof(cmd) - len, "*%02X\r\n", checksum);

  SerialGPS.println(cmd);

  // Enviar PMTK220: modo vehiculo (mas sensible a movimiento)
  SerialGPS.println("$PMTK220,1000*1F");  // 1Hz update

  Serial.printf("[GPS] Warm start con posicion: %.7f, %.7f, Alt: %.1f m\n",
                savedPos.lat, savedPos.lon, savedPos.alt);
  Serial.printf("[GPS] Speed: %.1f km/h, Course: %.1f deg\n",
                savedPos.speed, savedPos.course);
  Serial.printf("[GPS] Guardada %lu veces, Sats al guardar: %d\n",
                savedPos.saveCount, savedPos.satsAtSave);
  Serial.println("[GPS] Esperando fix... (15-30 segundos)");
}

void sendColdStart() {
  SerialGPS.println("$PMTK105*37");  // Cold start
  Serial.println("[GPS] Cold start enviado (borrar memoria GPS)");
  Serial.println("[GPS] Esperando fix... (2-5 minutos)");
}

void printSavedPosition() {
  if (savedPos.magic != EEPROM_MAGIC) {
    Serial.println("\n[EEPROM] Sin posicion guardada");
    Serial.println("  Usa 'save' cuando tengas fix para guardar");
    return;
  }

  Serial.println("\n========== POSICION GUARDADA ==========");
  Serial.printf("  Lat:         %.7f\n", savedPos.lat);
  Serial.printf("  Lon:         %.7f\n", savedPos.lon);
  Serial.printf("  Altitud:     %.1f m\n", savedPos.alt);
  Serial.printf("  Velocidad:   %.1f km/h\n", savedPos.speed);
  Serial.printf("  Curso:       %.1f deg\n", savedPos.course);
  Serial.printf("  Satelites:   %d\n", savedPos.satsAtSave);
  Serial.printf("  HDOP:        %.1f\n", savedPos.hdopX10 / 10.0f);
  Serial.printf("  Fecha UTC:   %04d-%02d-%02d\n",
                savedPos.year, savedPos.month, savedPos.day);
  Serial.printf("  Hora UTC:    %02d:%02d:%02d\n",
                savedPos.hour, savedPos.minute, savedPos.second);
  uint32_t ageHrs = (millis() - savedPos.savedAtMs) / 3600000;
  Serial.printf("  Guardada:    ~%lu horas atras\n", ageHrs);
  Serial.printf("  Veces guard: %lu\n", savedPos.saveCount);
  Serial.println("========================================\n");
}

// --- Deteccion exceso de velocidad ---

void checkSpeeding(float speedKmh) {
  uint32_t nowMs = millis();
  bool isOver = speedKmh > SPEED_THRESHOLD_KMH;

  if (isOver) {
    if (!speedWindowActive) {
      // Iniciar ventana
      speedWindowActive = true;
      speedWindowStartMs = nowMs;
      Serial.printf("[SPEED] Ventana iniciada: %.1f km/h > %.0f km/h\n",
                    speedKmh, SPEED_THRESHOLD_KMH);
    } else if (nowMs - speedWindowStartMs >= SPEED_WINDOW_MS) {
      // Ventana completa: TODOS los valores > 90 durante 5 segundos
      if ((nowMs - lastSpeedEventMs) > SPEED_COOLDOWN_MS) {
        speedEventCount++;
        lastSpeedEventMs = nowMs;
        speedWindowActive = false;
        Serial.printf("[SPEED] *** EVENTO EXCESO VELOCIDAD #%lu *** %.1f km/h (5s continuos)\n",
                      speedEventCount, speedKmh);
      } else {
        uint32_t cooldownLeft = SPEED_COOLDOWN_MS - (nowMs - lastSpeedEventMs);
        Serial.printf("[SPEED] Exceso detectado pero en cooldown (%lu ms restantes)\n",
                      cooldownLeft);
        speedWindowActive = false;
      }
    }
  } else {
    if (speedWindowActive) {
      Serial.printf("[SPEED] Ventana cancelada: %.1f km/h <= %.0f km/h\n",
                    speedKmh, SPEED_THRESHOLD_KMH);
    }
    speedWindowActive = false;
  }
}

void printSpeedConfig() {
  Serial.println("\n========== EXCESO VELOCIDAD ==========");
  Serial.printf("  Umbral:         %.0f km/h\n", SPEED_THRESHOLD_KMH);
  Serial.printf("  Ventana:        %lu ms (%.1f s)\n", SPEED_WINDOW_MS, SPEED_WINDOW_MS / 1000.0f);
  Serial.printf("  Cooldown:       %lu ms (%.1f s)\n", SPEED_COOLDOWN_MS, SPEED_COOLDOWN_MS / 1000.0f);
  Serial.printf("  Ventana activa: %s\n", speedWindowActive ? "SI" : "NO");
  if (speedWindowActive) {
    uint32_t elapsed = millis() - speedWindowStartMs;
    Serial.printf("  Tiempo ventana: %lu ms / %lu ms\n", elapsed, SPEED_WINDOW_MS);
  }
  Serial.printf("  Ultimo evento:  %lu ms atras\n",
    lastSpeedEventMs > 0 ? millis() - lastSpeedEventMs : 0);
  Serial.printf("  Total eventos:  %lu\n", speedEventCount);
  Serial.println("=======================================\n");
}

// --- Funciones de salida ---

void printConsole() {
  float accuracyM = estimatedAccuracyMeters();

  Serial.print("ms=");
  Serial.print(millis() - startMs);

  Serial.print(", sats=");
  int sats = gps.satellites.isValid() ? gps.satellites.value() : 0;
  Serial.print(sats);
  if (sats > maxSatsSeen) maxSatsSeen = sats;

  Serial.print(", valid=");
  Serial.print(gps.location.isValid() ? 1 : 0);

  Serial.print(", lat=");
  if (gps.location.isValid()) Serial.print(gps.location.lat(), 7);
  else Serial.print("---");

  Serial.print(", lon=");
  if (gps.location.isValid()) Serial.print(gps.location.lng(), 7);
  else Serial.print("---");

  Serial.print(", hdop=");
  float hdop = gps.hdop.isValid() ? gps.hdop.hdop() : 99.99;
  Serial.print(hdop, 2);
  if (hdop < minHdopSeen && hdop < 10.0f) minHdopSeen = hdop;

  Serial.print(", precision_m=");
  if (accuracyM >= 0.0f) Serial.print(accuracyM, 1);
  else Serial.print("---");

  Serial.print(", speed_kmh=");
  float speed = gps.speed.isValid() ? gps.speed.kmph() : 0.0f;
  Serial.print(speed, 1);
  if (speed > maxSpeedSeen) maxSpeedSeen = speed;

  Serial.print(", course=");
  if (gps.course.isValid()) Serial.print(gps.course.deg(), 1);
  else Serial.print("---");

  Serial.print(", date=");
  if (gps.date.isValid()) {
    Serial.printf("%04d-%02d-%02d", gps.date.year(), gps.date.month(), gps.date.day());
  } else {
    Serial.print("----");
  }

  Serial.print(", time=");
  if (gps.time.isValid()) {
    Serial.printf("%02d:%02d:%02d", gps.time.hour(), gps.time.minute(), gps.time.second());
  } else {
    Serial.print("--:--:--");
  }

  Serial.print(", chars=");
  Serial.print(gpsCharsThisSecond);

  Serial.print(", chk_ok=");
  Serial.print(totalPassedChecksum);

  Serial.print(", chk_err=");
  Serial.println(totalFailedChecksum);

  gpsCharsThisSecond = 0;
}

void printRaw() {
  while (SerialGPS.available() > 0) {
    char c = (char)SerialGPS.read();
    gps.encode(c);
    gpsCharsThisSecond++;
    lastGpsCharMs = millis();
    Serial.write(c);
  }
}

void printPlot() {
  // CSV para Serial Plotter: lat,lon,sats,hdop,speed,course
  float lat = gps.location.isValid() ? gps.location.lat() : 0.0f;
  float lon = gps.location.isValid() ? gps.location.lng() : 0.0f;
  int sats = gps.satellites.isValid() ? gps.satellites.value() : 0;
  float hdop = gps.hdop.isValid() ? gps.hdop.hdop() : 99.99f;
  float speed = gps.speed.isValid() ? gps.speed.kmph() : 0.0f;
  float course = gps.course.isValid() ? gps.course.deg() : 0.0f;

  Serial.printf("%.7f,%.7f,%d,%.2f,%.2f,%.2f\n", lat, lon, sats, hdop, speed, course);
}

void printSats() {
  int sats = gps.satellites.isValid() ? gps.satellites.value() : 0;
  float hdop = gps.hdop.isValid() ? gps.hdop.hdop() : 99.99f;
  bool valid = gps.location.isValid();
  uint32_t age = valid ? gps.location.age() : 0;

  Serial.print("sats=");
  Serial.print(sats);
  Serial.print(" | hdop=");
  Serial.print(hdop, 2);
  Serial.print(" | fix=");
  Serial.print(valid ? "SI" : "NO");
  Serial.print(" | age=");
  Serial.print(age);
  Serial.print("ms | max_sats=");
  Serial.print(maxSatsSeen);
  Serial.print(" | min_hdop=");
  Serial.print(minHdopSeen, 2);
  Serial.print(" | max_speed=");
  Serial.print(maxSpeedSeen, 1);
  Serial.print(" km/h");

  if (hadFix) {
    uint32_t fixAge = (millis() - firstFixMs) / 1000;
    Serial.printf(" | fix_since=%lus", fixAge);
  }

  Serial.println();
}

// --- Diagnostico ---

void printDiagnostics(const char* reason) {
  uint32_t nowMs = millis();
  uint32_t passed = gps.passedChecksum();
  uint32_t failed = gps.failedChecksum();
  uint32_t totalChars = gps.charsProcessed();
  uint32_t charsDelta = totalChars - lastTotalChars;

  Serial.println("\n========== DIAGNOSTICO ==========");
  Serial.printf("  Razon:           %s\n", reason);
  Serial.printf("  Uptime:          %lu ms\n", nowMs);
  Serial.printf("  GPS baud:        %lu\n", GPS_BAUD);
  Serial.printf("  Pins:            RX=%d TX=%d\n", GPS_RX, GPS_TX);

  Serial.println("\n  --- UART ---");
  Serial.printf("  Chars total:     %lu\n", totalChars);
  Serial.printf("  Chars ultimo s:  %lu\n", charsDelta);
  Serial.printf("  Passed checksum: %lu\n", passed);
  Serial.printf("  Failed checksum: %lu\n", failed);
  Serial.printf("  Ultimo char:     %lu ms atras\n",
    lastGpsCharMs == 0 ? nowMs : nowMs - lastGpsCharMs);

  Serial.println("\n  --- GPS ---");
  Serial.printf("  Location valid:  %s\n", gps.location.isValid() ? "SI" : "NO");
  Serial.printf("  Satelites:       %d\n", gps.satellites.isValid() ? gps.satellites.value() : 0);
  Serial.printf("  HDOP:            %.2f\n", gps.hdop.isValid() ? gps.hdop.hdop() : 99.99);
  Serial.printf("  Speed valid:     %s\n", gps.speed.isValid() ? "SI" : "NO");
  Serial.printf("  Date valid:      %s\n", gps.date.isValid() ? "SI" : "NO");
  Serial.printf("  Time valid:      %s\n", gps.time.isValid() ? "SI" : "NO");

  Serial.println("\n  --- RENDIMIENTO ---");
  Serial.printf("  Max satelites:   %d\n", maxSatsSeen);
  Serial.printf("  Min HDOP:        %.2f\n", minHdopSeen);
  Serial.printf("  Max velocidad:   %.1f km/h\n", maxSpeedSeen);
  if (hadFix) {
    Serial.printf("  Primer fix:      %lu ms\n", firstFixMs);
  } else {
    Serial.println("  Primer fix:      SIN FIX");
  }

  Serial.println("\n  --- DIAGNOSTICO ---");
  if (totalChars == 0) {
    Serial.println("  ⚠ No llegan bytes.");
    Serial.println("  → Revisar: alimentacion GPS, GND comun, RX/TX cruzados");
  } else if (passed == 0 && failed > 0) {
    Serial.println("  ⚠ Llegan bytes pero fallan checksums.");
    Serial.println("  → Revisar: baud rate o ruido en UART");
  } else if (charsDelta > 0 && charsDelta < 50) {
    Serial.println("  ⚠ Pocos bytes por segundo.");
    Serial.println("  → Posible: módulo en modo sleep o baud incorrecto");
  } else if (charsDelta >= 50 && !gps.location.isValid()) {
    Serial.println("  ℹ Datos llegan bien, pero sin fix.");
    Serial.println("  → Sacar al aire libre, esperar 2-5 minutos");
    Serial.println("  → Asegurar antena mirando al cielo");
  } else if (gps.location.isValid()) {
    Serial.println("  ✓ GPS funcionando correctamente!");
  } else {
    Serial.println("  ? Estado indeterminado");
  }

  Serial.println("==================================\n");

  lastTotalChars = totalChars;
}

// --- Comandos seriales ---

void handleSerialCommand() {
  if (!Serial.available()) return;

  String cmd = Serial.readStringUntil('\n');
  cmd.trim();
  cmd.toLowerCase();

  if (cmd == "run") {
    streaming = true;
    startMs = millis();
    lastPrintMs = millis();
    lastSatsMs = millis();
    gpsCharsThisSecond = 0;
    lastTotalChars = gps.charsProcessed();
    Serial.println("# RUN - Streaming GPS activado");

  } else if (cmd == "pause") {
    streaming = false;
    uint32_t elapsed = (millis() - startMs) / 1000;
    Serial.printf("# PAUSED - %lu segundos, %lu chars recibidos\n",
                  elapsed, gps.charsProcessed());

  } else if (cmd == "console") {
    outputMode = MODE_CONSOLE;
    streaming = true;
    startMs = millis();
    lastPrintMs = millis();
    Serial.println("# MODO: CONSOLE (datos parseados cada 1s)");
    Serial.println("# Formato: ms, sats, valid, lat, lon, hdop, precision_m, speed_kmh, course, date, time, chars, chk_ok, chk_err");

  } else if (cmd == "raw") {
    outputMode = MODE_RAW;
    streaming = true;
    Serial.println("# MODO: RAW (tramas NMEA crudas)");
    Serial.println("# Presiona pause para detener");

  } else if (cmd == "plot") {
    outputMode = MODE_PLOT;
    streaming = true;
    startMs = millis();
    lastPrintMs = millis();
    Serial.println("# MODO: PLOT (CSV @1Hz)");
    Serial.println("# Columnas: lat,lon,sats,hdop,speed,course");

  } else if (cmd == "sats") {
    outputMode = MODE_SATS;
    streaming = true;
    startMs = millis();
    lastSatsMs = millis();
    Serial.println("# MODO: SATS (monitoreo de satelites)");
    Serial.println("# Muestra: sats, hdop, fix, max_sats, min_hdop, max_speed");

  } else if (cmd == "diag") {
    streaming = false;
    printDiagnostics("manual");

  } else if (cmd == "warm") {
    streaming = false;
    sendWarmStart();

  } else if (cmd == "cold") {
    streaming = false;
    sendColdStart();

  } else if (cmd == "save") {
    savePositionToEEPROM();

  } else if (cmd == "saved") {
    streaming = false;
    printSavedPosition();

  } else if (cmd == "clear") {
    clearSavedPosition();

  } else if (cmd == "battery") {
    streaming = false;
    printBatteryStatus();

  } else if (cmd == "speed") {
    streaming = false;
    printSpeedConfig();

  } else if (cmd == "ntp") {
    outputMode = MODE_NTP;
    streaming = true;
    startMs = millis();
    lastPrintMs = millis();
    Serial.println("# MODO: NTP (CSV con hora @1Hz)");
    Serial.println("# Orden columnas:");
    Serial.println("#  1   Hora (HH:MM:SS)");
    Serial.println("#  2   Latitud (grados)");
    Serial.println("#  3   Longitud (grados)");
    Serial.println("#  4   Velocidad (km/h)");
    Serial.println("#  5   Precision (m)");

  } else if (cmd == "status") {
    const char* modeStr = "CONSOLE";
    if (outputMode == MODE_RAW) modeStr = "RAW";
    else if (outputMode == MODE_PLOT) modeStr = "PLOT";
    else if (outputMode == MODE_SATS) modeStr = "SATS";
    else if (outputMode == MODE_NTP) modeStr = "NTP";

    Serial.println("\n========== STATUS ==========");
    Serial.printf("  Baud GPS:        %lu\n", GPS_BAUD);
    Serial.printf("  Baud Serial:     %lu\n", SERIAL_BAUD);
    Serial.printf("  Pins:            RX=%d TX=%d\n", GPS_RX, GPS_TX);
    Serial.printf("  Modo:            %s\n", modeStr);
    Serial.printf("  Streaming:       %s\n", streaming ? "SI" : "NO");
    Serial.printf("  Uptime:          %lu ms\n", millis());
    Serial.printf("  Chars total:     %lu\n", gps.charsProcessed());
    Serial.printf("  Passed checksum: %lu\n", gps.passedChecksum());
    Serial.printf("  Failed checksum: %lu\n", gps.failedChecksum());
    Serial.printf("  Location valid:  %s\n", gps.location.isValid() ? "SI" : "NO");
    if (gps.location.isValid()) {
      Serial.printf("  Lat:             %.7f\n", gps.location.lat());
      Serial.printf("  Lon:             %.7f\n", gps.location.lng());
      Serial.printf("  Age:             %lu ms\n", gps.location.age());
    }
    Serial.printf("  Satelites:       %d\n", gps.satellites.isValid() ? gps.satellites.value() : 0);
    Serial.printf("  HDOP:            %.2f\n", gps.hdop.isValid() ? gps.hdop.hdop() : 99.99);
    Serial.printf("  Speed:           %.1f km/h\n", gps.speed.isValid() ? gps.speed.kmph() : 0.0f);
    Serial.printf("  Max satelites:   %d\n", maxSatsSeen);
    Serial.printf("  Min HDOP:        %.2f\n", minHdopSeen);
    Serial.printf("  Max velocidad:   %.1f km/h\n", maxSpeedSeen);
    Serial.printf("  Precision est.:  ");
    float acc = estimatedAccuracyMeters();
    if (acc >= 0) Serial.printf("%.1f m\n", acc);
    else Serial.println("---");
    Serial.printf("  EEPROM guardada: %s\n", savedPos.magic == EEPROM_MAGIC ? "SI" : "NO");
    if (savedPos.magic == EEPROM_MAGIC) {
      Serial.printf("  Guardada pos:    %.7f, %.7f\n", savedPos.lat, savedPos.lon);
      uint32_t ageHrs = (millis() - savedPos.savedAtMs) / 3600000;
      Serial.printf("  Guardada hace:   ~%lu horas\n", ageHrs);
    }
    Serial.println("===========================\n");

  } else if (cmd == "help") {
    Serial.println("\n========== COMANDOS ==========");
    Serial.println("  --- Control ---");
    Serial.println("  run      - Inicia streaming GPS");
    Serial.println("  pause    - Pausa streaming");
    Serial.println("  --- Modos de salida ---");
    Serial.println("  console  - Modo consola (datos parseados 1s)");
    Serial.println("  raw      - Modo crudo (NMEA completas)");
    Serial.println("  plot     - Modo grafica (CSV)");
    Serial.println("  ntp      - Modo NTP (CSV con hora @1Hz)");
    Serial.println("  sats     - Monitoreo de satelites");
    Serial.println("  --- GPS ---");
    Serial.println("  warm     - Warm start con posicion guardada");
    Serial.println("  cold     - Cold start (borrar memoria GPS)");
    Serial.println("  --- EEPROM ---");
    Serial.println("  save     - Guardar posicion actual");
    Serial.println("  saved    - Ver posicion guardada");
    Serial.println("  clear    - Borrar posicion de EEPROM");
    Serial.println("  --- Bateria ---");
    Serial.println("  battery  - Estado bateria backup + start type");
    Serial.println("  --- Velocidad ---");
    Serial.println("  speed    - Config deteccion exceso velocidad");
    Serial.println("  --- Info ---");
    Serial.println("  diag     - Diagnostico del modulo");
    Serial.println("  status   - Ver configuracion actual");
    Serial.println("  help     - Esta ayuda");
    Serial.println("==============================\n");

  } else if (cmd.length() > 0) {
    Serial.println("# Comando no valido. Envia 'help'");
  }
}

// --- Setup ---

void setup() {
  Serial.begin(SERIAL_BAUD);
  delay(1500);

  bootMs = millis();
  SerialGPS.begin(GPS_BAUD, SERIAL_8N1, GPS_RX, GPS_TX);

  // EEPROM
  EEPROM.begin(EEPROM_SIZE);

  // WiFi + NTP
  connectWiFi();

  Serial.println("\n========================================");
  Serial.println("    SENTINELDRIVE - TEST GPS");
  Serial.println("========================================");
  Serial.printf("  GPS:     RX=%d TX=%d @ %lu baud\n", GPS_RX, GPS_TX, GPS_BAUD);
  Serial.printf("  Serial:  @ %lu baud\n", SERIAL_BAUD);
  Serial.printf("  Precision: HDOP x %.1f metros\n", HDOP_TO_METERS);
  Serial.println("\n  Envia 'help' para ver comandos");
  Serial.println("  Envia 'run' para iniciar streaming");
  Serial.println("========================================\n");

  // Cargar posicion guardada y hacer warm start automatico
  loadSavedPosition();
  if (savedPos.magic == EEPROM_MAGIC) {
    Serial.println("[GPS] Enviando warm start automatico...");
    sendWarmStart();
  }

  printDiagnostics("boot");
}

// --- Loop ---

void loop() {
  handleSerialCommand();

  // Leer GPS siempre
  while (SerialGPS.available() > 0) {
    char c = (char)SerialGPS.read();
    gps.encode(c);
    gpsCharsThisSecond++;
    lastGpsCharMs = millis();
  }

  // Detectar primer fix
  if (!hadFix && gps.location.isValid()) {
    hadFix = true;
    firstFixMs = millis();
    detectStartType();  // Detectar tipo de start
    Serial.println("# ¡PRIMER FIX! GPS localizado");
    // Auto-guardar para warm start en proximo reinicio
    if (gps.date.isValid() && gps.time.isValid()) {
      savePositionToEEPROM();
      Serial.println("[AUTO] Posicion auto-guardada para warm start");
    }
  }

  // Deteccion exceso de velocidad (cada segundo, 1 Hz del GPS)
  if (gps.speed.isValid()) {
    static uint32_t lastSpeedCheckMs = 0;
    uint32_t nowMs = millis();
    if (nowMs - lastSpeedCheckMs >= 1000) {
      lastSpeedCheckMs = nowMs;
      checkSpeeding(gps.speed.kmph());
    }
  }

  // Warning si no hay datos
  uint32_t nowMs = millis();
  if (lastGpsCharMs == 0 && nowMs > NO_DATA_WARN_MS && nowMs - lastDiagMs > NO_DATA_WARN_MS) {
    lastDiagMs = nowMs;
    printDiagnostics("no_data");
  }

  // Salida segun modo
  if (streaming) {
    if (outputMode == MODE_CONSOLE) {
      if (nowMs - lastPrintMs >= PRINT_INTERVAL_MS) {
        lastPrintMs = nowMs;
        printConsole();
      }
    } else if (outputMode == MODE_RAW) {
      printRaw();
    } else if (outputMode == MODE_PLOT) {
      if (nowMs - lastPrintMs >= PRINT_INTERVAL_MS) {
        lastPrintMs = nowMs;
        printPlot();
      }
    } else if (outputMode == MODE_SATS) {
      if (nowMs - lastSatsMs >= 500) {  // Cada 500ms
        lastSatsMs = nowMs;
        printSats();
      }
    } else if (outputMode == MODE_NTP) {
      if (nowMs - lastPrintMs >= PRINT_INTERVAL_MS) {
        lastPrintMs = nowMs;
        double lat = gps.location.isValid() ? gps.location.lat() : 0.0;
        double lon = gps.location.isValid() ? gps.location.lng() : 0.0;
        float spd = gps.speed.isValid() ? gps.speed.kmph() : 0.0f;
        float prec = gps.hdop.isValid() ? gps.hdop.hdop() * HDOP_TO_METERS : 0.0f;
        String ntpTime = getNtpTime();
        // Formato google sheets: ; como delimitador, , como decimal
        String latStr = String(lat, 7); latStr.replace(".", ",");
        String lonStr = String(lon, 7); lonStr.replace(".", ",");
        String spdStr = String(spd, 2); spdStr.replace(".", ",");
        String precStr = String(prec, 2); precStr.replace(".", ",");
        Serial.printf("%s;%s;%s;%s;%s\n",
                      ntpTime.c_str(), latStr.c_str(), lonStr.c_str(),
                      spdStr.c_str(), precStr.c_str());
      }
    }
  }
}
