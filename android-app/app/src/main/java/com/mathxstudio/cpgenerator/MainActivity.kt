package com.mathxstudio.cpgenerator

import android.app.Application
import android.app.DownloadManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.os.Environment
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.compose.animation.animateContentSize
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Slider
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import com.mathxstudio.cpgenerator.ui.theme.AppBackground
import com.mathxstudio.cpgenerator.ui.theme.AppCard
import com.mathxstudio.cpgenerator.ui.theme.AppCardAlt
import com.mathxstudio.cpgenerator.ui.theme.CPGeneratorTheme
import com.mathxstudio.cpgenerator.ui.theme.Graphite
import com.mathxstudio.cpgenerator.ui.theme.Ink
import com.mathxstudio.cpgenerator.ui.theme.InkSoft
import com.mathxstudio.cpgenerator.ui.theme.OutlineSoft
import com.mathxstudio.cpgenerator.ui.theme.Paper
import com.mathxstudio.cpgenerator.ui.theme.Sage
import com.mathxstudio.cpgenerator.ui.theme.Sand
import com.mathxstudio.cpgenerator.ui.theme.SandDeep
import com.mathxstudio.cpgenerator.ui.theme.Teal
import com.mathxstudio.cpgenerator.ui.theme.Terracotta
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import kotlin.math.cos
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt
import kotlin.math.sin

private const val UPDATE_REPOSITORY = "MathxStudio/cp_generator"
private const val UPDATE_API_URL = "https://api.github.com/repos/$UPDATE_REPOSITORY/releases/latest"
private const val DEFAULT_CAMERA_YAW = -0.55f
private const val DEFAULT_CAMERA_PITCH = 0.42f

class MainActivity : ComponentActivity() {
    private val viewModel by viewModels<MainViewModel> {
        MainViewModel.factory(application)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            CPGeneratorTheme {
                CpGeneratorApp(viewModel = viewModel)
            }
        }
    }
}

@Composable
private fun CpGeneratorApp(viewModel: MainViewModel) {
    val state by viewModel.uiState.collectAsStateWithLifecycle()

    Scaffold(
        containerColor = AppBackground,
        contentColor = Ink,
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(padding)
                .padding(horizontal = 20.dp, vertical = 18.dp),
            verticalArrangement = Arrangement.spacedBy(18.dp),
        ) {
            HeroCard(state = state)
            StageCard(
                state = state,
                onStageModeChanged = viewModel::setStageMode,
                onPreviewProgressChanged = viewModel::updatePreviewProgress,
                onCameraDrag = viewModel::adjustCamera,
                onResetCamera = viewModel::resetCamera,
            )
            ControlsCard(
                state = state,
                onPointCountChanged = viewModel::updatePointCount,
                onSearchAttemptsChanged = viewModel::updateSearchAttempts,
                onLocalRoundsChanged = viewModel::updateLocalRounds,
                onGenerate = viewModel::generatePattern,
                onRefine = viewModel::refinePattern,
                onAssign = viewModel::assignPattern,
                onAutoLocalGreen = viewModel::optimizeUntilLocalGreen,
                onAutoAllGreen = viewModel::autoAllGreen,
            )
            DiagnosticsCard(state = state)
            UpdateCard(
                update = state.update,
                busy = state.isBusy,
                onCheck = viewModel::checkForUpdates,
                onDownload = viewModel::downloadUpdate,
                onInstall = viewModel::installDownloadedUpdate,
                onOpenReleaseNotes = viewModel::openReleaseNotes,
            )
        }
    }
}

@Composable
private fun HeroCard(state: MainUiState) {
    val snapshot = state.snapshot
    val status = snapshot?.status ?: StatusBanner(
        title = "Preparing studio",
        message = "Generating a fresh sheet and loading the mobile preview pipeline.",
        tone = "neutral",
    )

    Surface(
        shape = RoundedCornerShape(30.dp),
        color = AppCard,
        shadowElevation = 8.dp,
        tonalElevation = 2.dp,
    ) {
        Column(
            modifier = Modifier.padding(22.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            StatusPill(label = "CP Generator for Android", tone = "neutral")
            Text(
                text = "Origami crease studio",
                style = MaterialTheme.typography.headlineLarge,
                color = Ink,
            )
            Text(
                text = snapshot?.subtitle ?: "A focused portrait workflow for sheet inspection, folding, and search automation.",
                style = MaterialTheme.typography.bodyLarge,
                color = InkSoft,
            )
            Surface(
                shape = RoundedCornerShape(22.dp),
                color = toneContainer(status.tone),
                contentColor = toneContent(status.tone),
            ) {
                Column(
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 14.dp),
                    verticalArrangement = Arrangement.spacedBy(4.dp),
                ) {
                    Text(
                        text = status.title,
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.SemiBold,
                    )
                    Text(
                        text = status.message,
                        style = MaterialTheme.typography.bodyMedium,
                    )
                }
            }
            snapshot?.automation?.let { automation ->
                AutomationSummary(automation = automation)
            }
            if (state.errorMessage != null) {
                Surface(
                    shape = RoundedCornerShape(20.dp),
                    color = toneContainer("danger"),
                    contentColor = toneContent("danger"),
                ) {
                    Text(
                        text = state.errorMessage,
                        modifier = Modifier.padding(horizontal = 16.dp, vertical = 12.dp),
                        style = MaterialTheme.typography.bodyMedium,
                    )
                }
            }
            if (state.isBusy) {
                LinearProgressIndicator(
                    modifier = Modifier.fillMaxWidth(),
                    color = Terracotta,
                    trackColor = Terracotta.copy(alpha = 0.18f),
                )
            }
        }
    }
}

