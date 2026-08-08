package com.findone.app.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertThrows
import org.junit.Test

class UserMigrationTest {
    @Test
    fun `unresolved legacy row survives a newer resolved track row`() {
        val unresolved = row(instance = "weak-wrong", streak = 0, resolved = 0, updated = 200)
        val newerResolved = row(instance = "domain-resolved", streak = 4, resolved = 1, updated = 300)

        val merged = mergeMigratingWrongRows(listOf(unresolved, newerResolved)).single()

        assertEquals(0, merged.resolved)
        assertEquals(0, merged.correctStreak)
        assertEquals("weak-wrong", merged.lastInstanceId)
        assertEquals(200L, merged.updatedAt)
    }

    @Test
    fun `multiple unresolved rows merge conservatively around latest wrong instance`() {
        val older = row(instance = "older", streak = 0, resolved = 0, updated = 100)
        val newer = row(instance = "newer", streak = 1, resolved = 0, updated = 250)

        val merged = mergeMigratingWrongRows(listOf(older, newer)).single()

        assertEquals(0, merged.resolved)
        assertEquals(0, merged.correctStreak)
        assertEquals("newer", merged.lastInstanceId)
        assertEquals(250L, merged.updatedAt)
    }

    @Test
    fun `all resolved legacy rows remain resolved`() {
        val first = row(instance = "first", streak = 2, resolved = 1, updated = 100)
        val second = row(instance = "second", streak = 5, resolved = 1, updated = 220)

        val merged = mergeMigratingWrongRows(listOf(first, second)).single()

        assertEquals(1, merged.resolved)
        assertEquals(5, merged.correctStreak)
        assertEquals("second", merged.lastInstanceId)
    }

    @Test
    fun `schema 2 queue pointer chooses latest matching wrong attempt deterministically`() {
        val attempts = listOf(
            attempt(id = 1, createdAt = 100),
            attempt(id = 2, createdAt = 200),
            attempt(id = 3, createdAt = 200),
            attempt(id = 4, createdAt = 300, correct = true),
            attempt(id = 5, createdAt = 400, elementId = "ACC-01"),
            attempt(id = 6, createdAt = 500, instanceId = "different-instance"),
        )

        val result = latestMigratingWrongAttemptId(
            attempts,
            elementId = "CF-07",
            templateId = TEMPLATE_ID,
            instanceId = "wrong-instance",
        )

        assertEquals(3L, result)
    }

    @Test
    fun `schema 2 queue pointer stays null when detailed wrong row is missing`() {
        val attempts = listOf(
            attempt(id = 1, createdAt = 100, correct = true),
            attempt(id = 2, createdAt = 200, templateId = "other-template"),
        )

        val result = latestMigratingWrongAttemptId(
            attempts,
            elementId = "CF-07",
            templateId = TEMPLATE_ID,
            instanceId = "wrong-instance",
        )

        assertNull(result)
    }

    @Test
    fun `queue retention keeps newest unresolved row for each semantic target`() {
        val retained = retainedWrongQueueKeys(
            listOf(
                retention(template = "concept-v1", updated = 100),
                retention(template = "concept-v2", updated = 200),
                retention(template = "oral-v1", presentation = "ORAL", updated = 150),
                retention(template = "calculation-v1", mode = "CALCULATION", updated = 175),
            ),
            maxResolvedRows = 0,
        )

        assertEquals(
            setOf(
                "CF-07" to "concept-v2",
                "CF-07" to "oral-v1",
                "CF-07" to "calculation-v1",
            ),
            retained,
        )
    }

    @Test
    fun `queue retention bounds resolved history after choosing newest row per element`() {
        val retained = retainedWrongQueueKeys(
            listOf(
                retention(element = "CF-07", template = "cf-old", resolved = true, updated = 100),
                retention(element = "CF-07", template = "cf-new", resolved = true, updated = 250),
                retention(element = "ACC-01", template = "acc", resolved = true, updated = 300),
                retention(element = "INV-02", template = "inv", resolved = true, updated = 200),
            ),
            maxResolvedRows = 2,
        )

        assertEquals(setOf("ACC-01" to "acc", "CF-07" to "cf-new"), retained)
    }

    @Test
    fun `backup row policy accepts exporter limits and rejects any oversized table`() {
        requireBackupRowCounts(
            BackupRowCounts(
                attempts = 100_000,
                bookmarks = 10_000,
                wrongQueue = 2_000,
                elementProgress = 135,
                settings = 100,
            )
        )

        assertThrows(IllegalArgumentException::class.java) {
            requireBackupRowCounts(BackupRowCounts(100_001, 0, 0, 0, 0))
        }
        assertThrows(IllegalArgumentException::class.java) {
            requireBackupRowCounts(BackupRowCounts(0, 10_001, 0, 0, 0))
        }
        assertThrows(IllegalArgumentException::class.java) {
            requireBackupRowCounts(BackupRowCounts(0, 0, 2_001, 0, 0))
        }
        assertThrows(IllegalArgumentException::class.java) {
            requireBackupRowCounts(BackupRowCounts(0, 0, 0, 136, 0))
        }
        assertThrows(IllegalArgumentException::class.java) {
            requireBackupRowCounts(BackupRowCounts(0, 0, 0, 0, 101))
        }
    }

    private fun row(instance: String, streak: Int, resolved: Int, updated: Long) = MigratingWrongRow(
        elementId = "CF-07",
        templateId = TEMPLATE_ID,
        mode = "CONCEPT",
        presentation = "STANDARD",
        lastInstanceId = instance,
        lastSeed = updated,
        correctStreak = streak,
        resolved = resolved,
        updatedAt = updated,
    )

    private fun attempt(
        id: Long,
        createdAt: Long,
        instanceId: String = "wrong-instance",
        elementId: String = "CF-07",
        templateId: String = TEMPLATE_ID,
        correct: Boolean = false,
    ) = MigratingAttemptRow(
        id = id,
        instanceId = instanceId,
        elementId = elementId,
        templateId = templateId,
        correct = correct,
        createdAt = createdAt,
    )

    private fun retention(
        element: String = "CF-07",
        template: String,
        mode: String = "CONCEPT",
        presentation: String = "STANDARD",
        resolved: Boolean = false,
        updated: Long,
    ) = WrongQueueRetentionRow(
        elementId = element,
        templateId = template,
        mode = mode,
        presentation = presentation,
        resolved = resolved,
        updatedAt = updated,
    )

    private companion object {
        const val TEMPLATE_ID = "CF-07-concept-rquiz-engine-1.0.0-standard"
    }
}
