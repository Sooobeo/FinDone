package com.findone.app.update

import android.app.PendingIntent
import android.content.ActivityNotFoundException
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageInfo
import android.content.pm.PackageInstaller
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.provider.Settings
import android.provider.DocumentsContract
import androidx.core.content.edit
import androidx.core.net.toUri
import java.io.File
import java.io.FileOutputStream
import java.security.MessageDigest

data class PreparedUpdate(
    val versionName: String,
    val versionCode: Long,
    internal val apkFile: File,
)

sealed interface PendingInstallStatus {
    data object None : PendingInstallStatus

    data class Waiting(
        val versionName: String,
        val versionCode: Long,
    ) : PendingInstallStatus

    data class RetryRequired(
        val versionName: String,
        val versionCode: Long,
        val message: String,
    ) : PendingInstallStatus
}

/** Process-local gate: the installer confirmation is opened only while the landing UI is visible. */
object InstallUiVisibility {
    @Volatile
    private var landingForeground = false

    fun setLandingForeground(foreground: Boolean) {
        landingForeground = foreground
    }

    fun isLandingForeground(): Boolean = landingForeground
}

class UpdatePreparationException(message: String, cause: Throwable? = null) : Exception(message, cause)

class AppUpdateManager(context: Context) {
    private val appContext = context.applicationContext
    private val packageManager = appContext.packageManager
    private val store = UpdateInstallStore(appContext)
    private val releaseTreeStore = ReleaseTreeStore(appContext)

    fun canInstallUnknownApps(): Boolean = packageManager.canRequestPackageInstalls()

    fun unknownAppsSettingsIntent(): Intent = Intent(
        Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
        "package:${appContext.packageName}".toUri(),
    )

    fun prepareUpdate(
        uri: Uri,
        expectedSha256: String? = null,
        expectedVersionCode: Long? = null,
        expectedVersionName: String? = null,
    ): PreparedUpdate {
        val directory = File(appContext.cacheDir, UPDATE_DIRECTORY).apply { mkdirs() }
        val temporary = File(directory, "$CACHED_APK_NAME.tmp")
        val cached = File(directory, CACHED_APK_NAME)
        val expectedHash = expectedSha256?.lowercase()?.also { hash ->
            if (!hash.matches(Regex("[0-9a-f]{64}"))) {
                throw UpdatePreparationException("릴리스 매니페스트의 APK 해시가 올바르지 않습니다.")
            }
        }
        val fileDigest = expectedHash?.let { MessageDigest.getInstance("SHA-256") }

        temporary.delete()
        try {
            appContext.contentResolver.openInputStream(uri)?.use { input ->
                FileOutputStream(temporary).use { output ->
                    val buffer = ByteArray(DEFAULT_BUFFER_SIZE)
                    var copied = 0L
                    while (true) {
                        val count = input.read(buffer)
                        if (count < 0) break
                        copied += count
                        if (copied > MAX_APK_BYTES) {
                            throw UpdatePreparationException("APK 파일이 허용 크기(500MB)를 초과합니다.")
                        }
                        fileDigest?.update(buffer, 0, count)
                        output.write(buffer, 0, count)
                    }
                    output.fd.sync()
                }
            } ?: throw UpdatePreparationException("선택한 APK 파일을 열 수 없습니다.")

            if (expectedHash != null) {
                val actualHash = fileDigest!!.digest().joinToString("") { byte -> "%02x".format(byte) }
                if (actualHash != expectedHash) {
                    throw UpdatePreparationException("APK SHA-256이 릴리스 매니페스트와 일치하지 않습니다.")
                }
            }

            cached.delete()
            if (!temporary.renameTo(cached)) {
                throw UpdatePreparationException("업데이트 APK를 앱 캐시에 저장하지 못했습니다.")
            }
            val prepared = validateCachedApk(cached)
            if (expectedVersionCode != null && expectedVersionName != null) {
                val expectedManifest = ReleaseManifestMetadata(
                    schemaVersion = 2,
                    applicationId = EXPECTED_APPLICATION_ID,
                    versionCode = expectedVersionCode,
                    versionName = expectedVersionName,
                    releaseApkSha256 = expectedHash,
                )
                if (!ReleaseSelectionPolicy.matchesManifestVersion(
                        manifest = expectedManifest,
                        apkVersionCode = prepared.versionCode,
                        apkVersionName = prepared.versionName,
                    )
                ) {
                    throw UpdatePreparationException("APK 버전이 릴리스 매니페스트와 일치하지 않습니다.")
                }
            } else if (expectedVersionCode != null || expectedVersionName != null) {
                throw UpdatePreparationException("릴리스 매니페스트의 버전 정보가 불완전합니다.")
            }
            return prepared
        } catch (error: UpdatePreparationException) {
            temporary.delete()
            cached.delete()
            throw error
        } catch (error: Exception) {
            temporary.delete()
            cached.delete()
            throw UpdatePreparationException("APK를 안전하게 읽는 중 오류가 발생했습니다.", error)
        }
    }

