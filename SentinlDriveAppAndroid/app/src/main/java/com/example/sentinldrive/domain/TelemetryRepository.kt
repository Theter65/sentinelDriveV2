package com.example.sentinldrive.domain

import android.net.Uri
import android.util.Log
import com.example.sentinldrive.data.connectivity.ConnectivityObserver
import com.example.sentinldrive.data.location.GpsLogger
import com.example.sentinldrive.data.location.LocationProvider
import com.example.sentinldrive.data.mqtt.MqttManager
import com.example.sentinldrive.data.offline.PendingMessageRepository
import com.example.sentinldrive.data.offline.SavedTelemetryRepository
import com.example.sentinldrive.data.payload.PayloadFactory
import com.example.sentinldrive.data.sensors.ImuLogger
import com.example.sentinldrive.data.sensors.SensorProvider
import com.example.sentinldrive.data.settings.SettingsRepository
import com.example.sentinldrive.data.time.NtpTime
import com.example.sentinldrive.domain.model.CalibrationData
import com.example.sentinldrive.domain.model.ConnectionState
import com.example.sentinldrive.domain.model.ManualEventInput
import com.example.sentinldrive.domain.model.MqttSettings
import com.example.sentinldrive.domain.model.OutboundMessage
import com.example.sentinldrive.domain.model.SavedTelemetryRecord
import com.example.sentinldrive.domain.model.StartSendingResult
import com.example.sentinldrive.domain.model.TelemetryUiState
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter

