package com.example.sentinldrive.data.sensors

import com.example.sentinldrive.domain.model.LocationSnapshot
import com.example.sentinldrive.domain.model.MqttSettings
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlin.math.abs
import kotlin.math.ceil

class EventDetector {

    data class DetectedEvent(
        val type: String,
        val value: Double,
    )

    private var brakeWindow: RingBuffer = RingBuffer(50)
    private var curveWindow: RingBuffer = RingBuffer(300)

    private var brakeEdgeActive = false
    private var curveEdgeActive = false

    private var lastBrakeEventMs = 0L
    private var lastCurveEventMs = 0L
    private var lastSpeedEventMs = 0L
    private var speedOverSinceMs = 0L

    @Volatile private var currentSettings: MqttSettings = MqttSettings()

    @Volatile private var gpsLat: Double? = null
    @Volatile private var gpsLon: Double? = null
    @Volatile private var gpsSpeed: Double? = null
    @Volatile private var gpsValid = false
    @Volatile private var gpsWarmup = false

    private val _events = MutableSharedFlow<DetectedEvent>(extraBufferCapacity = 8)
    val events: SharedFlow<DetectedEvent> = _events.asSharedFlow()

    fun updateSettings(settings: MqttSettings) {
        currentSettings = settings
        val brakeCap = (settings.brakeWindowSeconds * 100).toInt().coerceIn(10, 500)
        val curveCap = (settings.curveWindowSeconds * 100).toInt().coerceIn(10, 1000)
        if (brakeWindow.capacity != brakeCap) brakeWindow = RingBuffer(brakeCap)
        if (curveWindow.capacity != curveCap) curveWindow = RingBuffer(curveCap)
    }

    fun updateGps(lat: Double?, lon: Double?, speedKmh: Double?, valid: Boolean, warmup: Boolean) {
        gpsLat = lat
        gpsLon = lon
        gpsSpeed = speedKmh
        gpsValid = valid
        gpsWarmup = warmup
    }

    fun onSample(linX: Double, linY: Double, timestampMs: Long) {
        val settings = currentSettings
        val brakeWin = brakeWindow
        val curveWin = curveWindow

        val speed = gpsSpeed
        val vehicleMoving = !settings.eventsRequireSpeed || (speed ?: 0.0) > MIN_SPEED_FOR_EVENTS_KMH

        brakeWin.push(linX, linX < settings.brakeThreshold)
        curveWin.push(linY, abs(linY) > settings.curveThreshold)

        val cooldownMs = (settings.eventCooldownSeconds * 1000.0).toLong()

        val brakeMin = ceil(brakeWin.capacity * 0.6).toInt()
        if (brakeWin.count >= brakeMin) {
            val brakeActive = brakeWin.sobrePct >= EVENT_THRESHOLD_PCT && vehicleMoving
            if (brakeActive && !brakeEdgeActive) {
                if (timestampMs - lastBrakeEventMs > cooldownMs) {
                    val avg = brakeWin.avg
                    if (gpsWarmup && gpsValid) {
                        _events.tryEmit(DetectedEvent("frenado_brusco", avg))
                        lastBrakeEventMs = timestampMs
                    }
                }
            }
            brakeEdgeActive = brakeActive
        }

        val curveMin = ceil(curveWin.capacity * 0.9).toInt()
        if (curveWin.count >= curveMin) {
            val curveActive = curveWin.sobrePct >= EVENT_THRESHOLD_PCT
                && curveWin.dirPct >= EVENT_THRESHOLD_PCT && vehicleMoving
            if (curveActive && !curveEdgeActive) {
                if (timestampMs - lastCurveEventMs > cooldownMs) {
                    val avg = curveWin.avg
                    if (gpsWarmup && gpsValid) {
                        _events.tryEmit(DetectedEvent("curva_peligrosa", avg))
                        lastCurveEventMs = timestampMs
                    }
                }
            }
            curveEdgeActive = curveActive
        }

        if (speed != null && speed > settings.speedLimitKmh) {
            if (speedOverSinceMs == 0L) speedOverSinceMs = timestampMs
            val speedWindowMs = (settings.speedWindowSeconds * 1000.0).toLong()
            if (timestampMs - speedOverSinceMs >= speedWindowMs) {
                if (timestampMs - lastSpeedEventMs > cooldownMs) {
                    if (gpsWarmup && gpsValid) {
                        _events.tryEmit(DetectedEvent("exceso_velocidad", speed))
                    }
                    lastSpeedEventMs = timestampMs
                }
                speedOverSinceMs = 0L
            }
        } else {
            speedOverSinceMs = 0L
        }
    }

    fun reset() {
        brakeWindow.reset()
        curveWindow.reset()
        brakeEdgeActive = false
        curveEdgeActive = false
        lastBrakeEventMs = 0L
        lastCurveEventMs = 0L
        lastSpeedEventMs = 0L
        speedOverSinceMs = 0L
    }

    private class RingBuffer(val capacity: Int) {
        private val buf = DoubleArray(capacity)
        private val sobre = BooleanArray(capacity)
        private val sign = IntArray(capacity)
        private var head = 0
        var count = 0; private set
        var sobreCount = 0; private set
        var posCount = 0; private set
        var negCount = 0; private set
        private var sum = 0.0

        val sobrePct: Int get() = if (count > 0) sobreCount * 100 / count else 0
        val dirPct: Int get() = if (count > 0) maxOf(posCount, negCount) * 100 / count else 0
        val avg: Double get() = if (count > 0) sum / count else 0.0

        fun push(value: Double, isSobre: Boolean) {
            val sgn = if (value >= 0) 1 else -1
            if (count == capacity) {
                sum -= buf[head]
                if (sobre[head]) sobreCount--
                if (sign[head] > 0) posCount-- else negCount--
            } else {
                count++
            }
            buf[head] = value
            sobre[head] = isSobre
            sign[head] = sgn
            sum += value
            if (isSobre) sobreCount++
            if (sgn > 0) posCount++ else negCount++
            head = (head + 1) % capacity
        }

        fun reset() {
            head = 0; count = 0; sobreCount = 0; posCount = 0; negCount = 0; sum = 0.0
        }
    }

    companion object {
        private const val EVENT_THRESHOLD_PCT = 80
        private const val MIN_SPEED_FOR_EVENTS_KMH = 5.0
    }
}
