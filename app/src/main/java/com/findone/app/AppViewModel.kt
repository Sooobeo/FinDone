package com.findone.app

import android.app.Application
import android.content.ContentResolver
import android.net.Uri
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.SavedStateHandle
import com.findone.app.data.AttemptInput
import com.findone.app.data.BookmarkInput
import com.findone.app.data.BookmarkRecord
import com.findone.app.data.ContentRepository
import com.findone.app.data.ElementProgress
import com.findone.app.data.StudyStats
import com.findone.app.data.UserRepository
import com.findone.app.model.ContentElement
import com.findone.app.model.ContentManifest
import com.findone.app.model.Domain
import com.findone.app.quiz.ElementSeed
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
import kotlin.math.ceil
import kotlin.math.floor

enum class MainTab { HOME, STUDY, QUIZ, RECORDS }

enum class QuizTrack(val title: String, val description: String) {
    DOMAIN("분야별 학습", "선택한 분야의 요소를 고르게 섞습니다."),
    WEAK("약점 집중", "최근 오답이 남은 요소부터 다시 풉니다."),
    SPRINT("면접 스프린트", "30·60·90초 개념·암산 문제를 섞습니다."),
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
    private val contentRepository: ContentRepository?

    val domains: List<Domain>
    val allElements: List<ContentElement>
    val contentManifest: ContentManifest?

    var contentError by mutableStateOf<String?>(null)
        private set
    var currentTab by mutableStateOf(
        runCatching { MainTab.valueOf(savedStateHandle["tab"] ?: MainTab.HOME.name) }.getOrDefault(MainTab.HOME)
    )
        private set
    var selectedElementId by mutableStateOf(savedStateHandle.get<String>("elementId"))
        private set
    var studyDomainId by mutableStateOf<String?>(null)
        private set
    var studyQuery by mutableStateOf("")
        private set
    var studyResults by mutableStateOf<List<ContentElement>>(emptyList())
        private set
    var quizDomainId by mutableStateOf<String?>(null)
        private set
    var quizDifficulty by mutableStateOf(1)
        private set
    var quizCount by mutableStateOf(10)
        private set
    var selectedTrack by mutableStateOf(QuizTrack.DOMAIN)
        private set
    var quizSession by mutableStateOf<QuizSessionState?>(null)
        private set
    var quizMessage by mutableStateOf<String?>(null)
        private set
    var stats by mutableStateOf(StudyStats())
        private set
    var progress by mutableStateOf<Map<String, ElementProgress>>(emptyMap())
        private set
    var bookmarks by mutableStateOf<List<BookmarkRecord>>(emptyList())
        private set
    var recentWrong by mutableStateOf(userRepository.recentWrong())
        private set
    var resolutionSuggestions by mutableStateOf<Set<String>>(emptySet())
        private set
    var autoBookmarkWrong by mutableStateOf(userRepository.setting("auto_bookmark_wrong", "false").toBoolean())
        private set

    init {
        var repository: ContentRepository? = null
        var loadedDomains = emptyList<Domain>()
        var loadedElements = emptyList<ContentElement>()
        var loadedManifest: ContentManifest? = null
        runCatching {
            ContentRepository(application).also { repo ->
                repository = repo
                loadedDomains = repo.domains()
                loadedElements = repo.elements()
                loadedManifest = repo.manifest
            }
        }.onFailure { contentError = it.message ?: "콘텐츠 DB를 열지 못했습니다." }
        contentRepository = repository
        domains = loadedDomains
        allElements = loadedElements
        contentManifest = loadedManifest
        studyResults = loadedElements
        refreshUserData()
        savedStateHandle.get<String>("quizSession")?.let { saved ->
            runCatching { restoreQuizSession(saved) }
                .onSuccess { quizSession = it }
                .onFailure { savedStateHandle.remove<String>("quizSession") }
        }
    }

    val selectedElement: ContentElement?
        get() = selectedElementId?.let { id -> allElements.firstOrNull { it.id == id } }

    fun selectTab(tab: MainTab) {
        currentTab = tab
        savedStateHandle["tab"] = tab.name
        if (tab != MainTab.STUDY) closeElement()
    }

    fun openElement(elementId: String) {
        selectedElementId = elementId
        savedStateHandle["elementId"] = elementId
        currentTab = MainTab.STUDY
        savedStateHandle["tab"] = MainTab.STUDY.name
    }

    fun closeElement() {
        selectedElementId = null
        savedStateHandle.remove<String>("elementId")
    }

    fun setStudyDomain(domainId: String?) {
        studyDomainId = domainId
        updateStudyResults()
    }

    fun updateStudyQuery(query: String) {
        studyQuery = query
        updateStudyResults()
    }

    private fun updateStudyResults() {
        studyResults = runCatching { contentRepository?.elements(studyDomainId, studyQuery).orEmpty() }
            .onFailure { contentError = it.message }
            .getOrDefault(emptyList())
    }

    fun setQuizDomain(domainId: String?) { quizDomainId = domainId }
    fun updateQuizDifficulty(difficulty: Int) { quizDifficulty = difficulty.coerceIn(1, 3) }
    fun updateQuizCount(count: Int) { quizCount = count.coerceIn(1, 20) }
    fun setQuizTrack(track: QuizTrack) { selectedTrack = track }
    fun clearQuizMessage() { quizMessage = null }

