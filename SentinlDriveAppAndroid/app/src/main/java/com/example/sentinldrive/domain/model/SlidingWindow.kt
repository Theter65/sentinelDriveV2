package com.example.sentinldrive.domain.model

import kotlin.math.abs

class SlidingWindow(val capacity: Int) {

    private val buf = DoubleArray(capacity)
    private val sobre = BooleanArray(capacity)
    private val sign = IntArray(capacity)
    private var head = 0
    private var count = 0
    private var sobreCount = 0
    private var posCount = 0
    private var negCount = 0
    private var sum = 0.0

    val sampleCount: Int get() = count
    val sobrePct: Int get() = if (count > 0) sobreCount * 100 / count else 0
    val dirPct: Int get() = if (count > 0) maxOf(posCount, negCount) * 100 / count else 0
    val avg: Double get() = if (count > 0) sum / count else 0.0

    fun push(value: Double, isSobre: Boolean) {
        val sgn = if (value >= 0) 1 else -1

        if (count == capacity) {
            val oldVal = buf[head]
            val oldSobre = sobre[head]
            val oldSign = sign[head]
            sum -= oldVal
            if (oldSobre) sobreCount--
            if (oldSign > 0) posCount-- else negCount--
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

    val peak: Double get() {
        var p = 0.0
        val n = minOf(count, capacity)
        for (i in 0 until n) {
            val idx = (head - 1 - i + capacity) % capacity
            if (abs(buf[idx]) > abs(p)) p = buf[idx]
        }
        return p
    }

    fun reset() {
        head = 0
        count = 0
        sobreCount = 0
        posCount = 0
        negCount = 0
        sum = 0.0
    }
}
