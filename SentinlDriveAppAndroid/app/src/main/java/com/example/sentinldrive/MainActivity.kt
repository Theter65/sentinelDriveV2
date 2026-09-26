package com.example.sentinldrive

import android.Manifest
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.consumeWindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.view.WindowCompat
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.example.sentinldrive.domain.model.ConnectionState
import com.example.sentinldrive.domain.model.SavedTelemetryRecord
import com.example.sentinldrive.service.TelemetryForegroundService
import com.example.sentinldrive.ui.components.ManualEventDialog
import com.example.sentinldrive.ui.gpslog.GpsLogScreen
import com.example.sentinldrive.ui.imulog.ImuLogScreen
import com.example.sentinldrive.ui.localdata.LocalDataScreen
import com.example.sentinldrive.ui.main.MainScreen
import com.example.sentinldrive.ui.main.MainViewModel
import com.example.sentinldrive.ui.main.MainViewModelFactory
import com.example.sentinldrive.ui.settings.SettingsScreen
import com.example.sentinldrive.ui.theme.SentinlDriveTheme
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.OutputStreamWriter
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class MainActivity : ComponentActivity() {

    private val viewModel: MainViewModel by viewModels {
        MainViewModelFactory((application as SentinlDriveApp).appContainer.telemetryRepository)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        WindowCompat.setDecorFitsSystemWindows(window, false)
        setContent {
            SentinlDriveTheme {
                AppContent(viewModel = viewModel)
            }
        }
    }

    @Composable
    private fun AppContent(viewModel: MainViewModel) {
        val state by viewModel.uiState.collectAsStateWithLifecycle()

        var screenName by remember { mutableStateOf(Screen.Main.name) }
        val screen = Screen.valueOf(screenName)

        var showManualEvent by remember { mutableStateOf(false) }
        var showSaveLocalPrompt by remember { mutableStateOf(false) }

        BackHandler(enabled = showManualEvent) {
            showManualEvent = false
        }

        BackHandler(enabled = showSaveLocalPrompt) {
            showSaveLocalPrompt = false
        }

        BackHandler(enabled = !showManualEvent && !showSaveLocalPrompt && screen != Screen.Main) {
            screenName = Screen.Main.name
        }

        val permissionLauncher = rememberLauncherForActivityResult(
            contract = ActivityResultContracts.RequestMultiplePermissions(),
            onResult = {
                viewModel.refreshLiveSources()
            },
        )
        val exportLauncher = rememberLauncherForActivityResult(
            contract = ActivityResultContracts.CreateDocument("text/csv"),
            onResult = { uri ->
                if (uri != null) {
                    exportSavedTelemetryCsv(uri = uri, viewModel = viewModel)
                }
            },
        )
        val imuLogLauncher = rememberLauncherForActivityResult(
            contract = ActivityResultContracts.CreateDocument("text/csv"),
            onResult = { uri ->
                if (uri != null) {
                    viewModel.startImuLogging(uri)
                }
            },
        )
        val gpsLogLauncher = rememberLauncherForActivityResult(
            contract = ActivityResultContracts.CreateDocument("text/csv"),
            onResult = { uri ->
                if (uri != null) {
                    viewModel.startGpsLogging(uri)
                }
            },
        )

        LaunchedEffect(Unit) {
            viewModel.refreshLiveSources()
            val permissions = buildList {
                add(Manifest.permission.ACCESS_FINE_LOCATION)
                add(Manifest.permission.ACCESS_COARSE_LOCATION)
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                    add(Manifest.permission.POST_NOTIFICATIONS)
                }
            }
            permissionLauncher.launch(permissions.toTypedArray())
        }

        Box(
            modifier = Modifier
                .fillMaxSize()
                .background(
                    brush = Brush.verticalGradient(
                        colors = listOf(Color(0xFF050A10), Color(0xFF081322), Color(0xFF0C1726))
                    )
                )
                .windowInsetsPadding(WindowInsets.safeDrawing)
        ) {
            Scaffold(
                modifier = Modifier.fillMaxSize(),
                containerColor = Color.Transparent,
                contentWindowInsets = WindowInsets(0, 0, 0, 0),
                topBar = {
                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(horizontal = 12.dp, vertical = 8.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        Surface(
                            color = MaterialTheme.colorScheme.surface.copy(alpha = 0.72f),
                            shape = RoundedCornerShape(20.dp),
                            shadowElevation = 6.dp,
                        ) {
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(horizontal = 12.dp, vertical = 10.dp),
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.spacedBy(10.dp),
                            ) {
                                Image(
                                    painter = painterResource(id = R.drawable.sentinl_logo),
                                    contentDescription = "Logo SentinlDrive",
                                    modifier = Modifier
                                        .size(38.dp)
                                        .clip(CircleShape),
                                    contentScale = ContentScale.Crop,
                                )
                                Column {
                                    Text(
                                        "SENTINLDRIVE",
                                        color = Color(0xFFF3F8F6),
                                        fontWeight = FontWeight.Bold,
                                    )
                                    Text(
                                        "Telemetría móvil",
                                        style = MaterialTheme.typography.labelMedium,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                                    )
                                }
                            }
                        }

                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                        ) {
                            NavButton(
                                text = "Principal",
                                selected = screen == Screen.Main,
                                onClick = { screenName = Screen.Main.name },
                                modifier = Modifier.weight(1f),
                            )
                            NavButton(
                                text = "Datos",
                                selected = screen == Screen.LocalData,
                                onClick = { screenName = Screen.LocalData.name },
                                modifier = Modifier.weight(1f),
                            )
                            NavButton(
                                text = "Config.",
                                selected = screen == Screen.Settings,
                                onClick = { screenName = Screen.Settings.name },
                                modifier = Modifier.weight(1f),
                            )
                            NavButton(
                                text = "IMU",
                                selected = screen == Screen.ImuLog,
                                onClick = { screenName = Screen.ImuLog.name },
                                modifier = Modifier.weight(1f),
                            )
                            NavButton(
                                text = "GPS",
                                selected = screen == Screen.GpsLog,
                                onClick = { screenName = Screen.GpsLog.name },
                                modifier = Modifier.weight(1f),
                            )
                        }
                    }
                }
            ) { padding ->
                when (screen) {
                    Screen.Main -> MainScreen(
                        state = state,
                        onToggleMqtt = {
                            if (state.mqttState.isConnectedLike()) {
                                viewModel.disconnectMqtt()
                            } else {
                                viewModel.connectMqtt()
                            }
                        },
                        onToggleSending = {
                            if (state.isSending || state.backgroundServiceRunning) {
                                TelemetryForegroundService.pause(this@MainActivity)
                                viewModel.pauseSending()
                            } else {
                                showSaveLocalPrompt = true
                            }
                        },
                        onRetryPending = { viewModel.retryPendingNow() },
                        onOpenSettings = { screenName = Screen.Settings.name },
                        onOpenCalibration = { screenName = Screen.ImuLog.name },
                        onOpenManualEvent = { showManualEvent = true },
                        onOpenSavedData = { screenName = Screen.LocalData.name },
                        modifier = Modifier
                            .padding(padding)
                            .consumeWindowInsets(padding),
                    )

                    Screen.Settings -> SettingsScreen(
                        settings = state.settings,
                        onSave = { viewModel.saveSettings(it) },
                        modifier = Modifier
                            .padding(padding)
                            .consumeWindowInsets(padding),
                    )

                    Screen.ImuLog -> ImuLogScreen(
                        sensor = state.sensor,
                        isLogging = state.imuLogging,
                        onStartLogging = {
                            imuLogLauncher.launch("imu_${defaultDateStamp()}.csv")
                        },
                        onStopLogging = { viewModel.stopImuLogging() },
                        modifier = Modifier
                            .padding(padding)
                            .consumeWindowInsets(padding),
                    )

                    Screen.GpsLog -> GpsLogScreen(
                        location = state.location,
                        isLogging = state.gpsLogging,
                        onStartLogging = {
                            gpsLogLauncher.launch("gps_${defaultDateStamp()}.csv")
                        },
                        onStopLogging = { viewModel.stopGpsLogging() },
                        modifier = Modifier
                            .padding(padding)
                            .consumeWindowInsets(padding),
                    )

                    Screen.LocalData -> LocalDataScreen(
                        records = state.savedTelemetryRecords,
                        totalCount = state.savedTelemetryCount,
                        eventCount = state.savedTelemetryEventCount,
                        onClear = { viewModel.clearSavedTelemetry() },
                        onExportCsv = {
                            exportLauncher.launch(defaultExportFileName())
                        },
                        modifier = Modifier
                            .padding(padding)
                            .consumeWindowInsets(padding),
                    )
                }
            }

            if (showManualEvent) {
                ManualEventDialog(
                    onDismiss = { showManualEvent = false },
                    onSend = { viewModel.sendManualEvent(it) },
                )
            }

            if (showSaveLocalPrompt) {
                AlertDialog(
                    onDismissRequest = { showSaveLocalPrompt = false },
                    title = { Text("Guardar datos localmente") },
                    text = {
                        Text(
                            "¿Quieres guardar una copia local de los datos enviados durante este recorrido? " +
                                "Podrás revisarlos luego en la sección Datos.",
                        )
                    },
                    confirmButton = {
                        TextButton(
                            onClick = {
                                showSaveLocalPrompt = false
                                if (state.settings.backgroundEnabled) {
                                    TelemetryForegroundService.start(this@MainActivity, saveLocal = true)
                                } else {
                                    viewModel.startSending(saveLocal = true)
                                }
                            },
                        ) {
                            Text("Guardar y enviar")
                        }
                    },
                    dismissButton = {
                        TextButton(
                            onClick = {
                                showSaveLocalPrompt = false
                                if (state.settings.backgroundEnabled) {
                                    TelemetryForegroundService.start(this@MainActivity, saveLocal = false)
                                } else {
                                    viewModel.startSending(saveLocal = false)
                                }
                            },
                        ) {
                            Text("Solo enviar")
                        }
                    },
                )
            }
        }
    }

    private fun exportSavedTelemetryCsv(uri: Uri, viewModel: MainViewModel) {
        lifecycleScope.launch {
            val result = runCatching {
                val records = withContext(Dispatchers.IO) {
                    viewModel.getAllSavedTelemetry()
                }
                val csv = buildSavedTelemetryCsv(records)
                withContext(Dispatchers.IO) {
                    contentResolver.openOutputStream(uri)?.use { output ->
                        OutputStreamWriter(output, Charsets.UTF_8).use { writer ->
                            writer.write(csv)
                        }
                    } ?: error("No se pudo abrir el archivo destino")
                }
                records.size
            }

            result
                .onSuccess { count ->
                    Toast.makeText(
                        this@MainActivity,
                        "CSV descargado con $count registros",
                        Toast.LENGTH_LONG,
                    ).show()
                }
                .onFailure { error ->
                    Toast.makeText(
                        this@MainActivity,
                        "No se pudo descargar el CSV: ${error.message}",
                        Toast.LENGTH_LONG,
                    ).show()
                }
        }
    }
}