@Composable
private fun AutomationSummary(automation: AutomationModel) {
    Surface(
        shape = RoundedCornerShape(20.dp),
        color = AppCardAlt,
        tonalElevation = 1.dp,
    ) {
        Column(
            modifier = Modifier.padding(horizontal = 14.dp, vertical = 12.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            Text(
                text = if (automation.kind == "all_green") "Automation search" else "Local automation",
                style = MaterialTheme.typography.labelLarge,
                color = Ink,
            )
            Text(
                text = "${automation.attempts}/${automation.maxAttempts} tries · ${automation.rounds}/${automation.maxRounds} rounds · ${automation.iterations} iterations",
                style = MaterialTheme.typography.bodySmall,
                color = InkSoft,
            )
        }
    }
}

@Composable
private fun StageCard(
    state: MainUiState,
    onStageModeChanged: (StageMode) -> Unit,
    onPreviewProgressChanged: (Float) -> Unit,
    onCameraDrag: (Float, Float) -> Unit,
    onResetCamera: () -> Unit,
) {
    val snapshot = state.snapshot
    val preview = snapshot?.preview
    val currentMode = if (preview == null) StageMode.SHEET else state.stageMode

    Surface(
        shape = RoundedCornerShape(30.dp),
        color = AppCard,
        shadowElevation = 8.dp,
        tonalElevation = 2.dp,
    ) {
        Column(
            modifier = Modifier.padding(18.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column(
                    modifier = Modifier.weight(1f),
                    verticalArrangement = Arrangement.spacedBy(4.dp),
                ) {
                    Text(
                        text = if (currentMode == StageMode.SHEET) "Crease sheet" else "Folded figure",
                        style = MaterialTheme.typography.titleLarge,
                        color = Ink,
                    )
                    Text(
                        text = when {
                            currentMode == StageMode.PREVIEW && preview != null -> preview.message
                            snapshot != null -> snapshot.summary
                            else -> "The mobile layout keeps the geometry front and center."
                        },
                        style = MaterialTheme.typography.bodyMedium,
                        color = InkSoft,
                        maxLines = 3,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    ToggleChip(
                        label = "2D",
                        selected = currentMode == StageMode.SHEET,
                        onClick = { onStageModeChanged(StageMode.SHEET) },
                    )
                    ToggleChip(
                        label = "3D",
                        selected = currentMode == StageMode.PREVIEW,
                        enabled = preview != null,
                        onClick = { onStageModeChanged(StageMode.PREVIEW) },
                    )
                }
            }

            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .aspectRatio(1f)
                    .background(AppCardAlt),
            ) {
                when {
                    snapshot == null -> EmptyStage("No crease sheet yet")
                    currentMode == StageMode.PREVIEW && preview != null -> FoldPreviewStage(
                        preview = preview,
                        progress = state.previewProgress,
                        yaw = state.cameraYaw,
                        pitch = state.cameraPitch,
                        onCameraDrag = onCameraDrag,
                    )
                    else -> PatternStage(stage = snapshot.stage)
                }
            }

            if (currentMode == StageMode.SHEET) {
                LegendRow()
            } else {
                PreviewControls(
                    preview = preview,
                    progress = state.previewProgress,
                    onProgressChanged = onPreviewProgressChanged,
                    onResetCamera = onResetCamera,
                )
            }

            snapshot?.stats?.let { stats ->
                StatsRow(stats = stats)
            }
        }
    }
}

@Composable
private fun ToggleChip(
    label: String,
    selected: Boolean,
    enabled: Boolean = true,
    onClick: () -> Unit,
) {
    if (selected) {
        FilledTonalButton(
            onClick = onClick,
            enabled = enabled,
            shape = RoundedCornerShape(18.dp),
            colors = ButtonDefaults.filledTonalButtonColors(
                containerColor = Ink,
                contentColor = Paper,
            ),
            contentPadding = PaddingValues(horizontal = 14.dp, vertical = 10.dp),
        ) {
            Text(label)
        }
    } else {
        OutlinedButton(
            onClick = onClick,
            enabled = enabled,
            shape = RoundedCornerShape(18.dp),
            contentPadding = PaddingValues(horizontal = 14.dp, vertical = 10.dp),
        ) {
            Text(label)
        }
    }
}

@Composable
private fun EmptyStage(message: String) {
    Box(
        modifier = Modifier.fillMaxSize(),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            text = message,
            style = MaterialTheme.typography.titleMedium,
            color = InkSoft,
        )
    }
}

@Composable
private fun PatternStage(stage: StageModel) {
    Canvas(
        modifier = Modifier
            .fillMaxSize()
            .padding(12.dp),
    ) {
        val squareSize = min(size.width, size.height) * 0.88f
        val left = (size.width - squareSize) * 0.5f
        val top = (size.height - squareSize) * 0.5f
        val paperTopLeft = Offset(left, top)
        val paperSize = Size(squareSize, squareSize)

        drawRect(
            color = Paper,
            topLeft = paperTopLeft,
            size = paperSize,
        )
        drawRect(
            color = OutlineSoft,
            topLeft = paperTopLeft,
            size = paperSize,
            style = Stroke(width = squareSize * 0.008f),
        )

        val neutralStroke = squareSize * 0.008f
        val accentStroke = squareSize * 0.010f

        fun project(x: Float, y: Float): Offset {
            return Offset(
                x = left + x * squareSize,
                y = top + y * squareSize,
            )
        }

        stage.folds.filter { it.type == -1 }.forEach { fold ->
            drawLine(
                color = Graphite.copy(alpha = 0.72f),
                start = project(fold.x1, fold.y1),
                end = project(fold.x2, fold.y2),
                strokeWidth = neutralStroke,
                cap = StrokeCap.Round,
            )
        }

        stage.folds.filter { it.type != -1 }.forEach { fold ->
            drawLine(
                color = when (fold.type) {
                    0 -> Terracotta
                    1 -> Teal
                    else -> Graphite
                },
                start = project(fold.x1, fold.y1),
                end = project(fold.x2, fold.y2),
                strokeWidth = accentStroke,
                cap = StrokeCap.Round,
            )
        }

        stage.vertices.filter { !it.onEdge }.forEach { vertex ->
            drawCircle(
                color = Ink.copy(alpha = 0.86f),
                radius = squareSize * 0.010f,
                center = project(vertex.x, vertex.y),
            )
        }
    }
}

