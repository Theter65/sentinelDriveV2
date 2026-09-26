package com.example.sentinldrive.ui.components

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.example.sentinldrive.domain.model.ManualEventInput

private val manualEvents = listOf("conduccion_agresiva", "sobrecalentamiento", "otros")
private val otherDescriptions = listOf(
    "Presi\u00f3n de llantas (psi)",
    "Voltaje de bater\u00eda (V)",
    "Presi\u00f3n de aceite (kPa)",
    "Nivel de combustible (%)",
    "Otro personalizado",
)

@Composable
fun ManualEventDialog(
    onDismiss: () -> Unit,
    onSend: (ManualEventInput) -> Unit,
) {
    var eventName by remember { mutableStateOf("conduccion_agresiva") }
    var eventMenuExpanded by remember { mutableStateOf(false) }

    var selectedOtherDescription by remember { mutableStateOf(otherDescriptions.first()) }
    var descriptionMenuExpanded by remember { mutableStateOf(false) }
    var customDescription by remember { mutableStateOf("") }

    var valueText by remember { mutableStateOf("") }
    var unitText by remember { mutableStateOf("") }
    var temperatureText by remember { mutableStateOf("") }
    var accelXText by remember { mutableStateOf("") }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Enviar evento manual") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Evento")
                Row {
                    Button(onClick = { eventMenuExpanded = true }) {
                        Text(eventName)
                    }
                    DropdownMenu(expanded = eventMenuExpanded, onDismissRequest = { eventMenuExpanded = false }) {
                        manualEvents.forEach { option ->
                            DropdownMenuItem(
                                text = { Text(option) },
                                onClick = {
                                    eventName = option
                                    eventMenuExpanded = false
                                }
                            )
                        }
                    }
                }

                when (eventName) {
                    "conduccion_agresiva" -> {
                        OutlinedTextField(
                            value = accelXText,
                            onValueChange = { accelXText = it },
                            label = { Text("accel_x (opcional)") },
                            modifier = Modifier.fillMaxWidth(),
                        )
                    }

                    "sobrecalentamiento" -> {
                        OutlinedTextField(
                            value = temperatureText,
                            onValueChange = { temperatureText = it },
                            label = { Text("temperature") },
                            modifier = Modifier.fillMaxWidth(),
                        )
                    }

                    "otros" -> {
                        Row {
                            Button(onClick = { descriptionMenuExpanded = true }) {
                                Text(selectedOtherDescription)
                            }
                            DropdownMenu(expanded = descriptionMenuExpanded, onDismissRequest = { descriptionMenuExpanded = false }) {
                                otherDescriptions.forEach { option ->
                                    DropdownMenuItem(
                                        text = { Text(option) },
                                        onClick = {
                                            selectedOtherDescription = option
                                            descriptionMenuExpanded = false
                                        }
                                    )
                                }
                            }
                        }

                        if (selectedOtherDescription == "Otro personalizado") {
                            OutlinedTextField(
                                value = customDescription,
                                onValueChange = { customDescription = it },
                                label = { Text("Descripci\u00f3n personalizada") },
                                modifier = Modifier.fillMaxWidth(),
                            )
                        }

                        OutlinedTextField(
                            value = valueText,
                            onValueChange = { valueText = it },
                            label = { Text("value") },
                            modifier = Modifier.fillMaxWidth(),
                        )
                        OutlinedTextField(
                            value = unitText,
                            onValueChange = { unitText = it },
                            label = { Text("Unidad (opcional)") },
                            modifier = Modifier.fillMaxWidth(),
                        )
                    }
                }
            }
        },
        confirmButton = {
            TextButton(
                onClick = {
                    val payload = when (eventName) {
                        "conduccion_agresiva" -> ManualEventInput(
                            eventName = eventName,
                            accelX = accelXText.toDoubleOrNull(),
                        )

                        "sobrecalentamiento" -> ManualEventInput(
                            eventName = eventName,
                            temperature = temperatureText.toDoubleOrNull(),
                        )

                        else -> {
                            val description = if (selectedOtherDescription == "Otro personalizado") {
                                customDescription.ifBlank { "Otro personalizado" }
                            } else {
                                selectedOtherDescription
                            }
                            ManualEventInput(
                                eventName = "otros",
                                description = description,
                                value = valueText.toDoubleOrNull(),
                                unit = unitText.ifBlank { null },
                            )
                        }
                    }
                    onSend(payload)
                    onDismiss()
                }
            ) {
                Text("Enviar")
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text("Cancelar")
            }
        },
        modifier = Modifier.padding(8.dp),
    )
}
