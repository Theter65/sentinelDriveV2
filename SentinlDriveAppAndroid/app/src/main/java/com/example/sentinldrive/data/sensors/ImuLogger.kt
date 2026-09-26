package com.example.sentinldrive.data.sensors

import android.content.Context
import android.net.Uri
import android.util.Log
import java.io.OutputStreamWriter
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class ImuLogger(private val context: Context) {

    private var writer: OutputStreamWriter? = null
    private var currentUri: Uri? = null
    private var isLogging = false
    private var writeCount = 0
    private val timeFormat = SimpleDateFormat("HH:mm:ss", Locale.US)

    val isActive: Boolean get() = isLogging

    fun start(uri: Uri): Boolean {
        if (isLogging) return false
        return try {
            val os = context.contentResolver.openOutputStream(uri) ?: return false
            writer = OutputStreamWriter(os, Charsets.UTF_8)
            writer!!.write("Hora;Ax_mps2;Ay_mps2;Az_mps2;Gx_dps;Gy_dps;Gz_dps;Pitch_deg;Roll_deg;LinX_mps2;LinY_mps2;LinZ_mps2\n")
            writer!!.flush()
            currentUri = uri
            writeCount = 0
            isLogging = true
            Log.i(TAG, "IMU log started: $uri")
            true
        } catch (e: Exception) {
            Log.e(TAG, "Failed to start IMU log", e)
            false
        }
    }

    fun append(
        timestampMillis: Long,
        pitchDeg: Double,
        rollDeg: Double,
        linX: Double,
        linY: Double,
        linZ: Double,
        accelX: Double,
        accelY: Double,
        accelZ: Double,
        gyroX: Double,
        gyroY: Double,
        gyroZ: Double,
    ) {
        if (!isLogging) return
        try {
            val timeStr = timeFormat.format(Date(timestampMillis))
            writer?.write(
                "%s;%.6f;%.6f;%.6f;%.6f;%.6f;%.6f;%.4f;%.4f;%.4f;%.4f;%.4f\n".format(
                    timeStr,
                    accelX, accelY, accelZ,
                    gyroX, gyroY, gyroZ,
                    pitchDeg, rollDeg,
                    linX, linY, linZ,
                ).replace(".", ",")
            )
            writeCount++
            if (writeCount % 10 == 0) {
                writer?.flush()
            }
        } catch (e: Exception) {
            Log.w(TAG, "Failed to write IMU log line", e)
        }
    }

    fun stop(): Uri? {
        if (!isLogging) return null
        isLogging = false
        try {
            writer?.flush()
            writer?.close()
        } catch (e: Exception) {
            Log.w(TAG, "Error closing IMU log", e)
        }
        writer = null
        val uri = currentUri
        currentUri = null
        Log.i(TAG, "IMU log stopped: $uri")
        return uri
    }

    companion object {
        private const val TAG = "SentinlDrive-ImuLog"
    }
}
