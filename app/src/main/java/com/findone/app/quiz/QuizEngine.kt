package com.findone.app.quiz

/**
 * The minimum content needed by the renderer. It intentionally has no dependency on the
 * application's database or UI models, so all 135 curriculum elements can use the engine.
 */
data class ElementSeed(
    val id: String,
    val title: String,
    val domainName: String,
    val coreRelation: String,
)

enum class QuizMode { CONCEPT, CALCULATION }

enum class QuizAnswerKind { MULTIPLE_CHOICE, INTEGER }

data class QuizChoice(
    val id: String,
    val text: String,
    val sourceElementId: String? = null,
)

data class QuizAnswer(
    val kind: QuizAnswerKind,
    val canonicalValue: String,
    val unit: String = "",
    val correctChoiceId: String? = null,
)

/** Every explanation has the same five sections, including for a concept question. */
data class ExplanationSteps(
    val concept: String,
    val formula: String,
    val substitution: String,
    val answer: String,
    val interpretation: String,
)

/** One deliberately chosen, exact integer step in the mental calculation path. */
data class MentalMathOperation(
    val expression: String,
    val result: Long,
    val exact: Boolean,
)

/**
 * A renderer-side proof that no rounding was used and that the intended mental path stays
 * inside the cap for the requested difficulty.
 */
data class MentalMathAudit(
    val operations: List<MentalMathOperation>,
    val maxAbsoluteIntermediate: Long,
    val maxAllowedAbsoluteIntermediate: Long,
    val operationCount: Int,
    val maxAllowedOperations: Int,
    val allIntermediatesAreIntegers: Boolean,
    val withinDifficultyCap: Boolean,
    val passed: Boolean,
) {
    /** Raw AST/intermediate nodes remain available in [operations]; this is the grouped score. */
    val weightedOperationScore: Int get() = operationCount
    val maxAllowedWeightedOperationScore: Int get() = maxAllowedOperations
    val rawOperationCount: Int get() = operations.size
}

/** Materialized, deterministic representation used for cache keys and regression fixtures. */
data class QuestionSnapshot(
    val id: String,
    val version: Int,
    val rendererVersion: String,
    val generationSeed: Long,
    val difficulty: Int,
    val canonicalPayload: String,
)

data class QuizQuestion(
    val instanceId: String,
    val elementId: String,
    val mode: QuizMode,
    val prompt: String,
    val choices: List<QuizChoice>?,
    val canonicalAnswer: String,
    val answerUnit: String,
    val answer: QuizAnswer,
    val explanationSteps: ExplanationSteps,
    val audit: MentalMathAudit,
    val snapshot: QuestionSnapshot,
) {
    init {
        require(answer.canonicalValue == canonicalAnswer)
        require(answer.unit == answerUnit)
        require((mode == QuizMode.CONCEPT) == (choices != null))
    }

    val snapshotId: String get() = snapshot.id
    val snapshotVersion: Int get() = snapshot.version
}

data class GradeResult(
    val isCorrect: Boolean,
    val normalizedResponse: String?,
    val expectedCanonicalAnswer: String,
    val feedback: String,
)

private data class DifficultyCap(
    val maxAbsoluteIntermediate: Long,
    val maxOperations: Int,
)

private data class CalculationDraft(
    val prompt: String,
    val answer: Long,
    val unit: String,
    val concept: String,
    val formula: String,
    val substitution: String,
    val interpretation: String,
    val operations: List<MentalMathOperation>,
)

private typealias CalculationFactory = (StableRandom, Int) -> CalculationDraft

/**
 * Offline, deterministic quiz renderer. No Android, clock, locale, network, or database API is
 * referenced, which makes output reproducible in JVM tests and on-device.
 */
object QuizEngine {
    const val SNAPSHOT_VERSION: Int = 1
    const val RENDERER_VERSION: String = "quiz-engine-1.1.0"

    private val calculationFactories: Map<String, CalculationFactory> = linkedMapOf(
        "ACC-01" to ::acc01,
        "ACC-04" to ::acc04,
        "ACC-12" to ::acc12,
        "CF-02" to ::cf02,
        "CF-09" to ::cf09,
        "CF-11" to ::cf11,
        "INV-01" to ::inv01,
        "INV-04" to ::inv04,
        "INV-06" to ::inv06,
        "FI-03" to ::fi03,
        "FI-07" to ::fi07,
        "FI-10" to ::fi10,
        "DER-01" to ::der01,
        "DER-04" to ::der04,
        "DER-06" to ::der06,
        "EQV-01" to ::eqv01,
        "EQV-02" to ::eqv02,
        "EQV-15" to ::eqv15,
        "IBT-01" to ::ibt01,
        "IBT-02" to ::ibt02,
        "IBT-03" to ::ibt03,
        "IBT-04" to ::ibt04,
        "IBT-05" to ::ibt05,
        "IBT-06" to ::ibt06,
        "IBT-07" to ::ibt07,
        "IBT-08" to ::ibt08,
        "IBT-09" to ::ibt09,
        "IBT-10" to ::ibt10,
        "IBT-11" to ::ibt11,
        "IBT-12" to ::ibt12,
        "IBT-13" to ::ibt13,
        "IBT-14" to ::ibt14,
        "IBT-15" to ::ibt15,
        "IBT-16" to ::ibt16,
        "IBT-17" to ::ibt17,
        "IBT-18" to ::ibt18,
    )

    /** Stable, sorted view suitable for capability checks and content validation. */
    val calculationElementIds: Set<String>
        get() = calculationFactories.keys.toSortedSet()

    /**
     * Generates a four-choice concept question for any valid [ElementSeed]. The pool can contain
     * all 135 elements; same-domain distractors are preferred at higher difficulty. If a tiny pool
     * is supplied, deterministic misconception placeholders complete the four choices.
     */
    fun generateConcept(
        target: ElementSeed,
        pool: List<ElementSeed>,
        seed: Long,
        difficulty: Int,
    ): QuizQuestion {
        requireDifficulty(difficulty)
        require(target.id.isNotBlank()) { "Element id must not be blank." }
        require(target.title.isNotBlank()) { "Element title must not be blank." }
        require(target.domainName.isNotBlank()) { "Domain name must not be blank." }
        require(target.coreRelation.isNotBlank()) { "Core relation must not be blank." }

        val random = StableRandom(mixedSeed(seed, target.id, difficulty, QuizMode.CONCEPT))
        val promptFrames = listOf(
            "다음 핵심 관계에 해당하는 학습요소는 무엇인가?\n${target.coreRelation}",
            "${target.domainName} 분야에서 다음 관계와 직접 연결되는 항목을 고르세요.\n${target.coreRelation}",
            "다음 설명을 가장 정확하게 대표하는 개념은 무엇인가?\n${target.coreRelation}",
            "금융권 실무에서 다음 관계를 설명할 때, 먼저 짚어야 할 학습요소는?\n${target.coreRelation}",
        )
        val prompt = random.pick(promptFrames)

        val candidates = pool.asSequence()
            .filter { it.id != target.id && it.title != target.title }
            .distinctBy { it.id }
            .sortedBy { it.id }
            .toList()
        val sameDomain = random.shuffled(candidates.filter { it.domainName == target.domainName })
        val otherDomain = random.shuffled(candidates.filter { it.domainName != target.domainName })
        val ordered = if (difficulty >= 2) sameDomain + otherDomain else otherDomain + sameDomain
        val selected = mutableListOf<ElementSeed>()
        for (candidate in ordered) {
            if (selected.none { it.title == candidate.title }) selected += candidate
            if (selected.size == 3) break
        }

        data class ChoiceSeed(val text: String, val sourceId: String?, val correct: Boolean)

        val rawChoices = mutableListOf(
            ChoiceSeed(target.title, target.id, true),
        )
        rawChoices += selected.map { ChoiceSeed(it.title, it.id, false) }
        val fallbackLabels = listOf(
            "단순 평균만으로 설명되는 관계",
            "현금의 시점과 무관한 관계",
            "위험과 수익의 방향을 항상 같게 보는 관계",
            "분자와 분모의 기준이 다른 관계",
        )
        var fallbackIndex = 0
        while (rawChoices.size < 4) {
            val label = fallbackLabels[fallbackIndex++]
            if (rawChoices.none { it.text == label }) rawChoices += ChoiceSeed(label, null, false)
        }

        val ids = listOf("A", "B", "C", "D")
        val shuffled = random.shuffled(rawChoices)
        val choices = shuffled.mapIndexed { index, choice ->
            QuizChoice(ids[index], choice.text, choice.sourceId)
        }
        val correctIndex = shuffled.indexOfFirst { it.correct }
        val canonicalAnswer = ids[correctIndex]
        val answer = QuizAnswer(
            kind = QuizAnswerKind.MULTIPLE_CHOICE,
            canonicalValue = canonicalAnswer,
            correctChoiceId = canonicalAnswer,
        )
        val explanation = ExplanationSteps(
            concept = "${target.title}의 정의와 핵심 관계를 식별하는 문제입니다.",
            formula = target.coreRelation,
            substitution = "제시된 관계를 각 선택지의 정의와 직접 대조합니다.",
            answer = "정답은 $canonicalAnswer. ${target.title}입니다.",
            interpretation = "${target.domainName}에서 이 관계는 ${target.coreRelation}로 해석합니다.",
        )
        return materialize(
            elementId = target.id,
            mode = QuizMode.CONCEPT,
            prompt = prompt,
            choices = choices,
            answer = answer,
            explanation = explanation,
            audit = noMathAudit(difficulty),
            seed = seed,
            difficulty = difficulty,
        )
    }

