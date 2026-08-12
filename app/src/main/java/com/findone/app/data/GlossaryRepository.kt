package com.findone.app.data

import android.content.Context
import androidx.sqlite.SQLiteConnection
import androidx.sqlite.SQLiteStatement
import androidx.sqlite.driver.bundled.BundledSQLiteDriver
import androidx.sqlite.driver.bundled.SQLITE_OPEN_FULLMUTEX
import androidx.sqlite.driver.bundled.SQLITE_OPEN_READONLY
import com.findone.app.model.GlossaryCategory
import com.findone.app.model.GlossaryManifest
import com.findone.app.model.GlossaryRelatedTerm
import com.findone.app.model.GlossaryTerm
import com.findone.app.model.GlossaryTermSummary
import org.json.JSONArray
import org.json.JSONObject
import java.io.Closeable
import java.io.File
import java.io.FileOutputStream
import java.nio.file.Files
import java.nio.file.StandardCopyOption
import java.security.MessageDigest
import java.util.Locale

class GlossaryIntegrityException(message: String, cause: Throwable? = null) :
    IllegalStateException(message, cause)

/** Read-only access to the independently downloadable, fully offline glossary pack. */
class GlossaryRepository(context: Context) : Closeable {
    val manifest: GlossaryManifest

    private val database: SQLiteConnection
    private val queryLock = Any()

    init {
        val appContext = context.applicationContext
        manifest = loadManifest(appContext)
        validateManifestInvariants(manifest)
        val databasePath = prepareDatabase(appContext, manifest)
        database = openReadOnly(databasePath)
        pruneObsoleteDatabases(glossaryDirectory(appContext), databasePath)
    }

    fun categories(): List<GlossaryCategory> = synchronized(queryLock) {
        database.query(
            """SELECT category_id, name, display_order, term_count
               FROM categories ORDER BY display_order""".trimIndent()
        ) { statement ->
            buildList {
                while (statement.step()) {
                    add(
                        GlossaryCategory(
                            id = statement.getText(0),
                            name = statement.getText(1),
                            displayOrder = statement.getLong(2).toInt(),
                            termCount = statement.getLong(3).toInt(),
                        )
                    )
                }
            }
        }
    }

    @JvmOverloads
    fun terms(categoryId: String? = null, query: String = ""): List<GlossaryTermSummary> {
        val normalizedCategory = categoryId?.trim()?.takeIf(String::isNotEmpty)
        val normalizedQuery = query.trim()
        return synchronized(queryLock) {
            if (normalizedQuery.isEmpty()) listTerms(normalizedCategory)
            else searchTerms(normalizedCategory, normalizedQuery)
        }
    }

