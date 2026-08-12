package com.findone.app.data

import android.content.Context
import com.findone.app.BuildConfig
import com.findone.app.model.GlossaryManifest
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.io.File
import java.io.FileOutputStream
import java.net.HttpURLConnection
import java.net.URI
import java.net.URL
import java.security.MessageDigest
import java.util.Locale

sealed interface GlossaryUpdateResult {
    data object Disabled : GlossaryUpdateResult
    data object Current : GlossaryUpdateResult
    data class Installed(val manifest: GlossaryManifest) : GlossaryUpdateResult
    data class Failed(val message: String) : GlossaryUpdateResult
}

/** Downloads only a signed, compiled glossary pack; it never calls an LLM endpoint. */
class GlossaryUpdateManager(private val context: Context) {
    fun updateIfAvailable(currentVersion: Int): GlossaryUpdateResult {
        val endpoint = BuildConfig.GLOSSARY_RELEASE_ENDPOINT.trim()
        if (endpoint.isEmpty()) return GlossaryUpdateResult.Disabled
        return try {
            requireHttps(endpoint, "glossary release endpoint")
            val release = JSONObject(fetchBytes(endpoint, MAX_METADATA_BYTES).toString(Charsets.UTF_8))
            if (release.getInt("protocolVersion") != 1 || release.getString("channel") != "stable") {
                throw GlossaryIntegrityException("Unsupported glossary release response")
            }
            if (release.getBoolean("llmRuntimeUsed")) {
                throw GlossaryIntegrityException("Runtime-authored glossary releases are forbidden")
            }
            val remoteVersion = release.getInt("glossaryDbVersion")
            if (remoteVersion <= currentVersion) return GlossaryUpdateResult.Current
            if (release.getInt("schemaVersion") != 1) {
                throw GlossaryIntegrityException("Glossary update requires an unsupported schema")
            }
            if (release.getInt("minimumAppVersion") > BuildConfig.VERSION_CODE) {
                throw GlossaryIntegrityException("A newer FinDone app is required for this glossary")
            }

            val manifestUrl = release.getString("manifestUrl")
            val databaseUrl = release.getString("databaseUrl")
            requireHttps(manifestUrl, "glossary manifest URL")
            requireHttps(databaseUrl, "glossary database URL")
            val expectedManifestSha = release.requireSha256("manifestSha256")
            val expectedDatabaseSha = release.requireSha256("databaseSha256")
            val expectedDatabaseBytes = release.getLong("databaseByteSize")
            if (expectedDatabaseBytes !in 1..MAX_DATABASE_BYTES) {
                throw GlossaryIntegrityException("Glossary database size is outside the safety limit")
            }

            val manifestBytes = fetchBytes(manifestUrl, MAX_MANIFEST_BYTES)
            if (sha256(manifestBytes) != expectedManifestSha) {
                throw GlossaryIntegrityException("Downloaded glossary manifest hash mismatch")
            }
            val manifestJson = JSONObject(manifestBytes.toString(Charsets.UTF_8))
            if (manifestJson.getInt("glossaryDbVersion") != remoteVersion ||
                manifestJson.getInt("schemaVersion") != release.getInt("schemaVersion") ||
                manifestJson.getBoolean("llmRuntimeUsed") ||
                manifestJson.getString("sha256").lowercase(Locale.ROOT) != expectedDatabaseSha ||
                manifestJson.getLong("byteSize") != expectedDatabaseBytes
            ) throw GlossaryIntegrityException("Glossary manifest does not match the stable release")

            val directory = File(context.filesDir, "glossary")
            if (!directory.exists() && !directory.mkdirs()) {
                throw GlossaryIntegrityException("Could not create app-private glossary directory")
            }
            val temporary = File(
                directory,
                ".download-${android.os.Process.myPid()}-${System.nanoTime()}.sqlite3.tmp",
            )
            try {
                downloadDatabase(databaseUrl, temporary, expectedDatabaseBytes, expectedDatabaseSha)
                GlossaryUpdateResult.Installed(
                    GlossaryRepository.installDownloadedRelease(context, manifestBytes, temporary)
                )
            } finally {
                temporary.delete()
            }
        } catch (error: Exception) {
            GlossaryUpdateResult.Failed(error.message ?: "Glossary update failed")
        }
    }

    private fun fetchBytes(url: String, maximumBytes: Int): ByteArray {
        val connection = open(url)
        return try {
            val declaredLength = connection.contentLengthLong
            if (declaredLength > maximumBytes) {
                throw GlossaryIntegrityException("Glossary response exceeds the safety limit")
            }
            connection.inputStream.use { input ->
                val output = ByteArrayOutputStream(
                    if (declaredLength in 1..maximumBytes.toLong()) declaredLength.toInt() else 8192
                )
                val buffer = ByteArray(DEFAULT_BUFFER_SIZE)
                var total = 0
                while (true) {
                    val read = input.read(buffer)
                    if (read < 0) break
                    total += read
                    if (total > maximumBytes) {
                        throw GlossaryIntegrityException("Glossary response exceeds the safety limit")
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
                throw GlossaryIntegrityException("Glossary database response size mismatch")
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
                            throw GlossaryIntegrityException("Glossary database response exceeds the expected size")
                        }
                        digest.update(buffer, 0, read)
                        output.write(buffer, 0, read)
                    }
                    output.flush()
                    output.fd.sync()
                }
            }
            if (total != expectedBytes) {
                throw GlossaryIntegrityException("Glossary database response is incomplete")
            }
            val actualSha = digest.digest().joinToString("") { "%02x".format(it) }
            if (actualSha != expectedSha256) {
                throw GlossaryIntegrityException("Downloaded glossary database hash mismatch")
            }
        } finally {
            connection.disconnect()
        }
    }

    private fun open(initialUrl: String): HttpURLConnection {
        var current = initialUrl
        repeat(MAX_REDIRECTS + 1) { redirectCount ->
            requireHttps(current, "glossary download URL")
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
                    ?: throw GlossaryIntegrityException("Glossary redirect has no destination")
                current = URI(current).resolve(location).toString()
                connection.disconnect()
            } else {
                connection.disconnect()
                throw GlossaryIntegrityException("Glossary server returned HTTP $status")
            }
        }
        throw GlossaryIntegrityException("Too many glossary download redirects")
    }

    private fun requireHttps(value: String, label: String) {
        val uri = runCatching { URI(value) }.getOrNull()
        if (uri?.scheme != "https" || uri.host.isNullOrBlank() || uri.userInfo != null) {
            throw GlossaryIntegrityException("$label must be an HTTPS URL")
        }
    }

    private fun JSONObject.requireSha256(key: String): String {
        val value = getString(key).lowercase(Locale.ROOT)
        if (!value.matches(Regex("[0-9a-f]{64}"))) {
            throw GlossaryIntegrityException("$key is not a SHA-256 value")
        }
        return value
    }

    private fun sha256(value: ByteArray): String = MessageDigest.getInstance("SHA-256")
        .digest(value)
        .joinToString("") { "%02x".format(it) }

    companion object {
        private const val CONNECT_TIMEOUT_MS = 8_000
        private const val READ_TIMEOUT_MS = 30_000
        private const val MAX_REDIRECTS = 4
        private const val MAX_METADATA_BYTES = 256 * 1024
        private const val MAX_MANIFEST_BYTES = 1024 * 1024
        private const val MAX_DATABASE_BYTES = 128L * 1024 * 1024
    }
}
