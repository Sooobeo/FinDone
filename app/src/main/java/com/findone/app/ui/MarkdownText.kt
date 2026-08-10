package com.findone.app.ui

import android.content.Context
import android.graphics.Canvas
import android.graphics.ColorFilter
import android.graphics.Paint
import android.graphics.Path
import android.graphics.PixelFormat
import android.graphics.RectF
import android.graphics.Typeface
import android.graphics.drawable.Drawable
import android.os.Bundle
import android.text.TextPaint
import android.text.TextUtils
import android.text.method.LinkMovementMethod
import android.util.Log
import android.util.TypedValue
import android.view.ActionMode
import android.view.Menu
import android.view.MenuItem
import android.view.MotionEvent
import android.view.ViewConfiguration
import android.view.ViewGroup
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
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
import java.security.MessageDigest
import java.util.LinkedHashMap
import java.util.concurrent.Executors
import com.findone.app.data.LearningTextAnchor
import com.findone.app.data.LearningTextAnnotation
import com.findone.app.data.TextAnnotationStyle
import kotlin.math.ceil
import kotlin.math.max
import kotlin.math.min
import ru.noties.jlatexmath.JLatexMathAndroid

/** Serialize access to JLatexMath's process-wide mutable formula and font registries. */
private val latexExecutor = Executors.newSingleThreadExecutor { runnable ->
    Thread(runnable, "findone-latex").apply { isDaemon = true }
}

/** Avoid flooding logcat without retaining an unbounded set of formula keys. */
private val reportedLatexErrors = object : LinkedHashMap<String, Unit>(16, 0.75f, true) {
    override fun removeEldestEntry(eldest: MutableMap.MutableEntry<String, Unit>?): Boolean =
        size > 128
}

private val blockOrInlineLatex = Regex("""(?s)\$\$(.+?)\$\$""")
private val singleDollarLatex = Regex("""(?<!\$)\$([^$\n]+?)\$(?!\$)""")
private const val LATEX_FALLBACK_MAX_WIDTH_EM = 20f
private const val LATEX_FALLBACK_MAX_CODE_POINTS = 512
data class MarkdownSelectionAction(
    val sourceText: String,
    val startOffset: Int,
    val endOffset: Int,
    val style: TextAnnotationStyle,
    val requestComment: Boolean,
)

private data class MarkdownRenderKey(
    val markdown: String,
    val textSizePx: Float,
    val textColor: Int,
)

private data class ResolvedLearningAnnotation(
    val annotation: LearningTextAnnotation,
    val start: Int,
    val end: Int,
)

private data class CommentMarker(
    val annotation: LearningTextAnnotation,
    val bounds: RectF,
)

private data class LearningAnnotationApplicationKey(
    val sourceText: String,
    val annotations: List<LearningTextAnnotation>,
)

/** Draws persisted learning marks using Layout coordinates, including replacement-span formulas. */
private class LearningMarkdownTextView(context: Context) : TextView(context) {
    var onCommentClick: ((LearningTextAnnotation) -> Unit)? = null
        set(value) {
            field = value
            invalidate()
        }
    var annotationApplicationKey: LearningAnnotationApplicationKey? = null

    private var resolvedAnnotations: List<ResolvedLearningAnnotation> = emptyList()
    private var commentMarkers: List<CommentMarker> = emptyList()
    private var pressedMarker: CommentMarker? = null
    private var pointerDownX = 0f
    private var pointerDownY = 0f
    private var pointerDownAt = 0L
    private val touchSlop = ViewConfiguration.get(context).scaledTouchSlop.toFloat()
    private val overlayPath = Path()
    private val overlayPaint = Paint(Paint.ANTI_ALIAS_FLAG)
    private var accessibilityComments: Map<Int, LearningTextAnnotation> = emptyMap()

    fun setLearningAnnotations(annotations: List<ResolvedLearningAnnotation>) {
        val changed = resolvedAnnotations != annotations
        resolvedAnnotations = annotations
        accessibilityComments = annotations.asSequence()
            .map(ResolvedLearningAnnotation::annotation)
            .filter { !it.comment.isNullOrBlank() }
            .distinctBy(LearningTextAnnotation::id)
            .take(MAX_ACCESSIBILITY_COMMENT_ACTIONS)
            .mapIndexed { index, annotation -> ACCESSIBILITY_COMMENT_ACTION_BASE + index to annotation }
            .toMap()
        invalidate()
        if (changed && isAttachedToWindow) {
            sendAccessibilityEvent(AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED)
        }
    }

