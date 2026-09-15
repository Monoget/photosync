package com.photosync.app.discovery

import android.content.Context
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import android.os.Build
import android.util.Log
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import java.net.ServerSocket
import java.util.concurrent.ConcurrentLinkedQueue
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Local Wi-Fi discovery (spec section 11, Phase 3).
 *
 * Browses for PhotoSync desktops (`_photosync._tcp.`) and registers this
 * phone (`_photosync-m._tcp.`) so the PC can list it before pairing.
 * The registered port is a real bound socket that the transfer client
 * work in later phases replaces.
 */
class PcDiscovery(context: Context) {

    private val nsdManager =
        context.applicationContext.getSystemService(Context.NSD_SERVICE) as NsdManager

    private val _pcs = MutableStateFlow<List<DiscoveredPc>>(emptyList())
    val pcs: StateFlow<List<DiscoveredPc>> = _pcs

    private val _searching = MutableStateFlow(false)
    val searching: StateFlow<Boolean> = _searching

    private var discoveryListener: NsdManager.DiscoveryListener? = null
    private var registrationListener: NsdManager.RegistrationListener? = null
    private var localSocket: ServerSocket? = null

    // NsdManager only supports one resolve at a time on older releases.
    private val resolveQueue = ConcurrentLinkedQueue<NsdServiceInfo>()
    private val resolving = AtomicBoolean(false)

    fun start() {
        if (discoveryListener != null) return
        registerSelf()
        val listener = object : NsdManager.DiscoveryListener {
            override fun onDiscoveryStarted(serviceType: String) {
                _searching.value = true
            }

            override fun onDiscoveryStopped(serviceType: String) {
                _searching.value = false
            }

            override fun onStartDiscoveryFailed(serviceType: String, errorCode: Int) {
                Log.w(TAG, "Start discovery failed: $errorCode")
                _searching.value = false
            }

            override fun onStopDiscoveryFailed(serviceType: String, errorCode: Int) {
                Log.w(TAG, "Stop discovery failed: $errorCode")
            }

            override fun onServiceFound(serviceInfo: NsdServiceInfo) {
                if (serviceInfo.serviceType.startsWith(DESKTOP_TYPE)) {
                    resolveQueue.add(serviceInfo)
                    resolveNext()
                }
            }

            override fun onServiceLost(serviceInfo: NsdServiceInfo) {
                _pcs.value = _pcs.value.filterNot {
                    it.serviceName == serviceInfo.serviceName
                }
            }
        }
        discoveryListener = listener
        nsdManager.discoverServices(DESKTOP_TYPE, NsdManager.PROTOCOL_DNS_SD, listener)
    }

    fun stop() {
        discoveryListener?.let { runCatching { nsdManager.stopServiceDiscovery(it) } }
        discoveryListener = null
        registrationListener?.let { runCatching { nsdManager.unregisterService(it) } }
        registrationListener = null
        runCatching { localSocket?.close() }
        localSocket = null
        _pcs.value = emptyList()
        _searching.value = false
    }

    private fun registerSelf() {
        val socket = ServerSocket(0).also { localSocket = it }
        val info = NsdServiceInfo().apply {
            serviceName = "PhotoSync ${Build.MODEL}".take(63)
            serviceType = MOBILE_TYPE
            port = socket.localPort
            setAttribute("protocol", "1")
            setAttribute("name", Build.MODEL)
            setAttribute("platform", "android")
        }
        val listener = object : NsdManager.RegistrationListener {
            override fun onServiceRegistered(serviceInfo: NsdServiceInfo) {
                Log.i(TAG, "Registered as ${serviceInfo.serviceName}")
            }

            override fun onRegistrationFailed(serviceInfo: NsdServiceInfo, errorCode: Int) {
                Log.w(TAG, "Registration failed: $errorCode")
            }

            override fun onServiceUnregistered(serviceInfo: NsdServiceInfo) {}

            override fun onUnregistrationFailed(serviceInfo: NsdServiceInfo, errorCode: Int) {
                Log.w(TAG, "Unregistration failed: $errorCode")
            }
        }
        registrationListener = listener
        nsdManager.registerService(info, NsdManager.PROTOCOL_DNS_SD, listener)
    }

    private fun resolveNext() {
        if (!resolving.compareAndSet(false, true)) return
        val next = resolveQueue.poll()
        if (next == null) {
            resolving.set(false)
            return
        }
        @Suppress("DEPRECATION") // replacement requires API 34
        nsdManager.resolveService(next, object : NsdManager.ResolveListener {
            override fun onResolveFailed(serviceInfo: NsdServiceInfo, errorCode: Int) {
                Log.w(TAG, "Resolve failed for ${serviceInfo.serviceName}: $errorCode")
                finish()
            }

            override fun onServiceResolved(serviceInfo: NsdServiceInfo) {
                val host = hostAddress(serviceInfo)
                if (host != null) {
                    val pc = DiscoveredPc(
                        serviceName = serviceInfo.serviceName,
                        displayName = txt(serviceInfo, "name")
                            ?: serviceInfo.serviceName,
                        host = host,
                        port = serviceInfo.port,
                    )
                    _pcs.value =
                        _pcs.value.filterNot { it.serviceName == pc.serviceName } + pc
                    Log.i(TAG, "PC on network: ${pc.displayName} ${pc.host}:${pc.port}")
                }
                finish()
            }

            private fun finish() {
                resolving.set(false)
                resolveNext()
            }
        })
    }

    private fun hostAddress(info: NsdServiceInfo): String? =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            info.hostAddresses.firstOrNull()?.hostAddress
        } else {
            @Suppress("DEPRECATION")
            info.host?.hostAddress
        }

    private fun txt(info: NsdServiceInfo, key: String): String? =
        info.attributes[key]?.toString(Charsets.UTF_8)?.takeIf { it.isNotBlank() }

    companion object {
        private const val TAG = "PcDiscovery"
        private const val DESKTOP_TYPE = "_photosync._tcp."
        private const val MOBILE_TYPE = "_photosync-m._tcp."
    }
}
