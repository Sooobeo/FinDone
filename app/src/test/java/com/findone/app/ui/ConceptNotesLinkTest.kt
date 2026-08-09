package com.findone.app.ui

import org.junit.Assert.assertEquals
import org.junit.Test

class ConceptNotesLinkTest {
    @Test
    fun `bare http and https URLs are linkified without trailing prose punctuation`() {
        val text = "참고 https://example.com/a(b). 보조 자료 HTTP://docs.example.org/item?q=1, 끝"

        val links = findHttpUrlRanges(text)

        assertEquals(
            listOf(
                "https://example.com/a(b)",
                "HTTP://docs.example.org/item?q=1",
            ),
            links.map { it.url },
        )
        links.forEach { link ->
            assertEquals(link.url, text.substring(link.start, link.endExclusive))
        }
    }

    @Test
    fun `non web schemes and plain prose are not linkified`() {
        val text = "javascript:alert(1) file:///tmp/a mailto:user@example.com example.com"

        assertEquals(emptyList<HttpUrlRange>(), findHttpUrlRanges(text))
    }

    @Test
    fun `web schemes without a host are not linkified`() {
        val text = "https://) http://?query https://#fragment https://user@"

        assertEquals(emptyList<HttpUrlRange>(), findHttpUrlRanges(text))
    }

    @Test
    fun `localhost and bracketed IPv6 authorities are linkified`() {
        val text = "http://localhost:8080/path https://[::1]/guide"

        assertEquals(
            listOf("http://localhost:8080/path", "https://[::1]/guide"),
            findHttpUrlRanges(text).map { it.url },
        )
    }

    @Test
    fun `markdown and code delimiters are not consumed by URL ranges`() {
        val text = "[문서](https://example.com/a(b))와 `https://code.example.org/sample`"

        val links = findHttpUrlRanges(text)

        assertEquals(
            listOf("https://example.com/a(b)", "https://code.example.org/sample"),
            links.map { it.url },
        )
        links.forEach { link ->
            assertEquals(link.url, text.substring(link.start, link.endExclusive))
        }
    }

    @Test
    fun `long unmatched closing delimiter suffix is trimmed in linear time`() {
        val text = "https://example.com/a(" + ")".repeat(10_000)

        assertEquals(
            listOf("https://example.com/a()"),
            findHttpUrlRanges(text).map { it.url },
        )
    }
}
