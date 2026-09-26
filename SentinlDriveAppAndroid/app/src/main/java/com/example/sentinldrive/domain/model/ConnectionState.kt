package com.example.sentinldrive.domain.model

enum class ConnectionState {
    DISCONNECTED,
    CONNECTING,
    CONNECTED,
    RECONNECTING,
    ERROR
}

enum class PendingStatus {
    PENDING,
    SENT,
    ERROR
}
