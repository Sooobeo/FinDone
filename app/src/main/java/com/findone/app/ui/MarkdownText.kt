package com.findone.app.ui

import android.graphics.Typeface
import android.text.TextUtils
import android.text.method.LinkMovementMethod
import android.util.Log
import android.util.TypedValue
import android.view.ViewGroup
import android.widget.TextView
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.LocalContentColor
import androidx.compose.material3.LocalTextStyle
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.isSpecified
import androidx.compose.ui.viewinterop.AndroidView
import io.noties.markwon.Markwon
import kotlin.math.max

private val blockOrInlineLatex = Regex("""(?s)\$\$(.+?)\$\$""")
private val singleDollarLatex = Regex("""(?<!\$)\$([^$\n]+?)\$(?!\$)""")
private data class MarkdownRenderKey(val markdown: String, val textSizePx: Float, val textColor: Int)

/**
 * Renders CommonMark without a WebView. Formula spans are converted to code-styled text before
 * Markwon sees them. This deliberately avoids jlatexmath's asynchronous Drawable/Canvas path,
 * which can terminate the Android process after a detail screen starts drawing.
 */
@Composable
fun MarkdownText(
    markdown: String,
    modifier: Modifier = Modifier,
    style: TextStyle = LocalTextStyle.current,
    color: Color = LocalContentColor.current,
    maxLines: Int = Int.MAX_VALUE,
    linksEnabled: Boolean = true,
) {
    require(maxLines > 0) { "maxLines must be greater than zero." }
    val context = LocalContext.current
    val density = LocalDensity.current
    val resolvedStyle = LocalTextStyle.current.merge(style)
    val textSizePx = with(density) {
        if (resolvedStyle.fontSize.isSpecified) resolvedStyle.fontSize.toPx()
        else 16f * density.density
    }
    val lineHeightPx = with(density) {
        if (resolvedStyle.lineHeight.isSpecified) resolvedStyle.lineHeight.toPx()
        else textSizePx * 1.4f
    }
    val textColor = color.toArgb()
    val applicationContext = context.applicationContext
    val markdownRenderer = remember(applicationContext) {
        Markwon.create(applicationContext)
    }
    val normalizedMarkdown = remember(markdown) { deviceSafeMarkdown(markdown) }
    val latexAccessibilityText = remember(markdown) {
        if (containsLatex(markdown)) markdownAccessibilityText(markdown) else null
    }
    val renderKey = MarkdownRenderKey(normalizedMarkdown, textSizePx, textColor)

    AndroidView(
        modifier = modifier.fillMaxWidth(),
        factory = { viewContext ->
            TextView(viewContext).apply {
                layoutParams = ViewGroup.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT,
                    ViewGroup.LayoutParams.WRAP_CONTENT,
                )
                includeFontPadding = false
                highlightColor = android.graphics.Color.TRANSPARENT
            }
        },
        update = { textView ->
            textView.setTextColor(textColor)
            textView.setTextSize(TypedValue.COMPLEX_UNIT_PX, textSizePx)
            textView.setLineSpacing(max(0f, lineHeightPx - textSizePx), 1f)
            textView.maxLines = maxLines
            textView.ellipsize = if (maxLines == Int.MAX_VALUE) null else TextUtils.TruncateAt.END
            textView.linksClickable = linksEnabled
            textView.movementMethod = if (linksEnabled) LinkMovementMethod.getInstance() else null
            textView.isClickable = linksEnabled
            if (!linksEnabled) textView.isLongClickable = false
            textView.contentDescription = latexAccessibilityText
            textView.setTypeface(
                Typeface.DEFAULT,
                if ((resolvedStyle.fontWeight ?: FontWeight.Normal) >= FontWeight.SemiBold) {
                    Typeface.BOLD
                } else {
                    Typeface.NORMAL
                },
            )
            if (textView.tag != renderKey) {
                runCatching { markdownRenderer.setMarkdown(textView, normalizedMarkdown) }
                    .onFailure { error ->
                        reportMarkdownRenderingError(normalizedMarkdown, error)
                        textView.text = markdownPlainTextFallback(normalizedMarkdown)
                    }
                textView.tag = renderKey
            }
        },
    )
}

