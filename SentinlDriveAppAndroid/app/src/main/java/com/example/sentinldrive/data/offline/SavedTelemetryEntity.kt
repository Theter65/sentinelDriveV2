package com.example.sentinldrive.data.offline

import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey

@Entity(
    tableName = "saved_telemetry",
    indices = [Index(value = ["createdAtMillis"]), Index(value = ["sentAtMillis"])],
)
data class SavedTelemetryEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
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
    val sentAtMillis: Long? = null,
    val deliveryStatus: String = "PENDING",
)
