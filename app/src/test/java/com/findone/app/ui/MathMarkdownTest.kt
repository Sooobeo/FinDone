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
            "\$\$\\mathrm{PV} = C1 / (r - g)\$\$",
            safeMathMarkdown("PV = C1 / (r - g)"),
        )
        assertEquals(
            "\$\$\\mathrm{ROE} = \\mathrm{margin} \\times \\mathrm{turnover} " +
                "\\times \\mathrm{multiplier}\$\$",
            safeMathMarkdown("ROE = margin × turnover × multiplier"),
        )
    }

    @Test
    fun `multi character scripts are braced without swallowing the next symbol`() {
        assertEquals(
            "\$\$\\mathrm{rho}_{\\mathrm{AB}}=r_{\\mathrm{As}}^{(1/n)}+p_sV_s\$\$",
            safeMathMarkdown("rho_AB=r_As^(1/n)+p_sV_s"),
        )
        assertEquals(
            "\$\$D_{\\mathrm{Mod}}=D_{\\mathrm{Base}}\$\$",
            safeMathMarkdown("D_Mod=D_Base"),
        )
    }

    @Test
    fun `prose labels stay readable while safe right hand sides render as math`() {
        assertEquals(
            "**Project FCF** = \$\$\\mathrm{OCF}-\\mathrm{Capex}-" +
                "\\Delta \\mathrm{NWC}\$\$",
            safeMathMarkdown("Project FCF=OCF-Capex-ΔNWC"),
        )
        assertEquals(
            "**Jensen α** = \$\$R_p-[R_f+\\beta _p(R_m-R_f)]\$\$",
            safeMathMarkdown("Jensen α=R_p-[R_f+β_p(R_m-R_f)]"),
        )
        assertEquals(
            "**Call payoff** = \$\$\\mathrm{position} \\times N \\times M \\times " +
                "\\max(\\mathrm{ST}-K,0)\$\$",
            safeMathMarkdown("Call payoff = position×N×M×max(ST-K,0)"),
        )
        assertEquals(
            "**Mid-year PV** = \$\$\\mathrm{FCF}_t/(1+r)^{(t-0.5)}\$\$",
            safeMathMarkdown("Mid-year PV=FCF_t/(1+r)^(t-0.5)"),
        )
    }

    @Test
    fun `colon labels split safely and an unsafe right hand side remains complete`() {
        assertEquals(
            "**민감도**: \$\$\\Delta \\mathrm{EV}=\\mathrm{EBITDA} \\times " +
                "\\Delta \\mathrm{Multiple}\$\$",
            safeMathMarkdown("민감도: ΔEV=EBITDA×ΔMultiple"),
        )
        assertEquals(
            "**설명**: `X=Y 일부 설명`",
            safeMathMarkdown("설명: X=Y 일부 설명"),
        )
    }

    @Test
    fun `upright identifiers preserve generated commands and known functions`() {
        assertEquals(
            "\$\$\\Delta \\mathrm{Price}=\\max(\\mathrm{FCF}," +
                "\\ln(\\mathrm{WACC}))+D_{\\mathrm{Mod}}\$\$",
            safeMathMarkdown("ΔPrice=max(FCF,ln(WACC))+D_Mod"),
        )
        assertEquals(
            "\$\$\\sigma =\\sqrt{\\sigma ^{2}}\$\$",
            safeMathMarkdown("σ=√σ²"),
        )
        assertEquals(
            "\$\$\\mathrm{SD}=\\sqrt{\\mathrm{Variance}}\$\$",
            safeMathMarkdown("SD=√Variance"),
        )
    }

    @Test
    fun `safe numeric substitution becomes latex markdown`() {
        assertEquals(
            "\$\$(1{,}000 - 800 + 20) \\times 100 / 1{,}000\$\$",
            safeMathMarkdown("(1,000 - 800 + 20) × 100 / 1,000"),
        )
        assertEquals("\$\$100\$\$", safeMathMarkdown("100"))
    }

    @Test
    fun `long formulas use delimiter only block math while short formulas stay inline`() {
        val longFormula = "X=1+2+3+4+5+6+7+8+9+10+11+12+13+14+15+16+17+18+19"

        assertEquals("\$\$\n$longFormula\n\$\$", safeMathMarkdown(longFormula))
        assertEquals("\$\$x+1\$\$", safeMathMarkdown("x+1"))
    }

    @Test
    fun `top level comparison commas split equations but preserve arguments and grouped digits`() {
        assertEquals(
            "- \$\$\\mathrm{Cov}(A,B)=X\$\$\n" +
                "- \$\$\\mathrm{rho}_{\\mathrm{AB}}=\\mathrm{Cov}(A,B)/(s_A s_B)\$\$\n" +
                "- \$\$-1 \\le \\mathrm{rho}_{\\mathrm{AB}} \\le 1\$\$.",
            safeMathMarkdown("Cov(A,B)=X, rho_AB=Cov(A,B)/(s_A s_B), -1≤rho_AB≤1."),
        )
        assertEquals(
            "\$\$X=\\max(A,B)+1{,}000\$\$",
            safeMathMarkdown("X=max(A,B)+1,000"),
        )
    }

    @Test
    fun `terminal sentence punctuation remains outside math`() {
        assertEquals(
            "**Project FCF** = \$\$\\mathrm{OCF}-\\mathrm{Capex}-" +
                "\\Delta \\mathrm{NWC}\$\$.",
            safeMathMarkdown("Project FCF=OCF-Capex-ΔNWC."),
        )
    }

    @Test
    fun `sentence boundaries split comparison clauses or fall back whole`() {
        assertEquals(
            "- \$\$X=Y\$\$.\n- \$\$A=B\$\$.",
            safeMathMarkdown("X=Y. A=B."),
        )
        assertEquals(
            "- \$\$X=Y\$\$.\n- `explanation`",
            safeMathMarkdown("X=Y. explanation"),
        )
    }

    @Test
    fun `signed scripts are braced and malformed scripts are rejected whole`() {
        assertEquals("\$\$x^{-2}\$\$", safeMathMarkdown("x^-2"))
        assertEquals("`x_=1`", safeMathMarkdown("x_=1"))
        assertEquals("`x_^2`", safeMathMarkdown("x_^2"))
    }

    @Test
    fun `only three digit groups use numeric comma spacing`() {
        assertEquals("\$\$X=1{,}234\$\$", safeMathMarkdown("X=1,234"))
        assertEquals("`X=1,2`", safeMathMarkdown("X=1,2"))
        assertEquals(
            "- \$\$X=1\$\$\n- \$\$Y=2\$\$",
            safeMathMarkdown("X=1,Y=2"),
        )
        assertEquals("\$\$X=\\max(1,2)\$\$", safeMathMarkdown("X=max(1,2)"))
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
