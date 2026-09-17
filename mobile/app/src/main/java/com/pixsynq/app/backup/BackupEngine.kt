package com.pixsynq.app.backup

import android.content.Context
import com.pixsynq.app.discovery.DiscoveredPc
import com.pixsynq.app.media.GalleryScanner
import com.pixsynq.app.pairing.TrustStore
import com.pixsynq.app.pairing.TrustedPc
import com.pixsynq.app.transfer.UploadClient
import com.pixsynq.app.transfer.UploadResult

data class BackupRun(
    val total: Int = 0,
    val done: Int = 0,
    val uploaded: Int = 0,
    val duplicates: Int = 0,
    val failed: Int = 0,
)

/**
 * The incremental backup pipeline (spec §13), shared by the in-app
 * "Backup Now" button and the background worker:
 * scan → skip locally-known → reconcile with the PC → upload the rest.
 */
class BackupEngine(context: Context) {

    private val appContext = context.applicationContext
    private val scanner = GalleryScanner(appContext)
    private val uploader = UploadClient(appContext)
    private val stateDb = BackupStateDb(appContext)
    private val trustStore = TrustStore(appContext)

    fun backedUpCount(pcId: String): Int = stateDb.count(pcId)

    suspend fun pendingCount(pcId: String): Int {
        val photos = runCatching { scanner.scan() }.getOrDefault(emptyList())
        val known = stateDb.backedUpIds(pcId)
        return photos.count { it.mediaId !in known }
    }

    suspend fun run(
        pc: DiscoveredPc,
        trusted: TrustedPc,
        onProgress: (BackupRun) -> Unit = {},
    ): BackupRun {
        val photos = runCatching { scanner.scan() }.getOrDefault(emptyList())

        // 1. Skip everything this phone already knows is backed up.
        val known = stateDb.backedUpIds(trusted.pcId)
        var candidates = photos.filter { it.mediaId !in known }

        // 2. Reconcile the rest with the PC's backup state in batches;
        //    ids the PC already has are marked locally and skipped.
        //    If a check fails we fall back to uploading (the PC dedups).
        val needed = mutableSetOf<Long>()
        var checksFailed = false
        for (batch in candidates.chunked(500)) {
            uploader.syncCheck(pc.host, pc.port, trusted, batch.map { it.mediaId })
                .onSuccess { neededIds ->
                    needed += neededIds
                    stateDb.markBackedUp(
                        trusted.pcId,
                        batch.map { it.mediaId }.filter { it !in neededIds },
                    )
                }
                .onFailure {
                    checksFailed = true
                    needed += batch.map { it.mediaId }
                }
        }
        if (!checksFailed) {
            candidates = candidates.filter { it.mediaId in needed }
        }

        // 3. Upload what remains; one bad file never stops the run.
        var progress = BackupRun(total = candidates.size)
        onProgress(progress)
        for (photo in candidates) {
            progress = when (uploader.upload(pc.host, pc.port, trusted, photo)) {
                is UploadResult.Uploaded -> {
                    stateDb.markBackedUp(trusted.pcId, listOf(photo.mediaId))
                    progress.copy(uploaded = progress.uploaded + 1)
                }
                is UploadResult.Duplicate -> {
                    stateDb.markBackedUp(trusted.pcId, listOf(photo.mediaId))
                    progress.copy(duplicates = progress.duplicates + 1)
                }
                is UploadResult.Failed -> progress.copy(failed = progress.failed + 1)
            }.let { it.copy(done = it.done + 1) }
            onProgress(progress)
        }

        if (progress.failed == 0 || progress.uploaded > 0 || progress.duplicates > 0) {
            trustStore.lastBackupMs = System.currentTimeMillis()
        }
        return progress
    }
}
