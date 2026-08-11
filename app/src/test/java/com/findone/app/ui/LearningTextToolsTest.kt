package com.findone.app.ui

import com.findone.app.data.LearningTextAnchor
import com.findone.app.model.ContentElement
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.nio.file.Files
import java.nio.file.Path
import java.sql.DriverManager

class LearningTextToolsTest {
    @Test
    fun `extracts every distinct formula identifier and explains common variables`() {
        val variables = formulaVariables(
            element(
                formula = """
                    - Assets $$(A)$$ = liabilities $$(L)$$ + equity $$(E)$$
                    - $$\mathrm{Revenue}_{\mathrm{accrual}}=\mathrm{CashCollected}+\mathrm{AR}_{\mathrm{end}}$$
                """.trimIndent(),
            )
        )

        assertEquals(
            listOf("A", "L", "E", "Revenue_accrual", "CashCollected", "AR_end"),
            variables.map { it.symbol },
        )
        assertTrue(variables.all { it.meaning.isNotBlank() })
    }

    @Test
    fun `glossary ids are stable and content groups retain full element names`() {
        val element = element(
            formula = """**Accrual revenue**: ${'$'}${'$'}\mathrm{Revenue}_{\mathrm{accrual}}${'$'}${'$'}""",
        )
        val first = glossaryTerms(listOf(element))
        val second = glossaryTerms(listOf(element))

        assertEquals(first, second)
        assertTrue(first.any { it.term == element.title })
        assertTrue(first.any { it.term == "Accrual revenue" })
        assertTrue(first.any { it.term == "Revenue_accrual" })
        assertTrue(first.all { it.elementTitle == "Accrual and cash accounting" })
    }

    @Test
    fun `annotation anchor follows its surrounding context after a content edit`() {
        val anchor = LearningTextAnchor(
            sectionKey = "definition",
            selectedText = "현재가치",
            prefixContext = "기업가치는 미래 현금흐름의 ",
            suffixContext = "를 합산한 값이다.",
            startOffset = 2,
            endOffset = 6,
        )
        val edited = "용어 설명. 현재가치와 기업가치는 다르다. 기업가치는 미래 현금흐름의 현재가치를 합산한 값이다."

        val range = resolveLearningAnnotationRange(edited, anchor)

        assertEquals("현재가치", range?.let { edited.substring(it.first, it.last + 1) })
        assertTrue(range != null && range.first > edited.indexOf("현재가치"))
    }

    @Test
    fun `every packaged formula variable has a concrete financial meaning`() {
        val database = copyPackagedDatabaseToTemp()
        try {
            Class.forName("org.sqlite.JDBC")
            val generic = mutableListOf<String>()
            val leakedLabels = mutableListOf<String>()
            val emptyElements = mutableListOf<String>()
            var formulaCount = 0
            DriverManager.getConnection("jdbc:sqlite:${database.toAbsolutePath()}").use { connection ->
                connection.createStatement().use { statement ->
                    statement.executeQuery(
                        """SELECT e.element_id, e.domain_id, e.title, f.expression
                           FROM elements e JOIN formula_cards f USING(element_id)
                           ORDER BY e.display_order""".trimIndent()
                    ).use { rows ->
                        while (rows.next()) {
                            formulaCount += 1
                            val element = element(
                                id = rows.getString(1),
                                domainId = rows.getString(2),
                                title = rows.getString(3),
                                formula = rows.getString(4),
                            )
                            val variables = formulaVariables(element)
                            if (variables.isEmpty()) emptyElements += element.id
                            variables.forEach { variable ->
                                if ("식에서 사용하는" in variable.meaning) {
                                    generic += "${element.id}:${variable.symbol} -> ${variable.meaning}"
                                }
                                if (
                                    variable.symbol in NON_VARIABLE_SYMBOLS ||
                                    variable.symbol.lowercase() in NON_VARIABLE_LABELS
                                ) {
                                    leakedLabels += "${element.id}:${variable.symbol}"
                                }
                            }
                        }
                    }
                }
            }

            assertTrue(
                "Generic formula-variable explanations remain:\n${generic.joinToString("\n")}",
                generic.isEmpty(),
            )
            assertTrue(
                "Function, operator, prose, or unit labels leaked as variables:\n" +
                    leakedLabels.joinToString("\n"),
                leakedLabels.isEmpty(),
            )
            assertEquals("The packaged formula-card count changed", 135, formulaCount)
            assertTrue(
                "Formula parsing produced no financial variables for: ${emptyElements.joinToString()}",
                emptyElements.isEmpty(),
            )
        } finally {
            Files.deleteIfExists(database)
        }
    }

    @Test
    fun `every packaged variable symbol can render as latex`() {
        val fallbacks = loadPackagedFormulaElements().flatMap { element ->
            formulaVariables(element).mapNotNull { variable ->
                val rendered = safeMathMarkdown(variable.symbol)
                if ("\$\$" in rendered && '`' !in rendered) null
                else "${element.id}:${variable.symbol} -> $rendered"
            }
        }

        assertTrue(
            "Formula-variable symbols fell back to code or plain text:\n${fallbacks.joinToString("\n")}",
            fallbacks.isEmpty(),
        )
    }

