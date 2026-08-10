package com.findone.app.ui

/**
 * Converts an untrusted one-line formula/relation value to safe Markdown without dropping text.
 *
 * Complete existing math/code spans are kept intact. Symbolic expressions are promoted to LaTeX,
 * while Korean labels and prose stay as native Markdown text. JLatexMath does not ship a Hangul
 * math font, so a whole mixed-language relation must never be handed to the formula renderer.
 */
fun safeMathMarkdown(rawValue: String): String {
    val value = rawValue.trim()
    if (value.isEmpty()) return ""
    if (isCompleteMathSpan(value) || isCompleteCodeSpan(value)) return value
    val clauses = splitTopLevelFormulaClauses(value)
    if (clauses.size > 1) {
        return clauses.mapIndexed { index, clause ->
            val hasExplicitMathSignal = clause.any { character ->
                character.isDigit() || character in MATH_SIGNALS
            }
            val rendered = if (
                index > 0 &&
                !hasExplicitMathSignal &&
                HANGUL.containsMatchIn(clause)
            ) {
                clause
            } else if (index > 0 && !hasExplicitMathSignal) {
                inlineCodeSpan(clause)
            } else {
                safeMathMarkdown(clause)
            }
            if (rendered.startsWith("\$\$\n")) rendered else "- $rendered"
        }.joinToString("\n")
    }

    val (formula, punctuation) = splitTerminalPunctuation(value)
    val labeled = renderLabeledMath(formula)
    val safeExpression = isSafeSymbolicExpression(formula)
    if (!isCompleteMathSpan(formula) && !isCompleteCodeSpan(formula) && labeled == null && !safeExpression) {
        return nativeMixedMathMarkdown(value) ?: inlineCodeSpan(value)
    }
    val rendered = when {
        isCompleteMathSpan(formula) || isCompleteCodeSpan(formula) -> formula
        labeled != null -> labeled
        !safeExpression -> inlineCodeSpan(formula)
        else -> latexMarkdown(formula)
    }
    if (punctuation.isEmpty()) return rendered
    return if ('\n' in rendered && rendered.endsWith("\$\$")) {
        if (punctuation.all { it == '.' || it == '。' }) rendered else "$rendered\n$punctuation"
    } else {
        rendered + punctuation
    }
}

private fun splitTerminalPunctuation(value: String): Pair<String, String> {
    var punctuationStart = value.length
    while (punctuationStart > 0 && value[punctuationStart - 1] in TERMINAL_PUNCTUATION) {
        punctuationStart -= 1
    }
    if (punctuationStart == value.length || value.substring(0, punctuationStart).isBlank()) {
        return value to ""
    }
    return value.substring(0, punctuationStart).trimEnd() to value.substring(punctuationStart)
}

private fun splitTopLevelFormulaClauses(value: String): List<String> {
    val clauses = mutableListOf<String>()
    val stack = ArrayDeque<Char>()
    var segmentStart = 0

    fun addClause(end: Int) {
        value.substring(segmentStart, end).trim().takeIf(String::isNotEmpty)?.let(clauses::add)
    }

    value.forEachIndexed { index, character ->
        when (character) {
            '(', '[', '{' -> stack.addLast(character)
            ')' -> if (stack.removeLastOrNull() != '(') return listOf(value)
            ']' -> if (stack.removeLastOrNull() != '[') return listOf(value)
            '}' -> if (stack.removeLastOrNull() != '{') return listOf(value)
            ';', '\n', '\r' -> if (stack.isEmpty()) {
                addClause(index)
                segmentStart = index + 1
            }
            ',' -> if (stack.isEmpty() && !value.isDigitGroupingComma(index)) {
                val before = value.substring(segmentStart, index)
                val after = value.substring(index + 1)
                if (
                    COMPARISON_OPERATOR.containsMatchIn(before) &&
                    COMPARISON_OPERATOR.containsMatchIn(after)
                ) {
                    addClause(index)
                    segmentStart = index + 1
                }
            }
            '.', '!', '?', '。' -> if (
                stack.isEmpty() &&
                !value.isDecimalPoint(index) &&
                value.substring(index + 1).isNotBlank()
            ) {
                val before = value.substring(segmentStart, index)
                if (COMPARISON_OPERATOR.containsMatchIn(before)) {
                    addClause(index + 1)
                    segmentStart = index + 1
                }
            }
        }
    }
    if (stack.isNotEmpty()) return listOf(value)
    addClause(value.length)
    return clauses.ifEmpty { listOf(value) }
}

