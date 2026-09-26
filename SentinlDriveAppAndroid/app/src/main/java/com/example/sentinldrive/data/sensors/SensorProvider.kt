package com.example.sentinldrive.data.sensors

import android.content.Context
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.util.Log
import com.example.sentinldrive.domain.model.SensorSnapshot
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

class SensorProvider(context: Context) : SensorEventListener {

    private val sensorManager = context.getSystemService(Context.SENSOR_SERVICE) as SensorManager
    private val accelerometer = sensorManager.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)
    private val gyroscope = sensorManager.getDefaultSensor(Sensor.TYPE_GYROSCOPE)

    private val _latest = MutableStateFlow(SensorSnapshot())
    val latest: StateFlow<SensorSnapshot> = _latest.asStateFlow()

    private val imuProcessor = ImuProcessor()
    val eventDetector = EventDetector()

    private var started = false
    private var lastAccelTimestampNs = 0L
    private var lastGyroTimestampNs = 0L

    private var lastAccelX = 0.0
    private var lastAccelY = 0.0
    private var lastAccelZ = 0.0
    private var lastGyroX = 0.0
    private var lastGyroY = 0.0
    private var lastGyroZ = 0.0

    @Volatile
    var beta: Double = 0.04

    fun start(): Boolean {
        if (started) return true

        var registeredAny = false
        accelerometer?.let {
            registeredAny = sensorManager.registerListener(this, it, SENSOR_RATE_US) || registeredAny
        }
        gyroscope?.let {
            registeredAny = sensorManager.registerListener(this, it, SENSOR_RATE_US) || registeredAny
        }

        started = registeredAny

        if (!registeredAny) {
            Log.w(TAG, "No se pudo registrar sensores. accel=${accelerometer != null} gyro=${gyroscope != null}")
        } else {
            Log.i(TAG, "Sensores activos. accel=${accelerometer != null} gyro=${gyroscope != null}")
        }

        return registeredAny
    }

    fun stop() {
        if (!started) return
        sensorManager.unregisterListener(this)
        started = false
        imuProcessor.reset()
        eventDetector.reset()
    }

    fun hasAccelerometer(): Boolean = accelerometer != null

    fun hasGyroscope(): Boolean = gyroscope != null

    override fun onSensorChanged(event: SensorEvent) {
        try {
            val timestampNs = event.timestamp

            when (event.sensor.type) {
                Sensor.TYPE_ACCELEROMETER -> {
                    lastAccelX = event.values[0].toDouble()
                    lastAccelY = event.values[1].toDouble()
                    lastAccelZ = event.values[2].toDouble()
                    lastAccelTimestampNs = timestampNs
                }

                Sensor.TYPE_GYROSCOPE -> {
                    lastGyroX = event.values[0].toDouble()
                    lastGyroY = event.values[1].toDouble()
                    lastGyroZ = event.values[2].toDouble()
                    lastGyroTimestampNs = timestampNs
                }
            }

            if (lastAccelTimestampNs == 0L || lastGyroTimestampNs == 0L) return
            if (event.sensor.type != Sensor.TYPE_GYROSCOPE) return

            val processed = imuProcessor.process(
                accelX = lastAccelX,
                accelY = lastAccelY,
                accelZ = lastAccelZ,
                gyroX = lastGyroX,
                gyroY = lastGyroY,
                gyroZ = lastGyroZ,
                timestampNs = lastGyroTimestampNs,
                beta = beta,
            )

            _latest.value = SensorSnapshot(
                accelX = processed.accelX,
                accelY = processed.accelY,
                accelZ = processed.accelZ,
                gyroX = processed.gyroX,
                gyroY = processed.gyroY,
                gyroZ = processed.gyroZ,
                linX = processed.linX,
                linY = processed.linY,
                linZ = processed.linZ,
                pitchDeg = processed.pitchDeg,
                rollDeg = processed.rollDeg,
                timestampMillis = processed.timestampMillis,
                betaUsed = processed.betaUsed,
            )

            eventDetector.onSample(
                linX = processed.linX,
                linY = processed.linY,
                timestampMs = processed.timestampMillis,
            )
        } catch (e: Exception) {
            Log.e(TAG, "Error procesando sensor", e)
        }
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) = Unit

    companion object {
        private const val TAG = "SentinlDrive-Sensor"
        private const val SENSOR_RATE_US = 10_000
    }
}
