package com.findone.app.data

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import com.findone.app.quiz.QuizMode
import com.findone.app.quiz.QuizPresentation
import com.findone.app.quiz.QuizTemplateIdentity
import org.json.JSONArray
import org.json.JSONObject
import java.io.InputStream
import java.io.OutputStream
import java.io.ByteArrayOutputStream
import java.io.File
import java.io.FileOutputStream
import java.nio.file.Files
import java.nio.file.StandardCopyOption
import java.security.MessageDigest

data class AttemptInput(
    val instanceId: String,
    val elementId: String,
    val templateId: String,
    val mode: String,
    val presentation: String,
    val seed: Long,
    val prompt: String,
    val canonicalAnswer: String,
    val userAnswer: String,
    val correct: Boolean,
    val explanation: List<String>,
    val elapsedMs: Long,
)

data class WrongQueueEntry(
    val elementId: String,
    val templateId: String,
    val mode: String,
    val presentation: String,
    val lastSeed: Long,
    val updatedAt: Long,
)

data class AttemptRecord(
    val id: Long,
    val instanceId: String,
    val elementId: String,
    val templateId: String,
    val mode: String,
    val seed: Long,
    val prompt: String,
    val canonicalAnswer: String,
    val userAnswer: String,
    val correct: Boolean,
    val explanation: List<String>,
    val elapsedMs: Long,
    val createdAt: Long,
)

data class BookmarkInput(
    val instanceId: String,
    val elementId: String,
    val templateId: String,
    val mode: String,
    val seed: Long,
    val snapshotJson: String,
    val origin: BookmarkOrigin = BookmarkOrigin.MANUAL,
)

enum class BookmarkOrigin { MANUAL, AUTO_WRONG }

data class BookmarkRecord(
    val instanceId: String,
    val elementId: String,
    val templateId: String,
    val mode: String,
    val seed: Long,
    val snapshotJson: String,
    val createdAt: Long,
    val origin: BookmarkOrigin = BookmarkOrigin.MANUAL,
)

data class StudyStats(
    val attempted: Int = 0,
    val correct: Int = 0,
    val wrongUnresolved: Int = 0,
    val bookmarked: Int = 0,
    val studiedElements: Int = 0,
) {
    val accuracyPercent: Int
        get() = if (attempted == 0) 0 else (correct * 100.0 / attempted).toInt()
}

data class ElementProgress(
    val elementId: String,
    val attempts: Int,
    val correct: Int,
    val currentStreak: Int,
    val lastAttemptAt: Long,
)

class UserRepository(context: Context) {
    private val databaseContext = context.applicationContext
    private val helper: UserDatabase

    init {
        preservePreMigrationDatabase(databaseContext)
        helper = UserDatabase(databaseContext)
        // Open now so migration failures surface while the verified N-1 copy still exists.
        val db = helper.writableDatabase
        db.inTransaction { maintainBoundedUserHistory(db) }
    }

    fun recordAttempt(input: AttemptInput): Long {
        val db = helper.writableDatabase
        val now = System.currentTimeMillis()
        var rowId = -1L
        db.beginTransaction()
        try {
            requireCanInsertKeyedRow(
                db = db,
                table = "element_progress",
                keyColumn = "element_id",
                key = input.elementId,
                maxRows = MAX_PROGRESS_ROWS,
                errorMessage = "진도 행이 허용량을 넘습니다.",
            )
            rowId = db.insertOrThrow("attempts", null, ContentValues().apply {
                put("instance_id", input.instanceId)
                put("element_id", input.elementId)
                put("template_id", input.templateId)
                put("mode", input.mode)
                put("presentation", input.presentation)
                put("seed", input.seed)
                put("prompt", input.prompt)
                put("canonical_answer", input.canonicalAnswer)
                put("user_answer", input.userAnswer)
                put("is_correct", if (input.correct) 1 else 0)
                put("explanation_json", JSONArray(input.explanation).toString())
                put("elapsed_ms", input.elapsedMs.coerceAtLeast(0))
                put("created_at", now)
            })

            val existing = progress(input.elementId)
            val nextStreak = if (input.correct) existing.currentStreak + 1 else 0
            db.insertWithOnConflict("element_progress", null, ContentValues().apply {
                put("element_id", input.elementId)
                put("attempts", existing.attempts + 1)
                put("correct", existing.correct + if (input.correct) 1 else 0)
                put("current_streak", nextStreak)
                put("last_attempt_at", now)
            }, SQLiteDatabase.CONFLICT_REPLACE)

            if (input.correct) {
                db.execSQL(
                    """UPDATE wrong_queue
                       SET correct_streak = correct_streak + 1,
                           updated_at = ?
                       WHERE element_id = ? AND template_id = ? AND resolved = 0""".trimIndent(),
                    arrayOf(now, input.elementId, input.templateId),
                )
            } else {
                db.insertWithOnConflict("wrong_queue", null, ContentValues().apply {
                    put("element_id", input.elementId)
                    put("template_id", input.templateId)
                    put("mode", input.mode)
                    put("presentation", input.presentation)
                    put("last_instance_id", input.instanceId)
                    put("last_attempt_id", rowId)
                    put("last_seed", input.seed)
                    put("correct_streak", 0)
                    put("resolved", 0)
                    put("updated_at", now)
                }, SQLiteDatabase.CONFLICT_REPLACE)
            }
            cleanupWrongQueue(db)
            requireTableRowsAtMost(db, "wrong_queue", MAX_WRONG_QUEUE, "오답 큐가 허용량을 넘습니다.")
            pruneAttempts(db, input.elementId)
            requireTableRowsAtMost(
                db,
                "attempts",
                MAX_RECENT_ATTEMPTS_TOTAL,
                "상세 시도 기록 정리에 실패했습니다.",
            )
            db.setTransactionSuccessful()
        } finally {
            db.endTransaction()
        }
        return rowId
    }

    fun toggleBookmark(input: BookmarkInput): Boolean {
        val db = helper.writableDatabase
        var bookmarked = false
        db.beginTransaction()
        try {
            val exists = db.rawQuery(
                "SELECT 1 FROM bookmarks WHERE instance_id = ? LIMIT 1",
                arrayOf(input.instanceId),
            ).use { it.moveToFirst() }
            if (exists) {
                db.delete("bookmarks", "instance_id = ?", arrayOf(input.instanceId))
            } else {
                db.insertOrThrow("bookmarks", null, ContentValues().apply {
                    put("instance_id", input.instanceId)
                    put("element_id", input.elementId)
                    put("template_id", input.templateId)
                    put("mode", input.mode)
                    put("seed", input.seed)
                    put("snapshot_json", input.snapshotJson)
                    put("created_at", System.currentTimeMillis())
                    put("origin", input.origin.name)
                })
                if (input.origin == BookmarkOrigin.AUTO_WRONG) {
                    pruneAutomaticBookmarks(db, input.elementId)
                }
                requireTableRowsAtMost(db, "bookmarks", MAX_BOOKMARKS, "북마크가 허용량을 넘습니다.")
                bookmarked = true
            }
            db.setTransactionSuccessful()
        } finally {
            db.endTransaction()
        }
        return bookmarked
    }

    fun isBookmarked(instanceId: String): Boolean = helper.readableDatabase.rawQuery(
        "SELECT 1 FROM bookmarks WHERE instance_id = ? LIMIT 1", arrayOf(instanceId)
    ).use { it.moveToFirst() }

    fun progress(elementId: String): ElementProgress = helper.readableDatabase.rawQuery(
        "SELECT attempts, correct, current_streak, last_attempt_at FROM element_progress WHERE element_id = ?",
        arrayOf(elementId),
    ).use { cursor ->
        if (cursor.moveToFirst()) ElementProgress(
            elementId,
            cursor.getInt(0),
            cursor.getInt(1),
            cursor.getInt(2),
            cursor.getLong(3),
        ) else ElementProgress(elementId, 0, 0, 0, 0)
    }

