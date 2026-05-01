package com.mathxstudio.cpgenerator

import android.app.Application
import android.content.Context
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.compose.animation.Crossfade
import androidx.compose.animation.animateContentSize
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
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
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
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
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
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
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import kotlin.math.min
import kotlin.math.roundToInt


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
            StageCard(state = state)
            ControlsCard(
                state = state,
                onPointCountChanged = viewModel::updatePointCount,
                onGenerate = viewModel::generatePattern,
                onRefine = viewModel::refinePattern,
                onAssign = viewModel::assignPattern,
                onLoadSample = viewModel::loadSample,
            )
            DiagnosticsCard(state = state)
        }
    }
}


@Composable
private fun HeroCard(state: MainUiState) {
    val snapshot = state.snapshot
    val status = snapshot?.status ?: StatusBanner(
        title = "Preparing studio",
        message = "Loading the authored mobile-friendly sample.",
        tone = "neutral",
    )

    Surface(
        shape = RoundedCornerShape(30.dp),
        color = Color.Transparent,
        shadowElevation = 10.dp,
    ) {
        Box(
            modifier = Modifier
                .background(
                    brush = Brush.linearGradient(
                        colors = listOf(Paper, Sand, AppCardAlt),
                    ),
                )
                .padding(22.dp),
        ) {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                StatusPill(
                    label = "Android studio shell",
                    tone = "neutral",
                )
                Text(
                    text = "CP Generator",
                    style = MaterialTheme.typography.headlineLarge,
                    color = Ink,
                )
                Text(
                    text = snapshot?.subtitle ?: "Portrait-first origami crease explorer",
                    style = MaterialTheme.typography.bodyLarge,
                    color = InkSoft,
                )
                Surface(
                    shape = RoundedCornerShape(24.dp),
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
                        modifier = Modifier
                            .fillMaxWidth()
                            .clip(RoundedCornerShape(99.dp)),
                        color = Terracotta,
                        trackColor = Terracotta.copy(alpha = 0.18f),
                    )
                }
            }
        }
    }
}


@Composable
private fun StageCard(state: MainUiState) {
    val snapshot = state.snapshot

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
                        text = "Crease sheet",
                        style = MaterialTheme.typography.titleLarge,
                        color = Ink,
                    )
                    Text(
                        text = snapshot?.summary
                            ?: "The mobile shell keeps the experience focused on geometry, diagnostics, and quick iteration.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = InkSoft,
                        maxLines = 3,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
                if (snapshot?.sampleKey != null) {
                    AssistChip(
                        onClick = {},
                        enabled = false,
                        label = { Text("Sample loaded") },
                    )
                }
            }

            Crossfade(
                targetState = snapshot?.stage,
                label = "pattern-stage",
            ) { stage ->
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .aspectRatio(1f)
                        .clip(RoundedCornerShape(26.dp))
                        .background(
                            brush = Brush.linearGradient(
                                colors = listOf(Paper, AppCardAlt),
                            ),
                        ),
                ) {
                    if (stage == null) {
                        EmptyStage()
                    } else {
                        PatternStage(stage = stage)
                    }
                }
            }

            LegendRow()
            snapshot?.stats?.let { stats ->
                StatsRow(stats = stats)
            }
        }
    }
}


@Composable
private fun EmptyStage() {
    Box(
        modifier = Modifier.fillMaxSize(),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            text = "No crease sheet yet",
            style = MaterialTheme.typography.titleMedium,
            color = InkSoft,
        )
    }
}


