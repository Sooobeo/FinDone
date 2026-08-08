package com.findone.app.quiz

enum class QuizPresentation { STANDARD, ORAL }

data class NormalizedQuizTemplate(
    val id: String,
    val presentation: QuizPresentation,
)

/** Stable identity for a renderer template, independent of the session that selected it. */
object QuizTemplateIdentity {
    private val legacyTracks = setOf(
        "domain", "weak", "sprint", "concept", "oral", "case", "bookmark",
    )

    fun id(
        elementId: String,
        mode: QuizMode,
        rendererVersion: String,
        presentation: QuizPresentation,
    ): String = buildString {
        append(elementId)
        append('-')
        append(mode.name.lowercase())
        append("-r")
        append(rendererVersion)
        append('-')
        append(presentation.name.lowercase())
    }

    /** Converts the schema-1 `element-mode-sessionTrack-rRenderer` identity when encountered. */
    fun normalizeLegacy(
        elementId: String,
        mode: QuizMode,
        templateId: String,
    ): NormalizedQuizTemplate {
        val prefix = "$elementId-${mode.name.lowercase()}-"
        if (!templateId.startsWith(prefix)) {
            return NormalizedQuizTemplate(templateId, inferPresentation(templateId))
        }
        val suffix = templateId.removePrefix(prefix)
        val canonical = Regex("^r(.+)-(standard|oral)$").matchEntire(suffix)
        if (canonical != null) {
            return NormalizedQuizTemplate(
                id = templateId,
                presentation = if (canonical.groupValues[2] == "oral") QuizPresentation.ORAL else QuizPresentation.STANDARD,
            )
        }
        val legacy = Regex("^([a-z]+)-r(.+)$").matchEntire(suffix)
        if (legacy != null && legacy.groupValues[1] in legacyTracks) {
            val presentation = if (legacy.groupValues[1] == "oral") QuizPresentation.ORAL else QuizPresentation.STANDARD
            return NormalizedQuizTemplate(
                id = id(elementId, mode, legacy.groupValues[2], presentation),
                presentation = presentation,
            )
        }
        return NormalizedQuizTemplate(templateId, inferPresentation(templateId))
    }

    private fun inferPresentation(templateId: String): QuizPresentation =
        if ("-oral-r" in templateId || templateId.endsWith("-oral")) QuizPresentation.ORAL
        else QuizPresentation.STANDARD
}
