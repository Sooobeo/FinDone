package com.findone.app.ui

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
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.filled.Star
import androidx.compose.material.icons.outlined.StarBorder
import androidx.compose.material3.Checkbox
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.IconToggleButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedCard
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.findone.app.AppViewModel

private const val BOOKMARKED_CATEGORY = "__GLOSSARY_BOOKMARKED__"

/**
 * Content-derived glossary grouped by learning element.
 *
 * [onBack] is optional so the screen can be embedded either as a top-level destination or as a
 * page opened from Home. The checked/bookmarked values remain in [AppViewModel]'s user database.
 */
@Composable
fun GlossaryScreen(
    vm: AppViewModel,
    onBack: (() -> Unit)? = null,
    modifier: Modifier = Modifier,
) {
    val allTerms = remember(vm.allElements) { glossaryTerms(vm.allElements) }
    val termStates = vm.glossaryTermStates
    val domainIds = remember(vm.domains) { vm.domains.map { it.id } }
    var selectedCategory by rememberSaveable {
        mutableStateOf(domainIds.firstOrNull() ?: BOOKMARKED_CATEGORY)
    }

    LaunchedEffect(domainIds) {
        if (selectedCategory != BOOKMARKED_CATEGORY && selectedCategory !in domainIds) {
            selectedCategory = domainIds.firstOrNull() ?: BOOKMARKED_CATEGORY
        }
    }

    val visibleTerms = remember(allTerms, termStates, selectedCategory) {
        when (selectedCategory) {
            BOOKMARKED_CATEGORY -> allTerms.filter { termStates[it.id]?.bookmarked == true }
            else -> allTerms.filter { it.domainId == selectedCategory }
        }
    }
    val groupedTerms = remember(visibleTerms) {
        visibleTerms.groupBy(GlossaryTerm::elementId).values.toList()
    }
    val selectedDomain = vm.domains.firstOrNull { it.id == selectedCategory }
    val checkedCount = visibleTerms.count { termStates[it.id]?.checked == true }
    val bookmarkedCount = allTerms.count { termStates[it.id]?.bookmarked == true }
    val glossaryListState = rememberLazyListState()

    LaunchedEffect(selectedCategory) {
        glossaryListState.scrollToItem(0)
    }

    Column(
        modifier = modifier
            .widthIn(max = 860.dp)
            .fillMaxSize()
            .padding(start = 20.dp, end = 20.dp, top = 20.dp, bottom = 20.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.Top,
        ) {
            if (onBack != null) {
                IconButton(onClick = onBack) {
                    Icon(
                        Icons.AutoMirrored.Outlined.ArrowBack,
                        contentDescription = "이전 페이지로",
                    )
                }
                Spacer(Modifier.width(4.dp))
            }
            PageHeader(
                eyebrow = "GLOSSARY",
                title = "금융 용어집",
                description = "대단원을 선택해 소주제별 용어를 익히고, 다시 볼 용어에는 별을 표시하세요.",
                modifier = Modifier.weight(1f),
            )
        }

        LazyRow(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            item(key = BOOKMARKED_CATEGORY) {
                FilterChip(
                    selected = selectedCategory == BOOKMARKED_CATEGORY,
                    onClick = { selectedCategory = BOOKMARKED_CATEGORY },
                    leadingIcon = {
                        Icon(
                            if (selectedCategory == BOOKMARKED_CATEGORY) {
                                Icons.Filled.Star
                            } else {
                                Icons.Outlined.StarBorder
                            },
                            contentDescription = null,
                            modifier = Modifier.size(18.dp),
                        )
                    },
                    label = { Text("북마크 $bookmarkedCount") },
                )
            }
            items(vm.domains, key = { it.id }) { domain ->
                FilterChip(
                    selected = selectedCategory == domain.id,
                    onClick = { selectedCategory = domain.id },
                    label = { Text("${domain.id} · ${domain.name}") },
                )
            }
        }

        val scopeName = if (selectedCategory == BOOKMARKED_CATEGORY) {
            "북마크한 용어"
        } else {
            listOfNotNull(selectedDomain?.id, selectedDomain?.name).joinToString(" · ")
        }
        SectionTitle(
            title = scopeName.ifBlank { "용어" },
            trailing = "$checkedCount / ${visibleTerms.size} 학습",
        )

        OutlinedCard(
            modifier = Modifier
                .fillMaxWidth()
                .weight(1f),
        ) {
            if (groupedTerms.isEmpty()) {
                EmptyGlossaryState(
                    bookmarked = selectedCategory == BOOKMARKED_CATEGORY,
                    modifier = Modifier.fillMaxSize(),
                )
            } else {
                LazyColumn(
                    modifier = Modifier.fillMaxSize(),
                    state = glossaryListState,
                    contentPadding = PaddingValues(12.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    items(
                        items = groupedTerms,
                        key = { terms -> terms.first().elementId },
                    ) { terms ->
                        val first = terms.first()
                        val domainName = vm.domains.firstOrNull { it.id == first.domainId }?.name
                        GlossaryElementCard(
                            domainName = domainName,
                            terms = terms,
                            isChecked = { term -> termStates[term.id]?.checked == true },
                            isBookmarked = { term -> termStates[term.id]?.bookmarked == true },
                            onCheckedChange = vm::setGlossaryTermChecked,
                            onBookmarkedChange = vm::setGlossaryTermBookmarked,
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun GlossaryElementCard(
    domainName: String?,
    terms: List<GlossaryTerm>,
    isChecked: (GlossaryTerm) -> Boolean,
    isBookmarked: (GlossaryTerm) -> Boolean,
    onCheckedChange: (String, Boolean) -> Unit,
    onBookmarkedChange: (String, Boolean) -> Unit,
) {
    val first = terms.first()
    OutlinedCard(modifier = Modifier.fillMaxWidth()) {
        Column {
            Row(
                modifier = Modifier.fillMaxWidth().padding(16.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                DomainBadge(first.domainId)
                Spacer(Modifier.width(10.dp))
                Column(modifier = Modifier.weight(1f)) {
                    if (domainName != null) {
                        Text(
                            text = domainName,
                            style = MaterialTheme.typography.labelMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    Text(
                        text = "${first.elementId} · ${first.elementTitle}",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold,
                    )
                }
                Text(
                    text = "${terms.size}개",
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }

            HorizontalDivider()
            terms.forEachIndexed { index, term ->
                GlossaryTermRow(
                    term = term,
                    checked = isChecked(term),
                    bookmarked = isBookmarked(term),
                    onCheckedChange = { onCheckedChange(term.id, it) },
                    onBookmarkedChange = { onBookmarkedChange(term.id, it) },
                )
                if (index != terms.lastIndex) {
                    HorizontalDivider(modifier = Modifier.padding(start = 16.dp))
                }
            }
        }
    }
}

@Composable
private fun GlossaryTermRow(
    term: GlossaryTerm,
    checked: Boolean,
    bookmarked: Boolean,
    onCheckedChange: (Boolean) -> Unit,
    onBookmarkedChange: (Boolean) -> Unit,
) {
    Row(
        modifier = Modifier.fillMaxWidth().padding(start = 12.dp, end = 6.dp, top = 10.dp, bottom = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(
            modifier = Modifier.weight(1f).padding(start = 6.dp, end = 4.dp),
            verticalArrangement = Arrangement.spacedBy(3.dp),
        ) {
            Text(
                text = term.term,
                style = MaterialTheme.typography.bodyLarge,
                fontWeight = FontWeight.SemiBold,
            )
            Text(
                text = term.description,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        Checkbox(
            checked = checked,
            onCheckedChange = onCheckedChange,
            modifier = Modifier.semantics {
                contentDescription = "${term.term} 학습 완료"
            },
        )
        IconToggleButton(
            checked = bookmarked,
            onCheckedChange = onBookmarkedChange,
        ) {
            Icon(
                imageVector = if (bookmarked) Icons.Filled.Star else Icons.Outlined.StarBorder,
                contentDescription = if (bookmarked) {
                    "${term.term} 북마크 해제"
                } else {
                    "${term.term} 북마크 추가"
                },
                tint = if (bookmarked) {
                    MaterialTheme.colorScheme.tertiary
                } else {
                    MaterialTheme.colorScheme.onSurfaceVariant
                },
            )
        }
    }
}

@Composable
private fun EmptyGlossaryState(
    bookmarked: Boolean,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier.fillMaxWidth().padding(vertical = 42.dp, horizontal = 20.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(8.dp, Alignment.CenterVertically),
    ) {
        Icon(
            Icons.Outlined.StarBorder,
            contentDescription = null,
            tint = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.size(40.dp),
        )
        Text(
            text = if (bookmarked) "북마크한 용어가 없습니다" else "표시할 용어가 없습니다",
            fontWeight = FontWeight.Bold,
        )
        Text(
            text = if (bookmarked) {
                "각 용어 오른쪽의 별을 누르면 이곳에 모아볼 수 있습니다."
            } else {
                "이 대단원의 용어 데이터를 불러오지 못했습니다."
            },
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}
