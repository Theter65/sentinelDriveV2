package com.example.sentinldrive.data.mqtt

import android.content.Context
import android.util.Log
import com.example.sentinldrive.domain.model.ConnectionState
import com.example.sentinldrive.domain.model.MqttSettings
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import org.eclipse.paho.client.mqttv3.IMqttActionListener
import org.eclipse.paho.client.mqttv3.IMqttDeliveryToken
import org.eclipse.paho.client.mqttv3.IMqttToken
import org.eclipse.paho.client.mqttv3.MqttAsyncClient
import org.eclipse.paho.client.mqttv3.MqttCallbackExtended
import org.eclipse.paho.client.mqttv3.MqttConnectOptions
import org.eclipse.paho.client.mqttv3.MqttException
import org.eclipse.paho.client.mqttv3.MqttMessage
import org.eclipse.paho.client.mqttv3.persist.MqttDefaultFilePersistence
import java.io.File
import kotlin.coroutines.resume

class MqttManager(context: Context) {

    private val mutex = Mutex()
    private val appContext = context.applicationContext
    private val persistenceDir: File = File(appContext.noBackupFilesDir, "mqtt-persistence").apply {
        mkdirs()
    }

    private val _connectionState = MutableStateFlow(ConnectionState.DISCONNECTED)
    val connectionState: StateFlow<ConnectionState> = _connectionState.asStateFlow()

    private val _lastError = MutableStateFlow<String?>(null)
    val lastError: StateFlow<String?> = _lastError.asStateFlow()

    private var client: MqttAsyncClient? = null
    private var lastServerUri: String = ""

    suspend fun connect(settings: MqttSettings): Result<Unit> = mutex.withLock {
        val normalizedHost = normalizeHost(settings.host)
        if (normalizedHost.isBlank() || settings.username.isBlank() || settings.password.isBlank()) {
            val msg = "Configuraci\u00f3n MQTT incompleta"
            _connectionState.value = ConnectionState.ERROR
            _lastError.value = msg
            Log.w(TAG, msg)
            return Result.failure(IllegalArgumentException(msg))
        }
        if (settings.port !in 1..65535) {
            val msg = "Puerto MQTT inv\u00e1lido: ${settings.port}"
            _connectionState.value = ConnectionState.ERROR
            _lastError.value = msg
            Log.w(TAG, msg)
            return Result.failure(IllegalArgumentException(msg))
        }

        val existing = client
        if (existing?.isConnected == true) {
            _connectionState.value = ConnectionState.CONNECTED
            _lastError.value = null
            return Result.success(Unit)
        }

        safeDisconnectAndClose(existing)

        val serverUri = "ssl://$normalizedHost:${settings.port}"
        lastServerUri = serverUri
        val clientId = "sentinldrive-${System.currentTimeMillis()}"

        _connectionState.value = ConnectionState.CONNECTING
        _lastError.value = null
        Log.i(TAG, "Intentando conectar MQTT a $serverUri con usuario=${settings.username.trim()}")

        return try {
            val mqttClient = MqttAsyncClient(
                serverUri,
                clientId,
                MqttDefaultFilePersistence(persistenceDir.absolutePath),
            )
            mqttClient.setCallback(object : MqttCallbackExtended {
                override fun connectComplete(reconnect: Boolean, serverURI: String?) {
                    _connectionState.value = if (reconnect) ConnectionState.RECONNECTING else ConnectionState.CONNECTED
                    Log.i(TAG, "MQTT conectado. reconnect=$reconnect uri=$serverURI")
                }

                override fun connectionLost(cause: Throwable?) {
                    _connectionState.value = ConnectionState.ERROR
                    _lastError.value = toFriendlyError(cause)
                    Log.e(TAG, "MQTT perdi\u00f3 conexi\u00f3n. causa=${describeThrowable(cause)}", cause)
                }

                override fun messageArrived(topic: String?, message: MqttMessage?) = Unit

                override fun deliveryComplete(token: IMqttDeliveryToken?) = Unit
            })

            val options = MqttConnectOptions().apply {
                isAutomaticReconnect = true
                isCleanSession = true
                userName = settings.username.trim()
                password = settings.password.toCharArray()
                connectionTimeout = 10
                keepAliveInterval = 60
                mqttVersion = MqttConnectOptions.MQTT_VERSION_3_1_1
            }

            suspendCancellableCoroutine<Result<Unit>> { cont ->
                mqttClient.connect(options, null, object : IMqttActionListener {
                    override fun onSuccess(asyncActionToken: IMqttToken?) {
                        client = mqttClient
                        _connectionState.value = ConnectionState.CONNECTED
                        _lastError.value = null
                        Log.i(TAG, "Conexi\u00f3n MQTT exitosa a $serverUri")
                        cont.resume(Result.success(Unit))
                    }

                    override fun onFailure(asyncActionToken: IMqttToken?, exception: Throwable?) {
                        val msg = toFriendlyError(exception)
                        _connectionState.value = ConnectionState.ERROR
                        _lastError.value = msg
                        Log.e(
                            TAG,
                            "Fallo al conectar MQTT en $serverUri. detalle=${describeThrowable(exception)}",
                            exception
                        )
                        safeDisconnectAndClose(mqttClient)
                        cont.resume(Result.failure(exception ?: RuntimeException(msg)))
                    }
                })
            }
        } catch (ex: Exception) {
            val msg = toFriendlyError(ex)
            _connectionState.value = ConnectionState.ERROR
            _lastError.value = msg
            Log.e(TAG, "Excepci\u00f3n al crear/conectar cliente MQTT. detalle=${describeThrowable(ex)}", ex)
            Result.failure(ex)
        }
    }

