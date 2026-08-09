package com.findone.app.ui

/**
 * Converts an untrusted one-line formula/relation value to safe Markdown without dropping text.
 *
 * Complete existing math/code spans are kept intact. Only a deliberately small symbolic alphabet
 * is promoted to LaTeX; prose, mixed-language relations, and ambiguous delimiter input fall back
 * to a code span containing the complete original value.
 */
fun safeMathMarkdown(rawValue: String): String {
    val value = rawValue.trim()
    if (value.isEmpty()) return ""
    if (isCompleteMathSpan(value) || isCompleteCodeSpan(value)) return value
    if (!isSafeSymbolicExpression(value)) return inlineCodeSpan(value)

    val latex = braceMulticharScripts(value)
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
        .replace(Regex("[ \\t]+"), " ")
        .trim()
    return "\$\$$latex\$\$"
}

private fun braceMulticharScripts(value: String): String = buildString(value.length + 8) {
    var index = 0
    while (index < value.length) {
        val operator = value[index]
        if (operator !in "_^" || index + 1 >= value.length) {
            append(operator)
            index += 1
            continue
        }

        append(operator)
        val scriptStart = index + 1
        when (value[scriptStart]) {
            '{' -> {
                val end = matchingDelimiterIndex(value, scriptStart)
                if (end < 0) {
                    append(value, scriptStart, value.length)
                    break
                }
                append(value, scriptStart, end + 1)
                index = end + 1
            }
            '(' -> {
                val end = matchingDelimiterIndex(value, scriptStart)
                if (end < 0) {
                    append(value, scriptStart, value.length)
                    break
                }
                append('{').append(value, scriptStart, end + 1).append('}')
                index = end + 1
            }
            else -> {
                val token = SCRIPT_TOKEN.find(value, scriptStart)
                    ?.takeIf { it.range.first == scriptStart }
                    ?.value
                if (token == null) {
                    append(value[scriptStart])
                    index = scriptStart + 1
                } else {
                    if (token.length > 1) append('{').append(token).append('}') else append(token)
                    index = scriptStart + token.length
                }
            }
        }
    }
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
    if (!SAFE_SYMBOLIC.matches(value) || !hasBalancedDelimiters(value)) return false
    if (value.contains("**") || value.contains("__")) return false

    val hasMathSignal = value.any { character ->
        character.isDigit() || character in MATH_SIGNALS
    }
    if (hasMathSignal) return true

    // A single identifier is unambiguous; multiple prose-like words are not promoted to math.
    return SINGLE_SYMBOL.matches(value)
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
    "[A-Za-z0-9_αβγδμρσλΔΣ∑()\\[\\]{}+\\-−–—×÷*/^%.,=≈≤≥<>² \\t]+",
)
private val SINGLE_SYMBOL = Regex("[A-Za-zαβγδμρσλΔΣ][A-Za-z0-9_αβγδμρσλΔΣ]*")
private val MATH_SIGNALS = setOf(
    '_', '+', '-', '−', '–', '—', '×', '÷', '*', '/', '^', '%', '=',
    '≈', '≤', '≥', '<', '>', '²', 'Σ', '∑',
)
private val BACKTICK_RUN = Regex("`+")
private val SCRIPT_TOKEN = Regex(
    "[A-Z]+[0-9]*(?![a-z])|[A-Z][a-z0-9]*|[a-z][a-z0-9]*|[0-9]+",
)
private const val SINGLE_DOLLAR = "\$"
private const val DOUBLE_DOLLAR = "\$\$"
