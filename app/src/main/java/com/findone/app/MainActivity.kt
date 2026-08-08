package com.findone.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.automirrored.outlined.OpenInNew
import androidx.compose.material.icons.outlined.AutoStories
import androidx.compose.material.icons.outlined.Bookmark
import androidx.compose.material.icons.outlined.BookmarkBorder
import androidx.compose.material.icons.outlined.Calculate
import androidx.compose.material.icons.outlined.CheckCircle
import androidx.compose.material.icons.outlined.ChevronRight
import androidx.compose.material.icons.outlined.Close
import androidx.compose.material.icons.outlined.CloudOff
import androidx.compose.material.icons.outlined.DeleteForever
import androidx.compose.material.icons.outlined.Download
import androidx.compose.material.icons.outlined.ErrorOutline
import androidx.compose.material.icons.outlined.ExpandLess
import androidx.compose.material.icons.outlined.ExpandMore
import androidx.compose.material.icons.outlined.HistoryEdu
import androidx.compose.material.icons.outlined.Home
import androidx.compose.material.icons.outlined.Info
import androidx.compose.material.icons.automirrored.outlined.MenuBook
import androidx.compose.material.icons.outlined.MoreHoriz
import androidx.compose.material.icons.outlined.Psychology
import androidx.compose.material.icons.outlined.Quiz
import androidx.compose.material.icons.outlined.Refresh
import androidx.compose.material.icons.outlined.RestartAlt
import androidx.compose.material.icons.outlined.School
import androidx.compose.material.icons.outlined.Search
import androidx.compose.material.icons.outlined.Shield
import androidx.compose.material.icons.outlined.Speed
import androidx.compose.material.icons.outlined.Upload
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedCard
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.lifecycle.viewmodel.compose.viewModel
import com.findone.app.data.AttemptRecord
import com.findone.app.data.BookmarkRecord
import com.findone.app.model.ContentElement
import com.findone.app.model.Domain
import com.findone.app.quiz.QuizAnswerKind
import com.findone.app.quiz.QuizMode
import com.findone.app.quiz.QuizPresentation
import com.findone.app.quiz.QuizQuestion
import com.findone.app.ui.BrandHeader
import com.findone.app.ui.DomainBadge
import com.findone.app.ui.MarkdownText
import com.findone.app.ui.OfflineBanner
import com.findone.app.ui.PageHeader
import com.findone.app.ui.SectionTitle
import com.findone.app.ui.StatCard
import com.findone.app.ui.domainAccent
import com.findone.app.ui.theme.FinDoneTheme
import kotlinx.coroutines.launch
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge(
            statusBarStyle = SystemBarStyle.auto(android.graphics.Color.TRANSPARENT, android.graphics.Color.TRANSPARENT),
            navigationBarStyle = SystemBarStyle.auto(android.graphics.Color.TRANSPARENT, android.graphics.Color.TRANSPARENT),
        )
        setContent {
            FinDoneTheme {
                val appViewModel: AppViewModel = viewModel()
                FinDoneApp(appViewModel)
            }
        }
    }
}

@Composable
private fun FinDoneApp(vm: AppViewModel) {
    val snackbar = remember { SnackbarHostState() }
    val scope = rememberCoroutineScope()
    val context = LocalContext.current
    var confirmReset by remember { mutableStateOf(false) }
    var confirmLeaveQuiz by remember { mutableStateOf(false) }
    var userDataBusy by remember { mutableStateOf(false) }

    val exportLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.CreateDocument("application/json")
    ) { uri ->
        if (uri != null) scope.launch {
            userDataBusy = true
            try {
                runCatching { withContext(Dispatchers.IO) { vm.exportBackup(context.contentResolver, uri) } }
                    .onSuccess { snackbar.showSnackbar("학습 기록 백업을 저장했습니다.") }
                    .onFailure { snackbar.showSnackbar(it.message ?: "백업 저장에 실패했습니다.") }
            } finally {
                userDataBusy = false
            }
        }
    }
    val importLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.OpenDocument()
    ) { uri ->
        if (uri != null) scope.launch {
            userDataBusy = true
            try {
                runCatching { withContext(Dispatchers.IO) { vm.importBackup(context.contentResolver, uri) } }
                    .onSuccess {
                        vm.reloadUserData()
                        snackbar.showSnackbar("백업을 검증하고 복원했습니다.")
                    }
                    .onFailure { snackbar.showSnackbar(it.message ?: "백업 복원에 실패했습니다.") }
            } finally {
                userDataBusy = false
            }
        }
    }

    LaunchedEffect(vm.quizMessage) {
        vm.quizMessage?.let {
            snackbar.showSnackbar(it)
            vm.clearQuizMessage()
        }
    }

    BackHandler(enabled = vm.selectedElement != null || vm.quizSession != null) {
        when {
            vm.selectedElement != null -> vm.closeElement()
            vm.quizSession != null -> confirmLeaveQuiz = true
        }
    }

    Scaffold(
        snackbarHost = { SnackbarHost(snackbar) },
        bottomBar = {
            if (vm.quizSession == null) {
                NavigationBar {
                    val tabs = listOf(
                        Triple(MainTab.HOME, "오늘", Icons.Outlined.Home),
                        Triple(MainTab.STUDY, "학습", Icons.AutoMirrored.Outlined.MenuBook),
                        Triple(MainTab.QUIZ, "퀴즈", Icons.Outlined.Quiz),
                        Triple(MainTab.RECORDS, "기록", Icons.Outlined.Bookmark),
                    )
                    tabs.forEach { (tab, label, icon) ->
                        NavigationBarItem(
                            selected = vm.currentTab == tab,
                            onClick = { vm.selectTab(tab) },
                            icon = { Icon(icon, contentDescription = null) },
                            label = { Text(label) },
                        )
                    }
                }
            }
        },
    ) { scaffoldPadding ->
        Box(
            Modifier
                .padding(scaffoldPadding)
                .fillMaxSize()
                .imePadding(),
            contentAlignment = Alignment.TopCenter,
        ) {
            when {
                vm.contentError != null -> ContentFailure(vm.contentError.orEmpty())
                vm.quizSession != null -> QuizSessionScreen(vm) { confirmLeaveQuiz = true }
                vm.currentTab == MainTab.HOME -> HomeScreen(vm)
                vm.currentTab == MainTab.STUDY && vm.selectedElement != null -> ElementDetailScreen(vm)
                vm.currentTab == MainTab.STUDY -> StudyScreen(vm)
                vm.currentTab == MainTab.QUIZ -> QuizSetupScreen(vm)
                else -> RecordsScreen(
                    vm = vm,
                    exportBackup = { exportLauncher.launch("FinDone-backup-${backupDate()}.json") },
                    importBackup = { importLauncher.launch(arrayOf("application/json", "text/plain")) },
                    requestReset = { confirmReset = true },
                )
            }
        }
    }

    if (confirmReset) {
        AlertDialog(
            onDismissRequest = { confirmReset = false },
            icon = { Icon(Icons.Outlined.DeleteForever, contentDescription = null) },
            title = { Text("학습 기록을 모두 지울까요?") },
            text = { Text("오답, 북마크, 정답률과 진도가 삭제됩니다. 먼저 수동 백업할 수 있습니다.") },
            confirmButton = {
                Button(
                    onClick = { vm.clearLearningData(); confirmReset = false },
                    colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.error),
                ) { Text("삭제") }
            },
            dismissButton = { TextButton(onClick = { confirmReset = false }) { Text("취소") } },
        )
    }

    if (confirmLeaveQuiz) {
        AlertDialog(
            onDismissRequest = { confirmLeaveQuiz = false },
            title = { Text("퀴즈를 종료할까요?") },
            text = { Text("이미 제출한 답변은 기록에 남고, 아직 제출하지 않은 문제는 저장되지 않습니다.") },
            confirmButton = {
                Button(onClick = { vm.leaveQuiz(); confirmLeaveQuiz = false }) { Text("종료") }
            },
            dismissButton = { TextButton(onClick = { confirmLeaveQuiz = false }) { Text("계속 풀기") } },
        )
    }

    if (userDataBusy) {
        Dialog(
            onDismissRequest = {},
            properties = DialogProperties(dismissOnBackPress = false, dismissOnClickOutside = false),
        ) {
            Card {
                Row(
                    Modifier.padding(horizontal = 24.dp, vertical = 20.dp),
                    horizontalArrangement = Arrangement.spacedBy(14.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    CircularProgressIndicator(Modifier.size(28.dp), strokeWidth = 3.dp)
                    Text("학습 기록을 안전하게 처리하는 중입니다.")
                }
            }
        }
    }
}