@Composable
private fun FoldPreviewStage(
    preview: PreviewModel,
    progress: Float,
    yaw: Float,
    pitch: Float,
    onCameraDrag: (Float, Float) -> Unit,
) {
    Canvas(
        modifier = Modifier
            .fillMaxSize()
            .padding(12.dp)
            .pointerInput(preview, yaw, pitch, progress) {
                detectDragGestures { change, dragAmount ->
                    change.consume()
                    onCameraDrag(dragAmount.x, dragAmount.y)
                }
            },
    ) {
        drawRect(color = Paper)

        val faces = interpolatePreviewFaces(preview, progress)
        if (faces.isEmpty()) {
            return@Canvas
        }

        val bounds = preview.bounds
        val centerX = (bounds.minX + bounds.maxX) * 0.5f
        val centerY = (bounds.minY + bounds.maxY) * 0.5f
        val centerZ = (bounds.minZ + bounds.maxZ) * 0.5f
        val span = max(
            max(bounds.maxX - bounds.minX, bounds.maxY - bounds.minY),
            max(bounds.maxZ - bounds.minZ, 1f),
        ).coerceAtLeast(1f)

        val rotatedFaces = faces.map { face ->
            val points = face.points.map { point ->
                val nx = (point.x - centerX) / span
                val ny = (point.y - centerY) / span
                val nz = (point.z - centerZ) / span
                rotatePoint(nx, ny, nz, yaw, pitch)
            }
            val averageDepth = points.map { it.z }.average().toFloat()
            RenderFace(points = points, topSurface = face.topSurface, depth = averageDepth)
        }.sortedBy { it.depth }

        val projectedAll = rotatedFaces.flatMap { face ->
            face.points.map { point ->
                projectPoint(point)
            }
        }
        if (projectedAll.isEmpty()) {
            return@Canvas
        }

        val minXProjected = projectedAll.minOf { it.x }
        val maxXProjected = projectedAll.maxOf { it.x }
        val minYProjected = projectedAll.minOf { it.y }
        val maxYProjected = projectedAll.maxOf { it.y }
        val projectedWidth = (maxXProjected - minXProjected).coerceAtLeast(0.2f)
        val projectedHeight = (maxYProjected - minYProjected).coerceAtLeast(0.2f)
        val scale = min(size.width * 0.76f / projectedWidth, size.height * 0.76f / projectedHeight)
        val offsetX = (size.width - projectedWidth * scale) * 0.5f - minXProjected * scale
        val offsetY = (size.height - projectedHeight * scale) * 0.5f - minYProjected * scale

        rotatedFaces.forEach { face ->
            val depthT = ((face.depth + 1f) / 2f).coerceIn(0f, 1f)
            val fillColor = if (face.topSurface) {
                lerpColor(Paper, Sand, depthT * 0.35f)
            } else {
                lerpColor(Sand, SandDeep, 0.35f + depthT * 0.25f)
            }
            val strokeColor = if (face.topSurface) Ink.copy(alpha = 0.42f) else Graphite.copy(alpha = 0.52f)
            val path = Path()
            face.points.forEachIndexed { index, point ->
                val projected = projectPoint(point)
                val canvasPoint = Offset(
                    x = projected.x * scale + offsetX,
                    y = projected.y * scale + offsetY,
                )
                if (index == 0) {
                    path.moveTo(canvasPoint.x, canvasPoint.y)
                } else {
                    path.lineTo(canvasPoint.x, canvasPoint.y)
                }
            }
            path.close()
            drawPath(path = path, color = fillColor)
            drawPath(
                path = path,
                color = strokeColor,
                style = Stroke(width = 1.4.dp.toPx()),
            )
        }
    }
}

@Composable
private fun PreviewControls(
    preview: PreviewModel?,
    progress: Float,
    onProgressChanged: (Float) -> Unit,
    onResetCamera: () -> Unit,
) {
    if (preview == null) {
        Text(
            text = "Assign folds to unlock the folded figure preview.",
            style = MaterialTheme.typography.bodySmall,
            color = InkSoft,
        )
        return
    }

    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text = when (preview.mode) {
                    "exact" -> "Exact fold stack"
                    "mesh" -> "Mesh fallback"
                    "scripted" -> "Authored sample finish"
                    else -> "Preview unavailable"
                },
                style = MaterialTheme.typography.bodyMedium,
                color = Ink,
            )
            OutlinedButton(
                onClick = onResetCamera,
                shape = RoundedCornerShape(18.dp),
                contentPadding = PaddingValues(horizontal = 14.dp, vertical = 10.dp),
            ) {
                Text("Reset view")
            }
        }
        Text(
            text = "Drag on the figure to rotate it, or scrub the fold progress below.",
            style = MaterialTheme.typography.bodySmall,
            color = InkSoft,
        )
        Slider(
            value = progress,
            onValueChange = onProgressChanged,
            valueRange = 0f..1f,
        )
    }
}

private fun rotatePoint(x: Float, y: Float, z: Float, yaw: Float, pitch: Float): Point3 {
    val yawCos = cos(yaw)
    val yawSin = sin(yaw)
    val pitchCos = cos(pitch)
    val pitchSin = sin(pitch)

    val x1 = x * yawCos + z * yawSin
    val z1 = -x * yawSin + z * yawCos
    val y1 = y * pitchCos - z1 * pitchSin
    val z2 = y * pitchSin + z1 * pitchCos
    return Point3(x1, y1, z2)
}

private fun projectPoint(point: Point3): Offset {
    val depth = 1.45f - point.z * 0.55f
    val perspective = 1f / depth.coerceAtLeast(0.55f)
    return Offset(
        x = point.x * perspective,
        y = -point.y * perspective,
    )
}

private fun lerpColor(start: Color, end: Color, t: Float): Color {
    val clamped = t.coerceIn(0f, 1f)
    return Color(
        red = start.red + (end.red - start.red) * clamped,
        green = start.green + (end.green - start.green) * clamped,
        blue = start.blue + (end.blue - start.blue) * clamped,
        alpha = start.alpha + (end.alpha - start.alpha) * clamped,
    )
}