    @Test
    fun `filters functions operators prose and units from formula variables`() {
        val symbols = formulaVariables(
            element(
                id = "IBT-02",
                domainId = "IBT",
                title = "FX translation gain or loss",
                formula = """
                    ${'$'}${'$'}\mathrm{USDNotional}\times\mathrm{KRW}/\mathrm{USD}${'$'}${'$'}
                    ${'$'}${'$'}E(R)=\sum_i p_sR_s${'$'}${'$'}
                    ${'$'}${'$'}C=S_0 N(d_1)-K e^{-r\times T}N(d_2)${'$'}${'$'}
                    ${'$'}${'$'}\operatorname{Cov}(R_A,R_B)${'$'}${'$'}
                    ${'$'}${'$'}100\mathrm{bp}=1\%p${'$'}${'$'}
                    ${'$'}${'$'}\text{plain vanilla swap}${'$'}${'$'}
                """.trimIndent(),
            )
        ).map { it.symbol }

        assertFalse(
            symbols.any {
                it in setOf(
                    "E", "N", "Cov", "e", "Σ", "i", "bp", "p", "KRW", "USD",
                    "plain", "vanilla", "swap",
                )
            }
        )
        assertTrue(
            symbols.containsAll(
                setOf(
                    "USDNotional", "R", "p_s", "R_s", "C", "S_0", "d_1", "K", "r", "T",
                    "d_2", "R_A", "R_B",
                )
            )
        )
    }

    @Test
    fun `keeps financial abbreviations intact instead of inventing letter variables`() {
        val symbols = formulaVariables(
            element(
                id = "EQV-33",
                domainId = "EQV",
                title = "Accounting adjustments",
                formula = """
                    ${'$'}${'$'}D\&A+M\&A+PP\&E+\mathrm{CurrentR}\&D+\mathrm{AcquisitionS}\&M${'$'}${'$'}
                """.trimIndent(),
            )
        ).map { it.symbol }

        assertEquals(
            listOf(
                "DepreciationAmortization",
                "MergerAcquisition",
                "PPE",
                "CurrentResearchDevelopment",
                "AcquisitionSalesMarketing",
            ),
            symbols,
        )
    }

    @Test
    fun `resolves ambiguous and Greek symbols from their element context`() {
        val capitalStructure = formulaVariables(
            element(
                id = "CF-08",
                domainId = "CF",
                title = "Leverage and capital structure",
                formula = """${'$'}${'$'}\beta L=\beta U[1+(1-T)D/E]${'$'}${'$'}""",
            )
        ).associate { it.symbol to it.meaning }
        assertTrue(capitalStructure.getValue("D").contains("부채"))
        assertTrue(capitalStructure.getValue("E").contains("자기자본"))
        assertTrue(capitalStructure.getValue("β_L").contains("레버드 베타"))
        assertTrue(capitalStructure.getValue("β_U").contains("언레버드 베타"))

        val covariance = formulaVariables(
            element(
                id = "INV-03",
                domainId = "INV",
                title = "Covariance and correlation",
                formula = """${'$'}${'$'}\rho_{AB}=\sigma_A\sigma_B+\mu_A+\mu_B${'$'}${'$'}""",
            )
        ).associate { it.symbol to it.meaning }
        assertEquals(setOf("ρ_AB", "σ_A", "σ_B", "μ_A", "μ_B"), covariance.keys)
        assertTrue(covariance.getValue("ρ_AB").contains("상관계수"))
        assertTrue(covariance.getValue("μ_A").contains("기대수익률"))

        val binomial = formulaVariables(
            element(
                id = "DER-07",
                domainId = "DER",
                title = "Binomial option pricing",
                formula = """${'$'}${'$'}q=(R-d)/(u-d),\quad \Delta=(V_u-V_d)/(S_u-S_d)${'$'}${'$'}""",
            )
        ).associate { it.symbol to it.meaning }
        assertTrue(binomial.getValue("q").contains("위험중립"))
        assertTrue(binomial.getValue("d").contains("하락배수"))
        assertTrue(binomial.getValue("Δ").contains("델타"))
    }

