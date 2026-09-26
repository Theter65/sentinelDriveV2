package com.example.sentinldrive.data.offline

import com.example.sentinldrive.domain.model.OutboundMessage
import kotlinx.coroutines.flow.Flow

class PendingMessageRepository(private val dao: PendingMessageDao) {

    fun pendingCountFlow(): Flow<Int> = dao.pendingCountFlow()

    suspend fun enqueue(message: OutboundMessage, savedTelemetryId: Long? = null) {
        dao.insert(
            PendingMessageEntity(
                topic = message.topic,
                qos = message.qos,
                payloadJson = message.payloadJson,
                messageType = message.type,
                createdAtMillis = System.currentTimeMillis(),
                savedTelemetryId = savedTelemetryId,
                status = "PENDING",
                attemptCount = 0,
                lastError = null,
            )
        )
    }

    suspend fun getPending(limit: Int = 200): List<PendingMessageEntity> = dao.getPending(limit)

    suspend fun markSent(id: Long) = dao.markSent(id)

    suspend fun markError(id: Long, error: String) = dao.markError(id, error)

    suspend fun recycleErrorsToPending() = dao.recycleErrorsToPending()

    suspend fun clearAll() = dao.clearAll()
}