private fun String.isDigitGroupingComma(index: Int): Boolean =
    index > 0 &&
        this[index - 1].isDigit() &&
        index + 3 < length &&
        this[index + 1].isDigit() &&
        this[index + 2].isDigit() &&
        this[index + 3].isDigit() &&
        (index + 4 == length || !this[index + 4].isDigit())

private fun String.isDecimalPoint(index: Int): Boolean =
    this[index] == '.' &&
        index > 0 &&
        index + 1 < length &&
        this[index - 1].isDigit() &&
        this[index + 1].isDigit()

private fun hasUnsafeTopLevelPunctuation(value: String): Boolean {
    val stack = ArrayDeque<Char>()
    value.forEachIndexed { index, character ->
        when (character) {
            '(', '[', '{' -> stack.addLast(character)
            ')', ']', '}' -> stack.removeLastOrNull()
            ',' -> if (stack.isEmpty() && !value.isDigitGroupingComma(index)) return true
            '.', '!', '?', '。' -> if (
                stack.isEmpty() &&
                !value.isDecimalPoint(index) &&
                value.substring(index + 1).isNotBlank()
            ) {
                return true
            }
        }
    }
    return false
}

private fun latexMarkdown(value: String): String {
    val latex = toLatex(value)
    if (latexRenderWeight(latex) <= MAX_INLINE_MATH_WEIGHT) return "\$\$$latex\$\$"
    return semanticFormulaLines(value).joinToString("\n\n") { lineSource ->
        "\$\$\n${toLatex(lineSource)}\n\$\$"
    }
}

/** Estimate visible width from transformed TeX instead of counting unrelated source characters. */
private fun latexRenderWeight(latex: String): Int {
    val visible = LATEX_UPRIGHT_GROUP.replace(latex, "$1")
        .let { LATEX_NAMED_SYMBOL.replace(it, "x") }
        .replace("\\%", "%")
        .replace("\\&", "&")
    return visible.count { character -> !character.isWhitespace() && character !in "{}" }
}

/** Split a long top-level sum at semantic operator boundaries into independent block spans. */
private fun semanticFormulaLines(source: String): List<String> {
    val stack = ArrayDeque<Char>()
    val breakpoints = mutableListOf<Int>()
    source.forEachIndexed { index, character ->
        when (character) {
            '(', '[', '{' -> stack.addLast(character)
            ')' -> if (stack.lastOrNull() == '(') stack.removeLast()
            ']' -> if (stack.lastOrNull() == '[') stack.removeLast()
            '}' -> if (stack.lastOrNull() == '{') stack.removeLast()
            '+', '-', '−', '–', '—', '×', '*' -> if (
                stack.isEmpty() &&
                index > 0 &&
                source[index - 1] !in SEMANTIC_BREAK_PREDECESSORS
            ) {
                breakpoints += index
            }
        }
    }
    if (breakpoints.isEmpty()) return listOf(source)

    val parts = buildList {
        add(source.substring(0, breakpoints.first()))
        breakpoints.zipWithNext().forEach { (start, end) -> add(source.substring(start, end)) }
        add(source.substring(breakpoints.last()))
    }
    val lines = mutableListOf<String>()
    var current = ""
    parts.forEach { part ->
        val candidate = current + part
        if (current.isNotEmpty() && latexRenderWeight(toLatex(candidate)) > MAX_BLOCK_LINE_WEIGHT) {
            lines += current.trim()
            current = part
        } else {
            current = candidate
        }
    }
    current.trim().takeIf(String::isNotEmpty)?.let(lines::add)
    return if (lines.size > 1) lines else listOf(source)
}

