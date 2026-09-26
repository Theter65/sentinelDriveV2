package com.example.sentinldrive.service

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import com.example.sentinldrive.MainActivity
import com.example.sentinldrive.R
import com.example.sentinldrive.SentinlDriveApp
import com.example.sentinldrive.domain.TelemetryRepository
import com.example.sentinldrive.domain.model.StartSendingResult
import com.example.sentinldrive.domain.model.TelemetryUiState
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

class TelemetryForegroundService : Service() {

    private val telemetryRepository: TelemetryRepository
        get() = (application as SentinlDriveApp).appContainer.telemetryRepository

    private val serviceScope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private var notificationJob: Job? = null

    override fun onCreate() {
        super.onCreate()
        createChannelIfNeeded()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_START -> startTelemetry(intent.getBooleanExtra(EXTRA_SAVE_LOCAL, false))
            ACTION_PAUSE -> pauseTelemetry()
            ACTION_STOP -> stopTelemetry()
            else -> startTelemetry(saveLocal = false)
        }
        return START_STICKY
    }

    override fun onDestroy() {
        notificationJob?.cancel()
        serviceScope.cancel()
        telemetryRepository.setBackgroundServiceRunning(false)
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun startTelemetry(saveLocal: Boolean) {
        val notification = buildNotification("Preparando envío en segundo plano")
        try {
            ServiceCompat.startForeground(
                this,
                NOTIFICATION_ID,
                notification,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION,
            )
            telemetryRepository.setBackgroundServiceRunning(true)
            when (val result = telemetryRepository.startSending(saveLocal)) {
                StartSendingResult.Started -> startNotificationUpdates()
                is StartSendingResult.Blocked -> {
                    notify(result.reason)
                    telemetryRepository.setBackgroundServiceRunning(false)
                    stopSelf()
                }
            }
        } catch (_: SecurityException) {
            telemetryRepository.setBackgroundServiceRunning(false)
            stopSelf()
        }
    }

    private fun pauseTelemetry() {
        telemetryRepository.pauseSending()
        telemetryRepository.setBackgroundServiceRunning(false)
        notificationJob?.cancel()
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    private fun stopTelemetry() {
        telemetryRepository.pauseSending()
        telemetryRepository.setBackgroundServiceRunning(false)
        notificationJob?.cancel()
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    private fun startNotificationUpdates() {
        notificationJob?.cancel()
        notificationJob = serviceScope.launch {
            while (true) {
                notify(notificationText(telemetryRepository.uiState.value))
                delay(5_000L)
            }
        }
    }

    private fun notify(contentText: String) {
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        manager.notify(NOTIFICATION_ID, buildNotification(contentText))
    }

    private fun notificationText(state: TelemetryUiState): String {
        if (state.isWaitingForLocation) return "Esperando ubicación para enviar"
        val speed = state.location.speedKmh?.let { "%.1f km/h".format(it) } ?: "velocidad -"
        val location = if (state.location.lat != null && state.location.lon != null) {
            "%.5f, %.5f".format(state.location.lat, state.location.lon)
        } else {
            "sin ubicación"
        }
        val local = if (state.localSavingEnabled) " | guardando local" else ""
        return "$location | $speed$local"
    }

    private fun buildNotification(contentText: String): Notification {
        val openIntent = PendingIntent.getActivity(
            this,
            100,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )

        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("SentinlDrive")
            .setContentText(contentText)
            .setSmallIcon(R.drawable.ic_launcher_foreground)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setContentIntent(openIntent)
            .build()
    }

    private fun createChannelIfNeeded() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val channel = NotificationChannel(
            CHANNEL_ID,
            "Telemetría",
            NotificationManager.IMPORTANCE_LOW,
        ).apply {
            description = "Envía GPS y eventos mientras la app está en segundo plano"
        }
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        manager.createNotificationChannel(channel)
    }

    companion object {
        private const val CHANNEL_ID = "telemetry_channel"
        private const val NOTIFICATION_ID = 4551
        private const val EXTRA_SAVE_LOCAL = "com.example.sentinldrive.extra.SAVE_LOCAL"

        const val ACTION_START = "com.example.sentinldrive.action.START"
        const val ACTION_PAUSE = "com.example.sentinldrive.action.PAUSE"
        const val ACTION_STOP = "com.example.sentinldrive.action.STOP"

        fun start(context: Context, saveLocal: Boolean) {
            val intent = Intent(context, TelemetryForegroundService::class.java).apply {
                action = ACTION_START
                putExtra(EXTRA_SAVE_LOCAL, saveLocal)
            }
            context.startForegroundService(intent)
        }

        fun pause(context: Context) {
            val intent = Intent(context, TelemetryForegroundService::class.java).apply {
                action = ACTION_PAUSE
            }
            context.startService(intent)
        }

        fun stop(context: Context) {
            val intent = Intent(context, TelemetryForegroundService::class.java).apply {
                action = ACTION_STOP
            }
            context.startService(intent)
        }
    }
}