    /** Returns null when an element intentionally has no curated mental-math template. */
    fun generateCalculation(elementId: String, seed: Long, difficulty: Int): QuizQuestion? {
        requireDifficulty(difficulty)
        val factory = calculationFactories[elementId] ?: return null
        val random = StableRandom(mixedSeed(seed, elementId, difficulty, QuizMode.CALCULATION))
        val draft = factory(random, difficulty)
        require(draft.operations.isNotEmpty()) { "A calculation must expose its integer path." }
        require(draft.operations.last().result == draft.answer) {
            "The final audited operation must equal the canonical answer for $elementId."
        }
        val audit = mathAudit(difficulty, draft.operations)
        check(audit.passed) { "Generated question exceeded its mental-math cap for $elementId." }
        val answer = QuizAnswer(
            kind = QuizAnswerKind.INTEGER,
            canonicalValue = draft.answer.toString(),
            unit = draft.unit,
        )
        return materialize(
            elementId = elementId,
            mode = QuizMode.CALCULATION,
            prompt = draft.prompt,
            choices = null,
            answer = answer,
            explanation = ExplanationSteps(
                concept = draft.concept,
                formula = draft.formula,
                substitution = draft.substitution,
                answer = "${commas(draft.answer)} ${draft.unit}".trim(),
                interpretation = draft.interpretation,
            ),
            audit = audit,
            seed = seed,
            difficulty = difficulty,
        )
    }

    fun grade(question: QuizQuestion, response: String): GradeResult = when (question.answer.kind) {
        QuizAnswerKind.MULTIPLE_CHOICE -> gradeMultipleChoice(question, response)
        QuizAnswerKind.INTEGER -> gradeInteger(question, response)
    }

    fun gradeMultipleChoice(question: QuizQuestion, response: String): GradeResult {
        if (question.answer.kind != QuizAnswerKind.MULTIPLE_CHOICE) {
            return wrongKind(question, "이 문항은 객관식이 아닙니다.")
        }
        val trimmed = response.trim()
        val choices = question.choices.orEmpty()
        val byId = choices.firstOrNull { it.id.equals(trimmed, ignoreCase = true) }
        val byNumber = trimmed.toIntOrNull()?.let { number -> choices.getOrNull(number - 1) }
        val byText = choices.firstOrNull { it.text == trimmed }
        val normalized = (byId ?: byNumber ?: byText)?.id
        val correct = normalized == question.canonicalAnswer
        return GradeResult(
            isCorrect = correct,
            normalizedResponse = normalized,
            expectedCanonicalAnswer = question.canonicalAnswer,
            feedback = if (correct) "정답입니다." else "선택지 ID 또는 선택지 문구를 확인하세요.",
        )
    }

    fun gradeInteger(question: QuizQuestion, response: String): GradeResult {
        if (question.answer.kind != QuizAnswerKind.INTEGER) {
            return wrongKind(question, "이 문항은 정수 계산형이 아닙니다.")
        }
        val trimmed = response.trim()
        val numericPart = if (
            question.answerUnit.isNotBlank() &&
            trimmed.endsWith(question.answerUnit, ignoreCase = true)
        ) {
            trimmed.dropLast(question.answerUnit.length).trim()
        } else {
            trimmed
        }
        val normalized = normalizeNumericAnswer(numericPart)
        val correct = normalized == question.canonicalAnswer
        return GradeResult(
            isCorrect = correct,
            normalizedResponse = normalized,
            expectedCanonicalAnswer = question.canonicalAnswer,
            feedback = when {
                normalized == null -> "부호가 있는 정수로 입력하세요. 천 단위 쉼표는 사용할 수 있습니다."
                correct -> "정답입니다."
                else -> "계산 경로와 부호를 다시 확인하세요."
            },
        )
    }

    /** Accepts +1200, -1200, +1,200, -1,200; malformed comma groups and decimals are rejected. */
    fun normalizeNumericAnswer(input: String): String? {
        val value = input.trim().replace('−', '-')
        val plain = Regex("[+-]?\\d+")
        val grouped = Regex("[+-]?\\d{1,3}(,\\d{3})+")
        if (!plain.matches(value) && !grouped.matches(value)) return null
        return value.replace(",", "").toLongOrNull()?.toString()
    }

    private fun wrongKind(question: QuizQuestion, feedback: String) = GradeResult(
        isCorrect = false,
        normalizedResponse = null,
        expectedCanonicalAnswer = question.canonicalAnswer,
        feedback = feedback,
    )

    private fun materialize(
        elementId: String,
        mode: QuizMode,
        prompt: String,
        choices: List<QuizChoice>?,
        answer: QuizAnswer,
        explanation: ExplanationSteps,
        audit: MentalMathAudit,
        seed: Long,
        difficulty: Int,
    ): QuizQuestion {
        val payload = canonicalPayload(
            elementId,
            mode,
            prompt,
            choices,
            answer,
            explanation,
            audit,
            seed,
            difficulty,
        )
        val snapshotId = "snapshot-v$SNAPSHOT_VERSION-${hex64(stableHash64(payload))}"
        val snapshot = QuestionSnapshot(
            id = snapshotId,
            version = SNAPSHOT_VERSION,
            rendererVersion = RENDERER_VERSION,
            generationSeed = seed,
            difficulty = difficulty,
            canonicalPayload = payload,
        )
        return QuizQuestion(
            instanceId = "quiz-$snapshotId",
            elementId = elementId,
            mode = mode,
            prompt = prompt,
            choices = choices,
            canonicalAnswer = answer.canonicalValue,
            answerUnit = answer.unit,
            answer = answer,
            explanationSteps = explanation,
            audit = audit,
            snapshot = snapshot,
        )
    }

