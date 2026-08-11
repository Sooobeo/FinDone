package com.findone.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Delete
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Icon
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedCard
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.findone.app.data.LearningTextAnnotation

private const val COMMENT_MAX_LENGTH = 20_000

/**
 * A Markdown learning section with Android's text selection menu extended by FinDone actions.
 * Annotation persistence stays outside this component so it remains testable and reusable.
 */
@Composable
fun AnnotatableMarkdown(
    sectionKey: String,
    markdown: String,
    annotations: List<LearningTextAnnotation>,
    onAdd: (MarkdownSelectionAction, String?) -> Boolean,
    onSetComment: (annotationId: Long, comment: String) -> Boolean,
    onDelete: (annotationId: Long) -> Boolean,
    modifier: Modifier = Modifier,
    style: TextStyle,
    color: Color,
) {
    var pendingComment by remember(sectionKey, markdown) { mutableStateOf<MarkdownSelectionAction?>(null) }
    var editingAnnotation by remember(sectionKey, markdown) { mutableStateOf<LearningTextAnnotation?>(null) }
    var commentDraft by remember(sectionKey, markdown) { mutableStateOf("") }

    MarkdownText(
        markdown = markdown,
        modifier = modifier,
        style = style,
        color = color,
        sectionKey = sectionKey,
        annotations = annotations,
        onSelectionAction = { action ->
            val annotationsAtSelection = annotations.filter { annotation ->
                annotation.anchor.sectionKey == sectionKey &&
                    resolveLearningAnnotationRange(action.sourceText, annotation.anchor)?.let { range ->
                        range.first == action.startOffset && range.last + 1 == action.endOffset
                    } == true
            }
            val duplicateStyle = annotationsAtSelection.firstOrNull { it.style == action.style }
            val commentTarget = annotationsAtSelection.firstOrNull { !it.comment.isNullOrBlank() }
                ?: annotationsAtSelection.firstOrNull {
                    it.style == com.findone.app.data.TextAnnotationStyle.HIGHLIGHT
                }
            if (action.requestComment && commentTarget != null) {
                editingAnnotation = commentTarget
                pendingComment = null
                commentDraft = commentTarget.comment.orEmpty()
            } else if (action.requestComment) {
                pendingComment = action
                editingAnnotation = null
                commentDraft = ""
            } else if (duplicateStyle != null && duplicateStyle.comment.isNullOrBlank()) {
                onDelete(duplicateStyle.id)
            } else if (duplicateStyle != null) {
                editingAnnotation = duplicateStyle
                pendingComment = null
                commentDraft = duplicateStyle.comment.orEmpty()
            } else {
                onAdd(action, null)
            }
        },
        onCommentClick = { annotation ->
            editingAnnotation = annotation
            pendingComment = null
            commentDraft = annotation.comment.orEmpty()
        },
    )

    pendingComment?.let { action ->
        AnnotationCommentDialog(
            title = "코멘트 추가",
            selectedText = action.selectedText(),
            comment = commentDraft,
            onCommentChange = { commentDraft = it.take(COMMENT_MAX_LENGTH) },
            onDismiss = {
                pendingComment = null
                commentDraft = ""
            },
            onSave = {
                if (onAdd(action, commentDraft)) {
                    pendingComment = null
                    commentDraft = ""
                }
            },
        )
    }

    editingAnnotation?.let { annotation ->
        AnnotationCommentDialog(
            title = "코멘트",
            selectedText = annotation.anchor.selectedText,
            comment = commentDraft,
            onCommentChange = { commentDraft = it.take(COMMENT_MAX_LENGTH) },
            onDismiss = {
                editingAnnotation = null
                commentDraft = ""
            },
            onSave = {
                if (onSetComment(annotation.id, commentDraft)) {
                    editingAnnotation = null
                    commentDraft = ""
                }
            },
            onDelete = {
                if (onDelete(annotation.id)) {
                    editingAnnotation = null
                    commentDraft = ""
                }
            },
        )
    }
}

