package com.findone.app.data

import android.content.Context
import androidx.sqlite.SQLiteConnection
import androidx.sqlite.SQLiteStatement
import androidx.sqlite.driver.bundled.BundledSQLiteDriver
import androidx.sqlite.driver.bundled.SQLITE_OPEN_FULLMUTEX
import androidx.sqlite.driver.bundled.SQLITE_OPEN_READONLY
import com.findone.app.model.ContentElement
import com.findone.app.model.ContentManifest
import com.findone.app.model.Domain
import org.json.JSONObject
import java.io.Closeable
import java.io.File
import java.io.FileOutputStream
import java.nio.file.Files
import java.nio.file.StandardCopyOption
import java.security.MessageDigest
import java.util.Locale

class ContentIntegrityException(message: String, cause: Throwable? = null) :
    IllegalStateException(message, cause)

/**
 * Read-only access to the signed content asset.
 *
 * The asset uses FTS5, which is not guaranteed by Android's framework SQLite. A bundled SQLite
 * driver is therefore deliberately used so API 26+ devices all execute the same FTS5/BM25 code.
 */
class ContentRepository(context: Context) : Closeable {
    val manifest: ContentManifest

    private val database: SQLiteConnection
    private val queryLock = Any()

    init {
        val appContext = context.applicationContext
        manifest = loadManifest(appContext)
        validateManifestInvariants(manifest)
        val databaseFile = prepareDatabase(appContext, manifest)
        database = openReadOnly(databaseFile)
    }

    fun domains(): List<Domain> = synchronized(queryLock) {
        database.query(
            """SELECT domain_id, name, description, element_count, color_token
               FROM domains ORDER BY display_order""".trimIndent()
        ) { statement ->
            buildList {
                while (statement.step()) {
                    add(
                        Domain(
                            id = statement.getText(0),
                            name = statement.getText(1),
                            description = statement.getText(2),
                            count = statement.getLong(3).toInt(),
                            colorToken = statement.getText(4),
                        )
                    )
                }
            }
        }
    }

    @JvmOverloads
    fun elements(domainId: String? = null, query: String = ""): List<ContentElement> {
        val normalizedDomain = domainId?.trim()?.uppercase(Locale.ROOT)?.takeIf(String::isNotEmpty)
        val normalizedQuery = query.trim()
        return synchronized(queryLock) {
            if (normalizedQuery.isEmpty()) listElements(normalizedDomain)
            else searchElements(normalizedDomain, normalizedQuery)
        }
    }

    fun element(id: String): ContentElement? {
        val normalizedId = id.trim().uppercase(Locale.ROOT)
        if (normalizedId.isEmpty()) return null
        return synchronized(queryLock) {
            database.query(
                "SELECT $ELEMENT_PROJECTION FROM elements e WHERE e.element_id = ? LIMIT 1",
                listOf(normalizedId),
            ) { statement -> if (statement.step()) statement.contentElement() else null }
        }
    }

    override fun close() = synchronized(queryLock) { database.close() }

    private fun listElements(domainId: String?): List<ContentElement> {
        val whereClause = if (domainId == null) "" else "WHERE e.domain_id = ?"
        val arguments = if (domainId == null) emptyList() else listOf(domainId)
        return database.query(
            """SELECT $ELEMENT_PROJECTION
               FROM elements e JOIN domains d ON d.domain_id = e.domain_id
               $whereClause ORDER BY d.display_order, e.element_number""".trimIndent(),
            arguments,
        ) { it.readElements() }
    }

    private fun searchElements(domainId: String?, query: String): List<ContentElement> {
        val ftsQuery = toFtsQuery(query)
        if (ftsQuery.isEmpty()) return searchElementsWithLike(domainId, query)
        val domainClause = if (domainId == null) "" else "AND e.domain_id = ?"
        val arguments = buildList {
            add(ftsQuery)
            if (domainId != null) add(domainId)
        }
        return database.query(
            """SELECT $ELEMENT_PROJECTION
               FROM knowledge_fts JOIN elements e ON e.element_id = knowledge_fts.element_id
               WHERE knowledge_fts MATCH ? $domainClause
               ORDER BY bm25(knowledge_fts), e.display_order""".trimIndent(),
            arguments,
        ) { it.readElements() }
    }

    private fun searchElementsWithLike(domainId: String?, query: String): List<ContentElement> {
        val domainClause = if (domainId == null) "" else "AND e.domain_id = ?"
        val arguments = buildList {
            repeat(3) { add("%$query%") }
            if (domainId != null) add(domainId)
        }
        return database.query(
            """SELECT $ELEMENT_PROJECTION FROM elements e
               WHERE (e.title LIKE ? OR e.core_relation LIKE ? OR e.scope_notes LIKE ?)
               $domainClause ORDER BY e.display_order""".trimIndent(),
            arguments,
        ) { it.readElements() }
    }

