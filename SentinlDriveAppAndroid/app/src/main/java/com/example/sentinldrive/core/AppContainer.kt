package com.example.sentinldrive.core

import android.content.Context
import com.example.sentinldrive.data.connectivity.ConnectivityObserver
import com.example.sentinldrive.data.location.GpsLogger
import com.example.sentinldrive.data.location.LocationProvider
import com.example.sentinldrive.data.mqtt.MqttManager
import com.example.sentinldrive.data.offline.PendingMessageDatabase
import com.example.sentinldrive.data.offline.PendingMessageRepository
import com.example.sentinldrive.data.offline.SavedTelemetryRepository
import com.example.sentinldrive.data.sensors.ImuLogger
import com.example.sentinldrive.data.sensors.SensorProvider
import com.example.sentinldrive.data.settings.SettingsRepository
import com.example.sentinldrive.domain.TelemetryRepository

class AppContainer(context: Context) {
    private val appContext = context.applicationContext

    private val settingsRepository: SettingsRepository by lazy { SettingsRepository(appContext) }
    private val pendingMessageRepository: PendingMessageRepository by lazy {
        PendingMessageRepository(PendingMessageDatabase.getInstance(appContext).pendingMessageDao())
    }
    private val savedTelemetryRepository: SavedTelemetryRepository by lazy {
        SavedTelemetryRepository(PendingMessageDatabase.getInstance(appContext).savedTelemetryDao())
    }
    private val mqttManager: MqttManager by lazy { MqttManager(appContext) }
    private val locationProvider: LocationProvider by lazy { LocationProvider(appContext) }
    private val sensorProvider: SensorProvider by lazy { SensorProvider(appContext) }
    private val connectivityObserver: ConnectivityObserver by lazy { ConnectivityObserver(appContext) }
    private val imuLogger: ImuLogger by lazy { ImuLogger(appContext) }
    private val gpsLogger: GpsLogger by lazy { GpsLogger(appContext) }

    val telemetryRepository: TelemetryRepository by lazy {
        TelemetryRepository(
            settingsRepository = settingsRepository,
            pendingRepository = pendingMessageRepository,
            savedTelemetryRepository = savedTelemetryRepository,
            mqttManager = mqttManager,
            locationProvider = locationProvider,
            sensorProvider = sensorProvider,
            connectivityObserver = connectivityObserver,
            imuLogger = imuLogger,
            gpsLogger = gpsLogger,
        )
    }
}
