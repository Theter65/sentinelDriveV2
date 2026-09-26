package com.example.sentinldrive.data.offline

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import kotlinx.coroutines.flow.Flow

@Dao
interface SavedTelemetryDao {

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insert(entity: SavedTelemetryEntity): Long

    @Query("SELECT * FROM saved_telemetry ORDER BY createdAtMillis DESC LIMIT :limit")
    fun recentFlow(limit: Int = 100): Flow<List<SavedTelemetryEntity>>

    @Query("SELECT * FROM saved_telemetry ORDER BY createdAtMillis DESC")
    suspend fun getAll(): List<SavedTelemetryEntity>

    @Query("SELECT COUNT(*) FROM saved_telemetry")
    fun countFlow(): Flow<Int>

    @Query("SELECT COUNT(*) FROM saved_telemetry WHERE messageType = 'event'")
    fun eventCountFlow(): Flow<Int>

    @Query("UPDATE saved_telemetry SET sentAtMillis = :sentAtMillis, deliveryStatus = 'SENT' WHERE id = :id")
    suspend fun markSent(id: Long, sentAtMillis: Long)

    @Query("UPDATE saved_telemetry SET deliveryStatus = 'PENDING' WHERE id = :id AND sentAtMillis IS NULL")
    suspend fun markPending(id: Long)

    @Query("UPDATE saved_telemetry SET deliveryStatus = 'ERROR' WHERE id = :id AND sentAtMillis IS NULL")
    suspend fun markError(id: Long)

    @Query("DELETE FROM saved_telemetry")
    suspend fun clearAll()
}
