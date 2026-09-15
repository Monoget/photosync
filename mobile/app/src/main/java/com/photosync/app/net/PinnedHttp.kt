package com.photosync.app.net

import java.io.IOException
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
 * HTTPS connections authenticated by certificate-fingerprint pinning.
 *
 * With `expected = null` (pairing only) the first certificate seen is
 * recorded (trust-on-first-use); otherwise the connection fails unless
 * the server presents exactly the pinned certificate.
 */
object PinnedHttp {

    class PinningTrustManager(private val expected: String?) : X509TrustManager {
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

    fun open(
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
        conn.readTimeout = 30000
        return conn to tm
    }
}

class FingerprintMismatchException : IOException("Server certificate changed")