    suspend fun disconnect(): Result<Unit> = mutex.withLock {
        val mqttClient = client
        if (mqttClient == null) {
            _connectionState.value = ConnectionState.DISCONNECTED
            return Result.success(Unit)
        }

        if (!mqttClient.isConnected) {
            safeDisconnectAndClose(mqttClient)
            client = null
            _connectionState.value = ConnectionState.DISCONNECTED
            return Result.success(Unit)
        }

        return suspendCancellableCoroutine { cont ->
            try {
                mqttClient.disconnect(null, object : IMqttActionListener {
                    override fun onSuccess(asyncActionToken: IMqttToken?) {
                        safeDisconnectAndClose(mqttClient)
                        client = null
                        _connectionState.value = ConnectionState.DISCONNECTED
                        _lastError.value = null
                        Log.i(TAG, "MQTT desconectado manualmente")
                        cont.resume(Result.success(Unit))
                    }

                    override fun onFailure(asyncActionToken: IMqttToken?, exception: Throwable?) {
                        val msg = toFriendlyError(exception)
                        _connectionState.value = ConnectionState.ERROR
                        _lastError.value = msg
                        Log.e(TAG, "Fallo al desconectar MQTT. detalle=${describeThrowable(exception)}", exception)
                        cont.resume(Result.failure(exception ?: RuntimeException(msg)))
                    }
                })
            } catch (ex: MqttException) {
                val msg = toFriendlyError(ex)
                _connectionState.value = ConnectionState.ERROR
                _lastError.value = msg
                Log.e(TAG, "Excepci\u00f3n al desconectar MQTT. detalle=${describeThrowable(ex)}", ex)
                cont.resume(Result.failure(ex))
            }
        }
    }

    suspend fun publish(topic: String, payloadJson: String, qos: Int): Result<Unit> {
        val mqttClient = client
        if (mqttClient == null || !mqttClient.isConnected) {
            return Result.failure(IllegalStateException("MQTT desconectado"))
        }

        return suspendCancellableCoroutine { cont ->
            try {
                val message = MqttMessage(payloadJson.toByteArray()).apply {
                    this.qos = qos
                    isRetained = false
                }
                mqttClient.publish(topic, message, null, object : IMqttActionListener {
                    override fun onSuccess(asyncActionToken: IMqttToken?) {
                        cont.resume(Result.success(Unit))
                    }

                    override fun onFailure(asyncActionToken: IMqttToken?, exception: Throwable?) {
                        val msg = toFriendlyError(exception)
                        _lastError.value = msg
                        Log.e(
                            TAG,
                            "Fallo al publicar MQTT topic=$topic qos=$qos detalle=${describeThrowable(exception)}",
                            exception
                        )
                        cont.resume(Result.failure(exception ?: RuntimeException(msg)))
                    }
                })
            } catch (ex: Exception) {
                val msg = toFriendlyError(ex)
                _lastError.value = msg
                Log.e(TAG, "Excepci\u00f3n publicando MQTT topic=$topic qos=$qos detalle=${describeThrowable(ex)}", ex)
                cont.resume(Result.failure(ex))
            }
        }
    }

    fun isConnected(): Boolean = client?.isConnected == true

    private fun safeDisconnectAndClose(target: MqttAsyncClient?) {
        if (target == null) return
        try {
            if (target.isConnected) {
                target.disconnect()
            }
        } catch (_: Exception) {
        }
        try {
            target.close()
        } catch (_: Exception) {
        }
    }

