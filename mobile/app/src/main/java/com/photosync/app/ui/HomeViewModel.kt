package com.photosync.app.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.photosync.app.discovery.DiscoveredPc
import com.photosync.app.discovery.PcDiscovery
import com.photosync.app.pairing.PairingClient
import com.photosync.app.pairing.TrustStore
import com.photosync.app.pairing.TrustedPc
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

enum class PairingStatus { IDLE, IN_PROGRESS, WRONG_CODE, FAILED }

data class HomeUiState(
    val searching: Boolean = false,
    val pcs: List<DiscoveredPc> = emptyList(),
    val pairedPc: TrustedPc? = null,
    val connected: Boolean = false,
    val pairingStatus: PairingStatus = PairingStatus.IDLE,
)

class HomeViewModel(application: Application) : AndroidViewModel(application) {

    private val discovery = PcDiscovery(application)
    private val trustStore = TrustStore(application)
    private val client = PairingClient()

    private val pairedPc = MutableStateFlow(trustStore.trustedPc)
    private val connected = MutableStateFlow(false)
    private val pairingStatus = MutableStateFlow(PairingStatus.IDLE)

    val uiState: StateFlow<HomeUiState> =
        combine(
            discovery.searching, discovery.pcs, pairedPc, connected, pairingStatus,
        ) { searching, pcs, paired, isConnected, status ->
            HomeUiState(
                searching = searching,
                pcs = pcs,
                pairedPc = paired,
                connected = isConnected,
                pairingStatus = status,
            )
        }.stateIn(viewModelScope, SharingStarted.Eagerly, HomeUiState())

    init {
        discovery.start()
        // Whenever the network view changes, re-verify the paired PC.
        viewModelScope.launch {
            combine(discovery.pcs, pairedPc) { pcs, paired -> pcs to paired }
                .collect { (pcs, paired) -> connected.value = verify(pcs, paired) }
        }
    }

    private suspend fun verify(pcs: List<DiscoveredPc>, paired: TrustedPc?): Boolean {
        if (paired == null) return false
        // The paired PC may have a new DHCP address; try any discovered PC —
        // fingerprint pinning ensures we only ever trust the right machine.
        return pcs.any { client.ping(it.host, it.port, paired) }
    }

    fun pair(pc: DiscoveredPc, code: String) {
        pairingStatus.value = PairingStatus.IN_PROGRESS
        viewModelScope.launch {
            client.pair(pc.host, pc.port, code, trustStore.deviceId)
                .onSuccess { trusted ->
                    trustStore.trustedPc = trusted
                    pairedPc.value = trusted
                    pairingStatus.value = PairingStatus.IDLE
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

    override fun onCleared() {
        discovery.stop()
    }
}
