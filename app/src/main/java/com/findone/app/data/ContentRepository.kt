package com.findone.app.data

import android.content.Context
import androidx.sqlite.SQLiteConnection
import androidx.sqlite.SQLiteStatement
import androidx.sqlite.driver.bundled.BundledSQLiteDriver
import androidx.sqlite.driver.bundled.SQLITE_OPEN_FULLMUTEX
import androidx.sqlite.driver.bundled.SQLITE_OPEN_READONLY
import com.findone.app.model.ContentElement
import com.findone.app.model.ContentManifest
import com.findone.app.model.ContentSource
import com.findone.app.model.Domain
import com.findone.app.quiz.CuratedConceptChoice
import com.findone.app.quiz.CuratedConceptQuestion
import org.json.JSONArray
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

private data class CuratedQuestionBuilder(
    val questionId: String,
    val elementId: String,
    val questionType: String,
    val stem: String,
    val explanation: String,
    val coreRelation: String,
    val difficulty: Int,
    val modelVersion: String,
    val reviewStatus: String,
    val sourceFactIds: List<String>,
    val choices: MutableList<CuratedConceptChoice> = mutableListOf(),
) {
    fun build() = CuratedConceptQuestion(
        questionId = questionId,
        elementId = elementId,
        questionType = questionType,
        stem = stem,
        explanation = explanation,
        coreRelation = coreRelation,
        difficulty = difficulty,
        modelVersion = modelVersion,
        reviewStatus = reviewStatus,
        sourceFactIds = sourceFactIds,
        choices = choices.toList(),
    )
}

/**
 * Read-only access to the signed content asset.
 *
 * The asset uses FTS5, which is not guaranteed by Android's framework SQLite. A bundled SQLite
 * driver is therefore deliberately used so API 26+ devices all execute the same FTS5/BM25 code.
 */
class ContentRepository(context: Context) : Closeable {
    val manifest: ContentManifest

    private val database: SQLiteConnection
    private val sourcesByElement: Map<String, List<ContentSource>>
    private val queryLock = Any()