private fun toLatex(value: String): String {
    val canonicalValue = canonicalSymbolicSource(value)
    val rooted = checkNotNull(replaceSquareRoots(canonicalValue))
    val scripted = checkNotNull(braceMulticharScripts(rooted))
    return scripted
        .replace("×", " \\times ")
        .replace("÷", " \\div ")
        .replace("−", "-")
        .replace("–", "-")
        .replace("—", "-")
        .replace("≈", " \\approx ")
        .replace("≤", " \\le ")
        .replace("≥", " \\ge ")
        .replace("²", "^{2}")
        .replace("%", "\\%")
        .replace("α", "\\alpha ")
        .replace("β", "\\beta ")
        .replace("γ", "\\gamma ")
        .replace("δ", "\\delta ")
        .replace("μ", "\\mu ")
        .replace("ρ", "\\rho ")
        .replace("σ", "\\sigma ")
        .replace("λ", "\\lambda ")
        .replace("Δ", "\\Delta ")
        .replace("Σ", "\\sum ")
        .replace("∑", "\\sum ")
        .replace("Π", "\\prod ")
        .replace("∂", "\\partial ")
        .replace("±", "\\pm ")
        .replace("&", "\\&")
        .let { DIGIT_GROUPING_COMMA.replace(it, "{,}") }
        .let(::uprightAsciiIdentifiers)
        .replace(Regex("[ \\t]+"), " ")
        .trim()
}

private fun replaceSquareRoots(value: String): String? = buildString(value.length + 8) {
    var index = 0
    while (index < value.length) {
        if (value[index] != '√') {
            append(value[index++])
            continue
        }

        val atomStart = index + 1
        if (atomStart >= value.length) return null
        val atomEnd = if (value[atomStart] == '(') {
            matchingDelimiterIndex(value, atomStart).takeIf { it >= 0 } ?: return null
        } else {
            (rootAtomEndExclusive(value, atomStart) ?: return null) - 1
        }
        append("\\sqrt{").append(value, atomStart, atomEnd + 1).append('}')
        index = atomEnd + 1
    }
}

private fun rootAtomEndExclusive(value: String, start: Int): Int? {
    val base = ROOT_BASE_TOKEN.find(value, start)
        ?.takeIf { it.range.first == start }
        ?: return null
    var cursor = base.range.last + 1
    while (cursor < value.length) {
        cursor = when (value[cursor]) {
            '²' -> cursor + 1
            '_', '^' -> scriptEndExclusive(value, cursor + 1) ?: return null
            else -> return cursor
        }
    }
    return cursor
}

private fun scriptEndExclusive(value: String, start: Int): Int? {
    if (start >= value.length) return null
    return when (value[start]) {
        '{', '(' -> {
            val end = matchingDelimiterIndex(value, start)
            if (end <= start + 1) null else end + 1
        }
        '+', '-', '−', '–', '—' -> {
            var cursor = start + 1
            while (cursor < value.length && value[cursor].isDigit()) cursor += 1
            if (cursor == start + 1) null else cursor
        }
        else -> SCRIPT_TOKEN.find(value, start)
            ?.takeIf { it.range.first == start }
            ?.let { it.range.last + 1 }
    }
}

/**
 * Keeps descriptive labels readable while rendering only their symbolic right-hand side.
 * An unsafe right-hand side is preserved in full as a code span.
 */
private fun renderLabeledMath(value: String): String? {
    val colonIndex = value.indexOfFirst { it == ':' || it == '：' }
    if (colonIndex > 0) {
        val label = value.substring(0, colonIndex).trim()
        val expression = value.substring(colonIndex + 1).trim()
        if (
            isReadableLabel(label) &&
            expression.isNotEmpty() &&
            looksLikeFormula(expression)
        ) {
            return labeledMarkdown(label, value[colonIndex].toString(), expression)
        }
    }

    val comparison = COMPARISON_OPERATOR.find(value) ?: return null
    val label = value.substring(0, comparison.range.first).trim()
    val expression = value.substring(comparison.range.last + 1).trim()
    if (
        expression.isEmpty() ||
        !isReadableLabel(label) ||
        !hasProseLikeComparisonLabel(value)
    ) {
        return null
    }
    return labeledMarkdown(label, comparison.value, expression)
}

