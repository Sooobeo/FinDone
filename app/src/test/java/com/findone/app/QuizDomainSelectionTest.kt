package com.findone.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class QuizDomainSelectionTest {
    @Test
    fun `missing saved selection defaults to every available domain`() {
        assertEquals(
            linkedSetOf("ACC", "CF", "INV"),
            normalizeQuizDomainSelection(listOf("ACC", "CF", "INV"), restoredDomainIds = null),
        )
    }

    @Test
    fun `saved selection keeps stable available order and filters removed domains`() {
        assertEquals(
            linkedSetOf("CF", "INV"),
            normalizeQuizDomainSelection(
                availableDomainIds = listOf("ACC", "CF", "INV"),
                restoredDomainIds = listOf("REMOVED", "INV", "CF", "INV"),
            ),
        )
        assertTrue(
            normalizeQuizDomainSelection(
                availableDomainIds = listOf("ACC", "CF"),
                restoredDomainIds = emptyList(),
            ).isEmpty(),
        )
    }

    @Test
    fun `domain track uses multi selection while other tracks keep single-domain semantics`() {
        val multi = linkedSetOf("ACC", "CF")

        assertEquals(multi, quizDomainFilter(QuizTrack.DOMAIN, multi, singleDomainId = "INV"))
        assertEquals(setOf("INV"), quizDomainFilter(QuizTrack.WEAK, multi, singleDomainId = "INV"))
        assertNull(quizDomainFilter(QuizTrack.SPRINT, multi, singleDomainId = null))
    }
}
