package com.findone.app.ui

import com.findone.app.model.ContentElement
import java.util.Locale

data class FormulaVariable(
    val symbol: String,
    val meaning: String,
)

data class GlossaryTerm(
    val id: String,
    val domainId: String,
    val elementId: String,
    val elementTitle: String,
    val term: String,
    val description: String,
)

/** Extract every distinct financial variable rendered inside a math delimiter. */
internal fun formulaVariables(element: ContentElement): List<FormulaVariable> {
    val symbols = linkedSetOf<String>()
    val normalizedMarkdown = element.formulaMarkdown.normalizeCrossSpanFormulaTokens()
    MATH_PAYLOAD.findAll(normalizedMarkdown).forEach { match ->
        val readable = TEX_UPRIGHT.replace(
            TEX_TEXT_OR_OPERATOR.replace(match.groupValues[1], " ")
        ) { group -> group.groupValues[1] }
            .replace("\\Delta", "Δ")
            .replace("\\Sigma", "Σ")
            .replace("\\Pi", "Π")
            .replace("\\alpha", "α")
            .replace("\\beta", "β")
            .replace("\\gamma", "γ")
            .replace("\\delta", "δ")
            .replace("\\mu", "μ")
            .replace("\\rho", "ρ")
            .replace("\\sigma", "σ")
            .replace("\\lambda", "λ")
            .let { TEX_COMMAND.replace(it, " ") }
            .normalizeFormulaTokens()

        val greekIdentifiers = GREEK_IDENTIFIER.findAll(readable).toList()
        val candidates = buildList {
            greekIdentifiers.forEach { identifier ->
                val base = identifier.groupValues[1]
                val subscript = identifier.firstNonBlankGroupAfterBase()
                val symbol = formulaSymbol(base, subscript)
                add(FormulaSymbolCandidate(identifier.range.first, identifier.range.last, symbol))
            }
            IDENTIFIER.findAll(readable).forEach { identifier ->
                if (greekIdentifiers.any { greek -> identifier.range.first in greek.range }) return@forEach
                val base = identifier.groupValues[1]
                val subscript = identifier.firstNonBlankGroupAfterBase()
                val symbol = formulaSymbol(base, subscript)
                add(FormulaSymbolCandidate(identifier.range.first, identifier.range.last, symbol))
            }
        }.sortedBy(FormulaSymbolCandidate::start)

        candidates.forEach { candidate ->
            val symbol = candidate.symbol
            if (
                shouldIgnoreFormulaSymbol(
                    symbol = symbol,
                    formula = readable,
                    symbolStart = candidate.start,
                    symbolEnd = candidate.end,
                    element = element,
                )
            ) return@forEach
            symbols += symbol
        }
    }
    return symbols.map { symbol -> FormulaVariable(symbol, variableMeaning(symbol, element)) }
}

private data class FormulaSymbolCandidate(
    val start: Int,
    val end: Int,
    val symbol: String,
)

private fun MatchResult.firstNonBlankGroupAfterBase(): String =
    groupValues.drop(2).firstOrNull(String::isNotBlank).orEmpty()

private fun formulaSymbol(base: String, rawSubscript: String): String {
    val subscript = rawSubscript.replace(Regex("\\s+"), "")
    if (subscript.isBlank()) return base
    return if (subscript.all(Char::isLetterOrDigit)) {
        "${base}_$subscript"
    } else {
        "${base}_{${subscript}}"
    }
}

private fun String.normalizeCrossSpanFormulaTokens(): String = this
    .replace(SPLIT_DEPRECIATION_AMORTIZATION) { "\$\$DepreciationAmortization\$\$" }
    .replace(SPLIT_EXIT_MULTIPLE) { "\$\$ExitMultiple\$\$" }

private fun String.normalizeFormulaTokens(): String = this
    .replace("AcquisitionS\\&M", "AcquisitionSalesMarketing")
    .replace("CurrentR\\&D", "CurrentResearchDevelopment")
    .replace("D\\&A", "DepreciationAmortization")
    .replace("D&A", "DepreciationAmortization")
    .replace("M\\&A", "MergerAcquisition")
    .replace("M&A", "MergerAcquisition")
    .replace("PP\\&E", "PPE")
    .replace("A/D", "AccretionDilution")
    .replace(Regex("""β\s+([LU])"""), "β_{$1}")
    .replace(MERGED_INDEXED_PRODUCT) { match ->
        "${match.groupValues[1]}_{${match.groupValues[2]}} " +
            "${match.groupValues[3]}_{${match.groupValues[4]}}"
    }

private fun shouldIgnoreFormulaSymbol(
    symbol: String,
    formula: String,
    symbolStart: Int,
    symbolEnd: Int,
    element: ContentElement,
): Boolean {
    val normalized = symbol.lowercase(Locale.ROOT)
    if (normalized in IGNORED_IDENTIFIERS || normalized in UNIT_IDENTIFIERS) return true
    if (symbol in ELEMENT_IGNORED_IDENTIFIERS[element.id].orEmpty()) return true
    if (symbol == "e" || symbol == "Σ" || symbol == "Π" || symbol == "i" || symbol == "k") return true

    val next = formula.drop(symbolEnd + 1).firstOrNull { !it.isWhitespace() && it !in "{}" }
    val previous = formula.take(symbolStart).lastOrNull { !it.isWhitespace() && it !in "{}\\" }
    if (next == '(' && normalized.substringBefore('_') in FUNCTION_IDENTIFIERS) return true
    if (normalized == "p" && previous == '%') return true
    // A leading delta denotes the change operator. A standalone replication/option delta has an
    // equals sign after it and remains a genuine financial variable.
    if (symbol == "Δ" && next != '=') return true
    return false
}

/**
 * Builds a stable, content-derived glossary. Domain selection keeps the UI bounded, while each
 * element remains visible with its full title and every emphasized term/formula identifier.
 */
internal fun glossaryTerms(elements: List<ContentElement>): List<GlossaryTerm> = buildList {
    elements.forEach { element ->
        val candidates = linkedMapOf<String, String>()
        candidates[element.title] = "${element.title} 학습요소 전체를 가리키는 소주제입니다."

        element.allLearningMarkdown().forEach { markdown ->
            BOLD_TERM.findAll(markdown).forEach { match ->
                val term = cleanGlossaryTerm(match.groupValues[1])
                if (term.length in 2..80) {
                    candidates.putIfAbsent(term, "${element.title}에서 정의·적용하는 핵심 용어입니다.")
                }
            }
        }

        formulaVariables(element).forEach { variable ->
            candidates.putIfAbsent(variable.symbol, variable.meaning)
        }

        TITLE_ACRONYM.findAll(element.title).forEach { match ->
            candidates.putIfAbsent(match.value, variableMeaning(match.value, element))
        }

        candidates.forEach { (term, description) ->
            add(
                GlossaryTerm(
                    id = stableGlossaryTermId(element.id, term),
                    domainId = element.domainId,
                    elementId = element.id,
                    elementTitle = element.title,
                    term = term,
                    description = description,
                )
            )
        }
    }
}