private fun interpolatePreviewFaces(preview: PreviewModel, progress: Float): List<PreviewFace> {
    if (preview.frames.isEmpty()) {
        return emptyList()
    }
    if (preview.frames.size == 1) {
        return preview.frames.first().faces
    }

    val clamped = progress.coerceIn(0f, 1f)
    val scaled = clamped * (preview.frames.size - 1)
    val lowerIndex = scaled.toInt().coerceIn(0, preview.frames.lastIndex)
    val upperIndex = (lowerIndex + 1).coerceIn(0, preview.frames.lastIndex)
    val fraction = (scaled - lowerIndex).coerceIn(0f, 1f)
    val lower = preview.frames[lowerIndex]
    val upper = preview.frames[upperIndex]

    return lower.faces.zip(upper.faces).map { (left, right) ->
        PreviewFace(
            index = left.index,
            topSurface = left.topSurface,
            points = left.points.zip(right.points).map { (a, b) ->
                Point3(
                    x = a.x + (b.x - a.x) * fraction,
                    y = a.y + (b.y - a.y) * fraction,
                    z = a.z + (b.z - a.z) * fraction,
                )
            },
        )
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun LegendRow() {
    @Composable
    fun LegendItem(label: String, swatch: Color) {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Box(
                modifier = Modifier
                    .size(width = 18.dp, height = 4.dp)
                    .background(swatch),
            )
            Text(
                text = label,
                style = MaterialTheme.typography.bodySmall,
                color = InkSoft,
            )
        }
    }

    FlowRow(
        horizontalArrangement = Arrangement.spacedBy(14.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        LegendItem(label = "Mountain", swatch = Terracotta)
        LegendItem(label = "Valley", swatch = Teal)
        LegendItem(label = "Undecided", swatch = Graphite.copy(alpha = 0.72f))
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun StatsRow(stats: StatsModel) {
    FlowRow(
        horizontalArrangement = Arrangement.spacedBy(12.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        StatTile(label = "Vertices", value = stats.vertices.toString())
        StatTile(label = "Folds", value = stats.folds.toString())
        StatTile(label = "Assigned", value = stats.assignedFolds.toString())
        StatTile(label = "Faces", value = stats.faceCount?.toString() ?: "—")
    }
}

@Composable
private fun StatTile(label: String, value: String) {
    Surface(
        shape = RoundedCornerShape(22.dp),
        color = AppCardAlt,
        tonalElevation = 1.dp,
        modifier = Modifier.animateContentSize(),
    ) {
        Column(
            modifier = Modifier.padding(horizontal = 14.dp, vertical = 12.dp),
            verticalArrangement = Arrangement.spacedBy(2.dp),
        ) {
            Text(
                text = value,
                style = MaterialTheme.typography.titleLarge,
                color = Ink,
            )
            Text(
                text = label,
                style = MaterialTheme.typography.bodySmall,
                color = InkSoft,
            )
        }
    }
}

@Composable
private fun ControlsCard(
    state: MainUiState,
    onPointCountChanged: (Float) -> Unit,
    onSearchAttemptsChanged: (Float) -> Unit,
    onLocalRoundsChanged: (Float) -> Unit,
    onGenerate: () -> Unit,
    onRefine: () -> Unit,
    onAssign: () -> Unit,
    onAutoLocalGreen: () -> Unit,
    onAutoAllGreen: () -> Unit,
) {
    val snapshot = state.snapshot
    val hasPattern = snapshot != null

    Surface(
        shape = RoundedCornerShape(30.dp),
        color = AppCard,
        shadowElevation = 8.dp,
        tonalElevation = 2.dp,
    ) {
        Column(
            modifier = Modifier.padding(18.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Text(
                text = "Controls",
                style = MaterialTheme.typography.titleLarge,
                color = Ink,
            )
            Text(
                text = "The mobile build keeps the core desktop flow: generate, refine, assign, preview, and search for a clean all-green sheet.",
                style = MaterialTheme.typography.bodyMedium,
                color = InkSoft,
            )

            Surface(
                shape = RoundedCornerShape(24.dp),
                color = AppCardAlt,
            ) {
                Column(
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 14.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    LabeledSlider(
                        title = "Random interior points",
                        valueLabel = state.pointCount.toString(),
                        value = state.pointCount.toFloat(),
                        onValueChange = onPointCountChanged,
                        enabled = !state.isBusy,
                        valueRange = 0f..18f,
                        steps = 17,
                    )
                    LabeledSlider(
                        title = "Search tries",
                        valueLabel = state.searchAttempts.toString(),
                        value = state.searchAttempts.toFloat(),
                        onValueChange = onSearchAttemptsChanged,
                        enabled = !state.isBusy,
                        valueRange = 1f..24f,
                        steps = 22,
                    )
                    LabeledSlider(
                        title = "Local rounds",
                        valueLabel = state.localRounds.toString(),
                        value = state.localRounds.toFloat(),
                        onValueChange = onLocalRoundsChanged,
                        enabled = !state.isBusy,
                        valueRange = 1f..12f,
                        steps = 10,
                    )
                }
            }

            Row(
                modifier = Modifier.fillMaxWidth(),
            ) {
                Button(
                    onClick = onGenerate,
                    enabled = !state.isBusy,
                    shape = RoundedCornerShape(22.dp),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = Terracotta,
                        contentColor = Paper,
                    ),
                    contentPadding = PaddingValues(horizontal = 18.dp, vertical = 14.dp),
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Text("Randomize")
                }
            }

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                FilledTonalButton(
                    onClick = onRefine,
                    enabled = !state.isBusy && hasPattern,
                    shape = RoundedCornerShape(22.dp),
                    colors = ButtonDefaults.filledTonalButtonColors(
                        containerColor = Sand,
                        contentColor = Ink,
                    ),
                    contentPadding = PaddingValues(horizontal = 18.dp, vertical = 14.dp),
                    modifier = Modifier.weight(1f),
                ) {
                    Text("Refine")
                }
                OutlinedButton(
                    onClick = onAssign,
                    enabled = !state.isBusy && hasPattern,
                    shape = RoundedCornerShape(22.dp),
                    contentPadding = PaddingValues(horizontal = 18.dp, vertical = 14.dp),
                    modifier = Modifier.weight(1f),
                ) {
                    Text("Assign")
                }
            }

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                FilledTonalButton(
                    onClick = onAutoLocalGreen,
                    enabled = !state.isBusy && hasPattern,
                    shape = RoundedCornerShape(22.dp),
                    colors = ButtonDefaults.filledTonalButtonColors(
                        containerColor = Teal.copy(alpha = 0.16f),
                        contentColor = Teal,
                    ),
                    contentPadding = PaddingValues(horizontal = 18.dp, vertical = 14.dp),
                    modifier = Modifier.weight(1f),
                ) {
                    Text("Auto local")
                }
                Button(
                    onClick = onAutoAllGreen,
                    enabled = !state.isBusy,
                    shape = RoundedCornerShape(22.dp),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = Ink,
                        contentColor = Paper,
                    ),
                    contentPadding = PaddingValues(horizontal = 18.dp, vertical = 14.dp),
                    modifier = Modifier.weight(1f),
                ) {
                    Text("Auto all green")
                }
            }
        }
    }
}

@Composable
private fun LabeledSlider(
    title: String,
    valueLabel: String,
    value: Float,
    onValueChange: (Float) -> Unit,
    enabled: Boolean,
    valueRange: ClosedFloatingPointRange<Float>,
    steps: Int,
) {
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text = title,
                style = MaterialTheme.typography.titleMedium,
                color = Ink,
            )
            StatusPill(label = valueLabel, tone = "neutral")
        }
        Slider(
            value = value,
            onValueChange = onValueChange,
            enabled = enabled,
            valueRange = valueRange,
            steps = steps,
        )
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun DiagnosticsCard(state: MainUiState) {
    val snapshot = state.snapshot

    Surface(
        shape = RoundedCornerShape(30.dp),
        color = AppCard,
        shadowElevation = 8.dp,
        tonalElevation = 2.dp,
    ) {
        Column(
            modifier = Modifier.padding(18.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Text(
                text = "Diagnostics",
                style = MaterialTheme.typography.titleLarge,
                color = Ink,
            )
            FlowRow(
                horizontalArrangement = Arrangement.spacedBy(10.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                snapshot?.diagnostics?.forEach { diagnostic ->
                    StatusPill(
                        label = "${diagnostic.label} ${diagnostic.status.uppercase()}",
                        tone = diagnostic.tone,
                    )
                }
            }
            snapshot?.diagnostics?.forEach { diagnostic ->
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(10.dp),
                    verticalAlignment = Alignment.Top,
                ) {
                    Box(
                        modifier = Modifier
                            .padding(top = 6.dp)
                            .size(9.dp)
                            .background(toneContent(diagnostic.tone), CircleShape),
                    )
                    Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        Text(
                            text = diagnostic.label,
                            style = MaterialTheme.typography.titleSmall,
                            color = Ink,
                        )
                        Text(
                            text = diagnostic.message,
                            style = MaterialTheme.typography.bodyMedium,
                            color = InkSoft,
                        )
                    }
                }
            }
            Text(
                text = snapshot?.note
                    ?: "The mobile build now includes the same core search and preview loop as the desktop workflow.",
                style = MaterialTheme.typography.bodyMedium,
                color = InkSoft,
            )
        }
    }
}

@Composable
private fun UpdateCard(
    update: UpdateUiState,
    busy: Boolean,
    onCheck: () -> Unit,
    onDownload: () -> Unit,
    onInstall: () -> Unit,
    onOpenReleaseNotes: () -> Unit,
) {
    Surface(
        shape = RoundedCornerShape(30.dp),
        color = AppCard,
        shadowElevation = 8.dp,
        tonalElevation = 2.dp,
    ) {
        Column(
            modifier = Modifier.padding(18.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            Text(
                text = "Updates",
                style = MaterialTheme.typography.titleLarge,
                color = Ink,
            )
            Text(
                text = "The app can check the GitHub release channel, download a newer APK, and hand it to Android's installer.",
                style = MaterialTheme.typography.bodyMedium,
                color = InkSoft,
            )
            Surface(
                shape = RoundedCornerShape(22.dp),
                color = toneContainer(update.tone),
                contentColor = toneContent(update.tone),
            ) {
                Column(
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 14.dp),
                    verticalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    Text(
                        text = "Current version ${update.currentVersion}",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.SemiBold,
                    )
                    Text(
                        text = update.message,
                        style = MaterialTheme.typography.bodyMedium,
                    )
                    update.latestVersion?.let { latest ->
                        Text(
                            text = "Latest release $latest",
                            style = MaterialTheme.typography.bodySmall,
                        )
                    }
                }
            }
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                FilledTonalButton(
                    onClick = onCheck,
                    enabled = !busy && !update.isChecking,
                    shape = RoundedCornerShape(22.dp),
                    colors = ButtonDefaults.filledTonalButtonColors(
                        containerColor = Sand,
                        contentColor = Ink,
                    ),
                    contentPadding = PaddingValues(horizontal = 18.dp, vertical = 14.dp),
                    modifier = Modifier.weight(1f),
                ) {
                    Text(if (update.isChecking) "Checking..." else "Check now")
                }
                when {
                    update.readyToInstall -> Button(
                        onClick = onInstall,
                        enabled = !busy,
                        shape = RoundedCornerShape(22.dp),
                        colors = ButtonDefaults.buttonColors(
                            containerColor = Sage,
                            contentColor = Paper,
                        ),
                        contentPadding = PaddingValues(horizontal = 18.dp, vertical = 14.dp),
                        modifier = Modifier.weight(1f),
                    ) {
                        Text("Install update")
                    }

                    update.canDownload -> Button(
                        onClick = onDownload,
                        enabled = !busy && !update.isDownloading,
                        shape = RoundedCornerShape(22.dp),
                        colors = ButtonDefaults.buttonColors(
                            containerColor = Terracotta,
                            contentColor = Paper,
                        ),
                        contentPadding = PaddingValues(horizontal = 18.dp, vertical = 14.dp),
                        modifier = Modifier.weight(1f),
                    ) {
                        Text(if (update.isDownloading) "Downloading..." else "Download APK")
                    }

                    else -> OutlinedButton(
                        onClick = onOpenReleaseNotes,
                        enabled = update.releaseUrl != null,
                        shape = RoundedCornerShape(22.dp),
                        contentPadding = PaddingValues(horizontal = 18.dp, vertical = 14.dp),
                        modifier = Modifier.weight(1f),
                    ) {
                        Text("Release notes")
                    }
                }
            }
        }
    }
}

