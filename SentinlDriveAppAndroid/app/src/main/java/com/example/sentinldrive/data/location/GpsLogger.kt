package com.example.sentinldrive.data.location

import android.content.Context
import android.net.Uri
import android.util.Log
import com.example.sentinldrive.data.time.NtpTime
import java.io.OutputStreamWriter
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class GpsLogger(private val context: Context) {

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
            writer!!.write("Hora;Latitud;Longitud;Velocidad_kmh;Precision_m\n")
            writer!!.flush()
            currentUri = uri
            writeCount = 0
            isLogging = true
            Log.i(TAG, "GPS log started: $uri")
            true
        } catch (e: Exception) {
            Log.e(TAG, "Failed to start GPS log", e)
            false
        }
    }

    fun append(
        lat: Double,
        lon: Double,
        speedKmh: Double?,
        accuracyMeters: Float?,
    ) {
        if (!isLogging) return
        try {
            val nowMs = NtpTime.nowMs()
            val timeStr = timeFormat.format(Date(nowMs))
            val speed = speedKmh?.let { "%.2f".format(it).replace(".", ",") } ?: ""
            val acc = accuracyMeters?.let { "%.2f".format(it).replace(".", ",") } ?: ""
            val latStr = "%.7f".format(lat).replace(".", ",")
            val lonStr = "%.7f".format(lon).replace(".", ",")
            writer?.write("$timeStr;$latStr;$lonStr;$speed;$acc\n")
            writeCount++
            if (writeCount % 5 == 0) {
                writer?.flush()
            }
        } catch (e: Exception) {
            Log.w(TAG, "Failed to write GPS log line", e)
        }
    }

    fun stop(): Uri? {
        if (!isLogging) return null
        isLogging = false
        try {
            writer?.flush()
            writer?.close()
        } catch (e: Exception) {
            Log.w(TAG, "Error closing GPS log", e)
        }
        writer = null
        val uri = currentUri
        currentUri = null
        Log.i(TAG, "GPS log stopped: $uri")
        return uri
    }

    companion object {
        private const val TAG = "SentinlDrive-GpsLog"
    }
}
