package com.example.sentinldrive.data.offline

import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey

@Entity(
    tableName = "pending_message",
    indices = [Index(value = ["status", "createdAtMillis"])],
)
data class PendingMessageEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val topic: String,
    val qos: Int,
    val payloadJson: String,
    val messageType: String,
    val createdAtMillis: Long,
    val savedTelemetryId: Long?,
    val status: String,
    val attemptCount: Int,
    val lastError: String?,
)
