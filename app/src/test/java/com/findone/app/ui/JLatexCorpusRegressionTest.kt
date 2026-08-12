package com.findone.app.ui

import com.findone.app.quiz.QuizEngine
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.scilab.forge.jlatexmath.TeXConstants
import org.scilab.forge.jlatexmath.TeXFormula
import java.nio.file.Files
import java.nio.file.Path
import java.sql.Connection
import java.sql.DriverManager

class JLatexCorpusRegressionTest {
    @Test
    fun `packaged content and deterministic calculation quiz math builds TeX icons`() {
        val database = copyPackagedDatabaseToTemp(DATABASE_ASSET, "findone-content-")
        val glossaryDatabase = copyPackagedDatabaseToTemp(
            GLOSSARY_DATABASE_ASSET,
            "findone-glossary-",
        )
        try {
            Class.forName("org.sqlite.JDBC")
            DriverManager.getConnection("jdbc:sqlite:${database.toAbsolutePath()}").use { connection ->
                val content = readContentMath(connection)
                val quiz = deterministicCalculationQuizMath()
                val glossary = DriverManager.getConnection(
                    "jdbc:sqlite:${glossaryDatabase.toAbsolutePath()}"
                ).use(::readGlossaryMath)

                assertEquals("Every packaged Markdown field must be scanned", 135 * MARKDOWN_COLUMNS.size, content.fieldCount)
                assertTrue("The packaged content corpus unexpectedly contains no TeX", content.cases.isNotEmpty())
                assertTrue("The deterministic calculation corpus unexpectedly contains no TeX", quiz.isNotEmpty())
                assertEquals("Every glossary formula must be rendered", 421, glossary.size)
                assertEveryPayloadBuildsIcon(content.cases + quiz + glossary)
            }
        } finally {
            Files.deleteIfExists(database)
            Files.deleteIfExists(glossaryDatabase)
        }
    }

    private fun readGlossaryMath(connection: Connection): List<MathCase> = buildList {
        connection.createStatement().use { statement ->
            statement.executeQuery(
                """SELECT term_id, formula_latex FROM terms
                   WHERE length(trim(formula_latex)) > 0 ORDER BY term_id""".trimIndent()
            ).use { rows ->
                while (rows.next()) {
                    val termId = rows.getString(1)
                    val tex = rows.getString(2).trim()
                    require('$' !in tex && '`' !in tex) {
                        "Glossary formula contains its own Markdown delimiter: $termId"
                    }
                    add(MathCase("glossary:$termId", tex))
                }
            }
        }
    }

    private fun readContentMath(connection: Connection): ContentCorpus {
        val cases = mutableListOf<MathCase>()
        var fieldCount = 0
        MARKDOWN_COLUMNS.forEach { column ->
            connection.createStatement().use { statement ->
                statement.executeQuery(
                    "SELECT ${column.idColumn}, ${column.markdownColumn} " +
                        "FROM ${column.table} ORDER BY ${column.idColumn}"
                ).use { rows ->
                    while (rows.next()) {
                        fieldCount += 1
                        val sourceId = "content:${column.table}.${column.markdownColumn}:${rows.getString(1)}"
                        val markdown = rows.getString(2).orEmpty()
                        requireNoCodeFallback(sourceId, markdown)
                        cases += extractMath(sourceId, markdown)
                    }
                }
            }
        }
        return ContentCorpus(fieldCount, cases)
    }

    private fun deterministicCalculationQuizMath(): List<MathCase> = buildList {
        QuizEngine.calculationElementIds.sorted().forEachIndexed { elementIndex, elementId ->
            (1..3).forEach { difficulty ->
                val seed = QUIZ_SEED + elementIndex * 1_009L + difficulty
                val question = requireNotNull(
                    QuizEngine.generateCalculation(elementId, seed, difficulty)
                ) { "Calculation catalogue returned null for $elementId at difficulty $difficulty" }
                val sources = linkedMapOf(
                    "prompt" to question.prompt,
                    "formula" to safeMathMarkdown(question.explanationSteps.formula),
                    "substitution" to safeMathMarkdown(question.explanationSteps.substitution),
                    "answer" to question.explanationSteps.answer,
                    "interpretation" to question.explanationSteps.interpretation,
                )
                sources.forEach { (field, markdown) ->
                    val sourceId = "quiz:$elementId:d$difficulty:$field"
                    if (field == "formula" || field == "substitution") {
                        requireNoCodeFallback(sourceId, markdown)
                    }
                    addAll(extractMath(sourceId, markdown))
                }
                question.audit.operations.forEachIndexed { operationIndex, operation ->
                    val markdown = safeMathMarkdown("${operation.expression} = ${operation.result}")
                    val sourceId =
                        "quiz:$elementId:d$difficulty:audit-operation-${operationIndex + 1}"
                    requireNoCodeFallback(sourceId, markdown)
                    addAll(
                        extractMath(
                            sourceId,
                            markdown,
                        )
                    )
                }
            }
        }
    }