internal fun stableGlossaryTermId(elementId: String, term: String): String {
    var hash = -0x340d631b7bdddcdbL // FNV-1a 64-bit offset basis as a signed Long.
    "$elementId\u0000${term.trim().lowercase(Locale.ROOT)}".toByteArray(Charsets.UTF_8).forEach { byte ->
        hash = hash xor (byte.toLong() and 0xffL)
        hash *= 0x100000001b3L
    }
    return "$elementId:${hash.toULong().toString(16).padStart(16, '0')}"
}

private fun variableMeaning(symbol: String, element: ContentElement): String {
    ELEMENT_VARIABLE_MEANINGS[element.id]?.get(symbol)?.let { return it }
    DOMAIN_VARIABLE_MEANINGS[element.domainId]?.get(symbol)?.let { return it }
    EXACT_VARIABLE_MEANINGS[symbol]?.let { return it }
    patternedVariableMeaning(symbol)?.let { return it }

    val rawParts = splitIdentifier(symbol)
    val translatedParts = rawParts.map { part ->
        EXACT_VARIABLE_MEANINGS[part]
            ?: VARIABLE_WORD_MEANINGS[part.lowercase(Locale.ROOT)]
    }
    return if (translatedParts.all { it != null }) {
        "${translatedParts.filterNotNull().joinToString(" · ")}을(를) 뜻합니다. ‘${element.title}’의 기간·단위 기준을 적용합니다."
    } else {
        "‘${element.title}’ 식에서 사용하는 $symbol 값입니다. 식 주변의 정의와 동일한 기간·단위를 적용합니다."
    }
}

private fun patternedVariableMeaning(symbol: String): String? {
    val match = INDEXED_SYMBOL.matchEntire(symbol) ?: return null
    val base = match.groupValues[1]
    val index = match.groupValues[2]
    val baseMeaning = EXACT_VARIABLE_MEANINGS[base] ?: return null
    val indexMeaning = INDEX_MEANINGS[index] ?: return null
    return "$indexMeaning $baseMeaning"
}

private fun splitIdentifier(symbol: String): List<String> = symbol
    .replace(Regex("[_{}]+"), " ")
    .replace(Regex("(?<=[a-z0-9])(?=[A-Z])"), " ")
    .split(Regex("\\s+"))
    .filter(String::isNotBlank)

private fun ContentElement.allLearningMarkdown(): List<String> = listOf(
    definitionMarkdown,
    intuitionMarkdown,
    formulaMarkdown,
    assumptionsMarkdown,
    learningNotesMarkdown,
    checklistMarkdown,
)

private fun cleanGlossaryTerm(value: String): String = value
    .replace(Regex("[`*_]+"), "")
    .replace(Regex("\\s+"), " ")
    .trim(' ', ':', '.', '。')

private val MATH_PAYLOAD = Regex("""(?s)\$\$(.+?)\$\$""")
private val TEX_UPRIGHT = Regex("""\\mathrm\{([^{}]+)\}""")
private val TEX_TEXT_OR_OPERATOR = Regex("""\\(?:text|operatorname)\{[^{}]*\}""")
private val TEX_COMMAND = Regex("""\\[A-Za-z]+""")
private val IDENTIFIER = Regex(
    """(?<![A-Za-z0-9])([A-Za-z][A-Za-z0-9]*)(?:_(?:\{([^{}]+)}|([A-Za-z0-9]+)))?(?![A-Za-z0-9])""",
)
private val GREEK_IDENTIFIER = Regex(
    """([αβγδμρσλΔΣΠ])(?:\s*_\s*(?:\{([^{}]+)}|([A-Za-z0-9]+)))?""",
)
private val BOLD_TERM = Regex("""\*\*([^*\n]+)\*\*""")
private val TITLE_ACRONYM = Regex("""(?<![A-Za-z0-9])[A-Z][A-Z0-9]{1,9}(?![A-Za-z0-9])""")
private val MERGED_INDEXED_PRODUCT = Regex(
    """(?<![A-Za-z0-9])([A-Za-z])_\{?([a-z])\}?([A-Z])_\{?([A-Za-z0-9]+)\}?""",
)
private val INDEXED_SYMBOL = Regex("""([A-Za-z]+)_([A-Za-z0-9]+)""")
private const val DOUBLE_DOLLAR = "\$\$"
private val DOUBLE_DOLLAR_PATTERN = Regex.escape(DOUBLE_DOLLAR)
private val SPLIT_DEPRECIATION_AMORTIZATION = Regex(
    "$DOUBLE_DOLLAR_PATTERN\\s*D\\s*$DOUBLE_DOLLAR_PATTERN\\s*\\\\?&\\s*" +
        "$DOUBLE_DOLLAR_PATTERN\\s*A\\s*$DOUBLE_DOLLAR_PATTERN",
)
private val SPLIT_EXIT_MULTIPLE = Regex(
    "$DOUBLE_DOLLAR_PATTERN\\s*\\\\mathrm\\{Exit}\\s*$DOUBLE_DOLLAR_PATTERN\\s*" +
        "$DOUBLE_DOLLAR_PATTERN\\s*\\\\mathrm\\{Multiple}\\s*$DOUBLE_DOLLAR_PATTERN",
)
private val IGNORED_IDENTIFIERS = setOf(
    "max", "min", "ln", "log", "exp", "text", "mathrm", "operatorname",
    "plain", "vanilla", "swap",
)
private val FUNCTION_IDENTIFIERS = setOf("e", "cov", "var", "sd", "mean", "n", "pv", "dcf")
private val UNIT_IDENTIFIERS = setOf(
    "bp", "bps", "percent", "percentage", "krw", "usd", "krwperusd",
)

private val ELEMENT_IGNORED_IDENTIFIERS = mapOf(
    "EQV-52" to setOf("E"), // E in P/E is the denominator label, not a standalone variable row.
    "IBT-01" to setOf("p"), // %p is the percentage-point unit, not a formula variable.
)