@Composable
private fun ContentFailure(message: String) {
    Column(
        Modifier.fillMaxSize().widthIn(max = 640.dp).padding(28.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Icon(Icons.Outlined.ErrorOutline, contentDescription = null, tint = MaterialTheme.colorScheme.error, modifier = Modifier.size(42.dp))
        Spacer(Modifier.height(16.dp))
        Text("콘텐츠 무결성 검증 실패", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
        Spacer(Modifier.height(8.dp))
        Text(message, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Spacer(Modifier.height(12.dp))
        Text("서명된 APK를 다시 설치해 콘텐츠 DB를 복구하세요.", style = MaterialTheme.typography.bodySmall)
    }
}

@Composable
private fun HomeScreen(vm: AppViewModel) {
    LazyColumn(
        modifier = pageWidth(),
        contentPadding = pagePadding(),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        item {
            BrandHeader(
                eyebrow = "FINANCE CAREER",
                title = "금융권 진출을 위한\n오늘의 한 문제",
                description = "핵심 개념부터 실전 문제까지 차근차근 익히는 개인 금융 학습 도구입니다.",
            )
        }
        item { OfflineBanner() }
        item {
            Card(
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primary),
            ) {
                Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text("학습 현황", color = MaterialTheme.colorScheme.onPrimary.copy(alpha = .8f))
                    Text(
                        "${vm.stats.studiedElements} / ${vm.allElements.size} 요소",
                        color = MaterialTheme.colorScheme.onPrimary,
                        style = MaterialTheme.typography.headlineSmall,
                        fontWeight = FontWeight.Bold,
                    )
                    LinearProgressIndicator(
                        progress = { if (vm.allElements.isEmpty()) 0f else vm.stats.studiedElements / vm.allElements.size.toFloat() },
                        modifier = Modifier.fillMaxWidth(),
                        color = MaterialTheme.colorScheme.onPrimary,
                        trackColor = MaterialTheme.colorScheme.onPrimary.copy(alpha = .25f),
                    )
                    Button(
                        onClick = { vm.setQuizTrack(if (vm.stats.wrongUnresolved > 0) QuizTrack.WEAK else QuizTrack.SPRINT); vm.startConfiguredQuiz() },
                        colors = ButtonDefaults.buttonColors(
                            containerColor = MaterialTheme.colorScheme.onPrimary,
                            contentColor = MaterialTheme.colorScheme.primary,
                        ),
                    ) {
                        Icon(Icons.Outlined.Speed, contentDescription = null)
                        Spacer(Modifier.width(8.dp))
                        Text(if (vm.stats.wrongUnresolved > 0) "남은 오답 이어 풀기" else "금융권 스프린트 시작")
                    }
                }
            }
        }
        item {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                StatCard("정답률", "${vm.stats.accuracyPercent}%", Icons.Outlined.CheckCircle, Modifier.weight(1f))
                StatCard("남은 오답", "${vm.stats.wrongUnresolved}", Icons.Outlined.RestartAlt, Modifier.weight(1f), MaterialTheme.colorScheme.error)
                StatCard("북마크", "${vm.stats.bookmarked}", Icons.Outlined.Bookmark, Modifier.weight(1f), MaterialTheme.colorScheme.tertiary)
            }
        }
        item { SectionTitle("분야별 진도", "총 7개 분야 · 135개 요소") }
        items(vm.domains, key = { it.id }) { domain ->
            DomainProgressCard(domain, vm) {
                vm.setStudyDomain(domain.id)
                vm.selectTab(MainTab.STUDY)
            }
        }
        item {
            OutlinedCard {
                Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Outlined.Shield, contentDescription = null, tint = MaterialTheme.colorScheme.secondary)
                    Spacer(Modifier.width(12.dp))
                    Column {
                        Text("검증된 로컬 콘텐츠", fontWeight = FontWeight.Bold)
                        Text(
                            "DB v${vm.contentManifest?.contentDbVersion ?: "-"} · SHA-256 검증 · FTS5 검색",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun DomainProgressCard(domain: Domain, vm: AppViewModel, onClick: () -> Unit) {
    val attempted = vm.allElements.count { it.domainId == domain.id && (vm.progress[it.id]?.attempts ?: 0) > 0 }
    Card(onClick = onClick) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(9.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                DomainBadge(domain.id)
                Spacer(Modifier.width(10.dp))
                Text(domain.name, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
                Text("$attempted / ${domain.count}", style = MaterialTheme.typography.labelMedium)
                Spacer(Modifier.width(5.dp))
                Icon(Icons.Outlined.ChevronRight, contentDescription = null, modifier = Modifier.size(18.dp))
            }
            LinearProgressIndicator(
                progress = { if (domain.count == 0) 0f else attempted / domain.count.toFloat() },
                modifier = Modifier.fillMaxWidth(),
                color = domainAccent(domain.id),
            )
        }
    }
}

@Composable
private fun StudyScreen(vm: AppViewModel) {
    LazyColumn(
        modifier = pageWidth(),
        contentPadding = pagePadding(),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            PageHeader(
                eyebrow = "KNOWLEDGE BASE",
                title = "학습요소",
                description = "분야·ID·개념·수식으로 135개 요소를 검색하세요.",
            )
        }
        item {
            OutlinedTextField(
                value = vm.studyQuery,
                onValueChange = vm::updateStudyQuery,
                modifier = Modifier.fillMaxWidth(),
                leadingIcon = { Icon(Icons.Outlined.Search, contentDescription = null) },
                trailingIcon = {
                    if (vm.studyQuery.isNotEmpty()) IconButton(onClick = { vm.updateStudyQuery("") }) {
                        Icon(Icons.Outlined.Close, contentDescription = "검색어 지우기")
                    }
                },
                label = { Text("예: WACC, 듀레이션, EQV-41") },
                singleLine = true,
            )
        }
        item {
            LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                item { FilterChip(selected = vm.studyDomainId == null, onClick = { vm.setStudyDomain(null) }, label = { Text("전체") }) }
                items(vm.domains, key = { it.id }) { domain ->
                    FilterChip(
                        selected = vm.studyDomainId == domain.id,
                        onClick = { vm.setStudyDomain(if (vm.studyDomainId == domain.id) null else domain.id) },
                        label = { Text(domain.id) },
                    )
                }
            }
        }
        item { SectionTitle("검색 결과", "${vm.studyResults.size}개") }
        if (vm.studyResults.isEmpty()) {
            item {
                EmptyState(Icons.Outlined.Search, "일치하는 요소가 없습니다", "검색어를 줄이거나 다른 분야를 선택해 보세요.")
            }
        } else {
            items(vm.studyResults, key = { it.id }) { element -> ElementRow(element, vm) { vm.openElement(element.id) } }
        }
    }
}

@Composable
private fun ElementRow(element: ContentElement, vm: AppViewModel, onClick: () -> Unit) {
    val p = vm.progress[element.id]
    Card(onClick = onClick) {
        Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    DomainBadge(element.domainId)
                    Spacer(Modifier.width(8.dp))
                    Text(element.id, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    if ((p?.attempts ?: 0) > 0) {
                        Spacer(Modifier.width(8.dp))
                        Text("${p?.correct}/${p?.attempts}", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.primary)
                    }
                }
                Text(element.title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                Text(element.coreRelation, maxLines = 2, overflow = TextOverflow.Ellipsis, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            Spacer(Modifier.width(8.dp))
            Icon(Icons.Outlined.ChevronRight, contentDescription = "상세 보기")
        }
    }
}

@Composable
private fun ElementDetailScreen(vm: AppViewModel) {
    val element = vm.selectedElement ?: return
    val uriHandler = LocalUriHandler.current
    val webSources = element.sources.filter { it.isWebLink }.distinctBy { it.locator }
    var sourceOpenError by rememberSaveable(element.id) { mutableStateOf<String?>(null) }
    val openSource: (String) -> Unit = { locator ->
        runCatching { uriHandler.openUri(locator) }
            .onSuccess { sourceOpenError = null }
            .onFailure {
                sourceOpenError = "링크를 열 수 없습니다. 주소와 브라우저 설치 상태를 확인해 주세요."
            }
    }
    LazyColumn(
        modifier = pageWidth(),
        contentPadding = pagePadding(),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        item {
            TextButton(onClick = vm::closeElement) {
                Icon(Icons.AutoMirrored.Outlined.ArrowBack, contentDescription = null)
                Spacer(Modifier.width(6.dp))
                Text("학습요소 목록")
            }
        }
        item {
            DomainBadge(element.domainId)
            Spacer(Modifier.height(8.dp))
            Text(element.id, color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.Bold)
            Text(element.title, style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
        }
        item {
            Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer)) {
                Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Outlined.AutoStories, contentDescription = null, tint = MaterialTheme.colorScheme.onPrimaryContainer)
                        Spacer(Modifier.width(8.dp))
                        Text("핵심 개념", fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.onPrimaryContainer)
                    }
                    MarkdownText(
                        markdown = element.definitionMarkdown,
                        style = MaterialTheme.typography.bodyLarge,
                        color = MaterialTheme.colorScheme.onPrimaryContainer,
                    )
                }
            }
        }
        item {
            LearningMarkdownCard("직관과 실무 연결", element.intuitionMarkdown)
        }
        item {
            LearningMarkdownCard(
                "공식·가정",
                "${element.formulaMarkdown}\n\n${element.assumptionsMarkdown}",
            )
        }
        item {
            LearningMarkdownCard("적용 문제와 상세 범위", element.learningNotesMarkdown)
        }
        item {
            LearningMarkdownCard("학습 체크리스트", element.checklistMarkdown)
        }
        item {
            OutlinedCard {
                Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text("근거·더 자세히 읽기", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                    Text(
                        "개념 설명과 공식의 출처를 외부 브라우저에서 확인할 수 있습니다.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    if (webSources.isEmpty()) {
                        OutlinedButton(
                            onClick = { openSource(element.sourceLocator) },
                            enabled = element.sourceLocator.startsWith("https://") || element.sourceLocator.startsWith("http://"),
                            modifier = Modifier.fillMaxWidth(),
                        ) {
                            Icon(Icons.AutoMirrored.Outlined.OpenInNew, contentDescription = null, modifier = Modifier.size(18.dp))
                            Spacer(Modifier.width(7.dp))
                            Text(element.sourceLabel)
                        }
                    } else {
                        webSources.forEach { source ->
                            OutlinedButton(
                                onClick = { openSource(source.locator) },
                                modifier = Modifier.fillMaxWidth(),
                            ) {
                                Icon(Icons.AutoMirrored.Outlined.OpenInNew, contentDescription = null, modifier = Modifier.size(18.dp))
                                Spacer(Modifier.width(7.dp))
                                Text(source.label, maxLines = 2, overflow = TextOverflow.Ellipsis)
                            }
                        }
                    }
                    sourceOpenError?.let { message ->
                        Text(
                            message,
                            color = MaterialTheme.colorScheme.error,
                            style = MaterialTheme.typography.bodySmall,
                            modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite },
                        )
                    }
                    Text(
                        "내부 콘텐츠 위치 · ${element.specSectionLocator}",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        style = MaterialTheme.typography.labelSmall,
                    )
                }
            }
        }
        item {
            Button(onClick = { vm.startElementQuiz(element.id) }, modifier = Modifier.fillMaxWidth()) {
                Icon(Icons.Outlined.Quiz, contentDescription = null)
                Spacer(Modifier.width(8.dp))
                Text("이 요소 중심 5문제 풀기")
            }
        }
    }
}

