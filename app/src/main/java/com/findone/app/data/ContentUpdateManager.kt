package com.findone.app.data

import android.content.Context
import com.findone.app.BuildConfig
import com.findone.app.model.ContentManifest
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.io.File
import java.io.FileOutputStream
import java.net.HttpURLConnection
import java.net.URI
import java.net.URL
import java.security.MessageDigest
import java.util.Locale

sealed interface ContentUpdateResult {
    data object Disabled : ContentUpdateResult
    data object Current : ContentUpdateResult
    data class Installed(val manifest: ContentManifest) : ContentUpdateResult
    data class Failed(val message: String) : ContentUpdateResult
}

class ContentUpdateManager(private val context: Context) {
    fun updateIfAvailable(currentVersion: Int): ContentUpdateResult {
        val endpoint = BuildConfig.CONTENT_RELEASE_ENDPOINT.trim()
        if (endpoint.isEmpty()) return ContentUpdateResult.Disabled
        return try {
            requireHttps(endpoint, "content release endpoint")
            val release = JSONObject(fetchBytes(endpoint, MAX_METADATA_BYTES).toString(Charsets.UTF_8))
            if (release.getInt("protocolVersion") != 1 || release.getString("channel") != "stable") {
                throw ContentIntegrityException("Unsupported content release response")
            }
            val remoteVersion = release.getInt("contentDbVersion")
            if (remoteVersion <= currentVersion) return ContentUpdateResult.Current
            if (release.getInt("schemaVersion") != 1) {
                throw ContentIntegrityException("Content update requires an unsupported schema")
            }
            if (release.getInt("minimumAppVersion") > BuildConfig.VERSION_CODE) {
                throw ContentIntegrityException("A newer FinDone app is required for this content")
            }

            val manifestUrl = release.getString("manifestUrl")
            val databaseUrl = release.getString("databaseUrl")
            requireHttps(manifestUrl, "manifest download URL")
            requireHttps(databaseUrl, "database download URL")
            val expectedManifestSha = release.requireSha256("manifestSha256")
            val expectedDatabaseSha = release.requireSha256("databaseSha256")
            val expectedDatabaseBytes = release.getLong("databaseByteSize")
            if (expectedDatabaseBytes !in 1..MAX_DATABASE_BYTES) {
                throw ContentIntegrityException("Content database size is outside the safety limit")
            }

            val manifestBytes = fetchBytes(manifestUrl, MAX_MANIFEST_BYTES)
            if (sha256(manifestBytes) != expectedManifestSha) {
                throw ContentIntegrityException("Downloaded content manifest hash mismatch")
            }
            val manifestJson = JSONObject(manifestBytes.toString(Charsets.UTF_8))
            if (
                manifestJson.getInt("contentDbVersion") != remoteVersion ||
                manifestJson.getInt("schemaVersion") != release.getInt("schemaVersion") ||
                manifestJson.getString("sha256").lowercase(Locale.ROOT) != expectedDatabaseSha ||
                manifestJson.getLong("byteSize") != expectedDatabaseBytes
            ) {
                throw ContentIntegrityException("Content manifest does not match the stable release")
            }

            val contentDirectory = File(context.filesDir, "content")
            if (!contentDirectory.exists() && !contentDirectory.mkdirs()) {
                throw ContentIntegrityException("Could not create app-private content directory")
            }
            val temporary = File(
                contentDirectory,
                ".download-${android.os.Process.myPid()}-${System.nanoTime()}.sqlite3.tmp",
            )
            try {
                downloadDatabase(
                    url = databaseUrl,
                    target = temporary,
                    expectedBytes = expectedDatabaseBytes,
                    expectedSha256 = expectedDatabaseSha,
                )
                ContentUpdateResult.Installed(
                    ContentRepository.installDownloadedRelease(context, manifestBytes, temporary),
                )
            } finally {
                temporary.delete()
            }
        } catch (error: Exception) {
            ContentUpdateResult.Failed(error.message ?: "Content update failed")
        }
    }

