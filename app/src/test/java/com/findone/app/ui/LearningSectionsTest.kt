package com.findone.app.ui

import org.junit.Assert.assertEquals
import org.junit.Test

class LearningSectionsTest {
    @Test
    fun `splits application types into accordion content`() {
        val sections = learningSections(
            """
            ### 유형 A · 현재가치

            미래 현금흐름을 오늘 가치로 바꿉니다.

            ### 유형 B · 미래가치

            오늘의 금액을 미래 시점으로 옮깁니다.
            """.trimIndent()
        )

        assertEquals(listOf("유형 A · 현재가치", "유형 B · 미래가치"), sections.map { it.title })
        assertEquals("미래 현금흐름을 오늘 가치로 바꿉니다.", sections.first().markdown)
    }

    @Test
    fun `keeps legacy unsectioned content available`() {
        assertEquals(
            listOf(LearningSection("기본 적용", "기존 설명")),
            learningSections("기존 설명"),
        )
    }
}
