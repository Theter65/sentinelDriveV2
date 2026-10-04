package com.example.sentinldrive.data.time

import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicLong

object NtpTime {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val ntpOffsetMs = AtomicLong(0L)
    @Volatile private var synced = false

    val isSynced: Boolean get() = synced

    fun nowMs(): Long = System.currentTimeMillis() + ntpOffsetMs.get()

    fun syncAsync() {
        scope.launch {
            repeat(MAX_RETRIES) { attempt ->
                val ok = syncOnce()
                if (ok) return@launch
                if (attempt < MAX_RETRIES - 1) {
                    Log.w(TAG, "NTP sync falló, reintentando en ${RETRY_DELAY_MS}ms (intento ${attempt + 1}/$MAX_RETRIES)")
                    delay(RETRY_DELAY_MS)
                }
            }
        }
    }

    private fun syncOnce(): Boolean {
        val socket = DatagramSocket()
        return try {
            socket.soTimeout = 3_000
            val address = InetAddress.getByName(NTP_HOST)
            val buffer = ByteArray(48)
            buffer[0] = 0x1B.toByte()
            val request = DatagramPacket(buffer, buffer.size, address, NTP_PORT)
            val t1 = System.currentTimeMillis()
            socket.send(request)
            val response = DatagramPacket(buffer, buffer.size)
            socket.receive(response)
            val t4 = System.currentTimeMillis()

            val t2 = readNtpTimestamp(buffer, 32)
            val t3 = readNtpTimestamp(buffer, 40)
            val offset = ((t2 - t1) + (t3 - t4)) / 2
            ntpOffsetMs.set(offset)
            synced = true
            Log.i(TAG, "NTP synced, offset=${offset}ms")
            true
        } catch (e: Exception) {
            Log.w(TAG, "NTP sync failed: ${e.message}")
            false
        } finally {
            try { socket.close() } catch (_: Exception) {}
        }
    }

    private fun readNtpTimestamp(buffer: ByteArray, offset: Int): Long {
        val seconds = ((buffer[offset].toLong() and 0xFF) shl 24) or
            ((buffer[offset + 1].toLong() and 0xFF) shl 16) or
            ((buffer[offset + 2].toLong() and 0xFF) shl 8) or
            (buffer[offset + 3].toLong() and 0xFF)
        val fraction = ((buffer[offset + 4].toLong() and 0xFF) shl 24) or
            ((buffer[offset + 5].toLong() and 0xFF) shl 16) or
            ((buffer[offset + 6].toLong() and 0xFF) shl 8) or
            (buffer[offset + 7].toLong() and 0xFF)
        val millis = (seconds - NTP_EPOCH_S) * 1000L + (fraction * 1000L shr 32)
        return millis
    }

    private const val TAG = "SENTNLDRIVE-Ntp"
    private const val NTP_HOST = "pool.ntp.org"
    private const val NTP_PORT = 123
    private const val NTP_EPOCH_S = 2208988800L
    private const val MAX_RETRIES = 3
    private const val RETRY_DELAY_MS = 5_000L
}
