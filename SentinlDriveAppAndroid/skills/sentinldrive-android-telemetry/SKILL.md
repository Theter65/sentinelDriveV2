---
name: sentinldrive-android-telemetry
description: Continuar el desarrollo de la app Android de SentinlDrive que reemplaza al simulador Python y publica telemetria por MQTT. Usar esta skill cuando se trabaje en compatibilidad de payloads con la web, conexion MQTT TLS, sensores/GPS, foreground service, cola offline y pruebas de integracion Android.
---

# SentinlDrive Android Telemetry

## Objetivo
- Mantener y evolucionar la app Android de `SentinlDrive` para enviar datos reales de celular (GPS, acelerometro y giroscopio) por MQTT a la web existente.
- Preservar compatibilidad con el contrato JSON y topicos que la web ya espera.
- No editar la app web, solo usarla como referencia de lectura.

## Flujo de Trabajo Recomendado
1. Leer primero el error real en `ERRORSENTINL.logcat` y ubicar stack trace exacto.
2. Confirmar el contrato de mensajes revisando la web en modo lectura.
3. Aplicar cambios solo en Android (`app/src/main/...`).
4. Compilar con `:app:assembleDebug` antes de cerrar cambios.
5. Validar en dispositivo fisico permisos, GPS, sensores, MQTT y envio offline.

## Contrato de Datos y Compatibilidad
- Topico base configurable: `flota/ecuador/buses`.
- GPS: `flota/ecuador/buses/{bus_id}/gps` con QoS 0.
- Eventos: `flota/ecuador/buses/{bus_id}/event` con QoS 1.
- Campos minimos GPS: `bus_id`, `type=gps`, `timestamp`, `lat`, `lon`, `speed_gps` (si existe).
- Campos minimos evento: `bus_id`, `type=event`, `event`, `timestamp`, `lat/lon` opcionales.
- Mantener eventos: `exceso_velocidad`, `frenado_brusco`, `curva_peligrosa`, `conduccion_agresiva`, `sobrecalentamiento`, `otros`.
- Mantener `speed_obd = speed_gps` en `exceso_velocidad` hasta integrar OBD-II real.

## Archivos Clave Android
- `MainActivity.kt`: navegacion de pantallas, permisos runtime, acciones UI.
- `ui/main/MainScreen.kt`: estado principal y controles de conexion/envio.
- `service/TelemetryForegroundService.kt`: ejecucion en segundo plano y notificacion.
- `data/mqtt/MqttManager.kt`: conectar, desconectar, publicar, estado y errores MQTT.
- `data/location/LocationProvider.kt`: flujo de ubicacion real y velocidad GPS.
- `data/sensors/SensorProvider.kt`: acelerometro/giroscopio y lecturas continuas.
- `domain/TelemetryRepository.kt`: orquestacion de envio, deteccion de eventos y cola offline.
- `data/offline/*`: Room para mensajes pendientes y reintentos.
- `data/settings/SettingsRepository.kt`: configuracion persistente (DataStore).
- `AndroidManifest.xml`: permisos, tipo de foreground service y declaracion del servicio.

## Referencias de Lectura (Web, solo lectura)
- `simulator.py`
- `app/mqtt/subscriber.py`
- `app/models/event.py`
- `app/models/location.py`


## Errores Criticos Ya Encontrados
- Android 14+/API 34+: crash al iniciar FGS por permisos de tipo de servicio (`FOREGROUND_SERVICE_*`).
- UI bajo barra de estado cuando no se manejan insets del top bar custom.
- Falla MQTT por configuracion incompleta o por reconexiones no controladas.

## Validaciones Obligatorias
- Verificar que la app no crashee al presionar `Iniciar envio`.
- Verificar estado MQTT y mensaje de error legible en UI.
- Verificar que sensores cambien de `0.00` al mover el dispositivo.
- Verificar que GPS entregue `lat/lon` en exterior con ubicacion activa.
- Verificar incremento de cola offline sin internet y reenvio al reconectar.

## Pendientes Tecnicos de Proximas Iteraciones
- Anadir indicadores explicitos de disponibilidad de sensor por hardware.
- Afinar deduplicacion/cooldown de eventos automaticos por ruta real.
- Mejorar telemetria de diagnostico (logs internos de GPS/MQTT).
- Preparar integracion OBD-II (RPM, temperatura motor, velocidad OBD real).

## Skills y Recursos Utiles
- Usar `skill-creator` para mantener esta skill actualizada.
- Usar `openai-docs` cuando se necesite confirmar cambios oficiales de Android/OpenAI.
- Consultar `ERRORSENTINL.logcat` como fuente principal de verdad para crashes reales.