package com.findone.app.ui

import com.findone.app.data.LearningTextAnchor
import com.findone.app.data.buildLearningTextAnchor
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class MarkdownAnnotationResolverTest {
    @Test
    fun `exact source hash restores the original selection`() {
        val text = "기업가치는 미래 현금흐름의 현재가치다."
        val start = text.indexOf("현재가치")
        val anchor = buildLearningTextAnchor("definition", text, start, start + 4)

        assertEquals(start until start + 4, resolveLearningAnnotationRange(text, anchor))
    }

    @Test
    fun `ambiguous repeated quote without matching context stays unresolved`() {
        val anchor = LearningTextAnchor(
            sectionKey = "definition",
            selectedText = "가치",
            prefixContext = "원래 앞 문맥",
            suffixContext = "원래 뒤 문맥",
            startOffset = 0,
            endOffset = 2,
        )

        assertNull(resolveLearningAnnotationRange("가치와 또 다른 가치", anchor))
    }

    @Test
    fun `imported stale end offset cannot extend beyond the exact quote`() {
        val anchor = LearningTextAnchor(
            sectionKey = "definition",
            selectedText = "가치",
            prefixContext = "",
            suffixContext = " 설명",
            startOffset = 0,
            endOffset = 20,
        )

        assertEquals(0 until 2, resolveLearningAnnotationRange("가치 설명", anchor))
    }
}
