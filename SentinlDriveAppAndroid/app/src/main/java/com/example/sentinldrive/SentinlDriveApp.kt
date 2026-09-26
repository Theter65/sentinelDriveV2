package com.example.sentinldrive

import android.app.Application
import com.example.sentinldrive.core.AppContainer

class SentinlDriveApp : Application() {
    lateinit var appContainer: AppContainer
        private set

    override fun onCreate() {
        super.onCreate()
        appContainer = AppContainer(this)
    }
}
