package com.findone.app.update

data class ReleaseManifestMetadata(
    val schemaVersion: Int,
    val applicationId: String,
    val versionCode: Long,
    val versionName: String,
    val releaseApkSha256: String?,
)

data class ReleaseDescriptor(
    val folderName: String,
    val apkName: String,
    val manifest: ReleaseManifestMetadata,
)

/** A dependency-free parser for the flat release manifest written by the release script. */
object ReleaseManifestParser {
    fun parseOrNull(json: String): ReleaseManifestMetadata? = runCatching {
        val values = FlatJsonObjectParser(json).parse()
        val schemaVersion = when (val schema = values["schemaVersion"]) {
            null -> 1 // Releases made before schemaVersion was added are schema 1.
            is JsonScalar.NumberValue -> schema.value.toIntOrNull()
            else -> null
        } ?: return null
        if (schemaVersion !in 1..2) return null

        val applicationId = (values["applicationId"] as? JsonScalar.StringValue)?.value
            ?.takeIf { it.isNotBlank() && it.length <= 200 }
            ?: return null
        val versionCode = (values["versionCode"] as? JsonScalar.NumberValue)?.value
            ?.takeIf { it.matches(Regex("[0-9]+")) }
            ?.toLongOrNull()
            ?.takeIf { it in 1L..2_100_000_000L }
            ?: return null
        val versionName = (values["versionName"] as? JsonScalar.StringValue)?.value
            ?.takeIf { it.isNotBlank() && it.length <= 100 }
            ?: return null
        val sha256 = when (val hash = values["releaseApkSha256"]) {
            null, JsonScalar.NullValue -> null
            is JsonScalar.StringValue -> hash.value.lowercase()
                .takeIf { it.matches(Regex("[0-9a-f]{64}")) }
                ?: return null
            else -> return null
        }

        ReleaseManifestMetadata(
            schemaVersion = schemaVersion,
            applicationId = applicationId,
            versionCode = versionCode,
            versionName = versionName,
            releaseApkSha256 = sha256,
        )
    }.getOrNull()
}

object ReleaseSelectionPolicy {
    fun isReleaseFolderName(name: String): Boolean =
        name.length in 24..160 && RELEASE_FOLDER.matches(name)

    fun isReleaseApkName(name: String): Boolean =
        name.length in 13..140 && RELEASE_APK.matches(name)

    fun matchesManifestVersion(
        manifest: ReleaseManifestMetadata,
        apkVersionCode: Long,
        apkVersionName: String,
    ): Boolean = manifest.versionCode == apkVersionCode && manifest.versionName == apkVersionName

    fun selectHighest(
        candidates: List<ReleaseDescriptor>,
        installedApplicationId: String,
        installedVersionCode: Long,
    ): ReleaseDescriptor? = candidates
        .asSequence()
        .filter { candidate ->
            candidate.manifest.applicationId == installedApplicationId &&
                candidate.manifest.versionCode > installedVersionCode
        }
        .maxWithOrNull(
            compareBy<ReleaseDescriptor> { it.manifest.versionCode }
                .thenBy { it.folderName }
                .thenBy { it.apkName },
        )

    private val RELEASE_FOLDER = Regex(
        "^findone-[0-9A-Za-z][0-9A-Za-z.+_-]*-[0-9]{8}-[0-9]{6}(?:[0-9]{3})?(?:-[0-9a-f]{7,40})?$",
    )
    private val RELEASE_APK = Regex("^FinDone-[0-9A-Za-z][0-9A-Za-z._+-]*\\.apk$")
}

private sealed interface JsonScalar {
    data class StringValue(val value: String) : JsonScalar
    data class NumberValue(val value: String) : JsonScalar
    data class BooleanValue(val value: Boolean) : JsonScalar
    data object NullValue : JsonScalar
}

/**
 * Tiny strict JSON reader for a single flat object. Nested containers are intentionally rejected:
 * release discovery only needs scalar metadata, and bounded parsing keeps untrusted documents cheap.
 */
private class FlatJsonObjectParser(private val source: String) {
    private var index = 0

    fun parse(): Map<String, JsonScalar> {
        skipWhitespace()
        expect('{')
        skipWhitespace()
        val result = linkedMapOf<String, JsonScalar>()
        if (consume('}')) {
            requireEnd()
            return result
        }

        while (true) {
            val key = parseString()
            if (result.containsKey(key)) error("Duplicate JSON member")
            skipWhitespace()
            expect(':')
            skipWhitespace()
            result[key] = parseScalar()
            skipWhitespace()
            when {
                consume(',') -> {
                    skipWhitespace()
                    if (peek() == '}') error("Trailing comma")
                }
                consume('}') -> break
                else -> error("Expected comma or object end")
            }
        }
        requireEnd()
        return result
    }

    private fun parseScalar(): JsonScalar = when (peek()) {
        '"' -> JsonScalar.StringValue(parseString())
        't' -> { expectLiteral("true"); JsonScalar.BooleanValue(true) }
        'f' -> { expectLiteral("false"); JsonScalar.BooleanValue(false) }
        'n' -> { expectLiteral("null"); JsonScalar.NullValue }
        '-', in '0'..'9' -> JsonScalar.NumberValue(parseNumber())
        else -> error("Unsupported JSON value")
    }

    private fun parseString(): String {
        expect('"')
        val value = StringBuilder()
        while (index < source.length) {
            when (val character = source[index++]) {
                '"' -> return value.toString()
                '\\' -> {
                    if (index >= source.length) error("Incomplete escape")
                    value.append(
                        when (val escaped = source[index++]) {
                            '"', '\\', '/' -> escaped
                            'b' -> '\b'
                            'f' -> '\u000c'
                            'n' -> '\n'
                            'r' -> '\r'
                            't' -> '\t'
                            'u' -> parseUnicodeEscape()
                            else -> error("Invalid escape")
                        },
                    )
                }
                in '\u0000'..'\u001f' -> error("Control character in string")
                else -> value.append(character)
            }
        }
        error("Unterminated string")
    }

    private fun parseUnicodeEscape(): Char {
        if (index + 4 > source.length) error("Incomplete unicode escape")
        val value = source.substring(index, index + 4).toIntOrNull(16)
            ?: error("Invalid unicode escape")
        index += 4
        return value.toChar()
    }

    private fun parseNumber(): String {
        val start = index
        if (peek() == '-') index++
        if (peek() == '0') {
            index++
        } else {
            require(peek() in '1'..'9')
            while (peek() in '0'..'9') index++
        }
        if (peek() == '.') {
            index++
            require(peek() in '0'..'9')
            while (peek() in '0'..'9') index++
        }
        if (peek() == 'e' || peek() == 'E') {
            index++
            if (peek() == '+' || peek() == '-') index++
            require(peek() in '0'..'9')
            while (peek() in '0'..'9') index++
        }
        return source.substring(start, index)
    }

    private fun expectLiteral(value: String) {
        if (!source.startsWith(value, index)) error("Invalid literal")
        index += value.length
    }

    private fun expect(character: Char) {
        if (!consume(character)) error("Expected $character")
    }

    private fun consume(character: Char): Boolean {
        if (peek() != character) return false
        index++
        return true
    }

    private fun peek(): Char? = source.getOrNull(index)

    private fun skipWhitespace() {
        while (peek() == ' ' || peek() == '\n' || peek() == '\r' || peek() == '\t') index++
    }

    private fun requireEnd() {
        skipWhitespace()
        if (index != source.length) error("Unexpected trailing data")
    }
}