    private fun normalizeHost(raw: String): String {
        var host = raw.trim()
        val schemes = listOf("ssl://", "tcp://", "mqtt://", "mqtts://", "ws://", "wss://")
        schemes.forEach { scheme ->
            if (host.startsWith(scheme, ignoreCase = true)) {
                host = host.removePrefix(scheme)
            }
        }
        host = host.substringBefore("/")
        host = host.substringBefore(":")
        return host.trim()
    }

    private fun toFriendlyError(error: Throwable?): String {
        if (error is MqttException) {
            val mapped = mapMqttReasonCode(error.reasonCode)
            if (mapped != null) {
                return mapped
            }
        }

        val causeMsg = error?.cause?.message?.trim().orEmpty()
        if (causeMsg.contains("UnknownHostException", ignoreCase = true) ||
            causeMsg.contains("No address associated", ignoreCase = true) ||
            causeMsg.contains("not known", ignoreCase = true)
        ) {
            return "No se pudo resolver el host MQTT"
        }
        if (causeMsg.contains("SSLHandshakeException", ignoreCase = true)) {
            return "Fallo TLS/SSL al conectar MQTT"
        }
        if (causeMsg.contains("Connection refused", ignoreCase = true) || causeMsg.contains("ECONNREFUSED", ignoreCase = true)) {
            return "El broker rechaz\u00f3 la conexi\u00f3n"
        }
        if (causeMsg.contains("timeout", ignoreCase = true)) {
            return "Tiempo de espera agotado al conectar MQTT"
        }
        if (causeMsg.contains("not authorized", ignoreCase = true) || causeMsg.contains("bad user", ignoreCase = true)) {
            return "Usuario o contrase\u00f1a MQTT incorrectos"
        }

        val msg = error?.message?.trim().orEmpty()
        if (msg.contains("UnknownHostException", ignoreCase = true)) {
            return "No se pudo resolver el host MQTT"
        }
        if (msg.contains("Connection refused", ignoreCase = true)) {
            return "El broker rechaz\u00f3 la conexi\u00f3n"
        }
        if (msg.contains("Timeout", ignoreCase = true)) {
            return "Tiempo de espera agotado al conectar MQTT"
        }
        if (msg.contains("not authorized", ignoreCase = true) || msg.contains("bad user", ignoreCase = true)) {
            return "Usuario o contrase\u00f1a MQTT incorrectos"
        }
        if (msg.isNotBlank()) {
            return "MQTT: $msg"
        }
        if (lastServerUri.isNotBlank()) {
            return "MQTT exception (sin detalle). Broker: $lastServerUri"
        }
        return "MQTT exception"
    }

    private fun mapMqttReasonCode(reasonCode: Int): String? = when (reasonCode) {
        MqttException.REASON_CODE_BROKER_UNAVAILABLE.toInt() -> "Broker MQTT no disponible"
        MqttException.REASON_CODE_CLIENT_EXCEPTION.toInt() -> "Error interno del cliente MQTT"
        MqttException.REASON_CODE_CLIENT_CONNECTED.toInt() -> "El cliente MQTT ya estaba conectado"
        MqttException.REASON_CODE_CLIENT_TIMEOUT.toInt() -> "Tiempo de espera agotado al conectar MQTT"
        MqttException.REASON_CODE_CONNECTION_LOST.toInt() -> "Conexi\u00f3n MQTT perdida"
        MqttException.REASON_CODE_FAILED_AUTHENTICATION.toInt() -> "Usuario o contrase\u00f1a MQTT incorrectos"
        MqttException.REASON_CODE_INVALID_CLIENT_ID.toInt() -> "Client ID MQTT inv\u00e1lido"
        MqttException.REASON_CODE_NOT_AUTHORIZED.toInt() -> "No autorizado en broker MQTT"
        MqttException.REASON_CODE_SERVER_CONNECT_ERROR.toInt() -> "No se pudo abrir conexi\u00f3n con broker MQTT"
        MqttException.REASON_CODE_SOCKET_FACTORY_MISMATCH.toInt() -> "Configuraci\u00f3n SSL/TLS MQTT invalida"
        MqttException.REASON_CODE_SSL_CONFIG_ERROR.toInt() -> "Error de Configuraci\u00f3n SSL/TLS MQTT"
        MqttException.REASON_CODE_WRITE_TIMEOUT.toInt() -> "Timeout al publicar en MQTT"
        else -> null
    }

    private fun describeThrowable(error: Throwable?): String {
        if (error == null) return "sin detalle"
        val parts = mutableListOf<String>()
        var current: Throwable? = error
        var depth = 0
        while (current != null && depth < 4) {
            parts += "${current::class.java.simpleName}(${current.message ?: "sin mensaje"})"
            current = current.cause
            depth++
        }
        return parts.joinToString(" -> ")
    }

    companion object {
        private const val TAG = "SENTNLDRIVE-MQTT"
    }
}