private val ELEMENT_VARIABLE_MEANINGS = mapOf(
    "CF-02" to mapOf(
        "C" to "매 기간 말 지급되거나 수취되는 동일한 연금 현금흐름",
        "C1" to "성장영구연금의 첫 번째 기간 말 현금흐름",
    ),
    "CF-05" to mapOf(
        "P0" to "현재 주가",
        "D1" to "다음 기간의 기대 주당배당금",
    ),
    "CF-08" to mapOf(
        "D" to "이자부부채의 시장가치",
        "E" to "자기자본의 시장가치",
        "β_L" to "재무레버리지를 반영한 레버드 베타",
        "β_U" to "재무레버리지 영향을 제거한 언레버드 베타",
    ),
    "CF-10" to mapOf(
        // The source currently splits D&A across adjacent math spans in the FCFE line.
        "D" to "FCFF·FCFE에 가산하는 감가상각비(D&A 중 depreciation 부분)",
        "A" to "FCFF·FCFE에 가산하는 무형자산상각비(D&A 중 amortization 부분)",
    ),
    "CF-11" to mapOf(
        "FCF_{(n+1)}" to "명시적 예측기간이 끝난 직후 n+1기에 발생하는 첫 안정기 잉여현금흐름",
        "ExitMultiple" to "계속가치를 산정할 때 안정기 기준지표에 적용하는 출구 평가배수",
    ),
    "INV-01" to mapOf(
        "D" to "보유기간 중 받은 주당 배당금",
        "P0" to "보유기간 시작 시점의 자산가격",
        "P1" to "보유기간 종료 시점의 자산가격",
        "Pn" to "n기간 종료 시점의 자산가격",
        "r" to "해당 기간에 자산에서 실현된 투자수익률",
    ),
    "INV-02" to mapOf("R" to "확률분포를 갖는 투자수익률"),
    "INV-03" to mapOf(
        "A" to "공분산을 측정하는 첫 번째 자산 A",
        "B" to "공분산을 측정하는 두 번째 자산 B",
    ),
    "INV-04" to mapOf(
        "A" to "2자산 포트폴리오의 첫 번째 자산 A",
        "B" to "2자산 포트폴리오의 두 번째 자산 B",
        "w" to "전체 포트폴리오에서 자산 A가 차지하는 투자비중",
    ),
    "FI-01" to mapOf(
        "P" to "채권의 현재가격",
        "C" to "채권이 매 기간 지급하는 쿠폰 현금흐름",
        "F" to "만기에 상환되는 채권 액면금액",
        "y" to "채권 현금흐름을 할인하는 만기수익률(YTM)",
    ),
    "FI-02" to mapOf(
        "f_{1,2}" to "1년 뒤 시작해 2년 만기에 끝나는 1년 선도이자율",
        "f_{m,n}" to "m년 뒤 시작해 n년 만기에 끝나는 기간의 선도이자율",
    ),
    "FI-05" to mapOf("w" to "면역 포트폴리오에서 첫 번째 자산의 투자비중"),
    "FI-06" to mapOf("N" to "채권 포트폴리오의 금리위험을 상쇄하는 선물계약 수"),
    "FI-07" to mapOf(
        "h" to "담보가치에서 차감하는 repo haircut 비율",
        "I" to "repo 기간에 발생하는 이자금액",
        "r" to "repo 거래에 적용되는 연환산 이자율",
        "B" to "360일 또는 365일의 day-count 기준일수",
    ),
    "FI-08" to mapOf(
        "P_cash" to "인도 가능한 현물채권의 현재 시장가격",
        "CF" to "채권선물 인도 시 현물채권 가격을 표준화하는 전환계수(conversion factor)",
    ),
    "FI-09" to mapOf(
        "N" to "금리스왑의 명목원금",
        "d" to "해당 이자기간의 경과일수",
        "B" to "이자계산에 사용하는 연간 기준일수",
        "K" to "스왑 계약의 고정금리",
    ),
    "DER-01" to mapOf(
        "I" to "선도 만기 전에 기초자산에서 확정적으로 지급되는 현금수익의 현재가치",
        "r" to "기초자산 보유비용에 적용되는 무위험이자율",
        "r_d" to "통화선도 평가에서 원화 등 국내통화에 적용되는 국내 무위험이자율",
        "r_f" to "통화선도 평가에서 달러 등 외국통화에 적용되는 해외 무위험이자율",
    ),
    "DER-03" to mapOf(
        "h" to "현물 가격변동 위험을 최소화하는 최소분산 헤지비율",
        "N" to "헤지에 필요한 선물계약 수",
        "σ_S" to "헤지 대상 현물가격 변화의 표준편차",
        "σ_F" to "헤지에 사용하는 선물가격 변화의 표준편차",
        "Q_A" to "헤지하려는 현물자산의 총 보유수량",
        "Q_F" to "선물계약 한 개가 대표하는 기초자산 수량",
    ),
    "DER-05" to mapOf(
        "c" to "콜옵션 1단위에 처음 지급한 프리미엄",
        "p" to "풋옵션 1단위에 처음 지급한 프리미엄",
    ),
    "DER-06" to mapOf(
        "C" to "동일 행사가·만기의 유럽형 콜옵션 현재가격",
        "P" to "동일 행사가·만기의 유럽형 풋옵션 현재가격",
    ),
    "DER-07" to mapOf(
        "u" to "한 기간 뒤 주가가 상승할 때의 상승배수",
        "d" to "한 기간 뒤 주가가 하락할 때의 하락배수",
        "R" to "한 기간 무위험 총수익배수",
        "q" to "이항모형의 위험중립 상승확률",
        "Δ" to "주식으로 옵션을 복제할 때 필요한 델타 수량",
    ),
    "DER-08" to mapOf(
        "C" to "Black–Scholes–Merton 유럽형 콜옵션 가격",
        "P" to "Black–Scholes–Merton 유럽형 풋옵션 가격",
        "r" to "연속복리 무위험이자율",
    ),
    "DER-09" to mapOf("V" to "평가 대상 옵션 또는 파생상품의 가치"),
    "DER-10" to mapOf(
        "N" to "스왑 이자계산의 기준이 되는 명목원금",
        "K" to "스왑에서 지급하는 약정 고정금리",
        "B" to "이자계산에 사용하는 연간 기준일수",
        "L_{t-1}" to "t기 지급액을 계산하기 위해 직전 t-1기 초에 확정한 변동금리",
    ),
    "EQV-02" to mapOf(
        "grossMargin" to "매출액 중 매출총이익으로 남는 비율인 매출총이익률",
    ),
    "EQV-13" to mapOf(
        "t" to "부채 이자비용의 세금효과에 적용되는 법인세율",
    ),
    "EQV-14" to mapOf("t" to "명시적 예측기간 안에서 현금흐름이 발생하는 t번째 기간"),
    "EQV-17" to mapOf(
        "Target" to "애널리스트의 가치평가로 산출한 목표주가",
        "Current" to "상승여력 계산 기준일의 현재주가",
    ),
    "EQV-21" to mapOf(
        "R" to "제품별 가격과 판매량을 합산한 총매출액",
        "P0" to "브리지 기준기간의 단위 판매가격",
        "P1" to "브리지 비교기간의 단위 판매가격",
        "Q0" to "브리지 기준기간의 판매수량",
        "Q1" to "브리지 비교기간의 판매수량",
    ),
    "EQV-22" to mapOf("M" to "사업부별 매출비중을 반영한 연결 영업이익률"),
    "EQV-23" to mapOf(
        "New" to "해당 기간 새 고객 계약에서 추가된 신규 ARR",
        "Begin" to "증감 요인을 반영하기 전 기간 초 ARR",
    ),
    "EQV-24" to mapOf("LTV" to "고객 한 명이 이탈 전까지 창출할 것으로 예상되는 고객생애가치"),
    "EQV-35" to mapOf("Incremental" to "잠재적 희석증권에서 추가되는 증분 주식수"),
    "EQV-50" to mapOf("t" to "가치평가 기준일부터 t번째 현금흐름까지의 연수"),
    "EQV-52" to mapOf("B" to "P/B 배수의 분모인 주당 장부가치"),
    "EQV-58" to mapOf("Interest" to "보험계약서비스마진(CSM) 잔액에 당기 부리되는 이자"),
    "IBT-02" to mapOf(
        "N" to "환산하거나 헤지하는 외화 명목금액",
        "S0" to "거래 시작 시점의 원/달러 환율",
        "S1" to "결제 또는 평가 시점의 원/달러 환율",
    ),
    "IBT-03" to mapOf("D" to "신용스프레드 변화에 대한 채권의 수정듀레이션"),
    "IBT-04" to mapOf(
        "B" to "정책금리 변화가 적용되는 이자부 자산·부채 잔액",
        "rBp" to "베이시스포인트 단위의 금리변화폭",
    ),
    "IBT-06" to mapOf("r" to "인수 시너지 현금흐름의 위험에 맞춘 할인율"),
    "IBT-08" to mapOf("TargetShares" to "피인수회사의 인수 대상 발행주식 수"),
    "IBT-09" to mapOf(
        "Price" to "IPO 투자자에게 제시하는 주당 공모가격",
        "New" to "IPO에서 회사가 새로 발행하는 신주 수",
    ),
    "IBT-13" to mapOf("CapRate" to "안정화 순영업소득을 부동산 가치로 환산하는 자본환원율"),
    "IBT-14" to mapOf("LTV" to "담보 부동산 가치 대비 대출잔액 비율"),
    "IBT-17" to mapOf("Target" to "실적 전망과 목표배수를 반영해 수정하는 목표주가"),
)