@Composable
private fun StatusPill(label: String, tone: String) {
    Surface(
        shape = RoundedCornerShape(999.dp),
        color = toneContainer(tone),
        contentColor = toneContent(tone),
    ) {
        Text(
            text = label,
            modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp),
            style = MaterialTheme.typography.labelLarge,
        )
    }
}

private fun toneContainer(tone: String): Color {
    return when (tone) {
        "success" -> Sage.copy(alpha = 0.18f)
        "warning" -> Terracotta.copy(alpha = 0.16f)
        "danger" -> Color(0xFFF3D8D1)
        else -> Sand
    }
}

private fun toneContent(tone: String): Color {
    return when (tone) {
        "success" -> Sage
        "warning" -> Terracotta
        "danger" -> Color(0xFF9E3E2D)
        else -> InkSoft
    }
}

enum class StageMode {
    SHEET,
    PREVIEW,
}

data class MainUiState(
    val pointCount: Int = 8,
    val searchAttempts: Int = 12,
    val localRounds: Int = 6,
    val snapshot: MobileSnapshot? = null,
    val isBusy: Boolean = false,
    val errorMessage: String? = null,
    val stageMode: StageMode = StageMode.SHEET,
    val previewProgress: Float = 1f,
    val cameraYaw: Float = DEFAULT_CAMERA_YAW,
    val cameraPitch: Float = DEFAULT_CAMERA_PITCH,
    val update: UpdateUiState = UpdateUiState(),
)

data class MobileSnapshot(
    val patternJson: String,
    val title: String,
    val subtitle: String,
    val summary: String,
    val note: String,
    val pointCount: Int?,
    val status: StatusBanner,
    val stats: StatsModel,
    val diagnostics: List<DiagnosticModel>,
    val stage: StageModel,
    val preview: PreviewModel?,
    val automation: AutomationModel?,
)

data class StatusBanner(
    val title: String,
    val message: String,
    val tone: String,
)

data class StatsModel(
    val vertices: Int,
    val folds: Int,
    val interiorVertices: Int,
    val assignedFolds: Int,
    val unassignedFolds: Int,
    val faceCount: Int?,
)

data class DiagnosticModel(
    val key: String,
    val label: String,
    val status: String,
    val message: String,
    val tone: String,
)

data class StageModel(
    val folds: List<FoldLine>,
    val vertices: List<StageVertex>,
)

data class FoldLine(
    val x1: Float,
    val y1: Float,
    val x2: Float,
    val y2: Float,
    val type: Int,
)

data class StageVertex(
    val x: Float,
    val y: Float,
    val onEdge: Boolean,
)

data class AutomationModel(
    val kind: String,
    val found: Boolean,
    val attempts: Int,
    val maxAttempts: Int,
    val rounds: Int,
    val maxRounds: Int,
    val iterations: Int,
    val loss: Double?,
)

data class PreviewModel(
    val mode: String,
    val message: String,
    val faceCount: Int?,
    val usesProvisionalSigns: Boolean,
    val usesApproximateCycles: Boolean,
    val cycleDrift: Double?,
    val isMeshApproximation: Boolean,
    val bounds: PreviewBounds,
    val frames: List<PreviewFrame>,
)