    fun allProgress(): Map<String, ElementProgress> = buildMap {
        helper.readableDatabase.rawQuery(
            "SELECT element_id, attempts, correct, current_streak, last_attempt_at FROM element_progress",
            null,
        ).use { cursor ->
            while (cursor.moveToNext()) {
                val item = ElementProgress(
                    cursor.getString(0), cursor.getInt(1), cursor.getInt(2), cursor.getInt(3), cursor.getLong(4)
                )
                put(item.elementId, item)
            }
        }
    }

    fun stats(): StudyStats {
        val db = helper.readableDatabase
        fun scalar(sql: String): Int = db.rawQuery(sql, null).use { if (it.moveToFirst()) it.getInt(0) else 0 }
        return StudyStats(
            attempted = scalar("SELECT COALESCE(SUM(attempts), 0) FROM element_progress"),
            correct = scalar("SELECT COALESCE(SUM(correct), 0) FROM element_progress"),
            wrongUnresolved = scalar("SELECT COUNT(*) FROM wrong_queue WHERE resolved = 0"),
            bookmarked = scalar("SELECT COUNT(*) FROM bookmarks"),
            studiedElements = scalar("SELECT COUNT(*) FROM element_progress WHERE attempts > 0"),
        )
    }

    fun unresolvedWrong(): List<WrongQueueEntry> = buildList {
        helper.readableDatabase.rawQuery(
            """SELECT element_id, template_id, mode, presentation, last_seed, updated_at
               FROM wrong_queue WHERE resolved = 0 ORDER BY updated_at DESC""".trimIndent(),
            null,
        ).use { cursor ->
            while (cursor.moveToNext()) {
                add(
                    WrongQueueEntry(
                        elementId = cursor.getString(0),
                        templateId = cursor.getString(1),
                        mode = cursor.getString(2),
                        presentation = cursor.getString(3),
                        lastSeed = cursor.getLong(4),
                        updatedAt = cursor.getLong(5),
                    )
                )
            }
        }
    }

    fun resolutionSuggestions(): Set<String> = buildSet {
        helper.readableDatabase.rawQuery(
            "SELECT element_id, template_id FROM wrong_queue WHERE resolved = 0 AND correct_streak >= 2",
            null,
        ).use { cursor ->
            while (cursor.moveToNext()) add("${cursor.getString(0)}|${cursor.getString(1)}")
        }
    }

    fun confirmWrongResolved(elementId: String, templateId: String) {
        val db = helper.writableDatabase
        db.beginTransaction()
        try {
            db.update(
                "wrong_queue",
                ContentValues().apply {
                    put("resolved", 1)
                    put("updated_at", System.currentTimeMillis())
                },
                "element_id = ? AND template_id = ? AND correct_streak >= 2",
                arrayOf(elementId, templateId),
            )
            cleanupWrongQueue(db)
            pruneAttempts(db, elementId)
            db.setTransactionSuccessful()
        } finally {
            db.endTransaction()
        }
    }

    /** Latest retained wrong attempt per learning element, newest first. */
    fun recentWrong(limit: Int = MAX_RECENT_WRONG_ROWS): List<AttemptRecord> =
        recentWrongForScope(null, limit)

    fun recentWrongForElements(
        elementIds: Collection<String>,
        limit: Int = MAX_RECENT_WRONG_ROWS,
    ): List<AttemptRecord> = recentWrongForScope(elementIds, limit)

    private fun recentWrongForScope(
        elementIds: Collection<String>?,
        limit: Int,
    ): List<AttemptRecord> {
        val scope = elementIds?.distinct().orEmpty()
        if (elementIds != null && scope.isEmpty()) return emptyList()
        require(scope.size <= MAX_PROGRESS_ROWS) { "조회할 학습요소가 너무 많습니다." }
        val scopeSql = if (elementIds == null) "" else
            " AND a.element_id IN (${List(scope.size) { "?" }.joinToString(",")})"
        val args = buildList {
            addAll(scope)
            add(limit.coerceIn(1, MAX_RECENT_WRONG_ROWS).toString())
        }.toTypedArray()
        return attempts(
            """SELECT a.id,a.instance_id,a.element_id,a.template_id,a.mode,a.seed,a.prompt,
                      a.canonical_answer,a.user_answer,a.is_correct,a.explanation_json,a.elapsed_ms,a.created_at
               FROM attempts a
               WHERE a.is_correct = 0
                 AND NOT EXISTS (
                     SELECT 1 FROM attempts newer
                     WHERE newer.element_id = a.element_id
                       AND newer.is_correct = 0
                       AND (newer.created_at > a.created_at OR
                            (newer.created_at = a.created_at AND newer.id > a.id))
                 )$scopeSql
               ORDER BY a.created_at DESC, a.id DESC
               LIMIT ?""".trimIndent(),
            args,
        )
    }

    /** Full bookmark set used by quiz replay. Record screens should use [recentBookmarks]. */
    fun bookmarks(): List<BookmarkRecord> = queryBookmarks(null, null)

    fun recentBookmarks(
        elementIds: Collection<String>? = null,
        limit: Int = MAX_RECENT_BOOKMARK_ROWS,
    ): List<BookmarkRecord> = queryBookmarks(elementIds, limit.coerceIn(1, MAX_RECENT_BOOKMARK_ROWS))

    private fun queryBookmarks(elementIds: Collection<String>?, limit: Int?): List<BookmarkRecord> = buildList {
        val scope = elementIds?.distinct().orEmpty()
        if (elementIds != null && scope.isEmpty()) return@buildList
        require(scope.size <= MAX_PROGRESS_ROWS) { "조회할 학습요소가 너무 많습니다." }
        val where = if (elementIds == null) "" else
            " WHERE element_id IN (${List(scope.size) { "?" }.joinToString(",")})"
        val limitSql = if (limit == null) "" else " LIMIT ?"
        val args = buildList {
            addAll(scope)
            if (limit != null) add(limit.toString())
        }.toTypedArray()
        helper.readableDatabase.rawQuery(
            "SELECT instance_id,element_id,template_id,mode,seed,snapshot_json,created_at,origin " +
                "FROM bookmarks$where ORDER BY created_at DESC, instance_id DESC$limitSql",
            args,
        ).use { cursor ->
            while (cursor.moveToNext()) add(
                BookmarkRecord(
                    cursor.getString(0), cursor.getString(1), cursor.getString(2), cursor.getString(3),
                    cursor.getLong(4), cursor.getString(5), cursor.getLong(6),
                    runCatching { BookmarkOrigin.valueOf(cursor.getString(7)) }.getOrDefault(BookmarkOrigin.MANUAL),
                )
            )
        }
    }

    fun recentAttempts(limit: Int = 100): List<AttemptRecord> = attempts(
        "SELECT id,instance_id,element_id,template_id,mode,seed,prompt,canonical_answer,user_answer,is_correct,explanation_json,elapsed_ms,created_at " +
            "FROM attempts ORDER BY created_at DESC, id DESC LIMIT ?", arrayOf(limit.toString())
    )

    fun setting(key: String, default: String): String = helper.readableDatabase.rawQuery(
        "SELECT value FROM settings WHERE key = ?", arrayOf(key)
    ).use { if (it.moveToFirst()) it.getString(0) else default }

    fun setSetting(key: String, value: String) {
        val db = helper.writableDatabase
        db.inTransaction {
            requireCanInsertKeyedRow(
                db = db,
                table = "settings",
                keyColumn = "key",
                key = key,
                maxRows = MAX_SETTINGS,
                errorMessage = "설정 행이 허용량을 넘습니다.",
            )
            db.insertWithOnConflict("settings", null, ContentValues().apply {
                put("key", key); put("value", value)
            }, SQLiteDatabase.CONFLICT_REPLACE)
        }
    }

    fun clearLearningData() {
        val db = helper.writableDatabase
        db.beginTransaction()
        try {
            listOf("attempts", "bookmarks", "wrong_queue", "element_progress").forEach { db.delete(it, null, null) }
            db.setTransactionSuccessful()
        } finally {
            db.endTransaction()
        }
        deletePreMigrationDatabases(databaseContext)
    }