    fun term(termId: String): GlossaryTerm? {
        val normalizedId = termId.trim().uppercase(Locale.ROOT)
        if (!TERM_ID_PATTERN.matches(normalizedId)) return null
        return synchronized(queryLock) {
            val base = database.query(
                """SELECT t.term_id, t.category_id, c.name, t.canonical_name_en,
                          t.canonical_name_ko, t.concept_type, t.one_line_definition_ko,
                          t.core_definition_ko, t.practical_context_ko,
                          t.why_it_matters_ko, t.example_ko, t.formula_latex,
                          t.formula_notes_ko, t.jurisdictions_json, t.as_of_date,
                          t.review_status, t.review_flags_json
                   FROM terms t JOIN categories c ON c.category_id = t.category_id
                   WHERE t.term_id = ? LIMIT 1""".trimIndent(),
                listOf(normalizedId),
            ) { statement ->
                if (!statement.step()) null else TermBase(
                    id = statement.getText(0),
                    categoryId = statement.getText(1),
                    categoryName = statement.getText(2),
                    canonicalNameEn = statement.getText(3),
                    canonicalNameKo = statement.getText(4),
                    conceptType = statement.getText(5),
                    oneLineDefinitionKo = statement.getText(6),
                    coreDefinitionKo = statement.getText(7),
                    practicalContextKo = statement.getText(8),
                    whyItMattersKo = statement.getText(9),
                    exampleKo = statement.getText(10),
                    formulaLatex = statement.getText(11),
                    formulaNotesKo = statement.getText(12),
                    jurisdictions = statement.getText(13).jsonStrings(),
                    asOfDate = statement.getText(14),
                    reviewStatus = statement.getText(15),
                    reviewFlags = statement.getText(16).jsonStrings(),
                )
            } ?: return@synchronized null
            val aliases = database.textColumn(
                "SELECT label FROM aliases WHERE term_id = ? ORDER BY display_order",
                normalizedId,
            )
            val limitations = database.textColumn(
                "SELECT body_ko FROM limitations WHERE term_id = ? ORDER BY display_order",
                normalizedId,
            )
            val related = database.query(
                """SELECT t.term_id, t.canonical_name_en, t.canonical_name_ko
                   FROM related_terms r JOIN terms t ON t.term_id = r.related_term_id
                   WHERE r.term_id = ? ORDER BY r.display_order""".trimIndent(),
                listOf(normalizedId),
            ) { statement ->
                buildList {
                    while (statement.step()) {
                        add(GlossaryRelatedTerm(statement.getText(0), statement.getText(1), statement.getText(2)))
                    }
                }
            }
            base.toTerm(aliases, limitations, related)
        }
    }

    override fun close() = synchronized(queryLock) { database.close() }

    private fun listTerms(categoryId: String?): List<GlossaryTermSummary> {
        val categoryClause = if (categoryId == null) "" else "WHERE t.category_id = ?"
        val arguments = if (categoryId == null) emptyList() else listOf(categoryId)
        return database.query(
            """SELECT $SUMMARY_PROJECTION
               FROM terms t JOIN categories c ON c.category_id = t.category_id
               $categoryClause
               ORDER BY c.display_order, t.display_order LIMIT $MAX_RESULTS""".trimIndent(),
            arguments,
        ) { it.readSummaries() }
    }

    private fun searchTerms(categoryId: String?, query: String): List<GlossaryTermSummary> {
        val ftsQuery = toFtsQuery(query)
        if (ftsQuery.isEmpty()) return searchTermsWithLike(categoryId, query)
        val categoryClause = if (categoryId == null) "" else "AND t.category_id = ?"
        val arguments = buildList {
            add(ftsQuery)
            if (categoryId != null) add(categoryId)
        }
        val found = database.query(
            """SELECT $SUMMARY_PROJECTION
               FROM glossary_fts
               JOIN terms t ON t.term_id = glossary_fts.term_id
               JOIN categories c ON c.category_id = t.category_id
               WHERE glossary_fts MATCH ? $categoryClause
               ORDER BY bm25(glossary_fts), c.display_order, t.display_order
               LIMIT $MAX_RESULTS""".trimIndent(),
            arguments,
        ) { it.readSummaries() }
        return found.ifEmpty { searchTermsWithLike(categoryId, query) }
    }

    private fun searchTermsWithLike(categoryId: String?, query: String): List<GlossaryTermSummary> {
        val escaped = buildString(query.length) {
            query.forEach { character ->
                if (character == '\\' || character == '%' || character == '_') append('\\')
                append(character)
            }
        }
        val like = "%$escaped%"
        val categoryClause = if (categoryId == null) "" else "AND t.category_id = ?"
        val arguments = buildList {
            repeat(5) { add(like) }
            if (categoryId != null) add(categoryId)
        }
        return database.query(
            """SELECT $SUMMARY_PROJECTION
               FROM terms t JOIN categories c ON c.category_id = t.category_id
               WHERE (t.canonical_name_en LIKE ? ESCAPE '\\'
                   OR t.canonical_name_ko LIKE ? ESCAPE '\\'
                   OR t.one_line_definition_ko LIKE ? ESCAPE '\\'
                   OR t.core_definition_ko LIKE ? ESCAPE '\\'
                   OR EXISTS(SELECT 1 FROM aliases a
                             WHERE a.term_id = t.term_id AND a.label LIKE ? ESCAPE '\\'))
               $categoryClause
               ORDER BY c.display_order, t.display_order LIMIT $MAX_RESULTS""".trimIndent(),
            arguments,
        ) { it.readSummaries() }
    }

