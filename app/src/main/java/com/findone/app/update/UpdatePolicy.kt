package com.findone.app.update

/**
 * Android APIs와 무관한 업데이트 허용 정책입니다.
 *
 * APK 파싱은 [AppUpdateManager]가 담당하고, 보안 판단은 이 순수 함수에 모아
 * 로컬 단위 테스트로 모든 거부 조건을 검증할 수 있게 합니다.
 */
data class AppIdentity(
    val packageName: String,
    val versionCode: Long,
    val signerSha256: Set<String>,
)

sealed interface UpdateDecision {
    data object Allowed : UpdateDecision

    data class Rejected(val reason: UpdateRejection) : UpdateDecision
}

enum class UpdateRejection {
    PACKAGE_MISMATCH,
    VERSION_NOT_NEWER,
    SIGNING_CERTIFICATE_MISSING,
    SIGNING_CERTIFICATE_MISMATCH,
}

object UpdatePolicy {
    fun evaluate(installed: AppIdentity, candidate: AppIdentity): UpdateDecision {
        if (candidate.packageName != installed.packageName) {
            return UpdateDecision.Rejected(UpdateRejection.PACKAGE_MISMATCH)
        }
        if (candidate.versionCode <= installed.versionCode) {
            return UpdateDecision.Rejected(UpdateRejection.VERSION_NOT_NEWER)
        }
        if (installed.signerSha256.isEmpty() || candidate.signerSha256.isEmpty()) {
            return UpdateDecision.Rejected(UpdateRejection.SIGNING_CERTIFICATE_MISSING)
        }
        // FinDone uses one fixed personal release key. Deliberate exact-set matching also
        // rejects signing-key rotation until a separately reviewed migration policy exists.
        if (candidate.signerSha256 != installed.signerSha256) {
            return UpdateDecision.Rejected(UpdateRejection.SIGNING_CERTIFICATE_MISMATCH)
        }
        return UpdateDecision.Allowed
    }
}

object InstallCallbackPolicy {
    fun belongsToPendingSession(pendingSessionId: Int?, callbackSessionId: Int): Boolean =
        pendingSessionId != null && callbackSessionId >= 0 && pendingSessionId == callbackSessionId
}