private val DOMAIN_VARIABLE_MEANINGS = mapOf(
    "ACC" to mapOf(
        "A" to "회계등식의 자산 총액",
        "L" to "회계등식의 부채 총액",
        "E" to "회계등식의 자본 총액",
    ),
    "CF" to mapOf(
        "r" to "현금흐름의 위험과 기간에 맞춘 할인율",
        "T" to "이자 세금효과에 적용되는 법인세율",
    ),
    "INV" to mapOf(
        "R" to "투자자산의 수익률",
        "w" to "포트폴리오 투자비중",
        "ρ" to "두 자산 또는 현물·선물 수익률의 상관계수",
        "μ" to "확률가중 기대수익률",
        "α" to "위험모형이 설명하지 못한 초과수익률",
        "λ" to "APT 요인의 단위 노출당 위험프리미엄",
    ),
    "FI" to mapOf(
        "P" to "채권 또는 금리상품의 현재 시장가치",
        "y" to "채권의 만기수익률 또는 시장수익률",
        "N" to "금리위험을 조정하기 위해 취하는 헤지계약 수",
    ),
    "DER" to mapOf(
        "S" to "기초자산 현물가격",
        "F" to "선도·선물 계약가격",
        "K" to "옵션 보유자가 기초자산을 사고팔 수 있는 약정 행사가격",
        "T" to "파생계약 만기까지 남은 연수",
        "r" to "파생상품 평가에 적용되는 무위험이자율",
    ),
    "EQV" to mapOf(
        "P" to "주식 또는 상품의 단위가격",
        "Q" to "판매수량",
        "t" to "영업이익에 적용되는 법인세율",
    ),
)

private val INDEX_MEANINGS = mapOf(
    "0" to "기준시점의",
    "1" to "첫 번째 기간의",
    "2" to "두 번째 기간의",
    "n" to "n번째 또는 만기시점의",
    "t" to "t번째 기간의",
    "i" to "자산·상품 i의",
    "p" to "포트폴리오의",
    "f" to "무위험 기준의",
    "m" to "시장 기준의",
    "s" to "시나리오 s의",
    "A" to "자산 A의",
    "B" to "자산 B의",
    "AB" to "자산 A와 B 사이의",
    "u" to "상승 상태의",
    "d" to "하락 상태의",
    "L" to "레버드 기준의",
    "U" to "언레버드 기준의",
)

