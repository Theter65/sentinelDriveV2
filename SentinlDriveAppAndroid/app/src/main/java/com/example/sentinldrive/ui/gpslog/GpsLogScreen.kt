package com.example.sentinldrive.ui.gpslog

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardColors
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.sentinldrive.domain.model.LocationSnapshot

private val textWhite = Color(0xFFF2F6FA)
private val textDim = Color(0xBCF2F6FA)

@Composable
fun GpsLogScreen(
    location: LocationSnapshot,
    isLogging: Boolean,
    onStartLogging: () -> Unit,
    onStopLogging: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val cardColors = CardDefaults.cardColors(
        containerColor = MaterialTheme.colorScheme.surface.copy(alpha = 0.75f),
    )

    Column(
        modifier = modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text(
            "Monitoreo GPS",
            style = MaterialTheme.typography.titleLarge,
            color = textWhite,
        )

        ImuCard(title = "Posición", cardColors = cardColors) {
            Line("Latitud", "${location.lat?.let { "%.6f".format(it) } ?: "-"}")
            Line("Longitud", "${location.lon?.let { "%.6f".format(it) } ?: "-"}")
        }

        ImuCard(title = "Velocidad", cardColors = cardColors) {
            Line("Velocidad GPS", "${location.speedKmh?.let { "%.2f".format(it) } ?: "-"} km/h")
        }

        ImuCard(title = "Precisión", cardColors = cardColors) {
            Line("Precisión", "${location.accuracyMeters?.let { "%.2f".format(it) } ?: "-"} m")
        }

        Spacer(Modifier.height(8.dp))

        Button(
            onClick = if (isLogging) onStopLogging else onStartLogging,
            modifier = Modifier.fillMaxWidth(),
            colors = ButtonDefaults.buttonColors(
                containerColor = if (isLogging) Color(0xFFB71C1C) else Color(0xFF1B5E20),
            ),
        ) {
            Text(
                if (isLogging) "DETENER LOG (CSV)" else "INICIAR LOG (CSV)",
                color = Color.White,
            )
        }

        if (isLogging) {
            Text(
                "Guardando datos GPS en CSV (1 Hz, tiempo NTP)...",
                color = MaterialTheme.colorScheme.primary,
                style = MaterialTheme.typography.bodySmall,
            )
        }
    }
}

@Composable
private fun ImuCard(
    title: String,
    cardColors: CardColors,
    content: @Composable () -> Unit,
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = cardColors,
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            Text(
                title,
                style = MaterialTheme.typography.titleSmall,
                color = MaterialTheme.colorScheme.primary,
            )
            Spacer(Modifier.height(4.dp))
            content()
        }
    }
}

@Composable
private fun Line(name: String, value: String) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 1.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Text(name, fontFamily = FontFamily.Monospace, fontSize = 13.sp, color = textWhite)
        Text(value, fontFamily = FontFamily.Monospace, fontSize = 13.sp, color = textDim)
    }
}