/** Keeps every saved mark discoverable even when updated content can no longer be re-anchored. */
@Composable
fun LearningAnnotationManager(
    annotations: List<LearningTextAnnotation>,
    onSetComment: (annotationId: Long, comment: String) -> Boolean,
    onDelete: (annotationId: Long) -> Boolean,
    modifier: Modifier = Modifier,
) {
    if (annotations.isEmpty()) return
    var editingAnnotation by remember(annotations) { mutableStateOf<LearningTextAnnotation?>(null) }
    var expanded by remember { mutableStateOf(annotations.size <= 3) }
    var visibleCount by remember { mutableStateOf(20) }
    var commentDraft by remember(editingAnnotation?.id) {
        mutableStateOf(editingAnnotation?.comment.orEmpty())
    }

    OutlinedCard(modifier = modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier.padding(18.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Row(modifier = Modifier.fillMaxWidth()) {
                Text(
                    "저장된 본문 표시 ${annotations.size}개",
                    modifier = Modifier.weight(1f),
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                )
                TextButton(onClick = { expanded = !expanded }) {
                    Text(if (expanded) "접기" else "목록 보기")
                }
            }
            Text(
                "콘텐츠가 바뀌어 본문 위치를 찾지 못해도 구절과 코멘트는 이 목록에 남습니다.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            if (expanded) annotations.take(visibleCount).forEach { annotation ->
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            text = "${annotation.style.displayName()} · ${annotation.anchor.sectionKey.sectionName()}",
                            style = MaterialTheme.typography.labelMedium,
                            color = MaterialTheme.colorScheme.primary,
                        )
                        Text(
                            text = "“${annotation.anchor.selectedText.take(180)}${if (annotation.anchor.selectedText.length > 180) "…" else ""}”",
                            style = MaterialTheme.typography.bodyMedium,
                        )
                        annotation.comment?.let { comment ->
                            Text(
                                text = comment,
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }
                    TextButton(
                        onClick = {
                            editingAnnotation = annotation
                            commentDraft = annotation.comment.orEmpty()
                        },
                    ) { Text("관리") }
                }
            }
            if (expanded && visibleCount < annotations.size) {
                TextButton(
                    onClick = { visibleCount = (visibleCount + 20).coerceAtMost(annotations.size) },
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Text("표시 더 보기 (${annotations.size - visibleCount}개 남음)")
                }
            }
        }
    }

    editingAnnotation?.let { annotation ->
        AnnotationCommentDialog(
            title = "본문 표시 관리",
            selectedText = annotation.anchor.selectedText,
            comment = commentDraft,
            commentEditable = annotation.style == com.findone.app.data.TextAnnotationStyle.HIGHLIGHT ||
                !annotation.comment.isNullOrBlank(),
            onCommentChange = { commentDraft = it.take(COMMENT_MAX_LENGTH) },
            onDismiss = { editingAnnotation = null },
            onSave = {
                if (onSetComment(annotation.id, commentDraft)) editingAnnotation = null
            },
            onDelete = {
                if (onDelete(annotation.id)) editingAnnotation = null
            },
        )
    }
}

@Composable
private fun AnnotationCommentDialog(
    title: String,
    selectedText: String,
    comment: String,
    onCommentChange: (String) -> Unit,
    onDismiss: () -> Unit,
    onSave: () -> Unit,
    onDelete: (() -> Unit)? = null,
    commentEditable: Boolean = true,
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(title) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text("“${selectedText.take(160)}${if (selectedText.length > 160) "…" else ""}”")
                if (commentEditable) {
                    OutlinedTextField(
                        value = comment,
                        onValueChange = onCommentChange,
                        label = { Text("이 구절에 남길 메모") },
                        minLines = 3,
                        maxLines = 8,
                    )
                } else {
                    Text(
                        "밑줄에 코멘트를 추가하려면 본문에서 같은 구절을 선택한 뒤 ‘코멘트’를 누르세요.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        },
        confirmButton = {
            if (commentEditable) {
                TextButton(onClick = onSave, enabled = comment.isNotBlank()) { Text("저장") }
            }
        },
        dismissButton = {
            if (onDelete == null) {
                TextButton(onClick = onDismiss) { Text("취소") }
            } else {
                androidx.compose.foundation.layout.Row {
                    TextButton(onClick = onDelete) {
                        Icon(Icons.Outlined.Delete, contentDescription = null)
                        Text("표시 삭제")
                    }
                    TextButton(onClick = onDismiss) { Text("취소") }
                }
            }
        },
    )
}

private fun MarkdownSelectionAction.selectedText(): String =
    sourceText.substring(startOffset, endOffset)

private fun com.findone.app.data.TextAnnotationStyle.displayName(): String = when (this) {
    com.findone.app.data.TextAnnotationStyle.HIGHLIGHT -> "형광펜"
    com.findone.app.data.TextAnnotationStyle.UNDERLINE -> "밑줄"
}

private fun String.sectionName(): String = when (this) {
    "definition" -> "한 문장 정의"
    "intuition" -> "쉽게 이해하기"
    "formula" -> "핵심 공식"
    "formula_assumptions" -> "공식 적용 조건"
    "formula_variables" -> "변수·항목 뜻"
    "learning_notes" -> "적용 유형"
    "checklist" -> "실무 사용 사례"
    else -> if (startsWith("learning_notes_")) "적용 유형" else this
}
