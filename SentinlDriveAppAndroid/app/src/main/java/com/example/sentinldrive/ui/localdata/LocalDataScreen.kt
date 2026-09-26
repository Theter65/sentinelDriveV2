package com.example.sentinldrive.ui.localdata

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.example.sentinldrive.domain.model.SavedTelemetryRecord
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

@Composable
fun LocalDataScreen(
    records: List<SavedTelemetryRecord>,
    totalCount: Int,
    eventCount: Int,
    onClear: () -> Unit,
    onExportCsv: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val textColor = Color(0xFFF2F6FA)
    val gpsCount = (totalCount - eventCount).coerceAtLeast(0)
    Column(
        modifier = modifier
            .verticalScroll(rememberScrollState())
            .padding(16.dp)
            .navigationBarsPadding(),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Card(
            modifier = Modifier.fillMaxWidth(),
            colors = CardDefaults.cardColors(
                containerColor = MaterialTheme.colorScheme.surface.copy(alpha = 0.75f),
                contentColor = textColor,
            ),
        ) {
            Column(
                modifier = Modifier.padding(14.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Text("Datos guardados", style = MaterialTheme.typography.titleMedium, color = textColor)
                Text("Total local: $totalCount", color = textColor)
                Text("GPS guardados: $gpsCount", color = textColor)
                Text("Eventos guardados: $eventCount", color = textColor)
                Text("Vista ligera: últimos ${records.size} movimientos, sin payloads", color = textColor)
                Button(
                    onClick = onExportCsv,
                    enabled = totalCount > 0,
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Text("Descargar CSV")
                }
                Button(
                    onClick = onClear,
                    enabled = totalCount > 0,
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Text("Borrar registros locales")
                }
            }
        }

        if (records.isEmpty()) {
            Text("Todavía no hay datos guardados localmente.", color = textColor)
        } else {
            Text("Últimos movimientos", color = textColor, fontWeight = FontWeight.Bold)
            records.forEach { record ->
                SavedTelemetryRow(record = record)
            }
        }
    }
}

@Composable
private fun SavedTelemetryRow(record: SavedTelemetryRecord) {
    val textColor = Color(0xFFF2F6FA)
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surface.copy(alpha = 0.62f),
            contentColor = textColor,
        ),
    ) {
        Column(
            modifier = Modifier.padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Text(record.messageType.uppercase(), fontWeight = FontWeight.Bold, color = textColor)
                Text(record.deliveryStatus, color = textColor)
                Text("QoS ${record.qos}", color = textColor)
            }
            if (record.messageType == "event") {
                Text("Evento: ${record.eventType ?: "-"}", color = textColor)
                Text("Datos evento: ${record.eventDetails ?: "-"}", color = textColor)
            }
            Text("Creado: ${formatTime(record.createdAtMillis)}", color = textColor)
            Text("Enviado: ${record.sentAtMillis?.let { formatTime(it) } ?: "pendiente"}", color = textColor)
            Text("Bus: ${record.busId?.toString() ?: "-"}", color = textColor)
            Text(
                "Lat/Lon: ${record.lat?.let { formatNumber(it) } ?: "-"}, ${record.lon?.let { formatNumber(it) } ?: "-"}",
                color = textColor,
            )
            Text("Velocidad: ${record.speedKmh?.let { "${formatNumber(it)} km/h" } ?: "-"}", color = textColor)
        }
    }
}

private fun formatTime(millis: Long): String {
    return SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.getDefault()).format(Date(millis))
}

private fun formatNumber(value: Double): String {
    return "%.6f".format(Locale.US, value)
}
