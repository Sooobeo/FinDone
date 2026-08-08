package com.findone.app.ui

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.CheckCircle
import androidx.compose.material.icons.outlined.FolderOpen
import androidx.compose.material.icons.outlined.Home
import androidx.compose.material.icons.outlined.Info
import androidx.compose.material.icons.outlined.Refresh
import androidx.compose.material.icons.outlined.Security
import androidx.compose.material.icons.outlined.SystemUpdate
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import com.findone.app.BuildConfig
import com.findone.app.R
import com.findone.app.update.AppUpdateManager
import com.findone.app.update.AvailableRelease
import com.findone.app.update.InstallUiVisibility
import com.findone.app.update.PreparedUpdate
import com.findone.app.update.PendingInstallStatus
import com.findone.app.update.ReleaseScanResult
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

@Composable
fun UpdateLandingScreen(onContinue: () -> Unit) {
    val context = LocalContext.current
    val manager = remember(context.applicationContext) { AppUpdateManager(context) }
    val scope = rememberCoroutineScope()
    val lifecycleOwner = LocalLifecycleOwner.current
    var busyMessage by remember { mutableStateOf<String?>(null) }
    var statusMessage by rememberSaveable { mutableStateOf<String?>(null) }
    var errorMessage by rememberSaveable { mutableStateOf<String?>(null) }
    var completedVersion by rememberSaveable { mutableStateOf<String?>(null) }
    var preparedUpdate by remember { mutableStateOf<PreparedUpdate?>(null) }
    var pendingInstallStatus by remember { mutableStateOf<PendingInstallStatus>(PendingInstallStatus.None) }
    var scanState by remember { mutableStateOf<ReleaseScanResult?>(null) }
    var refreshRequest by remember { mutableIntStateOf(0) }
    var resumeRequest by remember { mutableIntStateOf(0) }

    DisposableEffect(lifecycleOwner) {
        InstallUiVisibility.setLandingForeground(
            lifecycleOwner.lifecycle.currentState.isAtLeast(Lifecycle.State.RESUMED),
        )
        val observer = LifecycleEventObserver { _, event ->
            when (event) {
                Lifecycle.Event.ON_RESUME -> {
                    InstallUiVisibility.setLandingForeground(true)
                    resumeRequest += 1
                }
                Lifecycle.Event.ON_PAUSE -> InstallUiVisibility.setLandingForeground(false)
                else -> Unit
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose {
            InstallUiVisibility.setLandingForeground(false)
            lifecycleOwner.lifecycle.removeObserver(observer)
        }
    }

    LaunchedEffect(resumeRequest) {
        pendingInstallStatus = withContext(Dispatchers.IO) { manager.reconcilePendingInstall() }
        manager.consumeCompletedVersion()?.let { completedVersion = it }
        manager.consumeInstallFailure()?.let { failure ->
            errorMessage = failure
            statusMessage = null
        }
    }

    LaunchedEffect(refreshRequest) {
        scanState = null
        scanState = withContext(Dispatchers.IO) {
            manager.scanConnectedReleases(BuildConfig.VERSION_CODE.toLong())
        }
    }

    val submitInstall: suspend (PreparedUpdate) -> Unit = { update ->
        busyMessage = "Android 설치 화면을 준비하고 있습니다."
        val result = runCatching {
            withContext(Dispatchers.IO) { manager.installPreparedUpdate(update) }
        }.onSuccess {
            statusMessage = "업데이트 v${update.versionName} 설치 요청을 보냈습니다. Android 설치 화면에서 ‘설치’를 누르세요. 설치가 끝나면 시스템 화면의 ‘열기’를 눌러 새 버전을 실행할 수 있습니다."
            errorMessage = null
        }.onFailure { error ->
            errorMessage = error.message ?: "업데이트 설치를 시작하지 못했습니다."
        }
        busyMessage = null
        if (result.isSuccess) {
            delay(350)
            pendingInstallStatus = withContext(Dispatchers.IO) { manager.reconcilePendingInstall() }
        }
    }

    val unknownAppsLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.StartActivityForResult(),
    ) {
        scope.launch {
            if (!manager.canInstallUnknownApps()) {
                errorMessage = "이 출처의 앱 설치 권한이 허용되지 않았습니다. 업데이트하려면 설정에서 FinDone을 허용해 주세요."
                return@launch
            }
            val update = preparedUpdate ?: runCatching {
                withContext(Dispatchers.IO) { manager.loadPreparedUpdate() }
            }.getOrNull()
            if (update == null) {
                errorMessage = "준비된 업데이트 파일을 찾지 못했습니다. APK를 다시 선택해 주세요."
                return@launch
            }
            submitInstall(update)
        }
    }

    val prepareAndRequestInstall: suspend (android.net.Uri, AvailableRelease?) -> Unit = { apkUri, release ->
        busyMessage = "APK의 패키지, 버전, 서명을 확인하고 있습니다."
        val result = runCatching {
            withContext(Dispatchers.IO) {
                manager.prepareUpdate(
                    uri = apkUri,
                    expectedSha256 = release?.expectedSha256,
                    expectedVersionCode = release?.versionCode,
                    expectedVersionName = release?.versionName,
                )
            }
        }
        busyMessage = null
        result.onSuccess { update ->
            preparedUpdate = update
            errorMessage = null
            if (manager.canInstallUnknownApps()) {
                submitInstall(update)
            } else {
                statusMessage = "검증을 마쳤습니다. Android 설정에서 ‘이 출처 허용’을 켜면 설치를 계속합니다."
                runCatching {
                    unknownAppsLauncher.launch(manager.unknownAppsSettingsIntent())
                }.onFailure {
                    statusMessage = null
                    errorMessage = "이 출처의 앱 설치 설정 화면을 열지 못했습니다. 기기 설정에서 FinDone을 직접 허용해 주세요."
                }
            }
        }.onFailure { error ->
            statusMessage = null
            errorMessage = error.message ?: "APK를 확인하지 못했습니다."
        }
    }

    val apkPicker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri == null) return@rememberLauncherForActivityResult
        scope.launch { prepareAndRequestInstall(uri, null) }
    }

    val releaseTreePicker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocumentTree()) { uri ->
        if (uri == null) {
            errorMessage = "릴리스 폴더 연결이 취소되었습니다. 기존 연결이 있다면 그대로 유지됩니다."
            return@rememberLauncherForActivityResult
        }
        scope.launch {
            busyMessage = "릴리스 폴더 읽기 권한을 저장하고 있습니다."
            val result = runCatching {
                withContext(Dispatchers.IO) {
                    manager.connectReleaseTree(uri)
                    manager.scanConnectedReleases(BuildConfig.VERSION_CODE.toLong())
                }
            }
            busyMessage = null
            result.onSuccess { scanResult ->
                scanState = scanResult
                errorMessage = null
            }.onFailure { error ->
                errorMessage = error.message ?: "릴리스 폴더를 연결하지 못했습니다."
            }
        }
    }

    Scaffold { scaffoldPadding ->
        LazyColumn(
            modifier = Modifier
                .padding(scaffoldPadding)
                .fillMaxSize()
                .widthIn(max = 680.dp)
                .padding(horizontal = 22.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            item { Spacer(Modifier.height(24.dp)) }
            item {
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Image(
                        painter = painterResource(R.drawable.ic_launcher_findone),
                        contentDescription = null,
                        modifier = Modifier.size(58.dp),
                    )
                    Text(
                        "FinDone",
                        style = MaterialTheme.typography.headlineLarge,
                        fontWeight = FontWeight.Bold,
                    )
                    Text(
                        "금융권 학습을 시작하기 전에 앱 버전을 확인하세요.",
                        style = MaterialTheme.typography.bodyLarge,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
            item {
                Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
                    Row(
                        Modifier.fillMaxWidth().padding(18.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Icon(Icons.Outlined.Info, contentDescription = null)
                        Spacer(Modifier.width(12.dp))
                        Column(Modifier.weight(1f)) {
                            Text("현재 설치 버전", style = MaterialTheme.typography.labelLarge)
                            Text(
                                "v${BuildConfig.VERSION_NAME} (versionCode ${BuildConfig.VERSION_CODE})",
                                style = MaterialTheme.typography.titleMedium,
                                fontWeight = FontWeight.Bold,
                            )
                        }
                    }
                }
            }
            completedVersion?.let { version ->
                item {
                    MessageCard(
                        icon = { Icon(Icons.Outlined.CheckCircle, contentDescription = null) },
                        title = "업데이트 완료",
                        message = "FinDone v$version 업데이트가 적용되었습니다.",
                        success = true,
                    )
                }
            }
            statusMessage?.let { message ->
                item {
                    MessageCard(
                        icon = { Icon(Icons.Outlined.SystemUpdate, contentDescription = null) },
                        title = "업데이트 안내",
                        message = message,
                    )
                }
            }
            errorMessage?.let { message ->
                item {
                    MessageCard(
                        icon = { Icon(Icons.Outlined.Info, contentDescription = null) },
                        title = "업데이트를 진행하지 못했습니다",
                        message = message,
                        isError = true,
                    )
                }
            }
            when (val pending = pendingInstallStatus) {
                PendingInstallStatus.None -> Unit
                is PendingInstallStatus.Waiting -> item {
                    MessageCard(
                        icon = { Icon(Icons.Outlined.SystemUpdate, contentDescription = null) },
                        title = "v${pending.versionName} 설치 확인 대기 중",
                        message = "Android 시스템 설치 화면을 완료한 뒤 FinDone으로 돌아오면 상태를 다시 확인합니다.",
                    )
                }
                is PendingInstallStatus.RetryRequired -> item {
                    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.errorContainer)) {
                        Column(
                            Modifier.fillMaxWidth().padding(16.dp),
                            verticalArrangement = Arrangement.spacedBy(10.dp),
                        ) {
                            Text(
                                "v${pending.versionName} 설치를 다시 확인해야 합니다",
                                fontWeight = FontWeight.Bold,
                                color = MaterialTheme.colorScheme.onErrorContainer,
                            )
                            Text(
                                pending.message,
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onErrorContainer,
                            )
                            Button(
                                onClick = {
                                    scope.launch {
                                        busyMessage = "캐시된 APK로 설치를 다시 준비하고 있습니다."
                                        val retry = runCatching {
                                            withContext(Dispatchers.IO) { manager.retryPendingInstall() }
                                        }
                                        busyMessage = null
                                        retry.onSuccess {
                                            statusMessage = "Android 설치 화면을 다시 요청했습니다."
                                            errorMessage = null
                                        }.onFailure { error ->
                                            statusMessage = null
                                            errorMessage = error.message ?: "설치를 다시 시작하지 못했습니다."
                                        }
                                        pendingInstallStatus = withContext(Dispatchers.IO) {
                                            manager.reconcilePendingInstall()
                                        }
                                    }
                                },
                                enabled = busyMessage == null,
                            ) {
                                Icon(Icons.Outlined.Refresh, contentDescription = null)
                                Spacer(Modifier.width(7.dp))
                                Text("설치 다시 시도")
                            }
                        }
                    }
                }
            }
            item {
                Card {
                    Column(
                        Modifier.padding(18.dp),
                        verticalArrangement = Arrangement.spacedBy(12.dp),
                    ) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Icon(Icons.Outlined.Security, contentDescription = null)
                            Spacer(Modifier.width(9.dp))
                            Text("오프라인 보안 업데이트", fontWeight = FontWeight.Bold)
                        }
                        Text(
                            "OneDrive 등에서 릴리스 폴더를 한 번 연결하면 시작할 때 새 버전을 자동으로 확인합니다. 파일은 외부로 전송되지 않습니다.",
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                        when (val state = scanState) {
                            null -> Row(
                                horizontalArrangement = Arrangement.spacedBy(10.dp),
                                verticalAlignment = Alignment.CenterVertically,
                            ) {
                                CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp)
                                Text("연결된 릴리스 폴더를 확인하는 중입니다.")
                            }

                            ReleaseScanResult.NotConnected -> Text(
                                "릴리스 root가 아직 연결되지 않았습니다. findone-* 폴더들이 바로 아래에 있는 폴더를 선택해 주세요.",
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )

                            is ReleaseScanResult.NoUpdate -> MessageCard(
                                icon = { Icon(Icons.Outlined.CheckCircle, contentDescription = null) },
                                title = "현재 버전이 최신입니다",
                                message = "${state.rootName}에서 ${state.releaseFoldersChecked}개 릴리스 폴더를 확인했습니다.",
                                success = true,
                            )

                            is ReleaseScanResult.UpdateAvailable -> {
                                MessageCard(
                                    icon = { Icon(Icons.Outlined.SystemUpdate, contentDescription = null) },
                                    title = "새 버전 v${state.release.versionName}",
                                    message = "${state.release.folderName} · versionCode ${state.release.versionCode}",
                                    success = true,
                                )
                                Button(
                                    onClick = {
                                        statusMessage = null
                                        errorMessage = null
                                        scope.launch {
                                            prepareAndRequestInstall(
                                                state.release.apkUri,
                                                state.release,
                                            )
                                        }
                                    },
                                    enabled = busyMessage == null && pendingInstallStatus is PendingInstallStatus.None,
                                    modifier = Modifier.fillMaxWidth(),
                                ) {
                                    Icon(Icons.Outlined.SystemUpdate, contentDescription = null)
                                    Spacer(Modifier.width(8.dp))
                                    Text("v${state.release.versionName} 업데이트")
                                }
                            }

                            is ReleaseScanResult.PermissionRequired -> MessageCard(
                                icon = { Icon(Icons.Outlined.Info, contentDescription = null) },
                                title = "폴더 권한이 필요합니다",
                                message = state.message,
                                isError = true,
                            )

                            is ReleaseScanResult.Failure -> MessageCard(
                                icon = { Icon(Icons.Outlined.Info, contentDescription = null) },
                                title = "릴리스 확인 오류",
                                message = state.message,
                                isError = true,
                            )
                        }
                        Row(
                            Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                        ) {
                            OutlinedButton(
                                onClick = { releaseTreePicker.launch(null) },
                                enabled = busyMessage == null,
                                modifier = Modifier.weight(1f),
                            ) {
                                Icon(Icons.Outlined.FolderOpen, contentDescription = null)
                                Spacer(Modifier.width(6.dp))
                                Text(if (scanState is ReleaseScanResult.NotConnected) "폴더 연결" else "폴더 재연결")
                            }
                            OutlinedButton(
                                onClick = { refreshRequest += 1 },
                                enabled = busyMessage == null &&
                                    scanState != null &&
                                    scanState !is ReleaseScanResult.NotConnected,
                                modifier = Modifier.weight(1f),
                            ) {
                                Icon(Icons.Outlined.Refresh, contentDescription = null)
                                Spacer(Modifier.width(6.dp))
                                Text("새로고침")
                            }
                        }
                        HorizontalDivider()
                        Text(
                            "폴더를 연결할 수 없으면 APK 파일을 직접 선택할 수도 있습니다. 어떤 방식이든 패키지명·서명키가 같고 versionCode가 더 높은 APK만 설치합니다.",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                        OutlinedButton(
                            onClick = {
                                statusMessage = null
                                errorMessage = null
                                apkPicker.launch(
                                    arrayOf(
                                        "application/vnd.android.package-archive",
                                        "application/octet-stream",
                                    ),
                                )
                            },
                            enabled = busyMessage == null && pendingInstallStatus is PendingInstallStatus.None,
                            modifier = Modifier.fillMaxWidth(),
                        ) {
                            Icon(Icons.Outlined.FolderOpen, contentDescription = null)
                            Spacer(Modifier.width(8.dp))
                            Text("APK 파일 직접 선택")
                        }
                        Text(
                            "Android 보안 정책상 설치 확인과 재실행은 시스템 화면에서 직접 해야 합니다. 앱이 스스로 강제 종료하거나 자동으로 다시 켜지는 방식은 사용하지 않습니다.",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
            }
            item {
                Button(
                    onClick = {
                        completedVersion = null
                        onContinue()
                    },
                    enabled = busyMessage == null,
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Icon(Icons.Outlined.Home, contentDescription = null)
                    Spacer(Modifier.width(8.dp))
                    Text("홈으로 계속")
                }
            }
            item { Spacer(Modifier.height(24.dp)) }
        }
    }

    busyMessage?.let { message ->
        Dialog(
            onDismissRequest = {},
            properties = DialogProperties(dismissOnBackPress = false, dismissOnClickOutside = false),
        ) {
            Card(shape = RoundedCornerShape(20.dp)) {
                Row(
                    Modifier.padding(horizontal = 24.dp, vertical = 22.dp),
                    horizontalArrangement = Arrangement.spacedBy(15.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    CircularProgressIndicator(Modifier.size(30.dp), strokeWidth = 3.dp)
                    Text(message, modifier = Modifier.weight(1f))
                }
            }
        }
    }
}

@Composable
private fun MessageCard(
    icon: @Composable () -> Unit,
    title: String,
    message: String,
    success: Boolean = false,
    isError: Boolean = false,
) {
    val containerColor = when {
        isError -> MaterialTheme.colorScheme.errorContainer
        success -> MaterialTheme.colorScheme.primaryContainer
        else -> MaterialTheme.colorScheme.secondaryContainer
    }
    val contentColor = when {
        isError -> MaterialTheme.colorScheme.onErrorContainer
        success -> MaterialTheme.colorScheme.onPrimaryContainer
        else -> MaterialTheme.colorScheme.onSecondaryContainer
    }
    Card(colors = CardDefaults.cardColors(containerColor = containerColor, contentColor = contentColor)) {
        Row(
            Modifier.fillMaxWidth().padding(16.dp),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
            verticalAlignment = Alignment.Top,
        ) {
            icon()
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(title, fontWeight = FontWeight.Bold)
                Text(message, style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}