    /** Portable, explicitly user-triggered backup. No automatic cloud backup is used. */
    fun exportBackup(output: OutputStream) {
        val db = helper.writableDatabase
        val payload = db.inTransaction {
            maintainBoundedUserHistory(db)
            requireBackupRowCounts(backupRowCounts(db))
            JSONObject().apply {
                put("schemaVersion", USER_DB_VERSION)
                put("exportedAt", System.currentTimeMillis())
                put("attempts", tableAsJson(db, "attempts"))
                put("bookmarks", tableAsJson(db, "bookmarks"))
                put("wrongQueue", tableAsJson(db, "wrong_queue"))
                put("elementProgress", tableAsJson(db, "element_progress"))
                put("settings", tableAsJson(db, "settings"))
            }
        }
        val payloadText = payload.toString()
        val envelope = JSONObject().apply {
            put("format", BACKUP_FORMAT)
            put("sha256", sha256(payloadText.toByteArray(Charsets.UTF_8)))
            // Hash and store the exact same byte sequence; JSONObject key ordering is not canonical.
            put("payload", payloadText)
        }
        val backupBytes = envelope.toString(2).toByteArray(Charsets.UTF_8)
        require(backupBytes.size <= MAX_BACKUP_BYTES) {
            "백업 데이터가 ${MAX_BACKUP_BYTES / (1024 * 1024)}MB 제한을 넘습니다. 오래된 기록을 정리한 뒤 다시 시도하세요."
        }
        output.use { it.write(backupBytes) }
    }

    fun importBackup(input: InputStream) {
        val envelopeBytes = input.readWithLimit(MAX_BACKUP_BYTES)
        val envelope = JSONObject(envelopeBytes.toString(Charsets.UTF_8))
        val format = envelope.getString("format")
        require(
            format == BACKUP_FORMAT || format == SCHEMA_2_BACKUP_FORMAT || format == LEGACY_BACKUP_FORMAT
        ) { "지원하지 않는 백업 형식입니다." }
        val payloadText = envelope.getString("payload")
        val actualHash = sha256(payloadText.toByteArray(Charsets.UTF_8))
        require(actualHash == envelope.getString("sha256")) { "백업 파일의 무결성 검증에 실패했습니다." }
        val rawPayload = JSONObject(payloadText)
        val payload = when {
            format == BACKUP_FORMAT && rawPayload.getInt("schemaVersion") == USER_DB_VERSION -> rawPayload
            format == SCHEMA_2_BACKUP_FORMAT && rawPayload.getInt("schemaVersion") == 2 ->
                migrateSchema2Backup(rawPayload)
            format == LEGACY_BACKUP_FORMAT && rawPayload.getInt("schemaVersion") == 1 ->
                migrateSchema2Backup(migrateLegacyBackup(rawPayload))
            else -> throw IllegalArgumentException("지원하지 않는 사용자 DB 버전입니다.")
        }

        val attempts = payload.getJSONArray("attempts")
        val bookmarks = payload.getJSONArray("bookmarks")
        val wrongQueue = payload.getJSONArray("wrongQueue")
        val elementProgress = payload.getJSONArray("elementProgress")
        val settings = payload.getJSONArray("settings")
        requireBackupRowCounts(
            BackupRowCounts(
                attempts = attempts.length(),
                bookmarks = bookmarks.length(),
                wrongQueue = wrongQueue.length(),
                elementProgress = elementProgress.length(),
                settings = settings.length(),
            )
        )

        val db = helper.writableDatabase
        db.beginTransaction()
        try {
            val mappings = listOf(
                Triple("attempts", attempts, ATTEMPT_COLUMNS),
                Triple("bookmarks", bookmarks, BOOKMARK_COLUMNS),
                Triple("wrong_queue", wrongQueue, WRONG_QUEUE_COLUMNS),
                Triple("element_progress", elementProgress, PROGRESS_COLUMNS),
                Triple("settings", settings, SETTING_COLUMNS),
            )
            mappings.forEach { (table, rows, allowedColumns) ->
                db.delete(table, null, null)
                for (index in 0 until rows.length()) {
                    val row = rows.getJSONObject(index)
                    require(row.keys().asSequence().toSet() == allowedColumns) {
                        "$table 백업의 열 구성이 현재 schema와 다릅니다."
                    }
                    validateBackupRow(table, row)
                    val values = ContentValues()
                    row.keys().forEach { key ->
                        // Never trust a serialized FK merely because the target ID exists. Rebuild
                        // it from the complete semantic identity after all rows have been loaded.
                        if (table == "wrong_queue" && key == "last_attempt_id") {
                            values.putNull(key)
                        } else {
                            when (val value = row.get(key)) {
                                is Int -> values.put(key, value)
                                is Long -> values.put(key, value)
                                is Number -> values.put(key, value.toLong())
                                JSONObject.NULL -> values.putNull(key)
                                else -> values.put(key, value.toString())
                            }
                        }
                    }
                    db.insertOrThrow(table, null, values)
                }
            }
            maintainBoundedUserHistory(db)
            requireBackupRowCounts(backupRowCounts(db))
            db.setTransactionSuccessful()
        } finally {
            db.endTransaction()
        }
    }

    private fun migrateLegacyBackup(payload: JSONObject): JSONObject {
        val attempts = payload.getJSONArray("attempts")
        val attemptPresentations = mutableMapOf<String, Pair<QuizMode, String>>()
        for (index in 0 until attempts.length()) {
            val row = attempts.getJSONObject(index)
            require(row.keys().asSequence().toSet() == LEGACY_ATTEMPT_COLUMNS) {
                "구버전 attempts 백업의 열 구성이 올바르지 않습니다."
            }
            val elementId = row.getString("element_id")
            val mode = QuizMode.valueOf(row.getString("mode"))
            val normalized = QuizTemplateIdentity.normalizeLegacy(elementId, mode, row.getString("template_id"))
            row.put("template_id", normalized.id)
            row.put("presentation", normalized.presentation.name)
            attemptPresentations[row.getString("instance_id")] = mode to normalized.presentation.name
        }

        val bookmarks = payload.getJSONArray("bookmarks")
        for (index in 0 until bookmarks.length()) {
            val row = bookmarks.getJSONObject(index)
            require(row.keys().asSequence().toSet() == SCHEMA_2_BOOKMARK_COLUMNS) {
                "구버전 bookmarks 백업의 열 구성이 올바르지 않습니다."
            }
            val elementId = row.getString("element_id")
            val mode = QuizMode.valueOf(row.getString("mode"))
            val normalized = QuizTemplateIdentity.normalizeLegacy(elementId, mode, row.getString("template_id"))
            row.put("template_id", normalized.id)
            val snapshot = JSONObject(row.getString("snapshot_json"))
            snapshot.put("presentation", normalized.presentation.name)
            row.put("snapshot_json", snapshot.toString())
        }

        val migratingWrong = mutableListOf<MigratingWrongRow>()
        val legacyWrong = payload.getJSONArray("wrongQueue")
        for (index in 0 until legacyWrong.length()) {
            val row = legacyWrong.getJSONObject(index)
            require(row.keys().asSequence().toSet() == LEGACY_WRONG_QUEUE_COLUMNS) {
                "구버전 wrong_queue 백업의 열 구성이 올바르지 않습니다."
            }
            val elementId = row.getString("element_id")
            val lastInstanceId = row.getString("last_instance_id")
            val mode = attemptPresentations[lastInstanceId]?.first
                ?: inferLegacyQuizMode(elementId, row.getString("template_id"))
            val normalized = QuizTemplateIdentity.normalizeLegacy(elementId, mode, row.getString("template_id"))
            migratingWrong += MigratingWrongRow(
                elementId = elementId,
                templateId = normalized.id,
                mode = mode.name,
                presentation = normalized.presentation.name,
                lastInstanceId = lastInstanceId,
                lastSeed = row.getLong("last_seed"),
                correctStreak = row.getInt("correct_streak"),
                resolved = row.getInt("resolved"),
                updatedAt = row.getLong("updated_at"),
            )
        }
        payload.put("wrongQueue", JSONArray().apply {
            mergeMigratingWrongRows(migratingWrong).forEach { row ->
                put(JSONObject().apply {
                    put("element_id", row.elementId)
                    put("template_id", row.templateId)
                    put("mode", row.mode)
                    put("presentation", row.presentation)
                    put("last_instance_id", row.lastInstanceId)
                    put("last_seed", row.lastSeed)
                    put("correct_streak", row.correctStreak)
                    put("resolved", row.resolved)
                    put("updated_at", row.updatedAt)
                })
            }
        })
        payload.put("schemaVersion", 2)
        return payload
    }

