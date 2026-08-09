package com.findone.app.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.text.ClickableText
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Add
import androidx.compose.material.icons.outlined.Close
import androidx.compose.material.icons.outlined.Delete
import androidx.compose.material.icons.outlined.Edit
import androidx.compose.material.icons.outlined.ExpandLess
import androidx.compose.material.icons.outlined.ExpandMore
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedCard
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.findone.app.data.CONCEPT_NOTE_BODY_MAX_LENGTH
import com.findone.app.data.CONCEPT_NOTE_TITLE_MAX_LENGTH
import com.findone.app.data.ConceptNote

private const val URL_ANNOTATION_TAG = "concept-note-url"
private val HTTP_URL_PATTERN = Regex(
    "https?://[A-Za-z0-9._~:/?#\\[\\]@!\\$&()*+,;=%-]+",
    RegexOption.IGNORE_CASE,
)
private val ALWAYS_TRAILING_URL_PUNCTUATION = setOf('.', ',', '!', '?', ';', ':')
private val TRAILING_URL_DELIMITER_PAIRS = mapOf(')' to '(', ']' to '[', '}' to '{')
private val OPENING_URL_DELIMITERS = TRAILING_URL_DELIMITER_PAIRS.entries.associate { (closing, opening) ->
    opening to closing
}

internal data class HttpUrlRange(
    val url: String,
    val start: Int,
    val endExclusive: Int,
)

private fun hasHttpAuthority(url: String): Boolean {
    val authorityStart = url.indexOf("://").takeIf { it >= 0 }?.plus(3) ?: return false
    val authorityEnd = url.indexOfAny(charArrayOf('/', '?', '#'), authorityStart)
        .let { if (it >= 0) it else url.length }
    val hostAndPort = url.substring(authorityStart, authorityEnd).substringAfterLast('@')
    if (hostAndPort.isEmpty()) return false

    val host = if (hostAndPort.startsWith('[')) {
        val closingBracket = hostAndPort.indexOf(']')
        if (closingBracket <= 1) return false
        val suffix = hostAndPort.substring(closingBracket + 1)
        if (suffix.isNotEmpty() && !suffix.matches(Regex(":\\d{1,5}"))) return false
        hostAndPort.substring(1, closingBracket)
    } else {
        hostAndPort.substringBefore(':')
    }
    return host.any { it.isLetterOrDigit() } || host.count { it == ':' } >= 2
}

internal fun findHttpUrlRanges(text: String): List<HttpUrlRange> = buildList {
    HTTP_URL_PATTERN.findAll(text).forEach { match ->
        var endExclusive = match.range.last + 1
        while (
            endExclusive > match.range.first &&
            text[endExclusive - 1] in ALWAYS_TRAILING_URL_PUNCTUATION
        ) {
            endExclusive--
        }
        val delimiterBalance = TRAILING_URL_DELIMITER_PAIRS.keys.associateWith { 0 }.toMutableMap()
        for (index in match.range.first until endExclusive) {
            val character = text[index]
            if (character in TRAILING_URL_DELIMITER_PAIRS) {
                delimiterBalance[character] = delimiterBalance.getValue(character) + 1
            } else {
                val closing = OPENING_URL_DELIMITERS[character]
                if (closing != null) {
                    delimiterBalance[closing] = delimiterBalance.getValue(closing) - 1
                }
            }
        }
        var balancedEnd = endExclusive
        while (balancedEnd > match.range.first) {
            val closing = text[balancedEnd - 1]
            if (closing !in TRAILING_URL_DELIMITER_PAIRS) break
            val unmatchedClosingCount = delimiterBalance.getValue(closing)
            if (unmatchedClosingCount <= 0) break
            delimiterBalance[closing] = unmatchedClosingCount - 1
            balancedEnd--
        }
        val candidate = text.substring(match.range.first, balancedEnd)
        if (hasHttpAuthority(candidate)) {
            add(
                HttpUrlRange(
                    url = candidate,
                    start = match.range.first,
                    endExclusive = balancedEnd,
                )
            )
        }
    }
}

