package com.findone.app

import android.app.Application
import android.content.ContentResolver
import android.net.Uri
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.viewModelScope
import com.findone.app.data.AttemptInput
import com.findone.app.data.AttemptRecord
import com.findone.app.data.BookmarkInput
import com.findone.app.data.BookmarkOrigin
import com.findone.app.data.BookmarkRecord
import com.findone.app.data.ConceptNote
import com.findone.app.data.ContentRepository
import com.findone.app.data.ContentUpdateManager
import com.findone.app.data.ContentUpdateResult
import com.findone.app.data.ElementProgress
import com.findone.app.data.GlossaryTermState
import com.findone.app.data.LearningTextAnnotation
import com.findone.app.data.StudyStats
import com.findone.app.data.TextAnnotationStyle
import com.findone.app.data.UserRepository
import com.findone.app.data.buildLearningTextAnchor
import com.findone.app.model.ContentElement
import com.findone.app.model.ContentManifest
import com.findone.app.model.Domain
import com.findone.app.quiz.ElementSeed
import com.findone.app.quiz.CuratedConceptQuestion
import com.findone.app.quiz.ExplanationSteps
import com.findone.app.quiz.MentalMathAudit
import com.findone.app.quiz.MentalMathOperation
import com.findone.app.quiz.QuestionSnapshot
import com.findone.app.quiz.QuizAnswer
import com.findone.app.quiz.QuizAnswerKind
import com.findone.app.quiz.QuizChoice
import com.findone.app.quiz.QuizEngine
import com.findone.app.quiz.QuizMode
import com.findone.app.quiz.QuizPresentation
import com.findone.app.quiz.QuizQuestion
import com.findone.app.quiz.QuizTemplateIdentity
import org.json.JSONArray
import org.json.JSONObject
import java.util.Random
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlin.math.ceil
import kotlin.math.floor

enum class MainTab { HOME, STUDY, QUIZ, RECORDS, GLOSSARY }

private const val QUIZ_DOMAIN_IDS_STATE = "quizDomainIds"
private const val QUIZ_DOMAIN_ID_STATE = "quizDomainId"
private const val QUIZ_TRACK_STATE = "quizTrack"
private const val NAVIGATION_HISTORY_STATE = "navigationHistory"
private const val STUDY_DOMAIN_STATE = "studyDomainId"
private const val STUDY_QUERY_STATE = "studyQuery"
private const val MAX_NAVIGATION_HISTORY = 32
private const val ELEMENT_ROUTE_PREFIX = "ELEMENT:"

private fun MainTab.routeKey(): String = name

private fun isRestorableRoute(route: String, validElementIds: Set<String>? = null): Boolean {
    if (MainTab.entries.any { tab -> tab.routeKey() == route }) return true
    if (!route.startsWith(ELEMENT_ROUTE_PREFIX)) return false
    val elementId = route.removePrefix(ELEMENT_ROUTE_PREFIX)
    return elementId.isNotBlank() && (validElementIds == null || elementId in validElementIds)
}

internal fun normalizeNavigationHistory(
    restoredRoutes: Collection<String>?,
    validElementIds: Set<String>? = null,
): List<String> {
    val normalized = mutableListOf<String>()
    restoredRoutes.orEmpty().forEach { route ->
        if (isRestorableRoute(route, validElementIds) && normalized.lastOrNull() != route) {
            normalized += route
        }
    }
    return normalized.takeLast(MAX_NAVIGATION_HISTORY)
}

internal fun navigationHistoryAfterQuizExitTo(
    history: List<String>,
    destination: MainTab,
): List<String> = if (destination == MainTab.HOME) {
    emptyList()
} else {
    history.dropLastWhile { it == destination.routeKey() }
}

internal fun normalizeQuizDomainSelection(
    availableDomainIds: Collection<String>,
    restoredDomainIds: Collection<String>?,
): Set<String> {
    val available = availableDomainIds.distinct()
    val requested = restoredDomainIds?.toSet() ?: available.toSet()
    return available.asSequence()
        .filter { it in requested }
        .toCollection(linkedSetOf())
}

internal fun quizDomainFilter(
    track: QuizTrack,
    selectedDomainIds: Set<String>,
    singleDomainId: String?,
): Set<String>? = if (track == QuizTrack.DOMAIN) {
    selectedDomainIds
} else {
    singleDomainId?.let(::setOf)
}

enum class QuizTrack(val title: String, val description: String) {
    DOMAIN("분야별 학습", "선택한 분야의 요소를 고르게 섞습니다."),
    WEAK("약점 집중", "최근 오답이 남은 요소부터 다시 풉니다."),
    SPRINT("금융권 스프린트", "30·60·90초 개념·계산 문제를 섞습니다."),
    CONCEPT("개념 랜덤", "핵심 관계와 흔한 혼동을 객관식으로 점검합니다."),
    ORAL("구술 연습", "30~60초로 답한 뒤 핵심 관계와 스스로 비교합니다."),
    CASE("통합 케이스", "리서치·기업가치·딜 요소를 연결해 연습합니다."),
    BOOKMARK("북마크 복습", "저장한 문제 snapshot을 같은 seed로 재생합니다."),
}

data class QuizSessionState(
    val track: QuizTrack,
    val questions: List<QuizQuestion>,
    val presentations: List<QuizPresentation> = List(questions.size) { track.presentation() },
    val currentIndex: Int = 0,
    val userAnswer: String = "",
    val submitted: Boolean = false,
    val wasCorrect: Boolean? = null,
    val correctCount: Int = 0,
    val questionStartedAt: Long = System.currentTimeMillis(),
    val finished: Boolean = false,
) {
    init {
        require(presentations.size == questions.size) { "Each quiz question needs one presentation mode" }
    }

    val currentQuestion: QuizQuestion?
        get() = questions.getOrNull(currentIndex)
    val currentPresentation: QuizPresentation
        get() = presentations.getOrElse(currentIndex) { track.presentation() }
}

private data class WeakTemplateTarget(
    val mode: QuizMode,
    val presentation: QuizPresentation,
    val seed: Long,
    val templateId: String,
)