    fun openComment(annotation: LearningTextAnnotation) {
        onCommentClick?.invoke(annotation)
    }

    override fun onDraw(canvas: Canvas) {
        val textLayout = layout
        super.onDraw(canvas)
        if (textLayout == null) {
            commentMarkers = emptyList()
            return
        }
        if (resolvedAnnotations.any { it.annotation.style == TextAnnotationStyle.HIGHLIGHT }) {
            val saveCount = canvas.save()
            canvas.translate(textOriginX(), textOriginY())
            overlayPaint.style = Paint.Style.FILL
            overlayPaint.color = HIGHLIGHT_OVERLAY_COLOR
            resolvedAnnotations.forEach { resolved ->
                if (resolved.annotation.style == TextAnnotationStyle.HIGHLIGHT) {
                    overlayPath.reset()
                    textLayout.getSelectionPath(resolved.start, resolved.end, overlayPath)
                    canvas.drawPath(overlayPath, overlayPaint)
                }
            }
            canvas.restoreToCount(saveCount)
        }
        drawUnderlines(canvas, textLayout)
        drawCommentMarkers(canvas, textLayout)
    }

    private fun drawUnderlines(canvas: Canvas, textLayout: android.text.Layout) {
        val underlined = resolvedAnnotations.filter { it.annotation.style == TextAnnotationStyle.UNDERLINE }
        if (underlined.isEmpty()) return
        val saveCount = canvas.save()
        canvas.translate(textOriginX(), textOriginY())
        overlayPaint.style = Paint.Style.STROKE
        overlayPaint.strokeWidth = max(resources.displayMetrics.density, textSize * 0.075f)
        overlayPaint.strokeCap = Paint.Cap.ROUND
        overlayPaint.color = currentTextColor
        underlined.forEach { resolved ->
            val firstLine = textLayout.getLineForOffset(resolved.start)
            val lastLine = textLayout.getLineForOffset((resolved.end - 1).coerceAtLeast(resolved.start))
            for (line in firstLine..lastLine) {
                val segmentStart = max(resolved.start, textLayout.getLineStart(line))
                val segmentEnd = min(resolved.end, textLayout.getLineEnd(line))
                if (segmentStart >= segmentEnd) continue
                val lineVisibleEnd = textLayout.getLineVisibleEnd(line)
                val startX = if (segmentStart <= textLayout.getLineStart(line)) {
                    textLayout.getLineLeft(line)
                } else {
                    textLayout.getPrimaryHorizontal(segmentStart)
                }
                val endX = if (segmentEnd >= lineVisibleEnd) {
                    textLayout.getLineRight(line)
                } else {
                    textLayout.getPrimaryHorizontal(segmentEnd)
                }
                val underlineY = textLayout.getLineBaseline(line) + overlayPaint.strokeWidth
                canvas.drawLine(min(startX, endX), underlineY, max(startX, endX), underlineY, overlayPaint)
            }
        }
        canvas.restoreToCount(saveCount)
    }

    private fun drawCommentMarkers(canvas: Canvas, textLayout: android.text.Layout) {
        val comments = resolvedAnnotations.filter { !it.annotation.comment.isNullOrBlank() }
        if (comments.isEmpty() || onCommentClick == null) {
            commentMarkers = emptyList()
            return
        }
        val originX = textOriginX()
        val originY = textOriginY()
        val density = resources.displayMetrics.density
        val radius = max(3f * density, textSize * 0.13f)
        val touchRadius = max(18f * density, radius * 3f)
        overlayPaint.style = Paint.Style.FILL
        overlayPaint.color = COMMENT_MARKER_COLOR
        commentMarkers = comments.map { resolved ->
            val safeEnd = resolved.end.coerceIn(1, text.length)
            val line = textLayout.getLineForOffset((safeEnd - 1).coerceAtLeast(0))
            val lineLeft = originX + min(textLayout.getLineLeft(line), textLayout.getLineRight(line))
            val lineRight = originX + max(textLayout.getLineLeft(line), textLayout.getLineRight(line))
            val endLine = textLayout.getLineForOffset(safeEnd)
            val rawX = if (endLine == line) {
                originX + textLayout.getPrimaryHorizontal(safeEnd)
            } else {
                lineRight
            }
            val markerX = rawX.coerceIn(lineLeft + radius, max(lineLeft + radius, lineRight - radius))
            val markerY = originY + textLayout.getLineTop(line) + radius * 1.5f
            canvas.drawCircle(markerX, markerY, radius, overlayPaint)
            CommentMarker(
                annotation = resolved.annotation,
                bounds = RectF(
                    markerX - touchRadius,
                    markerY - touchRadius,
                    markerX + touchRadius,
                    markerY + touchRadius,
                ),
            )
        }
    }