    fun startConfiguredQuiz() = startQuiz(selectedTrack, quizDomainId, quizCount, quizDifficulty)

    fun startElementQuiz(elementId: String) {
        val element = allElements.firstOrNull { it.id == elementId } ?: return
        startQuiz(
            track = QuizTrack.DOMAIN,
            domainId = element.domainId,
            count = 5,
            difficulty = quizDifficulty,
            explicitElementIds = listOf(elementId),
        )
    }

    fun startWeakQuiz() = startQuiz(QuizTrack.WEAK, quizDomainId, quizCount, quizDifficulty)

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
                QuizEngine.generateConcept(element.seed(), allElements.map { it.seed() }, seed, quizDifficulty)
            }
        }
        if (question == null) {
            quizMessage = "이 문제 유형을 현재 콘텐츠 버전에서 재생할 수 없습니다."
            return
        }
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
        domainId: String?,
        count: Int,
        difficulty: Int,
        explicitElementIds: List<String>? = null,
    ) {
        quizMessage = null
        val sessionCount = count.coerceIn(1, 20)
        if (track == QuizTrack.BOOKMARK) {
            val replayCandidates = bookmarks.asSequence()
                .filter { saved -> domainId == null || allElements.firstOrNull { it.id == saved.elementId }?.domainId == domainId }
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
        val unresolvedWrong = if (track == QuizTrack.WEAK) {
            userRepository.unresolvedWrong().filter { entry ->
                domainId == null || allElements.firstOrNull { it.id == entry.elementId }?.domainId == domainId
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
        val basePool = when {
            explicitElementIds != null -> explicitElementIds.mapNotNull { id -> allElements.firstOrNull { it.id == id } }
            track == QuizTrack.WEAK -> unresolvedWrong.mapNotNull { entry -> allElements.firstOrNull { it.id == entry.elementId } }
            track == QuizTrack.CASE -> CASE_ELEMENT_IDS.mapNotNull { id -> allElements.firstOrNull { it.id == id } }
            domainId != null -> allElements.filter { it.domainId == domainId }
            else -> allElements
        }.filter { candidate -> domainId == null || candidate.domainId == domainId }
            .distinctBy { it.id }
            .toMutableList()

        if (basePool.isEmpty() && track == QuizTrack.WEAK) {
            quizMessage = "아직 남은 오답이 없어 전체 요소로 시작합니다."
            basePool += allElements.filter { domainId == null || it.domainId == domainId }
        }
        if (basePool.isEmpty()) {
            quizMessage = if (track == QuizTrack.BOOKMARK) "저장된 북마크가 없습니다." else "출제할 요소가 없습니다."
            return
        }

        val maxPerElement = floor(sessionCount * 0.25).toInt().coerceAtLeast(1)
        val requiredUnique = ceil(sessionCount / maxPerElement.toDouble()).toInt()
        if (basePool.size < requiredUnique) {
            allElements.asSequence()
                .filter { candidate -> domainId == null || candidate.domainId == domainId }
                .filterNot { candidate -> basePool.any { it.id == candidate.id } }
                .take(requiredUnique - basePool.size)
                .forEach(basePool::add)
        }
        if (sessionCount >= 4 && basePool.size < requiredUnique) {
            quizMessage = "한 요소가 세션의 25%를 넘지 않게 구성할 수 없습니다."
            return
        }

        val baseSeed = System.currentTimeMillis() and Long.MAX_VALUE
        val random = Random(baseSeed)
        val ordered = if (track == QuizTrack.WEAK) {
            basePool.sortedWith(
                compareBy<ContentElement> { element ->
                    val item = progress[element.id]
                    if (item == null || item.attempts == 0) 1.0 else item.correct.toDouble() / item.attempts
                }.thenBy { progress[it.id]?.lastAttemptAt ?: 0L }
            )
        } else basePool.shuffled(random)
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
                val question = generated ?: QuizEngine.generateConcept(element.seed(), allSeeds, itemSeed, itemDifficulty)
                add(question)
                presentations += weakTarget?.presentation ?: track.presentation()
            }
        }
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
        if (!correct && autoBookmarkWrong && !userRepository.isBookmarked(question.instanceId)) {
            runCatching { userRepository.toggleBookmark(question.bookmarkInput(presentation)) }
        }
        quizSession = session.copy(
            submitted = true,
            wasCorrect = correct,
            correctCount = session.correctCount + if (correct) 1 else 0,
        )
        refreshUserData()
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
        refreshUserData()
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

    fun reloadUserData() = refreshUserData()

    private fun refreshUserData() {
        stats = userRepository.stats()
        progress = userRepository.allProgress()
        bookmarks = userRepository.bookmarks()
        recentWrong = userRepository.recentWrong()
        resolutionSuggestions = userRepository.resolutionSuggestions()
        autoBookmarkWrong = userRepository.setting("auto_bookmark_wrong", "false").toBoolean()
    }

    override fun onCleared() {
        contentRepository?.close()
        userRepository.close()
        super.onCleared()
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

    private fun QuizQuestion.bookmarkInput(presentation: QuizPresentation): BookmarkInput = BookmarkInput(
        instanceId = instanceId,
        elementId = elementId,
        templateId = templateId(presentation),
        mode = mode.name,
        seed = snapshot.generationSeed,
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
