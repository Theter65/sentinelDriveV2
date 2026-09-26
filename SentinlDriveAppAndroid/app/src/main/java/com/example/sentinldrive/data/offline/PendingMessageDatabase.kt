package com.example.sentinldrive.data.offline

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase
import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase

@Database(
    entities = [PendingMessageEntity::class, SavedTelemetryEntity::class],
    version = 5,
    exportSchema = false,
)
abstract class PendingMessageDatabase : RoomDatabase() {
    abstract fun pendingMessageDao(): PendingMessageDao
    abstract fun savedTelemetryDao(): SavedTelemetryDao

    companion object {
        @Volatile
        private var INSTANCE: PendingMessageDatabase? = null

        fun getInstance(context: Context): PendingMessageDatabase {
            return INSTANCE ?: synchronized(this) {
                INSTANCE ?: Room.databaseBuilder(
                    context.applicationContext,
                    PendingMessageDatabase::class.java,
                    "pending_messages.db"
                ).addMigrations(MIGRATION_2_3, MIGRATION_3_4, MIGRATION_4_5).fallbackToDestructiveMigration().build().also {
                    INSTANCE = it
                }
            }
        }

        private val MIGRATION_2_3 = object : Migration(2, 3) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL("ALTER TABLE pending_message ADD COLUMN savedTelemetryId INTEGER")
                db.execSQL("ALTER TABLE saved_telemetry ADD COLUMN sentAtMillis INTEGER")
                db.execSQL("ALTER TABLE saved_telemetry ADD COLUMN deliveryStatus TEXT NOT NULL DEFAULT 'PENDING'")
                db.execSQL("CREATE INDEX IF NOT EXISTS index_pending_message_status_createdAtMillis ON pending_message(status, createdAtMillis)")
                db.execSQL("CREATE INDEX IF NOT EXISTS index_saved_telemetry_createdAtMillis ON saved_telemetry(createdAtMillis)")
                db.execSQL("CREATE INDEX IF NOT EXISTS index_saved_telemetry_sentAtMillis ON saved_telemetry(sentAtMillis)")
            }
        }

        private val MIGRATION_3_4 = object : Migration(3, 4) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL("ALTER TABLE saved_telemetry ADD COLUMN busId INTEGER")
                db.execSQL("ALTER TABLE saved_telemetry ADD COLUMN lat REAL")
                db.execSQL("ALTER TABLE saved_telemetry ADD COLUMN lon REAL")
                db.execSQL("ALTER TABLE saved_telemetry ADD COLUMN speedKmh REAL")
            }
        }

        private val MIGRATION_4_5 = object : Migration(4, 5) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL("ALTER TABLE saved_telemetry ADD COLUMN eventType TEXT")
                db.execSQL("ALTER TABLE saved_telemetry ADD COLUMN eventDetails TEXT")
            }
        }
    }
}
