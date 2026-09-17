package com.pixsynq.app.ui.theme

import android.os.Build
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.dynamicDarkColorScheme
import androidx.compose.material3.dynamicLightColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext

private val Blue = Color(0xFF2563EB)
private val BlueLight = Color(0xFF3B82F6)

private val LightColors = lightColorScheme(
    primary = Blue,
    onPrimary = Color.White,
    surface = Color(0xFFFFFFFF),
    background = Color(0xFFF4F6F8),
    onSurfaceVariant = Color(0xFF5F6B7A),
)

private val DarkColors = darkColorScheme(
    primary = BlueLight,
    onPrimary = Color.White,
    surface = Color(0xFF1A2029),
    background = Color(0xFF12161C),
    onSurfaceVariant = Color(0xFF93A0B0),
)

@Composable
fun PixSynqTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    // Dynamic (Material You) color on Android 12+
    dynamicColor: Boolean = true,
    content: @Composable () -> Unit,
) {
    val colorScheme = when {
        dynamicColor && Build.VERSION.SDK_INT >= Build.VERSION_CODES.S -> {
            val context = LocalContext.current
            if (darkTheme) dynamicDarkColorScheme(context)
            else dynamicLightColorScheme(context)
        }
        darkTheme -> DarkColors
        else -> LightColors
    }
    MaterialTheme(
        colorScheme = colorScheme,
        content = content,
    )
}
