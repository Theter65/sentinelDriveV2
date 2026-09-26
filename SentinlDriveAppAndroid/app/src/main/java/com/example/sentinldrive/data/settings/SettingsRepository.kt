package com.example.sentinldrive.data.settings

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.doublePreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.emptyPreferences
import androidx.datastore.preferences.core.intPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import com.example.sentinldrive.domain.model.CalibrationData
import com.example.sentinldrive.domain.model.MqttSettings
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.catch
import kotlinx.coroutines.flow.map
import java.io.IOException

private val Context.appDataStore: DataStore<Preferences> by preferencesDataStore(name = "sentinldrive_settings")

class SettingsRepository(private val context: Context) {

    private object Keys {
        val host = stringPreferencesKey("host")
        val port = intPreferencesKey("port")
        val username = stringPreferencesKey("username")
        val password = stringPreferencesKey("password")
        val baseTopic = stringPreferencesKey("base_topic")
        val busId = intPreferencesKey("bus_id")
        val gpsIntervalSeconds = intPreferencesKey("gps_interval_seconds")
        val speedLimitKmh = doublePreferencesKey("speed_limit_kmh")
        val brakeThreshold = doublePreferencesKey("brake_threshold")
        val curveThreshold = doublePreferencesKey("curve_threshold")
        val backgroundEnabled = booleanPreferencesKey("background_enabled")
        val eventsRequireSpeed = booleanPreferencesKey("events_require_speed")
        val speedWindowSeconds = doublePreferencesKey("speed_window_seconds")
        val brakeWindowSeconds = doublePreferencesKey("brake_window_seconds")
        val curveWindowSeconds = doublePreferencesKey("curve_window_seconds")
        val eventCooldownSeconds = doublePreferencesKey("event_cooldown_seconds")
        val beta = doublePreferencesKey("beta")

        val accelOffsetX = doublePreferencesKey("accel_offset_x")
        val accelOffsetY = doublePreferencesKey("accel_offset_y")
        val accelOffsetZ = doublePreferencesKey("accel_offset_z")
        val calibratedAtIso = stringPreferencesKey("calibrated_at_iso")
    }

    val settingsFlow: Flow<MqttSettings> = context.appDataStore.data
        .catch {
            if (it is IOException) emit(emptyPreferences()) else throw it
        }
        .map { p ->
            MqttSettings(
                host = p[Keys.host] ?: "006b41188f8e4c48ad4936cbef2e695a.s1.eu.hivemq.cloud",
                port = p[Keys.port] ?: 8883,
                username = p[Keys.username] ?: "",
                password = p[Keys.password] ?: "",
                baseTopic = p[Keys.baseTopic] ?: "flota/ecuador/buses",
                busId = p[Keys.busId] ?: 1,
                gpsIntervalSeconds = p[Keys.gpsIntervalSeconds] ?: 10,
                speedLimitKmh = p[Keys.speedLimitKmh] ?: 90.0,
                brakeThreshold = p[Keys.brakeThreshold] ?: -2.94,
                curveThreshold = p[Keys.curveThreshold] ?: 3.92,
                backgroundEnabled = p[Keys.backgroundEnabled] ?: true,
                eventsRequireSpeed = p[Keys.eventsRequireSpeed] ?: false,
                speedWindowSeconds = p[Keys.speedWindowSeconds] ?: 5.0,
                brakeWindowSeconds = p[Keys.brakeWindowSeconds] ?: 0.5,
                curveWindowSeconds = p[Keys.curveWindowSeconds] ?: 3.0,
                eventCooldownSeconds = p[Keys.eventCooldownSeconds] ?: 30.0,
                beta = p[Keys.beta] ?: 0.04,
            )
        }

    val calibrationFlow: Flow<CalibrationData> = context.appDataStore.data
        .catch {
            if (it is IOException) emit(emptyPreferences()) else throw it
        }
        .map { p ->
            CalibrationData(
                accelOffsetX = p[Keys.accelOffsetX] ?: 0.0,
                accelOffsetY = p[Keys.accelOffsetY] ?: 0.0,
                accelOffsetZ = p[Keys.accelOffsetZ] ?: 0.0,
                calibratedAtIso = p[Keys.calibratedAtIso] ?: "",
            )
        }

    suspend fun saveSettings(settings: MqttSettings) {
        context.appDataStore.edit { p ->
            p[Keys.host] = settings.host.trim()
            p[Keys.port] = settings.port
            p[Keys.username] = settings.username.trim()
            p[Keys.password] = settings.password
            p[Keys.baseTopic] = settings.baseTopic.trim().trimEnd('/')
            p[Keys.busId] = settings.busId
            p[Keys.gpsIntervalSeconds] = settings.gpsIntervalSeconds
            p[Keys.speedLimitKmh] = settings.speedLimitKmh
            p[Keys.brakeThreshold] = settings.brakeThreshold
            p[Keys.curveThreshold] = settings.curveThreshold
            p[Keys.backgroundEnabled] = settings.backgroundEnabled
            p[Keys.eventsRequireSpeed] = settings.eventsRequireSpeed
            p[Keys.speedWindowSeconds] = settings.speedWindowSeconds
            p[Keys.brakeWindowSeconds] = settings.brakeWindowSeconds
            p[Keys.curveWindowSeconds] = settings.curveWindowSeconds
            p[Keys.eventCooldownSeconds] = settings.eventCooldownSeconds
            p[Keys.beta] = settings.beta
        }
    }

    suspend fun saveCalibration(calibration: CalibrationData) {
        context.appDataStore.edit { p ->
            p[Keys.accelOffsetX] = calibration.accelOffsetX
            p[Keys.accelOffsetY] = calibration.accelOffsetY
            p[Keys.accelOffsetZ] = calibration.accelOffsetZ
            p[Keys.calibratedAtIso] = calibration.calibratedAtIso
        }
    }
}
