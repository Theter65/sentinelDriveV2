package com.example.sentinldrive.data.sensors

import kotlin.math.sqrt

class MadgwickAHRS {

    private var q0 = 1.0
    private var q1 = 0.0
    private var q2 = 0.0
    private var q3 = 0.0

    var beta: Double = BETA_DEFAULT
        set(value) { field = value.coerceIn(0.0, 1.0) }

    fun update(gx: Double, gy: Double, gz: Double, ax: Double, ay: Double, az: Double, dt: Double) {
        var qDot1 = 0.5 * (-q1 * gx - q2 * gy - q3 * gz)
        var qDot2 = 0.5 * (q0 * gx + q2 * gz - q3 * gy)
        var qDot3 = 0.5 * (q0 * gy - q1 * gz + q3 * gx)
        var qDot4 = 0.5 * (q0 * gz + q1 * gy - q2 * gx)

        if (!(ax == 0.0 && ay == 0.0 && az == 0.0)) {
            val recipNorm = 1.0 / sqrt(ax * ax + ay * ay + az * az)
            val nax = ax * recipNorm
            val nay = ay * recipNorm
            val naz = az * recipNorm

            val _2q0 = 2.0 * q0
            val _2q1 = 2.0 * q1
            val _2q2 = 2.0 * q2
            val _2q3 = 2.0 * q3
            val _4q0 = 4.0 * q0
            val _4q1 = 4.0 * q1
            val _4q2 = 4.0 * q2
            val _8q1 = 8.0 * q1
            val _8q2 = 8.0 * q2
            val q0q0 = q0 * q0
            val q1q1 = q1 * q1
            val q2q2 = q2 * q2
            val q3q3 = q3 * q3

            var s0 = _4q0 * q2q2 + _2q2 * nax + _4q0 * q1q1 - _2q1 * nay
            var s1 = _4q1 * q3q3 - _2q3 * nax + 4.0 * q0q0 * q1 - _2q0 * nay - _4q1 + _8q1 * q1q1 + _8q1 * q2q2 + _4q1 * naz
            var s2 = 4.0 * q0q0 * q2 + _2q0 * nax + _4q2 * q3q3 - _2q3 * nay - _4q2 + _8q2 * q1q1 + _8q2 * q2q2 + _4q2 * naz
            var s3 = 4.0 * q1q1 * q3 - _2q1 * nax + 4.0 * q2q2 * q3 - _2q2 * nay

            val sNorm = 1.0 / sqrt(s0 * s0 + s1 * s1 + s2 * s2 + s3 * s3)
            s0 *= sNorm; s1 *= sNorm; s2 *= sNorm; s3 *= sNorm

            qDot1 -= beta * s0
            qDot2 -= beta * s1
            qDot3 -= beta * s2
            qDot4 -= beta * s3
        }

        q0 += qDot1 * dt
        q1 += qDot2 * dt
        q2 += qDot3 * dt
        q3 += qDot4 * dt

        val recipNorm = 1.0 / sqrt(q0 * q0 + q1 * q1 + q2 * q2 + q3 * q3)
        q0 *= recipNorm; q1 *= recipNorm; q2 *= recipNorm; q3 *= recipNorm
    }

    fun getQuaternion() = doubleArrayOf(q0, q1, q2, q3)

    fun getGravity(): DoubleArray {
        val gx = 2.0 * (q1 * q3 - q0 * q2)
        val gy = 2.0 * (q0 * q1 + q2 * q3)
        val gz = q0 * q0 - q1 * q1 - q2 * q2 + q3 * q3
        return doubleArrayOf(gx * G, gy * G, gz * G)
    }

    fun getPitchRad(): Double {
        val q1q3 = q1 * q3
        val q0q2 = q0 * q2
        return kotlin.math.asin(-2.0 * (q1q3 - q0q2))
    }

    fun getRollRad(): Double {
        return kotlin.math.atan2(2.0 * (q0 * q1 + q2 * q3), q0 * q0 - q1 * q1 - q2 * q2 + q3 * q3)
    }

    fun getPitchDeg(): Double = getPitchRad() * RAD2DEG

    fun getRollDeg(): Double = getRollRad() * RAD2DEG

    fun reset() {
        q0 = 1.0; q1 = 0.0; q2 = 0.0; q3 = 0.0
    }

    companion object {
        const val BETA_DEFAULT = 0.04
        const val G = 9.81
        const val RAD2DEG = 180.0 / Math.PI
    }
}
