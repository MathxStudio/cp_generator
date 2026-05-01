package com.mathxstudio.cpgenerator.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable


private val AppColorScheme = lightColorScheme(
    primary = Terracotta,
    onPrimary = Paper,
    secondary = Teal,
    onSecondary = Paper,
    tertiary = Sage,
    background = AppBackground,
    onBackground = Ink,
    surface = AppCard,
    onSurface = Ink,
    surfaceVariant = AppCardAlt,
    onSurfaceVariant = InkSoft,
    outline = OutlineSoft,
)


@Composable
fun CPGeneratorTheme(
    content: @Composable () -> Unit,
) {
    MaterialTheme(
        colorScheme = AppColorScheme,
        typography = CPGeneratorTypography,
        content = content,
    )
}