    override fun onTouchEvent(event: MotionEvent): Boolean {
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                pointerDownX = event.x
                pointerDownY = event.y
                pointerDownAt = event.eventTime
                pressedMarker = markerAt(event.x, event.y)
                val handled = super.onTouchEvent(event)
                return handled || pressedMarker != null
            }
            MotionEvent.ACTION_MOVE -> {
                if (
                    kotlin.math.abs(event.x - pointerDownX) > touchSlop ||
                    kotlin.math.abs(event.y - pointerDownY) > touchSlop
                ) {
                    pressedMarker = null
                }
            }
            MotionEvent.ACTION_UP -> {
                val marker = pressedMarker
                pressedMarker = null
                val isShortTap = event.eventTime - pointerDownAt < ViewConfiguration.getLongPressTimeout()
                if (
                    isShortTap && marker != null &&
                    markerAt(event.x, event.y)?.annotation?.id == marker.annotation.id
                ) {
                    MotionEvent.obtain(event).also { cancelEvent ->
                        cancelEvent.action = MotionEvent.ACTION_CANCEL
                        super.onTouchEvent(cancelEvent)
                        cancelEvent.recycle()
                    }
                    performClick()
                    openComment(marker.annotation)
                    return true
                }
            }
            MotionEvent.ACTION_CANCEL -> pressedMarker = null
        }
        return super.onTouchEvent(event)
    }

    override fun performClick(): Boolean {
        super.performClick()
        return true
    }

    override fun onInitializeAccessibilityNodeInfo(info: AccessibilityNodeInfo) {
        super.onInitializeAccessibilityNodeInfo(info)
        accessibilityComments.forEach { (actionId, annotation) ->
            val quote = annotation.anchor.selectedText.replace(Regex("\\s+"), " ").take(40)
            info.addAction(
                AccessibilityNodeInfo.AccessibilityAction(
                    actionId,
                    "코멘트 열기: $quote",
                )
            )
        }
    }

    override fun performAccessibilityAction(action: Int, arguments: Bundle?): Boolean {
        val annotation = accessibilityComments[action]
        if (annotation != null && onCommentClick != null) {
            openComment(annotation)
            return true
        }
        return super.performAccessibilityAction(action, arguments)
    }

    private fun markerAt(x: Float, y: Float): CommentMarker? =
        commentMarkers.lastOrNull { marker -> marker.bounds.contains(x, y) }

    private fun textOriginX(): Float = compoundPaddingLeft.toFloat() - scrollX

    private fun textOriginY(): Float = extendedPaddingTop.toFloat() - scrollY
}

private const val HIGHLIGHT_OVERLAY_COLOR = 0x55FFE066
private const val COMMENT_MARKER_COLOR = 0xFFE65100.toInt()
private const val ACCESSIBILITY_COMMENT_ACTION_BASE = 0x02100000
private const val MAX_ACCESSIBILITY_COMMENT_ACTIONS = 16

/**
 * Renders CommonMark and LaTeX locally without a WebView or network access.
 * Standard single-dollar inline expressions are normalized to Markwon's double-dollar syntax.
 */
