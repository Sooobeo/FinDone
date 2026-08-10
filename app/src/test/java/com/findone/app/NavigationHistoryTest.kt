package com.findone.app

import org.junit.Assert.assertEquals
import org.junit.Test

class NavigationHistoryTest {
    @Test
    fun `restored history keeps valid tabs and existing elements only`() {
        val restored = listOf(
            "HOME",
            "NOT_A_ROUTE",
            "ELEMENT:",
            "ELEMENT:REMOVED",
            "ELEMENT:ACC-01",
            "GLOSSARY",
        )

        assertEquals(
            listOf("HOME", "ELEMENT:ACC-01", "GLOSSARY"),
            normalizeNavigationHistory(restored, setOf("ACC-01")),
        )
    }

    @Test
    fun `restored history removes adjacent duplicates without changing chronology`() {
        assertEquals(
            listOf("HOME", "STUDY", "HOME"),
            normalizeNavigationHistory(
                listOf("HOME", "HOME", "STUDY", "STUDY", "HOME"),
                emptySet(),
            ),
        )
    }

    @Test
    fun `restored history retains only the newest bounded routes`() {
        val restored = List(40) { index -> if (index % 2 == 0) "HOME" else "STUDY" }

        assertEquals(restored.takeLast(32), normalizeNavigationHistory(restored, emptySet()))
    }

    @Test
    fun `explicit home exit from quiz makes home the root`() {
        assertEquals(
            emptyList<String>(),
            navigationHistoryAfterQuizExitTo(
                listOf("HOME", "STUDY", "ELEMENT:ACC-01"),
                MainTab.HOME,
            ),
        )
    }

    @Test
    fun `explicit quiz setup exit removes duplicate setup routes but keeps its origin`() {
        assertEquals(
            listOf("HOME", "STUDY", "ELEMENT:ACC-01"),
            navigationHistoryAfterQuizExitTo(
                listOf("HOME", "STUDY", "ELEMENT:ACC-01", "QUIZ", "QUIZ"),
                MainTab.QUIZ,
            ),
        )
    }
}
