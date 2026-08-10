package com.findone.app.data

import java.sql.Connection
import java.sql.DriverManager
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test

class TextAnnotationMigrationTest {
    @Test
    fun `anchor builder stores quote offsets context and source fingerprint`() {
        val source = "prefix 선택 구절 suffix"
        val start = source.indexOf("선택")
        val anchor = buildLearningTextAnchor(
            sectionKey = " definition ",
            sourceText = source,
            startOffset = start,
            endOffset = start + "선택 구절".length,
            contextCharacters = 4,
        )

        assertEquals("definition", anchor.sectionKey)
        assertEquals("선택 구절", anchor.selectedText)
        assertEquals(source.substring(start - 4, start), anchor.prefixContext)
        assertEquals(source.substring(start + "선택 구절".length).take(4), anchor.suffixContext)
        assertEquals(start, anchor.startOffset)
        assertEquals(start + "선택 구절".length, anchor.endOffset)
        assertTrue(anchor.sourceHash?.matches(Regex("[0-9a-f]{64}")) == true)
    }

    @Test
    fun `annotation validation preserves exact quote but normalizes comment deletion`() {
        val anchor = LearningTextAnchor(
            sectionKey = "formula",
            selectedText = "  A = L + E  ",
            prefixContext = "관계식:",
            suffixContext = "입니다.",
            startOffset = 10,
            endOffset = 23,
        )

        val draft = normalizeTextAnnotationDraft(
            elementId = "ACC-01",
            anchor = anchor,
            style = TextAnnotationStyle.UNDERLINE,
            comment = "  자산 = 부채 + 자본  ",
        )

        assertEquals(anchor.selectedText, draft.anchor.selectedText)
        assertEquals("자산 = 부채 + 자본", draft.comment)
        assertNull(normalizeAnnotationComment(" \n\t "))
    }

    @Test
    fun `annotation validation rejects unstable or oversized anchors`() {
        assertThrows(IllegalArgumentException::class.java) {
            buildLearningTextAnchor("definition", "short", 1, 20)
        }
        assertThrows(IllegalArgumentException::class.java) {
            normalizeLearningTextAnchor(
                LearningTextAnchor("definition", "quote", "", "", 5, 5)
            )
        }
        assertThrows(IllegalArgumentException::class.java) {
            normalizeLearningTextAnchor(
                LearningTextAnchor("definition", "quote", "", "", 0, 5, "not-a-hash")
            )
        }
        assertThrows(IllegalArgumentException::class.java) {
            requireGlossaryTermId(" \u0000 ")
        }
    }

    @Test
    fun `schema 5 migration is additive and preserves every schema 4 user row`() {
        Class.forName("org.sqlite.JDBC")
        DriverManager.getConnection("jdbc:sqlite::memory:").use { connection ->
            createSchema4Fixture(connection)
            insertSchema4Sentinels(connection)

            schema5MigrationStatements().forEach { sql ->
                connection.createStatement().use { it.execute(sql) }
            }

            assertEquals("attempt-1", connection.scalarText("SELECT instance_id FROM attempts"))
            assertEquals("bookmark-1", connection.scalarText("SELECT instance_id FROM bookmarks"))
            assertEquals("ACC-01", connection.scalarText("SELECT element_id FROM wrong_queue"))
            assertEquals("ACC-01", connection.scalarText("SELECT element_id FROM element_progress"))
            assertEquals("기존 메모", connection.scalarText("SELECT title FROM concept_notes"))
            assertEquals("true", connection.scalarText("SELECT value FROM settings"))
            assertTrue(connection.hasTable("text_annotations"))
            assertTrue(connection.hasTable("glossary_term_state"))
            assertEquals("ok", connection.scalarText("PRAGMA integrity_check"))
        }
    }

    @Test
    fun `schema 5 statements accept both annotation styles comments and glossary state`() {
        Class.forName("org.sqlite.JDBC")
        DriverManager.getConnection("jdbc:sqlite::memory:").use { connection ->
            schema5MigrationStatements().forEach { sql ->
                connection.createStatement().use { it.execute(sql) }
            }
            connection.createStatement().use { statement ->
                statement.executeUpdate(
                    """INSERT INTO text_annotations(
                           element_id, section_key, selected_text, prefix_context, suffix_context,
                           start_offset, end_offset, source_hash, style, comment, created_at, updated_at
                       ) VALUES(
                           'ACC-01', 'definition', '자산', '총 ', '은', 2, 4, NULL,
                           'HIGHLIGHT', '재무상태표 항목', 10, 10
                       )""".trimIndent()
                )
                statement.executeUpdate(
                    """INSERT INTO text_annotations(
                           element_id, section_key, selected_text, prefix_context, suffix_context,
                           start_offset, end_offset, source_hash, style, comment, created_at, updated_at
                       ) VALUES(
                           'ACC-01', 'formula', 'A=L+E', '', '', 0, 5, NULL,
                           'UNDERLINE', NULL, 11, 12
                       )""".trimIndent()
                )
                statement.executeUpdate(
                    "INSERT INTO glossary_term_state VALUES('ACC-01:asset', 1, 1, 20)"
                )
            }

            assertEquals(2, connection.scalarInt("SELECT COUNT(*) FROM text_annotations"))
            assertEquals(1, connection.scalarInt("SELECT COUNT(*) FROM text_annotations WHERE comment IS NOT NULL"))
            assertEquals(1, connection.scalarInt("SELECT checked FROM glossary_term_state"))
            assertEquals(1, connection.scalarInt("SELECT bookmarked FROM glossary_term_state"))
        }
    }