    private fun canonicalPayload(
        elementId: String,
        mode: QuizMode,
        prompt: String,
        choices: List<QuizChoice>?,
        answer: QuizAnswer,
        explanation: ExplanationSteps,
        audit: MentalMathAudit,
        seed: Long,
        difficulty: Int,
    ): String {
        val choicePayload = choices.orEmpty().joinToString(separator = "") {
            framed(it.id) + framed(it.text) + framed(it.sourceElementId.orEmpty())
        }
        val operationPayload = audit.operations.joinToString(separator = "") {
            framed(it.expression) + framed(it.result.toString()) + framed(it.exact.toString())
        }
        return listOf(
            SNAPSHOT_VERSION.toString(),
            RENDERER_VERSION,
            seed.toString(),
            difficulty.toString(),
            elementId,
            mode.name,
            prompt,
            choicePayload,
            answer.kind.name,
            answer.canonicalValue,
            answer.unit,
            answer.correctChoiceId.orEmpty(),
            explanation.concept,
            explanation.formula,
            explanation.substitution,
            explanation.answer,
            explanation.interpretation,
            operationPayload,
            audit.maxAbsoluteIntermediate.toString(),
            audit.maxAllowedAbsoluteIntermediate.toString(),
            audit.operationCount.toString(),
            audit.maxAllowedOperations.toString(),
            audit.allIntermediatesAreIntegers.toString(),
            audit.withinDifficultyCap.toString(),
            audit.passed.toString(),
        ).joinToString(separator = "", transform = ::framed)
    }

    private fun requireDifficulty(difficulty: Int) {
        require(difficulty in 1..3) { "Difficulty must be 1, 2, or 3." }
    }

    private fun capFor(difficulty: Int): DifficultyCap = when (difficulty) {
        1 -> DifficultyCap(maxAbsoluteIntermediate = 1_000_000L, maxOperations = 2)
        2 -> DifficultyCap(maxAbsoluteIntermediate = 5_000_000L, maxOperations = 4)
        else -> DifficultyCap(maxAbsoluteIntermediate = 25_000_000L, maxOperations = 6)
    }

    private fun noMathAudit(difficulty: Int): MentalMathAudit {
        val cap = capFor(difficulty)
        return MentalMathAudit(
            operations = emptyList(),
            maxAbsoluteIntermediate = 0,
            maxAllowedAbsoluteIntermediate = cap.maxAbsoluteIntermediate,
            operationCount = 0,
            maxAllowedOperations = cap.maxOperations,
            allIntermediatesAreIntegers = true,
            withinDifficultyCap = true,
            passed = true,
        )
    }

    private fun mathAudit(difficulty: Int, operations: List<MentalMathOperation>): MentalMathAudit {
        val cap = capFor(difficulty)
        var maximum = 0L
        for (operation in operations) {
            val absolute = if (operation.result < 0) -operation.result else operation.result
            if (absolute > maximum) maximum = absolute
        }
        val exact = operations.all { it.exact }
        // Each renderer strategy groups at most two adjacent exact AST nodes into one mental
        // chunk (for example, cancel a known factor and then move two zeros). The raw nodes are
        // retained above so exact intermediates are still independently inspectable.
        val weightedOperationScore = (operations.size + 1) / 2
        val within = maximum <= cap.maxAbsoluteIntermediate &&
            weightedOperationScore <= cap.maxOperations
        return MentalMathAudit(
            operations = operations,
            maxAbsoluteIntermediate = maximum,
            maxAllowedAbsoluteIntermediate = cap.maxAbsoluteIntermediate,
            operationCount = weightedOperationScore,
            maxAllowedOperations = cap.maxOperations,
            allIntermediatesAreIntegers = exact,
            withinDifficultyCap = within,
            passed = exact && within,
        )
    }

    private fun op(expression: String, result: Long, exact: Boolean = true) =
        MentalMathOperation(expression, result, exact)

    private fun calc(
        prompt: String,
        answer: Long,
        unit: String,
        concept: String,
        formula: String,
        substitution: String,
        interpretation: String,
        vararg operations: MentalMathOperation,
    ) = CalculationDraft(
        prompt = prompt,
        answer = answer,
        unit = unit,
        concept = concept,
        formula = formula,
        substitution = substitution,
        interpretation = interpretation,
        operations = operations.toList(),
    )

    // Accounting -----------------------------------------------------------------------------

    private fun acc01(r: StableRandom, d: Int): CalculationDraft {
        val liabilities = r.stepped(200, 500 + d * 200, 50).toLong()
        val equity = r.stepped(300, 700 + d * 250, 50).toLong()
        val nonCash = r.stepped(100, (liabilities + equity - 100).toInt(), 50).toLong()
        val total = liabilities + equity
        val cash = total - nonCash
        return calc(
            "부채가 ${commas(liabilities)}억원, 자본이 ${commas(equity)}억원, 비현금자산이 ${commas(nonCash)}억원이다. 현금은 얼마인가?",
            cash, "억원", "회계등식에서 자산은 부채와 자본의 합입니다.",
            "현금 = 부채 + 자본 - 비현금자산",
            "${commas(liabilities)} + ${commas(equity)} - ${commas(nonCash)}",
            "계산된 현금을 더하면 자산총계와 부채·자본총계가 일치합니다.",
            op("$liabilities + $equity", total),
            op("$total - $nonCash", cash),
        )
    }

    private fun acc04(r: StableRandom, d: Int): CalculationDraft {
        val beginning = r.stepped(100, 300 + d * 150, 10).toLong()
        val purchases = r.stepped(400, 800 + d * 300, 10).toLong()
        val available = beginning + purchases
        val ending = r.stepped(50, (available - 50).toInt(), 10).toLong()
        val cogs = available - ending
        return calc(
            "기초재고 ${commas(beginning)}억원, 당기매입 ${commas(purchases)}억원, 기말재고 ${commas(ending)}억원일 때 매출원가는?",
            cogs, "억원", "판매가능재고 중 기말에 남지 않은 금액이 매출원가입니다.",
            "COGS = 기초재고 + 매입 - 기말재고",
            "${commas(beginning)} + ${commas(purchases)} - ${commas(ending)}",
            "기말재고가 커질수록 다른 조건이 같을 때 매출원가는 작아집니다.",
            op("$beginning + $purchases", available),
            op("$available - $ending", cogs),
        )
    }

    private fun acc12(r: StableRandom, d: Int): CalculationDraft {
        val margin = r.between(3, 6 + d * 2).toLong()
        val turnover = r.between(1, if (d == 1) 2 else 3).toLong()
        val multiplier = r.between(1, if (d == 3) 4 else 3).toLong()
        val roa = margin * turnover
        val roe = roa * multiplier
        return calc(
            "순이익률 ${margin}%, 자산회전율 ${turnover}배, 자기자본승수 ${multiplier}배일 때 DuPont ROE는?",
            roe, "%", "DuPont은 수익성, 효율성, 재무레버리지를 곱해 ROE를 분해합니다.",
            "ROE = 순이익률 × 자산회전율 × 자기자본승수",
            "$margin × $turnover × $multiplier",
            "같은 마진에서도 회전율이나 레버리지가 높으면 ROE가 높아질 수 있습니다.",
            op("$margin * $turnover", roa),
            op("$roa * $multiplier", roe),
        )
    }

    // Corporate finance ----------------------------------------------------------------------

    private fun cf02(r: StableRandom, d: Int): CalculationDraft {
        val growth = r.between(0, 2 + d).toLong()
        val spread = r.between(3, 6 + d).toLong()
        val discount = growth + spread
        val k = r.between(5, 15 + d * 10).toLong()
        val cashFlow = spread * k
        val numerator = cashFlow * 100
        val value = numerator / spread
        return calc(
            "내년 현금흐름이 ${cashFlow}억원이고 할인율 ${discount}%, 영구성장률 ${growth}%일 때 성장영구연금의 현재가치는?",
            value, "억원", "성장영구연금은 할인율이 성장률보다 클 때만 유효합니다.",
            "PV = C1 / (r - g)",
            "$cashFlow × 100 / ($discount - $growth)",
            "할인율과 성장률의 차이가 작아질수록 가치 민감도가 커집니다.",
            op("$discount - $growth", spread),
            op("$cashFlow * 100", numerator),
            op("$numerator / $spread", value, numerator % spread == 0L),
        )
    }