private fun labeledMarkdown(label: String, separator: String, expression: String): String {
    val renderedExpression = when {
        isCompleteMathSpan(expression) || isCompleteCodeSpan(expression) -> expression
        isSafeSymbolicExpression(expression) -> latexMarkdown(expression)
        else -> nativeMixedMathMarkdown(expression) ?: inlineCodeSpan(expression)
    }
    val prefix = if (separator == ":" || separator == "：") {
        "**${escapeMarkdownLabel(label)}**$separator"
    } else {
        "**${escapeMarkdownLabel(label)}** $separator"
    }
    return if (renderedExpression.startsWith("\$\$\n")) {
        "$prefix\n\n$renderedExpression"
    } else {
        "$prefix $renderedExpression"
    }
}

private fun looksLikeFormula(value: String): Boolean =
    isCompleteMathSpan(value) ||
        isCompleteCodeSpan(value) ||
        isSafeSymbolicExpression(value) ||
        value.any { it in COMPARISON_SIGNALS }

/**
 * Keeps Hangul in the native TextView and promotes only unambiguous symbolic atoms. Operators
 * between native terms deliberately remain native text: they are readable without asking the
 * formula renderer to synthesize glyphs it does not contain.
 */
private fun nativeMixedMathMarkdown(value: String): String? {
    if (!HANGUL.containsMatchIn(value)) return null
    val candidate = canonicalSymbolicSource(value)
    if (!hasBalancedDelimiters(candidate) || candidate.any { it == '$' || it == '`' }) return null
    if (!candidate.any { character -> character.isDigit() || character in MATH_SIGNALS }) return candidate

    val output = StringBuilder(candidate.length + 16)
    var cursor = 0
    MIXED_SYMBOL_ATOM.findAll(candidate).forEach { match ->
        output.append(candidate, cursor, match.range.first)
        val atom = match.value
        output.append(if (isSafeSymbolicExpression(atom)) latexMarkdown(atom) else atom)
        cursor = match.range.last + 1
    }
    output.append(candidate, cursor, candidate.length)
    return output.toString()
}

private fun isReadableLabel(value: String): Boolean =
    value.any(Char::isLetter) && value.all { character ->
        character.isLetterOrDigit() || character.isWhitespace() || character in LABEL_PUNCTUATION
    }

private fun escapeMarkdownLabel(value: String): String = buildString(value.length + 4) {
    value.forEach { character ->
        if (character in LABEL_MARKDOWN_ESCAPES) append('\\')
        append(character)
    }
}

/** Make semantic multi-letter identifiers upright without rewriting generated TeX commands. */
private fun uprightAsciiIdentifiers(value: String): String = buildString(value.length + 16) {
    var index = 0
    while (index < value.length) {
        if (value[index] == '\\') {
            append(value[index++])
            while (index < value.length && value[index].isAsciiLetter()) append(value[index++])
            continue
        }
        if (!value[index].isAsciiLetter()) {
            append(value[index++])
            continue
        }

        val tokenStart = index
        if (index > 0 && value[index - 1] in "_^") {
            // braceMulticharScripts already braces every multi-character script, so an
            // unbraced script here is exactly one atom (for example p_sV_s).
            index += 1
        } else {
            while (index < value.length && (value[index].isAsciiLetter() || value[index].isDigit())) {
                index += 1
            }
        }
        val token = value.substring(tokenStart, index)
        val letterCount = token.count { it.isAsciiLetter() }
        val nextNonSpace = value.indexOfFirstFrom(index) { !it.isWhitespace() }
        when {
            token in LATEX_FUNCTIONS && nextNonSpace >= 0 && value[nextNonSpace] == '(' -> {
                append('\\').append(token)
            }
            letterCount > 1 -> append("\\mathrm{").append(token).append('}')
            else -> append(token)
        }
    }
}