data class PreviewBounds(
    val minX: Float,
    val maxX: Float,
    val minY: Float,
    val maxY: Float,
    val minZ: Float,
    val maxZ: Float,
)

data class PreviewFrame(
    val progress: Float,
    val faces: List<PreviewFace>,
)

data class PreviewFace(
    val index: Int,
    val points: List<Point3>,
    val topSurface: Boolean,
)

data class Point3(
    val x: Float,
    val y: Float,
    val z: Float,
)

private data class RenderFace(
    val points: List<Point3>,
    val topSurface: Boolean,
    val depth: Float,
)

data class UpdateUiState(
    val currentVersion: String = "0.2.1",
    val latestVersion: String? = null,
    val message: String = "Check the release channel when you want to look for a newer APK.",
    val tone: String = "neutral",
    val releaseUrl: String? = null,
    val downloadUrl: String? = null,
    val isChecking: Boolean = false,
    val isDownloading: Boolean = false,
    val readyToInstall: Boolean = false,
    val downloadId: Long? = null,
) {
    val canDownload: Boolean
        get() = downloadUrl != null && !readyToInstall
}

class MainViewModel(application: Application) : AndroidViewModel(application) {
    private val repository = MobileBridgeRepository(application)
    private val updater = AppUpdateRepository(application)
    private val _uiState = MutableStateFlow(
        MainUiState(
            update = UpdateUiState(currentVersion = updater.currentVersionName()),
        ),
    )
    val uiState: StateFlow<MainUiState> = _uiState

    private var downloadPollJob: Job? = null

    init {
        generatePattern()
    }

    fun updatePointCount(value: Float) {
        _uiState.update { state ->
            state.copy(pointCount = value.roundToInt())
        }
    }

    fun updateSearchAttempts(value: Float) {
        _uiState.update { state ->
            state.copy(searchAttempts = value.roundToInt().coerceAtLeast(1))
        }
    }

    fun updateLocalRounds(value: Float) {
        _uiState.update { state ->
            state.copy(localRounds = value.roundToInt().coerceAtLeast(1))
        }
    }

    fun setStageMode(mode: StageMode) {
        _uiState.update { it.copy(stageMode = mode) }
    }

    fun updatePreviewProgress(value: Float) {
        _uiState.update { it.copy(previewProgress = value.coerceIn(0f, 1f)) }
    }

    fun adjustCamera(deltaX: Float, deltaY: Float) {
        _uiState.update { state ->
            state.copy(
                cameraYaw = (state.cameraYaw + deltaX * 0.01f).coerceIn(-1.75f, 1.75f),
                cameraPitch = (state.cameraPitch + deltaY * 0.01f).coerceIn(-1.1f, 1.1f),
            )
        }
    }

    fun resetCamera() {
        _uiState.update {
            it.copy(
                cameraYaw = DEFAULT_CAMERA_YAW,
                cameraPitch = DEFAULT_CAMERA_PITCH,
            )
        }
    }

    fun generatePattern() {
        launchOperation {
            repository.buildRandomPattern(_uiState.value.pointCount)
        }
    }

    fun refinePattern() {
        val patternJson = _uiState.value.snapshot?.patternJson ?: return
        launchOperation {
            repository.optimizePattern(patternJson)
        }
    }

    fun optimizeUntilLocalGreen() {
        val patternJson = _uiState.value.snapshot?.patternJson ?: return
        val rounds = _uiState.value.localRounds
        launchOperation {
            repository.optimizeUntilLocalGreen(patternJson, rounds)
        }
    }

    fun assignPattern() {
        val patternJson = _uiState.value.snapshot?.patternJson ?: return
        launchOperation {
            repository.assignPattern(patternJson)
        }
    }

    fun autoAllGreen() {
        val state = _uiState.value
        launchOperation {
            repository.autoAllGreen(
                pointCount = state.pointCount,
                maxAttempts = state.searchAttempts,
                maxLocalRounds = state.localRounds,
            )
        }
    }

    fun checkForUpdates() {
        if (_uiState.value.update.isChecking) {
            return
        }
        viewModelScope.launch {
            _uiState.update {
                it.copy(update = it.update.copy(isChecking = true, message = "Checking the latest GitHub release...", tone = "neutral"))
            }
            val result = withContext(Dispatchers.IO) {
                updater.checkForUpdates()
            }
            _uiState.update {
                it.copy(
                    update = result.toUiState(currentVersion = updater.currentVersionName()),
                )
            }
        }
    }

    fun downloadUpdate() {
        val url = _uiState.value.update.downloadUrl ?: return
        if (_uiState.value.update.isDownloading) {
            return
        }
        viewModelScope.launch {
            val downloadId = withContext(Dispatchers.IO) {
                updater.startDownload(url)
            }
            _uiState.update {
                it.copy(
                    update = it.update.copy(
                        isDownloading = true,
                        readyToInstall = false,
                        downloadId = downloadId,
                        message = "Downloading the latest APK. Android will keep it in the app's downloads area.",
                        tone = "warning",
                    ),
                )
            }
            pollForDownloadedUpdate(downloadId)
        }
    }

    fun installDownloadedUpdate() {
        val downloadId = _uiState.value.update.downloadId ?: return
        updater.installDownloadedApk(downloadId)
    }

    fun openReleaseNotes() {
        val url = _uiState.value.update.releaseUrl ?: return
        updater.openUrl(url)
    }

    private fun launchOperation(block: suspend () -> MobileSnapshot) {
        if (_uiState.value.isBusy) {
            return
        }
        viewModelScope.launch {
            _uiState.update { it.copy(isBusy = true, errorMessage = null) }
            try {
                val snapshot = withContext(Dispatchers.Default) {
                    block()
                }
                _uiState.update { state ->
                    state.copy(
                        snapshot = snapshot,
                        isBusy = false,
                        errorMessage = null,
                        stageMode = if (snapshot.preview != null) StageMode.PREVIEW else StageMode.SHEET,
                        previewProgress = if (snapshot.preview != null) 1f else 0f,
                        cameraYaw = DEFAULT_CAMERA_YAW,
                        cameraPitch = DEFAULT_CAMERA_PITCH,
                    )
                }
            } catch (exc: Throwable) {
                _uiState.update {
                    it.copy(
                        isBusy = false,
                        errorMessage = exc.message ?: "The Android bridge failed unexpectedly.",
                    )
                }
            }
        }
    }