@Composable
private fun PatternStage(stage: StageModel) {
    Canvas(modifier = Modifier.fillMaxSize()) {
        val squareSize = min(size.width, size.height) * 0.84f
        val left = (size.width - squareSize) * 0.5f
        val top = (size.height - squareSize) * 0.5f
        val paperTopLeft = Offset(left, top)
        val paperSize = Size(squareSize, squareSize)
        val radius = CornerRadius(squareSize * 0.075f, squareSize * 0.075f)

        drawCircle(
            color = Teal.copy(alpha = 0.08f),
            radius = squareSize * 0.43f,
            center = Offset(left + squareSize * 0.22f, top + squareSize * 0.28f),
        )
        drawCircle(
            color = Terracotta.copy(alpha = 0.10f),
            radius = squareSize * 0.38f,
            center = Offset(left + squareSize * 0.78f, top + squareSize * 0.78f),
        )
        drawRoundRect(
            color = Color.White.copy(alpha = 0.96f),
            topLeft = paperTopLeft,
            size = paperSize,
            cornerRadius = radius,
        )
        drawRoundRect(
            color = OutlineSoft,
            topLeft = paperTopLeft,
            size = paperSize,
            cornerRadius = radius,
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

        val foldPath = Path().apply {
            moveTo(left + squareSize * 0.16f, top + squareSize * 0.14f)
            lineTo(left + squareSize * 0.84f, top + squareSize * 0.14f)
            lineTo(left + squareSize * 0.62f, top + squareSize * 0.36f)
            close()
        }
        drawPath(
            path = foldPath,
            color = SandDeep.copy(alpha = 0.06f),
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
                    .clip(RoundedCornerShape(99.dp))
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
    onGenerate: () -> Unit,
    onRefine: () -> Unit,
    onAssign: () -> Unit,
    onLoadSample: () -> Unit,
) {
    val snapshot = state.snapshot
    val isSample = snapshot?.sampleKey != null

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
                text = "Tune the point count for random studies, or reopen the authored sample when you want a stable reference.",
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
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text(
                            text = "Random interior points",
                            style = MaterialTheme.typography.titleMedium,
                            color = Ink,
                        )
                        StatusPill(
                            label = state.pointCount.toString(),
                            tone = "neutral",
                        )
                    }
                    Slider(
                        value = state.pointCount.toFloat(),
                        onValueChange = onPointCountChanged,
                        enabled = !state.isBusy,
                        valueRange = 0f..18f,
                        steps = 17,
                    )
                }
            }
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(12.dp),
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
                    modifier = Modifier.weight(1f),
                ) {
                    Text("Randomize")
                }
                FilledTonalButton(
                    onClick = onRefine,
                    enabled = !state.isBusy && snapshot != null && !isSample,
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
            }
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                OutlinedButton(
                    onClick = onAssign,
                    enabled = !state.isBusy && snapshot != null && !isSample,
                    shape = RoundedCornerShape(22.dp),
                    contentPadding = PaddingValues(horizontal = 18.dp, vertical = 14.dp),
                    modifier = Modifier.weight(1f),
                ) {
                    Text("Assign")
                }
                FilledTonalButton(
                    onClick = onLoadSample,
                    enabled = !state.isBusy,
                    shape = RoundedCornerShape(22.dp),
                    colors = ButtonDefaults.filledTonalButtonColors(
                        containerColor = Sage.copy(alpha = 0.18f),
                        contentColor = Sage,
                    ),
                    contentPadding = PaddingValues(horizontal = 18.dp, vertical = 14.dp),
                    modifier = Modifier.weight(1f),
                ) {
                    Text("Box Head")
                }
            }
        }
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
                            .clip(CircleShape)
                            .background(toneContent(diagnostic.tone)),
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
                    ?: "The Android shell focuses on generation, refinement, assignment, and crease inspection in a phone-friendly flow.",
                style = MaterialTheme.typography.bodyMedium,
                color = InkSoft,
            )
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


@Composable
private fun toneContainer(tone: String): Color {
    return when (tone) {
        "success" -> Sage.copy(alpha = 0.18f)
        "warning" -> Terracotta.copy(alpha = 0.16f)
        "danger" -> Color(0xFFF3D8D1)
        else -> Sand
    }
}


@Composable
private fun toneContent(tone: String): Color {
    return when (tone) {
        "success" -> Sage
        "warning" -> Terracotta
        "danger" -> Color(0xFF9E3E2D)
        else -> InkSoft
    }
}


data class MainUiState(
    val pointCount: Int = 8,
    val snapshot: MobileSnapshot? = null,
    val isBusy: Boolean = false,
    val errorMessage: String? = null,
)


data class MobileSnapshot(
    val patternJson: String,
    val title: String,
    val subtitle: String,
    val summary: String,
    val note: String,
    val pointCount: Int?,
    val sampleKey: String?,
    val status: StatusBanner,
    val stats: StatsModel,
    val diagnostics: List<DiagnosticModel>,
    val stage: StageModel,
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


class MainViewModel(application: Application) : AndroidViewModel(application) {
    private val repository = MobileBridgeRepository(application)
    private val _uiState = MutableStateFlow(MainUiState())
    val uiState: StateFlow<MainUiState> = _uiState

    init {
        loadSample()
    }

    fun updatePointCount(value: Float) {
        _uiState.update { state ->
            state.copy(pointCount = value.roundToInt())
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

    fun assignPattern() {
        val patternJson = _uiState.value.snapshot?.patternJson ?: return
        launchOperation {
            repository.assignPattern(patternJson)
        }
    }

    fun loadSample() {
        launchOperation {
            repository.loadBoxHead()
        }
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
                _uiState.update {
                    it.copy(
                        snapshot = snapshot,
                        isBusy = false,
                        errorMessage = null,
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
    fun loadBoxHead(): MobileSnapshot {
        return parseSnapshot(call("load_box_head"))
    }

    fun buildRandomPattern(pointCount: Int): MobileSnapshot {
        return parseSnapshot(call("build_random_pattern", pointCount))
    }

    fun optimizePattern(patternJson: String): MobileSnapshot {
        return parseSnapshot(call("optimize_pattern", patternJson))
    }

    fun assignPattern(patternJson: String): MobileSnapshot {
        return parseSnapshot(call("assign_pattern", patternJson))
    }

    private fun call(attribute: String, vararg args: Any): String {
        if (!Python.isStarted()) {
            Python.start(AndroidPlatform(context))
        }
        val module = Python.getInstance().getModule("cp_generator.mobile_api")
        return module.callAttr(attribute, *args).toString()
    }
}


private fun parseSnapshot(raw: String): MobileSnapshot {
    val json = JSONObject(raw)
    val statusJson = json.getJSONObject("status")
    val statsJson = json.getJSONObject("stats")
    val stageJson = json.getJSONObject("stage")

    return MobileSnapshot(
        patternJson = json.getString("pattern_json"),
        title = json.getString("title"),
        subtitle = json.getString("subtitle"),
        summary = json.getString("summary"),
        note = json.getString("note"),
        pointCount = json.optIntOrNull("point_count"),
        sampleKey = json.optStringOrNull("sample_key"),
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


private fun <T> stageArray(array: JSONArray, mapper: (JSONObject) -> T): List<T> {
    return List(array.length()) { index ->
        mapper(array.getJSONObject(index))
    }
}
