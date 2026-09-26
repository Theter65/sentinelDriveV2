package com.example.sentinldrive.data.offline

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import kotlinx.coroutines.flow.Flow

@Dao
interface PendingMessageDao {

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insert(entity: PendingMessageEntity): Long

    @Query("SELECT * FROM pending_message WHERE status = 'PENDING' ORDER BY createdAtMillis ASC LIMIT :limit")
    suspend fun getPending(limit: Int = 200): List<PendingMessageEntity>

    @Query("SELECT COUNT(*) FROM pending_message WHERE status = 'PENDING'")
    fun pendingCountFlow(): Flow<Int>

    @Query("UPDATE pending_message SET status = 'SENT', lastError = NULL WHERE id = :id")
    suspend fun markSent(id: Long)

    @Query("UPDATE pending_message SET attemptCount = attemptCount + 1, status = 'ERROR', lastError = :error WHERE id = :id")
    suspend fun markError(id: Long, error: String)

    @Query("UPDATE pending_message SET status = 'PENDING' WHERE status = 'ERROR'")
    suspend fun recycleErrorsToPending()

    @Query("DELETE FROM pending_message")
    suspend fun clearAll()
}
