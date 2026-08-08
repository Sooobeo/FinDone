package com.findone.app.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

object FinColors {
    val Canvas = Color(0xFFFBFCFB)
    val Paper = Color(0xFFF7F9F8)
    val Surface = Color(0xFFEEF3F2)
    val Ink = Color(0xFF162321)
    val InkSecondary = Color(0xFF435550)
    val Muted = Color(0xFF5A6B67)
    val Border = Color(0xFFCBD8D5)
    val OutlineStrong = Color(0xFF748B85)
    val Teal = Color(0xFF246B65)
    val TealDark = Color(0xFF18524E)
    val TealSoft = Color(0xFFDCECE8)
    val Blue = Color(0xFF335E85)
    val BlueSoft = Color(0xFFE2EAF2)
    val Violet = Color(0xFF66558B)
    val VioletSoft = Color(0xFFEAE5F2)
}

private val LightColors = lightColorScheme(
    primary = FinColors.Teal,
    onPrimary = Color.White,
    primaryContainer = FinColors.TealSoft,
    onPrimaryContainer = FinColors.TealDark,
    secondary = FinColors.Blue,
    onSecondary = Color.White,
    secondaryContainer = FinColors.BlueSoft,
    onSecondaryContainer = Color(0xFF173D5E),
    tertiary = FinColors.Violet,
    onTertiary = Color.White,
    tertiaryContainer = FinColors.VioletSoft,
    onTertiaryContainer = Color(0xFF3A2D58),
    background = FinColors.Canvas,
    onBackground = FinColors.Ink,
    surface = FinColors.Paper,
    onSurface = FinColors.Ink,
    surfaceVariant = FinColors.Surface,
    onSurfaceVariant = FinColors.InkSecondary,
    outline = FinColors.OutlineStrong,
    outlineVariant = FinColors.Border,
)

private val DarkColors = darkColorScheme(
    primary = Color(0xFF8FD4CB),
    onPrimary = Color(0xFF003733),
    primaryContainer = Color(0xFF0B514C),
    onPrimaryContainer = Color(0xFFAAEFE5),
    secondary = Color(0xFFA5C8ED),
    onSecondary = Color(0xFF043355),
    secondaryContainer = Color(0xFF234B70),
    onSecondaryContainer = Color(0xFFD2E7FF),
    tertiary = Color(0xFFD0BDEF),
    onTertiary = Color(0xFF382A50),
    tertiaryContainer = Color(0xFF4F4168),
    onTertiaryContainer = Color(0xFFEADDFF),
    background = Color(0xFF0F1514),
    onBackground = Color(0xFFE0E6E3),
    surface = Color(0xFF121A18),
    onSurface = Color(0xFFE0E6E3),
    surfaceVariant = Color(0xFF26312E),
    onSurfaceVariant = Color(0xFFC0CBC7),
    outline = Color(0xFF899A95),
    outlineVariant = Color(0xFF3A4945),
)

@Composable
fun FinDoneTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = if (isSystemInDarkTheme()) DarkColors else LightColors,
        content = content,
    )
}