    private fun assertEveryPayloadBuildsIcon(cases: List<MathCase>) {
        val failures = mutableListOf<String>()
        cases.groupBy(MathCase::tex).forEach { (tex, occurrences) ->
            runCatching {
                val icon = TeXFormula(tex).createTeXIcon(TeXConstants.STYLE_DISPLAY, 48F)
                check(icon.iconWidth > 0 && icon.iconHeight > 0) {
                    "non-positive icon size ${icon.iconWidth}x${icon.iconHeight}"
                }
            }.onFailure { error ->
                val ids = occurrences.joinToString { it.sourceId }
                failures += "$ids -> ${error.javaClass.simpleName}: ${error.message}; TeX=$tex"
            }
        }

        assertTrue(
            buildString {
                append("Bundled jlatexmath 0.2.0 failed ")
                append(failures.size)
                append(" of ")
                append(cases.map(MathCase::tex).distinct().size)
                append(" unique TeX payloads")
                if (failures.isNotEmpty()) {
                    append(":\n")
                    append(failures.take(MAX_FAILURES_IN_MESSAGE).joinToString("\n"))
                    if (failures.size > MAX_FAILURES_IN_MESSAGE) {
                        append("\n... and ${failures.size - MAX_FAILURES_IN_MESSAGE} more")
                    }
                }
            },
            failures.isEmpty(),
        )
    }

    private fun requireNoCodeFallback(sourceId: String, markdown: String) {
        require('`' !in markdown) {
            "Formula-shaped content fell back to a Markdown code span in $sourceId: $markdown"
        }
    }

    private fun extractMath(sourceId: String, markdown: String): List<MathCase> = buildList {
        var cursor = 0
        var occurrence = 0
        while (true) {
            val start = markdown.indexOf(MATH_DELIMITER, cursor)
            if (start < 0) break
            val end = markdown.indexOf(MATH_DELIMITER, start + MATH_DELIMITER.length)
            require(end >= 0) { "Unclosed TeX delimiter in $sourceId" }
            val tex = markdown.substring(start + MATH_DELIMITER.length, end).trim()
            require(tex.isNotEmpty()) { "Empty TeX payload in $sourceId" }
            occurrence += 1
            add(MathCase("$sourceId#$occurrence", tex))
            cursor = end + MATH_DELIMITER.length
        }
    }

    private fun copyPackagedDatabaseToTemp(asset: String, prefix: String): Path {
        val classLoader = requireNotNull(javaClass.classLoader)
        val stream = requireNotNull(classLoader.getResourceAsStream(asset)) {
            "$asset was not present in merged debug assets"
        }
        return Files.createTempFile(prefix, ".sqlite3").also { target ->
            stream.use { input ->
                Files.newOutputStream(target).use { output -> input.copyTo(output) }
            }
        }
    }

    private data class MarkdownColumn(
        val table: String,
        val idColumn: String,
        val markdownColumn: String,
    )

    private data class MathCase(val sourceId: String, val tex: String)
    private data class ContentCorpus(val fieldCount: Int, val cases: List<MathCase>)

    private companion object {
        const val DATABASE_ASSET = "content.sqlite3"
        const val GLOSSARY_DATABASE_ASSET = "glossary.sqlite3"
        const val MATH_DELIMITER = "\u0024\u0024"
        const val QUIZ_SEED = 0x5F37_59DFL
        const val MAX_FAILURES_IN_MESSAGE = 40

        val MARKDOWN_COLUMNS = listOf(
            MarkdownColumn("concept_cards", "concept_id", "definition"),
            MarkdownColumn("concept_cards", "concept_id", "intuition"),
            MarkdownColumn("concept_cards", "concept_id", "scope_notes"),
            MarkdownColumn("formula_cards", "formula_id", "expression"),
            MarkdownColumn("formula_cards", "formula_id", "assumptions"),
            MarkdownColumn("formula_cards", "formula_id", "notes"),
        )
    }
}
