package com.findone.app.update

import android.content.ContentResolver
import android.net.Uri
import android.provider.DocumentsContract
import java.io.ByteArrayOutputStream

data class AvailableRelease(
    val folderName: String,
    val apkName: String,
    val apkUri: Uri,
    val versionCode: Long,
    val versionName: String,
    val expectedSha256: String?,
)

sealed interface ReleaseScanResult {
    data object NotConnected : ReleaseScanResult

    data class NoUpdate(
        val rootName: String,
        val releaseFoldersChecked: Int,
    ) : ReleaseScanResult

    data class UpdateAvailable(
        val rootName: String,
        val release: AvailableRelease,
    ) : ReleaseScanResult

    data class PermissionRequired(val message: String) : ReleaseScanResult

    data class Failure(val message: String) : ReleaseScanResult
}

internal class ReleaseTreeScanner(private val resolver: ContentResolver) {
    fun scan(
        treeUri: Uri,
        installedApplicationId: String,
        installedVersionCode: Long,
    ): ReleaseScanResult {
        if (!DocumentsContract.isTreeUri(treeUri)) {
            return ReleaseScanResult.PermissionRequired("저장된 위치가 Android 문서 폴더가 아닙니다. 폴더를 다시 연결해 주세요.")
        }
        val hasReadPermission = resolver.persistedUriPermissions.any { permission ->
            permission.uri == treeUri && permission.isReadPermission
        }
        if (!hasReadPermission) {
            return ReleaseScanResult.PermissionRequired("릴리스 폴더 읽기 권한이 만료되었습니다. 폴더를 다시 연결해 주세요.")
        }

        return try {
            val treeDocumentId = DocumentsContract.getTreeDocumentId(treeUri)
            val rootName = queryDocumentName(treeUri, treeDocumentId)?.take(120) ?: "연결된 릴리스 폴더"
            val rootChildren = queryChildren(treeUri, treeDocumentId, MAX_ROOT_CHILDREN)
            val releaseFolders = rootChildren.filter { entry ->
                entry.isDirectory && ReleaseSelectionPolicy.isReleaseFolderName(entry.displayName)
            }
            if (releaseFolders.size > MAX_RELEASE_FOLDERS) {
                return ReleaseScanResult.Failure(
                    "findone-* 릴리스 폴더가 너무 많습니다. 최근 릴리스만 남긴 뒤 다시 시도해 주세요.",
                )
            }

            val scanned = releaseFolders.mapNotNull { folder ->
                scanReleaseFolder(treeUri, folder)
            }
            val selectedDescriptor = ReleaseSelectionPolicy.selectHighest(
                candidates = scanned.map { it.descriptor },
                installedApplicationId = installedApplicationId,
                installedVersionCode = installedVersionCode,
            )
            val selected = selectedDescriptor?.let { descriptor ->
                scanned.first { it.descriptor == descriptor }
            }
            if (selected == null) {
                ReleaseScanResult.NoUpdate(rootName, releaseFolders.size)
            } else {
                ReleaseScanResult.UpdateAvailable(
                    rootName = rootName,
                    release = AvailableRelease(
                        folderName = selected.descriptor.folderName,
                        apkName = selected.descriptor.apkName,
                        apkUri = selected.apkUri,
                        versionCode = selected.descriptor.manifest.versionCode,
                        versionName = selected.descriptor.manifest.versionName,
                        expectedSha256 = selected.descriptor.manifest.releaseApkSha256,
                    ),
                )
            }
        } catch (_: SecurityException) {
            ReleaseScanResult.PermissionRequired("릴리스 폴더를 읽을 권한이 없습니다. 폴더를 다시 연결해 주세요.")
        } catch (error: ScanLimitException) {
            ReleaseScanResult.Failure(error.message ?: "릴리스 폴더의 항목 수 제한을 초과했습니다.")
        } catch (_: Exception) {
            ReleaseScanResult.Failure("릴리스 폴더를 확인하지 못했습니다. 연결 상태를 확인하고 새로고침해 주세요.")
        }
    }

