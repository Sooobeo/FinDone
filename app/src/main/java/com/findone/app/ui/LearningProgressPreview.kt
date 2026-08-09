package com.findone.app.ui

private val PREVIEW_WHITESPACE = Regex("\\s+")

/**
 * Produces a lightweight, single-paragraph preview for the scrolling study list.
 * Full Markdown and LaTeX rendering is intentionally reserved for the detail screen.
 */
internal fun learningProgressPreview(value: String): String =
    value.trim().replace(PREVIEW_WHITESPACE, " ")
