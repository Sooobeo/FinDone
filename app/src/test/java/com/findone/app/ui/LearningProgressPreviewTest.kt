package com.findone.app.ui

import org.junit.Assert.assertEquals
import org.junit.Test

class LearningProgressPreviewTest {
    @Test
    fun `list summary is authored from the element identity instead of its body`() {
        assertEquals(
            "영업현금흐름: 현금흐름의 원인과 기업가치 영향을 판단하는 방법을 익힙니다.",
            learningElementSummary("CF", "영업현금흐름"),
        )
    }

    @Test
    fun `every curriculum domain has a concise learning purpose`() {
        assertEquals(
            7,
            listOf("ACC", "CF", "INV", "FI", "DER", "EQV", "IBT")
                .map { learningElementSummary(it, "테스트") }
                .distinct()
                .size,
        )
    }

    @Test
    fun `unknown domain and blank title still produce a complete sentence`() {
        assertEquals(
            "이 학습요소: 핵심 원리와 실무 적용 기준을 익힙니다.",
            learningElementSummary("NEW", "  "),
        )
    }
}
