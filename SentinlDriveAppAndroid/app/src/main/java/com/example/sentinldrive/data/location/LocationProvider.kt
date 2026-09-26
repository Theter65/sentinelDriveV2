package com.example.sentinldrive.data.location

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.os.Handler
import android.os.HandlerThread
import android.os.Build
import android.os.Looper
import android.util.Log
import androidx.core.app.ActivityCompat
import com.example.sentinldrive.domain.model.LocationSnapshot
import com.google.android.gms.location.LocationCallback
import com.google.android.gms.location.LocationRequest
import com.google.android.gms.location.LocationResult
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

class LocationProvider(private val context: Context) {

    private val fusedClient = LocationServices.getFusedLocationProviderClient(context)
    private val locationManager = context.getSystemService(Context.LOCATION_SERVICE) as LocationManager

    private val _latest = MutableStateFlow(LocationSnapshot())
    val latest: StateFlow<LocationSnapshot> = _latest.asStateFlow()

    private var locationCallback: LocationCallback? = null
    private var frameworkListener: LocationListener? = null

    private val gpsHandlerThread = HandlerThread("SentinlDrive-GPS").apply { start() }
    private val gpsHandler = Handler(gpsHandlerThread.looper)

    fun start(): Boolean {
        if (!hasLocationPermission()) {
            Log.w(TAG, "No hay permisos de ubicacion")
            return false
        }
        if (!isLocationServiceEnabled()) {
            Log.w(TAG, "Servicio de ubicacion apagado en el dispositivo")
            return false
        }
        if (locationCallback != null || frameworkListener != null) return true

        val fusedStarted = startFusedUpdates()
        val frameworkStarted = if (fusedStarted) false else startFrameworkFallback()

        if (!fusedStarted && !frameworkStarted) {
            Log.w(TAG, "No se pudo iniciar ninguna fuente de ubicacion")
        }
        return fusedStarted || frameworkStarted
    }

    fun hasLocationPermissionGranted(): Boolean = hasLocationPermission()

    fun isLocationServiceEnabled(): Boolean {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            locationManager.isLocationEnabled
        } else {
            val gps = runCatching { locationManager.isProviderEnabled(LocationManager.GPS_PROVIDER) }.getOrDefault(false)
            val net = runCatching { locationManager.isProviderEnabled(LocationManager.NETWORK_PROVIDER) }.getOrDefault(false)
            gps || net
        }
    }

    fun stop() {
        val cb = locationCallback
        if (cb != null) {
            fusedClient.removeLocationUpdates(cb)
            locationCallback = null
        }

        val listener = frameworkListener
        if (listener != null) {
            runCatching { locationManager.removeUpdates(listener) }
            frameworkListener = null
        }
    }

    fun shutdown() {
        stop()
        gpsHandlerThread.quitSafely()
    }

    private fun startFusedUpdates(): Boolean {
        val request = LocationRequest.Builder(Priority.PRIORITY_HIGH_ACCURACY, 2_000)
            .setMinUpdateIntervalMillis(1_000)
            .build()

        locationCallback = object : LocationCallback() {
            override fun onLocationResult(result: LocationResult) {
                val loc = result.lastLocation ?: return
                publishLocation(loc)
            }
        }

        return try {
            fusedClient.requestLocationUpdates(request, locationCallback!!, gpsHandler.looper)
            fusedClient.lastLocation
                .addOnSuccessListener { loc ->
                    if (loc != null) {
                        publishLocation(loc)
                    } else {
                        Log.d(TAG, "lastLocation nula")
                    }
                }
                .addOnFailureListener { ex ->
                    Log.w(TAG, "Fallo lastLocation: ${ex.message}")
                }

            fusedClient.getCurrentLocation(Priority.PRIORITY_HIGH_ACCURACY, null)
                .addOnSuccessListener { loc ->
                    if (loc != null) {
                        publishLocation(loc)
                    }
                }
                .addOnFailureListener { ex ->
                    Log.w(TAG, "Fallo getCurrentLocation: ${ex.message}")
                }

            Log.i(TAG, "Ubicacion Fused iniciada")
            true
        } catch (security: SecurityException) {
            locationCallback = null
            Log.e(TAG, "SecurityException al iniciar Fused", security)
            false
        } catch (ex: Exception) {
            locationCallback = null
            Log.e(TAG, "Error al iniciar Fused", ex)
            false
        }
    }

    private fun startFrameworkFallback(): Boolean {
        frameworkListener = LocationListener { location ->
            publishLocation(location)
        }

        val providers = listOf(LocationManager.GPS_PROVIDER, LocationManager.NETWORK_PROVIDER)
        var atLeastOne = false
        for (provider in providers) {
            try {
                if (locationManager.isProviderEnabled(provider)) {
                    locationManager.requestLocationUpdates(
                        provider,
                        1_000L,
                        0f,
                        frameworkListener!!,
                        gpsHandler.looper,
                    )
                    atLeastOne = true
                    Log.i(TAG, "Ubicacion fallback activa en provider=$provider")
                }
            } catch (security: SecurityException) {
                Log.e(TAG, "SecurityException fallback provider=$provider", security)
            } catch (ex: Exception) {
                Log.w(TAG, "No se pudo iniciar fallback provider=$provider: ${ex.message}")
            }
        }

        if (!atLeastOne) {
            frameworkListener = null
        }
        return atLeastOne
    }

    private fun hasLocationPermission(): Boolean {
        val fine = ActivityCompat.checkSelfPermission(context, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED
        val coarse = ActivityCompat.checkSelfPermission(context, Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED
        return fine || coarse
    }

    private fun publishLocation(loc: Location) {
        if (isStale(loc)) {
            Log.d(TAG, "Ubicacion descartada por antiguedad: ageMs=${System.currentTimeMillis() - loc.time}")
            return
        }

        val speedKmh = extractSpeedKmh(loc)
        _latest.value = LocationSnapshot(
            lat = loc.latitude,
            lon = loc.longitude,
            speedKmh = speedKmh,
            accuracyMeters = if (loc.hasAccuracy()) loc.accuracy else null,
            timestampMillis = loc.time,
        )
    }

    private fun extractSpeedKmh(current: Location): Double? {
        if (current.hasSpeed()) {
            val speedKmh = current.speed.toDouble() * 3.6
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O &&
                current.hasSpeedAccuracy() &&
                current.speedAccuracyMetersPerSecond > MAX_SPEED_ACCURACY_MS
            ) {
                Log.d(TAG, "Velocidad GPS descartada por baja precision: accuracy=${current.speedAccuracyMetersPerSecond}")
                return null
            }
            return speedKmh.takeIf { it <= MAX_REALISTIC_BUS_SPEED_KMH }
        }
        return null
    }

    companion object {
        private const val TAG = "SentinlDrive-GPS"
        private const val MAX_LOCATION_AGE_MS = 3_000L
        private const val MAX_REALISTIC_BUS_SPEED_KMH = 160.0
        private const val MAX_SPEED_ACCURACY_MS = 10f

        private fun isStale(location: Location): Boolean {
            return location.time > 0L && System.currentTimeMillis() - location.time > MAX_LOCATION_AGE_MS
        }
    }
}