class TelemetryRepository(
    private val settingsRepository: SettingsRepository,
    private val pendingRepository: PendingMessageRepository,
    private val savedTelemetryRepository: SavedTelemetryRepository,
    private val mqttManager: MqttManager,
    private val locationProvider: LocationProvider,
    private val sensorProvider: SensorProvider,
    private val connectivityObserver: ConnectivityObserver,
    private val imuLogger: ImuLogger,
    private val gpsLogger: GpsLogger,
) {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val _uiState = MutableStateFlow(TelemetryUiState())
    val uiState: StateFlow<TelemetryUiState> = _uiState.asStateFlow()

    private var sendingJob: Job? = null
    private var latestCalibration = CalibrationData()
    private var saveLocalDuringSession = false
    private val flushMutex = Mutex()
    private val reconnectMutex = Mutex()
    private var imuLoggingJob: Job? = null
    private var gpsLoggingJob: Job? = null
    private var gpsFirstFixMs = 0L

    init {
        NtpTime.syncAsync()
        ensureLiveSources()

        scope.launch {
            settingsRepository.settingsFlow.collect { settings ->
                _uiState.update { it.copy(settings = settings) }
                sensorProvider.eventDetector.updateSettings(settings)
            }
        }
        scope.launch {
            settingsRepository.calibrationFlow.collect { calibration ->
                latestCalibration = calibration
            }
        }
        scope.launch {
            connectivityObserver.internetAvailableFlow().collect { available ->
                _uiState.update { it.copy(internetAvailable = available) }
                if (available) {
                    reconnectMqttIfUseful()
                    flushPendingIfPossible()
                }
            }
        }
        scope.launch {
            mqttManager.connectionState.collect { state ->
                _uiState.update { it.copy(mqttState = state) }
                if (state == ConnectionState.CONNECTED || state == ConnectionState.RECONNECTING) {
                    flushPendingIfPossible()
                }
            }
        }
        scope.launch {
            mqttManager.lastError.collect { error ->
                _uiState.update { it.copy(mqttError = error) }
            }
        }
        scope.launch {
            locationProvider.latest.collect { location ->
                val clearLocationError = location.lat != null && location.lon != null
                _uiState.update { it.copy(
                    location = location,
                    locationError = if (clearLocationError) null else _uiState.value.locationError,
                ) }
                val hasFix = location.lat != null && location.lon != null
                if (hasFix && gpsFirstFixMs == 0L) {
                    gpsFirstFixMs = System.currentTimeMillis()
                }
                val warmupComplete = gpsFirstFixMs > 0L &&
                    (System.currentTimeMillis() - gpsFirstFixMs >= GPS_WARMUP_MS)
                sensorProvider.eventDetector.updateGps(
                    lat = location.lat,
                    lon = location.lon,
                    speedKmh = location.speedKmh,
                    valid = hasFix,
                    warmup = warmupComplete,
                )
            }
        }
        scope.launch {
            sensorProvider.latest.collect { sensor ->
                val clearSensorError =
                    sensor.accelX != 0.0 || sensor.accelY != 0.0 || sensor.accelZ != 0.0 ||
                        sensor.gyroX != 0.0 || sensor.gyroY != 0.0 || sensor.gyroZ != 0.0
                _uiState.update { it.copy(
                    sensor = sensor,
                    sensorError = if (clearSensorError) null else _uiState.value.sensorError,
                ) }
            }
        }
        scope.launch {
            sensorProvider.eventDetector.events.collect { detected ->
                val settings = _uiState.value.settings
                val location = _uiState.value.location

                val event = when (detected.type) {
                    "frenado_brusco" -> PayloadFactory.buildBrakeEvent(settings, location, detected.value)
                    "curva_peligrosa" -> PayloadFactory.buildCurveEvent(settings, location, detected.value)
                    "exceso_velocidad" -> PayloadFactory.buildOverspeedEvent(settings, location, detected.value)
                    else -> return@collect
                }

                sendOrQueue(event)
                _uiState.update { it.copy(lastEventPayload = event.payloadJson) }
                Log.i(TAG, "EVENTO ${detected.type} avg=${"%.2f".format(detected.value)}")
            }
        }
        scope.launch {
            pendingRepository.pendingCountFlow().collect { count ->
                _uiState.update { it.copy(pendingCount = count) }
            }
        }
        scope.launch {
            savedTelemetryRepository.countFlow().collect { count ->
                _uiState.update { it.copy(savedTelemetryCount = count) }
            }
        }
        scope.launch {
            savedTelemetryRepository.eventCountFlow().collect { count ->
                _uiState.update { it.copy(savedTelemetryEventCount = count) }
            }
        }
        scope.launch {
            savedTelemetryRepository.recentFlow(limit = 9).collect { records ->
                _uiState.update { it.copy(savedTelemetryRecords = records) }
            }
        }
    }

    suspend fun connectMqtt(): Result<Unit> = mqttManager.connect(_uiState.value.settings)

    suspend fun disconnectMqtt(): Result<Unit> = mqttManager.disconnect()

    fun refreshLiveSources() {
        ensureLiveSources()
    }

    fun startSending(saveLocal: Boolean): StartSendingResult {
        if (sendingJob?.isActive == true) return StartSendingResult.Started

        ensureLiveSources()
        val preflightError = startPreflightError()
        if (preflightError != null) {
            _uiState.update { it.copy(
                locationError = preflightError,
                isSending = false,
                isWaitingForLocation = false,
            ) }
            return StartSendingResult.Blocked(preflightError)
        }

        saveLocalDuringSession = saveLocal

        sendingJob = scope.launch {
            var lastGpsPublishMs = 0L

            _uiState.update { it.copy(
                isSending = true,
                internetAvailable = connectivityObserver.hasInternet(),
                localSavingEnabled = saveLocal,
                isWaitingForLocation = _uiState.value.location.lat == null || _uiState.value.location.lon == null,
            ) }
            reconnectMqttIfUseful()

            while (true) {
                val settings = _uiState.value.settings
                sensorProvider.beta = settings.beta
                val location = _uiState.value.location
                val now = System.currentTimeMillis()

                if (location.lat == null || location.lon == null) {
                    _uiState.update { it.copy(
                        isWaitingForLocation = true,
                        locationError = "Esperando ubicación antes de enviar datos",
                    ) }
                    delay(2_000L)
                    continue
                } else if (_uiState.value.isWaitingForLocation) {
                    _uiState.update { it.copy(
                        isWaitingForLocation = false,
                        locationError = null,
                    ) }
                }

                val gpsInterval = settings.gpsIntervalSeconds.coerceIn(3, 300) * 1000L
                if (now - lastGpsPublishMs >= gpsInterval) {
                    PayloadFactory.buildGpsMessage(settings, location)?.let { gps ->
                        sendOrQueue(gps)
                        _uiState.update { it.copy(lastGpsPayload = gps.payloadJson) }
                    }
                    flushPendingIfPossible()
                    lastGpsPublishMs = now
                }

                delay(SENSOR_POLL_INTERVAL_MS)
            }
        }

        return StartSendingResult.Started
    }

    fun pauseSending() {
        sendingJob?.cancel()
        sendingJob = null
        saveLocalDuringSession = false
        _uiState.update { it.copy(
            isSending = false,
            localSavingEnabled = false,
            isWaitingForLocation = false,
        ) }
    }

    suspend fun sendManualEvent(input: ManualEventInput): Result<Unit> {
        val message = PayloadFactory.buildManualEvent(
            settings = _uiState.value.settings,
            location = _uiState.value.location,
            calibration = latestCalibration,
            input = input,
        )

        return runCatching {
            sendOrQueue(message)
            _uiState.update { it.copy(lastEventPayload = message.payloadJson) }
        }
    }

    suspend fun updateSettings(transform: (MqttSettings) -> MqttSettings) {
        val current = _uiState.value.settings
        val updated = transform(current)
        settingsRepository.saveSettings(updated)
    }

    suspend fun calibrateNow() {
        val sensor = _uiState.value.sensor
        val calibration = CalibrationData(
            accelOffsetX = sensor.accelX,
            accelOffsetY = sensor.accelY,
            accelOffsetZ = sensor.accelZ,
            calibratedAtIso = LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss")),
        )
        settingsRepository.saveCalibration(calibration)
    }

    fun startImuLogging(uri: Uri): Boolean {
        if (imuLogger.isActive) return true
        val ok = imuLogger.start(uri)
        if (ok) {
            imuLoggingJob = scope.launch {
                while (imuLogger.isActive) {
                    val sensor = _uiState.value.sensor
                    val now = System.currentTimeMillis()
                    imuLogger.append(
                        timestampMillis = now,
                        pitchDeg = sensor.pitchDeg,
                        rollDeg = sensor.rollDeg,
                        linX = sensor.linX,
                        linY = sensor.linY,
                        linZ = sensor.linZ,
                        accelX = sensor.accelX,
                        accelY = sensor.accelY,
                        accelZ = sensor.accelZ,
                        gyroX = sensor.gyroX,
                        gyroY = sensor.gyroY,
                        gyroZ = sensor.gyroZ,
                    )
                    delay(IMU_LOG_INTERVAL_MS)
                }
            }
        }
        _uiState.update { it.copy(imuLogging = ok) }
        return ok
    }

    fun stopImuLogging(): Uri? {
        if (!imuLogger.isActive) return null
        imuLoggingJob?.cancel()
        imuLoggingJob = null
        val uri = imuLogger.stop()
        _uiState.update { it.copy(imuLogging = false) }
        return uri
    }

    fun startGpsLogging(uri: Uri): Boolean {
        if (gpsLogger.isActive) return true
        val ok = gpsLogger.start(uri)
        if (ok) {
            gpsLoggingJob = scope.launch {
                while (gpsLogger.isActive) {
                    val loc = _uiState.value.location
                    if (loc.lat != null && loc.lon != null) {
                        gpsLogger.append(
                            lat = loc.lat,
                            lon = loc.lon,
                            speedKmh = loc.speedKmh,
                            accuracyMeters = loc.accuracyMeters,
                        )
                    }
                    delay(GPS_LOG_INTERVAL_MS)
                }
            }
        }
        _uiState.update { it.copy(gpsLogging = ok) }
        return ok
    }

    fun stopGpsLogging(): Uri? {
        if (!gpsLogger.isActive) return null
        gpsLoggingJob?.cancel()
        gpsLoggingJob = null
        val uri = gpsLogger.stop()
        _uiState.update { it.copy(gpsLogging = false) }
        return uri
    }

    suspend fun flushPendingIfPossible() {
        if (!mqttManager.isConnected() || !_uiState.value.internetAvailable) return

        if (!flushMutex.tryLock()) return

        try {
            pendingRepository.recycleErrorsToPending()
            var processedBatches = 0
            while (processedBatches < MAX_FLUSH_BATCHES_PER_RUN) {
                if (!mqttManager.isConnected() || !_uiState.value.internetAvailable) break

                val pending = pendingRepository.getPending(limit = FLUSH_BATCH_SIZE)
                if (pending.isEmpty()) break

                for (row in pending) {
                    val result = mqttManager.publish(row.topic, row.payloadJson, row.qos)
                    if (result.isSuccess) {
                        val sentAtMillis = System.currentTimeMillis()
                        pendingRepository.markSent(row.id)
                        row.savedTelemetryId?.let { savedTelemetryRepository.markSent(it, sentAtMillis) }
                    } else {
                        pendingRepository.markError(row.id, result.exceptionOrNull()?.message ?: "publish_failed")
                        row.savedTelemetryId?.let { savedTelemetryRepository.markError(it) }
                    }
                }

                processedBatches++
            }
        } finally {
            flushMutex.unlock()
        }
    }

    fun setBackgroundServiceRunning(running: Boolean) {
        _uiState.update { it.copy(backgroundServiceRunning = running) }
    }

    fun destroy() {
        sensorProvider.stop()
        locationProvider.shutdown()
        scope.cancel()
    }

    suspend fun clearSavedTelemetry() {
        savedTelemetryRepository.clearAll()
        pendingRepository.clearAll()
    }

    suspend fun getAllSavedTelemetry(): List<SavedTelemetryRecord> {
        return savedTelemetryRepository.getAll()
    }

    private suspend fun sendOrQueue(message: OutboundMessage) {
        val savedTelemetryId = if (saveLocalDuringSession) {
            savedTelemetryRepository.save(message)
        } else {
            null
        }

        val internetAvailableNow = connectivityObserver.hasInternet()
        if (internetAvailableNow != _uiState.value.internetAvailable) {
            _uiState.update { it.copy(internetAvailable = internetAvailableNow) }
        }
        if (internetAvailableNow && !mqttManager.isConnected()) {
            reconnectMqttIfUseful()
        }

        val shouldTryLive = internetAvailableNow && mqttManager.isConnected()
        if (!shouldTryLive) {
            pendingRepository.enqueue(message, savedTelemetryId)
            savedTelemetryId?.let { savedTelemetryRepository.markPending(it) }
            return
        }

        val result = mqttManager.publish(message.topic, message.payloadJson, message.qos)
        if (result.isSuccess) {
            savedTelemetryId?.let { savedTelemetryRepository.markSent(it, System.currentTimeMillis()) }
        } else {
            pendingRepository.enqueue(message, savedTelemetryId)
            savedTelemetryId?.let { savedTelemetryRepository.markPending(it) }
            reconnectMqttIfUseful()
        }
    }

    private suspend fun reconnectMqttIfUseful() {
        if (!_uiState.value.internetAvailable || mqttManager.isConnected()) return
        if (!shouldAutoReconnectMqtt()) return
        if (!reconnectMutex.tryLock()) return

        try {
            if (_uiState.value.internetAvailable && !mqttManager.isConnected() && shouldAutoReconnectMqtt()) {
                mqttManager.connect(_uiState.value.settings)
                flushPendingIfPossible()
            }
        } finally {
            reconnectMutex.unlock()
        }
    }

    private fun shouldAutoReconnectMqtt(): Boolean {
        val state = _uiState.value
        return state.isSending || state.backgroundServiceRunning || state.pendingCount > 0
    }

    private fun startPreflightError(): String? {
        return when {
            !locationProvider.hasLocationPermissionGranted() -> "Permiso de ubicación no concedido"
            !locationProvider.isLocationServiceEnabled() -> "GPS/ubicación apagado. Actívalo en el teléfono"
            else -> null
        }
    }

    private fun ensureLiveSources() {
        val hasPermission = locationProvider.hasLocationPermissionGranted()
        val serviceEnabled = locationProvider.isLocationServiceEnabled()
        val locationStarted = locationProvider.start()
        val sensorStarted = sensorProvider.start()

        val locationMessage = when {
            locationStarted -> _uiState.value.locationError
            !hasPermission -> "Permiso de ubicación no concedido"
            !serviceEnabled -> "GPS/ubicación apagado. Actívalo en el teléfono"
            else -> "GPS no disponible. Revisa permisos y ubicación del teléfono"
        }

        _uiState.update { it.copy(
            locationError = locationMessage,
            sensorError = if (sensorStarted) null else "Sensores no disponibles o desactivados en este dispositivo",
        ) }

        Log.i(
            TAG,
            "Live sources -> locationStarted=$locationStarted sensorStarted=$sensorStarted hasPermission=$hasPermission serviceEnabled=$serviceEnabled"
        )
    }

    companion object {
        private const val TAG = "SentinlDrive-Repo"
        private const val FLUSH_BATCH_SIZE = 250
        private const val MAX_FLUSH_BATCHES_PER_RUN = 20
        private const val SENSOR_POLL_INTERVAL_MS = 10L
        private const val IMU_LOG_INTERVAL_MS = 50L
        private const val GPS_LOG_INTERVAL_MS = 1_000L
        private const val GPS_WARMUP_MS = 15_000L
    }
}