    /** Adds schema-3 retention metadata after any schema-1 identity normalization has completed. */
    private fun migrateSchema2Backup(payload: JSONObject): JSONObject {
        val attemptsJson = payload.getJSONArray("attempts")
        val migratingAttempts = buildList {
            for (index in 0 until attemptsJson.length()) {
                val row = attemptsJson.getJSONObject(index)
                require(row.keys().asSequence().toSet() == ATTEMPT_COLUMNS) {
                    "schema 2 attempts 백업의 열 구성이 올바르지 않습니다."
                }
                add(
                    MigratingAttemptRow(
                        id = row.getLong("id"),
                        instanceId = row.getString("instance_id"),
                        elementId = row.getString("element_id"),
                        templateId = row.getString("template_id"),
                        correct = row.getInt("is_correct") == 1,
                        createdAt = row.getLong("created_at"),
                    )
                )
            }
        }
        val latestWrongAttemptIds = latestMigratingWrongAttemptIds(migratingAttempts)

        val bookmarks = payload.getJSONArray("bookmarks")
        for (index in 0 until bookmarks.length()) {
            val row = bookmarks.getJSONObject(index)
            require(row.keys().asSequence().toSet() == SCHEMA_2_BOOKMARK_COLUMNS) {
                "schema 2 bookmarks 백업의 열 구성이 올바르지 않습니다."
            }
            row.put("origin", BookmarkOrigin.MANUAL.name)
        }

        val wrongQueue = payload.getJSONArray("wrongQueue")
        for (index in 0 until wrongQueue.length()) {
            val row = wrongQueue.getJSONObject(index)
            require(row.keys().asSequence().toSet() == SCHEMA_2_WRONG_QUEUE_COLUMNS) {
                "schema 2 wrong_queue 백업의 열 구성이 올바르지 않습니다."
            }
            val attemptId = latestWrongAttemptIds[Triple(
                row.getString("element_id"),
                row.getString("template_id"),
                row.getString("last_instance_id"),
            )]
            row.put("last_attempt_id", attemptId ?: JSONObject.NULL)
        }
        payload.put("schemaVersion", USER_DB_VERSION)
        return payload
    }

    private fun validateBackupRow(table: String, row: JSONObject) {
        when (table) {
            "attempts" -> {
                row.requiredLong("id", 1)
                row.requiredText("instance_id", 160)
                row.requireElementId()
                row.requiredText("template_id", 512)
                QuizMode.valueOf(row.requiredText("mode", 32))
                QuizPresentation.valueOf(row.requiredText("presentation", 32))
                row.requiredLong("seed")
                row.requiredText("prompt", 200_000)
                row.requiredText("canonical_answer", 50_000)
                row.requiredText("user_answer", 50_000, allowBlank = true)
                require(row.requiredInt("is_correct", 0) in 0..1) { "is_correct 값이 올바르지 않습니다." }
                val explanation = JSONArray(row.requiredText("explanation_json", 500_000))
                require(explanation.length() in 1..20) { "해설 단계 수가 올바르지 않습니다." }
                for (index in 0 until explanation.length()) {
                    require(explanation.get(index) is String) { "해설 항목이 문자열이 아닙니다." }
                }
                row.requiredLong("elapsed_ms", 0)
                row.requiredLong("created_at", 0)
            }
            "bookmarks" -> {
                val instanceId = row.requiredText("instance_id", 160)
                val elementId = row.requireElementId()
                row.requiredText("template_id", 512)
                val mode = QuizMode.valueOf(row.requiredText("mode", 32))
                row.requiredLong("seed")
                val snapshot = JSONObject(row.requiredText("snapshot_json", 1_000_000))
                require(snapshot.getString("instanceId") == instanceId) { "북마크 instance ID가 snapshot과 다릅니다." }
                require(snapshot.getString("elementId") == elementId) { "북마크 element ID가 snapshot과 다릅니다." }
                require(snapshot.getString("mode") == mode.name) { "북마크 mode가 snapshot과 다릅니다." }
                QuizPresentation.valueOf(snapshot.getString("presentation"))
                row.requiredLong("created_at", 0)
                BookmarkOrigin.valueOf(row.requiredText("origin", 32))
            }
            "wrong_queue" -> {
                row.requireElementId()
                row.requiredText("template_id", 512)
                QuizMode.valueOf(row.requiredText("mode", 32))
                QuizPresentation.valueOf(row.requiredText("presentation", 32))
                row.requiredText("last_instance_id", 160)
                if (!row.isNull("last_attempt_id")) row.requiredLong("last_attempt_id", 1)
                row.requiredLong("last_seed")
                row.requiredInt("correct_streak", 0)
                require(row.requiredInt("resolved", 0) in 0..1) { "resolved 값이 올바르지 않습니다." }
                row.requiredLong("updated_at", 0)
            }
            "element_progress" -> {
                row.requireElementId()
                val attempts = row.requiredInt("attempts", 0)
                val correct = row.requiredInt("correct", 0)
                val streak = row.requiredInt("current_streak", 0)
                require(correct <= attempts && streak <= attempts) { "진도 집계가 서로 일치하지 않습니다." }
                row.requiredLong("last_attempt_at", 0)
            }
            "settings" -> {
                row.requiredText("key", 100)
                row.requiredText("value", 10_000, allowBlank = true)
            }
            else -> throw IllegalArgumentException("알 수 없는 백업 테이블입니다.")
        }
    }

    private fun attempts(sql: String, args: Array<String>): List<AttemptRecord> = buildList {
        helper.readableDatabase.rawQuery(sql, args).use { cursor ->
            while (cursor.moveToNext()) add(
                AttemptRecord(
                    id = cursor.getLong(0),
                    instanceId = cursor.getString(1),
                    elementId = cursor.getString(2),
                    templateId = cursor.getString(3),
                    mode = cursor.getString(4),
                    seed = cursor.getLong(5),
                    prompt = cursor.getString(6),
                    canonicalAnswer = cursor.getString(7),
                    userAnswer = cursor.getString(8),
                    correct = cursor.getInt(9) == 1,
                    explanation = JSONArray(cursor.getString(10)).let { array ->
                        List(array.length()) { array.getString(it) }
                    },
                    elapsedMs = cursor.getLong(11),
                    createdAt = cursor.getLong(12),
                )
            )
        }
    }

    private fun tableAsJson(db: SQLiteDatabase, table: String): JSONArray {
        val result = JSONArray()
        db.rawQuery("SELECT * FROM $table", null).use { cursor ->
            while (cursor.moveToNext()) {
                val row = JSONObject()
                for (column in cursor.columnNames.indices) {
                    when (cursor.getType(column)) {
                        android.database.Cursor.FIELD_TYPE_NULL -> row.put(cursor.columnNames[column], JSONObject.NULL)
                        android.database.Cursor.FIELD_TYPE_INTEGER -> row.put(cursor.columnNames[column], cursor.getLong(column))
                        android.database.Cursor.FIELD_TYPE_FLOAT -> row.put(cursor.columnNames[column], cursor.getDouble(column))
                        else -> row.put(cursor.columnNames[column], cursor.getString(column))
                    }
                }
                result.put(row)
            }
        }
        return result
    }

    private fun sha256(bytes: ByteArray): String = MessageDigest.getInstance("SHA-256")
        .digest(bytes).joinToString("") { "%02x".format(it) }

    fun close() = helper.close()
}

