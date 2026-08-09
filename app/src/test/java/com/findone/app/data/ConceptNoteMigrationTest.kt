package com.findone.app.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test

class ConceptNoteMigrationTest {
    @Test
    fun `note draft is scoped to one element and trims only outer whitespace`() {
        val draft = normalizeConceptNoteDraft(
            elementId = "CF-07",
            title = "  듀레이션 정리  ",
            body = "\n첫 줄\nhttps://example.com/reference\n",
        )

        assertEquals("CF-07", draft.elementId)
        assertEquals("듀레이션 정리", draft.title)
        assertEquals("첫 줄\nhttps://example.com/reference", draft.body)
    }

    @Test
    fun `note draft rejects invalid scope blank values and oversized input`() {
        assertThrows(IllegalArgumentException::class.java) {
            normalizeConceptNoteDraft("UNKNOWN-01", "제목", "내용")
        }
        assertThrows(IllegalArgumentException::class.java) {
            normalizeConceptNoteDraft("CF-07", "   ", "내용")
        }
        assertThrows(IllegalArgumentException::class.java) {
            normalizeConceptNoteDraft("CF-07", "제목", "\n\t")
        }
        assertThrows(IllegalArgumentException::class.java) {
            normalizeConceptNoteDraft("CF-07", "가".repeat(CONCEPT_NOTE_TITLE_MAX_LENGTH + 1), "내용")
        }
        assertThrows(IllegalArgumentException::class.java) {
            normalizeConceptNoteDraft("CF-07", "제목", "가".repeat(CONCEPT_NOTE_BODY_MAX_LENGTH + 1))
        }
    }

    @Test
    fun `schema 4 migration only creates the notes table and its index`() {
        val statements = schema4MigrationStatements()
        val normalized = statements.map { it.trim().uppercase() }

        assertEquals(2, statements.size)
        assertTrue(normalized.all { it.startsWith("CREATE ") })
        assertTrue(normalized.any { "CREATE TABLE IF NOT EXISTS CONCEPT_NOTES" in it })
        assertTrue(normalized.any { "CREATE INDEX IF NOT EXISTS CONCEPT_NOTES_ELEMENT_UPDATED_IDX" in it })
        assertFalse(
            normalized.any { sql ->
                listOf("DROP ", "DELETE ", "ALTER ", "UPDATE ", "INSERT ", "REPLACE ")
                    .any(sql::contains)
            }
        )
    }

    @Test
    fun `only schema 4 backup replaces personal notes`() {
        assertTrue(backupFormatIncludesConceptNotes("findone-user-backup-v5"))
        assertFalse(backupFormatIncludesConceptNotes("findone-user-backup-v4"))
        assertFalse(backupFormatIncludesConceptNotes("findone-user-backup-v3"))
        assertFalse(backupFormatIncludesConceptNotes("findone-user-backup-v2"))
    }

    @Test
    fun `note text budget counts UTF 8 bytes and rejects oversized totals`() {
        assertEquals(3L + 6L, conceptNoteUtf8Bytes("abc", "한글"))
        requireConceptNoteTextBudget(MAX_CONCEPT_NOTE_TEXT_BYTES)

        assertThrows(IllegalArgumentException::class.java) {
            requireConceptNoteTextBudget(MAX_CONCEPT_NOTE_TEXT_BYTES + 1)
        }
        assertThrows(IllegalArgumentException::class.java) {
            requireConceptNoteTextBudget(-1)
        }
    }
}