private fun Char.isAsciiLetter(): Boolean = this in 'A'..'Z' || this in 'a'..'z'

private inline fun String.indexOfFirstFrom(start: Int, predicate: (Char) -> Boolean): Int {
    for (index in start until length) if (predicate(this[index])) return index
    return -1
}

private fun braceMulticharScripts(value: String): String? {
    val output = StringBuilder(value.length + 8)
    var index = 0
    while (index < value.length) {
        val operator = value[index]
        if (operator !in "_^") {
            output.append(operator)
            index += 1
            continue
        }
        if (index + 1 >= value.length) return null

        output.append(operator)
        val scriptStart = index + 1
        val scriptEnd = scriptEndExclusive(value, scriptStart) ?: return null
        when (value[scriptStart]) {
            '{' -> {
                val inner = braceMulticharScripts(value.substring(scriptStart + 1, scriptEnd - 1))
                    ?: return null
                output.append('{').append(inner).append('}')
            }
            '(' -> {
                val inner = braceMulticharScripts(value.substring(scriptStart + 1, scriptEnd - 1))
                    ?: return null
                output.append("{(").append(inner).append(")}")
            }
            else -> {
                val token = value.substring(scriptStart, scriptEnd)
                if (token.length > 1) output.append('{').append(token).append('}')
                else output.append(token)
            }
        }
        index = scriptEnd
    }
    return output.toString()
}

private fun matchingDelimiterIndex(value: String, start: Int): Int {
    val opening = value[start]
    val closing = when (opening) {
        '(' -> ')'
        '[' -> ']'
        '{' -> '}'
        else -> return -1
    }
    var depth = 0
    for (index in start until value.length) {
        when (value[index]) {
            opening -> depth += 1
            closing -> {
                depth -= 1
                if (depth == 0) return index
            }
        }
    }
    return -1
}

private fun isSafeSymbolicExpression(value: String): Boolean {
    val canonicalValue = canonicalSymbolicSource(value)
    if (!SAFE_SYMBOLIC.matches(canonicalValue) || !hasBalancedDelimiters(canonicalValue)) return false
    if (value.contains("**") || value.contains("__")) return false
    if (hasProseLikeComparisonLabel(value)) return false
    if (hasUnsafeTopLevelPunctuation(value)) return false
    val rooted = replaceSquareRoots(canonicalValue) ?: return false
    val scripted = braceMulticharScripts(rooted) ?: return false
    if (REPEATED_TEX_SCRIPT.containsMatchIn(scripted)) return false

    val hasMathSignal = value.any { character ->
        character.isDigit() || character in MATH_SIGNALS
    }
    if (hasMathSignal) return true

    // A single identifier is unambiguous; multiple prose-like words are not promoted to math.
    return SINGLE_SYMBOL.matches(value) || PARENTHESIZED_SINGLE_SYMBOL.matches(value)
}

private fun canonicalSymbolicSource(value: String): String =
    KNOWN_SYMBOLIC_REWRITES.fold(value) { result, (original, canonical) ->
        result.replace(original, canonical)
    }.let { source ->
        KNOWN_SYMBOLIC_REGEX_REWRITES.fold(source) { result, (pattern, canonical) ->
            pattern.replace(result, canonical)
        }
    }

/**
 * TeX discards ordinary spaces and treats hyphens as subtraction. A comparison label such as
 * "Call payoff" or "Mid-year PV" must therefore stay outside the math span.
 */
private fun hasProseLikeComparisonLabel(value: String): Boolean {
    val comparison = COMPARISON_OPERATOR.find(value) ?: return false
    val label = value.substring(0, comparison.range.first)
    return PROSE_LHS_TOKEN_GAP.containsMatchIn(label) ||
        PROSE_HYPHENATED_LABEL.containsMatchIn(label)
}

private fun hasBalancedDelimiters(value: String): Boolean {
    val stack = ArrayDeque<Char>()
    value.forEach { character ->
        when (character) {
            '(', '[', '{' -> stack.addLast(character)
            ')' -> if (stack.removeLastOrNull() != '(') return false
            ']' -> if (stack.removeLastOrNull() != '[') return false
            '}' -> if (stack.removeLastOrNull() != '{') return false
        }
    }
    return stack.isEmpty()
}