    private fun pollForDownloadedUpdate(downloadId: Long) {
        downloadPollJob?.cancel()
        downloadPollJob = viewModelScope.launch {
            while (true) {
                when (val status = withContext(Dispatchers.IO) { updater.queryDownload(downloadId) }) {
                    is DownloadStatus.Pending -> delay(1200)
                    is DownloadStatus.Success -> {
                        _uiState.update {
                            it.copy(
                                update = it.update.copy(
                                    isDownloading = false,
                                    readyToInstall = true,
                                    downloadId = downloadId,
                                    message = "The APK is downloaded and ready to hand off to Android's installer.",
                                    tone = "success",
                                ),
                            )
                        }
                        return@launch
                    }

                    is DownloadStatus.Failed -> {
                        _uiState.update {
                            it.copy(
                                update = it.update.copy(
                                    isDownloading = false,
                                    readyToInstall = false,
                                    message = status.message,
                                    tone = "danger",
                                ),
                            )
                        }
                        return@launch
                    }
                }
            }
        }
    }

    companion object {
        fun factory(application: Application): ViewModelProvider.Factory {
            return object : ViewModelProvider.Factory {
                @Suppress("UNCHECKED_CAST")
                override fun <T : ViewModel> create(modelClass: Class<T>): T {
                    if (modelClass.isAssignableFrom(MainViewModel::class.java)) {
                        return MainViewModel(application) as T
                    }
                    throw IllegalArgumentException("Unknown ViewModel class: ${modelClass.name}")
                }
            }
        }
    }
}

private class MobileBridgeRepository(
    private val context: Context,
) {
    fun buildRandomPattern(pointCount: Int): MobileSnapshot {
        return parseSnapshot(call("build_random_pattern", pointCount))
    }

    fun optimizePattern(patternJson: String): MobileSnapshot {
        return parseSnapshot(call("optimize_pattern", patternJson))
    }

    fun optimizeUntilLocalGreen(patternJson: String, rounds: Int): MobileSnapshot {
        return parseSnapshot(call("optimize_until_local_green", patternJson, rounds))
    }

    fun assignPattern(patternJson: String): MobileSnapshot {
        return parseSnapshot(call("assign_pattern", patternJson))
    }

    fun autoAllGreen(pointCount: Int, maxAttempts: Int, maxLocalRounds: Int): MobileSnapshot {
        return parseSnapshot(call("auto_all_green", pointCount, maxAttempts, maxLocalRounds))
    }

    private fun call(attribute: String, vararg args: Any): String {
        if (!Python.isStarted()) {
            Python.start(AndroidPlatform(context))
        }
        val module = Python.getInstance().getModule("cp_generator.mobile_api")
        return module.callAttr(attribute, *args).toString()
    }
}

private class AppUpdateRepository(
    private val context: Context,
) {
    fun currentVersionName(): String {
        return try {
            @Suppress("DEPRECATION")
            context.packageManager.getPackageInfo(context.packageName, 0).versionName ?: "0.2.1"
        } catch (_: Exception) {
            "0.2.1"
        }
    }

    fun checkForUpdates(): UpdateCheckResult {
        val connection = URL(UPDATE_API_URL).openConnection() as HttpURLConnection
        return try {
            connection.requestMethod = "GET"
            connection.setRequestProperty("Accept", "application/vnd.github+json")
            connection.setRequestProperty("X-GitHub-Api-Version", "2022-11-28")
            connection.connectTimeout = 10000
            connection.readTimeout = 10000

            val code = connection.responseCode
            if (code == 404) {
                return UpdateCheckResult(
                    available = false,
                    latestVersion = null,
                    message = "No published release channel was found yet for automatic updates.",
                    tone = "warning",
                    releaseUrl = null,
                    downloadUrl = null,
                )
            }
            if (code !in 200..299) {
                throw IllegalStateException("GitHub returned HTTP $code while checking for updates.")
            }

            val raw = connection.inputStream.bufferedReader().use { it.readText() }
            val json = JSONObject(raw)
            val tag = json.optString("tag_name")
            val htmlUrl = json.optStringOrNull("html_url")
            val assets = json.optJSONArray("assets")
            val apkAsset = assets?.let { array ->
                (0 until array.length())
                    .map { array.getJSONObject(it) }
                    .firstOrNull { item -> item.optString("name").endsWith(".apk") }
            }
            val latestVersion = normalizeVersion(tag)
            val currentVersion = normalizeVersion(currentVersionName())
            val newer = compareVersions(latestVersion, currentVersion) > 0

            if (apkAsset == null) {
                return UpdateCheckResult(
                    available = false,
                    latestVersion = latestVersion.ifEmpty { null },
                    message = "A release exists, but it does not include an APK asset yet.",
                    tone = "warning",
                    releaseUrl = htmlUrl,
                    downloadUrl = null,
                )
            }

            if (!newer) {
                return UpdateCheckResult(
                    available = false,
                    latestVersion = latestVersion.ifEmpty { null },
                    message = "This install already matches the latest published release.",
                    tone = "success",
                    releaseUrl = htmlUrl,
                    downloadUrl = apkAsset.optStringOrNull("browser_download_url"),
                )
            }

            return UpdateCheckResult(
                available = true,
                latestVersion = latestVersion.ifEmpty { null },
                message = "A newer APK is available from the release channel.",
                tone = "success",
                releaseUrl = htmlUrl,
                downloadUrl = apkAsset.optStringOrNull("browser_download_url"),
            )
        } finally {
            connection.disconnect()
        }
    }

    fun startDownload(url: String): Long {
        val request = DownloadManager.Request(Uri.parse(url))
            .setTitle("CP Generator update")
            .setDescription("Downloading the latest APK")
            .setMimeType("application/vnd.android.package-archive")
            .setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
            .setAllowedOverMetered(true)
            .setAllowedOverRoaming(true)
            .setDestinationInExternalFilesDir(
                context,
                Environment.DIRECTORY_DOWNLOADS,
                "cp-generator-update.apk",
            )

        val manager = context.getSystemService(Context.DOWNLOAD_SERVICE) as DownloadManager
        return manager.enqueue(request)
    }

    fun queryDownload(downloadId: Long): DownloadStatus {
        val manager = context.getSystemService(Context.DOWNLOAD_SERVICE) as DownloadManager
        val query = DownloadManager.Query().setFilterById(downloadId)
        manager.query(query).use { cursor ->
            if (!cursor.moveToFirst()) {
                return DownloadStatus.Failed("The update download could not be found anymore.")
            }
            val status = cursor.getInt(cursor.getColumnIndexOrThrow(DownloadManager.COLUMN_STATUS))
            return when (status) {
                DownloadManager.STATUS_SUCCESSFUL -> DownloadStatus.Success
                DownloadManager.STATUS_FAILED -> {
                    val reason = cursor.getInt(cursor.getColumnIndexOrThrow(DownloadManager.COLUMN_REASON))
                    DownloadStatus.Failed("The update download failed (reason $reason).")
                }
                else -> DownloadStatus.Pending
            }
        }
    }

    fun installDownloadedApk(downloadId: Long) {
        val manager = context.getSystemService(Context.DOWNLOAD_SERVICE) as DownloadManager
        val uri = manager.getUriForDownloadedFile(downloadId) ?: return
        val intent = Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(uri, "application/vnd.android.package-archive")
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
        context.startActivity(intent)
    }

    fun openUrl(url: String) {
        val intent = Intent(Intent.ACTION_VIEW, Uri.parse(url)).apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        context.startActivity(intent)
    }
}

