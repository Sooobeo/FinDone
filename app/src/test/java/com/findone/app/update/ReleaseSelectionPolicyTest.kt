package com.findone.app.update

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class ReleaseSelectionPolicyTest {
    @Test
    fun `schema 1 manifest without schemaVersion is accepted`() {
        val parsed = ReleaseManifestParser.parseOrNull(
            """{
                "applicationId":"com.findone.app",
                "versionCode":2,
                "versionName":"0.3.0",
                "releaseApkSha256":"${"a".repeat(64)}",
                "internetPermission":false
            }""".trimIndent(),
        )

        assertEquals(1, parsed?.schemaVersion)
        assertEquals(2L, parsed?.versionCode)
        assertEquals("a".repeat(64), parsed?.releaseApkSha256)
    }

    @Test
    fun `schema 2 manifest is accepted`() {
        val parsed = ReleaseManifestParser.parseOrNull(
            """{
                "schemaVersion":2,
                "applicationId":"com.findone.app",
                "versionCode":12,
                "versionName":"1.2.0"
            }""".trimIndent(),
        )

        assertEquals(2, parsed?.schemaVersion)
        assertEquals("1.2.0", parsed?.versionName)
    }

    @Test
    fun `unsupported schema and malformed hash are rejected`() {
        assertNull(ReleaseManifestParser.parseOrNull(manifest(schema = 3, versionCode = 4)))
        assertNull(
            ReleaseManifestParser.parseOrNull(
                manifest(schema = 2, versionCode = 4, extra = ",\"releaseApkSha256\":\"bad\""),
            ),
        )
    }

    @Test
    fun `duplicate security field is rejected`() {
        assertNull(
            ReleaseManifestParser.parseOrNull(
                """{"schemaVersion":2,"applicationId":"com.findone.app","applicationId":"other","versionCode":4,"versionName":"0.4.0"}""",
            ),
        )
    }

    @Test
    fun `highest strictly newer matching package is selected`() {
        val candidates = listOf(
            descriptor("findone-0.3.0", "FinDone-0.3.0.apk", 3),
            descriptor("findone-other", "Other.apk", 99, applicationId = "other.app"),
            descriptor("findone-0.5.0", "FinDone-0.5.0.apk", 5),
            descriptor("findone-current", "FinDone-current.apk", 2),
        )

        val selected = ReleaseSelectionPolicy.selectHighest(candidates, "com.findone.app", 2)

        assertEquals(5L, selected?.manifest?.versionCode)
        assertEquals("FinDone-0.5.0.apk", selected?.apkName)
    }

    @Test
    fun `returns null when releases are not newer`() {
        val candidates = listOf(descriptor("findone-old", "FinDone-old.apk", 1))

        assertNull(ReleaseSelectionPolicy.selectHighest(candidates, "com.findone.app", 2))
    }

    @Test
    fun `manifest and parsed APK versions must match exactly`() {
        val release = descriptor("findone-0.5.0-20260808-123456789", "FinDone-0.5.0.apk", 5).manifest

        assertTrue(ReleaseSelectionPolicy.matchesManifestVersion(release, 5, "v5"))
        assertEquals(false, ReleaseSelectionPolicy.matchesManifestVersion(release, 6, "v5"))
        assertEquals(false, ReleaseSelectionPolicy.matchesManifestVersion(release, 5, "0.5.0"))
    }

    @Test
    fun `only bounded findone prefix names are release folders`() {
        assertTrue(ReleaseSelectionPolicy.isReleaseFolderName("findone-0.4.0-20260808-123456789"))
        assertEquals(false, ReleaseSelectionPolicy.isReleaseFolderName("other-0.4.0"))
        assertEquals(false, ReleaseSelectionPolicy.isReleaseFolderName("findone-"))
        assertTrue(ReleaseSelectionPolicy.isReleaseApkName("FinDone-0.4.0.apk"))
        assertEquals(false, ReleaseSelectionPolicy.isReleaseApkName("other.apk"))
        assertEquals(false, ReleaseSelectionPolicy.isReleaseApkName("findone-0.4.0.apk"))
    }

    private fun manifest(schema: Int, versionCode: Long, extra: String = ""): String =
        """{"schemaVersion":$schema,"applicationId":"com.findone.app","versionCode":$versionCode,"versionName":"0.4.0"$extra}"""

    private fun descriptor(
        folder: String,
        apk: String,
        versionCode: Long,
        applicationId: String = "com.findone.app",
    ) = ReleaseDescriptor(
        folderName = folder,
        apkName = apk,
        manifest = ReleaseManifestMetadata(
            schemaVersion = 2,
            applicationId = applicationId,
            versionCode = versionCode,
            versionName = "v$versionCode",
            releaseApkSha256 = null,
        ),
    )
}