@Composable
fun ConceptNotesSection(
    elementId: String,
    notes: List<ConceptNote>,
    errorMessage: String?,
    onDismissError: () -> Unit,
    onAdd: (title: String, body: String) -> Boolean,
    onUpdate: (noteId: Long, title: String, body: String) -> Boolean,
    onDelete: (noteId: Long) -> Boolean,
    modifier: Modifier = Modifier,
) {
    var expandedNoteId by rememberSaveable(elementId) { mutableStateOf<Long?>(null) }
    var editorOpen by rememberSaveable(elementId) { mutableStateOf(false) }
    var editorNoteId by rememberSaveable(elementId) { mutableStateOf<Long?>(null) }
    var editorTitle by rememberSaveable(elementId) { mutableStateOf("") }
    var editorBody by rememberSaveable(elementId) { mutableStateOf("") }
    var deleteNoteId by rememberSaveable(elementId) { mutableStateOf<Long?>(null) }

    LaunchedEffect(notes) {
        if (expandedNoteId != null && notes.none { it.id == expandedNoteId }) expandedNoteId = null
        if (deleteNoteId != null && notes.none { it.id == deleteNoteId }) deleteNoteId = null
    }

    Column(modifier, verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text("개인 메모", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                Text(
                    "이 학습요소에만 저장되며 제목을 눌러 내용을 펼칠 수 있습니다.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Spacer(Modifier.width(10.dp))
            OutlinedButton(
                onClick = {
                    onDismissError()
                    editorNoteId = null
                    editorTitle = ""
                    editorBody = ""
                    editorOpen = true
                },
            ) {
                Icon(Icons.Outlined.Add, contentDescription = null, modifier = Modifier.size(18.dp))
                Spacer(Modifier.width(6.dp))
                Text("추가")
            }
        }

        errorMessage?.let { message ->
            OutlinedCard(
                colors = CardDefaults.outlinedCardColors(
                    containerColor = MaterialTheme.colorScheme.errorContainer,
                ),
            ) {
                Row(
                    Modifier.fillMaxWidth().padding(start = 14.dp, top = 8.dp, bottom = 8.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(
                        message,
                        modifier = Modifier.weight(1f).semantics { liveRegion = LiveRegionMode.Polite },
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onErrorContainer,
                    )
                    IconButton(onClick = onDismissError) {
                        Icon(Icons.Outlined.Close, contentDescription = "오류 메시지 닫기")
                    }
                }
            }
        }

        if (notes.isEmpty()) {
            OutlinedCard(Modifier.fillMaxWidth()) {
                Text(
                    "아직 저장한 메모가 없습니다.",
                    modifier = Modifier.padding(16.dp),
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        } else {
            notes.forEach { note ->
                val expanded = expandedNoteId == note.id
                OutlinedCard(Modifier.fillMaxWidth()) {
                    Column {
                        Row(
                            Modifier
                                .fillMaxWidth()
                                .clickable(
                                    role = Role.Button,
                                    onClickLabel = if (expanded) "메모 접기" else "메모 펼치기",
                                ) { expandedNoteId = if (expanded) null else note.id }
                                .padding(16.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Text(
                                note.title,
                                modifier = Modifier.weight(1f),
                                style = MaterialTheme.typography.titleSmall,
                                fontWeight = FontWeight.SemiBold,
                                maxLines = 2,
                                overflow = TextOverflow.Ellipsis,
                            )
                            Spacer(Modifier.width(8.dp))
                            Icon(
                                if (expanded) Icons.Outlined.ExpandLess else Icons.Outlined.ExpandMore,
                                contentDescription = if (expanded) "접기" else "펼치기",
                            )
                        }
                        if (expanded) {
                            HorizontalDivider()
                            Column(
                                Modifier.fillMaxWidth().padding(16.dp),
                                verticalArrangement = Arrangement.spacedBy(12.dp),
                            ) {
                                LinkifiedConceptNoteBody(note.body)
                                Row(
                                    modifier = Modifier.fillMaxWidth(),
                                    horizontalArrangement = Arrangement.End,
                                ) {
                                    TextButton(
                                        onClick = {
                                            onDismissError()
                                            editorNoteId = note.id
                                            editorTitle = note.title
                                            editorBody = note.body
                                            editorOpen = true
                                        },
                                    ) {
                                        Icon(Icons.Outlined.Edit, contentDescription = null, modifier = Modifier.size(18.dp))
                                        Spacer(Modifier.width(5.dp))
                                        Text("수정")
                                    }
                                    TextButton(
                                        onClick = {
                                            onDismissError()
                                            deleteNoteId = note.id
                                        },
                                    ) {
                                        Icon(Icons.Outlined.Delete, contentDescription = null, modifier = Modifier.size(18.dp))
                                        Spacer(Modifier.width(5.dp))
                                        Text("삭제")
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    if (editorOpen) {
        ConceptNoteEditorDialog(
            editing = editorNoteId != null,
            title = editorTitle,
            body = editorBody,
            errorMessage = errorMessage,
            onTitleChange = { if (it.length <= CONCEPT_NOTE_TITLE_MAX_LENGTH) editorTitle = it },
            onBodyChange = { if (it.length <= CONCEPT_NOTE_BODY_MAX_LENGTH) editorBody = it },
            onDismiss = {
                editorOpen = false
                onDismissError()
            },
            onSave = {
                val saved = editorNoteId?.let { onUpdate(it, editorTitle, editorBody) }
                    ?: onAdd(editorTitle, editorBody)
                if (saved) editorOpen = false
            },
        )
    }

    deleteNoteId?.let { noteId ->
        val noteTitle = notes.firstOrNull { it.id == noteId }?.title ?: "이 메모"
        AlertDialog(
            onDismissRequest = { deleteNoteId = null },
            title = { Text("개인 메모 삭제") },
            text = { Text("‘$noteTitle’을 삭제할까요? 삭제한 메모는 복구할 수 없습니다.") },
            confirmButton = {
                TextButton(
                    onClick = {
                        val deleted = onDelete(noteId)
                        deleteNoteId = null
                        if (deleted && expandedNoteId == noteId) expandedNoteId = null
                    },
                ) { Text("삭제", color = MaterialTheme.colorScheme.error) }
            },
            dismissButton = {
                TextButton(onClick = { deleteNoteId = null }) { Text("취소") }
            },
        )
    }
}

@Composable
private fun ConceptNoteEditorDialog(
    editing: Boolean,
    title: String,
    body: String,
    errorMessage: String?,
    onTitleChange: (String) -> Unit,
    onBodyChange: (String) -> Unit,
    onDismiss: () -> Unit,
    onSave: () -> Unit,
) {
    val canSave = title.isNotBlank() && body.isNotBlank() &&
        title.length <= CONCEPT_NOTE_TITLE_MAX_LENGTH && body.length <= CONCEPT_NOTE_BODY_MAX_LENGTH
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(if (editing) "개인 메모 수정" else "개인 메모 추가") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                OutlinedTextField(
                    value = title,
                    onValueChange = onTitleChange,
                    label = { Text("제목") },
                    singleLine = true,
                    supportingText = { Text("${title.length}/$CONCEPT_NOTE_TITLE_MAX_LENGTH") },
                    modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                    value = body,
                    onValueChange = onBodyChange,
                    label = { Text("내용") },
                    placeholder = { Text("웹 주소(http:// 또는 https://)는 저장 후 바로 누를 수 있습니다.") },
                    supportingText = { Text("${body.length}/$CONCEPT_NOTE_BODY_MAX_LENGTH") },
                    minLines = 5,
                    maxLines = 10,
                    modifier = Modifier.fillMaxWidth().heightIn(min = 160.dp),
                )
                errorMessage?.let {
                    Text(
                        it,
                        color = MaterialTheme.colorScheme.error,
                        style = MaterialTheme.typography.bodySmall,
                        modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite },
                    )
                }
            }
        },
        confirmButton = {
            TextButton(onClick = onSave, enabled = canSave) { Text("저장") }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text("취소") }
        },
    )
}

@Suppress("DEPRECATION")
@Composable
private fun LinkifiedConceptNoteBody(body: String) {
    val uriHandler = LocalUriHandler.current
    val linkColor = MaterialTheme.colorScheme.primary
    val bodyColor = MaterialTheme.colorScheme.onSurface
    val links = remember(body) { findHttpUrlRanges(body) }
    var openError by rememberSaveable(body) { mutableStateOf<String?>(null) }
    val annotatedBody = remember(body, links, linkColor) {
        buildAnnotatedString {
            var cursor = 0
            links.forEach { link ->
                append(body.substring(cursor, link.start))
                pushStringAnnotation(URL_ANNOTATION_TAG, link.url)
                pushStyle(SpanStyle(color = linkColor, textDecoration = TextDecoration.Underline))
                append(link.url)
                pop()
                pop()
                cursor = link.endExclusive
            }
            append(body.substring(cursor))
        }
    }
    ClickableText(
        text = annotatedBody,
        style = MaterialTheme.typography.bodyMedium.copy(color = bodyColor),
        onClick = { offset ->
            annotatedBody.getStringAnnotations(URL_ANNOTATION_TAG, offset, offset)
                .firstOrNull()
                ?.let { annotation ->
                    runCatching { uriHandler.openUri(annotation.item) }
                        .onSuccess { openError = null }
                        .onFailure { openError = "링크를 열 수 없습니다. 주소와 브라우저 상태를 확인해 주세요." }
                }
        },
    )
    openError?.let {
        Spacer(Modifier.height(8.dp))
        Text(
            it,
            color = MaterialTheme.colorScheme.error,
            style = MaterialTheme.typography.bodySmall,
            modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite },
        )
    }
}