    private fun SQLiteStatement.readSummaries(): List<GlossaryTermSummary> = buildList {
        while (step()) {
            add(
                GlossaryTermSummary(
                    id = getText(0),
                    categoryId = getText(1),
                    categoryName = getText(2),
                    canonicalNameEn = getText(3),
                    canonicalNameKo = getText(4),
                    aliases = getText(5).split(ALIAS_SEPARATOR).filter(String::isNotBlank),
                    oneLineDefinitionKo = getText(6),
                )
            )
        }
    }

    private data class TermBase(
        val id: String,
        val categoryId: String,
        val categoryName: String,
        val canonicalNameEn: String,
        val canonicalNameKo: String,
        val conceptType: String,
        val oneLineDefinitionKo: String,
        val coreDefinitionKo: String,
        val practicalContextKo: String,
        val whyItMattersKo: String,
        val exampleKo: String,
        val formulaLatex: String,
        val formulaNotesKo: String,
        val jurisdictions: List<String>,
        val asOfDate: String,
        val reviewStatus: String,
        val reviewFlags: List<String>,
    ) {
        fun toTerm(
            aliases: List<String>,
            limitations: List<String>,
            related: List<GlossaryRelatedTerm>,
        ) = GlossaryTerm(
            id = id,
            categoryId = categoryId,
            categoryName = categoryName,
            canonicalNameEn = canonicalNameEn,
            canonicalNameKo = canonicalNameKo,
            aliases = aliases,
            conceptType = conceptType,
            oneLineDefinitionKo = oneLineDefinitionKo,
            coreDefinitionKo = coreDefinitionKo,
            practicalContextKo = practicalContextKo,
            whyItMattersKo = whyItMattersKo,
            exampleKo = exampleKo,
            limitationsKo = limitations,
            formulaLatex = formulaLatex,
            formulaNotesKo = formulaNotesKo,
            jurisdictions = jurisdictions,
            asOfDate = asOfDate,
            reviewStatus = reviewStatus,
            reviewFlags = reviewFlags,
            relatedTerms = related,
        )
    }