    init {
        val appContext = context.applicationContext
        manifest = loadManifest(appContext)
        validateManifestInvariants(manifest)
        val databaseFile = prepareDatabase(appContext, manifest)
        database = openReadOnly(databaseFile)
        sourcesByElement = loadElementSources()
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
                """SELECT $ELEMENT_PROJECTION FROM elements e
                   JOIN concept_cards c ON c.element_id = e.element_id
                   JOIN formula_cards f ON f.element_id = e.element_id
                   WHERE e.element_id = ? LIMIT 1""".trimIndent(),
                listOf(normalizedId),
            ) { statement -> if (statement.step()) statement.contentElement() else null }
        }
    }

    fun conceptQuestions(): List<CuratedConceptQuestion> = synchronized(queryLock) {
        database.query(
            """
            SELECT q.question_id, q.element_id, q.question_type, q.stem,
                   q.explanation, e.core_relation, q.difficulty, q.model_version,
                   q.review_status, q.source_fact_ids_json,
                   c.choice_key, c.text, c.element_id, c.explanation, c.is_correct
            FROM concept_questions q
            JOIN elements e ON e.element_id = q.element_id
            JOIN concept_question_choices c ON c.question_id = q.question_id
            WHERE q.review_status IN ('automated_pass', 'owner_approved')
            ORDER BY q.display_order, c.choice_order
            """.trimIndent()
        ) { statement ->
            val builders = linkedMapOf<String, CuratedQuestionBuilder>()
            while (statement.step()) {
                val questionId = statement.getText(0)
                val builder = builders.getOrPut(questionId) {
                    val sourceJson = JSONArray(statement.getText(9))
                    CuratedQuestionBuilder(
                        questionId = questionId,
                        elementId = statement.getText(1),
                        questionType = statement.getText(2),
                        stem = statement.getText(3),
                        explanation = statement.getText(4),
                        coreRelation = statement.getText(5),
                        difficulty = statement.getLong(6).toInt(),
                        modelVersion = statement.getText(7),
                        reviewStatus = statement.getText(8),
                        sourceFactIds = List(sourceJson.length()) { sourceJson.getString(it) },
                    )
                }
                builder.choices += CuratedConceptChoice(
                    key = statement.getText(10),
                    text = statement.getText(11),
                    elementId = statement.getText(12),
                    explanation = statement.getText(13),
                    isCorrect = statement.getLong(14) == 1L,
                )
            }
            builders.values.map(CuratedQuestionBuilder::build)
        }
    }

    override fun close() = synchronized(queryLock) { database.close() }

    private fun listElements(domainId: String?): List<ContentElement> {
        val whereClause = if (domainId == null) "" else "WHERE e.domain_id = ?"
        val arguments = if (domainId == null) emptyList() else listOf(domainId)
        return database.query(
            """SELECT $ELEMENT_PROJECTION
               FROM elements e
               JOIN domains d ON d.domain_id = e.domain_id
               JOIN concept_cards c ON c.element_id = e.element_id
               JOIN formula_cards f ON f.element_id = e.element_id
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
        val ftsResults = database.query(
            """SELECT $ELEMENT_PROJECTION
               FROM knowledge_fts
               JOIN elements e ON e.element_id = knowledge_fts.element_id
               JOIN concept_cards c ON c.element_id = e.element_id
               JOIN formula_cards f ON f.element_id = e.element_id
               WHERE knowledge_fts MATCH ? $domainClause
               ORDER BY bm25(knowledge_fts), e.display_order""".trimIndent(),
            arguments,
        ) { it.readElements() }
        return if (ftsResults.isNotEmpty()) ftsResults
        else searchElementsWithLike(domainId, query)
    }

    private fun searchElementsWithLike(domainId: String?, query: String): List<ContentElement> {
        val domainClause = if (domainId == null) "" else "AND e.domain_id = ?"
        val escapedQuery = buildString(query.length) {
            query.forEach { character ->
                if (character == '\\' || character == '%' || character == '_') append('\\')
                append(character)
            }
        }
        val likeArgument = "%$escapedQuery%"
        val arguments = buildList {
            repeat(8) { add(likeArgument) }
            if (domainId != null) add(domainId)
        }
        return database.query(
            """SELECT $ELEMENT_PROJECTION FROM elements e
               JOIN concept_cards c ON c.element_id = e.element_id
               JOIN formula_cards f ON f.element_id = e.element_id
               WHERE (e.title LIKE ? ESCAPE '\' OR e.core_relation LIKE ? ESCAPE '\'
                   OR c.definition LIKE ? ESCAPE '\' OR c.intuition LIKE ? ESCAPE '\'
                   OR c.scope_notes LIKE ? ESCAPE '\' OR f.expression LIKE ? ESCAPE '\'
                   OR f.assumptions LIKE ? ESCAPE '\' OR f.notes LIKE ? ESCAPE '\')
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
        definitionMarkdown = getText(8),
        intuitionMarkdown = getText(9),
        learningNotesMarkdown = getText(10),
        formulaMarkdown = getText(11),
        assumptionsMarkdown = getText(12),
        checklistMarkdown = getText(13),
        sources = sourcesByElement[getText(0)].orEmpty(),
    )

    private fun loadElementSources(): Map<String, List<ContentSource>> = database.query(
        """SELECT es.element_id, s.source_id, s.label, s.locator, s.source_type, s.notes
           FROM element_sources es JOIN sources s ON s.source_id = es.source_id
           ORDER BY es.element_id, es.ordinal""".trimIndent()
    ) { statement ->
        buildMap<String, MutableList<ContentSource>> {
            while (statement.step()) {
                getOrPut(statement.getText(0)) { mutableListOf() }.add(
                    ContentSource(
                        id = statement.getText(1),
                        label = statement.getText(2),
                        locator = statement.getText(3),
                        type = statement.getText(4),
                        notes = statement.getText(5),
                    )
                )
            }
        }
    }

    companion object {
        private const val MANIFEST_ASSET = "content-manifest.json"
        private const val ACTIVE_MANIFEST = "active-manifest.json"
        private val EXPECTED_DOMAIN_COUNTS = mapOf(
            "ACC" to 12, "CF" to 12, "INV" to 9, "FI" to 10,
            "DER" to 10, "EQV" to 64, "IBT" to 18,
        )
        private val VERIFIED_TABLES = setOf(
            "metadata", "domains", "elements", "concept_cards", "formula_cards",
            "concept_questions", "concept_question_choices", "sources",
            "element_sources", "knowledge_fts",
        )
        private const val ELEMENT_PROJECTION = """
            e.element_id, e.domain_id, e.title, e.core_relation, e.scope_notes,
            e.source_label, e.source_locator, e.spec_section_locator,
            c.definition, c.intuition, c.scope_notes,
            f.expression, f.assumptions, f.notes
        """

        private fun parseManifest(value: String): ContentManifest {
            val json = JSONObject(value)
            return ContentManifest(
                manifestVersion = json.getInt("manifestVersion"),
                schemaVersion = json.getInt("schemaVersion"),
                contentDbVersion = json.getInt("contentDbVersion"),
                databaseAsset = json.getString("databaseAsset"),
                sha256 = json.getString("sha256").lowercase(Locale.ROOT),
                byteSize = json.getLong("byteSize"),
                sourceSpec = json.getString("sourceSpec"),
                sourceSha256 = json.getString("sourceSha256").lowercase(Locale.ROOT),
                conceptQuestionBankVersion = json.getInt("conceptQuestionBankVersion"),
                conceptQuestionBankSha256 = json.getString("conceptQuestionBankSha256")
                    .lowercase(Locale.ROOT),
                conceptQuestionModelVersion = json.getString("conceptQuestionModelVersion"),
                conceptQuestionReleaseStatus = json.getString("conceptQuestionReleaseStatus"),
                rowCounts = json.getJSONObject("rowCounts").toIntMap(),
                domainElementCounts = json.getJSONObject("domainElementCounts").toIntMap(),
            )
        }

        private fun packagedManifest(context: Context): ContentManifest = context.assets
            .open(MANIFEST_ASSET)
            .bufferedReader(Charsets.UTF_8)
            .use { parseManifest(it.readText()) }

        private fun contentDirectory(context: Context): File = File(context.filesDir, "content")

        private fun databaseFile(context: Context, manifest: ContentManifest): File = File(
            contentDirectory(context),
            "v${manifest.contentDbVersion}-${manifest.sha256.take(16)}.sqlite3",
        )

        private fun loadManifest(context: Context): ContentManifest {
            val packaged = packagedManifest(context)
            validateManifestInvariants(packaged)
            val activeFile = File(contentDirectory(context), ACTIVE_MANIFEST)
            val active = runCatching {
                val candidate = parseManifest(activeFile.readText(Charsets.UTF_8))
                validateManifestInvariants(candidate)
                if (candidate.contentDbVersion < packaged.contentDbVersion) {
                    throw ContentIntegrityException("Downloaded content is older than the packaged baseline")
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

        private fun validateManifestInvariants(manifest: ContentManifest) {
            if (manifest.manifestVersion != 1 || manifest.schemaVersion != 2) {
                throw ContentIntegrityException("Unsupported content manifest/schema version")
            }
            if (manifest.databaseAsset != "content.sqlite3") {
                throw ContentIntegrityException("Unsupported database asset name")
            }
            if (!manifest.sha256.matches(Regex("[0-9a-f]{64}")) ||
                !manifest.sourceSha256.matches(Regex("[0-9a-f]{64}")) ||
                !manifest.conceptQuestionBankSha256.matches(Regex("[0-9a-f]{64}"))
            ) {
                throw ContentIntegrityException("Malformed content SHA-256")
            }
            if (manifest.contentDbVersion < 1 || manifest.byteSize < 1) {
                throw ContentIntegrityException("Invalid content version or size")
            }
            if (manifest.rowCounts["domains"] != 7 || manifest.rowCounts["elements"] != 135) {
                throw ContentIntegrityException("Manifest domain/element invariant failed")
            }
            if (manifest.rowCounts["concept_cards"] != 135 ||
                manifest.rowCounts["formula_cards"] != 135 ||
                manifest.rowCounts["concept_questions"] != 405 ||
                manifest.rowCounts["concept_question_choices"] != 2025 ||
                manifest.rowCounts["knowledge_fts"] != 135
            ) throw ContentIntegrityException("Manifest card/question/FTS invariant failed")
            if (manifest.conceptQuestionBankVersion != 1 ||
                manifest.conceptQuestionModelVersion.isBlank() ||
                manifest.conceptQuestionReleaseStatus !in setOf(
                    "bootstrap_not_reviewed", "candidate", "release_ready"
                )
            ) throw ContentIntegrityException("Manifest question-bank invariant failed")
            if (manifest.domainElementCounts != EXPECTED_DOMAIN_COUNTS) {
                throw ContentIntegrityException("Manifest domain row counts are not canonical")
            }
            if (manifest.rowCounts.keys != VERIFIED_TABLES) {
                throw ContentIntegrityException("Manifest table verification set is incomplete")
            }
        }

        private fun prepareDatabase(context: Context, manifest: ContentManifest): File {
            val contentDirectory = contentDirectory(context)
            if (!contentDirectory.exists() && !contentDirectory.mkdirs()) {
                throw ContentIntegrityException("Could not create app-private content directory")
            }
            val target = databaseFile(context, manifest)
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
                val bankSha = connection.scalarText(
                    "SELECT value FROM metadata WHERE key = 'concept_question_bank_sha256'"
                )
                if (!bankSha.equals(manifest.conceptQuestionBankSha256, ignoreCase = true)) {
                    throw ContentIntegrityException("Database concept-question bank hash mismatch")
                }
                val bankStatus = connection.scalarText(
                    "SELECT value FROM metadata WHERE key = 'concept_question_release_status'"
                )
                if (bankStatus != manifest.conceptQuestionReleaseStatus) {
                    throw ContentIntegrityException("Database concept-question status mismatch")
                }
                val invalidReviewStatuses = connection.scalarLong(
                    """
                    SELECT COUNT(*) FROM concept_questions
                    WHERE review_status NOT IN (
                        'automated_pass', 'needs_owner_review', 'blocked', 'owner_approved'
                    )
                    """.trimIndent()
                )
                if (invalidReviewStatuses != 0L) {
                    throw ContentIntegrityException("Database concept-question review status is invalid")
                }
                if (bankStatus == "release_ready") {
                    val ineligibleReleaseQuestions = connection.scalarLong(
                        """
                        SELECT COUNT(*) FROM concept_questions
                        WHERE review_status NOT IN ('automated_pass', 'owner_approved')
                        """.trimIndent()
                    )
                    if (ineligibleReleaseQuestions != 0L) {
                        throw ContentIntegrityException(
                            "Release-ready database contains non-eligible concept questions"
                        )
                    }
                }
                val missingEligibleCoverage = connection.scalarLong(
                    """
                    SELECT COUNT(*)
                    FROM (
                        SELECT e.element_id
                        FROM elements e
                        LEFT JOIN concept_questions q
                            ON q.element_id = e.element_id
                           AND q.review_status IN ('automated_pass', 'owner_approved')
                        GROUP BY e.element_id
                        HAVING COUNT(q.question_id) = 0
                    )
                    """.trimIndent()
                )
                if (missingEligibleCoverage != 0L) {
                    throw ContentIntegrityException(
                        "Database has elements without an eligible concept question"
                    )
                }
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

        fun installDownloadedRelease(
            context: Context,
            manifestBytes: ByteArray,
            downloadedDatabase: File,
        ): ContentManifest {
            val appContext = context.applicationContext
            val manifestText = manifestBytes.toString(Charsets.UTF_8)
            val manifest = try {
                parseManifest(manifestText)
            } catch (error: Exception) {
                throw ContentIntegrityException("Downloaded content manifest is invalid", error)
            }
            validateManifestInvariants(manifest)
            val current = loadManifest(appContext)
            if (manifest.contentDbVersion <= current.contentDbVersion) {
                throw ContentIntegrityException("Downloaded content is not newer than the active content")
            }
            verifyDatabase(downloadedDatabase, manifest)

            val directory = contentDirectory(appContext)
            if (!directory.exists() && !directory.mkdirs()) {
                throw ContentIntegrityException("Could not create app-private content directory")
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
                val installed = loadManifest(appContext)
                if (installed.contentDbVersion != manifest.contentDbVersion || installed.sha256 != manifest.sha256) {
                    throw ContentIntegrityException("Downloaded content was not activated")
                }
                return installed
            } catch (error: ContentIntegrityException) {
                throw error
            } catch (error: Exception) {
                throw ContentIntegrityException("Could not activate downloaded content", error)
            } finally {
                Files.deleteIfExists(databaseTemporary.toPath())
                Files.deleteIfExists(manifestTemporary.toPath())
            }
        }

        private fun moveReplacing(source: File, target: File) {
            try {
                Files.move(
                    source.toPath(),
                    target.toPath(),
                    StandardCopyOption.ATOMIC_MOVE,
                    StandardCopyOption.REPLACE_EXISTING,
                )
            } catch (_: java.nio.file.AtomicMoveNotSupportedException) {
                Files.move(source.toPath(), target.toPath(), StandardCopyOption.REPLACE_EXISTING)
            }
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