private sealed class DownloadStatus {
    data object Pending : DownloadStatus()
    data object Success : DownloadStatus()
    data class Failed(val message: String) : DownloadStatus()
}

private data class UpdateCheckResult(
    val available: Boolean,
    val latestVersion: String?,
    val message: String,
    val tone: String,
    val releaseUrl: String?,
    val downloadUrl: String?,
) {
    fun toUiState(currentVersion: String): UpdateUiState {
        return UpdateUiState(
            currentVersion = currentVersion,
            latestVersion = latestVersion,
            message = message,
            tone = tone,
            releaseUrl = releaseUrl,
            downloadUrl = downloadUrl,
            isChecking = false,
            isDownloading = false,
            readyToInstall = false,
            downloadId = null,
        )
    }
}

private fun normalizeVersion(value: String?): String {
    if (value.isNullOrBlank()) {
        return ""
    }
    return value.trim().removePrefix("v")
}

private fun compareVersions(left: String, right: String): Int {
    val leftParts = left.split(".", "-", "_").mapNotNull { it.toIntOrNull() }
    val rightParts = right.split(".", "-", "_").mapNotNull { it.toIntOrNull() }
    val maxSize = max(leftParts.size, rightParts.size)
    for (index in 0 until maxSize) {
        val a = leftParts.getOrElse(index) { 0 }
        val b = rightParts.getOrElse(index) { 0 }
        if (a != b) {
            return a.compareTo(b)
        }
    }
    return 0
}

private fun parseSnapshot(raw: String): MobileSnapshot {
    val json = JSONObject(raw)
    val statusJson = json.getJSONObject("status")
    val statsJson = json.getJSONObject("stats")
    val stageJson = json.getJSONObject("stage")
    val previewJson = json.optJSONObject("preview")
    val automationJson = json.optJSONObject("automation")

    return MobileSnapshot(
        patternJson = json.getString("pattern_json"),
        title = json.getString("title"),
        subtitle = json.getString("subtitle"),
        summary = json.getString("summary"),
        note = json.getString("note"),
        pointCount = json.optIntOrNull("point_count"),
        status = StatusBanner(
            title = statusJson.getString("title"),
            message = statusJson.getString("message"),
            tone = statusJson.getString("tone"),
        ),
        stats = StatsModel(
            vertices = statsJson.getInt("vertices"),
            folds = statsJson.getInt("folds"),
            interiorVertices = statsJson.getInt("interior_vertices"),
            assignedFolds = statsJson.getInt("assigned_folds"),
            unassignedFolds = statsJson.getInt("unassigned_folds"),
            faceCount = statsJson.optIntOrNull("face_count"),
        ),
        diagnostics = stageArray(json.getJSONArray("diagnostics")) { item ->
            DiagnosticModel(
                key = item.getString("key"),
                label = item.getString("label"),
                status = item.getString("status"),
                message = item.getString("message"),
                tone = item.getString("tone"),
            )
        },
        stage = StageModel(
            folds = stageArray(stageJson.getJSONArray("folds")) { item ->
                FoldLine(
                    x1 = item.getDouble("x1").toFloat(),
                    y1 = item.getDouble("y1").toFloat(),
                    x2 = item.getDouble("x2").toFloat(),
                    y2 = item.getDouble("y2").toFloat(),
                    type = item.getInt("type"),
                )
            },
            vertices = stageArray(stageJson.getJSONArray("vertices")) { item ->
                StageVertex(
                    x = item.getDouble("x").toFloat(),
                    y = item.getDouble("y").toFloat(),
                    onEdge = item.getBoolean("on_edge"),
                )
            },
        ),
        preview = previewJson?.let { previewObject ->
            val boundsJson = previewObject.getJSONObject("bounds")
            PreviewModel(
                mode = previewObject.getString("mode"),
                message = previewObject.getString("message"),
                faceCount = previewObject.optIntOrNull("face_count"),
                usesProvisionalSigns = previewObject.getBoolean("uses_provisional_signs"),
                usesApproximateCycles = previewObject.getBoolean("uses_approximate_cycles"),
                cycleDrift = previewObject.optDoubleOrNull("cycle_drift"),
                isMeshApproximation = previewObject.getBoolean("is_mesh_approximation"),
                bounds = PreviewBounds(
                    minX = boundsJson.getDouble("min_x").toFloat(),
                    maxX = boundsJson.getDouble("max_x").toFloat(),
                    minY = boundsJson.getDouble("min_y").toFloat(),
                    maxY = boundsJson.getDouble("max_y").toFloat(),
                    minZ = boundsJson.getDouble("min_z").toFloat(),
                    maxZ = boundsJson.getDouble("max_z").toFloat(),
                ),
                frames = stageArray(previewObject.getJSONArray("frames")) { frame ->
                    PreviewFrame(
                        progress = frame.getDouble("progress").toFloat(),
                        faces = stageArray(frame.getJSONArray("faces")) { face ->
                            PreviewFace(
                                index = face.getInt("index"),
                                topSurface = face.getBoolean("top_surface"),
                                points = stageArray(face.getJSONArray("points")) { point ->
                                    Point3(
                                        x = point.getDouble("x").toFloat(),
                                        y = point.getDouble("y").toFloat(),
                                        z = point.getDouble("z").toFloat(),
                                    )
                                },
                            )
                        },
                    )
                },
            )
        },
        automation = automationJson?.let { item ->
            AutomationModel(
                kind = item.getString("kind"),
                found = item.getBoolean("found"),
                attempts = item.getInt("attempts"),
                maxAttempts = item.getInt("max_attempts"),
                rounds = item.getInt("rounds"),
                maxRounds = item.getInt("max_rounds"),
                iterations = item.getInt("iterations"),
                loss = item.optDoubleOrNull("loss"),
            )
        },
    )
}

private fun JSONObject.optStringOrNull(name: String): String? {
    if (!has(name) || isNull(name)) {
        return null
    }
    return getString(name)
}

private fun JSONObject.optIntOrNull(name: String): Int? {
    if (!has(name) || isNull(name)) {
        return null
    }
    return getInt(name)
}

private fun JSONObject.optDoubleOrNull(name: String): Double? {
    if (!has(name) || isNull(name)) {
        return null
    }
    return getDouble(name)
}

private fun <T> stageArray(array: JSONArray, mapper: (JSONObject) -> T): List<T> {
    return List(array.length()) { index ->
        mapper(array.getJSONObject(index))
    }
}