    companion object {
        private const val MANIFEST_ASSET = "glossary-manifest.json"
        private const val ACTIVE_MANIFEST = "active-manifest.json"
        private const val DATABASE_ASSET = "glossary.sqlite3"
        private const val EXPECTED_APPLICATION_ID = 1179071315
        private const val MAX_RESULTS = 2_000
        private const val ALIAS_SEPARATOR = "\u001f"
        private val TERM_ID_PATTERN = Regex("^FIN-(?:0[1-9]|1\\d|2[01])-\\d{3}$")
        private val VERIFIED_TABLES = setOf(
            "metadata", "categories", "terms", "aliases", "limitations", "sources",
            "term_sources", "related_terms", "glossary_fts",
        )
        private const val SUMMARY_PROJECTION = """
            t.term_id, t.category_id, c.name, t.canonical_name_en, t.canonical_name_ko,
            COALESCE((SELECT group_concat(ordered_alias.label, char(31))
                      FROM (SELECT label FROM aliases a
                            WHERE a.term_id = t.term_id ORDER BY display_order) ordered_alias), ''),
            t.one_line_definition_ko
        """

        private fun parseManifest(value: String): GlossaryManifest {
            val json = JSONObject(value)
            return GlossaryManifest(
                manifestVersion = json.getInt("manifestVersion"),
                schemaVersion = json.getInt("schemaVersion"),
                glossaryDbVersion = json.getInt("glossaryDbVersion"),
                llmRuntimeUsed = json.getBoolean("llmRuntimeUsed"),
                databaseAsset = json.getString("databaseAsset"),
                sha256 = json.getString("sha256").lowercase(Locale.ROOT),
                byteSize = json.getLong("byteSize"),
                inventorySha256 = json.getString("inventorySha256").lowercase(Locale.ROOT),
                catalogSha256 = json.getString("catalogSha256").lowercase(Locale.ROOT),
                rowCounts = json.getJSONObject("rowCounts").toIntMap(),
            )
        }

        private fun packagedManifest(context: Context): GlossaryManifest = context.assets
            .open(MANIFEST_ASSET)
            .bufferedReader(Charsets.UTF_8)
            .use { parseManifest(it.readText()) }

        private fun glossaryDirectory(context: Context): File = File(context.filesDir, "glossary")

        private fun databaseFile(context: Context, manifest: GlossaryManifest): File = File(
            glossaryDirectory(context),
            "v${manifest.glossaryDbVersion}-${manifest.sha256.take(16)}.sqlite3",
        )

        private fun loadManifest(context: Context): GlossaryManifest {
            val packaged = packagedManifest(context)
            validateManifestInvariants(packaged)
            val activeFile = File(glossaryDirectory(context), ACTIVE_MANIFEST)
            val active = runCatching {
                val candidate = parseManifest(activeFile.readText(Charsets.UTF_8))
                validateManifestInvariants(candidate)
                if (candidate.glossaryDbVersion < packaged.glossaryDbVersion) {
                    throw GlossaryIntegrityException("Downloaded glossary is older than the packaged baseline")
                }
                verifyDatabase(databaseFile(context, candidate), candidate)
                candidate
            }.getOrNull()
            return active ?: packaged
        }

        private fun JSONObject.toIntMap(): Map<String, Int> = buildMap {
            val iterator = keys()
            while (iterator.hasNext()) iterator.next().let { key -> put(key, getInt(key)) }
        }

        private fun validateManifestInvariants(manifest: GlossaryManifest) {
            if (manifest.manifestVersion != 1 || manifest.schemaVersion != 1) {
                throw GlossaryIntegrityException("Unsupported glossary manifest/schema version")
            }
            if (manifest.llmRuntimeUsed) {
                throw GlossaryIntegrityException("Runtime-authored glossary packs are forbidden")
            }
            if (manifest.databaseAsset != DATABASE_ASSET) {
                throw GlossaryIntegrityException("Unsupported glossary database asset name")
            }
            if (!manifest.sha256.isSha256() || !manifest.inventorySha256.isSha256() ||
                !manifest.catalogSha256.isSha256()
            ) throw GlossaryIntegrityException("Malformed glossary SHA-256")
            if (manifest.glossaryDbVersion < 1 || manifest.byteSize !in 1..MAX_DATABASE_BYTES) {
                throw GlossaryIntegrityException("Invalid glossary version or size")
            }
            if (manifest.rowCounts.keys != VERIFIED_TABLES) {
                throw GlossaryIntegrityException("Glossary table verification set is incomplete")
            }
            val terms = manifest.rowCounts.getValue("terms")
            if (manifest.rowCounts.getValue("categories") != 21 || terms !in 1..100_000 ||
                manifest.rowCounts.getValue("glossary_fts") != terms ||
                manifest.rowCounts.getValue("aliases") < terms ||
                manifest.rowCounts.getValue("limitations") < terms ||
                manifest.rowCounts.getValue("sources") < 1 ||
                manifest.rowCounts.getValue("term_sources") < terms
            ) throw GlossaryIntegrityException("Glossary row-count invariants failed")
        }

        private fun prepareDatabase(context: Context, manifest: GlossaryManifest): File {
            val directory = glossaryDirectory(context)
            if (!directory.exists() && !directory.mkdirs()) {
                throw GlossaryIntegrityException("Could not create app-private glossary directory")
            }
            val target = databaseFile(context, manifest)
            if (target.isFile) {
                runCatching { verifyDatabase(target, manifest) }.onSuccess { return target }
            }
            val temporary = File(
                directory,
                ".${target.name}.${android.os.Process.myPid()}.${System.nanoTime()}.tmp",
            )
            try {
                context.assets.open(manifest.databaseAsset).use { input ->
                    FileOutputStream(temporary).use { output ->
                        input.copyTo(output)
                        output.flush()
                        output.fd.sync()
                    }
                }
                verifyDatabase(temporary, manifest)
                moveReplacing(temporary, target)
                verifyDatabase(target, manifest)
                return target
            } catch (error: GlossaryIntegrityException) {
                throw error
            } catch (error: Exception) {
                throw GlossaryIntegrityException("Could not install verified glossary database", error)
            } finally {
                Files.deleteIfExists(temporary.toPath())
            }
        }

        private fun verifyDatabase(file: File, manifest: GlossaryManifest) {
            if (!file.isFile || file.length() != manifest.byteSize) {
                throw GlossaryIntegrityException("Glossary database size mismatch")
            }
            if (sha256(file) != manifest.sha256) {
                throw GlossaryIntegrityException("Glossary database SHA-256 mismatch")
            }
            openReadOnly(file).use { connection ->
                val integrity = connection.scalarText("PRAGMA integrity_check")
                if (integrity != "ok") throw GlossaryIntegrityException("Glossary integrity_check failed")
                if (connection.scalarLong("PRAGMA user_version").toInt() != manifest.schemaVersion ||
                    connection.scalarLong("PRAGMA application_id").toInt() != EXPECTED_APPLICATION_ID
                ) throw GlossaryIntegrityException("Glossary SQLite identity mismatch")
                manifest.rowCounts.forEach { (table, expected) ->
                    val actual = connection.scalarLong("SELECT COUNT(*) FROM \"$table\"").toInt()
                    if (actual != expected) {
                        throw GlossaryIntegrityException("$table row invariant failed: expected $expected, found $actual")
                    }
                }
                if (connection.scalarLong("SELECT COUNT(*) FROM categories") != 21L ||
                    connection.scalarLong(
                        "SELECT COUNT(*) FROM terms WHERE length(trim(one_line_definition_ko)) < 18"
                    ) != 0L
                ) throw GlossaryIntegrityException("Glossary authored-copy invariant failed")
                val inventorySha = connection.scalarText(
                    "SELECT value FROM metadata WHERE key = 'inventory_sha256'"
                )
                val catalogSha = connection.scalarText(
                    "SELECT value FROM metadata WHERE key = 'catalog_sha256'"
                )
                val databaseVersion = connection.scalarText(
                    "SELECT value FROM metadata WHERE key = 'glossary_db_version'"
                ).toIntOrNull()
                val metadataTermCount = connection.scalarText(
                    "SELECT value FROM metadata WHERE key = 'term_count'"
                ).toIntOrNull()
                if (!inventorySha.equals(manifest.inventorySha256, ignoreCase = true) ||
                    !catalogSha.equals(manifest.catalogSha256, ignoreCase = true) ||
                    databaseVersion != manifest.glossaryDbVersion ||
                    metadataTermCount != manifest.rowCounts.getValue("terms")
                ) throw GlossaryIntegrityException("Glossary metadata mismatch")
                if (connection.query("PRAGMA foreign_key_check") { it.step() }) {
                    throw GlossaryIntegrityException("Glossary foreign_key_check failed")
                }
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

        fun installDownloadedRelease(
            context: Context,
            manifestBytes: ByteArray,
            downloadedDatabase: File,
        ): GlossaryManifest {
            val appContext = context.applicationContext
            val manifest = try {
                parseManifest(manifestBytes.toString(Charsets.UTF_8))
            } catch (error: Exception) {
                throw GlossaryIntegrityException("Downloaded glossary manifest is invalid", error)
            }
            validateManifestInvariants(manifest)
            val current = loadManifest(appContext)
            if (manifest.glossaryDbVersion <= current.glossaryDbVersion) {
                throw GlossaryIntegrityException("Downloaded glossary is not newer than the active glossary")
            }
            verifyDatabase(downloadedDatabase, manifest)

            val directory = glossaryDirectory(appContext)
            if (!directory.exists() && !directory.mkdirs()) {
                throw GlossaryIntegrityException("Could not create app-private glossary directory")
            }
            val target = databaseFile(appContext, manifest)
            val databaseTemporary = File(
                directory,
                ".${target.name}.${android.os.Process.myPid()}.${System.nanoTime()}.tmp",
            )
            val manifestTarget = File(directory, ACTIVE_MANIFEST)
            val manifestTemporary = File(
                directory,
                ".$ACTIVE_MANIFEST.${android.os.Process.myPid()}.${System.nanoTime()}.tmp",
            )
            try {
                downloadedDatabase.inputStream().use { input ->
                    FileOutputStream(databaseTemporary).use { output ->
                        input.copyTo(output)
                        output.flush()
                        output.fd.sync()
                    }
                }
                verifyDatabase(databaseTemporary, manifest)
                moveReplacing(databaseTemporary, target)
                verifyDatabase(target, manifest)
                FileOutputStream(manifestTemporary).use { output ->
                    output.write(manifestBytes)
                    output.flush()
                    output.fd.sync()
                }
                moveReplacing(manifestTemporary, manifestTarget)
                return loadManifest(appContext).also { installed ->
                    if (installed.glossaryDbVersion != manifest.glossaryDbVersion ||
                        installed.sha256 != manifest.sha256
                    ) throw GlossaryIntegrityException("Downloaded glossary was not activated")
                }
            } catch (error: GlossaryIntegrityException) {
                throw error
            } catch (error: Exception) {
                throw GlossaryIntegrityException("Could not activate downloaded glossary", error)
            } finally {
                Files.deleteIfExists(databaseTemporary.toPath())
                Files.deleteIfExists(manifestTemporary.toPath())
            }
        }

        private fun moveReplacing(source: File, target: File) {
            try {
                Files.move(
                    source.toPath(), target.toPath(), StandardCopyOption.ATOMIC_MOVE,
                    StandardCopyOption.REPLACE_EXISTING,
                )
            } catch (_: java.nio.file.AtomicMoveNotSupportedException) {
                Files.move(source.toPath(), target.toPath(), StandardCopyOption.REPLACE_EXISTING)
            }
        }

        private fun pruneObsoleteDatabases(directory: File, active: File) {
            val releaseFile = Regex("^v\\d+-[0-9a-f]{16}\\.sqlite3$")
            directory.listFiles()?.forEach { candidate ->
                if (candidate != active && candidate.isFile && releaseFile.matches(candidate.name)) {
                    runCatching { Files.deleteIfExists(candidate.toPath()) }
                }
            }
        }

        private fun toFtsQuery(query: String): String = Regex("[\\p{L}\\p{N}]+")
            .findAll(query)
            .map { "\"${it.value.replace("\"", "\"\"")}\"*" }
            .take(8)
            .joinToString(" AND ")

        private fun String.isSha256(): Boolean = matches(Regex("[0-9a-f]{64}"))
        private const val MAX_DATABASE_BYTES = 128L * 1024 * 1024
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
    if (!statement.step()) throw GlossaryIntegrityException("Glossary scalar query returned no row")
    statement.getText(0)
}

private fun SQLiteConnection.scalarLong(sql: String): Long = query(sql) { statement ->
    if (!statement.step()) throw GlossaryIntegrityException("Glossary scalar query returned no row")
    statement.getLong(0)
}

private fun SQLiteConnection.textColumn(sql: String, argument: String): List<String> =
    query(sql, listOf(argument)) { statement ->
        buildList { while (statement.step()) add(statement.getText(0)) }
    }

private fun String.jsonStrings(): List<String> {
    val array = JSONArray(this)
    return List(array.length()) { index -> array.getString(index) }
}
