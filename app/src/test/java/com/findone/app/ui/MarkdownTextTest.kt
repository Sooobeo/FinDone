package com.findone.app.ui

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class MarkdownTextTest {
    @Test
    fun `plain text fallback keeps learning content readable after renderer failure`() {
        assertEquals(
            "핵심 관계\n항목 자산 A = 부채 L + 자본 E.\n공식 문서, 링크",
            markdownPlainTextFallback(
                """
                ### 핵심 관계

                - 자산${'$'}${'$'}A${'$'}${'$'} = 부채${'$'}${'$'}L${'$'}${'$'} + 자본${'$'}${'$'}E${'$'}${'$'}.
                [공식 문서](https://example.com)
                """.trimIndent(),
            ),
        )
    }

    @Test
    fun `plain text fallback speaks braced latex without regex failures`() {
        assertEquals(
            "(a) 나누기 (b) 더하기 제곱근 (x) 의 2 승 아래첨자 i 값",
            markdownPlainTextFallback(
                "\$\$\\frac{a}{b} + \\sqrt{x}^{2}_{i} \\mathrm{값}\$\$",
            ),
        )
    }

    @Test
    fun `normalizes standard inline math and preserves native inline math`() {
        val input = "before \$x^2 + y_1\$ and \$\$\\frac{a}{b}\$\$ after"

        assertEquals(
            "before \$\$x^2 + y_1\$\$ and \$\$\\frac{a}{b}\$\$ after",
            normalizeInlineLatex(input),
        )
    }

    @Test
    fun `preserves delimiter-only block math and its body`() {
        val input = "text\r\n\$\$\r\nx = \$5 + 7\$\r\n\$\$\r\nafter \$z\$"

        assertEquals(
            "text\r\n\$\$\r\nx = \$5 + 7\$\r\n\$\$\r\nafter \$\$z\$\$",
            normalizeInlineLatex(input),
        )
    }

    @Test
    fun `does not normalize inline code spans of different delimiter lengths`() {
        val input = "`\$x\$` and ``code ` \$y\$`` and \$z\$"

        assertEquals(
            "`\$x\$` and ``code ` \$y\$`` and \$\$z\$\$",
            normalizeInlineLatex(input),
        )
    }

    @Test
    fun `preserves variable length inline code delimiter state across CRLF lines`() {
        val input = "before ``code\r\n\$x\$ and ` literal\r\nstill \$y\$`` after \$z\$\r\nlast \$w\$"

        assertEquals(
            "before ``code\r\n\$x\$ and ` literal\r\nstill \$y\$`` after \$\$z\$\$\r\nlast \$\$w\$\$",
            normalizeInlineLatex(input),
        )
    }

    @Test
    fun `does not normalize backtick or tilde fenced code`() {
        val dollar = '$'
        val input = """
            ````kotlin
            val formula = "${dollar}x${dollar}"
            ````
            ~~~text
            ${dollar}y${dollar}
            ~~~
            ${dollar}z${dollar}
        """.trimIndent()

        val expected = """
            ````kotlin
            val formula = "${dollar}x${dollar}"
            ````
            ~~~text
            ${dollar}y${dollar}
            ~~~
            ${dollar}${dollar}z${dollar}${dollar}
        """.trimIndent()

        assertEquals(expected, normalizeInlineLatex(input))
    }

    @Test
    fun `does not normalize four-column space or tab indented code lines`() {
        val input = "    \$x\$\r\n\t\$y\$\n  \t\$w\$\r\n   \$z\$"

        assertEquals(
            "    \$x\$\r\n\t\$y\$\n  \t\$w\$\r\n   \$\$z\$\$",
            normalizeInlineLatex(input),
        )
    }

    @Test
    fun `preserves escaped dollars and normalizes only the real formula`() {
        val input = "price \\${'$'}100, escaped \\${'$'}x\\${'$'}, formula \$x + 1\$"

        assertEquals(
            "price \\${'$'}100, escaped \\${'$'}x\\${'$'}, formula \$\$x + 1\$\$",
            normalizeInlineLatex(input),
        )
    }

    @Test
    fun `preserves malformed empty spaced and unclosed delimiters`() {
        val inputs = listOf(
            "empty \$\$ value",
            "spaced \$ x \$ value",
            "unclosed \$x + 1",
            "unclosed native \$\$x + 1",
        )

        inputs.forEach { input -> assertEquals(input, normalizeInlineLatex(input)) }
    }

    @Test
    fun `even backslashes do not accidentally escape a following formula delimiter`() {
        val input = "\\\\\$x\$"

        assertEquals("\\\\\$\$x\$\$", normalizeInlineLatex(input))
    }

    @Test
    fun `normalizes and bounds very long invalid latex fallback text`() {
        assertEquals("[invalid formula]", normalizedLatexFallbackText(" \r\n\t "))
        assertEquals("alpha beta", normalizedLatexFallbackText("  alpha\n\tbeta  "))
        assertEquals("😀😀😀…", normalizedLatexFallbackText("😀".repeat(10), maxCodePoints = 4))

        val longFallback = normalizedLatexFallbackText("x".repeat(10_000))
        assertEquals(512, longFallback.codePointCount(0, longFallback.length))
        assertTrue(longFallback.endsWith("…"))
    }

    @Test
    fun `caps invalid latex fallback intrinsic width to twenty em`() {
        assertEquals(40, boundedLatexFallbackWidthPx(39.2f, textSizePx = 16f))
        assertEquals(320, boundedLatexFallbackWidthPx(10_000f, textSizePx = 16f))
        assertEquals(320, boundedLatexFallbackWidthPx(Float.POSITIVE_INFINITY, textSizePx = 16f))
        assertEquals(1, boundedLatexFallbackWidthPx(0f, textSizePx = 16f))
    }
}
