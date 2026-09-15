package com.photosync.app.pairing

import android.os.Build
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest
import java.security.SecureRandom
import java.security.cert.CertificateException
import java.security.cert.X509Certificate
import javax.net.ssl.HostnameVerifier
import javax.net.ssl.HttpsURLConnection
import javax.net.ssl.SSLContext
import javax.net.ssl.X509TrustManager

/**
 * HTTPS client for the PC's receiver, authenticated by certificate
 * fingerprint pinning (spec §12).
 *
 * At pairing time no fingerprint is known yet, so the first connection
 * records the PC's certificate fingerprint (trust-on-first-use) while
 * the pairing code proves we reached the PC the user is looking at.
 * Every later connection requires an exact fingerprint match.
 */
class PairingClient {

    class FingerprintMismatchException : IOException("Server certificate changed")

    private class PinningTrustManager(private val expected: String?) : X509TrustManager {
        var seenFingerprint: String? = null

        override fun checkClientTrusted(chain: Array<X509Certificate>, authType: String) =
            throw CertificateException("client certs not supported")

        override fun checkServerTrusted(chain: Array<X509Certificate>, authType: String) {
            val fp = MessageDigest.getInstance("SHA-256")
                .digest(chain[0].encoded)
                .joinToString("") { "%02x".format(it) }
            seenFingerprint = fp
            if (expected != null && !fp.equals(expected, ignoreCase = true)) {
                throw CertificateException("certificate fingerprint mismatch")
            }
        }

        override fun getAcceptedIssuers(): Array<X509Certificate> = emptyArray()
    }

    private fun open(
        host: String,
        port: Int,
        path: String,
        pinned: String?,
    ): Pair<HttpsURLConnection, PinningTrustManager> {
        val tm = PinningTrustManager(pinned)
        val sslContext = SSLContext.getInstance("TLS").apply {
            init(null, arrayOf(tm), SecureRandom())
        }
        val conn = URL("https://$host:$port$path").openConnection() as HttpsURLConnection
        conn.sslSocketFactory = sslContext.socketFactory
        // Identity is proven by the pinned fingerprint, not the hostname.
        conn.hostnameVerifier = HostnameVerifier { _, _ -> true }
        conn.connectTimeout = 8000
        conn.readTimeout = 8000
        return conn to tm
    }

    /** Pair with the PC; returns the trust record to persist. */
    suspend fun pair(
        host: String,
        port: Int,
        code: String,
        deviceId: String,
        expectedFingerprint: String? = null,
    ): Result<TrustedPc> = withContext(Dispatchers.IO) {
        runCatching {
            val (conn, tm) = open(host, port, "/api/v1/pair", expectedFingerprint)
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
                val (conn, _) = open(host, port, "/api/v1/ping", pc.fingerprint)
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