    private fun cf09(r: StableRandom, d: Int): CalculationDraft {
        val depreciation = r.stepped(100, 400 + d * 300, 100).toLong()
        val taxRate = r.pick(listOf(10L, 15L, 20L, 25L, 30L))
        val numerator = depreciation * taxRate
        val shield = numerator / 100
        return calc(
            "연간 감가상각비 ${commas(depreciation)}억원, 법인세율 ${taxRate}%일 때 감가상각 절세효과는?",
            shield, "억원", "감가상각은 비현금비용이지만 과세소득을 줄여 현금 절세효과를 만듭니다.",
            "절세효과 = 감가상각비 × 세율",
            "${commas(depreciation)} × $taxRate / 100",
            "다른 조건이 같다면 이 절세효과만큼 프로젝트 영업현금흐름이 증가합니다.",
            op("$depreciation * $taxRate", numerator),
            op("$numerator / 100", shield, numerator % 100 == 0L),
        )
    }

    private fun cf11(r: StableRandom, d: Int): CalculationDraft {
        val growth = r.between(0, 2 + d).toLong()
        val spread = r.between(3, 5 + d).toLong()
        val wacc = growth + spread
        val k = r.between(10, 30 + d * 20).toLong()
        val nextFcf = spread * k
        val numerator = nextFcf * 100
        val terminal = numerator / spread
        return calc(
            "명시기간 다음 해 FCFF가 ${nextFcf}억원, WACC ${wacc}%, 영구성장률 ${growth}%일 때 명시기간 말 계속가치는?",
            terminal, "억원", "계속가치는 명시기간 이후 현금흐름의 명시기간 말 가치입니다.",
            "TV = FCFF(n+1) / (WACC - g)",
            "$nextFcf × 100 / ($wacc - $growth)",
            "g는 WACC보다 작아야 하며 작은 가정 변화도 가치에 크게 반영됩니다.",
            op("$wacc - $growth", spread),
            op("$nextFcf * 100", numerator),
            op("$numerator / $spread", terminal, numerator % spread == 0L),
        )
    }

    // Investments ----------------------------------------------------------------------------

    private fun inv01(r: StableRandom, d: Int): CalculationDraft {
        val k = r.between(10, 30 + d * 15).toLong()
        val initial = 100 * k
        val returnPct = r.pick(listOf(-20L, -10L, 5L, 10L, 15L, 20L, 30L, 40L))
        val dividendPct = r.between(0, 2 + d).toLong()
        val dividend = k * dividendPct
        val ending = initial + k * returnPct - dividend
        val gain = ending - initial + dividend
        val numerator = gain * 100
        val answer = numerator / initial
        return calc(
            "주식을 ${commas(initial)}원에 매수해 ${commas(ending)}원에 매도하고 배당 ${commas(dividend)}원을 받았다. 보유기간수익률은?",
            answer, "%", "보유기간수익률은 가격변화와 보유 중 현금분배를 모두 포함합니다.",
            "HPR = (P1 - P0 + D) / P0 × 100",
            "(${commas(ending)} - ${commas(initial)} + ${commas(dividend)}) × 100 / ${commas(initial)}",
            "음수이면 배당을 포함해도 투자기간 전체 손실이었다는 뜻입니다.",
            op("$ending - $initial + $dividend", gain),
            op("$gain * 100", numerator),
            op("$numerator / $initial", answer, numerator % initial == 0L),
        )
    }

    private fun inv04(r: StableRandom, d: Int): CalculationDraft {
        val weightA = r.pick(listOf(20L, 40L, 60L, 80L))
        val weightB = 100 - weightA
        val returnA = r.stepped(-10, 15 + d * 5, 5).toLong()
        val returnB = r.stepped(-10, 15 + d * 5, 5).toLong()
        val contributionA = weightA * returnA
        val contributionB = weightB * returnB
        val numerator = contributionA + contributionB
        val portfolio = numerator / 100
        return calc(
            "A자산 비중 ${weightA}%·수익률 ${signed(returnA)}%, B자산 비중 ${weightB}%·수익률 ${signed(returnB)}%일 때 포트폴리오 수익률은?",
            portfolio, "%", "포트폴리오 기대수익률은 자산별 수익률의 비중가중합입니다.",
            "Rp = wA×RA + wB×RB",
            "($weightA × $returnA + $weightB × $returnB) / 100",
            "한 자산의 음의 수익률도 비중만큼 전체 수익률에 반영됩니다.",
            op("$weightA * $returnA", contributionA),
            op("$weightB * $returnB", contributionB),
            op("$contributionA + $contributionB", numerator),
            op("$numerator / 100", portfolio, numerator % 100 == 0L),
        )
    }

    private fun inv06(r: StableRandom, d: Int): CalculationDraft {
        val riskFree = r.between(1, 3 + d).toLong()
        val beta100 = r.pick(listOf(50L, 75L, 100L, 125L, 150L))
        val premium = r.pick(listOf(4L, 8L, 12L))
        val rfBp = riskFree * 100
        val riskBp = beta100 * premium
        val requiredBp = rfBp + riskBp
        return calc(
            "무위험수익률 ${riskFree}%, 베타 ${beta100}/100, 시장위험프리미엄 ${premium}%일 때 CAPM 요구수익률을 bp로 구하라.",
            requiredBp, "bp", "CAPM은 체계적 위험인 베타에 대해서만 위험프리미엄을 요구합니다.",
            "E(Ri)bp = 100×Rf + beta×100 × MRP",
            "100 × $riskFree + $beta100 × $premium",
            "베타가 1보다 크면 시장위험프리미엄보다 큰 위험 보상이 붙습니다.",
            op("$riskFree * 100", rfBp),
            op("$beta100 * $premium", riskBp),
            op("$rfBp + $riskBp", requiredBp),
        )
    }

    // Fixed income ---------------------------------------------------------------------------

    private fun fi03(r: StableRandom, d: Int): CalculationDraft {
        val weight1 = r.stepped(10, 15 + d * 5, 5).toLong()
        val weight2 = r.stepped(15, 20 + d * 5, 5).toLong()
        val weight3 = 100 - weight1 - weight2
        val pv1 = weight1 * 100
        val pv2 = weight2 * 100
        val pv3 = weight3 * 100
        val weighted1 = weight1
        val weighted2 = 2 * weight2
        val weighted3 = 3 * weight3
        val duration100 = weighted1 + weighted2 + weighted3
        return calc(
            "1·2·3년 현금흐름의 현재가치가 각각 ${commas(pv1)}원, ${commas(pv2)}원, ${commas(pv3)}원이고 채권가격이 10,000원이다. Macaulay duration을 centiyear(0.01년)로 구하라.",
            duration100, "centiyear", "Macaulay duration은 현재가치 현금흐름의 시간 가중평균입니다.",
            "D×100 = Σ[t × PV(CFt)/100] (P=10,000)",
            "1×$weight1 + 2×$weight2 + 3×$weight3",
            "100 centiyear가 1년이며 만기 원금 비중이 클수록 duration이 만기에 가까워집니다.",
            op("1 * $weight1", weighted1),
            op("2 * $weight2", weighted2),
            op("3 * $weight3", weighted3),
            op("$weighted1 + $weighted2 + $weighted3", duration100),
        )
    }

