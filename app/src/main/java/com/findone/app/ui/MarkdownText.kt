package com.findone.app.ui

import android.graphics.Typeface
import android.text.method.LinkMovementMethod
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
import io.noties.markwon.ext.latex.JLatexMathPlugin
import io.noties.markwon.inlineparser.MarkwonInlineParserPlugin
import java.util.concurrent.Executors
import kotlin.math.max

/** A bounded process-wide pool avoids one cached executor per MarkdownText composition. */
private val latexExecutor = Executors.newFixedThreadPool(2) { runnable ->
    Thread(runnable, "findone-latex").apply { isDaemon = true }
}

private val blockOrInlineLatex = Regex("""(?s)\$\$(.+?)\$\$""")
private val singleDollarLatex = Regex("""(?<!\$)\$([^$\n]+?)\$(?!\$)""")

/**
 * Renders CommonMark and LaTeX without a WebView.
 *
 * Markwon uses `$$formula$$` for inline LaTeX and a pair of `$$` lines for block LaTeX.
 * Standard single-dollar inline expressions are normalized to Markwon's representation while
 * escaped dollar signs and block delimiters are left untouched.
 */
@Composable
fun MarkdownText(
    markdown: String,
    modifier: Modifier = Modifier,
    style: TextStyle = LocalTextStyle.current,
    color: Color = LocalContentColor.current,
) {
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
    val markdownRenderer = remember(context, textSizePx, textColor) {
        Markwon.builder(context)
            .usePlugin(MarkwonInlineParserPlugin.create())
            .usePlugin(
                JLatexMathPlugin.create(textSizePx) { builder ->
                    builder.inlinesEnabled(true)
                    builder.executorService(latexExecutor)
                    builder.theme().textColor(textColor)
                }
            )
            .build()
    }
    val normalizedMarkdown = remember(markdown) { normalizeInlineLatex(markdown) }
    val latexAccessibilityText = remember(markdown) {
        if (containsLatex(markdown)) markdownAccessibilityText(markdown) else null
    }

    AndroidView(
        modifier = modifier.fillMaxWidth(),
        factory = { viewContext ->
            TextView(viewContext).apply {
                layoutParams = ViewGroup.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT,
                    ViewGroup.LayoutParams.WRAP_CONTENT,
                )
                includeFontPadding = false
                linksClickable = true
                movementMethod = LinkMovementMethod.getInstance()
                highlightColor = android.graphics.Color.TRANSPARENT
            }
        },
        update = { textView ->
            textView.setTextColor(textColor)
            textView.setTextSize(TypedValue.COMPLEX_UNIT_PX, textSizePx)
            textView.setLineSpacing(max(0f, lineHeightPx - textSizePx), 1f)
            textView.contentDescription = latexAccessibilityText
            textView.setTypeface(
                Typeface.DEFAULT,
                if ((resolvedStyle.fontWeight ?: FontWeight.Normal) >= FontWeight.SemiBold) {
                    Typeface.BOLD
                } else {
                    Typeface.NORMAL
                },
            )
            markdownRenderer.setMarkdown(textView, normalizedMarkdown)
        },
    )
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
    val fraction = Regex("""\\frac\{([^{}]+)}\{([^{}]+)}""")
    repeat(3) {
        spoken = fraction.replace(spoken) { match ->
            "(${match.groupValues[1]}) 나누기 (${match.groupValues[2]})"
        }
    }
    spoken = Regex("""\\(?:text|mathrm|operatorname)\{([^{}]*)}""").replace(spoken) { match ->
        match.groupValues[1]
    }
    spoken = Regex("""\\sqrt\{([^{}]+)}""").replace(spoken) { match ->
        "제곱근 (${match.groupValues[1]})"
    }
    spoken = Regex("""\^\{([^{}]+)}""").replace(spoken) { match ->
        " 의 ${match.groupValues[1]} 승 "
    }
    spoken = Regex("""_\{([^{}]+)}""").replace(spoken) { match ->
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

private fun normalizeInlineLatex(markdown: String): String {
    if ('$' !in markdown) return markdown

    val output = StringBuilder(markdown.length + 16)
    var index = 0
    var fencedCode = false
    while (index < markdown.length) {
        if (markdown.startsWith("```", index)) {
            fencedCode = !fencedCode
            output.append("```")
            index += 3
            continue
        }
        if (!fencedCode && markdown.startsWith("$$", index)) {
            output.append("$$")
            index += 2
            continue
        }
        val char = markdown[index]
        if (
            !fencedCode &&
            char == '$' &&
            (index == 0 || markdown[index - 1] != '\\') &&
            (index == 0 || markdown[index - 1] != '$') &&
            (index + 1 >= markdown.length || markdown[index + 1] != '$')
        ) {
            val closing = findClosingSingleDollar(markdown, index + 1)
            if (closing > index + 1) {
                output.append("$$")
                output.append(markdown, index + 1, closing)
                output.append("$$")
                index = closing + 1
                continue
            }
        }
        output.append(char)
        index += 1
    }
    return output.toString()
}

private fun findClosingSingleDollar(markdown: String, start: Int): Int {
    var index = start
    while (index < markdown.length) {
        if (markdown[index] == '\n') return -1
        if (
            markdown[index] == '$' &&
            markdown[index - 1] != '\\' &&
            markdown[index - 1] != '$' &&
            (index + 1 >= markdown.length || markdown[index + 1] != '$')
        ) {
            return index
        }
        index += 1
    }
    return -1
}
