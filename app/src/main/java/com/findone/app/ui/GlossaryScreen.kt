package com.findone.app.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.filled.Star
import androidx.compose.material.icons.outlined.CheckCircle
import androidx.compose.material.icons.outlined.CloudOff
import androidx.compose.material.icons.outlined.Search
import androidx.compose.material.icons.outlined.StarBorder
import androidx.compose.material3.Checkbox
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.IconToggleButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedCard
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.findone.app.AppViewModel
import com.findone.app.BuildConfig
import com.findone.app.data.LearningTextAnnotation
import com.findone.app.model.GlossaryTerm
import com.findone.app.model.GlossaryTermSummary

@Composable
fun GlossaryScreen(
    vm: AppViewModel,
    onBack: (() -> Unit)? = null,
    modifier: Modifier = Modifier,
) {
    val selected = vm.selectedGlossaryTerm
    if (selected != null) {
        GlossaryDetail(vm = vm, term = selected, onBack = vm::closeGlossaryTerm, modifier = modifier)
        return
    }

    val selectedCategory = vm.glossaryCategoryId
    val bookmarkedMode = vm.glossaryBookmarkedOnly
    val visibleTerms = remember(
        vm.glossaryResults,
        vm.glossaryTermStates,
        bookmarkedMode,
    ) {
        if (bookmarkedMode) {
            vm.glossaryResults.filter { vm.glossaryTermStates[it.id]?.bookmarked == true }
        } else {
            vm.glossaryResults
        }
    }
    val checkedCount = visibleTerms.count { vm.glossaryTermStates[it.id]?.checked == true }
    val bookmarkedCount = vm.glossaryTermStates.values.count { it.bookmarked }

    Column(
        modifier = modifier
            .widthIn(max = 860.dp)
            .fillMaxSize()
            .padding(start = 20.dp, end = 20.dp, top = 20.dp, bottom = 20.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.Top) {
            if (onBack != null) {
                IconButton(onClick = onBack) {
                    Icon(Icons.AutoMirrored.Outlined.ArrowBack, contentDescription = "이전 페이지로")
                }
                Spacer(Modifier.width(4.dp))
            }
            PageHeader(
                eyebrow = "OFFLINE GLOSSARY",
                title = "금융 실무 용어집",
                description = "사전에 작성·검증된 DB를 내려받아 기기 안에서만 검색합니다. 검색 중에는 AI나 네트워크를 사용하지 않습니다.",
                modifier = Modifier.weight(1f),
            )
        }

        OutlinedTextField(
            value = vm.glossaryQuery,
            onValueChange = vm::updateGlossaryQuery,
            modifier = Modifier.fillMaxWidth(),
            singleLine = true,
            leadingIcon = { Icon(Icons.Outlined.Search, contentDescription = null) },
            label = { Text("한글·영문·약어·설명 검색") },
            supportingText = {
                Text(
                    "로컬 DB v${vm.glossaryManifest?.glossaryDbVersion ?: "-"} · " +
                        "${vm.glossaryManifest?.rowCounts?.get("terms") ?: 0}개 용어"
                )
            },
        )

        LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            item(key = "__ALL__") {
                FilterChip(
                    selected = selectedCategory == null && !bookmarkedMode,
                    onClick = { vm.setGlossaryCategory(null) },
                    label = { Text("전체") },
                )
            }
            item(key = "__GLOSSARY_BOOKMARKED__") {
                FilterChip(
                    selected = bookmarkedMode,
                    onClick = {
                        // Bookmark filtering still queries the complete local index first.
                        vm.showBookmarkedGlossaryTerms()
                    },
                    leadingIcon = {
                        Icon(
                            if (bookmarkedMode) Icons.Filled.Star else Icons.Outlined.StarBorder,
                            contentDescription = null,
                            modifier = Modifier.size(18.dp),
                        )
                    },
                    label = { Text("북마크 $bookmarkedCount") },
                )
            }
            items(vm.glossaryCategories, key = { it.id }) { category ->
                FilterChip(
                    selected = selectedCategory == category.id,
                    onClick = { vm.setGlossaryCategory(category.id) },
                    label = { Text("${category.id} · ${category.name}") },
                )
            }
        }

        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Text(
                if (bookmarkedMode) "북마크" else "검색 결과",
                modifier = Modifier.weight(1f),
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
            )
            Text(
                "$checkedCount / ${visibleTerms.size} 학습",
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }

        vm.glossaryError?.let { message ->
            OutlinedCard(Modifier.fillMaxWidth()) {
                Text(
                    message,
                    modifier = Modifier.padding(14.dp),
                    color = MaterialTheme.colorScheme.error,
                    style = MaterialTheme.typography.bodySmall,
                )
            }
        }

        OutlinedCard(Modifier.fillMaxWidth().weight(1f)) {
            if (visibleTerms.isEmpty()) {
                EmptyGlossaryState(bookmarkedMode, Modifier.fillMaxSize())
            } else {
                LazyColumn(
                    modifier = Modifier.fillMaxSize(),
                    contentPadding = PaddingValues(vertical = 4.dp),
                ) {
                    items(visibleTerms, key = { it.id }) { term ->
                        GlossaryTermRow(
                            term = term,
                            checked = vm.glossaryTermStates[term.id]?.checked == true,
                            bookmarked = vm.glossaryTermStates[term.id]?.bookmarked == true,
                            onOpen = { vm.openGlossaryTerm(term.id) },
                            onCheckedChange = { vm.setGlossaryTermChecked(term.id, it) },
                            onBookmarkedChange = { vm.setGlossaryTermBookmarked(term.id, it) },
                        )
                        HorizontalDivider(modifier = Modifier.padding(start = 16.dp))
                    }
                }
            }
        }

        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(
                Icons.Outlined.CloudOff,
                contentDescription = null,
                modifier = Modifier.size(18.dp),
                tint = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Spacer(Modifier.width(7.dp))
            Text(
                vm.glossaryUpdateMessage
                    ?: if (vm.glossaryUpdateInProgress) "새 용어집 DB 확인 중" else "현재 검색은 완전 오프라인",
                modifier = Modifier.weight(1f),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            if (BuildConfig.GLOSSARY_RELEASE_ENDPOINT.isNotBlank()) {
                TextButton(
                    onClick = { vm.checkForGlossaryUpdate(force = true) },
                    enabled = !vm.glossaryUpdateInProgress,
                ) { Text("업데이트 확인") }
            }
        }
    }
}

