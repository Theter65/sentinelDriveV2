package com.example.sentinldrive.data.payload

import com.example.sentinldrive.data.time.NtpTime
import com.example.sentinldrive.domain.model.CalibrationData
import com.example.sentinldrive.domain.model.LocationSnapshot
import com.example.sentinldrive.domain.model.ManualEventInput
import com.example.sentinldrive.domain.model.MqttSettings
import com.example.sentinldrive.domain.model.OutboundMessage
import org.json.JSONObject
import java.time.Instant
import java.time.LocalDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter

object PayloadFactory {

    private val timestampFormatter: DateTimeFormatter = DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss")

    private fun nowIso(): String {
        val nowMs = if (NtpTime.isSynced) NtpTime.nowMs() else System.currentTimeMillis()
        val ldt = LocalDateTime.ofInstant(
            Instant.ofEpochMilli(nowMs),
            ZoneId.systemDefault()
        )
        return ldt.format(timestampFormatter)
    }

    fun gpsTopic(settings: MqttSettings): String = "${settings.baseTopic.trimEnd('/')}/${settings.busId}/gps"

    fun eventTopic(settings: MqttSettings): String = "${settings.baseTopic.trimEnd('/')}/${settings.busId}/event"

    fun buildGpsMessage(settings: MqttSettings, location: LocationSnapshot): OutboundMessage? {
        val lat = location.lat ?: return null
        val lon = location.lon ?: return null

        val json = JSONObject()
            .put("bus_id", settings.busId)
            .put("type", "gps")
            .put("timestamp", nowIso())
            .put("lat", lat)
            .put("lon", lon)

        location.speedKmh?.let { json.put("speed", round2(it)) }

        return OutboundMessage(
            topic = gpsTopic(settings),
            qos = 0,
            payloadJson = json.toString(),
            type = "gps",
        )
    }

    fun buildOverspeedEvent(
        settings: MqttSettings,
        location: LocationSnapshot,
        speed: Double,
    ): OutboundMessage {
        val json = baseEventJson(settings, "exceso_velocidad", location.lat, location.lon)
            .put("value", round2(speed))
            .put("speed_limit", round2(settings.speedLimitKmh))
        return OutboundMessage(eventTopic(settings), 1, json.toString(), "event")
    }

    fun buildBrakeEvent(
        settings: MqttSettings,
        location: LocationSnapshot,
        peakValue: Double,
    ): OutboundMessage {
        val json = baseEventJson(settings, "frenado_brusco", location.lat, location.lon)
            .put("value", round2(peakValue))
        return OutboundMessage(eventTopic(settings), 1, json.toString(), "event")
    }

    fun buildCurveEvent(
        settings: MqttSettings,
        location: LocationSnapshot,
        peakValue: Double,
    ): OutboundMessage {
        val json = baseEventJson(settings, "curva_peligrosa", location.lat, location.lon)
            .put("value", round2(peakValue))
        return OutboundMessage(eventTopic(settings), 1, json.toString(), "event")
    }

    fun buildManualEvent(
        settings: MqttSettings,
        location: LocationSnapshot,
        calibration: CalibrationData,
        input: ManualEventInput,
    ): OutboundMessage {
        val json = baseEventJson(settings, input.eventName, location.lat, location.lon)

        when (input.eventName) {
            "conduccion_agresiva" -> {
                val accel = input.accelX ?: 0.0
                json.put("accel_x", round2(accel - calibration.accelOffsetX))
            }

            "sobrecalentamiento" -> {
                input.temperature?.let { json.put("temperature", round2(it)) }
            }

            "otros" -> {
                json.put("description", input.description ?: "")
                input.value?.let { json.put("value", round2(it)) }
                if (!input.unit.isNullOrBlank()) {
                    json.put("unit", input.unit)
                }
            }
        }

        return OutboundMessage(eventTopic(settings), 1, json.toString(), "event")
    }

    private fun baseEventJson(
        settings: MqttSettings,
        eventName: String,
        lat: Double?,
        lon: Double?,
    ): JSONObject {
        val json = JSONObject()
            .put("bus_id", settings.busId)
            .put("type", "event")
            .put("event", eventName)
            .put("timestamp", nowIso())

        lat?.let { json.put("lat", it) }
        lon?.let { json.put("lon", it) }
        return json
    }

    private fun round2(value: Double): Double = kotlin.math.round(value * 100.0) / 100.0
}
