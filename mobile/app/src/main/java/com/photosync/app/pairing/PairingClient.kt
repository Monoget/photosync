package com.photosync.app.pairing

import android.os.Build
import com.photosync.app.net.PinnedHttp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection

/**
 * Pairing and connection checks against the PC's receiver (spec §12).
 *
 * At pairing time no fingerprint is known yet, so the first connection
 * records the PC's certificate fingerprint (trust-on-first-use) while
 * the pairing code proves we reached the PC the user is looking at.
 * Every later connection requires an exact fingerprint match.
 */
class PairingClient {

    /** Pair with the PC; returns the trust record to persist. */
    suspend fun pair(
        host: String,
        port: Int,
        code: String,
        deviceId: String,
        expectedFingerprint: String? = null,
    ): Result<TrustedPc> = withContext(Dispatchers.IO) {
        runCatching {
            val (conn, tm) = PinnedHttp.open(host, port, "/api/v1/pair", expectedFingerprint)
            try {
                conn.requestMethod = "POST"
                conn.doOutput = true
                conn.setRequestProperty("Content-Type", "application/json")
                val body = JSONObject()
                    .put("device_id", deviceId)
                    .put("name", Build.MODEL)
                    .put("platform", "android")
                    .put("code", code.filter { it.isDigit() })
                    .toString()
                conn.outputStream.use { it.write(body.toByteArray()) }

                when (conn.responseCode) {
                    HttpURLConnection.HTTP_OK -> {
                        val json = JSONObject(
                            conn.inputStream.bufferedReader().readText()
                        )
                        TrustedPc(
                            pcId = json.getString("pc_id"),
                            pcName = json.getString("pc_name"),
                            fingerprint = tm.seenFingerprint
                                ?: throw IOException("no certificate seen"),
                            token = json.getString("token"),
                        )
                    }
                    HttpURLConnection.HTTP_FORBIDDEN ->
                        throw WrongCodeException()
                    else -> throw IOException("pairing failed: HTTP ${conn.responseCode}")
                }
            } finally {
                conn.disconnect()
            }
        }
    }

    /** Verify the stored pairing against a PC at host:port. */
    suspend fun ping(host: String, port: Int, pc: TrustedPc): Boolean =
        withContext(Dispatchers.IO) {
            runCatching {
                val (conn, _) = PinnedHttp.open(host, port, "/api/v1/ping", pc.fingerprint)
                try {
                    conn.setRequestProperty("Authorization", "Bearer ${pc.token}")
                    conn.responseCode == HttpURLConnection.HTTP_OK
                } finally {
                    conn.disconnect()
                }
            }.getOrDefault(false)
        }

    class WrongCodeException : IOException("Invalid or expired pairing code")
}