    private fun fi07(r: StableRandom, d: Int): CalculationDraft {
        val k = r.between(10, 30 + d * 20).toLong()
        val collateral = 100 * k
        val haircut = r.between(0, 5 + d * 5).toLong()
        val retainedPct = 100 - haircut
        val numerator = collateral * retainedPct
        val cash = numerator / 100
        return calc(
            "담보 시가가 ${commas(collateral)}만원이고 repo haircut이 ${haircut}%일 때 조달 가능한 현금은?",
            cash, "만원", "Haircut은 담보가치 중 대출에 반영하지 않는 비율입니다.",
            "Cash = Collateral × (1 - haircut)",
            "${commas(collateral)} × $retainedPct / 100",
            "Haircut이 커지면 같은 담보로 조달할 수 있는 현금은 줄어듭니다.",
            op("100 - $haircut", retainedPct),
            op("$collateral * $retainedPct", numerator),
            op("$numerator / 100", cash, numerator % 100 == 0L),
        )
    }

    private fun fi10(r: StableRandom, d: Int): CalculationDraft {
        val k = r.between(2, 3 + d * 2).toLong()
        val ead = 10_000 * k
        val pd = r.between(1, 4 + d * 2).toLong()
        val recovery = r.pick(listOf(20L, 40L, 50L, 60L, 80L))
        val lgd = 100 - recovery
        val eadUnit = ead / 10_000
        val pdLoss = eadUnit * pd
        val loss = pdLoss * lgd
        return calc(
            "부도 시 익스포저 ${commas(ead)}원, 부도확률 ${pd}%, 회수율 ${recovery}%일 때 1기간 기대손실은?",
            loss, "원", "기대손실은 익스포저, 부도확률, 부도 시 손실률을 곱합니다.",
            "EL = EAD × PD × (1 - Recovery)",
            "${commas(ead)} / 10,000 × $pd × $lgd",
            "이는 확률가중 평균 손실이며 실제 신용스프레드에는 다른 프리미엄도 포함됩니다.",
            op("$ead / 10000", eadUnit, ead % 10_000 == 0L),
            op("$eadUnit * $pd", pdLoss),
            op("$pdLoss * $lgd", loss),
        )
    }

    // Derivatives ----------------------------------------------------------------------------

    private fun der01(r: StableRandom, d: Int): CalculationDraft {
        val k = r.between(10, 30 + d * 20).toLong()
        val spot = 100 * k
        val rate = r.between(1, 4 + d * 2).toLong()
        val factor = 100 + rate
        val numerator = spot * factor
        val forward = numerator / 100
        return calc(
            "중간 현금수익이 없는 자산의 현물가격이 ${commas(spot)}원이고 1년 조달금리가 ${rate}%일 때 이론 선도가격은?",
            forward, "원", "현물을 차입 매수해 선도로 인도하는 현금흐름이 이론가격을 결정합니다.",
            "F0 = S0 × (1 + r)",
            "${commas(spot)} × $factor / 100",
            "시장 선도가격이 이론가격과 다르면 거래비용 전 무차익 기회가 생길 수 있습니다.",
            op("100 + $rate", factor),
            op("$spot * $factor", numerator),
            op("$numerator / 100", forward, numerator % 100 == 0L),
        )
    }

    private fun der04(r: StableRandom, d: Int): CalculationDraft {
        val strike = r.stepped(5_000, 8_000 + d * 4_000, 500).toLong()
        val move = r.stepped(-3_000, 3_000, 500).toLong()
        val terminal = strike + move
        val isCall = r.nextBoolean()
        val isLong = r.nextBoolean()
        val multiplier = r.pick(listOf(1L, 10L))
        val contracts = r.between(1, 3 + d * 2).toLong()
        val intrinsic = if (isCall) maxOf(terminal - strike, 0) else maxOf(strike - terminal, 0)
        val gross = intrinsic * multiplier * contracts
        val payoff = if (isLong) gross else -gross
        val optionName = if (isCall) "콜" else "풋"
        val positionName = if (isLong) "매수" else "매도"
        return calc(
            "행사가 ${commas(strike)}원, 만기주가 ${commas(terminal)}원인 $optionName 옵션을 $positionName ${contracts}계약했다. 계약승수는 ${multiplier}이다. 만기 payoff는?",
            payoff, "원", "옵션 payoff는 내재가치에 수량과 포지션 부호를 반영하며 최초 프리미엄은 제외합니다.",
            if (isCall) "Call payoff = position×N×M×max(ST-K,0)" else "Put payoff = position×N×M×max(K-ST,0)",
            "${if (isLong) "+" else "-"}$contracts × $multiplier × $intrinsic",
            "매도 포지션의 payoff는 같은 옵션 매수 payoff의 정확한 반대 부호입니다.",
            op(if (isCall) "max($terminal - $strike, 0)" else "max($strike - $terminal, 0)", intrinsic),
            op("$intrinsic * $multiplier * $contracts", gross),
            op("position * $gross", payoff),
        )
    }

    private fun der06(r: StableRandom, d: Int): CalculationDraft {
        val spot = r.stepped(5_000, 10_000 + d * 5_000, 500).toLong()
        val discount = r.stepped(500, 1_000 + d * 500, 100).toLong()
        val pvStrike = spot - discount
        val put = r.stepped(200, 500 + d * 300, 100).toLong()
        val right = put + spot
        val call = right - pvStrike
        return calc(
            "동일 만기·행사가의 무배당 유럽형 옵션에서 현물 ${commas(spot)}원, 행사가 현재가치 ${commas(pvStrike)}원, 풋 ${commas(put)}원이다. 풋-콜 패리티가 성립하는 콜 가격은?",
            call, "원", "풋-콜 패리티는 같은 만기와 행사가를 가진 합성 포지션의 무차익 관계입니다.",
            "C + PV(K) = P + S0",
            "C = ${commas(put)} + ${commas(spot)} - ${commas(pvStrike)}",
            "두 변의 시장가치가 다르면 싼 포트폴리오를 사고 비싼 포트폴리오를 파는 차익거래를 검토합니다.",
            op("$put + $spot", right),
            op("$right - $pvStrike", call),
        )
    }

    // Equity research ------------------------------------------------------------------------

    private fun eqv01(r: StableRandom, d: Int): CalculationDraft {
        val price = r.between(2, 5 + d * 3).toLong()
        val quantity = r.stepped(10, 30 + d * 20, 10).toLong()
        val revenue = price * quantity
        return calc(
            "제품 평균단가가 천 개당 ${price}억원이고 판매량이 ${quantity}천 개일 때 매출은?",
            revenue, "억원", "매출 드라이버는 가격과 판매량으로 분해할 수 있습니다.",
            "Revenue = Price × Quantity",
            "$price × $quantity",
            "매출 변화가 가격 효과인지 물량 효과인지 나누면 추정의 원인을 설명하기 쉽습니다.",
            op("$price * $quantity", revenue),
        )
    }

    private fun eqv02(r: StableRandom, d: Int): CalculationDraft {
        val k = r.between(5, 10 + d * 8).toLong()
        val revenue = 100 * k
        val grossMargin = r.between(35, 45 + d * 5).toLong()
        val sgaMargin = r.between(10, 20 + d * 3).toLong()
        val operatingMargin = grossMargin - sgaMargin
        val ebit = k * operatingMargin
        return calc(
            "매출 ${commas(revenue)}억원, 매출총이익률 ${grossMargin}%, 판관비율 ${sgaMargin}%일 때 영업이익은?",
            ebit, "억원", "영업이익률은 매출총이익률에서 매출 대비 판관비율을 뺀 값입니다.",
            "EBIT = Revenue × (GrossMargin - SG&A Margin)",
            "${commas(revenue)} / 100 × ($grossMargin - $sgaMargin)",
            "매출총이익률이 같아도 판관비 부담이 높으면 영업이익은 줄어듭니다.",
            op("$grossMargin - $sgaMargin", operatingMargin),
            op("$revenue / 100", k, revenue % 100 == 0L),
            op("$k * $operatingMargin", ebit),
        )
    }

