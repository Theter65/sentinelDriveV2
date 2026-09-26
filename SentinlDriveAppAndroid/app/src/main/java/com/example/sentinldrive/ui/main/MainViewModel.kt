package com.example.sentinldrive.ui.main

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import android.net.Uri
import com.example.sentinldrive.domain.TelemetryRepository
import com.example.sentinldrive.domain.model.ManualEventInput
import com.example.sentinldrive.domain.model.MqttSettings
import com.example.sentinldrive.domain.model.SavedTelemetryRecord
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

class MainViewModel(
    private val telemetryRepository: TelemetryRepository,
) : ViewModel() {

    val uiState = telemetryRepository.uiState.stateIn(
        scope = viewModelScope,
        started = SharingStarted.WhileSubscribed(5_000),
        initialValue = telemetryRepository.uiState.value,
    )

    fun connectMqtt() {
        viewModelScope.launch(Dispatchers.IO) {
            telemetryRepository.connectMqtt()
        }
    }

    fun disconnectMqtt() {
        viewModelScope.launch(Dispatchers.IO) {
            telemetryRepository.disconnectMqtt()
        }
    }

    fun startSending(saveLocal: Boolean) {
        telemetryRepository.startSending(saveLocal)
    }

    fun pauseSending() {
        telemetryRepository.pauseSending()
    }

    fun sendManualEvent(input: ManualEventInput) {
        viewModelScope.launch(Dispatchers.IO) {
            telemetryRepository.sendManualEvent(input)
        }
    }

    fun saveSettings(settings: MqttSettings) {
        viewModelScope.launch(Dispatchers.IO) {
            telemetryRepository.updateSettings { settings }
        }
    }

    fun calibrateNow() {
        viewModelScope.launch(Dispatchers.IO) {
            telemetryRepository.calibrateNow()
        }
    }

    fun startImuLogging(uri: Uri) {
        telemetryRepository.startImuLogging(uri)
    }

    fun stopImuLogging() {
        telemetryRepository.stopImuLogging()
    }

    fun startGpsLogging(uri: Uri) {
        telemetryRepository.startGpsLogging(uri)
    }

    fun stopGpsLogging() {
        telemetryRepository.stopGpsLogging()
    }

    fun retryPendingNow() {
        viewModelScope.launch(Dispatchers.IO) {
            telemetryRepository.flushPendingIfPossible()
        }
    }

    fun refreshLiveSources() {
        telemetryRepository.refreshLiveSources()
    }

    fun clearSavedTelemetry() {
        viewModelScope.launch(Dispatchers.IO) {
            telemetryRepository.clearSavedTelemetry()
        }
    }

    suspend fun getAllSavedTelemetry(): List<SavedTelemetryRecord> {
        return telemetryRepository.getAllSavedTelemetry()
    }
}

class MainViewModelFactory(
    private val telemetryRepository: TelemetryRepository,
) : ViewModelProvider.Factory {
    @Suppress("UNCHECKED_CAST")
    override fun <T : ViewModel> create(modelClass: Class<T>): T {
        return MainViewModel(telemetryRepository) as T
    }
}