private inline fun <T> SQLiteDatabase.inTransaction(block: () -> T): T {
    beginTransaction()
    return try {
        val result = block()
        setTransactionSuccessful()
        result
    } finally {
        endTransaction()
    }
}

private fun InputStream.readWithLimit(maxBytes: Int): ByteArray {
    val output = ByteArrayOutputStream(minOf(maxBytes, 64 * 1024))
    val buffer = ByteArray(16 * 1024)
    var total = 0
    while (true) {
        val read = read(buffer)
        if (read < 0) break
        total += read
        require(total <= maxBytes) { "백업 파일이 ${maxBytes / (1024 * 1024)}MB 제한을 넘습니다." }
        output.write(buffer, 0, read)
    }
    return output.toByteArray()
}

internal data class MigratingWrongRow(
    val elementId: String,
    val templateId: String,
    val mode: String,
    val presentation: String,
    val lastInstanceId: String,
    val lastSeed: Long,
    val correctStreak: Int,
    val resolved: Int,
    val updatedAt: Long,
)

internal data class MigratingAttemptRow(
    val id: Long,
    val instanceId: String,
    val elementId: String,
    val templateId: String,
    val correct: Boolean,
    val createdAt: Long,
)

/** Resolves a schema-2 queue pointer without assuming instance IDs are globally unique. */
internal fun latestMigratingWrongAttemptId(
    attempts: List<MigratingAttemptRow>,
    elementId: String,
    templateId: String,
    instanceId: String,
): Long? = latestMigratingWrongAttemptIds(attempts)[Triple(elementId, templateId, instanceId)]

internal fun latestMigratingWrongAttemptIds(
    attempts: List<MigratingAttemptRow>,
): Map<Triple<String, String, String>, Long> {
    val latest = mutableMapOf<Triple<String, String, String>, MigratingAttemptRow>()
    attempts.forEach { candidate ->
        if (candidate.correct) return@forEach
        val key = Triple(candidate.elementId, candidate.templateId, candidate.instanceId)
        val previous = latest[key]
        if (previous == null || candidate.createdAt > previous.createdAt ||
            candidate.createdAt == previous.createdAt && candidate.id > previous.id
        ) {
            latest[key] = candidate
        }
    }
    return latest.mapValues { it.value.id }
}

internal data class WrongQueueRetentionRow(
    val elementId: String,
    val templateId: String,
    val mode: String,
    val presentation: String,
    val resolved: Boolean,
    val updatedAt: Long,
)

/**
 * Keeps one unresolved target per element/mode/presentation, so renderer-version churn cannot
 * grow the protected attempt set forever. Resolved rows are history only: keep the newest row per
 * element and then the newest bounded global sample.
 */
internal fun retainedWrongQueueKeys(
    rows: List<WrongQueueRetentionRow>,
    maxResolvedRows: Int = MAX_RESOLVED_WRONG_QUEUE_ROWS,
): Set<Pair<String, String>> {
    require(maxResolvedRows >= 0)
    val newest = compareBy<WrongQueueRetentionRow> { it.updatedAt }.thenBy { it.templateId }
    val unresolved = rows.asSequence()
        .filterNot { it.resolved }
        .groupBy { Triple(it.elementId, it.mode, it.presentation) }
        .values
        .map { candidates -> candidates.maxWith(newest) }
    val resolved = rows.asSequence()
        .filter { it.resolved }
        .groupBy { it.elementId }
        .values
        .map { candidates -> candidates.maxWith(newest) }
        .sortedWith(newest.reversed())
        .take(maxResolvedRows)
    return (unresolved + resolved).mapTo(mutableSetOf()) { it.elementId to it.templateId }
}

internal data class BackupRowCounts(
    val attempts: Int,
    val bookmarks: Int,
    val wrongQueue: Int,
    val elementProgress: Int,
    val settings: Int,
)

/** The exact same bounded row policy is applied before export and before import. */
internal fun requireBackupRowCounts(counts: BackupRowCounts) {
    require(counts.attempts <= MAX_ATTEMPTS) { "시도 기록이 허용량을 넘습니다." }
    require(counts.bookmarks <= MAX_BOOKMARKS) { "북마크가 허용량을 넘습니다." }
    require(counts.wrongQueue <= MAX_WRONG_QUEUE) { "오답 큐가 허용량을 넘습니다." }
    require(counts.elementProgress <= MAX_PROGRESS_ROWS) { "진도 행이 허용량을 넘습니다." }
    require(counts.settings <= MAX_SETTINGS) { "설정 행이 허용량을 넘습니다." }
}

/** Conservatively merges schema-1 rows whose session-specific IDs now share one template ID. */
internal fun mergeMigratingWrongRows(rows: List<MigratingWrongRow>): List<MigratingWrongRow> =
    rows.groupBy { it.elementId to it.templateId }.values.map { candidates ->
        val unresolved = candidates.filter { it.resolved == 0 }
        val basis = (unresolved.ifEmpty { candidates }).maxBy { it.updatedAt }
        if (unresolved.isEmpty()) {
            basis.copy(correctStreak = candidates.maxOf { it.correctStreak }, resolved = 1)
        } else {
            basis.copy(correctStreak = unresolved.minOf { it.correctStreak }, resolved = 0)
        }
    }

private val ELEMENT_ID_PATTERN = Regex("^(ACC|CF|INV|FI|DER|EQV|IBT)-\\d{2}$")

private fun JSONObject.requiredText(key: String, maxLength: Int, allowBlank: Boolean = false): String {
    val value = get(key)
    require(value is String && value.length <= maxLength && (allowBlank || value.isNotBlank())) {
        "$key 값이 올바른 문자열이 아닙니다."
    }
    return value
}

private fun JSONObject.requiredLong(key: String, minimum: Long = Long.MIN_VALUE): Long {
    val value = get(key)
    val number = when (value) {
        is Byte, is Short, is Int, is Long -> (value as Number).toLong()
        is Float -> value.toDouble().also { require(it.isFinite() && it % 1.0 == 0.0) }.toLong()
        is Double -> value.also { require(it.isFinite() && it % 1.0 == 0.0) }.toLong()
        else -> throw IllegalArgumentException("$key 값이 정수가 아닙니다.")
    }
    require(number >= minimum) { "$key 값이 허용 범위를 벗어납니다." }
    return number
}

private fun JSONObject.requiredInt(key: String, minimum: Int = Int.MIN_VALUE): Int {
    val value = requiredLong(key, minimum.toLong())
    require(value <= Int.MAX_VALUE) { "$key 값이 너무 큽니다." }
    return value.toInt()
}

private fun JSONObject.requireElementId(key: String = "element_id"): String =
    requiredText(key, 8).also { require(ELEMENT_ID_PATTERN.matches(it)) { "$key 형식이 올바르지 않습니다." } }

private fun inferLegacyQuizMode(elementId: String, templateId: String): QuizMode =
    QuizMode.entries.firstOrNull { mode ->
        templateId.startsWith("$elementId-${mode.name.lowercase()}-")
    } ?: throw IllegalArgumentException("구버전 template ID에서 문제 유형을 확인할 수 없습니다.")

private fun preservePreMigrationDatabase(context: Context) {
    val source = context.getDatabasePath(USER_DB_NAME)
    if (!source.isFile) return
    val sourceVersion = inspectUserDatabase(source, SQLiteDatabase.OPEN_READWRITE)
    if (sourceVersion !in 1 until USER_DB_VERSION) return

    val backup = File(source.parentFile, "$USER_DB_NAME.pre-schema-$sourceVersion.bak")
    val temporary = File(source.parentFile, ".${backup.name}.${android.os.Process.myPid()}.tmp")
    try {
        source.inputStream().use { input ->
            FileOutputStream(temporary).use { output ->
                input.copyTo(output)
                output.flush()
                output.fd.sync()
            }
        }
        require(inspectUserDatabase(temporary, SQLiteDatabase.OPEN_READONLY) == sourceVersion) {
            "마이그레이션 전 사용자 DB 복사본의 version이 다릅니다."
        }
        try {
            Files.move(
                temporary.toPath(),
                backup.toPath(),
                StandardCopyOption.ATOMIC_MOVE,
                StandardCopyOption.REPLACE_EXISTING,
            )
        } catch (_: java.nio.file.AtomicMoveNotSupportedException) {
            Files.move(temporary.toPath(), backup.toPath(), StandardCopyOption.REPLACE_EXISTING)
        }
    } finally {
        Files.deleteIfExists(temporary.toPath())
    }
}

