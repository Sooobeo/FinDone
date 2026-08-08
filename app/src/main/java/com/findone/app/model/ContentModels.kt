package com.findone.app.model

data class Domain(
    val id: String,
    val name: String,
    val description: String,
    val count: Int,
    val colorToken: String,
)

data class ContentElement(
    val id: String,
    val domainId: String,
    val title: String,
    val coreRelation: String,
    val scope: String,
    val sourceLabel: String,
    val sourceLocator: String,
    val specSectionLocator: String,
)

data class ContentManifest(
    val manifestVersion: Int,
    val schemaVersion: Int,
    val contentDbVersion: Int,
    val databaseAsset: String,
    val sha256: String,
    val byteSize: Long,
    val sourceSpec: String,
    val sourceSha256: String,
    val rowCounts: Map<String, Int>,
    val domainElementCounts: Map<String, Int>,
)