@Composable
private fun QuizSetupScreen(vm: AppViewModel) {
    LazyColumn(
        modifier = pageWidth(),
        contentPadding = pagePadding(),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        item {
            PageHeader(
                eyebrow = "DETERMINISTIC PRACTICE",
                title = "퀴즈 만들기",
                description = "같은 콘텐츠 버전과 seed는 같은 문제를 만듭니다. 계산 문제의 답은 항상 정수입니다.",
            )
        }
        item { SectionTitle("학습 모드") }
        items(QuizTrack.entries, key = { it.name }) { track ->
            TrackCard(track, selected = vm.selectedTrack == track) { vm.setQuizTrack(track) }
        }
        item { SectionTitle("분야") }
        item {
            LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                item { FilterChip(selected = vm.quizDomainId == null, onClick = { vm.setQuizDomain(null) }, label = { Text("전체") }) }
                items(vm.domains, key = { it.id }) { domain ->
                    FilterChip(
                        selected = vm.quizDomainId == domain.id,
                        onClick = { vm.setQuizDomain(if (vm.quizDomainId == domain.id) null else domain.id) },
                        label = { Text(domain.id) },
                    )
                }
            }
        }
        item { SectionTitle("난이도") }
        item {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                (1..3).forEach { level ->
                    FilterChip(
                        selected = vm.quizDifficulty == level,
                        onClick = { vm.updateQuizDifficulty(level) },
                        label = { Text(listOf("1 · 30초", "2 · 60초", "3 · 90초")[level - 1]) },
                        modifier = Modifier.weight(1f),
                    )
                }
            }
        }
        item { SectionTitle("문제 수") }
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                listOf(5, 10, 20).forEach { count ->
                    FilterChip(selected = vm.quizCount == count, onClick = { vm.updateQuizCount(count) }, label = { Text("${count}문제") })
                }
            }
        }
        item {
            Button(onClick = vm::startConfiguredQuiz, modifier = Modifier.fillMaxWidth()) {
                Icon(Icons.Outlined.School, contentDescription = null)
                Spacer(Modifier.width(8.dp))
                Text("${vm.selectedTrack.displayTitle()} 시작")
            }
        }
        item {
            Row(
                Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(12.dp)).padding(12.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Icon(Icons.Outlined.Calculate, contentDescription = null, modifier = Modifier.size(18.dp))
                Spacer(Modifier.width(8.dp))
                Text("암산 문제에는 계산기·메모장·풀이 힌트를 제공하지 않습니다.", style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}

@Composable
private fun TrackCard(track: QuizTrack, selected: Boolean, onClick: () -> Unit) {
    val icon = when (track) {
        QuizTrack.DOMAIN -> Icons.AutoMirrored.Outlined.MenuBook
        QuizTrack.WEAK -> Icons.Outlined.RestartAlt
        QuizTrack.SPRINT -> Icons.Outlined.Speed
        QuizTrack.CONCEPT -> Icons.Outlined.Psychology
        QuizTrack.ORAL -> Icons.Outlined.HistoryEdu
        QuizTrack.CASE -> Icons.Outlined.AutoStories
        QuizTrack.BOOKMARK -> Icons.Outlined.Bookmark
    }
    OutlinedCard(
        modifier = Modifier.fillMaxWidth().clickable(onClick = onClick),
        colors = CardDefaults.outlinedCardColors(
            containerColor = if (selected) MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.surface,
        ),
    ) {
        Row(Modifier.padding(15.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(icon, contentDescription = null, tint = if (selected) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant)
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(track.displayTitle(), fontWeight = FontWeight.Bold)
                Text(track.description, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            if (selected) Icon(Icons.Outlined.CheckCircle, contentDescription = "선택됨", tint = MaterialTheme.colorScheme.primary)
        }
    }
}

@Composable
private fun QuizSessionScreen(vm: AppViewModel, requestLeave: () -> Unit) {
    val session = vm.quizSession ?: return
    if (session.finished) {
        QuizResultScreen(vm)
        return
    }
    val question = session.currentQuestion ?: return
    val oral = session.currentPresentation == QuizPresentation.ORAL
    var showAnswer by rememberSaveable(question.instanceId) { mutableStateOf(session.submitted) }
    var showSolution by rememberSaveable(question.instanceId) { mutableStateOf(false) }
    var submissionRevealHandled by rememberSaveable(question.instanceId) {
        mutableStateOf(session.submitted)
    }

    LaunchedEffect(question.instanceId, session.submitted) {
        if (session.submitted && !submissionRevealHandled) {
            showAnswer = true
            submissionRevealHandled = true
        }
    }

    LazyColumn(
        modifier = pageWidth(),
        contentPadding = PaddingValues(horizontal = 20.dp, vertical = 16.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        item {
            Row(verticalAlignment = Alignment.CenterVertically) {
                IconButton(onClick = requestLeave) { Icon(Icons.Outlined.Close, contentDescription = "퀴즈 종료") }
                Column(Modifier.weight(1f)) {
                    Text(session.track.displayTitle(), style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.Bold)
                    Text("${session.currentIndex + 1} / ${session.questions.size}", style = MaterialTheme.typography.labelSmall)
                }
                IconButton(onClick = vm::toggleCurrentBookmark) {
                    Icon(
                        if (vm.currentQuestionBookmarked()) Icons.Outlined.Bookmark else Icons.Outlined.BookmarkBorder,
                        contentDescription = if (vm.currentQuestionBookmarked()) "북마크 해제" else "북마크 저장",
                        tint = MaterialTheme.colorScheme.tertiary,
                    )
                }
            }
            LinearProgressIndicator(
                progress = { (session.currentIndex + 1) / session.questions.size.toFloat() },
                modifier = Modifier.fillMaxWidth(),
            )
        }
        item {
            val hideDomainCalculationTags = session.track == QuizTrack.DOMAIN && question.mode == QuizMode.CALCULATION
            LazyRow(horizontalArrangement = Arrangement.spacedBy(7.dp)) {
                item { QuizBadge(question.elementId) }
                if (!hideDomainCalculationTags) {
                    item { QuizBadge(if (question.mode == QuizMode.CALCULATION) "암산" else if (oral) "구술" else "개념") }
                }
                if (question.mode == QuizMode.CALCULATION && !hideDomainCalculationTags) {
                    item { QuizBadge("계산기 사용 안 함") }
                }
                if (question.mode == QuizMode.CALCULATION) {
                    item { QuizBadge("권장 ${question.snapshot.difficulty * 30}초") }
                }
            }
        }
        item {
            QuizQuestionCard(
                vm = vm,
                question = question,
                oral = oral,
                showAnswer = showAnswer,
            )
        }

        if (session.submitted) {
            item {
                QuizFaceToggle(
                    showAnswer = showAnswer,
                    showQuestion = {
                        showAnswer = false
                        showSolution = false
                    },
                    onShowAnswer = { showAnswer = true },
                )
            }
            if (showAnswer) {
                item {
                    OutlinedButton(
                        onClick = { showSolution = !showSolution },
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        Icon(
                            if (showSolution) Icons.Outlined.ExpandLess else Icons.Outlined.ExpandMore,
                            contentDescription = null,
                        )
                        Spacer(Modifier.width(7.dp))
                        Text(if (showSolution) "풀이 접기" else "풀이")
                    }
                }
                if (showSolution) item { SolutionContent(question) }
            }
            item {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(onClick = vm::toggleCurrentBookmark, modifier = Modifier.weight(1f)) {
                        Icon(
                            if (vm.currentQuestionBookmarked()) Icons.Outlined.Bookmark else Icons.Outlined.BookmarkBorder,
                            contentDescription = null,
                        )
                        Spacer(Modifier.width(6.dp))
                        Text(if (vm.currentQuestionBookmarked()) "저장됨" else "북마크")
                    }
                    Button(onClick = vm::nextQuestion, modifier = Modifier.weight(1f)) {
                        Text(if (session.currentIndex == session.questions.lastIndex) "결과 보기" else "다음 문제")
                        Spacer(Modifier.width(5.dp))
                        Icon(Icons.Outlined.ChevronRight, contentDescription = null)
                    }
                }
            }
        }
    }
}

@Composable
private fun LearningMarkdownCard(title: String, markdown: String) {
    if (markdown.isBlank()) return
    OutlinedCard(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
            MarkdownText(markdown = markdown, style = MaterialTheme.typography.bodyMedium)
        }
    }
}

@Composable
private fun QuizQuestionCard(
    vm: AppViewModel,
    question: QuizQuestion,
    oral: Boolean,
    showAnswer: Boolean,
) {
    val session = vm.quizSession ?: return
    val correct = session.wasCorrect == true
    val containerColor = when {
        showAnswer && correct -> MaterialTheme.colorScheme.primaryContainer
        showAnswer -> MaterialTheme.colorScheme.errorContainer
        else -> MaterialTheme.colorScheme.surfaceVariant
    }
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = containerColor),
    ) {
        Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            if (showAnswer && session.submitted) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite },
                ) {
                    Icon(
                        if (correct) Icons.Outlined.CheckCircle else Icons.Outlined.ErrorOutline,
                        contentDescription = null,
                        tint = if (correct) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error,
                    )
                    Spacer(Modifier.width(8.dp))
                    Text(
                        if (correct) "정답입니다" else "정답을 확인해 보세요",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold,
                    )
                }
                Text("정답", style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.Bold)
                MarkdownText(
                    markdown = question.explanationSteps.answer,
                    style = MaterialTheme.typography.titleLarge,
                    color = MaterialTheme.colorScheme.onSurface,
                )
                if (!oral && session.userAnswer.isNotBlank()) {
                    Text("내 답", style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.Bold)
                    MarkdownText(
                        markdown = userAnswerSummary(question, session.userAnswer),
                        style = MaterialTheme.typography.bodyLarge,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            } else {
                Text("문제", style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.Bold)
                val prompt = if (oral) {
                    val title = vm.allElements.firstOrNull { it.id == question.elementId }?.title ?: question.elementId
                    "‘$title’를 정의·핵심 관계·가정·금융권 실무 해석 순서로 30~60초 동안 설명하세요."
                } else {
                    question.prompt.financeCareerCopy()
                }
                MarkdownText(
                    markdown = prompt,
                    style = if (session.track == QuizTrack.DOMAIN) {
                        MaterialTheme.typography.titleMedium
                    } else {
                        MaterialTheme.typography.headlineSmall
                    },
                    color = MaterialTheme.colorScheme.onSurface,
                )

                if (!oral && question.answer.kind == QuizAnswerKind.MULTIPLE_CHOICE) {
                    question.choices.orEmpty().forEach { choice ->
                        ChoiceButton(
                            choiceId = choice.id,
                            text = choice.text,
                            selected = session.userAnswer == choice.id,
                            enabled = !session.submitted,
                            onClick = { vm.setQuizAnswer(choice.id) },
                        )
                    }
                } else if (!oral) {
                    OutlinedTextField(
                        value = session.userAnswer,
                        onValueChange = { raw ->
                            val cleaned = raw.filterIndexed { index, char ->
                                char.isDigit() || char == ',' || char == ' ' ||
                                    (char == '-' || char == '−' || char == '+') && index == 0
                            }
                            vm.setQuizAnswer(cleaned)
                        },
                        modifier = Modifier.fillMaxWidth(),
                        label = { Text("정수 답") },
                        suffix = { if (question.answerUnit.isNotBlank()) Text(question.answerUnit) },
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                        singleLine = true,
                        enabled = !session.submitted,
                        supportingText = { Text("쉼표와 음수 부호를 사용할 수 있습니다.") },
                    )
                }

                if (!session.submitted) {
                    if (oral) {
                        Text(
                            "말하기를 마친 뒤 스스로 평가하세요. 제출 후 핵심 답안을 보여드립니다.",
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            OutlinedButton(onClick = { vm.submitQuizAnswer(false) }, modifier = Modifier.weight(1f)) {
                                Text("복습 필요")
                            }
                            Button(onClick = { vm.submitQuizAnswer(true) }, modifier = Modifier.weight(1f)) {
                                Text("핵심 포함")
                            }
                        }
                    } else {
                        Button(
                            onClick = { vm.submitQuizAnswer() },
                            enabled = session.userAnswer.isNotBlank(),
                            modifier = Modifier.fillMaxWidth(),
                        ) { Text("답 제출") }
                    }
                }
            }
        }
    }
}

