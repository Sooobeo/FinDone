package com.findone.app.ui

import org.junit.Assert.assertEquals
import org.junit.Test

class MarkdownTextTest {
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
}