    private fun eqv15(r: StableRandom, d: Int): CalculationDraft {
        val growth = r.between(1, 2 + d).toLong()
        val spread = r.between(3, 5 + d).toLong()
        val wacc = growth + spread
        val k = r.between(10, 25 + d * 15).toLong()
        val nextFcff = k * spread
        val numerator = nextFcff * 100
        val terminal = numerator / spread
        return calc(
            "다음 해 FCFF ${nextFcff}억원, WACC ${wacc}%, 영구성장률 ${growth}%인 기업의 계속가치는?",
            terminal, "억원", "주식 리서치 DCF의 계속가치는 명시기간 이후 FCFF를 자본제공자 전체 기준으로 평가합니다.",
            "TV = FCFF(n+1) / (WACC - g)",
            "$nextFcff × 100 / ($wacc - $growth)",
            "계속가치를 EV에 반영한 뒤 순부채를 차감해야 보통주 지분가치가 됩니다.",
            op("$wacc - $growth", spread),
            op("$nextFcff * 100", numerator),
            op("$numerator / $spread", terminal, numerator % spread == 0L),
        )
    }

    // IB, markets, and alternatives ----------------------------------------------------------

    private fun ibt01(r: StableRandom, d: Int): CalculationDraft {
        val nominal = r.stepped(100, 250 + d * 100, 25).toLong()
        val inflation = r.stepped(100, 250 + d * 100, 25).toLong()
        val real = nominal - inflation
        return calc(
            "명목 정책금리가 ${nominal}bp이고 기대인플레이션이 ${inflation}bp일 때 근사 사전 실질금리는?",
            real, "bp", "근사 Fisher 관계에서는 명목금리에서 기대인플레이션을 뺍니다.",
            "RealRate(bp) ≈ NominalRate(bp) - Inflation(bp)",
            "$nominal - $inflation",
            "음수 실질금리는 명목금리가 기대인플레이션보다 낮다는 뜻입니다.",
            op("$nominal - $inflation", real),
        )
    }

    private fun ibt02(r: StableRandom, d: Int): CalculationDraft {
        val notional = r.between(1, 3 + d * 3).toLong()
        val start = r.stepped(1_100, 1_300 + d * 50, 10).toLong()
        val delta = r.pick(listOf(-100L, -50L, -20L, 20L, 50L, 100L))
        val end = start + delta
        val pnl = notional * delta
        return calc(
            "${notional}백만달러 매출채권을 보유하고 있다. 원/달러 환율이 ${commas(start)}원에서 ${commas(end)}원으로 변할 때 환산손익은?",
            pnl, "백만원", "달러 수취자산은 원/달러 환율 상승 시 원화 환산가치가 증가합니다.",
            "FX P&L = USD Notional × (S1 - S0)",
            "$notional × ($end - $start)",
            "부호가 양수면 환산이익, 음수면 환산손실입니다.",
            op("$end - $start", delta),
            op("$notional * $delta", pnl),
        )
    }

    private fun ibt03(r: StableRandom, d: Int): CalculationDraft {
        val duration = r.between(2, 3 + d * 2).toLong()
        val spreadChange = r.pick(listOf(-100L, -50L, -20L, 20L, 50L, 100L))
        val raw = duration * spreadChange
        val priceChange = -raw
        return calc(
            "수정듀레이션이 ${duration}인 회사채의 신용스프레드가 ${signed(spreadChange)}bp 변했다. 국채금리가 불변일 때 근사 가격변화는?",
            priceChange, "가격bp", "듀레이션 근사에서 요구수익률 또는 스프레드와 가격은 반대로 움직입니다.",
            "PriceChange(bp) ≈ -ModifiedDuration × SpreadChange(bp)",
            "-$duration × ($spreadChange)",
            "스프레드 확대는 음의 가격변화, 축소는 양의 가격변화를 뜻합니다.",
            op("$duration * $spreadChange", raw),
            op("-$raw", priceChange),
        )
    }

    private fun ibt04(r: StableRandom, d: Int): CalculationDraft {
        val rateChange = r.pick(listOf(-100L, -50L, -25L, 25L, 50L, 100L))
        val base = 10_000L / gcd(absNonMin(rateChange), 10_000L)
        val k = r.between(1, 2 + d * 2).toLong()
        val balance = base * k
        val numerator = balance * rateChange
        val interest = numerator / 10_000
        return calc(
            "변동금리 대출자산 ${commas(balance)}억원이 정책금리 변화를 100% 반영한다. 금리가 ${signed(rateChange)}bp 변할 때 연간 이자수익 변화는?",
            interest, "억원", "금리 bp 변화는 잔액에 10,000분의 변화율로 적용합니다.",
            "ΔInterest = Balance × ΔRateBp / 10,000",
            "${commas(balance)} × ($rateChange) / 10,000",
            "음수는 연간 이자수익 감소를 뜻합니다.",
            op("$balance * $rateChange", numerator),
            op("$numerator / 10000", interest, numerator % 10_000 == 0L),
        )
    }

    private fun ibt05(r: StableRandom, d: Int): CalculationDraft {
        val equity = r.stepped(500, 1_000 + d * 700, 100).toLong()
        val debt = r.stepped(100, 300 + d * 200, 100).toLong()
        val preferred = r.stepped(0, d * 100, 100).toLong()
        val minority = r.stepped(0, d * 100, 100).toLong()
        val cash = r.stepped(0, 100 + d * 100, 100).toLong()
        val ev = equity + debt + preferred + minority - cash
        val afterDebt = ev - debt
        val afterPreferred = afterDebt - preferred
        val afterMinority = afterPreferred - minority
        val answer = afterMinority + cash
        return calc(
            "거래 EV ${commas(ev)}억원, 부채 ${commas(debt)}억원, 우선주 ${commas(preferred)}억원, 비지배지분 ${commas(minority)}억원, 현금 ${commas(cash)}억원이다. 보통주 지분가치는?",
            answer, "억원", "EV에서 채권자와 다른 지분청구권을 빼고 비영업 현금을 더해 보통주 가치를 구합니다.",
            "Equity = EV - Debt - Preferred - Minority + Cash",
            "${commas(ev)} - ${commas(debt)} - ${commas(preferred)} - ${commas(minority)} + ${commas(cash)}",
            "EV와 equity value를 혼동하면 거래대금과 배수 해석이 달라집니다.",
            op("$ev - $debt", afterDebt),
            op("$afterDebt - $preferred", afterPreferred),
            op("$afterPreferred - $minority", afterMinority),
            op("$afterMinority + $cash", answer),
        )
    }

    private fun ibt06(r: StableRandom, d: Int): CalculationDraft {
        val rate = r.between(5, 8 + d * 2).toLong()
        val k = r.between(10, 20 + d * 15).toLong()
        val annualSynergy = rate * k
        val pvNumerator = annualSynergy * 100
        val synergyPv = pvNumerator / rate
        val integrationCost = r.stepped(0, (synergyPv / 2).toInt(), 100).toLong()
        val net = synergyPv - integrationCost
        return calc(
            "세후 연간 시너지 ${annualSynergy}억원이 무성장으로 영구 지속되고 할인율은 ${rate}%다. 일회성 통합비용 ${commas(integrationCost)}억원 차감 후 순가치창출액은?",
            net, "억원", "영구 시너지의 현재가치에서 일회성 통합비용을 차감합니다.",
            "NetValue = AnnualSynergy / r - IntegrationCost",
            "$annualSynergy × 100 / $rate - ${commas(integrationCost)}",
            "순가치가 양수여도 실행위험과 시너지 실현시점을 별도로 검토해야 합니다.",
            op("$annualSynergy * 100", pvNumerator),
            op("$pvNumerator / $rate", synergyPv, pvNumerator % rate == 0L),
            op("$synergyPv - $integrationCost", net),
        )
    }