private fun reportMarkdownRenderingError(markdown: String, error: Throwable) {
    val diagnosticKey = "${markdown.length}:${markdown.hashCode().toUInt().toString(16)}"
    Log.e(
        "FinDoneMarkdown",
        "Markdown renderer failed; displaying plain text (content=$diagnosticKey)",
        error,
    )
}

internal fun markdownPlainTextFallback(markdown: String): String =
    markdownAccessibilityText(markdown)
        .replace(Regex("[ \\t]+([.,;:!?。])"), "$1")
        .ifBlank { markdown.trim() }

/**
 * Converts formula delimiters to ordinary Markdown code spans/blocks. The result is safe to hand
 * to Markwon core because it contains no nodes that can invoke the jlatexmath Drawable loader.
 */
internal fun deviceSafeMarkdown(markdown: String): String {
    val normalized = normalizeInlineLatex(markdown)
    if ("$$" !in normalized) return normalized

    val output = StringBuilder(normalized.length + 32)
    var lineStart = 0
    var fencedCode: MarkdownFence? = null
    var blockLatex = false
    var inlineCodeDelimiterLength = 0
    while (lineStart < normalized.length) {
        val newlineIndex = normalized.indexOf('\n', lineStart)
        val lineEnd = if (newlineIndex >= 0) newlineIndex else normalized.length
        val contentEnd = if (lineEnd > lineStart && normalized[lineEnd - 1] == '\r') {
            lineEnd - 1
        } else {
            lineEnd
        }
        val line = normalized.substring(lineStart, contentEnd)
        val lineEnding = when {
            newlineIndex < 0 -> ""
            contentEnd < lineEnd -> "\r\n"
            else -> "\n"
        }
        val fenceRun = markdownFenceRun(line)

        when {
            fencedCode != null -> {
                output.append(line)
                if (
                    fenceRun != null &&
                    fenceRun.marker == fencedCode.marker &&
                    fenceRun.length >= fencedCode.minimumLength &&
                    fenceRun.remainderIsBlank
                ) {
                    fencedCode = null
                }
            }
            blockLatex -> {
                if (line.trim() == "$$") {
                    output.append(line.substringBefore("$$")).append("````")
                    blockLatex = false
                } else {
                    output.append(line)
                }
            }
            inlineCodeDelimiterLength > 0 -> {
                val safe = deviceSafeInlineLatexLine(line, inlineCodeDelimiterLength)
                output.append(safe.markdown)
                inlineCodeDelimiterLength = safe.inlineCodeDelimiterLength
            }
            fenceRun != null -> {
                output.append(line)
                fencedCode = MarkdownFence(fenceRun.marker, fenceRun.length)
            }
            line.trim() == "$$" -> {
                output.append(line.substringBefore("$$")).append("````text")
                blockLatex = true
            }
            isIndentedCodeLine(line) -> output.append(line)
            else -> {
                val safe = deviceSafeInlineLatexLine(line, inlineCodeDelimiterLength)
                output.append(safe.markdown)
                inlineCodeDelimiterLength = safe.inlineCodeDelimiterLength
            }
        }
        output.append(lineEnding)
        lineStart = if (newlineIndex >= 0) newlineIndex + 1 else normalized.length
    }
    return output.toString()
}

