package com.example.sentinldrive.ui.calibration

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.example.sentinldrive.domain.model.SensorSnapshot

@Composable
fun CalibrationScreen(
    sensor: SensorSnapshot,
    onCalibrate: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier.padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Card(modifier = Modifier.fillMaxWidth()) {
            Column(modifier = Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("Coloca el tel\u00e9fono fijo en la posici\u00f3n en la que viajar\u00e1 y presiona Calibrar.")
                Text("Lectura actual accel_x: ${"%.2f".format(sensor.accelX)}")
                Text("Lectura actual accel_y: ${"%.2f".format(sensor.accelY)}")
                Text("Lectura actual accel_z: ${"%.2f".format(sensor.accelZ)}")
            }
        }

        Button(onClick = onCalibrate, modifier = Modifier.fillMaxWidth()) {
            Text("Calibrar ahora")
        }
    }
}
