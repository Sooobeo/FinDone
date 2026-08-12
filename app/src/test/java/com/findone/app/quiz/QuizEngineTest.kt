package com.findone.app.quiz

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class QuizEngineTest {
    private val curriculum = (1..135).map { index ->
        val domain = listOf("ACC", "CF", "INV", "FI", "DER", "EQV", "IBT")[index % 7]
        ElementSeed(
            id = "$domain-${index.toString().padStart(3, '0')}",
            title = "학습요소 $index",
            domainName = "분야 $domain",
            coreRelation = "핵심값 $index = 입력 A와 입력 B의 검증된 관계",
        )
    }

    @Test
    fun `same inputs produce equal and byte-identical concept snapshots`() {
        val first = QuizEngine.generateConcept(curriculum[42], curriculum, 9_223_372L, 2)
        val second = QuizEngine.generateConcept(curriculum[42], curriculum, 9_223_372L, 2)

        assertEquals(first, second)
        assertArrayEquals(
            first.snapshot.canonicalPayload.toByteArray(Charsets.UTF_8),
            second.snapshot.canonicalPayload.toByteArray(Charsets.UTF_8),
        )
        assertEquals(QuizEngine.SNAPSHOT_VERSION, first.snapshotVersion)
        assertTrue(first.snapshotId.startsWith("snapshot-v2-"))
        assertEquals("quiz-${first.snapshotId}", first.instanceId)
    }

    @Test
    fun `concept renderer works for every supplied curriculum element`() {
        curriculum.forEachIndexed { index, target ->
            val question = QuizEngine.generateConcept(target, curriculum, index.toLong(), 3)

            assertEquals(target.id, question.elementId)
            assertEquals(QuizMode.CONCEPT, question.mode)
            assertEquals(5, question.choices?.size)
            assertEquals(5, question.choices?.map { it.text }?.distinct()?.size)
            assertTrue(question.choices.orEmpty().any {
                it.id == question.canonicalAnswer && it.sourceElementId == target.id
            })
            assertTrue(question.audit.passed)
        }
    }

    @Test
    fun `curated bank renderer keeps five choices and one target answer`() {
        val target = curriculum.first()
        val curated = CuratedConceptQuestion(
            questionId = "${target.id}-definition_to_term-01",
            elementId = target.id,
            questionType = "definition_to_term",
            stem = "다음 설명에 가장 부합하는 개념은?",
            explanation = "정답 개념을 검토된 사실 레코드와 대조합니다.",
            coreRelation = target.coreRelation,
            difficulty = 1,
            modelVersion = "test-ranker-v1",
            reviewStatus = "automated_pass",
            sourceFactIds = listOf("${target.id}:definition:01"),
            choices = curriculum.take(5).mapIndexed { index, element ->
                CuratedConceptChoice(
                    key = "ABCDE"[index].toString(),
                    text = element.title,
                    elementId = element.id,
                    explanation = "${element.title}의 검토된 정의입니다.",
                    isCorrect = element.id == target.id,
                )
            },
        )

        val first = QuizEngine.generateConceptFromBank(curated, seed = 42L)
        val repeated = QuizEngine.generateConceptFromBank(curated, seed = 42L)

        assertEquals(first, repeated)
        assertEquals(5, first.choices?.size)
        assertEquals(5, first.choices?.map { it.text }?.distinct()?.size)
        assertEquals(
            target.id,
            first.choices.orEmpty().single { it.id == first.canonicalAnswer }.sourceElementId,
        )
        first.choices.orEmpty().forEach { choice ->
            assertEquals("${choice.text}의 검토된 정의입니다.", choice.explanation)
        }
        assertTrue(first.audit.passed)
    }

    @Test
    fun `different seeds create substantive concept diversity`() {
        val target = curriculum[70]
        val signatures = (0L..39L).map { seed ->
            val question = QuizEngine.generateConcept(target, curriculum, seed, 2)
            question.prompt to question.choices.orEmpty().map { it.sourceElementId to it.id }
        }.toSet()

        assertTrue("Expected multiple prompt, distractor, or order variants", signatures.size >= 8)
        val seedZero = QuizEngine.generateConcept(target, curriculum, 0, 2)
        val seedOne = QuizEngine.generateConcept(target, curriculum, 1, 2)
        assertNotEquals(seedZero.snapshotId, seedOne.snapshotId)
    }

    @Test
    fun `multi-domain ordering is deterministic balanced and duplicate free`() {
        val candidates = buildList {
            listOf("A", "B", "C").forEach { domain ->
                (1..4).forEach { index ->
                    add(ElementSeed("$domain-$index", "$domain $index", domain, "$domain=$index"))
                }
            }
            add(ElementSeed("A-1", "duplicate", "A", "A=1"))
            add(ElementSeed("D-1", "unselected", "D", "D=1"))
        }
        val selected = setOf("A", "B", "C")

        val first = QuizEngine.balancedDomainElementIds(candidates, selected, seed = 42L)
        val repeated = QuizEngine.balancedDomainElementIds(candidates.reversed(), selected, seed = 42L)

        assertEquals(first, repeated)
        assertEquals(12, first.size)
        assertEquals(first.size, first.distinct().size)
        assertTrue(first.all { it.substringBefore('-') in selected })
        assertEquals(
            mapOf("A" to 3, "B" to 3, "C" to 3),
            first.take(9).groupingBy { it.substringBefore('-') }.eachCount(),
        )
    }

    @Test
    fun `multi-domain ordering returns no candidates for empty or unavailable selection`() {
        val candidates = listOf(ElementSeed("A-1", "A", "A", "A=1"))

        assertTrue(QuizEngine.balancedDomainElementIds(candidates, emptySet(), 1L).isEmpty())
        assertTrue(QuizEngine.balancedDomainElementIds(candidates, setOf("B"), 1L).isEmpty())
    }

    @Test
    fun `calculation catalogue spans every domain and all IBT elements`() {
        val ids = QuizEngine.calculationElementIds

        assertTrue(ids.size >= 30)
        listOf("ACC", "CF", "INV", "FI", "DER", "EQV", "IBT").forEach { domain ->
            assertTrue("Missing calculation coverage for $domain", ids.any { it.startsWith("$domain-") })
        }
        (1..18).forEach { number ->
            val id = "IBT-${number.toString().padStart(2, '0')}"
            assertTrue("Missing $id", id in ids)
        }
        assertNull(QuizEngine.generateCalculation("EQV-999", 1, 1))
    }

    @Test
    fun `every curated calculation has integer answer and passing audit`() {
        for (elementId in QuizEngine.calculationElementIds) {
            for (difficulty in 1..3) {
                for (seed in 0L..31L) {
                    val question = QuizEngine.generateCalculation(elementId, seed, difficulty)
                    assertNotNull("No question for $elementId", question)
                    question!!

                    assertEquals(QuizMode.CALCULATION, question.mode)
                    assertNull(question.choices)
                    assertNotNull("Non-integer answer for $elementId", question.canonicalAnswer.toLongOrNull())
                    assertTrue("Audit failed for $elementId seed=$seed d=$difficulty", question.audit.passed)
                    assertTrue(question.audit.allIntermediatesAreIntegers)
                    assertTrue(question.audit.withinDifficultyCap)
                    assertEquals(listOf(2, 4, 6)[difficulty - 1], question.audit.maxAllowedOperations)
                    assertEquals(question.audit.operationCount, question.audit.weightedOperationScore)
                    assertEquals(question.audit.operations.size, question.audit.rawOperationCount)
                    assertTrue(question.audit.operationCount <= question.audit.maxAllowedOperations)
                    assertTrue(
                        question.audit.maxAbsoluteIntermediate <=
                            question.audit.maxAllowedAbsoluteIntermediate,
                    )
                    assertEquals(
                        question.canonicalAnswer.toLong(),
                        question.audit.operations.last().result,
                    )
                    with(question.explanationSteps) {
                        assertTrue(concept.isNotBlank())
                        assertTrue(formula.isNotBlank())
                        assertTrue(substitution.isNotBlank())
                        assertTrue(answer.isNotBlank())
                        assertTrue(interpretation.isNotBlank())
                    }
                }
            }
        }
    }

    @Test
    fun `same calculation seed is equal while other seeds vary parameters`() {
        val first = QuizEngine.generateCalculation("IBT-05", 77, 3)
        val again = QuizEngine.generateCalculation("IBT-05", 77, 3)
        assertEquals(first, again)
        assertArrayEquals(
            first!!.snapshot.canonicalPayload.toByteArray(Charsets.UTF_8),
            again!!.snapshot.canonicalPayload.toByteArray(Charsets.UTF_8),
        )

        val substantive = (0L..39L).map { seed ->
            QuizEngine.generateCalculation("IBT-05", seed, 3)!!.let { it.prompt to it.canonicalAnswer }
        }.toSet()
        assertTrue(substantive.size >= 8)
    }

    @Test
    fun `numeric grading accepts signs commas unicode minus and an optional unit`() {
        assertEquals("1200", QuizEngine.normalizeNumericAnswer("+1,200"))
        assertEquals("-1200", QuizEngine.normalizeNumericAnswer("−1,200"))
        assertNull(QuizEngine.normalizeNumericAnswer("1,20"))
        assertNull(QuizEngine.normalizeNumericAnswer("12.0"))

        val large = (0L..1_000L).asSequence()
            .map { QuizEngine.generateCalculation("IBT-02", it, 3)!! }
            .first { kotlin.math.abs(it.canonicalAnswer.toLong()) >= 1_000 }
        val expected = large.canonicalAnswer.toLong()
        val grouped = withCommas(expected)
        assertTrue(QuizEngine.gradeInteger(large, grouped).isCorrect)
        assertTrue(QuizEngine.gradeInteger(large, "$grouped ${large.answerUnit}").isCorrect)

        val positive = QuizEngine.generateCalculation("IBT-13", 14, 2)!!
        assertTrue(QuizEngine.gradeInteger(positive, "+${positive.canonicalAnswer}").isCorrect)
        assertFalse(QuizEngine.gradeInteger(positive, "${positive.canonicalAnswer}.0").isCorrect)
        assertFalse(QuizEngine.gradeInteger(positive, "not a number").isCorrect)
    }

    @Test
    fun `multiple choice grading accepts id number and exact label`() {
        val question = QuizEngine.generateConcept(curriculum.first(), curriculum, 123, 2)
        val choices = question.choices!!
        val correctChoice = choices.first { it.id == question.canonicalAnswer }
        val number = choices.indexOf(correctChoice) + 1

        assertTrue(QuizEngine.grade(question, correctChoice.id.lowercase()).isCorrect)
        assertTrue(QuizEngine.grade(question, number.toString()).isCorrect)
        assertTrue(QuizEngine.grade(question, correctChoice.text).isCorrect)
        assertFalse(QuizEngine.grade(question, "Z").isCorrect)
    }

    @Test
    fun `template identity ignores selecting track but preserves oral presentation`() {
        val standard = QuizTemplateIdentity.id(
            "CF-07", QuizMode.CONCEPT, "concept-v2", QuizPresentation.STANDARD
        )
        val oral = QuizTemplateIdentity.id(
            "CF-07", QuizMode.CONCEPT, "concept-v2", QuizPresentation.ORAL
        )

        assertNotEquals(standard, oral)
        assertEquals(
            standard,
            QuizTemplateIdentity.normalizeLegacy(
                "CF-07", QuizMode.CONCEPT, "CF-07-concept-domain-rconcept-v2"
            ).id,
        )
        assertEquals(
            standard,
            QuizTemplateIdentity.normalizeLegacy(
                "CF-07", QuizMode.CONCEPT, "CF-07-concept-weak-rconcept-v2"
            ).id,
        )
        val migratedOral = QuizTemplateIdentity.normalizeLegacy(
            "CF-07", QuizMode.CONCEPT, "CF-07-concept-oral-rconcept-v2"
        )
        assertEquals(oral, migratedOral.id)
        assertEquals(QuizPresentation.ORAL, migratedOral.presentation)
        assertEquals(standard, QuizTemplateIdentity.normalizeLegacy("CF-07", QuizMode.CONCEPT, standard).id)
    }

    private fun withCommas(value: Long): String {
        val raw = value.toString()
        val negative = raw.startsWith('-')
        val digits = if (negative) raw.substring(1) else raw
        val grouped = digits.reversed().chunked(3).joinToString(",").reversed()
        return if (negative) "-$grouped" else grouped
    }
}