    fun loadPreparedUpdate(): PreparedUpdate? {
        val cached = File(File(appContext.cacheDir, UPDATE_DIRECTORY), CACHED_APK_NAME)
        if (!cached.isFile) return null
        return validateCachedApk(cached)
    }

    fun connectReleaseTree(treeUri: Uri) {
        if (!DocumentsContract.isTreeUri(treeUri)) {
            throw UpdatePreparationException("선택한 위치는 Android 문서 폴더가 아닙니다.")
        }
        try {
            appContext.contentResolver.takePersistableUriPermission(
                treeUri,
                Intent.FLAG_GRANT_READ_URI_PERMISSION,
            )
        } catch (error: RuntimeException) {
            throw UpdatePreparationException("선택한 릴리스 폴더의 지속 읽기 권한을 저장하지 못했습니다.", error)
        }

        val previous = releaseTreeStore.getTreeUri()
        releaseTreeStore.setTreeUri(treeUri)
        if (previous != null && previous != treeUri) {
            runCatching {
                appContext.contentResolver.releasePersistableUriPermission(
                    previous,
                    Intent.FLAG_GRANT_READ_URI_PERMISSION,
                )
            }
        }
    }

    fun scanConnectedReleases(installedVersionCode: Long): ReleaseScanResult {
        val treeUri = releaseTreeStore.getTreeUri() ?: return ReleaseScanResult.NotConnected
        return ReleaseTreeScanner(appContext.contentResolver).scan(
            treeUri = treeUri,
            installedApplicationId = EXPECTED_APPLICATION_ID,
            installedVersionCode = installedVersionCode,
        )
    }

