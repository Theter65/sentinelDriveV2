package com.example.sentinldrive.data.sensors

class ImuProcessor {

    private val madgwick = MadgwickAHRS()
    private var initialized = false
    private var lastUpdateNs = 0L

    data class ProcessedData(
        val pitchDeg: Double,
        val rollDeg: Double,
        val linX: Double,
        val linY: Double,
        val linZ: Double,
        val accelX: Double,
        val accelY: Double,
        val accelZ: Double,
        val gyroX: Double,
        val gyroY: Double,
        val gyroZ: Double,
        val timestampMillis: Long,
        val betaUsed: Double,
    )

    fun process(
        accelX: Double, accelY: Double, accelZ: Double,
        gyroX: Double, gyroY: Double, gyroZ: Double,
        timestampNs: Long,
        beta: Double = MadgwickAHRS.BETA_DEFAULT,
    ): ProcessedData {
        val nowMs = timestampNs / 1_000_000L

        if (!initialized) {
            madgwick.beta = beta
            lastUpdateNs = timestampNs
            initialized = true
        } else {
            madgwick.beta = beta
        }

        val dtNs = timestampNs - lastUpdateNs
        lastUpdateNs = timestampNs
        val dt = (dtNs.toDouble() / 1_000_000_000.0).coerceIn(0.0001, 0.05)

        madgwick.update(gyroX, gyroY, gyroZ, accelX, accelY, accelZ, dt)

        val grav = madgwick.getGravity()
        val linX = accelX - grav[0]
        val linY = accelY - grav[1]
        val linZ = accelZ - grav[2]

        return ProcessedData(
            pitchDeg = madgwick.getPitchDeg(),
            rollDeg = madgwick.getRollDeg(),
            linX = linX,
            linY = linY,
            linZ = linZ,
            accelX = accelX,
            accelY = accelY,
            accelZ = accelZ,
            gyroX = gyroX,
            gyroY = gyroY,
            gyroZ = gyroZ,
            timestampMillis = nowMs,
            betaUsed = madgwick.beta,
        )
    }

    fun reset() {
        madgwick.reset()
        initialized = false
        lastUpdateNs = 0L
    }
}
