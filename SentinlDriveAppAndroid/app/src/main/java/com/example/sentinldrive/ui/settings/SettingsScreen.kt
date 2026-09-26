package com.example.sentinldrive.ui.settings

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import com.example.sentinldrive.domain.model.MqttSettings

@Composable
fun SettingsScreen(
    settings: MqttSettings,
    onSave: (MqttSettings) -> Unit,
    modifier: Modifier = Modifier,
) {
    var host by remember { mutableStateOf(settings.host) }
    var port by remember { mutableStateOf(settings.port.toString()) }
    var username by remember { mutableStateOf(settings.username) }
    var password by remember { mutableStateOf(settings.password) }
    var baseTopic by remember { mutableStateOf(settings.baseTopic) }
    var busId by remember { mutableStateOf(settings.busId.toString()) }
    var gpsInterval by remember { mutableStateOf(settings.gpsIntervalSeconds.toString()) }
    var speedLimit by remember { mutableStateOf(settings.speedLimitKmh.toString()) }
    var brakeThreshold by remember { mutableStateOf(settings.brakeThreshold.toString()) }
    var curveThreshold by remember { mutableStateOf(settings.curveThreshold.toString()) }
    var backgroundEnabled by remember { mutableStateOf(settings.backgroundEnabled) }
    var eventsRequireSpeed by remember { mutableStateOf(settings.eventsRequireSpeed) }
    var speedWindowSeconds by remember { mutableStateOf(settings.speedWindowSeconds.toString()) }
    var brakeWindowSeconds by remember { mutableStateOf(settings.brakeWindowSeconds.toString()) }
    var curveWindowSeconds by remember { mutableStateOf(settings.curveWindowSeconds.toString()) }
    var eventCooldownSeconds by remember { mutableStateOf(settings.eventCooldownSeconds.toString()) }
    var beta by remember { mutableStateOf(settings.beta.toString()) }

    LaunchedEffect(settings) {
        host = settings.host
        port = settings.port.toString()
        username = settings.username
        password = settings.password
        baseTopic = settings.baseTopic
        busId = settings.busId.toString()
        gpsInterval = settings.gpsIntervalSeconds.toString()
        speedLimit = settings.speedLimitKmh.toString()
        brakeThreshold = settings.brakeThreshold.toString()
        curveThreshold = settings.curveThreshold.toString()
        backgroundEnabled = settings.backgroundEnabled
        eventsRequireSpeed = settings.eventsRequireSpeed
        speedWindowSeconds = settings.speedWindowSeconds.toString()
        brakeWindowSeconds = settings.brakeWindowSeconds.toString()
        curveWindowSeconds = settings.curveWindowSeconds.toString()
        eventCooldownSeconds = settings.eventCooldownSeconds.toString()
        beta = settings.beta.toString()
    }

    Column(
        modifier = modifier
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        OutlinedTextField(host, { host = it }, label = { Text("Host MQTT") }, modifier = Modifier.fillMaxWidth())
        OutlinedTextField(port, { port = it }, label = { Text("Puerto") }, modifier = Modifier.fillMaxWidth())
        OutlinedTextField(username, { username = it }, label = { Text("Usuario") }, modifier = Modifier.fillMaxWidth())
        OutlinedTextField(password, { password = it }, label = { Text("Contrase\u00f1a") }, modifier = Modifier.fillMaxWidth())
        OutlinedTextField(baseTopic, { baseTopic = it }, label = { Text("T\u00f3pico base") }, modifier = Modifier.fillMaxWidth())
        OutlinedTextField(busId, { busId = it }, label = { Text("bus_id") }, modifier = Modifier.fillMaxWidth())
        OutlinedTextField(gpsInterval, { gpsInterval = it }, label = { Text("Intervalo GPS (seg)") }, modifier = Modifier.fillMaxWidth())
        OutlinedTextField(speedLimit, { speedLimit = it }, label = { Text("L\u00edmite velocidad km/h") }, modifier = Modifier.fillMaxWidth())
        OutlinedTextField(brakeThreshold, { brakeThreshold = it }, label = { Text("Umbral frenado (m/s\u00b2)") }, modifier = Modifier.fillMaxWidth())
        OutlinedTextField(curveThreshold, { curveThreshold = it }, label = { Text("Umbral curva (m/s\u00b2)") }, modifier = Modifier.fillMaxWidth())

        Text("Ventanas de detecci\u00f3n (segundos)", color = Color(0xFF90CAF9))
        OutlinedTextField(speedWindowSeconds, { speedWindowSeconds = it }, label = { Text("Ventana exceso velocidad") }, modifier = Modifier.fillMaxWidth())
        OutlinedTextField(brakeWindowSeconds, { brakeWindowSeconds = it }, label = { Text("Ventana frenado brusco") }, modifier = Modifier.fillMaxWidth())
        OutlinedTextField(curveWindowSeconds, { curveWindowSeconds = it }, label = { Text("Ventana curva peligrosa") }, modifier = Modifier.fillMaxWidth())

        OutlinedTextField(eventCooldownSeconds, { eventCooldownSeconds = it }, label = { Text("Cooldown entre eventos (seg)") }, modifier = Modifier.fillMaxWidth())

        OutlinedTextField(beta, { beta = it }, label = { Text("Beta filtro Madgwick (0.0-1.0)") }, modifier = Modifier.fillMaxWidth())

        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Text("Env\u00edo en segundo plano", color = Color.White)
            Switch(checked = backgroundEnabled, onCheckedChange = { backgroundEnabled = it })
        }

        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Text("Eventos requieren velocidad GPS", color = Color.White)
            Switch(checked = eventsRequireSpeed, onCheckedChange = { eventsRequireSpeed = it })
        }

        Button(
            onClick = {
                val updated = settings.copy(
                    host = host.trim(),
                    port = port.toIntOrNull() ?: settings.port,
                    username = username.trim(),
                    password = password,
                    baseTopic = baseTopic.trim().trimEnd('/'),
                    busId = busId.toIntOrNull() ?: settings.busId,
                    gpsIntervalSeconds = gpsInterval.toIntOrNull() ?: settings.gpsIntervalSeconds,
                    speedLimitKmh = speedLimit.toDoubleOrNull() ?: settings.speedLimitKmh,
                    brakeThreshold = brakeThreshold.toDoubleOrNull() ?: settings.brakeThreshold,
                    curveThreshold = curveThreshold.toDoubleOrNull() ?: settings.curveThreshold,
                    backgroundEnabled = backgroundEnabled,
                    eventsRequireSpeed = eventsRequireSpeed,
                    speedWindowSeconds = speedWindowSeconds.toDoubleOrNull() ?: settings.speedWindowSeconds,
                    brakeWindowSeconds = brakeWindowSeconds.toDoubleOrNull() ?: settings.brakeWindowSeconds,
                    curveWindowSeconds = curveWindowSeconds.toDoubleOrNull() ?: settings.curveWindowSeconds,
                    eventCooldownSeconds = eventCooldownSeconds.toDoubleOrNull() ?: settings.eventCooldownSeconds,
                    beta = beta.toDoubleOrNull()?.coerceIn(0.0, 1.0) ?: settings.beta,
                )
                onSave(updated)
            },
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text("Guardar configuraci\u00f3n")
        }
    }
}