@Composable
private fun QuizFaceToggle(
    showAnswer: Boolean,
    showQuestion: () -> Unit,
    onShowAnswer: () -> Unit,
) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        FilterChip(
            selected = !showAnswer,
            onClick = showQuestion,
            label = { Text("문제 보기") },
            modifier = Modifier.weight(1f),
        )
        FilterChip(
            selected = showAnswer,
            onClick = onShowAnswer,
            label = { Text("정답 보기") },
            modifier = Modifier.weight(1f),
        )
    }
}

@Composable
private fun ChoiceButton(
    choiceId: String,
    text: String,
    selected: Boolean,
    enabled: Boolean,
    onClick: () -> Unit,
) {
    val container = if (selected) MaterialTheme.colorScheme.secondaryContainer else MaterialTheme.colorScheme.surface
    OutlinedCard(
        modifier = Modifier
            .fillMaxWidth()
            .selectable(
                selected = selected,
                enabled = enabled,
                role = Role.RadioButton,
                onClick = onClick,
            ),
        colors = CardDefaults.outlinedCardColors(containerColor = container),
    ) {
        Row(Modifier.padding(15.dp), verticalAlignment = Alignment.CenterVertically) {
            Box(
                Modifier
                    .background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(8.dp))
                    .padding(horizontal = 9.dp, vertical = 5.dp)
            ) {
                Text(choiceId, fontWeight = FontWeight.Bold)
            }
            Spacer(Modifier.width(10.dp))
            Text(text, modifier = Modifier.weight(1f))
        }
    }
}

