package com.findone.app.ui

data class LearningSection(
    val title: String,
    val markdown: String,
)

private val learningSectionHeading = Regex("""^###\s+(.+?)\s*$""")

/** Splits generated application notes into independent accordion panels. */
internal fun learningSections(
    markdown: String,
    fallbackTitle: String = "기본 적용",
): List<LearningSection> {
    val source = markdown.trim()
    if (source.isEmpty()) return emptyList()

    val sections = mutableListOf<LearningSection>()
    val preamble = mutableListOf<String>()
    var currentTitle: String? = null
    var currentBody = mutableListOf<String>()

    fun flushCurrent() {
        val title = currentTitle ?: return
        val body = currentBody.joinToString("\n").trim()
        if (body.isNotEmpty()) sections += LearningSection(title, body)
    }

    source.lines().forEach { line ->
        val heading = learningSectionHeading.matchEntire(line.trim())
        if (heading != null) {
            flushCurrent()
            currentTitle = heading.groupValues[1].trim()
            currentBody = mutableListOf()
        } else if (currentTitle == null) {
            preamble += line
        } else {
            currentBody += line
        }
    }
    flushCurrent()

    val preambleText = preamble.joinToString("\n").trim()
    if (sections.isEmpty()) return listOf(LearningSection(fallbackTitle, source))
    return if (preambleText.isEmpty()) {
        sections
    } else {
        listOf(LearningSection(fallbackTitle, preambleText)) + sections
    }
}