private fun deviceSafeInlineLatexLine(
    line: String,
    initialInlineCodeDelimiterLength: Int,
): NormalizedInlineLatexLine {
    val output = StringBuilder(line.length + 8)
    var index = 0
    var inlineCodeDelimiterLength = initialInlineCodeDelimiterLength
    while (index < line.length) {
        if (line[index] == '`') {
            var runEnd = index
            while (runEnd < line.length && line[runEnd] == '`') runEnd += 1
            val runLength = runEnd - index
            output.append(line, index, runEnd)
            inlineCodeDelimiterLength = when {
                inlineCodeDelimiterLength == 0 -> runLength
                inlineCodeDelimiterLength == runLength -> 0
                else -> inlineCodeDelimiterLength
            }
            index = runEnd
            continue
        }
        if (inlineCodeDelimiterLength > 0) {
            output.append(line[index])
            index += 1
            continue
        }
        if (line[index] == '\\') {
            output.append(line[index])
            if (index + 1 < line.length) {
                output.append(line[index + 1])
                index += 2
            } else {
                index += 1
            }
            continue
        }
        if (line.startsWith("$$", index)) {
            val closing = findClosingDoubleDollar(line, index + 2)
            if (closing < 0) {
                output.append(line, index, line.length)
                break
            }
            output.append(formulaCodeSpan(line.substring(index + 2, closing)))
            index = closing + 2
            continue
        }
        output.append(line[index])
        index += 1
    }
    return NormalizedInlineLatexLine(output.toString(), inlineCodeDelimiterLength)
}

private fun formulaCodeSpan(latex: String): String {
    val formula = latex.replace(Regex("\\s+"), " ").trim().ifEmpty { "invalid formula" }
    val longestBacktickRun = Regex("`+").findAll(formula)
        .maxOfOrNull { match -> match.value.length }
        ?: 0
    val delimiter = "`".repeat(longestBacktickRun + 1)
    val needsPadding = formula.firstOrNull() == '`' || formula.lastOrNull() == '`'
    return if (needsPadding) "$delimiter $formula $delimiter" else "$delimiter$formula$delimiter"
}

private fun containsLatex(markdown: String): Boolean =
    blockOrInlineLatex.containsMatchIn(markdown) || singleDollarLatex.containsMatchIn(markdown)

private fun markdownAccessibilityText(markdown: String): String {
    var spoken = blockOrInlineLatex.replace(markdown) { match ->
        " ${speakLatex(match.groupValues[1])} "
    }
    spoken = singleDollarLatex.replace(spoken) { match ->
        " ${speakLatex(match.groupValues[1])} "
    }
    spoken = Regex("""\[([^]]+)]\([^)]+\)""").replace(spoken) { match ->
        "${match.groupValues[1]}, 링크"
    }
    return spoken
        .replace(Regex("(?m)^#{1,6}\\s*"), "")
        .replace(Regex("(?m)^\\s*[-+]\\s+"), "항목 ")
        .replace("```", "")
        .replace("`", "")
        .replace("**", "")
        .replace("__", "")
        .replace(Regex("[ \\t]+"), " ")
        .replace(Regex("\\n{3,}"), "\n\n")
        .trim()
}

