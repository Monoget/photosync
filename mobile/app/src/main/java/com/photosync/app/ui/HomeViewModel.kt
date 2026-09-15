package com.photosync.app.ui

import android.app.Application
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.content.ContextCompat
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.photosync.app.backup.BackupStateDb
import com.photosync.app.discovery.DiscoveredPc
import com.photosync.app.discovery.PcDiscovery
import com.photosync.app.media.GalleryScanner
import com.photosync.app.pairing.PairingClient
import com.photosync.app.pairing.TrustStore
import com.photosync.app.pairing.TrustedPc
import com.photosync.app.transfer.UploadClient
import com.photosync.app.transfer.UploadResult
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

enum class PairingStatus { IDLE, IN_PROGRESS, WRONG_CODE, FAILED }

data class BackupProgress(
    val running: Boolean = false,
    val total: Int = 0,
    val done: Int = 0,
    val uploaded: Int = 0,
    val duplicates: Int = 0,
    val failed: Int = 0,
)

data class HomeUiState(
    val searching: Boolean = false,
    val pcs: List<DiscoveredPc> = emptyList(),
    val pairedPc: TrustedPc? = null,
    val connectedPc: DiscoveredPc? = null,
    val pairingStatus: PairingStatus = PairingStatus.IDLE,
    val hasPermission: Boolean = false,
    val photoCount: Int? = null,
    val backedUpCount: Int? = null,
    val backup: BackupProgress = BackupProgress(),
    val lastBackupMs: Long? = null,
) {
    val connected: Boolean get() = connectedPc != null
}

class HomeViewModel(application: Application) : AndroidViewModel(application) {

    companion object {
        val REQUIRED_PERMISSION: String =
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                android.Manifest.permission.READ_MEDIA_IMAGES
            } else {
                android.Manifest.permission.READ_EXTERNAL_STORAGE
            }
    }

    private val discovery = PcDiscovery(application)
    private val trustStore = TrustStore(application)
    private val client = PairingClient()
    private val scanner = GalleryScanner(application)
    private val uploader = UploadClient(application)
    private val stateDb = BackupStateDb(application)

    private val pairedPc = MutableStateFlow(trustStore.trustedPc)
    private val connectedPc = MutableStateFlow<DiscoveredPc?>(null)
    private val pairingStatus = MutableStateFlow(PairingStatus.IDLE)
    private val hasPermission = MutableStateFlow(checkPermission())
    private val photoCount = MutableStateFlow<Int?>(null)
    private val backedUpCount = MutableStateFlow<Int?>(null)
    private val backup = MutableStateFlow(BackupProgress())
    private val lastBackupMs = MutableStateFlow(trustStore.lastBackupMs)

    val uiState: StateFlow<HomeUiState> =
        combine(
            combine(discovery.searching, discovery.pcs, pairedPc) { s, p, t -> Triple(s, p, t) },
            combine(connectedPc, pairingStatus) { c, ps -> c to ps },
            combine(hasPermission, photoCount, backedUpCount) { hp, pc, bc ->
                Triple(hp, pc, bc)
            },
            combine(backup, lastBackupMs) { b, l -> b to l },
        ) { (searching, pcs, paired), (connected, status), (perm, count, backed), (bk, last) ->
            HomeUiState(
                searching = searching,
                pcs = pcs,
                pairedPc = paired,
                connectedPc = connected,
                pairingStatus = status,
                hasPermission = perm,
                photoCount = count,
                backedUpCount = backed,
                backup = bk,
                lastBackupMs = last,
            )
        }.stateIn(viewModelScope, SharingStarted.Eagerly, HomeUiState())

    init {
        discovery.start()
        viewModelScope.launch {
            combine(discovery.pcs, pairedPc) { pcs, paired -> pcs to paired }
                .collect { (pcs, paired) -> connectedPc.value = verify(pcs, paired) }
        }
        if (hasPermission.value) refreshGallery()
        refreshBackedUpCount()
    }

    private fun checkPermission(): Boolean =
        ContextCompat.checkSelfPermission(
            getApplication(), REQUIRED_PERMISSION
        ) == PackageManager.PERMISSION_GRANTED

    fun onPermissionResult() {
        hasPermission.value = checkPermission()
        if (hasPermission.value) refreshGallery()
    }

    private fun refreshGallery() {
        viewModelScope.launch {
            runCatching { photoCount.value = scanner.scan().size }
            refreshBackedUpCount()
        }
    }

    private fun refreshBackedUpCount() {
        val pcId = pairedPc.value?.pcId ?: return
        backedUpCount.value = stateDb.count(pcId)
    }

    private suspend fun verify(pcs: List<DiscoveredPc>, paired: TrustedPc?): DiscoveredPc? {
        if (paired == null) return null
        // The paired PC may have a new DHCP address; try any discovered PC —
        // fingerprint pinning ensures we only ever trust the right machine.
        return pcs.firstOrNull { client.ping(it.host, it.port, paired) }
    }

    fun pair(pc: DiscoveredPc, code: String) {
        pairingStatus.value = PairingStatus.IN_PROGRESS
        viewModelScope.launch {
            client.pair(pc.host, pc.port, code, trustStore.deviceId)
                .onSuccess { trusted ->
                    trustStore.trustedPc = trusted
                    pairedPc.value = trusted
                    pairingStatus.value = PairingStatus.IDLE
                    refreshBackedUpCount()
                }
                .onFailure { error ->
                    pairingStatus.value =
                        if (error is PairingClient.WrongCodeException) {
                            PairingStatus.WRONG_CODE
                        } else {
                            PairingStatus.FAILED
                        }
                }
        }
    }

    fun dismissPairingError() {
        pairingStatus.value = PairingStatus.IDLE
    }

    fun backupNow() {
        val pc = connectedPc.value ?: return
        val trusted = pairedPc.value ?: return
        if (backup.value.running || !hasPermission.value) return

        viewModelScope.launch {
            backup.value = BackupProgress(running = true)
            val photos = runCatching { scanner.scan() }.getOrDefault(emptyList())
            photoCount.value = photos.size

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
            refreshBackedUpCount()

            backup.value = backup.value.copy(total = candidates.size)
            var uploaded = 0
            var duplicates = 0
            var failed = 0
            for ((index, photo) in candidates.withIndex()) {
                when (uploader.upload(pc.host, pc.port, trusted, photo)) {
                    is UploadResult.Uploaded -> {
                        uploaded++
                        stateDb.markBackedUp(trusted.pcId, listOf(photo.mediaId))
                    }
                    is UploadResult.Duplicate -> {
                        duplicates++
                        stateDb.markBackedUp(trusted.pcId, listOf(photo.mediaId))
                    }
                    is UploadResult.Failed -> failed++  // one bad file never stops the run
                }
                backup.value = backup.value.copy(
                    done = index + 1,
                    uploaded = uploaded,
                    duplicates = duplicates,
                    failed = failed,
                )
            }

            if (failed == 0 || uploaded > 0 || duplicates > 0) {
                val now = System.currentTimeMillis()
                trustStore.lastBackupMs = now
                lastBackupMs.value = now
            }
            refreshBackedUpCount()
            backup.value = backup.value.copy(running = false)
        }
    }

    override fun onCleared() {
        discovery.stop()
    }
}