@Composable
fun MarkdownText(
    markdown: String,
    modifier: Modifier = Modifier,
    style: TextStyle = LocalTextStyle.current,
    color: Color = LocalContentColor.current,
    maxLines: Int = Int.MAX_VALUE,
    linksEnabled: Boolean = true,
    sectionKey: String? = null,
    annotations: List<LearningTextAnnotation> = emptyList(),
    onSelectionAction: ((MarkdownSelectionAction) -> Unit)? = null,
    onCommentClick: ((LearningTextAnnotation) -> Unit)? = null,
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
    val markdownRenderer = remember(applicationContext, textSizePx, textColor) {
        JLatexMathAndroid.init(applicationContext)
        Markwon.builder(applicationContext)
            .usePlugin(MarkwonInlineParserPlugin.create())
            .usePlugin(
                JLatexMathPlugin.create(textSizePx) { builder ->
                    builder.inlinesEnabled(true)
                    builder.executorService(latexExecutor)
                    builder.errorHandler { latex, error ->
                        reportLatexRenderingError(latex, error)
                        LatexFallbackDrawable(latex, textSizePx, textColor)
                    }
                    builder.theme().textColor(textColor)
                    builder.theme().blockFitCanvas(true)
                }
            )
            .build()
    }
    val normalizedMarkdown = remember(markdown) { normalizeInlineLatex(markdown) }
    val latexAccessibilityText = remember(markdown) {
        if (containsLatex(markdown)) markdownAccessibilityText(markdown) else null
    }
    val sectionAnnotations = remember(sectionKey, annotations) {
        if (sectionKey == null) emptyList() else annotations.filter { it.anchor.sectionKey == sectionKey }
    }
    val renderKey = MarkdownRenderKey(normalizedMarkdown, textSizePx, textColor)

    AndroidView(
        modifier = modifier.fillMaxWidth(),
        factory = { viewContext ->
            LearningMarkdownTextView(viewContext).apply {
                layoutParams = ViewGroup.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT,
                    ViewGroup.LayoutParams.WRAP_CONTENT,
                )
                includeFontPadding = false
            }
        },
        update = { textView ->
            textView.onCommentClick = onCommentClick
            textView.setTextColor(textColor)
            textView.setTextSize(TypedValue.COMPLEX_UNIT_PX, textSizePx)
            textView.setLineSpacing(max(0f, lineHeightPx - textSizePx), 1f)
            textView.maxLines = maxLines
            textView.ellipsize = if (maxLines == Int.MAX_VALUE) null else TextUtils.TruncateAt.END
            textView.linksClickable = linksEnabled
            textView.setTextIsSelectable(onSelectionAction != null)
            textView.highlightColor = if (onSelectionAction != null) {
                0x553F51B5
            } else {
                android.graphics.Color.TRANSPARENT
            }
            textView.movementMethod = if (linksEnabled || onCommentClick != null) {
                LinkMovementMethod.getInstance()
            } else {
                textView.movementMethod
            }
            textView.isClickable = linksEnabled || onCommentClick != null
            if (!linksEnabled && onSelectionAction == null) textView.isLongClickable = false
            textView.customSelectionActionModeCallback = selectionActionModeCallback(
                textView = textView,
                onSelectionAction = onSelectionAction,
            )
            val commentCount = sectionAnnotations.count { !it.comment.isNullOrBlank() }
            textView.contentDescription = latexAccessibilityText?.let { spokenText ->
                if (commentCount == 0) spokenText else "$spokenText. 저장된 코멘트 ${commentCount}개."
            }
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
            applyLearningAnnotations(textView, sectionAnnotations)
        },
    )
}

private const val ACTION_HIGHLIGHT = 0x46494E01
private const val ACTION_UNDERLINE = 0x46494E02
private const val ACTION_COMMENT = 0x46494E03

private fun selectionActionModeCallback(
    textView: TextView,
    onSelectionAction: ((MarkdownSelectionAction) -> Unit)?,
): ActionMode.Callback? {
    if (onSelectionAction == null) return null
    return object : ActionMode.Callback {
        override fun onCreateActionMode(mode: ActionMode, menu: Menu): Boolean = true

        override fun onPrepareActionMode(mode: ActionMode, menu: Menu): Boolean {
            menu.removeItem(ACTION_HIGHLIGHT)
            menu.removeItem(ACTION_UNDERLINE)
            menu.removeItem(ACTION_COMMENT)
            menu.add(Menu.NONE, ACTION_HIGHLIGHT, 100, "형광펜")
                .setShowAsAction(MenuItem.SHOW_AS_ACTION_IF_ROOM)
            menu.add(Menu.NONE, ACTION_UNDERLINE, 101, "밑줄")
                .setShowAsAction(MenuItem.SHOW_AS_ACTION_IF_ROOM)
            menu.add(Menu.NONE, ACTION_COMMENT, 102, "코멘트")
                .setShowAsAction(MenuItem.SHOW_AS_ACTION_IF_ROOM)
            return true
        }

        override fun onActionItemClicked(mode: ActionMode, item: MenuItem): Boolean {
            val selection = normalizedSelection(textView) ?: return false
            val (style, requestComment) = when (item.itemId) {
                ACTION_HIGHLIGHT -> TextAnnotationStyle.HIGHLIGHT to false
                ACTION_UNDERLINE -> TextAnnotationStyle.UNDERLINE to false
                ACTION_COMMENT -> TextAnnotationStyle.HIGHLIGHT to true
                else -> return false
            }
            onSelectionAction(
                MarkdownSelectionAction(
                    sourceText = textView.text.toString(),
                    startOffset = selection.first,
                    endOffset = selection.last + 1,
                    style = style,
                    requestComment = requestComment,
                )
            )
            mode.finish()
            return true
        }

        override fun onDestroyActionMode(mode: ActionMode) = Unit
    }
}

