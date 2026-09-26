package com.example.sentinldrive.data.offline

import com.example.sentinldrive.domain.model.OutboundMessage
import com.example.sentinldrive.domain.model.SavedTelemetryRecord
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import org.json.JSONObject

class SavedTelemetryRepository(private val dao: SavedTelemetryDao) {

    fun countFlow(): Flow<Int> = dao.countFlow()

    fun eventCountFlow(): Flow<Int> = dao.eventCountFlow()

    fun recentFlow(limit: Int = 100): Flow<List<SavedTelemetryRecord>> =
        dao.recentFlow(limit).map { rows ->
            rows.map { row -> row.toRecord() }
        }

    suspend fun getAll(): List<SavedTelemetryRecord> = dao.getAll().map { row -> row.toRecord() }

    suspend fun save(message: OutboundMessage): Long {
        val columns = message.toSavedColumns()
        return dao.insert(
            SavedTelemetryEntity(
                topic = message.topic,
                qos = message.qos,
                payloadJson = message.payloadJson,
                busId = columns.busId,
                messageType = message.type,
                eventType = columns.eventType,
                eventDetails = columns.eventDetails,
                lat = columns.lat,
                lon = columns.lon,
                speedKmh = columns.speedKmh,
                createdAtMillis = System.currentTimeMillis(),
            )
        )
    }

    suspend fun markSent(id: Long, sentAtMillis: Long = System.currentTimeMillis()) {
        dao.markSent(id, sentAtMillis)
    }

    suspend fun markPending(id: Long) {
        dao.markPending(id)
    }

    suspend fun markError(id: Long) {
        dao.markError(id)
    }

    suspend fun clearAll() = dao.clearAll()

    private fun SavedTelemetryEntity.toRecord(): SavedTelemetryRecord =
        SavedTelemetryRecord(
            id = id,
            topic = topic,
            qos = qos,
            payloadJson = payloadJson,
            busId = busId,
            messageType = messageType,
            eventType = eventType,
            eventDetails = eventDetails,
            lat = lat,
            lon = lon,
            speedKmh = speedKmh,
            createdAtMillis = createdAtMillis,
            sentAtMillis = sentAtMillis,
            deliveryStatus = deliveryStatus,
        )

    private fun OutboundMessage.toSavedColumns(): SavedColumns {
        val json = runCatching { JSONObject(payloadJson) }.getOrNull()
        return SavedColumns(
            busId = json?.optNullableInt("bus_id"),
            eventType = json?.optNullableString("event"),
            eventDetails = json?.eventDetails(),
            lat = json?.optNullableDouble("lat"),
            lon = json?.optNullableDouble("lon"),
            speedKmh = json?.optNullableDouble("speed"),
        )
    }

    private fun JSONObject.optNullableInt(name: String): Int? {
        return if (has(name) && !isNull(name)) optInt(name) else null
    }

    private fun JSONObject.optNullableDouble(name: String): Double? {
        return if (has(name) && !isNull(name)) optDouble(name) else null
    }

    private fun JSONObject.optNullableString(name: String): String? {
        return if (has(name) && !isNull(name)) optString(name).takeIf { it.isNotBlank() } else null
    }

    private fun JSONObject.eventDetails(): String? {
        val eventName = optNullableString("event") ?: return null
        return when (eventName) {
            "exceso_velocidad" -> {
                val value = optNullableDouble("value")
                val limit = optNullableDouble("speed_limit")
                buildString {
                    value?.let { append("velocidad=${formatNumber(it)} km/h") }
                    limit?.let { if (isNotEmpty()) append("; "); append("limite=${formatNumber(it)} km/h") }
                }.takeIf { it.isNotBlank() }
            }

            "frenado_brusco" -> {
                val value = optNullableDouble("value")
                val threshold = optNullableDouble("threshold")
                buildString {
                    value?.let { append("acel_longitudinal=${formatNumber(it)} m/s²") }
                    threshold?.let { if (isNotEmpty()) append("; "); append("umbral=${formatNumber(it)} m/s²") }
                }.takeIf { it.isNotBlank() }
            }

            "curva_peligrosa" -> {
                val value = optNullableDouble("value")
                val threshold = optNullableDouble("threshold")
                buildString {
                    value?.let { append("acel_transversal=${formatNumber(it)} m/s²") }
                    threshold?.let { if (isNotEmpty()) append("; "); append("umbral=${formatNumber(it)} m/s²") }
                }.takeIf { it.isNotBlank() }
            }

            "conduccion_agresiva" ->
                optNullableDouble("accel_x")?.let { "accel_x=${formatNumber(it)} m/s²" }

            "sobrecalentamiento" ->
                optNullableDouble("temperature")?.let { "temperature=${formatNumber(it)} °C" }

            "otros" -> {
                val description = optNullableString("description")
                val value = optNullableDouble("value")?.let { formatNumber(it) }
                val unit = optNullableString("unit")
                listOfNotNull(description, value, unit).joinToString(" ").takeIf { it.isNotBlank() }
            }

            else -> knownEventFields()
        }?.takeIf { it.isNotBlank() }
    }

    private fun JSONObject.knownEventFields(): String? {
        val ignored = setOf("bus_id", "type", "event", "timestamp", "lat", "lon")
        val keys = keys()
        val details = mutableListOf<String>()
        while (keys.hasNext()) {
            val key = keys.next()
            if (key !in ignored) {
                details += "$key=${opt(key)}"
            }
        }
        return details.joinToString("; ").takeIf { it.isNotBlank() }
    }

    private fun formatNumber(value: Double): String {
        return "%.2f".format(java.util.Locale.US, value)
    }

    private data class SavedColumns(
        val busId: Int?,
        val eventType: String?,
        val eventDetails: String?,
        val lat: Double?,
        val lon: Double?,
        val speedKmh: Double?,
    )
}