private val EXACT_VARIABLE_MEANINGS = mapOf(
    "A" to "자산(Assets)",
    "L" to "부채(Liabilities)",
    "E" to "자본 또는 지분가치(Equity)",
    "P" to "가격 또는 현재가(Price)",
    "Q" to "수량(Quantity)",
    "PV" to "현재가치(Present Value)",
    "FV" to "미래가치(Future Value)",
    "NPV" to "순현재가치(Net Present Value)",
    "IRR" to "내부수익률(Internal Rate of Return)",
    "WACC" to "가중평균자본비용",
    "EV" to "기업가치(Enterprise Value)",
    "EBIT" to "이자·법인세 차감 전 이익",
    "EBITDA" to "이자·법인세·감가상각비 차감 전 이익",
    "NOPAT" to "세후영업이익",
    "FCF" to "잉여현금흐름",
    "FCFF" to "기업 전체에 귀속되는 잉여현금흐름",
    "FCFE" to "보통주주에게 귀속되는 잉여현금흐름",
    "CFO" to "영업활동현금흐름",
    "CFI" to "투자활동현금흐름",
    "CFF" to "재무활동현금흐름",
    "NWC" to "순운전자본",
    "AR" to "매출채권(Accounts Receivable)",
    "AP" to "매입채무(Accounts Payable)",
    "COGS" to "매출원가",
    "EPS" to "주당순이익",
    "ROA" to "총자산이익률",
    "ROE" to "자기자본이익률",
    "ROIC" to "투하자본이익률",
    "PER" to "주가수익비율",
    "PBR" to "주가순자산비율",
    "ARR" to "연간반복매출",
    "NRR" to "순매출유지율",
    "GRR" to "총매출유지율",
    "CAC" to "고객획득비용",
    "GMV" to "총거래액",
    "DSO" to "매출채권 회수일수",
    "DIO" to "재고자산 보유일수",
    "DPO" to "매입채무 지급일수",
    "CCC" to "현금전환주기",
    "PD" to "부도확률",
    "LGD" to "부도 시 손실률",
    "EAD" to "부도 시 익스포저",
    "EL" to "기대손실",
    "NAV" to "순자산가치",
    "NOI" to "순영업소득",
    "LTV" to "담보인정비율 또는 고객생애가치로, 해당 소주제 문맥을 따릅니다.",
    "DSCR" to "부채상환비율",
    "HPR" to "보유기간수익률",
    "TE" to "추적오차",
    "IR" to "정보비율",
    "WriteOffs" to "회수가 불가능하다고 확정해 매출채권과 충당금에서 제거한 대손확정액",
    "UsefulLife" to "감가상각 대상 자산의 예상 내용연수",
    "NBV" to "취득원가에서 누적감가상각을 뺀 순장부가액",
    "NBV_sale" to "자산 처분시점의 순장부가액",
    "SaleProceeds" to "자산 매각으로 받은 처분대금",
    "BasicEPS" to "희석효과를 반영하기 전 기본주당이익",
    "NI" to "당기순이익(Net Income)",
    "Capex" to "유형자산 취득 등에 지출한 설비투자액",
    "PPE" to "유형자산(Property, Plant and Equipment)",
    "CFO_adjustment" to "영업활동현금흐름 계산에 반영하는 비현금 조정액",
    "CFI_adjustment" to "투자활동현금흐름에 반영하는 설비투자 조정액",
    "PPE_adjustment" to "유형자산 장부금액에 반영하는 증감 조정액",
    "DepreciationAmortization" to "감가상각비와 무형자산상각비(D&A)의 합계",
    "CF" to "해당 기간에 발생하는 현금흐름",
    "CF_t" to "t번째 기간의 현금흐름",
    "FCF_t" to "t번째 기간의 잉여현금흐름",
    "FCFF_t" to "t번째 기간의 기업잉여현금흐름",
    "FCF_{(n+1)}" to "명시적 예측기간 직후 n+1기에 발생하는 첫 안정기 잉여현금흐름",
    "FCFF_{(n+1)}" to "명시적 예측기간 직후 n+1기에 기업 전체가 창출하는 첫 안정기 잉여현금흐름",
    "I0" to "투자안의 시점 0 초기투자금액",
    "PV_0" to "기준시점 0의 현재가치",
    "FV_n" to "n기간 후의 미래가치",
    "TV" to "명시적 예측기간 이후 현금흐름의 계속가치",
    "TV_n" to "명시적 예측기간 말 n시점의 계속가치",
    "k_e" to "주주가 요구하는 자기자본비용",
    "k_d" to "세금효과 반영 전 부채비용",
    "kE" to "자기자본비용",
    "kD" to "세전 부채비용",
    "rf" to "무위험수익률",
    "Rm" to "시장포트폴리오 수익률",
    "w_E" to "총 자본조달액 중 자기자본의 시장가치 비중",
    "w_D" to "총 자본조달액 중 이자부부채의 시장가치 비중",
    "VL" to "부채를 사용하는 기업의 가치",
    "VU" to "부채를 사용하지 않는 동일 사업의 가치",
    "OCF" to "프로젝트의 세후 영업현금흐름",
    "Exit" to "계속가치 산정에 적용하는 출구 평가배수",
    "P0" to "기준시점 0의 가격",
    "P1" to "첫 번째 기간 말의 가격",
    "Pn" to "n번째 기간 말의 가격",
    "r_log" to "연속복리 기준 로그수익률",
    "r_A" to "기간수익률의 산술평균",
    "r_G" to "복리효과를 반영한 기하평균수익률",
    "r_t" to "t번째 기간의 수익률",
    "p_s" to "시나리오 s가 발생할 확률",
    "R_s" to "시나리오 s에서 실현되는 수익률",
    "R_A" to "자산 A의 수익률",
    "R_B" to "자산 B의 수익률",
    "R_As" to "시나리오 s에서 자산 A의 수익률",
    "R_Bs" to "시나리오 s에서 자산 B의 수익률",
    "R_i" to "평가대상 자산 i의 수익률",
    "R_m" to "시장포트폴리오 수익률",
    "R_f" to "무위험수익률",
    "R_p" to "평가대상 포트폴리오 수익률",
    "AR_t" to "t번째 기간의 포트폴리오 초과수익률",
    "R_pt" to "t번째 기간의 포트폴리오 수익률",
    "R_bt" to "t번째 기간의 벤치마크 수익률",
    "Sharpe" to "총위험 한 단위당 무위험 초과수익을 나타내는 Sharpe 지수",
    "Treynor" to "베타 한 단위당 무위험 초과수익을 나타내는 Treynor 지수",
    "D_Mac" to "채권 현금흐름 현재가치의 가중평균 회수기간인 Macaulay duration",
    "D_Mod" to "수익률 변화에 대한 채권가격 민감도인 modified duration",
    "DV01" to "수익률이 1bp 변할 때 채권가치가 변하는 금액",
    "MV" to "금리민감도를 측정하는 포지션의 시장가치",
    "Convexity" to "금리변화와 채권가격 변화의 곡률을 나타내는 convexity",
    "D_A" to "자산 포트폴리오의 듀레이션",
    "D_L" to "부채 현금흐름의 듀레이션",
    "D_1" to "첫 번째 면역화 자산의 듀레이션",
    "D_2" to "두 번째 면역화 자산의 듀레이션",
    "DV01_portfolio" to "헤지 대상 채권 포트폴리오의 DV01",
    "DV01_futures" to "선물계약 1개의 DV01",
    "V_P" to "헤지 대상 포트폴리오의 시장가치",
    "D_P" to "헤지 대상 포트폴리오의 듀레이션",
    "V_F" to "선물계약 1개가 대표하는 기초자산 가치",
    "D_F" to "선물 기초자산의 듀레이션",
    "Collateral" to "repo 거래에 제공되는 담보증권의 시장가치",
    "RP" to "원금과 repo 이자를 합한 재매입 지급액",
    "Basis" to "현물채권 가격에서 전환계수 조정 선물가격을 뺀 basis",
    "F_futures" to "채권선물의 시장가격",
    "Recovery" to "부도 발생 시 익스포저 중 회수되는 비율",
    "F_0" to "계약 체결시점의 이론 선도·선물가격",
    "S_0" to "계약 체결시점의 기초자산 현물가격",
    "S_T" to "옵션 만기 T시점의 기초자산 가격",
    "S_u" to "이항모형 상승 상태의 기초자산 가격",
    "S_d" to "이항모형 하락 상태의 기초자산 가격",
    "V_0" to "현재시점의 옵션가치",
    "V_u" to "이항모형 상승 상태의 옵션가치",
    "V_d" to "이항모형 하락 상태의 옵션가치",
    "d_1" to "Black–Scholes–Merton에서 주가·행사가·금리·변동성·만기를 결합한 표준화 변수 d1",
    "d_2" to "d1에서 만기 변동성 σ√T를 차감한 표준화 변수 d2",
    "Delta" to "기초자산 가격 1단위 변화에 대한 옵션가치 민감도",
    "Gamma" to "기초자산 가격 변화에 대한 Delta의 변화율",
    "Vega" to "변동성 변화에 대한 옵션가치 민감도",
    "Theta" to "시간 경과에 대한 옵션가치 민감도",
    "Rho" to "무위험금리 변화에 대한 옵션가치 민감도",
    "L_t" to "t기간에 적용되는 변동금리",
    "L_prev" to "직전 금리결정일에 확정된 변동금리",
    "accrual_i" to "i번째 이자기간의 연환산 기간비율",
    "NWC0" to "기준기간의 순운전자본",
    "NWC1" to "비교기간의 순운전자본",
    "BPS" to "주당 장부가치(Book Value per Share)",
    "Preferred" to "보통주보다 선순위인 우선주 가치",
    "Minority" to "연결 자회사 중 비지배주주에게 귀속되는 지분가치",
    "EVexplicit" to "명시적 예측기간 FCFF의 현재가치 합계",
    "MarketCap" to "현재 주가에 발행주식수를 곱해 산출한 보통주 시가총액",
    "ImpliedEV" to "비교기업 평가배수를 적용해 산출한 내재 기업가치",
    "Upside" to "현재가 대비 목표주가의 예상 상승여력",
    "FX" to "환율 변동 및 외화환산으로 발생한 증감효과",
    "Divestiture" to "사업 매각·철수로 인한 매출 감소효과",
    "ScopeChange" to "연결범위 변경으로 발생한 매출 증감효과",
    "w_i" to "전체 매출에서 사업부 i가 차지하는 비중",
    "m_i" to "사업부 i의 영업이익률",
    "SegmentEBIT" to "각 사업부가 창출한 영업이익",
    "Elimination" to "내부거래 제거 등 연결조정 영업이익",
    "Expansion" to "기존 고객의 업셀·사용량 증가로 늘어난 반복매출",
    "Contraction" to "기존 고객의 다운셀·사용량 감소로 줄어든 반복매출",
    "Churn" to "고객 이탈로 소멸한 반복매출 또는 이탈률",
    "AcquisitionSalesMarketing" to "신규고객 획득에 투입한 영업·마케팅 비용",
    "ARPU" to "사용자당 평균매출(Average Revenue per User)",
    "Payback" to "고객획득비용을 고객 총이익으로 회수하는 데 필요한 기간",
    "Yield" to "생산능력·가동량 중 판매 가능한 산출물로 전환되는 수율",
    "BreakEvenUnits" to "고정비를 모두 회수해 영업손익이 0이 되는 판매수량",
    "Bookings" to "해당 기간에 새로 수주한 계약금액",
    "Cancellations" to "취소되어 backlog에서 제거되는 계약금액",
    "BookToBill" to "기간 매출 대비 신규수주 비율",
    "Days" to "운전자본 일수 계산에 사용하는 연간 기준일수",
    "Billings" to "기간 중 고객에게 청구한 금액",
    "ContractAsset" to "수익을 인식했지만 아직 청구권이 무조건적이지 않은 계약자산",
    "ContractLiability" to "대가를 먼저 받았지만 아직 수익을 인식하지 않은 계약부채",
    "TrueOneOffLosses" to "정상화 과정에서 되돌려 더하는 실제 일회성 손실",
    "PolicyAdjustments" to "회계정책 차이를 일관된 기준으로 맞추는 조정액",
    "Options" to "희석주식수 계산 대상인 임직원 주식옵션 수",
    "Basic" to "희석증권 반영 전 기본 유통보통주식수",
    "RSU" to "희석주식수에 반영되는 양도제한조건부주식",
    "Convertibles" to "전환을 가정할 때 추가되는 전환증권 주식수",
    "FundedStatus" to "연금 사외적립자산에서 확정급여채무를 뺀 순적립상태",
    "DBO" to "확정급여형 연금의 현재가치 기준 급여채무",
    "BookETR" to "손익계산서 법인세비용을 세전이익으로 나눈 장부 실효세율",
    "PBT" to "법인세비용 차감 전 이익(Profit Before Tax)",
    "NOLShield" to "사용 가능한 이월결손금에서 발생하는 법인세 절감가치",
    "UsableNOL" to "향후 과세소득과 상계할 수 있을 것으로 인정한 이월결손금",
    "Goodwill" to "인수가격 중 식별가능 순자산 공정가치를 초과한 영업권",
    "Consideration" to "피취득기업 지배력 확보를 위해 지급한 인수대가",
    "NCI" to "연결 자회사 순자산 중 비지배주주 귀속분",
    "IC" to "영업활동에 투입된 투자자본(Invested Capital)",
    "NOPATMargin" to "매출액 대비 세후영업이익률",
    "EBT" to "법인세 차감 전 이익(Earnings Before Tax)",
    "EVA" to "투자자본의 자본비용을 차감한 경제적 부가가치",
    "Reinvestment" to "미래 성장을 위해 영업에 다시 투입한 투자액",
    "RI" to "순이익에서 자기자본 요구수익을 차감한 잔여이익",
    "r_e" to "보통주주가 요구하는 자기자본비용",
    "Disposals" to "유형자산 처분으로 장부에서 제거되는 금액",
    "SOTPEquity" to "사업부별 가치 합산 방식으로 산출한 보통주 지분가치",
    "SegmentEV" to "개별 사업부의 기업가치",
    "CorporateCosts" to "사업부에 배부되지 않은 본사 공통비용의 가치",
    "OtherClaims" to "보통주 지분가치보다 선순위인 기타 청구권 가치",
    "Driver" to "가치 민감도를 측정할 때 변화시키는 핵심 가정",
    "NII" to "은행의 이자수익에서 이자비용을 뺀 순이자이익",
    "NIM" to "평균 이자수익자산 대비 순이자이익률",
    "DepositBeta" to "시장 기준금리 변화 중 예금금리에 전가된 비율",
    "PPNR" to "충당금 및 세금 차감 전 은행의 핵심영업이익",
    "Opex" to "사업 운영에 발생한 영업비용",
    "ChargeOffs" to "회수가 불가능해 대출채권과 충당금에서 상각한 금액",
    "CET1" to "보통주자본 중심의 핵심자기자본",
    "RWA" to "신용·시장·운영위험을 반영한 위험가중자산",
    "ROTCE" to "평균 유형보통주자본 대비 보통주주 귀속이익률",
    "CommonNI" to "보통주주에게 귀속되는 당기순이익",
    "IncurredLosses" to "해당 기간 보험사고로 발생한 손해액과 손해조정비",
    "ClosingCSM" to "보고기간 말 보험계약서비스마진",
    "OpeningCSM" to "보고기간 초 보험계약서비스마진",
    "FutureServiceChanges" to "미래 보험서비스 관련 가정 변경으로 인한 CSM 조정액",
    "CSMRelease" to "당기 보험서비스 제공에 따라 이익으로 인식한 CSM 금액",
    "Closure" to "광산·유전 등의 폐쇄 및 복구에 필요한 예상 의무",
    "ARO" to "자산폐기의무(Asset Retirement Obligation)의 현재가치",
    "ReserveLife" to "현재 생산량 기준 가채매장량이 유지되는 예상 연수",
    "RecoverableReserves" to "경제적·기술적으로 회수 가능한 확인 매장량",
    "EstimateGap" to "자체 실적추정치가 시장 컨센서스를 상회·하회하는 비율",
    "OurEstimate" to "분석자가 독립적으로 산출한 실적추정치",
    "Consensus" to "시장 참여자 추정치의 대표값",
    "Surprise" to "실제 실적이 시장 컨센서스를 상회·하회한 비율",
    "LiquidityRunway" to "가용유동성으로 현금소진을 감당할 수 있는 기간",
    "UndrawnFacilities" to "약정됐지만 아직 인출하지 않은 신용한도",
    "NearTermObligations" to "가까운 시일 내 지급해야 하는 확정 채무",
    "ShareholderYield" to "배당·순자사주매입·순부채상환을 합한 주주환원수익률",
    "Inflation" to "명목금리에서 실질금리를 분리할 때 사용하는 기대 인플레이션율",
    "USDNotional" to "달러 표시 계약의 명목금액",
    "KRW" to "환율의 원화 표시 통화단위",
    "USD" to "환율의 미국 달러 표시 통화단위",
    "SynergyPV" to "인수 후 기대되는 세후 시너지 현금흐름의 현재가치",
    "ProFormaEPS" to "인수와 신주발행을 반영한 합병 후 주당순이익",
    "CombinedNI" to "인수회사와 피인수회사의 조정 후 합산순이익",
    "BuyerEPS" to "인수 전 인수회사 단독 주당순이익",
    "PrimaryProceeds" to "IPO 신주발행으로 회사에 유입되는 총조달금액",
    "DealSize" to "신주와 구주매출을 합한 전체 공모금액",
    "Secondary" to "기존주주가 매각하는 구주 수 또는 구주매출 규모",
    "Dilution" to "신주발행으로 기존주주의 소유비율이 감소하는 비율",
    "RevisedEPS" to "실적서프라이즈를 반영해 수정한 주당순이익 전망",
    "ConsensusEPS" to "시장 컨센서스 주당순이익 전망",
    "Revenue_accrual" to "현금회수액과 매출채권 증감을 반영한 발생주의 매출액",
    "BadDebtExpense" to "회수불능 예상액을 당기손익에 인식한 대손상각비",
    "GoodsAvailable" to "기초재고와 당기 순매입을 합한 판매가능재고 원가",
    "SalvageValue" to "내용연수 종료 시 예상되는 자산의 잔존가치",
    "AccumulatedDepreciation" to "취득 이후 누적해 인식한 감가상각비 총액",
    "GainLoss" to "자산 처분대금과 처분시점 장부가액의 차이인 처분손익",
    "FaceValue" to "사채 만기에 상환하기로 약정한 액면원금",
    "CouponRate" to "사채 액면원금에 적용해 현금이자를 정하는 표면이율",
    "EffectiveRate" to "사채 장부금액에 적용해 이자비용을 인식하는 유효이자율",
    "WeightedAverageCommonShares" to "기간 중 유통기간을 가중한 평균 보통주식수",
    "WeightedAvgDilutedShares" to "잠재적 희석증권을 반영한 가중평균 희석주식수",
    "AssetTurnover" to "평균총자산 한 단위가 창출한 매출액 비율",
    "DebtToEquity" to "자기자본 대비 부채 규모를 나타내는 부채비율",
    "μ_A" to "자산 A의 기대수익률",
    "μ_B" to "자산 B의 기대수익률",
    "ρ_AB" to "자산 A와 B 수익률의 상관계수",
    "σ_A" to "자산 A 수익률의 표준편차",
    "σ_B" to "자산 B 수익률의 표준편차",
    "σ_p" to "포트폴리오 수익률의 표준편차",
    "Cov_AB" to "자산 A와 B 수익률의 공분산",
    "β_i" to "자산 i의 시장수익률 민감도 베타",
    "β_ik" to "자산 i의 APT 요인 k에 대한 민감도",
    "β_p" to "포트폴리오의 시장수익률 민감도 베타",
    "λ_k" to "APT 요인 k의 단위 노출당 위험프리미엄",
    "R_actual" to "평가기간에 실제로 실현된 자산수익률",
    "s_1" to "1년 만기 현물이자율",
    "s_2" to "2년 만기 현물이자율",
    "s_m" to "m년 만기 현물이자율",
    "s_n" to "n년 만기 현물이자율",
    "f_1" to "1년 후 시작되는 선도이자율",
    "f_m" to "m시점부터 n시점까지 적용되는 선도이자율",
    "m" to "선도금리 구간이 시작되는 만기연수",
    "days" to "이자 또는 운전자본 계산에 반영하는 실제 경과일수",
    "D_i" to "i번째 지급시점 현금흐름의 할인계수",
    "D_n" to "마지막 지급시점 n의 할인계수",
    "s" to "신용위험과 유동성 등을 반영한 채권 신용스프레드",
    "K_mkt" to "시장에 실제 제시된 선도계약가격",
    "ρ" to "두 수익률 또는 가격변화 사이의 상관계수",
    "multiplier" to "선물 1계약의 지수점수를 금액으로 바꾸는 계약승수",
    "α_t" to "t번째 이자기간의 day-count 기준 연환산 기간비율",
    "sgaMargin" to "매출액 대비 판매비와관리비 비율",
    "nwcRatio" to "매출액 대비 영업순운전자본 비율",
    "DebtIssued" to "해당 기간 신규 차입 또는 사채발행으로 유입된 현금",
    "PeerMedianMultiple" to "비교기업 집단에서 관측한 가치평가 배수의 중앙값",
    "TargetMetric" to "비교기업 배수를 적용할 평가대상 회사의 실적지표",
    "Price_s" to "시나리오 s에서 산출되는 주식 또는 자산가치",
    "MergerAcquisition" to "인수합병으로 연결범위에 편입·제외된 실적효과",
    "CorporateCost" to "개별 사업부에 배부되지 않은 본사 공통비용",
    "MonthlyCustomerGrossProfit" to "고객 한 명이 월간 창출하는 매출총이익",
    "SalesPerStore" to "점포 한 곳이 일정 기간 창출한 평균매출액",
    "AverageTicket" to "거래 한 건당 평균 결제금액",
    "TakeRate" to "총거래액 중 플랫폼이 매출로 인식하는 수수료율",
    "ContributionProfit" to "매출에서 직접 변동비를 차감한 공헌이익",
    "VariableCosts" to "매출 또는 거래량 변화에 비례해 증감하는 비용",
    "UnitContribution" to "제품 한 단위 판매가격에서 단위 변동비를 뺀 공헌이익",
    "Backlog_begin" to "기간 초 아직 이행하지 않은 수주잔고",
    "Backlog_end" to "신규수주·매출인식·취소·환율효과를 반영한 기간 말 수주잔고",
    "RevenueRecognized" to "backlog 중 당기 이행을 완료해 매출로 인식한 금액",
    "AccrualRatio" to "순이익 중 영업현금흐름으로 전환되지 않은 발생액 비중",
    "GrossReceivables" to "대손충당금 차감 전 총매출채권",
    "CurrentResearchDevelopment" to "당기에 비용 처리한 연구개발 지출액",
    "ResearchAmortization" to "가상 자산화한 과거 연구개발비의 당기 상각액",
    "NonOperatingGains" to "정상 영업활동 밖에서 발생한 비영업이익",
    "LeaseAdjustedNetDebt" to "리스부채를 포함하도록 조정한 순부채",
    "LeaseLiabilities" to "리스계약의 미래 지급의무를 현재가치로 측정한 부채",
    "PlanAssets" to "확정급여채무 지급을 위해 사외 적립한 연금자산의 공정가치",
    "CashTaxesPaid" to "해당 기간 실제 현금으로 납부한 법인세",
    "FVPreviousInterest" to "단계적 취득에서 기존 보유지분의 취득일 공정가치",
    "FVIdentifiableNetAssets" to "취득일 기준 식별가능 자산과 부채의 순공정가치",
    "CommonEquityValue" to "모든 선순위 청구권을 조정한 보통주 지분가치",
    "NonOperatingAssets" to "핵심 영업가치에 포함되지 않은 현금·투자자산 등 비영업자산",
    "OtherDebtLikeClaims" to "연금부족액 등 보통주보다 선순위인 기타 부채성 청구권",
    "NonInterestBearingOperatingLiabilities" to "이자를 지급하지 않는 영업 관련 부채",
    "RetentionRatio" to "순이익 중 배당하지 않고 회사에 유보하는 비율",
    "NetBorrowing" to "신규 차입액에서 부채상환액을 뺀 순차입액",
    "BeginningBVE" to "기간 초 보통주 장부가치",
    "BeginRE" to "기간 초 이익잉여금",
    "EndRE" to "순이익과 배당을 반영한 기간 말 이익잉여금",
    "StableReinvestmentRate" to "안정기 성장을 유지하는 데 필요한 NOPAT 재투자율",
    "ImpliedTerminalMultiple" to "계속가치를 안정기 실적지표로 나눈 내재 출구배수",
    "TerminalMetric" to "내재 계속가치 배수를 계산할 안정기 실적지표",
    "V_s" to "시나리오 s에서 산출되는 기업 또는 지분가치",
    "AvgEarningAssets" to "이자수익을 창출하는 평균 운용자산",
    "DepositCost" to "예금잔액에 지급하는 평균 조달금리",
    "BenchmarkRate" to "예금금리 전가율을 비교하는 시장 기준금리",
    "NoninterestIncome" to "수수료 등 이자 외 영업활동에서 발생한 수익",
    "Other" to "충당금 롤포워드의 별도 공시 기타 조정액",
    "AvgTCE" to "평균 유형보통주자본",
    "EarnedPremium" to "보험사가 보장서비스 제공을 완료해 수익으로 인식한 보험료",
    "CombinedRatio" to "손해율과 사업비율 등을 합한 손해보험 합산비율",
    "NewBusiness" to "당기 신계약에서 최초 인식한 보험계약서비스마진",
    "SolvencyRatio" to "요구자본 대비 손실흡수 가능한 가용자본 비율",
    "CurrentScaleRevenue" to "현재 생산·판매 규모에서 발생하는 매출액",
    "ThroughCycleMargin" to "경기 한 사이클의 고점·저점을 평균화한 정상 영업마진",
    "RealizedPrice" to "헤지·품질·운송조건 등을 반영해 실제 수취한 판매단가",
    "AssetAfterTaxFCF" to "개별 자원자산이 창출할 것으로 예상되는 세후 잉여현금흐름",
    "OtherAssets" to "핵심 자원자산 가치 외에 NAV에 더하는 기타 자산가치",
    "AnnualProduction" to "1년 동안 경제적으로 생산 가능한 자원 물량",
    "ExpectedTSR" to "주가상승과 배당을 합한 기대 총주주수익률",
    "CashBurn" to "사업 운영으로 일정 기간 순소진되는 현금액",
    "NetBuybacks" to "자사주 매입액에서 자사주 발행·처분액을 뺀 순매입액",
    "NetDebtRepayment" to "신규차입을 차감한 순부채상환액",
    "RealRate" to "물가상승 효과를 제거한 실질이자율",
    "NominalRate" to "물가상승 기대를 포함해 표시되는 명목이자율",
    "priceChangeBp" to "스프레드 변화로 예상되는 채권가격 변화의 bp 환산값",
    "spreadChangeBp" to "신용스프레드 변화폭의 베이시스포인트 값",
    "AfterTaxAnnualSynergy" to "인수 후 매년 반복될 것으로 예상되는 세후 시너지 현금흐름",
    "NetValueCreated" to "시너지 현재가치에서 통합비용을 차감한 순가치창출액",
    "IntegrationCost" to "인수 후 조직·시스템 통합에 필요한 일회성 비용",
    "ProFormaShares" to "인수대가 신주와 희석증권을 반영한 합병 후 주식수",
    "AccretionDilution" to "인수 전후 EPS의 증가 또는 감소 비율",
    "ExchangeRatio" to "피인수회사 1주당 지급하는 인수회사 주식 수",
    "OfferPriceTarget" to "피인수회사 주식 1주에 제시한 인수가격",
    "BuyerSharePrice" to "교환비율 산정 기준인 인수회사 주가",
    "OfferPrice" to "IPO 투자자에게 제시한 주당 공모가격",
    "PostMoneyShares" to "신주발행 직후의 총발행주식수",
    "PostMoneyMarketCap" to "공모가와 상장 후 주식수로 계산한 post-money 시가총액",
    "PostShares" to "공모 신주를 반영한 상장 후 주식수",
    "GrossPotentialRent" to "공실이 전혀 없다고 가정한 잠재총임대료",
    "VacancyLoss" to "공실과 임대료 미회수로 줄어드는 잠재 임대수익",
    "OperatingExpenses" to "부동산 운영에 직접 필요한 비용으로 금융비용·감가상각은 제외한 금액",
    "PropertyValue" to "NOI 또는 시장가격으로 평가한 부동산 가치",
    "AnnualDebtService" to "1년 동안 지급해야 하는 대출 원금과 이자의 합계",
    "InitialEquity" to "투자 시작시점에 투입한 자기자본금액",
    "ExpectedDownside" to "위험 발생확률을 반영한 확률가중 기대 하락액",
    "LossIfEvent" to "해당 위험사건이 실제 발생할 때 예상되는 가치 하락액",
    "r" to "기간 수익률·할인율 또는 이자율",
    "g" to "지속 성장률",
    "t" to "시간 또는 기간 번호",
    "n" to "전체 기간 수 또는 관측치 수",
    "T" to "만기까지의 기간",
    "K" to "행사가격 또는 약정금액",
    "S" to "기초자산 현물가격",
    "F" to "선도·선물가격",
    "σ" to "변동성 또는 표준편차",
    "β" to "시장 민감도 베타",
    "Δ" to "변화량 또는 델타",
)