    private fun scanReleaseFolder(treeUri: Uri, folder: DocumentEntry): ScannedRelease? {
        val children = try {
            queryChildren(treeUri, folder.documentId, MAX_RELEASE_CHILDREN)
        } catch (_: ScanLimitException) {
            return null
        }
        val manifests = children.filter { !it.isDirectory && it.displayName == MANIFEST_NAME }
        val apks = children.filter { !it.isDirectory && ReleaseSelectionPolicy.isReleaseApkName(it.displayName) }
        if (manifests.size != 1 || apks.size != 1) return null

        val manifestDocument = manifests.single()
        if (manifestDocument.size != null && manifestDocument.size > MAX_MANIFEST_BYTES) return null
        val manifestUri = DocumentsContract.buildDocumentUriUsingTree(treeUri, manifestDocument.documentId)
        val manifestJson = readBoundedUtf8(manifestUri, MAX_MANIFEST_BYTES) ?: return null
        val manifest = ReleaseManifestParser.parseOrNull(manifestJson) ?: return null
        val apk = apks.single()
        return ScannedRelease(
            descriptor = ReleaseDescriptor(
                folderName = folder.displayName,
                apkName = apk.displayName,
                manifest = manifest,
            ),
            apkUri = DocumentsContract.buildDocumentUriUsingTree(treeUri, apk.documentId),
        )
    }

    private fun queryDocumentName(treeUri: Uri, documentId: String): String? {
        val documentUri = DocumentsContract.buildDocumentUriUsingTree(treeUri, documentId)
        resolver.query(
            documentUri,
            arrayOf(DocumentsContract.Document.COLUMN_DISPLAY_NAME),
            null,
            null,
            null,
        )?.use { cursor ->
            if (cursor.moveToFirst()) return cursor.getString(0)
        }
        return null
    }

    private fun queryChildren(treeUri: Uri, parentDocumentId: String, limit: Int): List<DocumentEntry> {
        val childrenUri = DocumentsContract.buildChildDocumentsUriUsingTree(treeUri, parentDocumentId)
        val projection = arrayOf(
            DocumentsContract.Document.COLUMN_DOCUMENT_ID,
            DocumentsContract.Document.COLUMN_DISPLAY_NAME,
            DocumentsContract.Document.COLUMN_MIME_TYPE,
            DocumentsContract.Document.COLUMN_SIZE,
        )
        val entries = mutableListOf<DocumentEntry>()
        resolver.query(childrenUri, projection, null, null, null)?.use { cursor ->
            if (cursor.count > limit) throw ScanLimitException("연결한 폴더의 항목이 ${limit}개를 초과합니다.")
            val idIndex = cursor.getColumnIndexOrThrow(DocumentsContract.Document.COLUMN_DOCUMENT_ID)
            val nameIndex = cursor.getColumnIndexOrThrow(DocumentsContract.Document.COLUMN_DISPLAY_NAME)
            val mimeIndex = cursor.getColumnIndexOrThrow(DocumentsContract.Document.COLUMN_MIME_TYPE)
            val sizeIndex = cursor.getColumnIndex(DocumentsContract.Document.COLUMN_SIZE)
            while (cursor.moveToNext()) {
                if (entries.size >= limit) throw ScanLimitException("연결한 폴더의 항목이 ${limit}개를 초과합니다.")
                val documentId = cursor.getString(idIndex) ?: continue
                val displayName = cursor.getString(nameIndex) ?: continue
                val mimeType = cursor.getString(mimeIndex)
                val size = if (sizeIndex < 0 || cursor.isNull(sizeIndex)) null else cursor.getLong(sizeIndex)
                entries += DocumentEntry(
                    documentId = documentId,
                    displayName = displayName,
                    isDirectory = mimeType == DocumentsContract.Document.MIME_TYPE_DIR,
                    size = size,
                )
            }
        } ?: throw IllegalStateException("문서 공급자가 폴더 목록을 반환하지 않았습니다.")
        return entries
    }

    private fun readBoundedUtf8(uri: Uri, maximumBytes: Int): String? {
        val input = resolver.openInputStream(uri) ?: return null
        input.use {
            val output = ByteArrayOutputStream(minOf(maximumBytes, DEFAULT_BUFFER_SIZE))
            val buffer = ByteArray(DEFAULT_BUFFER_SIZE)
            var total = 0
            while (true) {
                val count = it.read(buffer)
                if (count < 0) break
                total += count
                if (total > maximumBytes) return null
                output.write(buffer, 0, count)
            }
            return output.toString(Charsets.UTF_8.name())
        }
    }

    private data class DocumentEntry(
        val documentId: String,
        val displayName: String,
        val isDirectory: Boolean,
        val size: Long?,
    )

    private data class ScannedRelease(
        val descriptor: ReleaseDescriptor,
        val apkUri: Uri,
    )

    private class ScanLimitException(message: String) : Exception(message)

    companion object {
        private const val MANIFEST_NAME = "release-manifest.json"
        private const val MAX_ROOT_CHILDREN = 200
        private const val MAX_RELEASE_FOLDERS = 40
        private const val MAX_RELEASE_CHILDREN = 16
        private const val MAX_MANIFEST_BYTES = 64 * 1024
    }
}