private fun inspectUserDatabase(file: File, flags: Int): Int =
    SQLiteDatabase.openDatabase(file.absolutePath, null, flags).use { database ->
        val version = database.rawQuery("PRAGMA user_version", null).use { cursor ->
            require(cursor.moveToFirst()) { "사용자 DB version을 읽지 못했습니다." }
            cursor.getInt(0)
        }
        val integrity = database.rawQuery("PRAGMA integrity_check", null).use { cursor ->
            require(cursor.moveToFirst()) { "사용자 DB 무결성 결과를 읽지 못했습니다." }
            cursor.getString(0)
        }
        require(integrity == "ok") { "사용자 DB integrity_check가 실패했습니다: $integrity" }
        version
    }

private fun deletePreMigrationDatabases(context: Context) {
    val databaseFile = context.getDatabasePath(USER_DB_NAME)
    for (version in 1 until USER_DB_VERSION) {
        Files.deleteIfExists(File(databaseFile.parentFile, "$USER_DB_NAME.pre-schema-$version.bak").toPath())
    }
}

private fun rowCount(db: SQLiteDatabase, table: String): Int {
    require(table in USER_DATA_TABLES) { "지원하지 않는 사용자 데이터 테이블입니다." }
    return db.rawQuery("SELECT COUNT(*) FROM $table", null).use { cursor ->
        check(cursor.moveToFirst()) { "사용자 데이터 행 수를 읽지 못했습니다." }
        val count = cursor.getLong(0)
        require(count <= Int.MAX_VALUE) { "$table 행 수가 처리 가능한 범위를 넘습니다." }
        count.toInt()
    }
}

private fun requireTableRowsAtMost(
    db: SQLiteDatabase,
    table: String,
    maxRows: Int,
    errorMessage: String,
) {
    require(rowCount(db, table) <= maxRows) { errorMessage }
}

private fun requireCanInsertKeyedRow(
    db: SQLiteDatabase,
    table: String,
    keyColumn: String,
    key: String,
    maxRows: Int,
    errorMessage: String,
) {
    require(table to keyColumn in USER_KEYED_TABLES) { "지원하지 않는 사용자 데이터 키입니다." }
    val exists = db.rawQuery(
        "SELECT 1 FROM $table WHERE $keyColumn = ? LIMIT 1",
        arrayOf(key),
    ).use { it.moveToFirst() }
    if (!exists) require(rowCount(db, table) < maxRows) { errorMessage }
}

private fun backupRowCounts(db: SQLiteDatabase): BackupRowCounts = BackupRowCounts(
    attempts = rowCount(db, "attempts"),
    bookmarks = rowCount(db, "bookmarks"),
    wrongQueue = rowCount(db, "wrong_queue"),
    elementProgress = rowCount(db, "element_progress"),
    settings = rowCount(db, "settings"),
)

/**
 * Serialized queue pointers are only hints. Reconnect each one to the newest detailed wrong row
 * that matches every identity field; a missing or mismatched target deliberately becomes NULL.
 */
private fun reconnectWrongQueueAttemptPointers(db: SQLiteDatabase) {
    db.execSQL(
        """UPDATE wrong_queue
           SET last_attempt_id = (
               SELECT a.id FROM attempts a
               WHERE a.element_id = wrong_queue.element_id
                 AND a.template_id = wrong_queue.template_id
                 AND a.instance_id = wrong_queue.last_instance_id
                 AND a.is_correct = 0
               ORDER BY a.created_at DESC, a.id DESC
               LIMIT 1
           )""".trimIndent()
    )
}

/**
 * Renderer/template revisions must not pin detailed attempts forever. Keep the newest unresolved
 * row for each semantic learning target (element + mode + presentation). Resolved rows are history
 * only, so retain at most one per element and a bounded global sample.
 */
private fun cleanupWrongQueue(db: SQLiteDatabase) {
    val rows = buildList {
        db.rawQuery(
            "SELECT element_id, template_id, mode, presentation, resolved, updated_at FROM wrong_queue",
            null,
        ).use { cursor ->
            while (cursor.moveToNext()) {
                add(
                    WrongQueueRetentionRow(
                        elementId = cursor.getString(0),
                        templateId = cursor.getString(1),
                        mode = cursor.getString(2),
                        presentation = cursor.getString(3),
                        resolved = cursor.getInt(4) == 1,
                        updatedAt = cursor.getLong(5),
                    )
                )
            }
        }
    }
    val retainedKeys = retainedWrongQueueKeys(rows)
    rows.asSequence()
        .filter { (it.elementId to it.templateId) !in retainedKeys }
        .forEach { row ->
            db.delete(
                "wrong_queue",
                "element_id = ? AND template_id = ?",
                arrayOf(row.elementId, row.templateId),
            )
        }
    requireTableRowsAtMost(db, "wrong_queue", MAX_WRONG_QUEUE, "오답 큐가 허용량을 넘습니다.")
}

private fun maintainBoundedUserHistory(db: SQLiteDatabase) {
    cleanupWrongQueue(db)
    reconnectWrongQueueAttemptPointers(db)
    pruneAllAttempts(db)
    pruneAllAutomaticBookmarks(db)
}

private fun pruneAttempts(db: SQLiteDatabase, elementId: String) {
    pruneElementAttempts(db, elementId)
    pruneGlobalAttempts(db)
}

private fun pruneElementAttempts(db: SQLiteDatabase, elementId: String) {
    val protectedCount = db.rawQuery(
        """SELECT COUNT(DISTINCT last_attempt_id) FROM wrong_queue
           WHERE element_id = ? AND resolved = 0 AND last_attempt_id IS NOT NULL""".trimIndent(),
        arrayOf(elementId),
    ).use { cursor ->
        check(cursor.moveToFirst())
        cursor.getInt(0)
    }
    require(protectedCount <= MAX_RECENT_ATTEMPTS_PER_ELEMENT) {
        "미해결 오답 상세 기록이 단원별 보존 한도를 넘습니다."
    }
    val recentNonProtectedToKeep = MAX_RECENT_ATTEMPTS_PER_ELEMENT - protectedCount
    db.execSQL(
        """DELETE FROM attempts
           WHERE id IN (
               SELECT a.id FROM attempts a
               WHERE a.element_id = ?
                 AND a.id NOT IN (
                     SELECT w.last_attempt_id FROM wrong_queue w
                     WHERE w.element_id = ? AND w.resolved = 0
                       AND w.last_attempt_id IS NOT NULL
                 )
               ORDER BY a.created_at DESC, a.id DESC
               LIMIT -1 OFFSET $recentNonProtectedToKeep
             )""".trimIndent(),
        arrayOf(elementId, elementId),
    )
}

private fun pruneGlobalAttempts(db: SQLiteDatabase) {
    val protectedCount = db.rawQuery(
        """SELECT COUNT(DISTINCT last_attempt_id) FROM wrong_queue
           WHERE resolved = 0 AND last_attempt_id IS NOT NULL""".trimIndent(),
        null,
    ).use { cursor ->
        check(cursor.moveToFirst())
        cursor.getInt(0)
    }
    require(protectedCount <= MAX_RECENT_ATTEMPTS_TOTAL) {
        "미해결 오답 상세 기록이 전체 보존 한도를 넘습니다."
    }
    val recentNonProtectedToKeep = MAX_RECENT_ATTEMPTS_TOTAL - protectedCount
    db.execSQL(
        """DELETE FROM attempts
           WHERE id IN (
               SELECT a.id FROM attempts a
               WHERE a.id NOT IN (
                   SELECT w.last_attempt_id FROM wrong_queue w
                   WHERE w.resolved = 0 AND w.last_attempt_id IS NOT NULL
               )
               ORDER BY a.created_at DESC, a.id DESC
               LIMIT -1 OFFSET $recentNonProtectedToKeep
             )""".trimIndent()
    )
}

