package com.photosync.app.transfer

import android.content.Context
import com.photosync.app.media.PhotoItem
import com.photosync.app.net.PinnedHttp
import com.photosync.app.pairing.TrustedPc
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.IOException
import java.io.InputStream
import java.net.HttpURLConnection
import java.net.URLEncoder
import java.security.MessageDigest

sealed class UploadResult {
    data object Uploaded : UploadResult()
    data object Duplicate : UploadResult()
    data class Failed(val reason: String) : UploadResult()
}

/**
 * Streams one photo to the PC's /api/v1/upload endpoint over pinned TLS.
 *
 * The SHA-256 is computed in a first pass so the server can verify the
 * transfer before moving the file out of its .part state (spec §15).
 */
class UploadClient(context: Context) {

    private val resolver = context.applicationContext.contentResolver

    suspend fun upload(
        host: String,
        port: Int,
        pc: TrustedPc,
        photo: PhotoItem,
    ): UploadResult = withContext(Dispatchers.IO) {
        try {
            val sha256 = resolver.openInputStream(photo.uri)?.use { hash(it) }
                ?: return@withContext UploadResult.Failed("cannot open ${photo.displayName}")
            val size = resolver.openInputStream(photo.uri)?.use { countBytes(it) }
                ?: return@withContext UploadResult.Failed("cannot open ${photo.displayName}")

            val (conn, _) = PinnedHttp.open(host, port, "/api/v1/upload", pc.fingerprint)
            try {
                conn.requestMethod = "POST"
                conn.doOutput = true
                conn.setFixedLengthStreamingMode(size)
                conn.setRequestProperty("Authorization", "Bearer ${pc.token}")
                conn.setRequestProperty("Content-Type", "application/octet-stream")
                conn.setRequestProperty("X-PhotoSync-Media-Id", photo.mediaId.toString())
                conn.setRequestProperty(
                    "X-PhotoSync-Filename",
                    URLEncoder.encode(photo.displayName, "UTF-8"),
                )
                conn.setRequestProperty("X-PhotoSync-Sha256", sha256)
                conn.setRequestProperty("X-PhotoSync-Date-Taken", photo.dateTakenMs.toString())

                resolver.openInputStream(photo.uri)?.use { input ->
                    conn.outputStream.use { out -> input.copyTo(out, CHUNK) }
                } ?: return@withContext UploadResult.Failed("photo disappeared")

                when (conn.responseCode) {
                    HttpURLConnection.HTTP_OK -> {
                        val body = JSONObject(conn.inputStream.bufferedReader().readText())
                        if (body.optBoolean("duplicate")) UploadResult.Duplicate
                        else UploadResult.Uploaded
                    }
                    else -> UploadResult.Failed("HTTP ${conn.responseCode}")
                }
            } finally {
                conn.disconnect()
            }
        } catch (e: IOException) {
            UploadResult.Failed(e.message ?: "network error")
        } catch (e: SecurityException) {
            UploadResult.Failed("permission denied for ${photo.displayName}")
        }
    }

    private fun hash(input: InputStream): String {
        val digest = MessageDigest.getInstance("SHA-256")
        val buffer = ByteArray(CHUNK)
        while (true) {
            val read = input.read(buffer)
            if (read < 0) break
            digest.update(buffer, 0, read)
        }
        return digest.digest().joinToString("") { "%02x".format(it) }
    }

    private fun countBytes(input: InputStream): Long {
        // MediaStore SIZE can be stale; measure the real stream length.
        var total = 0L
        val buffer = ByteArray(CHUNK)
        while (true) {
            val read = input.read(buffer)
            if (read < 0) break
            total += read
        }
        return total
    }

    private companion object {
        const val CHUNK = 256 * 1024
    }
}