    private fun ibt07(r: StableRandom, d: Int): CalculationDraft {
        val buyerEps = r.stepped(1_000, 2_000 + d * 700, 100).toLong()
        val changePct = r.pick(listOf(-20L, -10L, 10L, 20L, 25L))
        val postNumerator = buyerEps * (100 + changePct)
        val postEps = postNumerator / 100
        val change = postEps - buyerEps
        val adNumerator = change * 100
        val answer = adNumerator / buyerEps
        return calc(
            "인수 전 매수회사 EPS가 ${commas(buyerEps)}원, 거래 후 pro forma EPS가 ${commas(postEps)}원이다. EPS accretion/dilution 비율은?",
            answer, "%", "거래 후 EPS를 거래 전 EPS와 비교해 증대 또는 희석을 측정합니다.",
            "A/D% = (ProFormaEPS / BuyerEPS - 1) × 100",
            "(${commas(postEps)} - ${commas(buyerEps)}) × 100 / ${commas(buyerEps)}",
            "양수는 accretion, 음수는 dilution이며 이것만으로 가치창출을 확정할 수는 없습니다.",
            op("$postEps - $buyerEps", change),
            op("$change * 100", adNumerator),
            op("$adNumerator / $buyerEps", answer, adNumerator % buyerEps == 0L),
        )
    }

    private fun ibt08(r: StableRandom, d: Int): CalculationDraft {
        val buyerPrice = r.stepped(4_000, 8_000 + d * 4_000, 1_000).toLong()
        val ratio100 = r.pick(listOf(25L, 50L, 75L, 100L, 125L, 150L, 200L))
        val numerator = buyerPrice * ratio100
        val offerPrice = numerator / 100
        val buyerPriceHundredth = buyerPrice / 100
        val answer = offerPrice / buyerPriceHundredth
        return calc(
            "인수회사 주가가 ${commas(buyerPrice)}원이고 목표회사 1주당 제시가가 ${commas(offerPrice)}원인 주식대가 거래다. 교환비율×100은?",
            answer, "교환비율×100", "주식교환비율은 목표주주 1주당 지급할 인수회사 주식 수입니다.",
            "ExchangeRatio×100 = OfferPrice / BuyerPrice × 100",
            "${commas(offerPrice)} × 100 / ${commas(buyerPrice)}",
            "100이면 목표주식 1주당 인수회사 주식 1주를 지급한다는 뜻입니다.",
            op("$buyerPrice / 100", buyerPriceHundredth, buyerPrice % 100 == 0L),
            op("$offerPrice / $buyerPriceHundredth", answer, offerPrice % buyerPriceHundredth == 0L),
        )
    }

    private fun ibt09(r: StableRandom, d: Int): CalculationDraft {
        val price = r.between(1, 4 + d * 3).toLong()
        val newShares = r.stepped(100, 200 + d * 150, 50).toLong()
        val secondary = r.stepped(0, 100 + d * 100, 50).toLong()
        val proceeds = price * newShares
        return calc(
            "IPO 공모가가 주당 ${price}만원, 신주 ${newShares}만주, 구주매출 ${secondary}만주다. 회사로 유입되는 gross primary proceeds는?",
            proceeds, "억원", "회사는 신주 발행대금만 수취하고 구주매출 대금은 기존 주주에게 귀속됩니다.",
            "PrimaryProceeds = OfferPrice × NewShares",
            "$price × $newShares (1만원×1만주=1억원)",
            "총 공모규모에는 구주매출이 포함되므로 회사 유입액과 구분해야 합니다.",
            op("$price * $newShares", proceeds),
        )
    }

    private fun ibt10(r: StableRandom, d: Int): CalculationDraft {
        val dilution = r.between(5, 15 + d * 8).toLong()
        val k = r.between(2, 5 + d * 3).toLong()
        val newShares = dilution * k
        val oldShares = (100 - dilution) * k
        val postShares = oldShares + newShares
        val numerator = newShares * 100
        val answer = numerator / postShares
        return calc(
            "IPO 전 기존주식 ${oldShares}만주에 신주 ${newShares}만주를 발행한다. 기존주주의 경제적 지분 희석률은?",
            answer, "%", "신주가 post-money 주식수에서 차지하는 비율이 기존주주의 소유비율 희석입니다.",
            "Dilution% = NewShares / PostMoneyShares × 100",
            "$newShares × 100 / ($oldShares + $newShares)",
            "이는 소유비율 희석이며 공모가격 자체의 할인율과는 다른 개념입니다.",
            op("$oldShares + $newShares", postShares),
            op("$newShares * 100", numerator),
            op("$numerator / $postShares", answer, numerator % postShares == 0L),
        )
    }

    private fun ibt11(r: StableRandom, d: Int): CalculationDraft {
        val eps = r.stepped(500, 1_000 + d * 700, 100).toLong()
        val per = r.between(5, 8 + d * 5).toLong()
        val price = eps * per
        val answer = price / eps
        return calc(
            "공모가가 ${commas(price)}원이고 post-money 기준 EPS가 ${commas(eps)}원일 때 공모가 기준 PER은?",
            answer, "배", "PER은 보통주 주가를 같은 기간·청구권의 EPS와 대응시킨 배수입니다.",
            "PER = Price / EPS",
            "${commas(price)} / ${commas(eps)}",
            "동일 PER 비교 전 일회성 이익과 회계기간을 정규화해야 합니다.",
            op("$price / $eps", answer, price % eps == 0L),
        )
    }

    private fun ibt12(r: StableRandom, d: Int): CalculationDraft {
        val k = r.between(5, 10 + d * 8).toLong()
        val grossRent = 100 * k
        val vacancy = r.between(0, 5 + d * 5).toLong()
        val vacancyLoss = k * vacancy
        val effectiveRent = grossRent - vacancyLoss
        val opex = r.stepped(10, maxOf(10, (effectiveRent / 2).toInt()), 10).toLong()
        val noi = effectiveRent - opex
        return calc(
            "잠재총임대료 ${commas(grossRent)}억원, 공실률 ${vacancy}%, 운영비 ${commas(opex)}억원일 때 NOI는?",
            noi, "억원", "NOI는 부동산 운영수익에서 공실손실과 운영비를 차감하며 금융비용은 제외합니다.",
            "NOI = GPR - VacancyLoss - OperatingExpenses",
            "${commas(grossRent)} - $k×$vacancy - ${commas(opex)}",
            "NOI는 cap rate 가치평가와 DSCR의 핵심 분자입니다.",
            op("$k * $vacancy", vacancyLoss),
            op("$grossRent - $vacancyLoss", effectiveRent),
            op("$effectiveRent - $opex", noi),
        )
    }

    private fun ibt13(r: StableRandom, d: Int): CalculationDraft {
        val capRate = r.between(3, 5 + d * 2).toLong()
        val k = r.between(10, 25 + d * 15).toLong()
        val noi = capRate * k
        val numerator = noi * 100
        val value = numerator / capRate
        return calc(
            "안정화 NOI가 ${noi}억원이고 시장 cap rate가 ${capRate}%일 때 부동산 가치는?",
            value, "억원", "직접환원법은 안정화 NOI를 시장 cap rate로 나눕니다.",
            "PropertyValue = NOI / CapRate",
            "$noi × 100 / $capRate",
            "NOI가 같다면 cap rate 상승은 가치 하락을 뜻합니다.",
            op("$noi * 100", numerator),
            op("$numerator / $capRate", value, numerator % capRate == 0L),
        )
    }

    private fun ibt14(r: StableRandom, d: Int): CalculationDraft {
        val ltv = r.between(40, 55 + d * 8).toLong()
        val k = r.between(10, 25 + d * 15).toLong()
        val propertyValue = 100 * k
        val loan = ltv * k
        val numerator = loan * 100
        val answer = numerator / propertyValue
        return calc(
            "담보가치 ${commas(propertyValue)}억원, 대출잔액 ${commas(loan)}억원일 때 LTV는?",
            answer, "%", "LTV는 담보가치 대비 대출원금의 비율입니다.",
            "LTV = Loan / PropertyValue × 100",
            "${commas(loan)} × 100 / ${commas(propertyValue)}",
            "LTV가 높을수록 담보가치 하락에 대한 대주 위험 완충이 작습니다.",
            op("$loan * 100", numerator),
            op("$numerator / $propertyValue", answer, numerator % propertyValue == 0L),
        )
    }