private fun normalizedSelection(textView: TextView): IntRange? {
    var start = min(textView.selectionStart, textView.selectionEnd).coerceAtLeast(0)
    var end = max(textView.selectionStart, textView.selectionEnd).coerceAtMost(textView.text.length)
    while (start < end && textView.text[start].isWhitespace()) start += 1
    while (end > start && textView.text[end - 1].isWhitespace()) end -= 1
    return if (start < end) start until end else null
}

private fun applyLearningAnnotations(
    textView: LearningMarkdownTextView,
    annotations: List<LearningTextAnnotation>,
) {
    val originalText = textView.text
    val sourceText = originalText.toString()
    val applicationKey = LearningAnnotationApplicationKey(sourceText, annotations)
    if (textView.annotationApplicationKey == applicationKey) return
    textView.annotationApplicationKey = applicationKey
    val sourceHash = if (annotations.any { it.anchor.sourceHash != null }) sha256Hex(sourceText) else null
    val resolvedAnnotations = mutableListOf<ResolvedLearningAnnotation>()
    annotations.forEach { annotation ->
        val range = resolveLearningAnnotationRange(sourceText, annotation.anchor, sourceHash)
            ?: return@forEach
        val start = range.first
        val end = range.last + 1
        resolvedAnnotations += ResolvedLearningAnnotation(annotation, start, end)
    }
    textView.setLearningAnnotations(resolvedAnnotations)
}

/** Resolves a persisted quote after harmless surrounding-content edits. */
internal fun resolveLearningAnnotationRange(
    text: String,
    anchor: LearningTextAnchor,
): IntRange? = resolveLearningAnnotationRange(
    text = text,
    anchor = anchor,
    currentSourceHash = anchor.sourceHash?.let { sha256Hex(text) },
)

private fun resolveLearningAnnotationRange(
    text: String,
    anchor: LearningTextAnchor,
    currentSourceHash: String?,
): IntRange? {
    val quote = anchor.selectedText
    if (quote.isEmpty() || quote.length > text.length) return null
    val storedStart = anchor.startOffset
    val storedEnd = storedStart + quote.length
    val storedOffsetMatches =
        storedStart >= 0 && storedEnd <= text.length && storedStart < storedEnd &&
        text.regionMatches(storedStart, quote, 0, quote.length)
    if (storedOffsetMatches) {
        if (anchor.sourceHash != null && anchor.sourceHash == currentSourceHash) {
            return storedStart until storedEnd
        }
        val prefix = text.substring(max(0, storedStart - anchor.prefixContext.length), storedStart)
        val suffix = text.substring(storedEnd, min(text.length, storedEnd + anchor.suffixContext.length))
        val matchingContext = matchingSuffixLength(prefix, anchor.prefixContext) +
            matchingPrefixLength(suffix, anchor.suffixContext)
        if (matchingContext == anchor.prefixContext.length + anchor.suffixContext.length) {
            return storedStart until storedEnd
        }
    }

    var bestStart = -1
    var bestContextScore = -1
    var bestDistance = Int.MAX_VALUE
    var occurrenceCount = 0
    var searchFrom = 0
    while (searchFrom <= text.length - quote.length) {
        val candidate = text.indexOf(quote, startIndex = searchFrom)
        if (candidate < 0) break
        occurrenceCount += 1
        val candidateEnd = candidate + quote.length
        val contextScore = matchingSuffixLength(
            text.substring(max(0, candidate - anchor.prefixContext.length), candidate),
            anchor.prefixContext,
        ) + matchingPrefixLength(
            text.substring(candidateEnd, min(text.length, candidateEnd + anchor.suffixContext.length)),
            anchor.suffixContext,
        )
        val distance = kotlin.math.abs(candidate - storedStart)
        if (contextScore > bestContextScore || contextScore == bestContextScore && distance < bestDistance) {
            bestContextScore = contextScore
            bestDistance = distance
            bestStart = candidate
        }
        searchFrom = candidate + 1
    }
    if (bestStart < 0) return null
    if (occurrenceCount == 1) return bestStart until (bestStart + quote.length)
    val availableContext = anchor.prefixContext.length + anchor.suffixContext.length
    val minimumContext = min(8, availableContext)
    return if (minimumContext > 0 && bestContextScore >= minimumContext) {
        bestStart until (bestStart + quote.length)
    } else {
        null
    }
}

