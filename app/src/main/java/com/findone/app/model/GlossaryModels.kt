package com.findone.app.model

data class GlossaryManifest(
    val manifestVersion: Int,
    val schemaVersion: Int,
    val glossaryDbVersion: Int,
    val llmRuntimeUsed: Boolean,
    val databaseAsset: String,
    val sha256: String,
    val byteSize: Long,
    val inventorySha256: String,
    val catalogSha256: String,
    val rowCounts: Map<String, Int>,
)

data class GlossaryCategory(
    val id: String,
    val name: String,
    val displayOrder: Int,
    val termCount: Int,
)

data class GlossaryTermSummary(
    val id: String,
    val categoryId: String,
    val categoryName: String,
    val canonicalNameEn: String,
    val canonicalNameKo: String,
    val aliases: List<String>,
    val oneLineDefinitionKo: String,
)

data class GlossaryRelatedTerm(
    val id: String,
    val canonicalNameEn: String,
    val canonicalNameKo: String,
)

data class GlossaryTerm(
    val id: String,
    val categoryId: String,
    val categoryName: String,
    val canonicalNameEn: String,
    val canonicalNameKo: String,
    val aliases: List<String>,
    val conceptType: String,
    val oneLineDefinitionKo: String,
    val coreDefinitionKo: String,
    val practicalContextKo: String,
    val whyItMattersKo: String,
    val exampleKo: String,
    val limitationsKo: List<String>,
    val formulaLatex: String,
    val formulaNotesKo: String,
    val jurisdictions: List<String>,
    val asOfDate: String,
    val reviewStatus: String,
    val reviewFlags: List<String>,
    val relatedTerms: List<GlossaryRelatedTerm>,
)