class AppViewModel(
    application: Application,
    private val savedStateHandle: SavedStateHandle,
) : AndroidViewModel(application) {
    private val userRepository = UserRepository(application)
    private var contentRepository: ContentRepository? = null
    private var conceptQuestionsByElement: Map<String, List<CuratedConceptQuestion>> = emptyMap()

    var domains by mutableStateOf<List<Domain>>(emptyList())
        private set
    var allElements by mutableStateOf<List<ContentElement>>(emptyList())
        private set
    var contentManifest by mutableStateOf<ContentManifest?>(null)
        private set

    var contentError by mutableStateOf<String?>(null)
        private set
    var contentUpdateInProgress by mutableStateOf(false)
        private set
    var contentUpdateMessage by mutableStateOf<String?>(null)
        private set
    var currentTab by mutableStateOf(
        runCatching { MainTab.valueOf(savedStateHandle["tab"] ?: MainTab.HOME.name) }.getOrDefault(MainTab.HOME)
    )
        private set
    var selectedElementId by mutableStateOf(savedStateHandle.get<String>("elementId"))
        private set
    var studyDomainId by mutableStateOf(savedStateHandle.get<String>(STUDY_DOMAIN_STATE))
        private set
    var studyQuery by mutableStateOf(savedStateHandle.get<String>(STUDY_QUERY_STATE).orEmpty())
        private set
    var studyResults by mutableStateOf<List<ContentElement>>(emptyList())
        private set
    var quizDomainId by mutableStateOf(savedStateHandle.get<String>(QUIZ_DOMAIN_ID_STATE))
        private set
    var quizDomainIds by mutableStateOf<Set<String>>(emptySet())
        private set
    var quizDifficulty by mutableStateOf(1)
        private set
    var quizCount by mutableStateOf(10)
        private set
    var selectedTrack by mutableStateOf(
        runCatching {
            QuizTrack.valueOf(savedStateHandle[QUIZ_TRACK_STATE] ?: QuizTrack.DOMAIN.name)
        }.getOrDefault(QuizTrack.DOMAIN)
    )
        private set
    var quizSession by mutableStateOf<QuizSessionState?>(null)
        private set
    var quizMessage by mutableStateOf<String?>(null)
        private set
    var stats by mutableStateOf(StudyStats())
        private set
    var progress by mutableStateOf<Map<String, ElementProgress>>(emptyMap())
        private set
    var conceptNotes by mutableStateOf<List<ConceptNote>>(emptyList())
        private set
    var conceptNoteError by mutableStateOf<String?>(null)
        private set
    var textAnnotations by mutableStateOf<List<LearningTextAnnotation>>(emptyList())
        private set
    var textAnnotationError by mutableStateOf<String?>(null)
        private set
    var glossaryTermStates by mutableStateOf<Map<String, GlossaryTermState>>(emptyMap())
        private set
    var recordDomainId by mutableStateOf(savedStateHandle.get<String>("recordDomainId"))
        private set
    var recordElementId by mutableStateOf(savedStateHandle.get<String>("recordElementId"))
        private set
    var bookmarks by mutableStateOf<List<BookmarkRecord>>(emptyList())
        private set
    var recordBookmarks by mutableStateOf<List<BookmarkRecord>>(emptyList())
        private set
    var recentWrong by mutableStateOf<List<AttemptRecord>>(emptyList())
        private set
    var recordUnresolvedWrongCount by mutableStateOf(0)
        private set
    var resolutionSuggestions by mutableStateOf<Set<String>>(emptySet())
        private set
    var autoBookmarkWrong by mutableStateOf(userRepository.setting("auto_bookmark_wrong", "false").toBoolean())
        private set
    private var navigationHistory by mutableStateOf(
        normalizeNavigationHistory(savedStateHandle.get<ArrayList<String>>(NAVIGATION_HISTORY_STATE))
    )

    init {
        var repository: ContentRepository? = null
        var loadedDomains = emptyList<Domain>()
        var loadedElements = emptyList<ContentElement>()
        var loadedConceptQuestions = emptyList<CuratedConceptQuestion>()
        var loadedManifest: ContentManifest? = null
        runCatching {
            ContentRepository(application).also { repo ->
                repository = repo
                loadedDomains = repo.domains()
                loadedElements = repo.elements()
                loadedConceptQuestions = repo.conceptQuestions()
                loadedManifest = repo.manifest
            }
        }.onFailure { contentError = it.message ?: "콘텐츠 DB를 열지 못했습니다." }
        contentRepository = repository
        domains = loadedDomains
        allElements = loadedElements
        conceptQuestionsByElement = loadedConceptQuestions.groupBy { it.elementId }
        contentManifest = loadedManifest
        studyDomainId = studyDomainId?.takeIf { id -> domains.any { it.id == id } }
        if (studyDomainId == null) savedStateHandle.remove<String>(STUDY_DOMAIN_STATE)
        selectedElementId = selectedElementId?.takeIf { id -> allElements.any { it.id == id } }
        if (selectedElementId == null) savedStateHandle.remove<String>("elementId")
        navigationHistory = normalizeNavigationHistory(
            restoredRoutes = navigationHistory,
            validElementIds = allElements.mapTo(hashSetOf()) { it.id },
        )
        persistNavigationHistory()
        updateStudyResults()
        val availableDomainIds = domains.map { it.id }
        quizDomainId = quizDomainId?.takeIf { it in availableDomainIds }
        quizDomainIds = normalizeQuizDomainSelection(
            availableDomainIds = availableDomainIds,
            restoredDomainIds = savedStateHandle.get<ArrayList<String>>(QUIZ_DOMAIN_IDS_STATE),
        )
        persistQuizDomainSelection()
        if (quizDomainId == null) savedStateHandle.remove<String>(QUIZ_DOMAIN_ID_STATE)
        recordDomainId = recordDomainId?.takeIf { id -> domains.any { it.id == id } }
        recordElementId = recordElementId?.takeIf { id ->
            allElements.any { element ->
                element.id == id && (recordDomainId == null || element.domainId == recordDomainId)
            }
        }
        refreshUserData()
        refreshGlossaryTermStates()
        refreshConceptNotes()
        refreshTextAnnotations()
        savedStateHandle.get<String>("quizSession")?.let { saved ->
            runCatching { restoreQuizSession(saved) }
                .onSuccess { quizSession = it }
                .onFailure { savedStateHandle.remove<String>("quizSession") }
        }
        checkForContentUpdate()
    }

    fun checkForContentUpdate() {
        if (BuildConfig.CONTENT_RELEASE_ENDPOINT.isBlank() || contentUpdateInProgress) return
        val currentVersion = contentManifest?.contentDbVersion ?: return
        contentUpdateInProgress = true
        contentUpdateMessage = null
        viewModelScope.launch {
            try {
                when (val result = withContext(Dispatchers.IO) {
                    ContentUpdateManager(getApplication()).updateIfAvailable(currentVersion)
                }) {
                    ContentUpdateResult.Disabled,
                    ContentUpdateResult.Current -> Unit
                    is ContentUpdateResult.Failed -> {
                        // A network failure must never block the offline app. Keep the
                        // message available to the data/settings screen without turning it
                        // into a fatal content error.
                        contentUpdateMessage = result.message
                    }
                    is ContentUpdateResult.Installed -> {
                        val loaded = withContext(Dispatchers.IO) {
                            ContentRepository(getApplication()).let { repository ->
                                LoadedContent(
                                    repository = repository,
                                    domains = repository.domains(),
                                    elements = repository.elements(),
                                    conceptQuestions = repository.conceptQuestions(),
                                    manifest = repository.manifest,
                                )
                            }
                        }
                        val previous = contentRepository
                        contentRepository = loaded.repository
                        domains = loaded.domains
                        allElements = loaded.elements
                        conceptQuestionsByElement = loaded.conceptQuestions.groupBy { it.elementId }
                        contentManifest = loaded.manifest
                        previous?.close()
                        normalizeContentSelections()
                        updateStudyResults()
                        refreshGlossaryTermStates()
                        contentUpdateMessage = "콘텐츠 DB v${result.manifest.contentDbVersion} 업데이트 완료"
                    }
                }
            } catch (error: Exception) {
                contentUpdateMessage = error.message ?: "콘텐츠 업데이트를 적용하지 못했습니다."
            } finally {
                contentUpdateInProgress = false
            }
        }
    }

    private fun normalizeContentSelections() {
        val validElementIds = allElements.mapTo(hashSetOf()) { it.id }
        studyDomainId = studyDomainId?.takeIf { id -> domains.any { it.id == id } }
        selectedElementId = selectedElementId?.takeIf { it in validElementIds }
        navigationHistory = normalizeNavigationHistory(navigationHistory, validElementIds)
        persistNavigationHistory()
        val availableDomainIds = domains.map { it.id }
        quizDomainId = quizDomainId?.takeIf { it in availableDomainIds }
        quizDomainIds = normalizeQuizDomainSelection(availableDomainIds, quizDomainIds)
        persistQuizDomainSelection()
        recordDomainId = recordDomainId?.takeIf { it in availableDomainIds }
        recordElementId = recordElementId?.takeIf { id ->
            allElements.any { element ->
                element.id == id && (recordDomainId == null || element.domainId == recordDomainId)
            }
        }
    }

    private data class LoadedContent(
        val repository: ContentRepository,
        val domains: List<Domain>,
        val elements: List<ContentElement>,
        val conceptQuestions: List<CuratedConceptQuestion>,
        val manifest: ContentManifest,
    )

    val selectedElement: ContentElement?
        get() = selectedElementId?.let { id -> allElements.firstOrNull { it.id == id } }

    val canNavigateBack: Boolean
        get() = quizSession != null || selectedElementId != null ||
            currentTab != MainTab.HOME || navigationHistory.isNotEmpty()

    fun selectTab(tab: MainTab) {
        val targetRoute = tab.routeKey()
        if (currentRouteKey() != targetRoute) pushCurrentRoute()
        applyRoute(targetRoute)
    }

    fun openElement(elementId: String) {
        if (allElements.none { it.id == elementId }) return
        if (selectedElementId != elementId) pushCurrentRoute()
        selectedElementId = elementId
        savedStateHandle["elementId"] = elementId
        currentTab = MainTab.STUDY
        savedStateHandle["tab"] = MainTab.STUDY.name
        refreshConceptNotes()
        refreshTextAnnotations()
    }

    fun closeElement() {
        if (selectedElementId != null) navigateBack() else clearElementState()
    }

    fun navigateBack(): Boolean {
        if (quizSession != null) return false
        while (navigationHistory.isNotEmpty()) {
            val previous = navigationHistory.last()
            navigationHistory = navigationHistory.dropLast(1)
            if (applyRoute(previous)) {
                persistNavigationHistory()
                return true
            }
        }
        persistNavigationHistory()
        if (selectedElementId != null) {
            clearElementState()
            applyRoute(MainTab.STUDY.routeKey())
            return true
        }
        if (currentTab != MainTab.HOME) {
            applyRoute(MainTab.HOME.routeKey())
            return true
        }
        return false
    }

    private fun clearElementState() {
        selectedElementId = null
        savedStateHandle.remove<String>("elementId")
        conceptNotes = emptyList()
        conceptNoteError = null
        textAnnotations = emptyList()
        textAnnotationError = null
    }

    private fun currentRouteKey(): String = when {
        selectedElementId != null -> "$ELEMENT_ROUTE_PREFIX$selectedElementId"
        else -> currentTab.routeKey()
    }

    private fun pushCurrentRoute() {
        val route = currentRouteKey()
        if (!isRestorableRoute(route) || navigationHistory.lastOrNull() == route) return
        navigationHistory = (navigationHistory + route).takeLast(MAX_NAVIGATION_HISTORY)
        persistNavigationHistory()
    }

    private fun persistNavigationHistory() {
        if (navigationHistory.isEmpty()) savedStateHandle.remove<ArrayList<String>>(NAVIGATION_HISTORY_STATE)
        else savedStateHandle[NAVIGATION_HISTORY_STATE] = ArrayList(navigationHistory)
    }

    private fun applyRoute(route: String): Boolean {
        if (route.startsWith(ELEMENT_ROUTE_PREFIX)) {
            val elementId = route.removePrefix(ELEMENT_ROUTE_PREFIX)
            if (allElements.any { it.id == elementId }) {
                currentTab = MainTab.STUDY
                selectedElementId = elementId
                savedStateHandle["tab"] = MainTab.STUDY.name
                savedStateHandle["elementId"] = elementId
                refreshConceptNotes()
                refreshTextAnnotations()
                return true
            }
            return false
        }

        val tab = MainTab.entries.firstOrNull { it.routeKey() == route } ?: return false
        clearElementState()
        currentTab = tab
        savedStateHandle["tab"] = tab.name
        return true
    }

    fun addConceptNote(title: String, body: String): Boolean {
        val elementId = selectedElement?.id ?: return false
        return runCatching {
            userRepository.addConceptNote(elementId, title, body)
            userRepository.conceptNotes(elementId)
        }
            .fold(
                onSuccess = { refreshedNotes ->
                    conceptNotes = refreshedNotes
                    conceptNoteError = null
                    true
                },
                onFailure = {
                    conceptNoteError = it.message ?: "개인 메모를 저장하지 못했습니다."
                    false
                },
            )
    }

    fun updateConceptNote(noteId: Long, title: String, body: String): Boolean {
        val elementId = selectedElement?.id ?: return false
        return runCatching {
            check(userRepository.updateConceptNote(noteId, elementId, title, body)) {
                "수정할 개인 메모를 찾지 못했습니다."
            }
            userRepository.conceptNotes(elementId)
        }.fold(
            onSuccess = { refreshedNotes ->
                conceptNotes = refreshedNotes
                conceptNoteError = null
                true
            },
            onFailure = {
                conceptNoteError = it.message ?: "개인 메모를 수정하지 못했습니다."
                false
            },
        )
    }

    fun deleteConceptNote(noteId: Long): Boolean {
        val elementId = selectedElement?.id ?: return false
        return runCatching {
            check(userRepository.deleteConceptNote(noteId, elementId)) {
                "삭제할 개인 메모를 찾지 못했습니다."
            }
            userRepository.conceptNotes(elementId)
        }.fold(
            onSuccess = { refreshedNotes ->
                conceptNotes = refreshedNotes
                conceptNoteError = null
                true
            },
            onFailure = {
                conceptNoteError = it.message ?: "개인 메모를 삭제하지 못했습니다."
                false
            },
        )
    }

    fun clearConceptNoteError() {
        conceptNoteError = null
    }

    fun addTextAnnotation(
        sectionKey: String,
        sourceText: String,
        startOffset: Int,
        endOffset: Int,
        style: TextAnnotationStyle,
        comment: String? = null,
    ): Boolean {
        val elementId = selectedElement?.id ?: return false
        return runCatching {
            val anchor = buildLearningTextAnchor(sectionKey, sourceText, startOffset, endOffset)
            userRepository.addTextAnnotation(elementId, anchor, style, comment)
            userRepository.textAnnotations(elementId)
        }.fold(
            onSuccess = { refreshed ->
                textAnnotations = refreshed
                textAnnotationError = null
                true
            },
            onFailure = { error ->
                textAnnotationError = error.message ?: "텍스트 표시를 저장하지 못했습니다."
                false
            },
        )
    }

    fun setTextAnnotationComment(annotationId: Long, comment: String?): Boolean {
        val elementId = selectedElement?.id ?: return false
        return runCatching {
            check(userRepository.setTextAnnotationComment(annotationId, elementId, comment)) {
                "수정할 코멘트를 찾지 못했습니다."
            }
            userRepository.textAnnotations(elementId)
        }.fold(
            onSuccess = { refreshed ->
                textAnnotations = refreshed
                textAnnotationError = null
                true
            },
            onFailure = { error ->
                textAnnotationError = error.message ?: "코멘트를 저장하지 못했습니다."
                false
            },
        )
    }

    fun deleteTextAnnotation(annotationId: Long): Boolean {
        val elementId = selectedElement?.id ?: return false
        return runCatching {
            check(userRepository.deleteTextAnnotation(annotationId, elementId)) {
                "삭제할 텍스트 표시를 찾지 못했습니다."
            }
            userRepository.textAnnotations(elementId)
        }.fold(
            onSuccess = { refreshed ->
                textAnnotations = refreshed
                textAnnotationError = null
                true
            },
            onFailure = { error ->
                textAnnotationError = error.message ?: "텍스트 표시를 삭제하지 못했습니다."
                false
            },
        )
    }

    fun clearTextAnnotationError() {
        textAnnotationError = null
    }

    fun setGlossaryTermChecked(termId: String, checked: Boolean) {
        runCatching { userRepository.setGlossaryTermChecked(termId, checked) }
            .onSuccess { state -> glossaryTermStates = glossaryTermStates + (termId to state) }
            .onFailure { quizMessage = it.message ?: "용어 학습 상태를 저장하지 못했습니다." }
    }

    fun setGlossaryTermBookmarked(termId: String, bookmarked: Boolean) {
        runCatching { userRepository.setGlossaryTermBookmarked(termId, bookmarked) }
            .onSuccess { state -> glossaryTermStates = glossaryTermStates + (termId to state) }
            .onFailure { quizMessage = it.message ?: "용어 북마크를 저장하지 못했습니다." }
    }

    fun setStudyDomain(domainId: String?) {
        studyDomainId = domainId
        if (domainId == null) savedStateHandle.remove<String>(STUDY_DOMAIN_STATE)
        else savedStateHandle[STUDY_DOMAIN_STATE] = domainId
        updateStudyResults()
    }

    fun updateStudyQuery(query: String) {
        studyQuery = query
        if (query.isBlank()) savedStateHandle.remove<String>(STUDY_QUERY_STATE)
        else savedStateHandle[STUDY_QUERY_STATE] = query
        updateStudyResults()
    }

    fun setRecordDomain(domainId: String?) {
        recordDomainId = domainId?.takeIf { candidate -> domains.any { it.id == candidate } }
        recordElementId = null
        if (recordDomainId == null) savedStateHandle.remove<String>("recordDomainId")
        else savedStateHandle["recordDomainId"] = recordDomainId
        savedStateHandle.remove<String>("recordElementId")
        refreshRecordData()
    }

    fun setRecordElement(elementId: String?) {
        recordElementId = elementId?.takeIf { candidate ->
            allElements.any { element ->
                element.id == candidate && (recordDomainId == null || element.domainId == recordDomainId)
            }
        }
        if (recordElementId == null) savedStateHandle.remove<String>("recordElementId")
        else savedStateHandle["recordElementId"] = recordElementId
        refreshRecordData()
    }

    private fun updateStudyResults() {
        studyResults = runCatching { contentRepository?.elements(studyDomainId, studyQuery).orEmpty() }
            .onFailure { contentError = it.message }
            .getOrDefault(emptyList())
    }

    fun setQuizDomain(domainId: String?) {
        quizDomainId = domainId?.takeIf { candidate -> domains.any { it.id == candidate } }
        if (quizDomainId == null) savedStateHandle.remove<String>(QUIZ_DOMAIN_ID_STATE)
        else savedStateHandle[QUIZ_DOMAIN_ID_STATE] = quizDomainId
    }

    fun toggleQuizDomain(domainId: String) {
        if (domains.none { it.id == domainId }) return
        setQuizDomains(
            if (domainId in quizDomainIds) quizDomainIds - domainId
            else quizDomainIds + domainId,
        )
    }

    fun selectAllQuizDomains() = setQuizDomains(domains.mapTo(linkedSetOf()) { it.id })

    fun clearQuizDomains() = setQuizDomains(emptySet())

    private fun setQuizDomains(domainIds: Set<String>) {
        quizDomainIds = domains.asSequence()
            .map { it.id }
            .filter { it in domainIds }
            .toCollection(linkedSetOf())
        persistQuizDomainSelection()
    }

    private fun persistQuizDomainSelection() {
        savedStateHandle[QUIZ_DOMAIN_IDS_STATE] = ArrayList(quizDomainIds)
    }

    fun updateQuizDifficulty(difficulty: Int) { quizDifficulty = difficulty.coerceIn(1, 3) }
    fun updateQuizCount(count: Int) { quizCount = count.coerceIn(1, 20) }
    fun setQuizTrack(track: QuizTrack) {
        selectedTrack = track
        savedStateHandle[QUIZ_TRACK_STATE] = track.name
    }
    fun clearQuizMessage() { quizMessage = null }

    val configuredQuizSelectionError: String?
        get() = when {
            selectedTrack != QuizTrack.DOMAIN -> null
            quizDomainIds.isEmpty() -> "분야별 학습은 분야를 1개 이상 선택해야 합니다."
            allElements.none { it.domainId in quizDomainIds } -> "선택한 분야에 출제할 학습요소가 없습니다."
            else -> null
        }

    fun startConfiguredQuiz() {
        configuredQuizSelectionError?.let { message ->
            quizMessage = message
            return
        }
        startQuiz(
            track = selectedTrack,
            domainIds = quizDomainFilter(selectedTrack, quizDomainIds, quizDomainId),
            count = quizCount,
            difficulty = quizDifficulty,
        )
    }

    fun startElementQuiz(elementId: String) {
        val element = allElements.firstOrNull { it.id == elementId } ?: return
        startQuiz(
            track = QuizTrack.DOMAIN,
            domainIds = setOf(element.domainId),
            count = 5,
            difficulty = quizDifficulty,
            explicitElementIds = listOf(elementId),
        )
    }

    fun startWeakQuiz() = startQuiz(
        QuizTrack.WEAK,
        quizDomainId?.let(::setOf),
        quizCount,
        quizDifficulty,
    )

    fun startRecordWeakQuiz() {
        if (recordUnresolvedWrongCount <= 0) {
            quizMessage = "선택한 조회 범위에 남은 오답이 없습니다."
            return
        }
        val elementId = recordElementId
        val domainId = recordDomainId
            ?: elementId?.let { selectedId -> allElements.firstOrNull { it.id == selectedId }?.domainId }
        startQuiz(
            track = QuizTrack.WEAK,
            domainIds = domainId?.let(::setOf),
            count = quizCount,
            difficulty = quizDifficulty,
            explicitElementIds = elementId?.let { listOf(it) },
        )
    }

    fun startBookmarkReview(bookmark: BookmarkRecord, freshNumbers: Boolean = false) {
        val element = allElements.firstOrNull { it.id == bookmark.elementId } ?: return
        val presentation = bookmark.presentation()
        val question = if (!freshNumbers) {
            runCatching { parseBookmarkedQuestion(bookmark.snapshotJson) }.getOrNull()
        } else {
            val seed = System.currentTimeMillis()
            if (bookmark.mode == QuizMode.CALCULATION.name) {
                QuizEngine.generateCalculation(element.id, seed, quizDifficulty)
            } else {
                generateConceptQuestion(element, seed, quizDifficulty)
            }
        }
        if (question == null) {
            quizMessage = "이 문제 유형을 현재 콘텐츠 버전에서 재생할 수 없습니다."
            return
        }
        pushCurrentRoute()
        quizSession = QuizSessionState(
            track = QuizTrack.BOOKMARK,
            questions = listOf(question),
            presentations = listOf(presentation),
        )
        currentTab = MainTab.QUIZ
        savedStateHandle["tab"] = MainTab.QUIZ.name
        persistQuizSession()
    }

    private fun startQuiz(
        track: QuizTrack,
        domainIds: Set<String>?,
        count: Int,
        difficulty: Int,
        explicitElementIds: List<String>? = null,
    ) {
        quizMessage = null
        val sessionCount = count.coerceIn(1, 20)
        val availableDomainIds = domains.mapTo(hashSetOf()) { it.id }
        val normalizedDomainIds = domainIds?.intersect(availableDomainIds)
        if (domainIds != null && normalizedDomainIds.isNullOrEmpty()) {
            quizMessage = "선택한 분야에 출제할 학습요소가 없습니다."
            return
        }
        fun ContentElement.inSelectedDomains(): Boolean =
            normalizedDomainIds == null || domainId in normalizedDomainIds

        if (track == QuizTrack.BOOKMARK) {
            val replayCandidates = bookmarks.asSequence()
                .filter { saved -> allElements.firstOrNull { it.id == saved.elementId }?.inSelectedDomains() == true }
                .mapNotNull { saved ->
                    runCatching { parseBookmarkedQuestion(saved.snapshotJson) to saved.presentation() }.getOrNull()
                }
                .toList()
            if (replayCandidates.isEmpty()) {
                quizMessage = "재생할 수 있는 북마크 snapshot이 없습니다."
                return
            }
            val maxPerElement = floor(sessionCount * 0.25).toInt().coerceAtLeast(1)
            val selected = mutableListOf<Pair<QuizQuestion, QuizPresentation>>()
            val elementCounts = mutableMapOf<String, Int>()
            replayCandidates.forEach { candidate ->
                if (selected.size >= sessionCount) return@forEach
                val elementId = candidate.first.elementId
                val used = elementCounts[elementId] ?: 0
                if (used < maxPerElement) {
                    selected += candidate
                    elementCounts[elementId] = used + 1
                }
            }
            if (selected.size < sessionCount) {
                quizMessage = "북마크가 요소별 25% 제한을 만족하기에 부족합니다. 개별 북마크 복습을 사용하세요."
                return
            }
            pushCurrentRoute()
            quizSession = QuizSessionState(
                track = track,
                questions = selected.map { it.first },
                presentations = selected.map { it.second },
            )
            currentTab = MainTab.QUIZ
            savedStateHandle["tab"] = MainTab.QUIZ.name
            persistQuizSession()
            return
        }
        val explicitElementSet = explicitElementIds?.toSet()
        val unresolvedWrong = if (track == QuizTrack.WEAK) {
            userRepository.unresolvedWrong().filter { entry ->
                (allElements.firstOrNull { it.id == entry.elementId }?.inSelectedDomains() == true) &&
                    (explicitElementSet == null || entry.elementId in explicitElementSet)
            }
        } else emptyList()
        val weakTargets = unresolvedWrong.groupBy { it.elementId }.mapValues { (_, entries) ->
            entries.mapNotNull { entry ->
                val mode = runCatching { QuizMode.valueOf(entry.mode) }.getOrNull() ?: return@mapNotNull null
                val presentation = runCatching { QuizPresentation.valueOf(entry.presentation) }
                    .getOrDefault(QuizPresentation.STANDARD)
                WeakTemplateTarget(mode, presentation, entry.lastSeed, entry.templateId)
            }.distinctBy { it.templateId }
        }
        val baseSeed = System.currentTimeMillis() and Long.MAX_VALUE
        val basePool = when {
            explicitElementIds != null -> explicitElementIds.mapNotNull { id -> allElements.firstOrNull { it.id == id } }
            track == QuizTrack.WEAK -> unresolvedWrong.mapNotNull { entry -> allElements.firstOrNull { it.id == entry.elementId } }
            track == QuizTrack.CASE -> CASE_ELEMENT_IDS.mapNotNull { id -> allElements.firstOrNull { it.id == id } }
            track == QuizTrack.DOMAIN && normalizedDomainIds != null -> {
                val elementsById = allElements.associateBy { it.id }
                QuizEngine.balancedDomainElementIds(
                    candidates = allElements.map { it.seed() },
                    selectedDomainIds = normalizedDomainIds,
                    seed = baseSeed,
                ).mapNotNull(elementsById::get)
            }
            normalizedDomainIds != null -> allElements.filter { it.domainId in normalizedDomainIds }
            else -> allElements
        }.filter { candidate -> candidate.inSelectedDomains() }
            .distinctBy { it.id }
            .toMutableList()

        if (basePool.isEmpty() && track == QuizTrack.WEAK) {
            quizMessage = "아직 남은 오답이 없어 전체 요소로 시작합니다."
            basePool += allElements.filter { it.inSelectedDomains() }
        }
        if (basePool.isEmpty()) {
            quizMessage = if (track == QuizTrack.BOOKMARK) "저장된 북마크가 없습니다." else "출제할 요소가 없습니다."
            return
        }

        val maxPerElement = floor(sessionCount * 0.25).toInt().coerceAtLeast(1)
        val requiredUnique = ceil(sessionCount / maxPerElement.toDouble()).toInt()
        if (explicitElementIds == null && basePool.size < requiredUnique) {
            allElements.asSequence()
                .filter { candidate -> candidate.inSelectedDomains() }
                .filterNot { candidate -> basePool.any { it.id == candidate.id } }
                .take(requiredUnique - basePool.size)
                .forEach(basePool::add)
        }
        if (explicitElementIds == null && sessionCount >= 4 && basePool.size < requiredUnique) {
            quizMessage = "한 요소가 세션의 25%를 넘지 않게 구성할 수 없습니다."
            return
        }

        val random = Random(baseSeed)
        val ordered = if (track == QuizTrack.WEAK) {
            basePool.sortedWith(
                compareBy<ContentElement> { element ->
                    val item = progress[element.id]
                    if (item == null || item.attempts == 0) 1.0 else item.correct.toDouble() / item.attempts
                }.thenBy { progress[it.id]?.lastAttemptAt ?: 0L }
            )
        } else if (track == QuizTrack.DOMAIN && normalizedDomainIds != null) {
            basePool
        } else {
            basePool.shuffled(random)
        }
        val allSeeds = allElements.map { it.seed() }
        val elementOccurrences = mutableMapOf<String, Int>()
        val presentations = mutableListOf<QuizPresentation>()
        val questions = buildList {
            repeat(sessionCount) { index ->
                val element = ordered[index % ordered.size]
                val occurrence = elementOccurrences[element.id] ?: 0
                elementOccurrences[element.id] = occurrence + 1
                val weakTarget = weakTargets[element.id]
                    ?.takeIf { it.isNotEmpty() }
                    ?.let { targets -> targets[occurrence % targets.size] }
                val itemSeed = weakTarget?.seed?.plus(occurrence * 104_729L)
                    ?: (baseSeed + index * 104_729L + element.id.hashCode().toLong())
                val itemDifficulty = if (track == QuizTrack.SPRINT) (index % 3) + 1 else difficulty
                val wantsCalculation = when {
                    weakTarget != null -> weakTarget.mode == QuizMode.CALCULATION
                    track == QuizTrack.CONCEPT || track == QuizTrack.ORAL -> false
                    track == QuizTrack.SPRINT || track == QuizTrack.CASE -> index % 2 == 0
                    else -> index % 3 == 1
                }
                val generated = if (wantsCalculation && element.id in QuizEngine.calculationElementIds) {
                    QuizEngine.generateCalculation(element.id, itemSeed, itemDifficulty)
                } else null
                val question = generated ?: generateConceptQuestion(
                    element,
                    itemSeed,
                    itemDifficulty,
                    allSeeds,
                )
                add(question)
                presentations += weakTarget?.presentation ?: track.presentation()
            }
        }
        pushCurrentRoute()
        quizSession = QuizSessionState(track, questions, presentations)
        currentTab = MainTab.QUIZ
        savedStateHandle["tab"] = MainTab.QUIZ.name
        persistQuizSession()
    }

    fun setQuizAnswer(answer: String) {
        val session = quizSession ?: return
        if (!session.submitted && !session.finished) {
            quizSession = session.copy(userAnswer = answer)
            persistQuizSession()
        }
    }

    fun submitQuizAnswer(selfAssessment: Boolean? = null) {
        val session = quizSession ?: return
        val question = session.currentQuestion ?: return
        if (session.submitted || session.userAnswer.isBlank() && selfAssessment == null) return
        val correct = selfAssessment ?: QuizEngine.grade(question, session.userAnswer).isCorrect
        val recordedAnswer = when (selfAssessment) {
            true -> "self_assessed_correct"
            false -> "self_assessed_review"
            null -> session.userAnswer
        }
        val presentation = session.currentPresentation
        val templateId = question.templateId(presentation)
        runCatching { userRepository.recordAttempt(
            AttemptInput(
                instanceId = question.instanceId,
                elementId = question.elementId,
                templateId = templateId,
                mode = question.mode.name,
                presentation = presentation.name,
                seed = question.snapshot.generationSeed,
                prompt = question.prompt,
                canonicalAnswer = question.answer.canonicalValue,
                userAnswer = recordedAnswer,
                correct = correct,
                explanation = question.explanationList(),
                elapsedMs = System.currentTimeMillis() - session.questionStartedAt,
            )
        ) }.onFailure {
            quizMessage = it.message ?: "답변 기록을 저장하지 못했습니다."
            return
        }
        var bookmarkSetChanged = false
        if (!correct && autoBookmarkWrong && !userRepository.isBookmarked(question.instanceId)) {
            runCatching {
                userRepository.toggleBookmark(
                    question.bookmarkInput(presentation, BookmarkOrigin.AUTO_WRONG)
                )
            }.onSuccess { bookmarkSetChanged = it }
        }
        quizSession = session.copy(
            submitted = true,
            wasCorrect = correct,
            correctCount = session.correctCount + if (correct) 1 else 0,
        )
        refreshUserData(refreshAllBookmarks = bookmarkSetChanged)
        persistQuizSession()
    }

    fun nextQuestion() {
        val session = quizSession ?: return
        if (!session.submitted) return
        if (session.currentIndex >= session.questions.lastIndex) {
            quizSession = session.copy(finished = true)
        } else {
            quizSession = session.copy(
                currentIndex = session.currentIndex + 1,
                userAnswer = "",
                submitted = false,
                wasCorrect = null,
                questionStartedAt = System.currentTimeMillis(),
            )
        }
        persistQuizSession()
    }

    fun leaveQuiz() {
        clearQuizSession()
        navigateBack()
    }

    fun leaveQuizTo(tab: MainTab) {
        clearQuizSession()
        val targetRoute = tab.routeKey()
        navigationHistory = navigationHistoryAfterQuizExitTo(navigationHistory, tab)
        persistNavigationHistory()
        applyRoute(targetRoute)
    }

    private fun clearQuizSession() {
        quizSession = null
        savedStateHandle.remove<String>("quizSession")
    }

    fun toggleCurrentBookmark() {
        val session = quizSession ?: return
        val question = session.currentQuestion ?: return
        runCatching { userRepository.toggleBookmark(question.bookmarkInput(session.currentPresentation)) }
            .onSuccess { refreshUserData() }
            .onFailure { quizMessage = it.message ?: "북마크를 저장하지 못했습니다." }
    }

    fun currentQuestionBookmarked(): Boolean = quizSession?.currentQuestion?.let {
        userRepository.isBookmarked(it.instanceId)
    } ?: false

    fun updateAutoBookmarkWrong(enabled: Boolean) {
        autoBookmarkWrong = enabled
        userRepository.setSetting("auto_bookmark_wrong", enabled.toString())
    }

    fun clearLearningData() {
        userRepository.clearLearningData()
        quizSession = null
        savedStateHandle.remove<String>("quizSession")
        refreshUserData()
    }

    fun confirmWrongResolved(elementId: String, templateId: String) {
        userRepository.confirmWrongResolved(elementId, templateId)
        refreshUserData(refreshAllBookmarks = false)
    }

    fun resolutionSuggested(elementId: String, templateId: String): Boolean =
        "$elementId|$templateId" in resolutionSuggestions

    fun exportBackup(resolver: ContentResolver, uri: Uri) {
        resolver.openOutputStream(uri, "wt")?.use(userRepository::exportBackup)
            ?: error("백업 파일을 열 수 없습니다.")
    }

    fun importBackup(resolver: ContentResolver, uri: Uri) {
        resolver.openInputStream(uri)?.use(userRepository::importBackup)
            ?: error("백업 파일을 열 수 없습니다.")
    }

    fun reloadUserData() {
        refreshUserData()
        refreshGlossaryTermStates()
        refreshConceptNotes()
        refreshTextAnnotations()
    }

    private fun refreshConceptNotes() {
        val elementId = selectedElement?.id
        if (elementId == null) {
            conceptNotes = emptyList()
            conceptNoteError = null
            return
        }
        runCatching { userRepository.conceptNotes(elementId) }
            .onSuccess {
                conceptNotes = it
                conceptNoteError = null
            }
            .onFailure {
                conceptNotes = emptyList()
                conceptNoteError = it.message ?: "개인 메모를 불러오지 못했습니다."
            }
    }

    private fun refreshTextAnnotations() {
        val elementId = selectedElement?.id
        if (elementId == null) {
            textAnnotations = emptyList()
            textAnnotationError = null
            return
        }
        runCatching { userRepository.textAnnotations(elementId) }
            .onSuccess {
                textAnnotations = it
                textAnnotationError = null
            }
            .onFailure {
                textAnnotations = emptyList()
                textAnnotationError = it.message ?: "텍스트 표시를 불러오지 못했습니다."
            }
    }

    private fun refreshGlossaryTermStates() {
        runCatching { userRepository.glossaryTermStates() }
            .onSuccess { states -> glossaryTermStates = states.associateBy { it.termId } }
            .onFailure { glossaryTermStates = emptyMap() }
    }

    private fun refreshUserData(refreshAllBookmarks: Boolean = true) {
        stats = userRepository.stats()
        progress = userRepository.allProgress()
        if (refreshAllBookmarks) bookmarks = userRepository.bookmarks()
        refreshRecordData()
        resolutionSuggestions = userRepository.resolutionSuggestions()
        autoBookmarkWrong = userRepository.setting("auto_bookmark_wrong", "false").toBoolean()
    }

    private fun refreshRecordData() {
        val elementIds = when {
            recordElementId != null -> listOf(recordElementId!!)
            recordDomainId != null -> allElements.filter { it.domainId == recordDomainId }.map { it.id }
            else -> null
        }
        recentWrong = if (elementIds == null) {
            userRepository.recentWrong()
        } else {
            userRepository.recentWrongForElements(elementIds)
        }
        recordBookmarks = userRepository.recentBookmarks(elementIds)
        val elementIdSet = elementIds?.toSet()
        recordUnresolvedWrongCount = userRepository.unresolvedWrong().count { entry ->
            elementIdSet == null || entry.elementId in elementIdSet
        }
    }

    override fun onCleared() {
        contentRepository?.close()
        userRepository.close()
        super.onCleared()
    }

    private fun generateConceptQuestion(
        element: ContentElement,
        seed: Long,
        difficulty: Int,
        fallbackPool: List<ElementSeed> = allElements.map { it.seed() },
    ): QuizQuestion {
        val allCurated = conceptQuestionsByElement[element.id].orEmpty()
        val difficultyMatched = allCurated.filter { it.difficulty <= difficulty }
        val candidates = (difficultyMatched.ifEmpty { allCurated }).sortedBy { it.questionId }
        if (candidates.isNotEmpty()) {
            val index = ((seed and Long.MAX_VALUE) % candidates.size).toInt()
            return QuizEngine.generateConceptFromBank(candidates[index], seed)
        }
        return QuizEngine.generateConcept(element.seed(), fallbackPool, seed, difficulty)
    }

    private fun ContentElement.seed() = ElementSeed(id, title, domainId, coreRelation)

    private fun BookmarkRecord.presentation(): QuizPresentation {
        val stored = runCatching {
            QuizPresentation.valueOf(JSONObject(snapshotJson).optString("presentation"))
        }.getOrNull()
        if (stored != null) return stored
        val quizMode = runCatching { QuizMode.valueOf(mode) }.getOrDefault(QuizMode.CONCEPT)
        return QuizTemplateIdentity.normalizeLegacy(elementId, quizMode, templateId).presentation
    }

    private fun QuizQuestion.templateId(presentation: QuizPresentation): String =
        QuizTemplateIdentity.id(elementId, mode, snapshot.rendererVersion, presentation)

    private fun QuizQuestion.explanationList(): List<String> = listOf(
        "관련 개념: ${explanationSteps.concept}",
        "수식: ${explanationSteps.formula}",
        "숫자 대입: ${explanationSteps.substitution}",
        "정답: ${explanationSteps.answer}",
        "해석: ${explanationSteps.interpretation}",
    )

    private fun QuizQuestion.bookmarkInput(
        presentation: QuizPresentation,
        origin: BookmarkOrigin = BookmarkOrigin.MANUAL,
    ): BookmarkInput = BookmarkInput(
        instanceId = instanceId,
        elementId = elementId,
        templateId = templateId(presentation),
        mode = mode.name,
        seed = snapshot.generationSeed,
        origin = origin,
        snapshotJson = JSONObject().apply {
            put("instanceId", instanceId)
            put("elementId", elementId)
            put("mode", mode.name)
            put("presentation", presentation.name)
            put("prompt", prompt)
            put("answer", JSONObject().apply {
                put("kind", answer.kind.name)
                put("canonicalValue", answer.canonicalValue)
                put("unit", answer.unit)
                put("correctChoiceId", answer.correctChoiceId ?: JSONObject.NULL)
            })
            put("choices", JSONArray().apply {
                choices.orEmpty().forEach { choice ->
                    put(JSONObject().apply {
                        put("id", choice.id)
                        put("text", choice.text)
                        put("sourceElementId", choice.sourceElementId ?: JSONObject.NULL)
                    })
                }
            })
            put("explanation", JSONObject().apply {
                put("concept", explanationSteps.concept)
                put("formula", explanationSteps.formula)
                put("substitution", explanationSteps.substitution)
                put("answer", explanationSteps.answer)
                put("interpretation", explanationSteps.interpretation)
            })
            put("audit", JSONObject().apply {
                put("operations", JSONArray().apply {
                    audit.operations.forEach { operation ->
                        put(JSONObject().apply {
                            put("expression", operation.expression)
                            put("result", operation.result)
                            put("exact", operation.exact)
                        })
                    }
                })
                put("maxAbsoluteIntermediate", audit.maxAbsoluteIntermediate)
                put("maxAllowedAbsoluteIntermediate", audit.maxAllowedAbsoluteIntermediate)
                put("operationCount", audit.operationCount)
                put("maxAllowedOperations", audit.maxAllowedOperations)
                put("allIntermediatesAreIntegers", audit.allIntermediatesAreIntegers)
                put("withinDifficultyCap", audit.withinDifficultyCap)
                put("passed", audit.passed)
            })
            put("snapshot", JSONObject().apply {
                put("id", snapshot.id)
                put("version", snapshot.version)
                put("rendererVersion", snapshot.rendererVersion)
                put("generationSeed", snapshot.generationSeed)
                put("difficulty", snapshot.difficulty)
                put("canonicalPayload", snapshot.canonicalPayload)
            })
        }.toString(),
    )

    private fun persistQuizSession() {
        val session = quizSession ?: run {
            savedStateHandle.remove<String>("quizSession")
            return
        }
        savedStateHandle["quizSession"] = JSONObject().apply {
            put("track", session.track.name)
            put("currentIndex", session.currentIndex)
            put("userAnswer", session.userAnswer)
            put("submitted", session.submitted)
            put("wasCorrect", session.wasCorrect ?: JSONObject.NULL)
            put("correctCount", session.correctCount)
            put("questionStartedAt", session.questionStartedAt)
            put("finished", session.finished)
            put("questions", JSONArray().apply {
                session.questions.forEachIndexed { index, question ->
                    val presentation = session.presentations.getOrElse(index) { session.track.presentation() }
                    put(JSONObject(question.bookmarkInput(presentation).snapshotJson))
                }
            })
        }.toString()
    }

    private fun restoreQuizSession(json: String): QuizSessionState {
        val root = JSONObject(json)
        val questionArray = root.getJSONArray("questions")
        val questionSnapshots = List(questionArray.length()) { index -> questionArray.getJSONObject(index) }
        val questions = questionSnapshots.map { parseBookmarkedQuestion(it.toString()) }
        val track = QuizTrack.valueOf(root.getString("track"))
        val presentations = questionSnapshots.map { snapshot ->
            runCatching { QuizPresentation.valueOf(snapshot.optString("presentation")) }
                .getOrDefault(track.presentation())
        }
        require(questions.isNotEmpty()) { "저장된 세션에 문제가 없습니다." }
        val index = root.getInt("currentIndex").coerceIn(0, questions.lastIndex)
        return QuizSessionState(
            track = track,
            questions = questions,
            presentations = presentations,
            currentIndex = index,
            userAnswer = root.getString("userAnswer"),
            submitted = root.getBoolean("submitted"),
            wasCorrect = if (root.isNull("wasCorrect")) null else root.getBoolean("wasCorrect"),
            correctCount = root.getInt("correctCount").coerceIn(0, questions.size),
            questionStartedAt = root.getLong("questionStartedAt"),
            finished = root.getBoolean("finished"),
        )
    }

    private fun parseBookmarkedQuestion(json: String): QuizQuestion {
        val root = JSONObject(json)
        val mode = QuizMode.valueOf(root.getString("mode"))
        val answerJson = root.getJSONObject("answer")
        val answer = QuizAnswer(
            kind = QuizAnswerKind.valueOf(answerJson.getString("kind")),
            canonicalValue = answerJson.getString("canonicalValue"),
            unit = answerJson.getString("unit"),
            correctChoiceId = answerJson.optString("correctChoiceId").takeIf { it.isNotBlank() },
        )
        val choicesJson = root.getJSONArray("choices")
        val choices = if (mode == QuizMode.CONCEPT) List(choicesJson.length()) { index ->
            val item = choicesJson.getJSONObject(index)
            QuizChoice(
                id = item.getString("id"),
                text = item.getString("text"),
                sourceElementId = item.optString("sourceElementId").takeIf { it.isNotBlank() },
            )
        } else null
        val explanationJson = root.getJSONObject("explanation")
        val explanation = ExplanationSteps(
            concept = explanationJson.getString("concept"),
            formula = explanationJson.getString("formula"),
            substitution = explanationJson.getString("substitution"),
            answer = explanationJson.getString("answer"),
            interpretation = explanationJson.getString("interpretation"),
        )
        val auditJson = root.getJSONObject("audit")
        val operationsJson = auditJson.getJSONArray("operations")
        val audit = MentalMathAudit(
            operations = List(operationsJson.length()) { index ->
                val item = operationsJson.getJSONObject(index)
                MentalMathOperation(item.getString("expression"), item.getLong("result"), item.getBoolean("exact"))
            },
            maxAbsoluteIntermediate = auditJson.getLong("maxAbsoluteIntermediate"),
            maxAllowedAbsoluteIntermediate = auditJson.getLong("maxAllowedAbsoluteIntermediate"),
            operationCount = auditJson.getInt("operationCount"),
            maxAllowedOperations = auditJson.getInt("maxAllowedOperations"),
            allIntermediatesAreIntegers = auditJson.getBoolean("allIntermediatesAreIntegers"),
            withinDifficultyCap = auditJson.getBoolean("withinDifficultyCap"),
            passed = auditJson.getBoolean("passed"),
        )
        val snapshotJson = root.getJSONObject("snapshot")
        val snapshot = QuestionSnapshot(
            id = snapshotJson.getString("id"),
            version = snapshotJson.getInt("version"),
            rendererVersion = snapshotJson.getString("rendererVersion"),
            generationSeed = snapshotJson.getLong("generationSeed"),
            difficulty = snapshotJson.getInt("difficulty"),
            canonicalPayload = snapshotJson.getString("canonicalPayload"),
        )
        return QuizQuestion(
            instanceId = root.getString("instanceId"),
            elementId = root.getString("elementId"),
            mode = mode,
            prompt = root.getString("prompt"),
            choices = choices,
            canonicalAnswer = answer.canonicalValue,
            answerUnit = answer.unit,
            answer = answer,
            explanationSteps = explanation,
            audit = audit,
            snapshot = snapshot,
        )
    }

    companion object {
        private val CASE_ELEMENT_IDS = listOf(
            "EQV-41", "EQV-45", "EQV-49", "EQV-53", "EQV-54",
            "IBT-05", "IBT-06", "IBT-07", "IBT-09", "IBT-12", "IBT-13", "IBT-15",
        )
    }
}

private fun QuizTrack.presentation(): QuizPresentation =
    if (this == QuizTrack.ORAL) QuizPresentation.ORAL else QuizPresentation.STANDARD