private fun isCompleteMathSpan(value: String): Boolean {
    val delimiter = when {
        value.startsWith(DOUBLE_DOLLAR) && value.endsWith(DOUBLE_DOLLAR) && value.length > 4 -> DOUBLE_DOLLAR
        value.startsWith('$') && !value.startsWith(DOUBLE_DOLLAR) && value.endsWith('$') && value.length > 2 -> SINGLE_DOLLAR
        else -> return false
    }
    val content = value.substring(delimiter.length, value.length - delimiter.length)
    if (content.isBlank()) return false
    return !containsUnescapedDollar(content)
}

private fun containsUnescapedDollar(value: String): Boolean {
    value.forEachIndexed { index, character ->
        if (character == '$' && precedingBackslashCount(value, index) % 2 == 0) return true
    }
    return false
}

private fun isCompleteCodeSpan(value: String): Boolean {
    if (!value.startsWith('`')) return false
    val fenceLength = value.indexOfFirst { it != '`' }.let { if (it < 0) value.length else it }
    if (fenceLength == value.length || value.length <= fenceLength * 2) return false
    val fence = "`".repeat(fenceLength)
    if (!value.endsWith(fence)) return false
    val content = value.substring(fenceLength, value.length - fenceLength)
    return content.isNotEmpty() && !content.contains(fence)
}

private fun inlineCodeSpan(value: String): String {
    val longestRun = BACKTICK_RUN.findAll(value).maxOfOrNull { it.value.length } ?: 0
    val fence = "`".repeat(longestRun + 1)
    val needsPadding = value.startsWith('`') || value.endsWith('`') ||
        (value.startsWith(' ') && value.endsWith(' '))
    return if (needsPadding) "$fence $value $fence" else "$fence$value$fence"
}

private fun precedingBackslashCount(value: String, index: Int): Int {
    var cursor = index - 1
    while (cursor >= 0 && value[cursor] == '\\') cursor--
    return index - cursor - 1
}

