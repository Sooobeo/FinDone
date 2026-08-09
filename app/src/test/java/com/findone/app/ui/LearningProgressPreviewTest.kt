package com.findone.app.ui

import org.junit.Assert.assertEquals
import org.junit.Test

class LearningProgressPreviewTest {
    @Test
    fun `multiline relation becomes one paragraph without losing symbols`() {
        assertEquals(
            "• CFO = NI + D&A − ΔNWC • EndCash = BeginCash + CFO",
            learningProgressPreview(
                """
                • CFO = NI + D&A − ΔNWC
                • EndCash = BeginCash + CFO
                """.trimIndent(),
            ),
        )
    }

    @Test
    fun `markdown characters remain literal for the plain text preview`() {
        assertEquals(
            "**ROE** = `NI / Equity` and \$x_y\$",
            learningProgressPreview("**ROE** = `NI / Equity`\r\n\tand \$x_y\$"),
        )
    }

    @Test
    fun `blank relation stays blank`() {
        assertEquals("", learningProgressPreview(" \r\n\t "))
    }
}