    private fun ibt15(r: StableRandom, d: Int): CalculationDraft {
        val debtService = r.stepped(20, 40 + d * 30, 10).toLong()
        val dscr100 = r.stepped(110, 140 + d * 30, 10).toLong()
        val numerator = debtService * dscr100
        val noi = numerator / 100
        val ratioNumerator = noi * 100
        val answer = ratioNumerator / debtService
        return calc(
            "NOI가 ${noi}억원이고 연간 원리금상환액이 ${debtService}억원이다. DSCR×100은?",
            answer, "DSCR×100", "DSCR은 부채상환재원인 NOI를 연간 원리금상환액과 비교합니다.",
            "DSCR×100 = NOI / DebtService × 100",
            "$noi × 100 / $debtService",
            "150은 1.50배이며, 100 미만이면 해당 기간 NOI만으로 상환액을 충당하지 못합니다.",
            op("$noi * 100", ratioNumerator),
            op("$ratioNumerator / $debtService", answer, ratioNumerator % debtService == 0L),
        )
    }

    private fun ibt16(r: StableRandom, d: Int): CalculationDraft {
        val k = r.between(10, 20 + d * 15).toLong()
        val initial = 100 * k
        val irr = r.pick(listOf(-20L, -10L, 10L, 20L, 30L, 40L, 50L))
        val distribution = k * (100 + irr)
        val gain = distribution - initial
        val numerator = gain * 100
        val answer = numerator / initial
        return calc(
            "초기 자기자본 ${commas(initial)}억원을 투자하고 1년 뒤 순분배액 ${commas(distribution)}억원을 받았다. 1년 levered IRR은?",
            answer, "%", "1년 단일기간에서는 IRR이 보유기간 자기자본수익률과 같습니다.",
            "IRR = (Distribution / InitialEquity - 1) × 100",
            "(${commas(distribution)} - ${commas(initial)}) × 100 / ${commas(initial)}",
            "레버리지는 자기자본수익률과 손실폭을 모두 확대할 수 있습니다.",
            op("$distribution - $initial", gain),
            op("$gain * 100", numerator),
            op("$numerator / $initial", answer, numerator % initial == 0L),
        )
    }

    private fun ibt17(r: StableRandom, d: Int): CalculationDraft {
        val surprise = r.pick(listOf(5L, 10L, 20L, 25L))
        val base = 100L / gcd(100, surprise)
        val k = r.between(20, 30 + d * 20).toLong()
        val consensus = base * k
        val revisedNumerator = consensus * (100 + surprise)
        val revised = revisedNumerator / 100
        val deltaEps = revised - consensus
        val targetPer = r.between(5, 8 + d * 4).toLong()
        val targetIncrease = deltaEps * targetPer
        return calc(
            "컨센서스 EPS ${commas(consensus)}원이 ${surprise}% 상향되고 목표 PER ${targetPer}배를 유지한다. 목표주가 상승분은?",
            targetIncrease, "원", "동일 배수를 유지하면 EPS 추정치 변화에 목표배수를 곱해 목표가 변화를 구할 수 있습니다.",
            "ΔTarget = (RevisedEPS - ConsensusEPS) × TargetPER",
            "(${commas(revised)} - ${commas(consensus)}) × $targetPer",
            "실적 촉매의 주가 영향은 이미 반영된 시장 기대와 배수 변화도 함께 봐야 합니다.",
            op("$revisedNumerator / 100", revised, revisedNumerator % 100 == 0L),
            op("$revised - $consensus", deltaEps),
            op("$deltaEps * $targetPer", targetIncrease),
        )
    }

    private fun ibt18(r: StableRandom, d: Int): CalculationDraft {
        val probability = r.stepped(10, 30 + d * 10, 10).toLong()
        val lossIfEvent = r.stepped(10, 50 + d * 30, 10).toLong()
        val numerator = probability * lossIfEvent
        val expected = numerator / 100
        return calc(
            "특정 하방위험의 발생확률이 ${probability}%이고 발생 시 목표주가 하락액이 ${lossIfEvent}원이다. 위험 미발생 시 손실 0원일 때 기대 하방은?",
            expected, "원", "기대 하방은 사건 확률과 사건 발생 시 손실액의 곱입니다.",
            "ExpectedDownside = Probability × LossIfEvent",
            "$probability × $lossIfEvent / 100",
            "확률가중 평균은 tail correlation이나 손실분포 전체를 대신하지 않는 보조지표입니다.",
            op("$probability * $lossIfEvent", numerator),
            op("$numerator / 100", expected, numerator % 100 == 0L),
        )
    }
}

/** Small LCG with explicitly wrapped Long arithmetic; output is stable across JVM/Android. */
private class StableRandom(seed: Long) {
    private var state: Long = seed

    private fun nextLong(): Long {
        state = state * 6_364_136_223_846_793_005L + 1_442_695_040_888_963_407L
        return state xor (state ushr 29)
    }

    fun nextInt(bound: Int): Int {
        require(bound > 0)
        return ((nextLong() ushr 1) % bound.toLong()).toInt()
    }

    fun nextBoolean(): Boolean = nextInt(2) == 0

    fun between(minimum: Int, maximum: Int): Int {
        require(maximum >= minimum)
        return minimum + nextInt(maximum - minimum + 1)
    }

    fun stepped(minimum: Int, maximum: Int, step: Int): Int {
        require(step > 0 && maximum >= minimum)
        val count = (maximum - minimum) / step + 1
        return minimum + nextInt(count) * step
    }

    fun <T> pick(values: List<T>): T {
        require(values.isNotEmpty())
        return values[nextInt(values.size)]
    }

    fun <T> shuffled(values: List<T>): List<T> {
        val result = values.toMutableList()
        for (index in result.lastIndex downTo 1) {
            val swapWith = nextInt(index + 1)
            val temporary = result[index]
            result[index] = result[swapWith]
            result[swapWith] = temporary
        }
        return result
    }
}

private fun mixedSeed(seed: Long, elementId: String, difficulty: Int, mode: QuizMode): Long =
    seed xor stableHash64("$elementId|${mode.name}|$difficulty")

/** FNV-1a over Kotlin Char code units; explicit overflow is part of the stable format. */
private fun stableHash64(value: String): Long {
    var hash = -3_750_763_034_362_895_579L
    for (character in value) {
        hash = hash xor character.code.toLong()
        hash *= 1_099_511_628_211L
    }
    return hash
}

private fun hex64(value: Long): String {
    val digits = "0123456789abcdef"
    val output = StringBuilder(16)
    for (shift in 60 downTo 0 step 4) {
        output.append(digits[((value ushr shift) and 0x0f).toInt()])
    }
    return output.toString()
}

private fun framed(value: String): String = "${value.length}:$value"

private fun gcd(first: Long, second: Long): Long {
    var a = absNonMin(first)
    var b = absNonMin(second)
    while (b != 0L) {
        val remainder = a % b
        a = b
        b = remainder
    }
    return a
}

private fun absNonMin(value: Long): Long = if (value < 0) -value else value

private fun signed(value: Long): String = if (value > 0) "+$value" else value.toString()

private fun commas(value: Long): String {
    val raw = value.toString()
    val negative = raw.startsWith('-')
    val digits = if (negative) raw.substring(1) else raw
    val grouped = digits.reversed().chunked(3).joinToString(",").reversed()
    return if (negative) "-$grouped" else grouped
}
