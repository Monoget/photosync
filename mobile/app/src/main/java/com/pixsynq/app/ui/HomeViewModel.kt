package com.pixsynq.app.ui

import android.app.Application
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.content.ContextCompat
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.pixsynq.app.backup.AutoBackupWorker
import com.pixsynq.app.backup.BackupEngine
import com.pixsynq.app.backup.BackupRun
import com.pixsynq.app.discovery.DiscoveredPc
import com.pixsynq.app.discovery.PcDiscovery
import com.pixsynq.app.media.GalleryScanner
import com.pixsynq.app.pairing.PairingClient
import com.pixsynq.app.pairing.TrustStore
import com.pixsynq.app.pairing.TrustedPc
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
    val autoBackup: Boolean = false,
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
        private const val AUTO_RUN_MIN_INTERVAL_MS = 15 * 60 * 1000L
    }

    private val discovery = PcDiscovery(application)
    private val trustStore = TrustStore(application)
    private val client = PairingClient()
    private val scanner = GalleryScanner(application)
    private val engine = BackupEngine(application)

    private val pairedPc = MutableStateFlow(trustStore.trustedPc)
    private val connectedPc = MutableStateFlow<DiscoveredPc?>(null)
    private val pairingStatus = MutableStateFlow(PairingStatus.IDLE)
    private val hasPermission = MutableStateFlow(checkPermission())
    private val photoCount = MutableStateFlow<Int?>(null)
    private val backedUpCount = MutableStateFlow<Int?>(null)
    private val autoBackup = MutableStateFlow(trustStore.autoBackup)
    private val backup = MutableStateFlow(BackupProgress())
    private val lastBackupMs = MutableStateFlow(trustStore.lastBackupMs)
    private var lastAutoRunMs = 0L

    val uiState: StateFlow<HomeUiState> =
        combine(
            combine(discovery.searching, discovery.pcs, pairedPc) { s, p, t -> Triple(s, p, t) },
            combine(connectedPc, pairingStatus) { c, ps -> c to ps },
            combine(hasPermission, photoCount, backedUpCount) { hp, pc, bc ->
                Triple(hp, pc, bc)
            },
            combine(backup, lastBackupMs, autoBackup) { b, l, a -> Triple(b, l, a) },
        ) { (searching, pcs, paired), (connected, status), (perm, count, backed),
            (bk, last, auto) ->
            HomeUiState(
                searching = searching,
                pcs = pcs,
                pairedPc = paired,
                connectedPc = connected,
                pairingStatus = status,
                hasPermission = perm,
                photoCount = count,
                backedUpCount = backed,
                autoBackup = auto,
                backup = bk,
                lastBackupMs = last,
            )
        }.stateIn(viewModelScope, SharingStarted.Eagerly, HomeUiState())

    init {
        discovery.start()
        viewModelScope.launch {
            combine(discovery.pcs, pairedPc) { pcs, paired -> pcs to paired }
                .collect { (pcs, paired) ->
                    connectedPc.value = verify(pcs, paired)
                    maybeAutoBackup()
                }
        }
        if (hasPermission.value) refreshGallery()
        refreshBackedUpCount()
        AutoBackupWorker.sync(application, trustStore.autoBackup)
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
        backedUpCount.value = engine.backedUpCount(pcId)
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

    fun setAutoBackup(enabled: Boolean) {
        trustStore.autoBackup = enabled
        autoBackup.value = enabled
        AutoBackupWorker.sync(getApplication(), enabled)
        if (enabled) maybeAutoBackup()
    }

    /** Kick off a backup when the trusted PC appears, at most every 15 min. */
    private fun maybeAutoBackup() {
        if (!autoBackup.value || connectedPc.value == null) return
        if (!hasPermission.value || backup.value.running) return
        val now = System.currentTimeMillis()
        if (now - lastAutoRunMs < AUTO_RUN_MIN_INTERVAL_MS) return
        lastAutoRunMs = now
        backupNow()
    }

    fun backupNow() {
        val pc = connectedPc.value ?: return
        val trusted = pairedPc.value ?: return
        if (backup.value.running || !hasPermission.value) return

        viewModelScope.launch {
            backup.value = BackupProgress(running = true)
            runCatching { photoCount.value = scanner.scan().size }

            val result = engine.run(pc, trusted) { run: BackupRun ->
                backup.value = BackupProgress(
                    running = true,
                    total = run.total,
                    done = run.done,
                    uploaded = run.uploaded,
                    duplicates = run.duplicates,
                    failed = run.failed,
                )
            }

            lastBackupMs.value = trustStore.lastBackupMs
            refreshBackedUpCount()
            backup.value = BackupProgress(
                running = false,
                total = result.total,
                done = result.done,
                uploaded = result.uploaded,
                duplicates = result.duplicates,
                failed = result.failed,
            )
        }
    }

    override fun onCleared() {
        discovery.stop()
    }
}