private fun speakLatex(latex: String): String {
    var spoken = latex.trim()
    val fraction = Regex("""\\frac\{([^{}]+)\}\{([^{}]+)\}""")
    repeat(3) {
        spoken = fraction.replace(spoken) { match ->
            "(${match.groupValues[1]}) 나누기 (${match.groupValues[2]})"
        }
    }
    spoken = Regex("""\\(?:text|mathrm|operatorname)\{([^{}]*)\}""").replace(spoken) { match ->
        match.groupValues[1]
    }
    spoken = Regex("""\\sqrt\{([^{}]+)\}""").replace(spoken) { match ->
        "제곱근 (${match.groupValues[1]})"
    }
    spoken = Regex("""\^\{([^{}]+)\}""").replace(spoken) { match ->
        " 의 ${match.groupValues[1]} 승 "
    }
    spoken = Regex("""_\{([^{}]+)\}""").replace(spoken) { match ->
        " 아래첨자 ${match.groupValues[1]} "
    }
    spoken = Regex("""\^([A-Za-z0-9]+)""").replace(spoken) { match ->
        " 의 ${match.groupValues[1]} 승 "
    }
    spoken = Regex("""_([A-Za-z0-9]+)""").replace(spoken) { match ->
        " 아래첨자 ${match.groupValues[1]} "
    }
    val commands = linkedMapOf(
        "\\times" to " 곱하기 ",
        "\\cdot" to " 곱하기 ",
        "\\div" to " 나누기 ",
        "\\pm" to " 플러스마이너스 ",
        "\\leq" to " 이하 ",
        "\\le" to " 이하 ",
        "\\geq" to " 이상 ",
        "\\ge" to " 이상 ",
        "\\neq" to " 같지 않음 ",
        "\\approx" to " 약 ",
        "\\sum" to " 합계 ",
        "\\infty" to " 무한대 ",
        "\\Delta" to " 델타 ",
        "\\alpha" to " 알파 ",
        "\\beta" to " 베타 ",
        "\\sigma" to " 시그마 ",
        "\\left" to "",
        "\\right" to "",
        "\\," to " ",
    )
    commands.forEach { (command, replacement) -> spoken = spoken.replace(command, replacement) }
    return spoken
        .replace("×", " 곱하기 ")
        .replace("÷", " 나누기 ")
        .replace("=", " 는 ")
        .replace("+", " 더하기 ")
        .replace("/", " 나누기 ")
        .replace("%", " 퍼센트 ")
        .replace(Regex("""\\([A-Za-z]+)""")) { match -> " ${match.groupValues[1]} " }
        .replace("{", " ")
        .replace("}", " ")
        .replace(Regex("\\s+"), " ")
        .trim()
}

private data class MarkdownFence(val marker: Char, val minimumLength: Int)

private data class MarkdownFenceRun(
    val marker: Char,
    val length: Int,
    val remainderIsBlank: Boolean,
)

private data class NormalizedInlineLatexLine(
    val markdown: String,
    val inlineCodeDelimiterLength: Int,
)

/**
 * Converts standard single-dollar inline math to Markwon's double-dollar inline syntax.
 *
 * The scanner deliberately leaves fenced code, inline code spans, escaped dollar signs,
 * native `$$...$$`, and delimiter-only block math untouched. Malformed or unclosed input is
 * preserved instead of guessing where a formula ends.
 */
internal fun normalizeInlineLatex(markdown: String): String {
    if ('$' !in markdown) return markdown

    val output = StringBuilder(markdown.length + 16)
    var lineStart = 0
    var fencedCode: MarkdownFence? = null
    var blockLatex = false
    var inlineCodeDelimiterLength = 0
    while (lineStart < markdown.length) {
        val newlineIndex = markdown.indexOf('\n', lineStart)
        val lineEnd = if (newlineIndex >= 0) newlineIndex else markdown.length
        val contentEnd = if (lineEnd > lineStart && markdown[lineEnd - 1] == '\r') {
            lineEnd - 1
        } else {
            lineEnd
        }
        val line = markdown.substring(lineStart, contentEnd)
        val lineEnding = when {
            newlineIndex < 0 -> ""
            contentEnd < lineEnd -> "\r\n"
            else -> "\n"
        }
        val fenceRun = markdownFenceRun(line)

        when {
            fencedCode != null -> {
                output.append(line)
                if (
                    fenceRun != null &&
                    fenceRun.marker == fencedCode.marker &&
                    fenceRun.length >= fencedCode.minimumLength &&
                    fenceRun.remainderIsBlank
                ) {
                    fencedCode = null
                }
            }
            blockLatex -> {
                output.append(line)
                if (line.trim() == "$$") blockLatex = false
            }
            inlineCodeDelimiterLength > 0 -> {
                val normalized = normalizeInlineLatexLine(line, inlineCodeDelimiterLength)
                output.append(normalized.markdown)
                inlineCodeDelimiterLength = normalized.inlineCodeDelimiterLength
            }
            fenceRun != null -> {
                output.append(line)
                fencedCode = MarkdownFence(fenceRun.marker, fenceRun.length)
            }
            line.trim() == "$$" -> {
                output.append(line)
                blockLatex = true
            }
            isIndentedCodeLine(line) -> output.append(line)
            else -> {
                val normalized = normalizeInlineLatexLine(line, inlineCodeDelimiterLength)
                output.append(normalized.markdown)
                inlineCodeDelimiterLength = normalized.inlineCodeDelimiterLength
            }
        }
        output.append(lineEnding)
        lineStart = if (newlineIndex >= 0) newlineIndex + 1 else markdown.length
    }
    return output.toString()
}