@Composable
private fun GlossaryTermRow(
    term: GlossaryTermSummary,
    checked: Boolean,
    bookmarked: Boolean,
    onOpen: () -> Unit,
    onCheckedChange: (Boolean) -> Unit,
    onBookmarkedChange: (Boolean) -> Unit,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(role = Role.Button, onClick = onOpen)
            .padding(start = 14.dp, end = 6.dp, top = 12.dp, bottom = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
            Text(term.canonicalNameEn, fontWeight = FontWeight.SemiBold)
            Text(
                term.canonicalNameKo,
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.primary,
            )
            Text(
                term.oneLineDefinitionKo,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            if (term.aliases.isNotEmpty()) {
                Text(
                    term.aliases.take(4).joinToString(" · "),
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
        Checkbox(
            checked = checked,
            onCheckedChange = onCheckedChange,
            modifier = Modifier.semantics { contentDescription = "${term.canonicalNameEn} 학습 완료" },
        )
        IconToggleButton(checked = bookmarked, onCheckedChange = onBookmarkedChange) {
            Icon(
                if (bookmarked) Icons.Filled.Star else Icons.Outlined.StarBorder,
                contentDescription = if (bookmarked) "북마크 해제" else "북마크 추가",
                tint = if (bookmarked) MaterialTheme.colorScheme.tertiary
                else MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Composable
private fun GlossaryDetail(
    vm: AppViewModel,
    term: GlossaryTerm,
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val state = vm.glossaryTermStates[term.id]
    LazyColumn(
        modifier = modifier.widthIn(max = 860.dp).fillMaxSize(),
        contentPadding = PaddingValues(start = 20.dp, end = 20.dp, top = 16.dp, bottom = 36.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        item {
            Row(verticalAlignment = Alignment.Top) {
                IconButton(onClick = onBack) {
                    Icon(Icons.AutoMirrored.Outlined.ArrowBack, contentDescription = "용어 목록으로")
                }
                Spacer(Modifier.width(4.dp))
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                    Text(
                        "${term.categoryId} · ${term.categoryName}",
                        style = MaterialTheme.typography.labelLarge,
                        color = MaterialTheme.colorScheme.primary,
                    )
                    Text(
                        term.canonicalNameEn,
                        style = MaterialTheme.typography.headlineMedium,
                        fontWeight = FontWeight.Bold,
                    )
                    Text(term.canonicalNameKo, style = MaterialTheme.typography.titleLarge)
                    if (term.aliases.isNotEmpty()) {
                        Text(
                            "다른 표기 · ${term.aliases.joinToString(" · ")}",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
                IconToggleButton(
                    checked = state?.bookmarked == true,
                    onCheckedChange = { vm.setGlossaryTermBookmarked(term.id, it) },
                ) {
                    Icon(
                        if (state?.bookmarked == true) Icons.Filled.Star else Icons.Outlined.StarBorder,
                        contentDescription = "용어 북마크",
                    )
                }
            }
        }

        item {
            OutlinedCard(Modifier.fillMaxWidth()) {
                Row(
                    Modifier.fillMaxWidth().padding(14.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Icon(Icons.Outlined.CheckCircle, contentDescription = null)
                    Spacer(Modifier.width(8.dp))
                    Text("이 용어를 학습함", modifier = Modifier.weight(1f), fontWeight = FontWeight.SemiBold)
                    Checkbox(
                        checked = state?.checked == true,
                        onCheckedChange = { vm.setGlossaryTermChecked(term.id, it) },
                    )
                }
            }
        }

        glossarySection(vm, "glossary_one_line", "한 문장 정의", term.oneLineDefinitionKo)
        glossarySection(vm, "glossary_core", "핵심 의미", term.coreDefinitionKo)
        glossarySection(vm, "glossary_context", "실무 문맥", term.practicalContextKo)
        glossarySection(vm, "glossary_importance", "왜 중요한가", term.whyItMattersKo)
        glossarySection(vm, "glossary_example", "예시", term.exampleKo)
        glossarySection(
            vm,
            "glossary_limitations",
            "주의·한계",
            term.limitationsKo.joinToString("\n") { "- $it" },
        )
        if (term.formulaLatex.isNotBlank() || term.formulaNotesKo.isNotBlank()) {
            glossarySection(
                vm,
                "glossary_formula",
                "공식",
                listOf(
                    term.formulaLatex.takeIf(String::isNotBlank)?.let { "\$\$\n$it\n\$\$" },
                    term.formulaNotesKo.takeIf(String::isNotBlank),
                ).filterNotNull().joinToString("\n\n"),
            )
        }

        if (term.relatedTerms.isNotEmpty()) {
            item {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("관련 용어", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                    term.relatedTerms.forEach { related ->
                        OutlinedCard(
                            modifier = Modifier.fillMaxWidth().clickable { vm.openGlossaryTerm(related.id) }
                        ) {
                            Column(Modifier.padding(13.dp)) {
                                Text(related.canonicalNameEn, fontWeight = FontWeight.SemiBold)
                                Text(
                                    related.canonicalNameKo,
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                )
                            }
                        }
                    }
                }
            }
        }

        item {
            LearningAnnotationManager(
                annotations = vm.glossaryTextAnnotations,
                onSetComment = vm::setGlossaryTextAnnotationComment,
                onDelete = vm::deleteGlossaryTextAnnotation,
            )
        }
        item {
            ConceptNotesSection(
                elementId = "GLOSSARY:${term.id}",
                subjectName = "용어",
                notes = vm.glossaryNotes,
                errorMessage = vm.glossaryNoteError,
                onDismissError = vm::clearGlossaryNoteError,
                onAdd = vm::addGlossaryNote,
                onUpdate = vm::updateGlossaryNote,
                onDelete = vm::deleteGlossaryNote,
            )
        }
        item {
            Text(
                "${term.conceptType} · 기준일 ${term.asOfDate} · 사전 작성된 오프라인 콘텐츠",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

private fun androidx.compose.foundation.lazy.LazyListScope.glossarySection(
    vm: AppViewModel,
    sectionKey: String,
    title: String,
    markdown: String,
) {
    item(key = sectionKey) {
        val annotations = vm.glossaryTextAnnotations.filter { it.anchor.sectionKey == sectionKey }
        OutlinedCard(Modifier.fillMaxWidth()) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(9.dp)) {
                Text(title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                AnnotatableMarkdown(
                    sectionKey = sectionKey,
                    markdown = markdown,
                    annotations = annotations,
                    onAdd = { action, comment ->
                        vm.addGlossaryTextAnnotation(
                            sectionKey = sectionKey,
                            sourceText = action.sourceText,
                            startOffset = action.startOffset,
                            endOffset = action.endOffset,
                            style = action.style,
                            comment = comment,
                        )
                    },
                    onSetComment = vm::setGlossaryTextAnnotationComment,
                    onDelete = vm::deleteGlossaryTextAnnotation,
                    style = MaterialTheme.typography.bodyLarge,
                    color = MaterialTheme.colorScheme.onSurface,
                )
            }
        }
    }
}

@Composable
private fun EmptyGlossaryState(bookmarked: Boolean, modifier: Modifier = Modifier) {
    Column(
        modifier = modifier.fillMaxWidth().padding(vertical = 42.dp, horizontal = 20.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(8.dp, Alignment.CenterVertically),
    ) {
        Icon(
            if (bookmarked) Icons.Outlined.StarBorder else Icons.Outlined.Search,
            contentDescription = null,
            tint = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.size(40.dp),
        )
        Text(
            if (bookmarked) "북마크한 용어가 없습니다" else "검색 결과가 없습니다",
            fontWeight = FontWeight.Bold,
        )
        Text(
            if (bookmarked) "용어 오른쪽의 별을 눌러 모아보세요."
            else "다른 한글·영문·약어로 검색해 보세요.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}
