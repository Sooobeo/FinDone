package com.findone.app.data

import org.junit.Assert.assertEquals
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

    private fun row(instance: String, streak: Int, resolved: Int, updated: Long) = MigratingWrongRow(
        elementId = "CF-07",
        templateId = "CF-07-concept-rquiz-engine-1.0.0-standard",
        mode = "CONCEPT",
        presentation = "STANDARD",
        lastInstanceId = instance,
        lastSeed = updated,
        correctStreak = streak,
        resolved = resolved,
        updatedAt = updated,
    )
}