    private fun fetchBytes(url: String, maximumBytes: Int): ByteArray {
        val connection = open(url)
        return try {
            val declaredLength = connection.contentLengthLong
            if (declaredLength > maximumBytes) {
                throw ContentIntegrityException("Content response exceeds the safety limit")
            }
            connection.inputStream.use { input ->
                val output = ByteArrayOutputStream(
                    if (declaredLength in 1..maximumBytes.toLong()) declaredLength.toInt() else 8192,
                )
                val buffer = ByteArray(DEFAULT_BUFFER_SIZE)
                var total = 0
                while (true) {
                    val read = input.read(buffer)
                    if (read < 0) break
                    total += read
                    if (total > maximumBytes) {
                        throw ContentIntegrityException("Content response exceeds the safety limit")
                    }
                    output.write(buffer, 0, read)
                }
                output.toByteArray()
            }
        } finally {
            connection.disconnect()
        }
    }

    private fun downloadDatabase(
        url: String,
        target: File,
        expectedBytes: Long,
        expectedSha256: String,
    ) {
        val connection = open(url)
        try {
            val declaredLength = connection.contentLengthLong
            if (declaredLength > 0 && declaredLength != expectedBytes) {
                throw ContentIntegrityException("Content database response size mismatch")
            }
            val digest = MessageDigest.getInstance("SHA-256")
            var total = 0L
            connection.inputStream.use { input ->
                FileOutputStream(target).use { output ->
                    val buffer = ByteArray(DEFAULT_BUFFER_SIZE)
                    while (true) {
                        val read = input.read(buffer)
                        if (read < 0) break
                        total += read
                        if (total > expectedBytes || total > MAX_DATABASE_BYTES) {
                            throw ContentIntegrityException("Content database response exceeds the expected size")
                        }
                        digest.update(buffer, 0, read)
                        output.write(buffer, 0, read)
                    }
                    output.flush()
                    output.fd.sync()
                }
            }
            if (total != expectedBytes) throw ContentIntegrityException("Content database response is incomplete")
            val actualSha = digest.digest().joinToString("") { "%02x".format(it) }
            if (actualSha != expectedSha256) {
                throw ContentIntegrityException("Downloaded content database hash mismatch")
            }
        } finally {
            connection.disconnect()
        }
    }

    private fun open(initialUrl: String): HttpURLConnection {
        var current = initialUrl
        repeat(MAX_REDIRECTS + 1) { redirectCount ->
            requireHttps(current, "content download URL")
            val connection = (URL(current).openConnection() as HttpURLConnection).apply {
                instanceFollowRedirects = false
                connectTimeout = CONNECT_TIMEOUT_MS
                readTimeout = READ_TIMEOUT_MS
                requestMethod = "GET"
                setRequestProperty("Accept", "application/json, application/octet-stream")
            }
            val status = connection.responseCode
            if (status in 200..299) return connection
            if (status in setOf(301, 302, 303, 307, 308) && redirectCount < MAX_REDIRECTS) {
                val location = connection.getHeaderField("Location")
                    ?: throw ContentIntegrityException("Content redirect has no destination")
                current = URI(current).resolve(location).toString()
                connection.disconnect()
            } else {
                connection.disconnect()
                throw ContentIntegrityException("Content server returned HTTP $status")
            }
        }
        throw ContentIntegrityException("Too many content download redirects")
    }

    private fun requireHttps(value: String, label: String) {
        val uri = runCatching { URI(value) }.getOrNull()
        if (uri?.scheme != "https" || uri.host.isNullOrBlank() || uri.userInfo != null) {
            throw ContentIntegrityException("$label must be an HTTPS URL")
        }
    }

    private fun JSONObject.requireSha256(key: String): String {
        val value = getString(key).lowercase(Locale.ROOT)
        if (!value.matches(Regex("[0-9a-f]{64}"))) {
            throw ContentIntegrityException("$key is not a SHA-256 value")
        }
        return value
    }

    private fun sha256(value: ByteArray): String = MessageDigest.getInstance("SHA-256")
        .digest(value)
        .joinToString("") { "%02x".format(it) }

    companion object {
        private const val CONNECT_TIMEOUT_MS = 8_000
        private const val READ_TIMEOUT_MS = 20_000
        private const val MAX_REDIRECTS = 4
        private const val MAX_METADATA_BYTES = 256 * 1024
        private const val MAX_MANIFEST_BYTES = 1024 * 1024
        private const val MAX_DATABASE_BYTES = 64L * 1024 * 1024
    }
}