private fun matchingSuffixLength(first: String, second: String): Int {
    var matched = 0
    while (
        matched < first.length && matched < second.length &&
        first[first.lastIndex - matched] == second[second.lastIndex - matched]
    ) {
        matched += 1
    }
    return matched
}

private fun matchingPrefixLength(first: String, second: String): Int {
    var matched = 0
    while (matched < first.length && matched < second.length && first[matched] == second[matched]) {
        matched += 1
    }
    return matched
}

private fun sha256Hex(value: String): String = MessageDigest.getInstance("SHA-256")
    .digest(value.toByteArray(Charsets.UTF_8))
    .joinToString("") { byte -> "%02x".format(byte.toInt() and 0xff) }

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

private fun reportLatexRenderingError(latex: String, error: Throwable) {
    val diagnosticKey = "${latex.length}:${latex.hashCode().toUInt().toString(16)}"
    val shouldLog = synchronized(reportedLatexErrors) {
        reportedLatexErrors.put(diagnosticKey, Unit) == null
    }
    if (shouldLog) {
        Log.e(
            "FinDoneLatex",
            "Bundled LaTeX renderer failed (formula=$diagnosticKey)",
            error,
        )
    }
}

/** Never leave a blank span when the bundled LaTeX engine rejects an expression. */
private class LatexFallbackDrawable(
    latex: String,
    textSizePx: Float,
    textColor: Int,
) : Drawable() {
    private val fallbackText = normalizedLatexFallbackText(latex)
    private val paint = TextPaint(Paint.ANTI_ALIAS_FLAG).apply {
        color = textColor
        textSize = textSizePx
        typeface = Typeface.MONOSPACE
    }
    private val intrinsicWidth = boundedLatexFallbackWidthPx(
        measuredTextWidthPx = paint.measureText(fallbackText),
        textSizePx = textSizePx,
    )
    private val displayText = TextUtils.ellipsize(
        fallbackText,
        paint,
        intrinsicWidth.toFloat(),
        TextUtils.TruncateAt.END,
    ).toString()

    override fun draw(canvas: Canvas) {
        val metrics = paint.fontMetrics
        canvas.drawText(
            displayText,
            bounds.left.toFloat(),
            bounds.top - metrics.top,
            paint,
        )
    }

    override fun setAlpha(alpha: Int) {
        paint.alpha = alpha
    }

    override fun setColorFilter(colorFilter: ColorFilter?) {
        paint.colorFilter = colorFilter
    }

    @Suppress("OVERRIDE_DEPRECATION")
    override fun getOpacity(): Int = PixelFormat.TRANSLUCENT

    override fun getIntrinsicWidth(): Int = intrinsicWidth

    override fun getIntrinsicHeight(): Int {
        val metrics = paint.fontMetrics
        return max(1, ceil(metrics.bottom - metrics.top).toInt())
    }
}

internal fun normalizedLatexFallbackText(
    latex: String,
    maxCodePoints: Int = LATEX_FALLBACK_MAX_CODE_POINTS,
): String {
    require(maxCodePoints >= 2) { "maxCodePoints must leave room for content and an ellipsis." }
    val normalized = latex.replace(Regex("\\s+"), " ").trim()
        .ifEmpty { "[invalid formula]" }
    val codePointCount = normalized.codePointCount(0, normalized.length)
    if (codePointCount <= maxCodePoints) return normalized

    val contentEnd = normalized.offsetByCodePoints(0, maxCodePoints - 1)
    return normalized.substring(0, contentEnd).trimEnd() + "…"
}

internal fun boundedLatexFallbackWidthPx(
    measuredTextWidthPx: Float,
    textSizePx: Float,
): Int {
    val safeTextSize = textSizePx.takeIf { it.isFinite() && it > 0f } ?: 1f
    val maximumWidth = safeTextSize * LATEX_FALLBACK_MAX_WIDTH_EM
    val boundedWidth = when {
        measuredTextWidthPx.isNaN() -> maximumWidth
        measuredTextWidthPx <= 0f -> 1f
        else -> measuredTextWidthPx.coerceAtMost(maximumWidth)
    }
    return max(1, ceil(boundedWidth).toInt())
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
