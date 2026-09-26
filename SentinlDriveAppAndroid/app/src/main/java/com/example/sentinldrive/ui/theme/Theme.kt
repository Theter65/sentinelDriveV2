package com.example.sentinldrive.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val DarkColorScheme = darkColorScheme(
    primary = SdAccentGreen,
    onPrimary = SdOnAccent,
    secondary = SdAccentCyan,
    tertiary = SdWarning,
    background = SdBg,
    onBackground = SdTextPrimary,
    surface = SdSurface,
    onSurface = SdTextPrimary,
    surfaceVariant = SdSurfaceStrong,
    onSurfaceVariant = SdTextSecondary,
    error = SdDanger,
)

private val LightColorScheme = lightColorScheme(
    primary = SdAccentGreen,
    onPrimary = SdOnAccent,
    secondary = SdAccentCyan,
    tertiary = SdWarning,
    background = Color(0xFFF4F7F9),
    onBackground = Color(0xFF0B1118),
    surface = Color(0xFFFFFFFF),
    onSurface = Color(0xFF0B1118),
    surfaceVariant = Color(0xFFE8EEF2),
    onSurfaceVariant = Color(0xFF405162),
    error = SdDanger,
)

@Composable
fun SentinlDriveTheme(
    darkTheme: Boolean = true,
    content: @Composable () -> Unit
) {
    val colorScheme = if (darkTheme) DarkColorScheme else LightColorScheme

    MaterialTheme(
        colorScheme = colorScheme,
        typography = Typography,
        content = content
    )
}