    fun installPreparedUpdate(prepared: PreparedUpdate) {
        store.getPending()?.let { pending ->
            throw UpdatePreparationException(
                "FinDone v${pending.versionName} 설치가 이미 진행 중입니다. 완료하거나 다시 시도한 뒤 새 설치를 시작해 주세요.",
            )
        }
        val verified = validateCachedApk(prepared.apkFile)
        if (verified.versionCode != prepared.versionCode) {
            throw UpdatePreparationException("검증 후 APK가 변경되어 설치를 중단했습니다.")
        }

        val installer = packageManager.packageInstaller
        val params = PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL).apply {
            setAppPackageName(appContext.packageName)
            setSize(prepared.apkFile.length())
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                setRequireUserAction(PackageInstaller.SessionParams.USER_ACTION_REQUIRED)
            }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                setPackageSource(PackageInstaller.PACKAGE_SOURCE_LOCAL_FILE)
            }
        }

        var sessionId: Int? = null
        try {
            sessionId = installer.createSession(params)
            installer.openSession(sessionId).use { session ->
                prepared.apkFile.inputStream().use { input ->
                    session.openWrite("base.apk", 0, prepared.apkFile.length()).use { output ->
                        input.copyTo(output)
                        session.fsync(output)
                    }
                }

                store.markPending(sessionId, prepared.versionCode, prepared.versionName)
                val resultIntent = Intent(appContext, InstallStatusReceiver::class.java).apply {
                    action = ACTION_INSTALL_STATUS
                    `package` = appContext.packageName
                }
                val callback = PendingIntent.getBroadcast(
                    appContext,
                    sessionId,
                    resultIntent,
                    PendingIntent.FLAG_UPDATE_CURRENT or
                        PendingIntent.FLAG_MUTABLE,
                )
                session.commit(callback.intentSender)
                store.markCommitted(sessionId)
            }
        } catch (error: Exception) {
            sessionId?.let(store::clearPending)
            sessionId?.let { runCatching { installer.abandonSession(it) } }
            throw UpdatePreparationException("Android 설치 프로그램을 시작하지 못했습니다.", error)
        }
    }

    fun consumeCompletedVersion(): String? {
        val completed = store.consumeCompletedIfInstalled(installedVersionCode())
        if (completed != null) deleteCachedUpdateFiles()
        return completed
    }

    fun consumeInstallFailure(): String? = store.consumeFailure()

    fun reconcilePendingInstall(): PendingInstallStatus {
        cleanupStaleTemporaryApk()
        val pending = store.getPending() ?: run {
            cleanupAbandonedCachedApk()
            return PendingInstallStatus.None
        }
        if (installedVersionCode() >= pending.versionCode) {
            store.markSucceeded(pending.sessionId)
            deleteCachedUpdateFiles()
            return PendingInstallStatus.None
        }

        if (pending.phase == PendingInstallPhase.COMMITTING) {
            store.markRetryRequired(
                pending.sessionId,
                "이전 설치 요청이 완료되기 전에 중단되었습니다. 캐시된 APK로 설치를 다시 시도해 주세요.",
            )
        }
        val sessionExists = runCatching {
            packageManager.packageInstaller.getSessionInfo(pending.sessionId) != null
        }.getOrDefault(false)
        if (!sessionExists && pending.phase != PendingInstallPhase.RETRY_REQUIRED) {
            store.markRetryRequired(
                pending.sessionId,
                "이전 설치 세션을 찾을 수 없습니다. 캐시된 APK로 설치를 다시 시도해 주세요.",
            )
        }
        val current = store.getPending() ?: return PendingInstallStatus.None
        return if (current.phase == PendingInstallPhase.RETRY_REQUIRED) {
            PendingInstallStatus.RetryRequired(
                versionName = current.versionName,
                versionCode = current.versionCode,
                message = current.statusMessage ?: "설치 확인 화면을 열지 못했습니다. 다시 시도해 주세요.",
            )
        } else {
            PendingInstallStatus.Waiting(current.versionName, current.versionCode)
        }
    }

    fun retryPendingInstall() {
        val pending = store.getPending()
            ?: throw UpdatePreparationException("다시 시도할 설치가 없습니다.")
        runCatching { packageManager.packageInstaller.abandonSession(pending.sessionId) }
        store.clearPending(pending.sessionId)
        val prepared = try {
            loadPreparedUpdate()
        } catch (error: Exception) {
            null
        } ?: throw UpdatePreparationException("캐시된 APK가 없어 릴리스 폴더에서 업데이트를 다시 선택해야 합니다.")
        installPreparedUpdate(prepared)
    }

    private fun cleanupAbandonedCachedApk() {
        val cached = File(File(appContext.cacheDir, UPDATE_DIRECTORY), CACHED_APK_NAME)
        val staleBefore = System.currentTimeMillis() - STALE_CACHE_MILLIS
        if (cached.isFile && cached.lastModified() < staleBefore) cached.delete()
    }

    private fun cleanupStaleTemporaryApk() {
        val temporary = File(File(appContext.cacheDir, UPDATE_DIRECTORY), "$CACHED_APK_NAME.tmp")
        val staleBefore = System.currentTimeMillis() - STALE_TEMP_MILLIS
        if (temporary.isFile && temporary.lastModified() < staleBefore) temporary.delete()
    }

    private fun deleteCachedUpdateFiles() {
        val directory = File(appContext.cacheDir, UPDATE_DIRECTORY)
        File(directory, CACHED_APK_NAME).delete()
        File(directory, "$CACHED_APK_NAME.tmp").delete()
    }

    private fun validateCachedApk(apk: File): PreparedUpdate {
        if (!apk.isFile || apk.length() == 0L) {
            throw UpdatePreparationException("선택한 파일은 유효한 APK가 아닙니다.")
        }

        val installedInfo = installedPackageInfo()
        val archiveInfo = archivePackageInfo(apk)
            ?: throw UpdatePreparationException("선택한 파일에서 APK 정보를 읽을 수 없습니다.")
        val installed = installedInfo.toIdentity()
        val candidate = archiveInfo.toIdentity()

        when (val decision = UpdatePolicy.evaluate(installed, candidate)) {
            UpdateDecision.Allowed -> Unit
            is UpdateDecision.Rejected -> throw UpdatePreparationException(decision.reason.userMessage())
        }

        return PreparedUpdate(
            versionName = archiveInfo.versionName ?: candidate.versionCode.toString(),
            versionCode = candidate.versionCode,
            apkFile = apk,
        )
    }

    @Suppress("DEPRECATION")
    private fun installedPackageInfo(): PackageInfo = packageManager.getPackageInfo(
        appContext.packageName,
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            PackageManager.GET_SIGNING_CERTIFICATES
        } else {
            PackageManager.GET_SIGNATURES
        },
    )

    @Suppress("DEPRECATION")
    private fun archivePackageInfo(apk: File): PackageInfo? = packageManager.getPackageArchiveInfo(
        apk.absolutePath,
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            PackageManager.GET_SIGNING_CERTIFICATES
        } else {
            PackageManager.GET_SIGNATURES
        },
    )

    @Suppress("DEPRECATION")
    private fun PackageInfo.toIdentity(): AppIdentity {
        val signatures = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            signingInfo?.apkContentsSigners.orEmpty()
        } else {
            signatures.orEmpty()
        }
        return AppIdentity(
            packageName = packageName,
            versionCode = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                longVersionCode
            } else {
                versionCode.toLong()
            },
            signerSha256 = signatures.mapTo(mutableSetOf()) { signature ->
                MessageDigest.getInstance("SHA-256")
                    .digest(signature.toByteArray())
                    .joinToString("") { byte -> "%02x".format(byte) }
            },
        )
    }

    @Suppress("DEPRECATION")
    private fun installedVersionCode(): Long {
        val info = packageManager.getPackageInfo(appContext.packageName, 0)
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            info.longVersionCode
        } else {
            info.versionCode.toLong()
        }
    }

    private fun UpdateRejection.userMessage(): String = when (this) {
        UpdateRejection.PACKAGE_MISMATCH -> "FinDone용 APK가 아니어서 설치할 수 없습니다."
        UpdateRejection.VERSION_NOT_NEWER -> "현재 앱보다 versionCode가 높은 APK만 설치할 수 있습니다."
        UpdateRejection.SIGNING_CERTIFICATE_MISSING -> "APK 서명 인증서를 확인할 수 없습니다."
        UpdateRejection.SIGNING_CERTIFICATE_MISMATCH -> "현재 FinDone과 같은 서명키로 만든 APK만 설치할 수 있습니다."
    }

    companion object {
        internal const val ACTION_INSTALL_STATUS = "com.findone.app.action.INSTALL_STATUS"
        internal const val UPDATE_DIRECTORY = "updates"
        internal const val CACHED_APK_NAME = "pending-update.apk"
        private const val MAX_APK_BYTES = 500L * 1024L * 1024L
        private const val STALE_CACHE_MILLIS = 24L * 60L * 60L * 1000L
        private const val STALE_TEMP_MILLIS = 60L * 60L * 1000L
        private const val EXPECTED_APPLICATION_ID = "com.findone.app"
    }
}