    @Test
    fun `schema 5 migration contains no destructive statement`() {
        val normalized = schema5MigrationStatements().map { it.trim().uppercase() }

        assertEquals(5, normalized.size)
        assertTrue(normalized.all { it.startsWith("CREATE ") })
        assertFalse(
            normalized.any { sql ->
                listOf("DROP ", "DELETE ", "ALTER ", "UPDATE ", "INSERT ", "REPLACE ")
                    .any(sql::contains)
            }
        )
    }

    @Test
    fun `old backup imports preserve records introduced by newer schemas`() {
        assertTrue(backupFormatIncludesConceptNotes("findone-user-backup-v6"))
        assertTrue(backupFormatIncludesConceptNotes("findone-user-backup-v5"))
        assertFalse(backupFormatIncludesConceptNotes("findone-user-backup-v4"))
        assertTrue(backupFormatIncludesTextAnnotations("findone-user-backup-v6"))
        assertFalse(backupFormatIncludesTextAnnotations("findone-user-backup-v5"))
    }

    @Test
    fun `backup bounds include annotation and glossary state collections`() {
        requireBackupRowCounts(
            BackupRowCounts(
                attempts = 0,
                bookmarks = 0,
                wrongQueue = 0,
                elementProgress = 0,
                settings = 0,
                textAnnotations = 10_000,
                glossaryTermStates = 20_000,
            )
        )

        assertThrows(IllegalArgumentException::class.java) {
            requireBackupRowCounts(
                BackupRowCounts(0, 0, 0, 0, 0, textAnnotations = 10_001)
            )
        }
        assertThrows(IllegalArgumentException::class.java) {
            requireBackupRowCounts(
                BackupRowCounts(0, 0, 0, 0, 0, glossaryTermStates = 20_001)
            )
        }
    }

    private fun createSchema4Fixture(connection: Connection) {
        connection.createStatement().use { statement ->
            statement.execute("CREATE TABLE attempts(id INTEGER PRIMARY KEY, instance_id TEXT NOT NULL)")
            statement.execute("CREATE TABLE bookmarks(instance_id TEXT PRIMARY KEY)")
            statement.execute("CREATE TABLE wrong_queue(element_id TEXT PRIMARY KEY)")
            statement.execute("CREATE TABLE element_progress(element_id TEXT PRIMARY KEY)")
            statement.execute("CREATE TABLE concept_notes(id INTEGER PRIMARY KEY, title TEXT NOT NULL)")
            statement.execute("CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            statement.execute("PRAGMA user_version = 4")
        }
    }

    private fun insertSchema4Sentinels(connection: Connection) {
        connection.createStatement().use { statement ->
            statement.executeUpdate("INSERT INTO attempts VALUES(1, 'attempt-1')")
            statement.executeUpdate("INSERT INTO bookmarks VALUES('bookmark-1')")
            statement.executeUpdate("INSERT INTO wrong_queue VALUES('ACC-01')")
            statement.executeUpdate("INSERT INTO element_progress VALUES('ACC-01')")
            statement.executeUpdate("INSERT INTO concept_notes VALUES(1, '기존 메모')")
            statement.executeUpdate("INSERT INTO settings VALUES('auto_bookmark_wrong', 'true')")
        }
    }

    private fun Connection.scalarText(sql: String): String = createStatement().use { statement ->
        statement.executeQuery(sql).use { result ->
            check(result.next())
            result.getString(1)
        }
    }

    private fun Connection.scalarInt(sql: String): Int = createStatement().use { statement ->
        statement.executeQuery(sql).use { result ->
            check(result.next())
            result.getInt(1)
        }
    }

    private fun Connection.hasTable(name: String): Boolean = prepareStatement(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
    ).use { statement ->
        statement.setString(1, name)
        statement.executeQuery().use { it.next() }
    }
}
