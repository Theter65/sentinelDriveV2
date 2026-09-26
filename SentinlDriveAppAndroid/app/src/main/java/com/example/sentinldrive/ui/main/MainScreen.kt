package com.example.sentinldrive.ui.main

import androidx.compose.animation.animateContentSize
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.example.sentinldrive.domain.model.ConnectionState
import com.example.sentinldrive.domain.model.TelemetryUiState

@Composable
fun MainScreen(
    state: TelemetryUiState,
    onToggleMqtt: () -> Unit,
    onToggleSending: () -> Unit,
    onRetryPending: () -> Unit,
    onOpenSettings: () -> Unit,
    onOpenCalibration: () -> Unit,
    onOpenSavedData: () -> Unit,
    onOpenManualEvent: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val cardColor = MaterialTheme.colorScheme.surface.copy(alpha = 0.75f)
    val buttonPrimary = MaterialTheme.colorScheme.primary
    val textPrimary = Color(0xFFF2F6FA)

    Column(
        modifier = modifier
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 16.dp, vertical = 10.dp)
            .navigationBarsPadding(),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        GlassCard(title = "Estado", cardColor = cardColor) {
            Text("Estado MQTT: ${state.mqttState.label()}", color = textPrimary)
            Text("Internet: ${if (state.internetAvailable) "Disponible" else "Sin conexión"}", color = textPrimary)
            Text("bus_id: ${state.settings.busId}", color = textPrimary)
            Text("Guardado local: ${if (state.localSavingEnabled) "Activo" else "Inactivo"}", color = textPrimary)
            Text("Registros locales: ${state.savedTelemetryCount}", color = textPrimary)
            state.mqttError?.let { Text("Error MQTT: $it", color = textPrimary) }
        }

        GlassCard(title = "Ubicación", cardColor = cardColor) {
            if (state.isWaitingForLocation) {
                Text("Esperando ubicación para iniciar la transmisión", color = Color(0xFFFFD166))
            }
            state.locationError?.let { Text("Estado GPS: $it", color = textPrimary) }
            Text("Latitud: ${state.location.lat?.let { "%.6f".format(it) } ?: "-"}", color = textPrimary)
            Text("Longitud: ${state.location.lon?.let { "%.6f".format(it) } ?: "-"}", color = textPrimary)
            Text("Velocidad GPS (km/h): ${state.location.speedKmh?.let { "%.2f".format(it) } ?: "-"}", color = textPrimary)
            Text("Precisión GPS: ${state.location.accuracyMeters?.let { "%.2f m".format(it) } ?: "-"}", color = textPrimary)
        }

        GlassCard(title = "Sensores", cardColor = cardColor) {
            state.sensorError?.let { Text("Estado sensores: $it", color = textPrimary) }
            Text("Longitudinal (X): ${"%.3f".format(state.sensor.linX)} m/s\u00B2", color = textPrimary)
            Text("Transversal (Y): ${"%.3f".format(state.sensor.linY)} m/s\u00B2", color = textPrimary)
            Text("Vertical (Z): ${"%.3f".format(state.sensor.linZ)} m/s\u00B2", color = textPrimary)
        }

        GlassCard(title = "Cola offline", cardColor = cardColor) {
            Text("Mensajes pendientes: ${state.pendingCount}", color = textPrimary)
            ActionButton(
                text = "Reintentar pendientes",
                container = buttonPrimary,
                onClick = onRetryPending,
            )
        }

        GlassCard(title = "Últimos mensajes", cardColor = cardColor) {
            Text("Último payload GPS", fontWeight = FontWeight.SemiBold, color = textPrimary)
            Text(state.lastGpsPayload.ifBlank { "Sin envíos aún" }, color = textPrimary)
            Text("Último evento", fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(top = 6.dp), color = textPrimary)
            Text(state.lastEventPayload.ifBlank { "Sin eventos aún" }, color = textPrimary)
        }

        ActionButton(
            text = if (state.mqttState.isConnectedLike()) "Desconectar MQTT" else "Conectar MQTT",
            container = if (state.mqttState.isConnectedLike()) Color(0xFF2A3240) else buttonPrimary,
            content = if (state.mqttState.isConnectedLike()) Color(0xFFF2F6FA) else Color(0xFF051109),
            onClick = onToggleMqtt,
        )

        ActionButton(
            text = if (state.isSending || state.backgroundServiceRunning) "Pausar envío" else "Iniciar envío",
            container = if (state.isSending || state.backgroundServiceRunning) Color(0xFF2A3240) else buttonPrimary,
            content = if (state.isSending || state.backgroundServiceRunning) Color(0xFFF2F6FA) else Color(0xFF051109),
            onClick = onToggleSending,
        )

        ActionButton(text = "Enviar evento manual", container = buttonPrimary, onClick = onOpenManualEvent)
        ActionButton(text = "Ver datos guardados", container = buttonPrimary, onClick = onOpenSavedData)
        ActionButton(text = "Configuración", container = buttonPrimary, onClick = onOpenSettings)
        ActionButton(text = "Calibrar sensores", container = buttonPrimary, onClick = onOpenCalibration)
    }
}

@Composable
private fun GlassCard(
    title: String,
    cardColor: Color,
    content: @Composable () -> Unit,
) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .animateContentSize(),
        colors = CardDefaults.cardColors(
            containerColor = cardColor,
            contentColor = Color(0xFFF2F6FA),
        ),
        shape = MaterialTheme.shapes.large,
    ) {
        Column(
            modifier = Modifier.padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            Text(
                title,
                style = MaterialTheme.typography.titleMedium,
                color = Color(0xFFF2F6FA),
            )
            content()
        }
    }
}

@Composable
private fun ActionButton(
    text: String,
    container: Color,
    content: Color = Color(0xFF051109),
    onClick: () -> Unit,
) {
    Button(
        onClick = onClick,
        modifier = Modifier
            .fillMaxWidth()
            .animateContentSize(),
        colors = ButtonDefaults.buttonColors(
            containerColor = container,
            contentColor = content,
        ),
    ) {
        Text(text)
    }
}

private fun ConnectionState.label(): String = when (this) {
    ConnectionState.DISCONNECTED -> "Desconectado"
    ConnectionState.CONNECTING -> "Conectando"
    ConnectionState.CONNECTED -> "Conectado"
    ConnectionState.RECONNECTING -> "Reconectando"
    ConnectionState.ERROR -> "Error"
}

private fun ConnectionState.isConnectedLike(): Boolean = when (this) {
    ConnectionState.CONNECTED, ConnectionState.CONNECTING, ConnectionState.RECONNECTING -> true
    ConnectionState.DISCONNECTED, ConnectionState.ERROR -> false
}
