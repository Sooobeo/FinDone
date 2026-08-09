package com.findone.app.ui

import org.junit.Assert.assertEquals
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
    fun `converts inline formulas to code styled text without latex drawables`() {
        val input = "before \$x^2 + y_1\$ and \$\$\\frac{a}{b}\$\$ after"

        assertEquals(
            "before `x^2 + y_1` and `\\frac{a}{b}` after",
            deviceSafeMarkdown(input),
        )
    }

    @Test
    fun `converts delimiter only formulas to ordinary fenced code blocks`() {
        val input = "관계식\r\n\$\$\r\nx = \\frac{a}{b}\r\n\$\$\r\n설명"

        assertEquals(
            "관계식\r\n````text\r\nx = \\frac{a}{b}\r\n````\r\n설명",
            deviceSafeMarkdown(input),
        )
    }

    @Test
    fun `device safe conversion preserves formulas inside existing code`() {
        val dollar = '$'
        val input = "`${dollar}inline${dollar}`\n```text\n${dollar}${dollar}block${dollar}${dollar}\n```\n${dollar}live${dollar}"

        assertEquals(
            "`${dollar}inline${dollar}`\n```text\n${dollar}${dollar}block${dollar}${dollar}\n```\n`live`",
            deviceSafeMarkdown(input),
        )
    }
}