private class ReleaseTreeStore(context: Context) {
    private val preferences = context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)

    fun getTreeUri(): Uri? = preferences.getString(KEY_TREE_URI, null)?.let { stored ->
        runCatching { stored.toUri() }.getOrNull()
    }

    fun setTreeUri(uri: Uri) {
        preferences.edit { putString(KEY_TREE_URI, uri.toString()) }
    }

    companion object {
        private const val PREFERENCES = "app_update_release_tree"
        private const val KEY_TREE_URI = "release_tree_uri"
    }
}

class InstallStatusReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != AppUpdateManager.ACTION_INSTALL_STATUS) return

        val store = UpdateInstallStore(context)
        val callbackSessionId = intent.getIntExtra(PackageInstaller.EXTRA_SESSION_ID, -1)
        if (!InstallCallbackPolicy.belongsToPendingSession(store.getPending()?.sessionId, callbackSessionId)) {
            return
        }
        when (val status = intent.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE)) {
            PackageInstaller.STATUS_PENDING_USER_ACTION -> {
                if (!InstallUiVisibility.isLandingForeground()) {
                    store.markRetryRequired(
                        callbackSessionId,
                        "FinDone 업데이트 화면이 보이지 않아 Android 설치 확인을 열지 않았습니다. 앱으로 돌아와 설치를 다시 시도해 주세요.",
                    )
                    return
                }
                val confirmation = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                    intent.getParcelableExtra(Intent.EXTRA_INTENT, Intent::class.java)
                } else {
                    @Suppress("DEPRECATION")
                    intent.getParcelableExtra(Intent.EXTRA_INTENT)
                }
                if (confirmation == null) {
                    store.markRetryRequired(
                        callbackSessionId,
                        "Android 설치 확인 화면을 전달받지 못했습니다. 설치를 다시 시도해 주세요.",
                    )
                    return
                }
                try {
                    confirmation.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    context.startActivity(confirmation)
                    store.markAwaitingUserAction(callbackSessionId)
                } catch (_: ActivityNotFoundException) {
                    store.markRetryRequired(
                        callbackSessionId,
                        "Android 설치 확인 화면을 열 앱을 찾지 못했습니다. 설치를 다시 시도해 주세요.",
                    )
                } catch (_: SecurityException) {
                    store.markRetryRequired(
                        callbackSessionId,
                        "Android 보안 설정 때문에 설치 확인 화면을 열지 못했습니다. 설치를 다시 시도해 주세요.",
                    )
                } catch (_: RuntimeException) {
                    store.markRetryRequired(
                        callbackSessionId,
                        "Android 설치 확인 화면을 열지 못했습니다. 설치를 다시 시도해 주세요.",
                    )
                }
            }

            PackageInstaller.STATUS_SUCCESS -> {
                store.markSucceeded(callbackSessionId)
                cachedApk(context).delete()
                temporaryApk(context).delete()
            }

            else -> {
                val detail = intent.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE)
                store.markFailed(
                    callbackSessionId,
                    detail ?: "설치가 취소되었거나 완료되지 않았습니다. (상태 $status)",
                )
                cachedApk(context).delete()
                temporaryApk(context).delete()
            }
        }
    }

    private fun cachedApk(context: Context): File = File(
        File(context.cacheDir, AppUpdateManager.UPDATE_DIRECTORY),
        AppUpdateManager.CACHED_APK_NAME,
    )

    private fun temporaryApk(context: Context): File = File(
        File(context.cacheDir, AppUpdateManager.UPDATE_DIRECTORY),
        "${AppUpdateManager.CACHED_APK_NAME}.tmp",
    )
}