private val SAFE_SYMBOLIC = Regex(
    "[A-Za-z0-9_αβγδμρσλΔΣΠ∑∂()\\[\\]{}+\\-−–—×÷*/^%.,=≈≤≥<>²√±& \\t]+",
)
private val SINGLE_SYMBOL = Regex("[A-Za-zαβγδμρσλΔΣΠ][A-Za-z0-9_αβγδμρσλΔΣΠ]*")
private val PARENTHESIZED_SINGLE_SYMBOL = Regex(
    "\\([A-Za-zαβγδμρσλΔΣΠ∑∂][A-Za-z0-9_αβγδμρσλΔΣΠ∑∂]*\\)",
)
private val MATH_SIGNALS = setOf(
    '_', '+', '-', '−', '–', '—', '×', '÷', '*', '/', '^', '%', '=',
    '≈', '≤', '≥', '<', '>', '²', 'Σ', 'Π', '∑', '√', '∂', '±', '&',
)
private val COMPARISON_SIGNALS = setOf('=', '≈', '≤', '≥', '<', '>')
private val COMPARISON_OPERATOR = Regex("≤|≥|≈|<=|>=|=|<|>")
private val PROSE_LHS_TOKEN_GAP = Regex(
    """[A-Za-z0-9_αβγδμρσλΔΣ]\s+[A-Za-z0-9_αβγδμρσλΔΣ]""",
)
private val PROSE_HYPHENATED_LABEL = Regex("[A-Za-z]{2,}[-–—][A-Za-z]{2,}")
private val DIGIT_GROUPING_COMMA = Regex("""(?<=\d),(?=\d{3}(?:\D|$))""")
private val BACKTICK_RUN = Regex("`+")
private val SCRIPT_TOKEN = Regex(
    "[A-Z]+[0-9]*(?![a-z])|[A-Z][a-z0-9]*|[a-z][a-z0-9]*|[0-9]+",
)
private val ROOT_BASE_TOKEN = Regex(
    "[A-Za-z][A-Za-z0-9]*|[αβγδμρσλΔΣΠ]",
)
private const val SINGLE_DOLLAR = "\$"
private const val DOUBLE_DOLLAR = "\$\$"
private const val MAX_INLINE_MATH_WEIGHT = 40
private const val MAX_BLOCK_LINE_WEIGHT = 40
private val TERMINAL_PUNCTUATION = setOf('.', '!', '?', '。')
private val LATEX_FUNCTIONS = setOf("max", "min", "ln", "log")
private val LABEL_PUNCTUATION = setOf('_', '-', '–', '—', '/', '&', '(', ')', '.', ',')
private val LABEL_MARKDOWN_ESCAPES = setOf('\\', '`', '*', '_', '[', ']')
private val HANGUL = Regex("[가-힣]")
private val MIXED_SYMBOL_ATOM = Regex(
    "(?<![A-Za-z0-9_])(?:\\([A-Za-zαβγδμρσλΔΣΠ∑∂][A-Za-z0-9_αβγδμρσλΔΣΠ∑∂]*\\)|" +
        "[A-Za-zαβγδμρσλΔΣΠ∑∂][A-Za-z0-9_αβγδμρσλΔΣΠ∑∂]*|" +
        "[0-9]+(?:\\.[0-9]+)?%?)(?![A-Za-z0-9_])",
)
private val LATEX_UPRIGHT_GROUP = Regex("""\\mathrm\{([^{}]*)\}""")
private val LATEX_NAMED_SYMBOL = Regex(
    """\\(?:alpha|beta|gamma|delta|mu|rho|sigma|lambda|Delta|times|div|approx|le|ge|pm|partial|sum|prod)""",
)
private val SEMANTIC_BREAK_PREDECESSORS = setOf(
    '=', '<', '>', '≈', '≤', '≥', '^', '_', '+', '-', '−', '–', '—', '×', '÷', '*', '/',
    '(', ',', '[', '{',
)
private val REPEATED_TEX_SCRIPT = Regex(
    """(?:_(?:\{[^{}]*\}|[A-Za-z0-9])){2}|(?:\^(?:\{[^{}]*\}|[A-Za-z0-9])){2}""",
)
private val KNOWN_SYMBOLIC_REWRITES = listOf(
    "(V_PD_P)/(V_FD_F)" to "(V_P×D_P)/(V_F×D_F)",
    "uS_0" to "u×S_0",
    "dS_0" to "d×S_0",
    "RS_0" to "R×S_0",
    "qV_u" to "q×V_u",
    "(1−q)V_d" to "(1−q)×V_d",
    "wR_A" to "w×R_A",
    "(1−w)R_B" to "(1−w)×R_B",
    "(1-w)R_B" to "(1-w)×R_B",
    "wD_1" to "w×D_1",
    "(1−w)D_2" to "(1−w)×D_2",
    "(1-w)D_2" to "(1-w)×D_2",
    "Ke^(−rT)N(" to "K×e^(−r×T)×N(",
    "Ke^(−rT)" to "K×e^(−r×T)",
    "Ke^(-rT)" to "K×e^(-r×T)",
    "S_0N(" to "S_0×N(",
    "(r+σ²/2)T" to "(r+σ²/2)×T",
    "σ√T" to "σ×√T",
)
private val KNOWN_SYMBOLIC_REGEX_REWRITES = listOf(
    Regex("(?<![A-Za-z0-9_])rT(?![A-Za-z0-9_])") to "r×T",
    Regex("(?<![A-Za-z0-9_])wE(?![A-Za-z0-9_])") to "w_E",
    Regex("(?<![A-Za-z0-9_])wD(?![A-Za-z0-9_])") to "w_D",
    Regex("(?<![A-Za-z0-9_])ke(?![A-Za-z0-9_])") to "k_e",
    Regex("(?<![A-Za-z0-9_])kd(?![A-Za-z0-9_])") to "k_d",
)