private fun pruneAllAttempts(db: SQLiteDatabase) {
    val elementIds = buildList {
        db.rawQuery("SELECT DISTINCT element_id FROM attempts", null).use { cursor ->
            while (cursor.moveToNext()) add(cursor.getString(0))
        }
    }
    elementIds.forEach { pruneElementAttempts(db, it) }
    pruneGlobalAttempts(db)
}

private fun pruneAutomaticBookmarks(db: SQLiteDatabase, elementId: String) {
    db.execSQL(
        """DELETE FROM bookmarks
           WHERE instance_id IN (
               SELECT instance_id FROM bookmarks
               WHERE element_id = ? AND origin = '${BookmarkOrigin.AUTO_WRONG.name}'
               ORDER BY created_at DESC, rowid DESC
               LIMIT -1 OFFSET $MAX_AUTO_BOOKMARKS_PER_ELEMENT
           )""".trimIndent(),
        arrayOf(elementId),
    )
}

private fun pruneAllAutomaticBookmarks(db: SQLiteDatabase) {
    val elementIds = buildList {
        db.rawQuery(
            "SELECT DISTINCT element_id FROM bookmarks WHERE origin = ?",
            arrayOf(BookmarkOrigin.AUTO_WRONG.name),
        ).use { cursor ->
            while (cursor.moveToNext()) add(cursor.getString(0))
        }
    }
    elementIds.forEach { pruneAutomaticBookmarks(db, it) }
}

private fun createSchema3Indexes(db: SQLiteDatabase) {
    db.execSQL(
        "CREATE INDEX IF NOT EXISTS attempts_element_recent_idx " +
            "ON attempts(element_id, created_at DESC, id DESC)"
    )
    db.execSQL(
        "CREATE INDEX IF NOT EXISTS attempts_wrong_recent_idx " +
            "ON attempts(created_at DESC, id DESC) WHERE is_correct = 0"
    )
    db.execSQL(
        "CREATE INDEX IF NOT EXISTS attempts_wrong_element_recent_idx " +
            "ON attempts(element_id, created_at DESC, id DESC) WHERE is_correct = 0"
    )
    db.execSQL(
        "CREATE INDEX IF NOT EXISTS bookmarks_recent_idx " +
            "ON bookmarks(created_at DESC, instance_id DESC)"
    )
    db.execSQL(
        "CREATE INDEX IF NOT EXISTS bookmarks_element_recent_idx " +
            "ON bookmarks(element_id, created_at DESC, instance_id DESC)"
    )
    db.execSQL(
        "CREATE INDEX IF NOT EXISTS bookmarks_auto_element_recent_idx " +
            "ON bookmarks(element_id, created_at DESC, instance_id DESC) WHERE origin = 'AUTO_WRONG'"
    )
    db.execSQL(
        "CREATE INDEX IF NOT EXISTS wrong_queue_open_recent_idx " +
            "ON wrong_queue(updated_at DESC) WHERE resolved = 0"
    )
}