private fun markdownFenceRun(line: String): MarkdownFenceRun? {
    var markerIndex = 0
    while (markerIndex < line.length && markerIndex < 4 && line[markerIndex] == ' ') {
        markerIndex += 1
    }
    if (markerIndex > 3 || markerIndex >= line.length) return null
    val marker = line[markerIndex]
    if (marker != '`' && marker != '~') return null
    var end = markerIndex
    while (end < line.length && line[end] == marker) end += 1
    val length = end - markerIndex
    if (length < 3) return null
    return MarkdownFenceRun(
        marker = marker,
        length = length,
        remainderIsBlank = line.substring(end).isBlank(),
    )
}

private fun isIndentedCodeLine(line: String): Boolean {
    var columns = 0
    for (character in line) {
        columns += when (character) {
            ' ' -> 1
            '\t' -> 4 - (columns % 4)
            else -> return false
        }
        if (columns >= 4) return true
    }
    return false
}

private fun normalizeInlineLatexLine(
    line: String,
    initialInlineCodeDelimiterLength: Int,
): NormalizedInlineLatexLine {
    val output = StringBuilder(line.length + 8)
    var index = 0
    var inlineCodeDelimiterLength = initialInlineCodeDelimiterLength
    while (index < line.length) {
        if (line[index] == '`') {
            var runEnd = index
            while (runEnd < line.length && line[runEnd] == '`') runEnd += 1
            val runLength = runEnd - index
            output.append(line, index, runEnd)
            inlineCodeDelimiterLength = when {
                inlineCodeDelimiterLength == 0 -> runLength
                inlineCodeDelimiterLength == runLength -> 0
                else -> inlineCodeDelimiterLength
            }
            index = runEnd
            continue
        }
        if (inlineCodeDelimiterLength > 0) {
            output.append(line[index])
            index += 1
            continue
        }
        if (line[index] == '\\') {
            output.append(line[index])
            if (index + 1 < line.length) {
                output.append(line[index + 1])
                index += 2
            } else {
                index += 1
            }
            continue
        }
        if (line.startsWith("$$", index)) {
            val closing = findClosingDoubleDollar(line, index + 2)
            if (closing < 0) {
                output.append(line, index, line.length)
                break
            }
            output.append(line, index, closing + 2)
            index = closing + 2
            continue
        }
        if (line[index] == '$') {
            val closing = findClosingSingleDollar(line, index + 1)
            if (
                closing > index + 1 &&
                !line[index + 1].isWhitespace() &&
                !line[closing - 1].isWhitespace()
            ) {
                output.append("$$")
                output.append(line, index + 1, closing)
                output.append("$$")
                index = closing + 1
                continue
            }
        }
        output.append(line[index])
        index += 1
    }
    return NormalizedInlineLatexLine(output.toString(), inlineCodeDelimiterLength)
}

private fun findClosingDoubleDollar(line: String, start: Int): Int {
    var index = start
    while (index + 1 < line.length) {
        if (line[index] == '\\') {
            index += 2
            continue
        }
        if (line.startsWith("$$", index)) return index
        index += 1
    }
    return -1
}

private fun findClosingSingleDollar(line: String, start: Int): Int {
    var index = start
    while (index < line.length) {
        if (line[index] == '\\') {
            index += 2
            continue
        }
        if (line.startsWith("$$", index)) return -1
        if (line[index] == '$') return index
        index += 1
    }
    return -1
}