@Composable
private fun SolutionContent(question: QuizQuestion) {
    OutlinedCard(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(11.dp)) {
            Text("풀이", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
            ExplanationLine("관련 개념", question.explanationSteps.concept)
            ExplanationLine("수식", question.explanationSteps.formula)
            ExplanationLine("숫자 대입", question.explanationSteps.substitution)
            if (question.mode == QuizMode.CALCULATION && question.audit.operations.isNotEmpty()) {
                ExplanationLine(
                    "암산 경로",
                    question.audit.operations.joinToString("\n") { "- `${it.expression} = ${it.result}`" },
                )
            }
            ExplanationLine("정답", question.explanationSteps.answer)
            ExplanationLine("해석", question.explanationSteps.interpretation)
            Text(
                "snapshot ${question.snapshot.id.take(12)}… · seed ${question.snapshot.generationSeed}",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Composable
private fun ExplanationLine(label: String, value: String) {
    if (value.isBlank()) return
    Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Text(label, style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.Bold)
        MarkdownText(
            markdown = explanationMarkdown(label, value),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurface,
        )
    }
}

@Composable
private fun QuizResultScreen(vm: AppViewModel) {
    val session = vm.quizSession ?: return
    val total = session.questions.size
    val accuracy = if (total == 0) 0 else session.correctCount * 100 / total
    Column(
        Modifier.fillMaxSize().widthIn(max = 680.dp).padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Icon(Icons.Outlined.CheckCircle, contentDescription = null, tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(54.dp))
        Spacer(Modifier.height(16.dp))
        Text("세션 완료", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
        Text("${session.correctCount} / $total 정답 · $accuracy%", style = MaterialTheme.typography.titleLarge)
        Spacer(Modifier.height(8.dp))
        Text(
            if (accuracy >= 80) "다음 난이도를 섞어도 좋습니다." else "오답은 약점 집중 모드에서 다시 만날 수 있습니다.",
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Spacer(Modifier.height(24.dp))
        Button(onClick = { vm.leaveQuiz(); vm.selectTab(MainTab.QUIZ) }, modifier = Modifier.fillMaxWidth()) { Text("새 퀴즈 만들기") }
        TextButton(onClick = { vm.leaveQuiz(); vm.selectTab(MainTab.HOME) }) { Text("오늘 화면으로") }
    }
}

@Composable
private fun RecordsScreen(
    vm: AppViewModel,
    exportBackup: () -> Unit,
    importBackup: () -> Unit,
    requestReset: () -> Unit,
) {
    var section by rememberSaveable { mutableStateOf(RecordSection.WRONG) }
    LazyColumn(
        modifier = pageWidth(),
        contentPadding = pagePadding(),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        item {
            PageHeader(
                eyebrow = "LOCAL RECORDS",
                title = "학습 기록",
                description = "누적 성적은 유지하고, 상세 기록은 가볍게 관리합니다. 분야와 단원별로 최근 오답·북마크를 확인하세요.",
            )
        }
        item {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                StatCard("풀이", "${vm.stats.attempted}", Icons.Outlined.Quiz, Modifier.weight(1f))
                StatCard("정답률", "${vm.stats.accuracyPercent}%", Icons.Outlined.CheckCircle, Modifier.weight(1f))
                StatCard("오답", "${vm.stats.wrongUnresolved}", Icons.Outlined.RestartAlt, Modifier.weight(1f), MaterialTheme.colorScheme.error)
            }
        }
        item {
            LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                items(RecordSection.entries) { item ->
                    FilterChip(selected = section == item, onClick = { section = item }, label = { Text(item.label) })
                }
            }
        }
        if (section != RecordSection.DATA) {
            item { RecordScopeFilters(vm) }
        }
        when (section) {
            RecordSection.WRONG -> {
                item {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        SectionTitle("단원별 최근 오답", "${vm.recentWrong.size}건", Modifier.weight(1f))
                        if (vm.recordUnresolvedWrongCount > 0) {
                            TextButton(onClick = vm::startRecordWeakQuiz) { Text("이 범위 풀기") }
                        }
                    }
                }
                if (vm.recentWrong.isEmpty()) item { EmptyState(Icons.Outlined.CheckCircle, "아직 오답이 없습니다", "첫 퀴즈를 풀면 이곳에 복습 기록이 쌓입니다.") }
                else items(vm.recentWrong, key = { it.id }) { WrongCard(it, vm) }
            }
            RecordSection.BOOKMARKS -> {
                item { SectionTitle("최근 북마크", "${vm.recordBookmarks.size}개") }
                if (vm.recordBookmarks.isEmpty()) item { EmptyState(Icons.Outlined.BookmarkBorder, "저장한 문제가 없습니다", "문제를 푼 뒤 북마크 버튼을 누르면 동일 snapshot을 다시 볼 수 있습니다.") }
                else items(vm.recordBookmarks, key = { it.instanceId }) { bookmark -> BookmarkCard(bookmark, vm) }
            }
            RecordSection.DATA -> {
                item { DataSettingsCard(vm, exportBackup, importBackup, requestReset) }
            }
        }
    }
}

private enum class RecordSection(val label: String) { WRONG("오답"), BOOKMARKS("북마크"), DATA("백업·정보") }

@Composable
private fun RecordScopeFilters(vm: AppViewModel) {
    val scopedElements = vm.recordDomainId?.let { domainId ->
        vm.allElements.filter { it.domainId == domainId }
    }.orEmpty()
    OutlinedCard(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(9.dp)) {
            Text("조회 범위", style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.Bold)
            LazyRow(horizontalArrangement = Arrangement.spacedBy(7.dp)) {
                item {
                    FilterChip(
                        selected = vm.recordDomainId == null,
                        onClick = { vm.setRecordDomain(null) },
                        label = { Text("전체") },
                    )
                }
                items(vm.domains, key = { it.id }) { domain ->
                    FilterChip(
                        selected = vm.recordDomainId == domain.id,
                        onClick = { vm.setRecordDomain(domain.id) },
                        label = { Text(domain.id) },
                    )
                }
            }
            if (vm.recordDomainId != null) {
                Text("단원", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                LazyRow(horizontalArrangement = Arrangement.spacedBy(7.dp)) {
                    item {
                        FilterChip(
                            selected = vm.recordElementId == null,
                            onClick = { vm.setRecordElement(null) },
                            label = { Text("전체 단원") },
                        )
                    }
                    items(scopedElements, key = { it.id }) { element ->
                        FilterChip(
                            selected = vm.recordElementId == element.id,
                            onClick = { vm.setRecordElement(element.id) },
                            label = {
                                Text(
                                    "${element.id} · ${element.title}",
                                    maxLines = 1,
                                    overflow = TextOverflow.Ellipsis,
                                )
                            },
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun WrongCard(attempt: AttemptRecord, vm: AppViewModel) {
    OutlinedCard {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                DomainBadge(attempt.elementId.substringBefore('-'))
                Spacer(Modifier.width(8.dp))
                Text(attempt.elementId, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
                Text(formatDate(attempt.createdAt), style = MaterialTheme.typography.labelSmall)
            }
            Text(attempt.prompt.financeCareerCopy(), maxLines = 3, overflow = TextOverflow.Ellipsis)
            Text("내 답: ${attempt.userAnswer} · 정답: ${attempt.canonicalAnswer}", color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
            if (vm.resolutionSuggested(attempt.elementId, attempt.templateId)) {
                Text("이 유형을 두 번 연속 맞혔습니다.", color = MaterialTheme.colorScheme.primary, style = MaterialTheme.typography.bodySmall)
                TextButton(onClick = { vm.confirmWrongResolved(attempt.elementId, attempt.templateId) }) {
                    Icon(Icons.Outlined.CheckCircle, contentDescription = null)
                    Spacer(Modifier.width(6.dp))
                    Text("오답 해결 처리")
                }
            }
        }
    }
}

@Composable
private fun BookmarkCard(bookmark: BookmarkRecord, vm: AppViewModel) {
    OutlinedCard {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(9.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Outlined.Bookmark, contentDescription = null, tint = MaterialTheme.colorScheme.tertiary)
                Spacer(Modifier.width(8.dp))
                Text(bookmark.elementId, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
                Text(if (bookmark.mode == QuizMode.CALCULATION.name) "암산" else "개념", style = MaterialTheme.typography.labelSmall)
            }
            Text("seed ${bookmark.seed} · ${formatDate(bookmark.createdAt)}", color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.bodySmall)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(onClick = { vm.startBookmarkReview(bookmark) }, modifier = Modifier.weight(1f)) { Text("같은 문제") }
                Button(onClick = { vm.startBookmarkReview(bookmark, freshNumbers = true) }, modifier = Modifier.weight(1f)) {
                    Text(if (bookmark.mode == QuizMode.CALCULATION.name) "새 숫자" else "새 문제")
                }
            }
        }
    }
}

@Composable
private fun DataSettingsCard(
    vm: AppViewModel,
    exportBackup: () -> Unit,
    importBackup: () -> Unit,
    requestReset: () -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
        OutlinedCard {
            Column(Modifier.padding(17.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text("수동 백업", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                Text("OneDrive SDK나 자동 동기화 없이, 사용자가 선택한 위치로 무결성 해시가 포함된 JSON을 내보냅니다.")
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(onClick = importBackup, modifier = Modifier.weight(1f)) {
                        Icon(Icons.Outlined.Upload, contentDescription = null)
                        Spacer(Modifier.width(6.dp))
                        Text("가져오기")
                    }
                    Button(onClick = exportBackup, modifier = Modifier.weight(1f)) {
                        Icon(Icons.Outlined.Download, contentDescription = null)
                        Spacer(Modifier.width(6.dp))
                        Text("내보내기")
                    }
                }
            }
        }
        OutlinedCard {
            Row(Modifier.padding(17.dp), verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("오답 자동 북마크", fontWeight = FontWeight.Bold)
                    Text("틀린 문제 snapshot을 바로 저장합니다.", style = MaterialTheme.typography.bodySmall)
                }
                Switch(checked = vm.autoBookmarkWrong, onCheckedChange = vm::updateAutoBookmarkWrong)
            }
        }
        OutlinedCard {
            Column(Modifier.padding(17.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("기록 저장 최적화", fontWeight = FontWeight.Bold)
                Text(
                    "누적 풀이·정답 통계는 단원별 집계로 계속 보존합니다. 용량이 큰 상세 풀이만 단원당 최근 20개·전체 2,000개로 관리하며, 미해결 최신 오답과 수동 북마크는 자동 삭제하지 않습니다.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
        OutlinedCard {
            Column(Modifier.padding(17.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("앱 정보", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                Text("FinDone ${BuildConfig.VERSION_NAME} · 개인 Android 사이드로드")
                Text("콘텐츠 DB v${vm.contentManifest?.contentDbVersion ?: "-"} · 사용자 DB schema 3")
                Text("특정 학회 공식 기출이 아닌 자체 제작 문제입니다. 실시간 투자정보나 투자 조언을 제공하지 않습니다.", color = MaterialTheme.colorScheme.onSurfaceVariant)
                HorizontalDivider()
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Outlined.CloudOff, contentDescription = null)
                    Spacer(Modifier.width(8.dp))
                    Text("INTERNET 권한·로그인·광고·분석·결제 없음", style = MaterialTheme.typography.labelLarge)
                }
            }
        }
        OutlinedButton(onClick = requestReset, modifier = Modifier.fillMaxWidth(), colors = ButtonDefaults.outlinedButtonColors(contentColor = MaterialTheme.colorScheme.error)) {
            Icon(Icons.Outlined.DeleteForever, contentDescription = null)
            Spacer(Modifier.width(7.dp))
            Text("학습 기록 초기화")
        }
    }
}

@Composable
private fun EmptyState(icon: androidx.compose.ui.graphics.vector.ImageVector, title: String, description: String) {
    Column(
        Modifier.fillMaxWidth().padding(vertical = 34.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Icon(icon, contentDescription = null, tint = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.size(38.dp))
        Text(title, fontWeight = FontWeight.Bold)
        Text(description, color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.bodySmall)
    }
}

@Composable
private fun QuizBadge(text: String) {
    Box(
        Modifier
            .background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(9.dp))
            .padding(horizontal = 10.dp, vertical = 7.dp)
    ) {
        Text(text, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

private fun QuizTrack.displayTitle(): String = when (this) {
    QuizTrack.SPRINT -> "금융권 스프린트"
    else -> title
}

private fun String.financeCareerCopy(): String =
    replace("면접 답변의 핵심 문장이", "금융권 실무 설명의 핵심 문장이")
        .replace("면접 해석", "금융권 실무 해석")

private fun userAnswerSummary(question: QuizQuestion, userAnswer: String): String {
    if (question.answer.kind == QuizAnswerKind.MULTIPLE_CHOICE) {
        val choice = question.choices.orEmpty().firstOrNull { it.id == userAnswer }
        if (choice != null) return "${choice.id}. ${choice.text}"
    }
    return listOf(userAnswer, question.answerUnit).filter { it.isNotBlank() }.joinToString(" ")
}

private fun explanationMarkdown(label: String, value: String): String = when (label) {
    "수식", "숫자 대입" -> if ('$' in value || '`' in value) value else "`${value.replace("`", "\\`")}`"
    "정답" -> if ('*' in value) value else "**$value**"
    else -> value
}

private fun pageWidth(): Modifier = Modifier.widthIn(max = 860.dp).fillMaxSize()
private fun pagePadding(): PaddingValues = PaddingValues(start = 20.dp, end = 20.dp, top = 20.dp, bottom = 32.dp)
private fun formatDate(timestamp: Long): String = SimpleDateFormat("M.d HH:mm", Locale.KOREA).format(Date(timestamp))
private fun backupDate(): String = SimpleDateFormat("yyyyMMdd-HHmm", Locale.US).format(Date())