private class UserDatabase(context: Context) : SQLiteOpenHelper(
    context,
    USER_DB_NAME,
    null,
    USER_DB_VERSION,
) {
    override fun onConfigure(db: SQLiteDatabase) {
        db.setForeignKeyConstraintsEnabled(true)
        db.disableWriteAheadLogging()
    }

    override fun onCreate(db: SQLiteDatabase) {
        db.execSQL(
            """CREATE TABLE attempts(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                instance_id TEXT NOT NULL,
                element_id TEXT NOT NULL,
                template_id TEXT NOT NULL,
                mode TEXT NOT NULL,
                presentation TEXT NOT NULL,
                seed INTEGER NOT NULL,
                prompt TEXT NOT NULL,
                canonical_answer TEXT NOT NULL,
                user_answer TEXT NOT NULL,
                is_correct INTEGER NOT NULL CHECK(is_correct IN (0,1)),
                explanation_json TEXT NOT NULL,
                elapsed_ms INTEGER NOT NULL,
                created_at INTEGER NOT NULL
            )""".trimIndent()
        )
        db.execSQL(
            """CREATE TABLE bookmarks(
                instance_id TEXT PRIMARY KEY,
                element_id TEXT NOT NULL,
                template_id TEXT NOT NULL,
                mode TEXT NOT NULL,
                seed INTEGER NOT NULL,
                snapshot_json TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                origin TEXT NOT NULL DEFAULT 'MANUAL' CHECK(origin IN ('MANUAL','AUTO_WRONG'))
            )""".trimIndent()
        )
        db.execSQL(
            """CREATE TABLE wrong_queue(
                element_id TEXT NOT NULL,
                template_id TEXT NOT NULL,
                mode TEXT NOT NULL,
                presentation TEXT NOT NULL,
                last_instance_id TEXT NOT NULL,
                last_attempt_id INTEGER,
                last_seed INTEGER NOT NULL,
                correct_streak INTEGER NOT NULL DEFAULT 0,
                resolved INTEGER NOT NULL DEFAULT 0 CHECK(resolved IN (0,1)),
                updated_at INTEGER NOT NULL,
                PRIMARY KEY(element_id, template_id),
                FOREIGN KEY(last_attempt_id) REFERENCES attempts(id) ON DELETE SET NULL
            )""".trimIndent()
        )
        db.execSQL(
            """CREATE TABLE element_progress(
                element_id TEXT PRIMARY KEY,
                attempts INTEGER NOT NULL,
                correct INTEGER NOT NULL,
                current_streak INTEGER NOT NULL,
                last_attempt_at INTEGER NOT NULL
            )""".trimIndent()
        )
        db.execSQL("CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        createSchema3Indexes(db)
    }

    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {
        if (oldVersion < 2) migrateToSchema2(db)
        if (oldVersion < 3) migrateToSchema3(db)
    }

    private fun migrateToSchema2(db: SQLiteDatabase) {
        db.execSQL("ALTER TABLE attempts ADD COLUMN presentation TEXT NOT NULL DEFAULT 'STANDARD'")

        val attempts = mutableListOf<Array<String>>()
        db.rawQuery("SELECT id, element_id, mode, template_id FROM attempts", null).use { cursor ->
            while (cursor.moveToNext()) {
                attempts += arrayOf(
                    cursor.getLong(0).toString(), cursor.getString(1), cursor.getString(2), cursor.getString(3)
                )
            }
        }
        attempts.forEach { row ->
            val mode = runCatching { QuizMode.valueOf(row[2]) }.getOrDefault(QuizMode.CONCEPT)
            val normalized = QuizTemplateIdentity.normalizeLegacy(row[1], mode, row[3])
            db.update(
                "attempts",
                ContentValues().apply {
                    put("template_id", normalized.id)
                    put("presentation", normalized.presentation.name)
                },
                "id = ?",
                arrayOf(row[0]),
            )
        }

        val bookmarks = mutableListOf<Array<String>>()
        db.rawQuery("SELECT instance_id, element_id, mode, template_id, snapshot_json FROM bookmarks", null).use { cursor ->
            while (cursor.moveToNext()) {
                bookmarks += arrayOf(
                    cursor.getString(0), cursor.getString(1), cursor.getString(2), cursor.getString(3), cursor.getString(4)
                )
            }
        }
        bookmarks.forEach { row ->
            val mode = runCatching { QuizMode.valueOf(row[2]) }.getOrDefault(QuizMode.CONCEPT)
            val normalized = QuizTemplateIdentity.normalizeLegacy(row[1], mode, row[3])
            val snapshot = JSONObject(row[4]).apply {
                put("presentation", normalized.presentation.name)
            }
            db.update(
                "bookmarks",
                ContentValues().apply {
                    put("template_id", normalized.id)
                    put("snapshot_json", snapshot.toString())
                },
                "instance_id = ?",
                arrayOf(row[0]),
            )
        }

        db.execSQL(
            """CREATE TABLE wrong_queue_v2(
                element_id TEXT NOT NULL,
                template_id TEXT NOT NULL,
                mode TEXT NOT NULL,
                presentation TEXT NOT NULL,
                last_instance_id TEXT NOT NULL,
                last_seed INTEGER NOT NULL,
                correct_streak INTEGER NOT NULL DEFAULT 0,
                resolved INTEGER NOT NULL DEFAULT 0 CHECK(resolved IN (0,1)),
                updated_at INTEGER NOT NULL,
                PRIMARY KEY(element_id, template_id)
            )""".trimIndent()
        )
        db.rawQuery(
            """SELECT w.element_id, w.template_id, w.last_instance_id, w.last_seed,
                      w.correct_streak, w.resolved, w.updated_at,
                      COALESCE(a.mode, 'CONCEPT')
               FROM wrong_queue w
               LEFT JOIN attempts a ON a.instance_id = w.last_instance_id
               ORDER BY w.updated_at ASC""".trimIndent(),
            null,
        ).use { cursor ->
            while (cursor.moveToNext()) {
                val elementId = cursor.getString(0)
                val mode = runCatching { QuizMode.valueOf(cursor.getString(7)) }.getOrDefault(QuizMode.CONCEPT)
                val normalized = QuizTemplateIdentity.normalizeLegacy(elementId, mode, cursor.getString(1))
                val candidate = MigratingWrongRow(
                    elementId = elementId,
                    templateId = normalized.id,
                    mode = mode.name,
                    presentation = normalized.presentation.name,
                    lastInstanceId = cursor.getString(2),
                    lastSeed = cursor.getLong(3),
                    correctStreak = cursor.getInt(4),
                    resolved = cursor.getInt(5),
                    updatedAt = cursor.getLong(6),
                )
                val existing = db.rawQuery(
                    "SELECT mode, presentation, last_instance_id, last_seed, correct_streak, resolved, updated_at " +
                        "FROM wrong_queue_v2 WHERE element_id = ? AND template_id = ?",
                    arrayOf(elementId, normalized.id),
                ).use { previous ->
                    if (!previous.moveToFirst()) null else MigratingWrongRow(
                        elementId, normalized.id, previous.getString(0), previous.getString(1),
                        previous.getString(2), previous.getLong(3), previous.getInt(4),
                        previous.getInt(5), previous.getLong(6),
                    )
                }
                val merged = mergeMigratingWrongRows(listOfNotNull(existing, candidate)).single()
                db.insertWithOnConflict(
                    "wrong_queue_v2",
                    null,
                    ContentValues().apply {
                        put("element_id", merged.elementId)
                        put("template_id", merged.templateId)
                        put("mode", merged.mode)
                        put("presentation", merged.presentation)
                        put("last_instance_id", merged.lastInstanceId)
                        put("last_seed", merged.lastSeed)
                        put("correct_streak", merged.correctStreak)
                        put("resolved", merged.resolved)
                        put("updated_at", merged.updatedAt)
                    },
                    SQLiteDatabase.CONFLICT_REPLACE,
                )
            }
        }
        db.execSQL("DROP TABLE wrong_queue")
        db.execSQL("ALTER TABLE wrong_queue_v2 RENAME TO wrong_queue")
    }

    private fun migrateToSchema3(db: SQLiteDatabase) {
        db.execSQL(
            "ALTER TABLE bookmarks ADD COLUMN origin TEXT NOT NULL DEFAULT 'MANUAL' " +
                "CHECK(origin IN ('MANUAL','AUTO_WRONG'))"
        )
        db.execSQL(
            """CREATE TABLE wrong_queue_v3(
                element_id TEXT NOT NULL,
                template_id TEXT NOT NULL,
                mode TEXT NOT NULL,
                presentation TEXT NOT NULL,
                last_instance_id TEXT NOT NULL,
                last_attempt_id INTEGER,
                last_seed INTEGER NOT NULL,
                correct_streak INTEGER NOT NULL DEFAULT 0,
                resolved INTEGER NOT NULL DEFAULT 0 CHECK(resolved IN (0,1)),
                updated_at INTEGER NOT NULL,
                PRIMARY KEY(element_id, template_id),
                FOREIGN KEY(last_attempt_id) REFERENCES attempts(id) ON DELETE SET NULL
            )""".trimIndent()
        )
        db.execSQL(
            """INSERT INTO wrong_queue_v3(
                   element_id, template_id, mode, presentation, last_instance_id, last_attempt_id,
                   last_seed, correct_streak, resolved, updated_at
               )
               SELECT w.element_id, w.template_id, w.mode, w.presentation, w.last_instance_id,
                      (
                          SELECT a.id FROM attempts a
                          WHERE a.element_id = w.element_id
                            AND a.template_id = w.template_id
                            AND a.instance_id = w.last_instance_id
                            AND a.is_correct = 0
                          ORDER BY a.created_at DESC, a.id DESC
                          LIMIT 1
                      ),
                      w.last_seed, w.correct_streak, w.resolved, w.updated_at
               FROM wrong_queue w""".trimIndent()
        )
        db.execSQL("DROP TABLE wrong_queue")
        db.execSQL("ALTER TABLE wrong_queue_v3 RENAME TO wrong_queue")
        db.execSQL("DROP INDEX IF EXISTS attempts_element_idx")
        createSchema3Indexes(db)
        maintainBoundedUserHistory(db)
    }
}

private const val USER_DB_VERSION = 3
private const val USER_DB_NAME = "user.sqlite3"
private const val BACKUP_FORMAT = "findone-user-backup-v4"
private const val SCHEMA_2_BACKUP_FORMAT = "findone-user-backup-v3"
private const val LEGACY_BACKUP_FORMAT = "findone-user-backup-v2"
private const val MAX_BACKUP_BYTES = 25 * 1024 * 1024
private const val MAX_ATTEMPTS = 100_000
private const val MAX_BOOKMARKS = 10_000
private const val MAX_WRONG_QUEUE = 2_000
private const val MAX_PROGRESS_ROWS = 135
private const val MAX_SETTINGS = 100
private const val MAX_RECENT_ATTEMPTS_PER_ELEMENT = 20
private const val MAX_RECENT_ATTEMPTS_TOTAL = 2_000
private const val MAX_RECENT_WRONG_ROWS = 135
private const val MAX_RECENT_BOOKMARK_ROWS = 100
private const val MAX_AUTO_BOOKMARKS_PER_ELEMENT = 10
private const val MAX_RESOLVED_WRONG_QUEUE_ROWS = 135
private val USER_DATA_TABLES = setOf("attempts", "bookmarks", "wrong_queue", "element_progress", "settings")
private val USER_KEYED_TABLES = setOf("element_progress" to "element_id", "settings" to "key")
private val ATTEMPT_COLUMNS = setOf(
    "id", "instance_id", "element_id", "template_id", "mode", "presentation", "seed", "prompt",
    "canonical_answer", "user_answer", "is_correct", "explanation_json", "elapsed_ms", "created_at",
)
private val LEGACY_ATTEMPT_COLUMNS = ATTEMPT_COLUMNS - "presentation"
private val BOOKMARK_COLUMNS = setOf(
    "instance_id", "element_id", "template_id", "mode", "seed", "snapshot_json", "created_at", "origin",
)
private val SCHEMA_2_BOOKMARK_COLUMNS = BOOKMARK_COLUMNS - "origin"
private val WRONG_QUEUE_COLUMNS = setOf(
    "element_id", "template_id", "mode", "presentation", "last_instance_id", "last_attempt_id", "last_seed",
    "correct_streak", "resolved", "updated_at",
)
private val SCHEMA_2_WRONG_QUEUE_COLUMNS = WRONG_QUEUE_COLUMNS - "last_attempt_id"
private val LEGACY_WRONG_QUEUE_COLUMNS = SCHEMA_2_WRONG_QUEUE_COLUMNS - setOf("mode", "presentation")
private val PROGRESS_COLUMNS = setOf("element_id", "attempts", "correct", "current_streak", "last_attempt_at")
private val SETTING_COLUMNS = setOf("key", "value")