private val VARIABLE_WORD_MEANINGS = mapOf(
    "revenue" to "매출액",
    "sales" to "매출액",
    "price" to "가격",
    "current" to "현재",
    "target" to "목표",
    "expected" to "기대",
    "actual" to "실제",
    "cash" to "현금",
    "collected" to "회수액",
    "begin" to "기초",
    "beginning" to "기초",
    "start" to "기초",
    "end" to "기말",
    "ending" to "기말",
    "average" to "평균",
    "avg" to "평균",
    "net" to "순액",
    "gross" to "총액",
    "income" to "이익",
    "expense" to "비용",
    "cost" to "비용",
    "debt" to "부채",
    "equity" to "자본·지분가치",
    "assets" to "자산",
    "liabilities" to "부채",
    "allowance" to "충당금",
    "inventory" to "재고자산",
    "purchases" to "매입액",
    "depreciation" to "감가상각비",
    "amortization" to "상각비",
    "carrying" to "장부",
    "value" to "가치",
    "market" to "시장",
    "cap" to "시가총액",
    "shares" to "주식 수",
    "dividend" to "배당",
    "dividends" to "배당금",
    "margin" to "마진율",
    "turnover" to "회전율",
    "rate" to "비율·금리",
    "ratio" to "비율",
    "multiple" to "평가배수",
    "tax" to "세금",
    "interest" to "이자",
    "operating" to "영업",
    "capital" to "자본",
    "invested" to "투하",
    "incremental" to "증분",
    "terminal" to "계속가치 시점",
    "growth" to "성장률",
    "return" to "수익률",
    "risk" to "위험",
    "variance" to "분산",
    "cov" to "공분산",
    "probability" to "확률",
    "loss" to "손실",
    "impact" to "영향액",
    "volume" to "물량",
    "quantity" to "수량",
    "capacity" to "생산능력",
    "utilization" to "가동률",
    "fixed" to "고정",
    "variable" to "변동",
    "contribution" to "공헌",
    "customers" to "고객 수",
    "stores" to "점포 수",
    "traffic" to "방문자 수",
    "conversion" to "전환율",
    "new" to "신규",
    "organic" to "유기적 성장",
    "reported" to "보고 기준",
    "adjusted" to "조정 기준",
    "normalized" to "정상화 기준",
    "provision" to "충당금 전입액",
    "recoveries" to "회수액",
    "premium" to "보험료",
    "required" to "요구",
    "available" to "가용",
    "annual" to "연간",
    "monthly" to "월간",
    "notional" to "명목원금",
    "spread" to "스프레드",
    "duration" to "듀레이션",
    "modified" to "수정",
    "loan" to "대출금",
    "distribution" to "분배금",
)
