package com.findone.app.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.nio.file.Files
import java.security.MessageDigest
import java.sql.DriverManager

class GlossaryAssetTest {
    @Test
    fun `packaged glossary manifest database and local search agree`() {
        val loader = requireNotNull(javaClass.classLoader)
        val databaseBytes = requireNotNull(loader.getResourceAsStream(DATABASE_ASSET)) {
            "$DATABASE_ASSET was not present in merged debug assets"
        }.use { it.readBytes() }
        val manifest = requireNotNull(loader.getResourceAsStream(MANIFEST_ASSET)) {
            "$MANIFEST_ASSET was not present in merged debug assets"
        }.bufferedReader(Charsets.UTF_8).use { it.readText() }
        val expectedBytes = manifest.longValue("byteSize")
        val expectedSha = manifest.stringValue("sha256")
        assertEquals(expectedBytes, databaseBytes.size.toLong())
        assertEquals(expectedSha, sha256(databaseBytes))
        assertFalse(manifest.booleanValue("llmRuntimeUsed"))
        assertEquals(1_649L, manifest.longValue("terms"))

        val path = Files.createTempFile("findone-glossary-", ".sqlite3")
        try {
            Files.write(path, databaseBytes)
            Class.forName("org.sqlite.JDBC")
            DriverManager.getConnection("jdbc:sqlite:${path.toAbsolutePath()}").use { connection ->
                connection.createStatement().use { statement ->
                    statement.executeQuery("PRAGMA integrity_check").use { rows ->
                        assertTrue(rows.next())
                        assertEquals("ok", rows.getString(1))
                    }
                    statement.executeQuery("PRAGMA foreign_key_check").use { rows ->
                        assertFalse(rows.next())
                    }
                    assertEquals(1L, statement.count("PRAGMA user_version"))
                    assertEquals(1_649L, statement.count("SELECT COUNT(*) FROM terms"))
                    assertEquals(1_649L, statement.count("SELECT COUNT(*) FROM glossary_fts"))
                    assertEquals(21L, statement.count("SELECT COUNT(*) FROM categories"))
                    assertEquals(28L, statement.count("SELECT COUNT(*) FROM sources"))
                    assertEquals(
                        0L,
                        statement.count(
                            """SELECT COUNT(*) FROM terms t
                               WHERE NOT EXISTS(
                                   SELECT 1 FROM term_sources s WHERE s.term_id=t.term_id
                               )""".trimIndent()
                        ),
                    )
                    assertEquals(
                        0L,
                        statement.count(
                            "SELECT COUNT(*) FROM sqlite_master WHERE lower(name) LIKE '%admin%'"
                        ),
                    )
                    statement.executeQuery(
                        """SELECT term_id FROM glossary_fts
                           WHERE glossary_fts MATCH '"Discounted"*' LIMIT 1""".trimIndent()
                    ).use { rows ->
                        assertTrue(rows.next())
                        assertEquals("FIN-09-003", rows.getString(1))
                    }
                }
            }
        } finally {
            Files.deleteIfExists(path)
        }
    }

    private fun java.sql.Statement.count(sql: String): Long = executeQuery(sql).use { rows ->
        check(rows.next()) { "No scalar result for $sql" }
        rows.getLong(1)
    }

    private fun String.longValue(key: String): Long =
        requireNotNull(Regex("\\\"$key\\\"\\s*:\\s*(\\d+)").find(this)) {
            "Manifest has no numeric $key"
        }.groupValues[1].toLong()

    private fun String.stringValue(key: String): String =
        requireNotNull(Regex("\\\"$key\\\"\\s*:\\s*\\\"([^\\\"]+)\\\"").find(this)) {
            "Manifest has no string $key"
        }.groupValues[1]

    private fun String.booleanValue(key: String): Boolean =
        requireNotNull(Regex("\\\"$key\\\"\\s*:\\s*(true|false)").find(this)) {
            "Manifest has no boolean $key"
        }.groupValues[1].toBooleanStrict()

    private fun sha256(value: ByteArray): String = MessageDigest.getInstance("SHA-256")
        .digest(value)
        .joinToString("") { "%02x".format(it) }

    private companion object {
        const val DATABASE_ASSET = "glossary.sqlite3"
        const val MANIFEST_ASSET = "glossary-manifest.json"
    }
}