@Composable
private fun NavButton(
    text: String,
    selected: Boolean,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val container = if (selected) {
        MaterialTheme.colorScheme.primary
    } else {
        MaterialTheme.colorScheme.surface.copy(alpha = 0.62f)
    }
    val content = if (selected) {
        Color(0xFF04120B)
    } else {
        MaterialTheme.colorScheme.onSurface
    }

    Button(
        onClick = onClick,
        modifier = modifier,
        shape = RoundedCornerShape(14.dp),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 4.dp, vertical = 8.dp),
        colors = ButtonDefaults.buttonColors(
            containerColor = container,
            contentColor = content,
        ),
    ) {
        Text(
            text = text,
            maxLines = 1,
            fontSize = 12.sp,
            textAlign = TextAlign.Center,
            modifier = Modifier.fillMaxWidth(),
        )
    }
}

private enum class Screen {
    Main,
    LocalData,
    Settings,
    ImuLog,
    GpsLog,
}

private fun ConnectionState.isConnectedLike(): Boolean = when (this) {
    ConnectionState.CONNECTED, ConnectionState.CONNECTING, ConnectionState.RECONNECTING -> true
    ConnectionState.DISCONNECTED, ConnectionState.ERROR -> false
}

private fun defaultExportFileName(): String {
    val stamp = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.getDefault()).format(Date())
    return "sentinldrive_datos_$stamp.csv"
}

