package com.findone.app.ui

import org.junit.Assert.assertEquals
import org.junit.Test

class MathMarkdownTest {
    @Test
    fun `complete existing math spans are preserved`() {
        assertEquals("\$PV = C_1 / (r - g)\$", safeMathMarkdown("\$PV = C_1 / (r - g)\$"))
        assertEquals("\$\$ROE = m \\times t\$\$", safeMathMarkdown("\$\$ROE = m \\times t\$\$"))
    }

    @Test
    fun `complete existing code spans are preserved`() {
        assertEquals("`현금 = 부채 + 자본`", safeMathMarkdown("`현금 = 부채 + 자본`"))
        assertEquals("``A ` B``", safeMathMarkdown("``A ` B``"))
    }

    @Test
    fun `safe symbolic formula becomes latex markdown`() {
        assertEquals(
            "\$\$PV = C1 / (r - g)\$\$",
            safeMathMarkdown("PV = C1 / (r - g)"),
        )
        assertEquals(
            "\$\$ROE = margin \\times turnover \\times multiplier\$\$",
            safeMathMarkdown("ROE = margin × turnover × multiplier"),
        )
    }

    @Test
    fun `multi character scripts are braced without swallowing the next symbol`() {
        assertEquals(
            "\$\$rho_{AB}=r_{As}^{(1/n)}+p_sV_s\$\$",
            safeMathMarkdown("rho_AB=r_As^(1/n)+p_sV_s"),
        )
    }

    @Test
    fun `safe numeric substitution becomes latex markdown`() {
        assertEquals(
            "\$\$(1,000 - 800 + 20) \\times 100 / 1,000\$\$",
            safeMathMarkdown("(1,000 - 800 + 20) × 100 / 1,000"),
        )
        assertEquals("\$\$100\$\$", safeMathMarkdown("100"))
    }

    @Test
    fun `unicode math operators are converted conservatively`() {
        assertEquals(
            "\$\$x \\le y \\approx z\\%\$\$",
            safeMathMarkdown("x ≤ y ≈ z%"),
        )
    }

    @Test
    fun `Korean or ampersand mixed relation falls back as one code span`() {
        assertEquals("`현금 = 부채 + 자본`", safeMathMarkdown("현금 = 부채 + 자본"))
        assertEquals("`A & B = C`", safeMathMarkdown("A & B = C"))
        assertEquals("`제시된 관계를 각 선택지와 대조합니다.`", safeMathMarkdown("제시된 관계를 각 선택지와 대조합니다."))
    }

    @Test
    fun `unbalanced or mismatched delimiters fall back without truncation`() {
        assertEquals("`PV = C1 / (r - g`", safeMathMarkdown("PV = C1 / (r - g"))
        assertEquals("`x = ([1 + 2)]`", safeMathMarkdown("x = ([1 + 2)]"))
        assertEquals("`price \$100`", safeMathMarkdown("price \$100"))
    }

    @Test
    fun `embedded and escaped backticks use a longer safe fence`() {
        assertEquals("``A `quoted` & B``", safeMathMarkdown("A `quoted` & B"))
        assertEquals("``A \\` B``", safeMathMarkdown("A \\` B"))
        assertEquals("```A `` B```", safeMathMarkdown("A `` B"))
    }

    @Test
    fun `blank input stays blank and outer whitespace is normalized`() {
        assertEquals("", safeMathMarkdown("  \t "))
        assertEquals("\$\$x + 1\$\$", safeMathMarkdown("  x + 1  "))
    }
}
