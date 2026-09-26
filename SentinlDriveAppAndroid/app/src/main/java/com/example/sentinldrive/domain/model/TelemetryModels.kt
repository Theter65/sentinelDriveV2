package com.example.sentinldrive.domain.model

data class MqttSettings(
    val host: String = "006b41188f8e4c48ad4936cbef2e695a.s1.eu.hivemq.cloud",
    val port: Int = 8883,
    val username: String = "",
    val password: String = "",
    val baseTopic: String = "flota/ecuador/buses",
    val busId: Int = 1,
    val gpsIntervalSeconds: Int = 10,
    val speedLimitKmh: Double = 90.0,
    val brakeThreshold: Double = -2.94,
    val curveThreshold: Double = 3.92,   // 0.4g
    val backgroundEnabled: Boolean = true,
    val eventsRequireSpeed: Boolean = false,
    val speedWindowSeconds: Double = 5.0,
    val brakeWindowSeconds: Double = 0.5,
    val curveWindowSeconds: Double = 3.0,
    val eventCooldownSeconds: Double = 30.0,
    val beta: Double = 0.04,
)

data class CalibrationData(
    val accelOffsetX: Double = 0.0,
    val accelOffsetY: Double = 0.0,
    val accelOffsetZ: Double = 0.0,
    val calibratedAtIso: String = "",
)

data class LocationSnapshot(
    val lat: Double? = null,
    val lon: Double? = null,
    val speedKmh: Double? = null,
    val accuracyMeters: Float? = null,
    val timestampMillis: Long = System.currentTimeMillis(),
)

data class SensorSnapshot(
    val accelX: Double = 0.0,
    val accelY: Double = 0.0,
    val accelZ: Double = 0.0,
    val gyroX: Double = 0.0,
    val gyroY: Double = 0.0,
    val gyroZ: Double = 0.0,
    val linX: Double = 0.0,
    val linY: Double = 0.0,
    val linZ: Double = 0.0,
    val pitchDeg: Double = 0.0,
    val rollDeg: Double = 0.0,
    val timestampMillis: Long = System.currentTimeMillis(),
    val betaUsed: Double = 0.04,
)

data class ManualEventInput(
    val eventName: String,
    val description: String? = null,
    val value: Double? = null,
    val unit: String? = null,
    val temperature: Double? = null,
    val accelX: Double? = null,
)

data class OutboundMessage(
    val topic: String,
    val qos: Int,
    val payloadJson: String,
    val type: String,
)

data class SavedTelemetryRecord(
    val id: Long,
    val topic: String,
    val qos: Int,
    val payloadJson: String,
    val busId: Int?,
    val messageType: String,
    val eventType: String?,
    val eventDetails: String?,
    val lat: Double?,
    val lon: Double?,
    val speedKmh: Double?,
    val createdAtMillis: Long,
    val sentAtMillis: Long?,
    val deliveryStatus: String,
)

data class TelemetryUiState(
    val mqttState: ConnectionState = ConnectionState.DISCONNECTED,
    val mqttError: String? = null,
    val internetAvailable: Boolean = false,
    val settings: MqttSettings = MqttSettings(),
    val isSending: Boolean = false,
    val location: LocationSnapshot = LocationSnapshot(),
    val locationError: String? = null,
    val sensor: SensorSnapshot = SensorSnapshot(),
    val sensorError: String? = null,
    val pendingCount: Int = 0,
    val savedTelemetryCount: Int = 0,
    val savedTelemetryEventCount: Int = 0,
    val savedTelemetryRecords: List<SavedTelemetryRecord> = emptyList(),
    val localSavingEnabled: Boolean = false,
    val isWaitingForLocation: Boolean = false,
    val lastGpsPayload: String = "",
    val lastEventPayload: String = "",
    val backgroundServiceRunning: Boolean = false,
    val imuLogging: Boolean = false,
    val gpsLogging: Boolean = false,
)

sealed class StartSendingResult {
    data object Started : StartSendingResult()
    data class Blocked(val reason: String) : StartSendingResult()
}
