package com.photosync.app.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.photosync.app.discovery.DiscoveredPc
import com.photosync.app.discovery.PcDiscovery
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn

data class HomeUiState(
    val searching: Boolean = false,
    val pcs: List<DiscoveredPc> = emptyList(),
)

class HomeViewModel(application: Application) : AndroidViewModel(application) {

    private val discovery = PcDiscovery(application)

    val uiState: StateFlow<HomeUiState> =
        combine(discovery.searching, discovery.pcs) { searching, pcs ->
            HomeUiState(searching = searching, pcs = pcs)
        }.stateIn(viewModelScope, SharingStarted.Eagerly, HomeUiState())

    init {
        discovery.start()
    }

    override fun onCleared() {
        discovery.stop()
    }
}