    @Test
    fun `packaged formulas retain element specific financial semantics`() {
        val variablesByElement = loadPackagedFormulaElements().associate { element ->
            element.id to formulaVariables(element).associate { it.symbol to it.meaning }
        }

        fun variables(elementId: String) = requireNotNull(variablesByElement[elementId])
        fun assertMeaning(elementId: String, symbol: String, expected: String) {
            val meaning = variables(elementId)[symbol]
            assertTrue(
                "$elementId:$symbol should contain '$expected', but was '$meaning'",
                meaning?.contains(expected) == true,
            )
        }

        assertMeaning("FI-08", "CF", "전환계수")
        assertMeaning("FI-08", "P_cash", "현물채권")
        assertMeaning("DER-01", "r_d", "국내")
        assertMeaning("DER-01", "r_f", "해외")
        assertMeaning("DER-03", "σ_S", "현물가격")
        assertMeaning("DER-03", "σ_F", "선물가격")
        assertMeaning("DER-03", "Q_A", "현물자산")
        assertMeaning("DER-03", "Q_F", "선물계약")

        assertMeaning("EQV-14", "t", "t번째 기간")
        assertFalse(variables("EQV-14").getValue("t").contains("세율"))
        assertMeaning("EQV-50", "t", "연수")
        assertFalse(variables("EQV-50").getValue("t").contains("세율"))

        assertMeaning("DER-10", "L_{t-1}", "직전")
        assertFalse("L_t" in variables("DER-10"))
        assertMeaning("IBT-13", "CapRate", "자본환원율")

        assertMeaning("FI-02", "f_{1,2}", "1년 뒤")
        assertMeaning("FI-02", "f_{m,n}", "m년 뒤")
        assertMeaning("CF-11", "FCF_{(n+1)}", "n+1기")
        assertMeaning("CF-11", "ExitMultiple", "출구 평가배수")
        assertFalse("Exit" in variables("CF-11"))
        assertFalse("Multiple" in variables("CF-11"))

        assertMeaning("CF-10", "DepreciationAmortization", "감가상각비")
        assertFalse("D" in variables("CF-10"))
        assertFalse("A" in variables("CF-10"))

        assertMeaning("EQV-02", "grossMargin", "매출총이익률")
        assertMeaning("EQV-11", "MarketCap", "시가총액")
        assertMeaning("EQV-17", "Target", "목표주가")
        assertMeaning("EQV-17", "Current", "현재주가")
        assertMeaning("EQV-23", "New", "신규 ARR")
        assertMeaning("EQV-23", "Begin", "기간 초 ARR")
        assertMeaning("EQV-35", "Incremental", "증분 주식수")
        assertMeaning("EQV-58", "Interest", "CSM")
        assertMeaning("IBT-08", "TargetShares", "피인수회사")
        assertMeaning("IBT-09", "Price", "공모가격")
        assertMeaning("IBT-09", "New", "신주")
        assertMeaning("IBT-17", "Target", "목표주가")
    }

    private fun element(
        formula: String,
        id: String = "ACC-02",
        domainId: String = "ACC",
        title: String = "Accrual and cash accounting",
    ) = ContentElement(
        id = id,
        domainId = domainId,
        title = title,
        coreRelation = "Accrual revenue",
        scope = "",
        sourceLabel = "",
        sourceLocator = "",
        specSectionLocator = "",
        definitionMarkdown = "",
        intuitionMarkdown = "",
        learningNotesMarkdown = "",
        formulaMarkdown = formula,
        assumptionsMarkdown = "",
        checklistMarkdown = "",
        sources = emptyList(),
    )

    private fun copyPackagedDatabaseToTemp(): Path {
        val stream = requireNotNull(javaClass.classLoader?.getResourceAsStream(DATABASE_ASSET)) {
            "$DATABASE_ASSET was not present in merged debug assets"
        }
        return Files.createTempFile("findone-glossary-content-", ".sqlite3").also { target ->
            stream.use { input -> Files.newOutputStream(target).use { output -> input.copyTo(output) } }
        }
    }

    private fun loadPackagedFormulaElements(): List<ContentElement> {
        val database = copyPackagedDatabaseToTemp()
        return try {
            Class.forName("org.sqlite.JDBC")
            DriverManager.getConnection("jdbc:sqlite:${database.toAbsolutePath()}").use { connection ->
                connection.createStatement().use { statement ->
                    statement.executeQuery(
                        """SELECT e.element_id, e.domain_id, e.title, f.expression
                           FROM elements e JOIN formula_cards f USING(element_id)
                           ORDER BY e.display_order""".trimIndent()
                    ).use { rows ->
                        buildList {
                            while (rows.next()) {
                                add(
                                    element(
                                        id = rows.getString(1),
                                        domainId = rows.getString(2),
                                        title = rows.getString(3),
                                        formula = rows.getString(4),
                                    )
                                )
                            }
                        }
                    }
                }
            }
        } finally {
            Files.deleteIfExists(database)
        }
    }

    private companion object {
        const val DATABASE_ASSET = "content.sqlite3"
        val NON_VARIABLE_LABELS = setOf(
            "max", "min", "ln", "log", "exp", "text", "mathrm", "operatorname",
            "cov", "var", "sd", "mean", "plain", "vanilla", "swap",
            "bp", "bps", "krw", "usd",
        )
        val NON_VARIABLE_SYMBOLS = setOf("Σ", "Π", "e", "i", "k")
    }
}