    private fun SQLiteStatement.readElements(): List<ContentElement> = buildList {
        while (step()) add(contentElement())
    }

    private fun SQLiteStatement.contentElement() = ContentElement(
        id = getText(0),
        domainId = getText(1),
        title = getText(2),
        coreRelation = getText(3),
        scope = getText(4),
        sourceLabel = getText(5),
        sourceLocator = getText(6),
        specSectionLocator = getText(7),
    )

    companion object {
        private const val MANIFEST_ASSET = "content-manifest.json"
        private val EXPECTED_DOMAIN_COUNTS = mapOf(
            "ACC" to 12, "CF" to 12, "INV" to 9, "FI" to 10,
            "DER" to 10, "EQV" to 64, "IBT" to 18,
        )
        private val VERIFIED_TABLES = setOf(
            "metadata", "domains", "elements", "concept_cards", "formula_cards",
            "sources", "element_sources", "knowledge_fts",
        )
        private const val ELEMENT_PROJECTION = """
            e.element_id, e.domain_id, e.title, e.core_relation, e.scope_notes,
            e.source_label, e.source_locator, e.spec_section_locator
        """

        private fun loadManifest(context: Context): ContentManifest {
            val json = context.assets.open(MANIFEST_ASSET).bufferedReader(Charsets.UTF_8).use {
                JSONObject(it.readText())
            }
            return ContentManifest(
                manifestVersion = json.getInt("manifestVersion"),
                schemaVersion = json.getInt("schemaVersion"),
                contentDbVersion = json.getInt("contentDbVersion"),
                databaseAsset = json.getString("databaseAsset"),
                sha256 = json.getString("sha256").lowercase(Locale.ROOT),
                byteSize = json.getLong("byteSize"),
                sourceSpec = json.getString("sourceSpec"),
                sourceSha256 = json.getString("sourceSha256").lowercase(Locale.ROOT),
                rowCounts = json.getJSONObject("rowCounts").toIntMap(),
                domainElementCounts = json.getJSONObject("domainElementCounts").toIntMap(),
            )
        }

        private fun JSONObject.toIntMap(): Map<String, Int> = buildMap {
            val iterator = keys()
            while (iterator.hasNext()) iterator.next().let { key -> put(key, getInt(key)) }
        }

        private fun validateManifestInvariants(manifest: ContentManifest) {
            if (manifest.manifestVersion != 1 || manifest.schemaVersion != 1) {
                throw ContentIntegrityException("Unsupported content manifest/schema version")
            }
            if (!manifest.databaseAsset.matches(Regex("[A-Za-z0-9._-]+"))) {
                throw ContentIntegrityException("Unsafe database asset name")
            }
            if (!manifest.sha256.matches(Regex("[0-9a-f]{64}"))) {
                throw ContentIntegrityException("Malformed content database SHA-256")
            }
            if (manifest.rowCounts["domains"] != 7 || manifest.rowCounts["elements"] != 135) {
                throw ContentIntegrityException("Manifest domain/element invariant failed")
            }
            if (manifest.rowCounts["concept_cards"] != 135 ||
                manifest.rowCounts["formula_cards"] != 135 ||
                manifest.rowCounts["knowledge_fts"] != 135
            ) throw ContentIntegrityException("Manifest card/FTS invariant failed")
            if (manifest.domainElementCounts != EXPECTED_DOMAIN_COUNTS) {
                throw ContentIntegrityException("Manifest domain row counts are not canonical")
            }
            if (!manifest.rowCounts.keys.all { it in VERIFIED_TABLES }) {
                throw ContentIntegrityException("Manifest asks to verify an unknown table")
            }
        }

        private fun prepareDatabase(context: Context, manifest: ContentManifest): File {
            val contentDirectory = File(context.filesDir, "content")
            if (!contentDirectory.exists() && !contentDirectory.mkdirs()) {
                throw ContentIntegrityException("Could not create app-private content directory")
            }
            val target = File(contentDirectory, "v${manifest.contentDbVersion}-${manifest.sha256.take(16)}.sqlite3")
            if (target.isFile) {
                runCatching { verifyDatabase(target, manifest) }.onSuccess { return target }
            }

            val temporary = File(contentDirectory, ".${target.name}.${android.os.Process.myPid()}.${System.nanoTime()}.tmp")
            try {
                context.assets.open(manifest.databaseAsset).use { input ->
                    FileOutputStream(temporary).use { output ->
                        input.copyTo(output)
                        output.flush()
                        output.fd.sync()
                    }
                }
                verifyDatabase(temporary, manifest)
                try {
                    Files.move(temporary.toPath(), target.toPath(), StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING)
                } catch (_: java.nio.file.AtomicMoveNotSupportedException) {
                    Files.move(temporary.toPath(), target.toPath(), StandardCopyOption.REPLACE_EXISTING)
                }
                verifyDatabase(target, manifest)
                return target
            } catch (error: ContentIntegrityException) {
                throw error
            } catch (error: Exception) {
                throw ContentIntegrityException("Could not install verified content database", error)
            } finally {
                Files.deleteIfExists(temporary.toPath())
            }
        }

        private fun verifyDatabase(file: File, manifest: ContentManifest) {
            if (!file.isFile || file.length() != manifest.byteSize) throw ContentIntegrityException("Content database size mismatch")
            if (sha256(file) != manifest.sha256) throw ContentIntegrityException("Content database SHA-256 mismatch")
            openReadOnly(file).use { connection ->
                val integrity = connection.scalarText("PRAGMA integrity_check")
                if (integrity != "ok") throw ContentIntegrityException("SQLite integrity_check failed: $integrity")
                val userVersion = connection.scalarLong("PRAGMA user_version").toInt()
                if (userVersion != manifest.schemaVersion) throw ContentIntegrityException("Content schema version mismatch")
                manifest.rowCounts.forEach { (table, expected) ->
                    val actual = connection.scalarLong("SELECT COUNT(*) FROM \"$table\"").toInt()
                    if (actual != expected) throw ContentIntegrityException("$table row invariant failed: expected $expected, found $actual")
                }
                val domainCounts = connection.query(
                    "SELECT domain_id, COUNT(*) FROM elements GROUP BY domain_id"
                ) { statement ->
                    buildMap {
                        while (statement.step()) put(statement.getText(0), statement.getLong(1).toInt())
                    }
                }
                if (domainCounts != EXPECTED_DOMAIN_COUNTS) throw ContentIntegrityException("Database domain row counts are not canonical")
                val specSha = connection.scalarText("SELECT value FROM metadata WHERE key = 'source_spec_sha256'")
                if (!specSha.equals(manifest.sourceSha256, ignoreCase = true)) throw ContentIntegrityException("Database source-spec hash mismatch")
                val foreignKeyError = connection.query("PRAGMA foreign_key_check") { it.step() }
                if (foreignKeyError) throw ContentIntegrityException("SQLite foreign_key_check failed")
                // This statement proves the bundled driver actually loaded FTS5 and BM25.
                connection.scalarLong("SELECT COUNT(*) FROM knowledge_fts WHERE knowledge_fts MATCH 'ROE'")
                connection.query("SELECT bm25(knowledge_fts) FROM knowledge_fts WHERE knowledge_fts MATCH 'ROE' LIMIT 1") { it.step() }
            }
        }

        private fun openReadOnly(file: File): SQLiteConnection = BundledSQLiteDriver().open(
            file.absolutePath,
            SQLITE_OPEN_READONLY or SQLITE_OPEN_FULLMUTEX,
        )

        private fun sha256(file: File): String {
            val digest = MessageDigest.getInstance("SHA-256")
            file.inputStream().buffered().use { input ->
                val buffer = ByteArray(DEFAULT_BUFFER_SIZE)
                while (true) {
                    val read = input.read(buffer)
                    if (read < 0) break
                    if (read > 0) digest.update(buffer, 0, read)
                }
            }
            return digest.digest().joinToString("") { "%02x".format(it) }
        }

        private fun toFtsQuery(query: String): String = Regex("[\\p{L}\\p{N}]+")
            .findAll(query)
            .map { "\"${it.value.replace("\"", "\"\"")}\"*" }
            .take(8)
            .joinToString(" AND ")
    }
}

private inline fun <T> SQLiteConnection.query(
    sql: String,
    arguments: List<String> = emptyList(),
    block: (SQLiteStatement) -> T,
): T {
    val statement = prepare(sql)
    return try {
        arguments.forEachIndexed { index, value -> statement.bindText(index + 1, value) }
        block(statement)
    } finally {
        statement.close()
    }
}

private fun SQLiteConnection.scalarText(sql: String): String = query(sql) { statement ->
    if (!statement.step()) throw ContentIntegrityException("Query returned no rows: $sql")
    statement.getText(0)
}

private fun SQLiteConnection.scalarLong(sql: String): Long = query(sql) { statement ->
    if (!statement.step()) throw ContentIntegrityException("Query returned no rows: $sql")
    statement.getLong(0)
}