internal class UpdateInstallStore(context: Context) {
    private val preferences = context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)

    fun getPending(): PendingInstallRecord? {
        val sessionId = preferences.getInt(KEY_PENDING_SESSION_ID, -1)
        val versionCode = preferences.getLong(KEY_PENDING_CODE, -1L)
        val versionName = preferences.getString(KEY_PENDING_NAME, null)
        if (sessionId < 0 || versionCode < 1L || versionName.isNullOrBlank()) return null
        val phase = runCatching {
            PendingInstallPhase.valueOf(
                preferences.getString(KEY_PENDING_PHASE, PendingInstallPhase.COMMITTING.name)
                    ?: PendingInstallPhase.COMMITTING.name,
            )
        }.getOrDefault(PendingInstallPhase.RETRY_REQUIRED)
        return PendingInstallRecord(
            sessionId = sessionId,
            versionCode = versionCode,
            versionName = versionName,
            phase = phase,
            statusMessage = preferences.getString(KEY_PENDING_STATUS, null),
        )
    }

    fun markPending(sessionId: Int, versionCode: Long, versionName: String) {
        preferences.edit(commit = true) {
            putInt(KEY_PENDING_SESSION_ID, sessionId)
            putLong(KEY_PENDING_CODE, versionCode)
            putString(KEY_PENDING_NAME, versionName)
            putString(KEY_PENDING_PHASE, PendingInstallPhase.COMMITTING.name)
            remove(KEY_PENDING_STATUS)
            remove(KEY_FAILURE)
        }
    }

    fun markCommitted(sessionId: Int) {
        val pending = getPending() ?: return
        if (pending.sessionId != sessionId || pending.phase != PendingInstallPhase.COMMITTING) return
        preferences.edit(commit = true) {
            putString(KEY_PENDING_PHASE, PendingInstallPhase.COMMITTED.name)
        }
    }

    fun markAwaitingUserAction(sessionId: Int) {
        if (getPending()?.sessionId != sessionId) return
        preferences.edit(commit = true) {
            putString(KEY_PENDING_PHASE, PendingInstallPhase.AWAITING_USER_ACTION.name)
            remove(KEY_PENDING_STATUS)
        }
    }

    fun markRetryRequired(sessionId: Int, message: String) {
        if (getPending()?.sessionId != sessionId) return
        preferences.edit(commit = true) {
            putString(KEY_PENDING_PHASE, PendingInstallPhase.RETRY_REQUIRED.name)
            putString(KEY_PENDING_STATUS, message)
        }
    }

    fun clearPending(sessionId: Int) {
        if (getPending()?.sessionId != sessionId) return
        preferences.edit(commit = true) { removePendingFields() }
    }

    fun markSucceeded(sessionId: Int) {
        val pending = getPending() ?: return
        if (pending.sessionId != sessionId) return
        preferences.edit(commit = true) {
            removePendingFields()
            remove(KEY_FAILURE)
            putLong(KEY_COMPLETED_CODE, pending.versionCode)
            putString(KEY_COMPLETED_NAME, pending.versionName)
        }
    }

    fun markFailed(sessionId: Int, message: String) {
        if (getPending()?.sessionId != sessionId) return
        preferences.edit(commit = true) {
            removePendingFields()
            putString(KEY_FAILURE, message)
        }
    }

    fun consumeCompletedIfInstalled(installedVersionCode: Long): String? {
        val completedCode = preferences.getLong(KEY_COMPLETED_CODE, -1L)
        val pending = getPending()
        val pendingCode = pending?.versionCode ?: -1L
        val targetCode = when {
            completedCode > 0L && installedVersionCode >= completedCode -> completedCode
            pendingCode > 0L && installedVersionCode >= pendingCode -> pendingCode
            else -> return null
        }
        val targetName = if (targetCode == completedCode) {
            preferences.getString(KEY_COMPLETED_NAME, null)
        } else {
            pending?.versionName
        }
        preferences.edit {
            remove(KEY_COMPLETED_CODE)
            remove(KEY_COMPLETED_NAME)
            removePendingFields()
        }
        return targetName ?: targetCode.toString()
    }

    fun consumeFailure(): String? {
        val message = preferences.getString(KEY_FAILURE, null) ?: return null
        preferences.edit { remove(KEY_FAILURE) }
        return message
    }

    private fun android.content.SharedPreferences.Editor.removePendingFields() {
        remove(KEY_PENDING_SESSION_ID)
        remove(KEY_PENDING_CODE)
        remove(KEY_PENDING_NAME)
        remove(KEY_PENDING_PHASE)
        remove(KEY_PENDING_STATUS)
    }

    companion object {
        private const val PREFERENCES = "app_update_install"
        private const val KEY_PENDING_SESSION_ID = "pending_session_id"
        private const val KEY_PENDING_CODE = "pending_version_code"
        private const val KEY_PENDING_NAME = "pending_version_name"
        private const val KEY_PENDING_PHASE = "pending_phase"
        private const val KEY_PENDING_STATUS = "pending_status"
        private const val KEY_COMPLETED_CODE = "completed_version_code"
        private const val KEY_COMPLETED_NAME = "completed_version_name"
        private const val KEY_FAILURE = "install_failure"
    }
}

internal data class PendingInstallRecord(
    val sessionId: Int,
    val versionCode: Long,
    val versionName: String,
    val phase: PendingInstallPhase,
    val statusMessage: String?,
)

internal enum class PendingInstallPhase {
    COMMITTING,
    COMMITTED,
    AWAITING_USER_ACTION,
    RETRY_REQUIRED,
}
