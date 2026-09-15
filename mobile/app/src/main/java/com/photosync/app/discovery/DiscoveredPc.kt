package com.photosync.app.discovery

/** A PhotoSync desktop seen on the local network (not necessarily paired). */
data class DiscoveredPc(
    val serviceName: String,
    val displayName: String,
    val host: String,
    val port: Int,
)