private fun defaultDateStamp(): String {
    return SimpleDateFormat("yyyyMMdd_HHmmss", Locale.getDefault()).format(Date())
}

private fun buildSavedTelemetryCsv(records: List<SavedTelemetryRecord>): String {
    return buildString {
        appendLine("id,bus_id,type,event_type,event_details,created_at,sent_at,delivery_status,lat,lon,speed_kmh")
        records.forEach { record ->
            appendCsvCell(record.id.toString())
            append(',')
            appendCsvCell(record.busId?.toString() ?: "")
            append(',')
            appendCsvCell(record.messageType)
            append(',')
            appendCsvCell(record.eventType ?: "")
            append(',')
            appendCsvCell(record.eventDetails ?: "")
            append(',')
            appendCsvCell(formatExportTime(record.createdAtMillis))
            append(',')
            appendCsvCell(record.sentAtMillis?.let { formatExportTime(it) } ?: "")
            append(',')
            appendCsvCell(record.deliveryStatus)
            append(',')
            appendCsvCell(record.lat?.toString() ?: "")
            append(',')
            appendCsvCell(record.lon?.toString() ?: "")
            append(',')
            appendCsvCell(record.speedKmh?.toString() ?: "")
            appendLine()
        }
    }
}

private fun StringBuilder.appendCsvCell(value: String) {
    append('"')
    append(value.replace("\"", "\"\""))
    append('"')
}

private fun formatExportTime(millis: Long): String {
    return SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.getDefault()).format(Date(millis))
}
