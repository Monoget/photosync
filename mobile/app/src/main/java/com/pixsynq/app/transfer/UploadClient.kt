package com.pixsynq.app.transfer

import android.content.Context
import com.pixsynq.app.media.PhotoItem
import com.pixsynq.app.net.PinnedHttp
import com.pixsynq.app.pairing.TrustedPc
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import org.json.JSONArray
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

    /**
     * Upload with retry and resume (spec §15): on a network failure the
     * PC is asked how many bytes of the .part file it already has, and
     * the next attempt streams only the remainder.
     */
    suspend fun upload(
        host: String,
        port: Int,
        pc: TrustedPc,
        photo: PhotoItem,
        maxAttempts: Int = 3,
    ): UploadResult = withContext(Dispatchers.IO) {
        val sha256 = try {
            resolver.openInputStream(photo.uri)?.use { hash(it) }
                ?: return@withContext UploadResult.Failed("cannot open ${photo.displayName}")
        } catch (e: SecurityException) {
            return@withContext UploadResult.Failed("permission denied for ${photo.displayName}")
        }
        val size = resolver.openInputStream(photo.uri)?.use { countBytes(it) }
            ?: return@withContext UploadResult.Failed("cannot open ${photo.displayName}")

        var lastError = "network error"
        for (attempt in 1..maxAttempts) {
            if (attempt > 1) delay(1000L * (attempt - 1))
            val offset = if (attempt == 1) 0L else {
                when (val remote = queryOffset(host, port, pc, photo.mediaId)) {
                    null -> 0L
                    -1L -> return@withContext UploadResult.Duplicate  // already complete
                    else -> remote
                }
            }
            try {
                return@withContext attemptUpload(host, port, pc, photo, sha256, size, offset)
            } catch (e: IOException) {
                lastError = e.message ?: "network error"
            } catch (e: SecurityException) {
                return@withContext UploadResult.Failed("permission denied for ${photo.displayName}")
            }
        }
        UploadResult.Failed(lastError)
    }

    private fun attemptUpload(
        host: String,
        port: Int,
        pc: TrustedPc,
        photo: PhotoItem,
        sha256: String,
        size: Long,
        offset: Long,
    ): UploadResult {
        val (conn, _) = PinnedHttp.open(host, port, "/api/v1/upload", pc.fingerprint)
        try {
            conn.requestMethod = "POST"
            conn.doOutput = true
            conn.setFixedLengthStreamingMode(size - offset)
            conn.setRequestProperty("Authorization", "Bearer ${pc.token}")
            conn.setRequestProperty("Content-Type", "application/octet-stream")
            conn.setRequestProperty("X-PixSynq-Media-Id", photo.mediaId.toString())
            conn.setRequestProperty(
                "X-PixSynq-Filename",
                URLEncoder.encode(photo.displayName, "UTF-8"),
            )
            conn.setRequestProperty("X-PixSynq-Sha256", sha256)
            conn.setRequestProperty("X-PixSynq-Date-Taken", photo.dateTakenMs.toString())
            conn.setRequestProperty("X-PixSynq-Total-Size", size.toString())
            conn.setRequestProperty("X-PixSynq-Offset", offset.toString())

            resolver.openInputStream(photo.uri)?.use { input ->
                skipFully(input, offset)
                conn.outputStream.use { out -> input.copyTo(out, CHUNK) }
            } ?: return UploadResult.Failed("photo disappeared")

            return when (conn.responseCode) {
                HttpURLConnection.HTTP_OK -> {
                    val body = JSONObject(conn.inputStream.bufferedReader().readText())
                    when {
                        body.optBoolean("partial") ->
                            throw IOException("transfer incomplete")  // retried by caller
                        body.optBoolean("duplicate") -> UploadResult.Duplicate
                        else -> UploadResult.Uploaded
                    }
                }
                HttpURLConnection.HTTP_CONFLICT ->
                    throw IOException("offset out of sync")  // re-queried on retry
                else -> UploadResult.Failed("HTTP ${conn.responseCode}")
            }
        } finally {
            conn.disconnect()
        }
    }

    /** @return remaining offset, -1 when the PC already has the file, null on error */
    private fun queryOffset(host: String, port: Int, pc: TrustedPc, mediaId: Long): Long? =
        runCatching {
            val (conn, _) = PinnedHttp.open(
                host, port, "/api/v1/upload/offset?media_id=$mediaId", pc.fingerprint
            )
            try {
                conn.setRequestProperty("Authorization", "Bearer ${pc.token}")
                if (conn.responseCode != HttpURLConnection.HTTP_OK) return@runCatching null
                val body = JSONObject(conn.inputStream.bufferedReader().readText())
                if (body.optBoolean("complete")) -1L else body.optLong("offset", 0L)
            } finally {
                conn.disconnect()
            }
        }.getOrNull()

    private fun skipFully(input: InputStream, count: Long) {
        var remaining = count
        while (remaining > 0) {
            val skipped = input.skip(remaining)
            if (skipped <= 0) throw IOException("cannot seek to resume offset")
            remaining -= skipped
        }
    }

    /**
     * Ask the PC which of these media ids still need transferring
     * (spec §13 step 3: compare with Windows backup state).
     */
    suspend fun syncCheck(
        host: String,
        port: Int,
        pc: TrustedPc,
        mediaIds: List<Long>,
    ): Result<Set<Long>> = withContext(Dispatchers.IO) {
        runCatching {
            val (conn, _) = PinnedHttp.open(host, port, "/api/v1/sync/check", pc.fingerprint)
            try {
                conn.requestMethod = "POST"
                conn.doOutput = true
                conn.setRequestProperty("Authorization", "Bearer ${pc.token}")
                conn.setRequestProperty("Content-Type", "application/json")
                val body = JSONObject()
                    .put("media_ids", JSONArray(mediaIds.map { it.toString() }))
                    .toString()
                conn.outputStream.use { it.write(body.toByteArray()) }
                if (conn.responseCode != HttpURLConnection.HTTP_OK) {
                    throw IOException("sync check failed: HTTP ${conn.responseCode}")
                }
                val json = JSONObject(conn.inputStream.bufferedReader().readText())
                val needed = json.getJSONArray("needed")
                buildSet {
                    for (i in 0 until needed.length()) {
                        needed.getString(i).toLongOrNull()?.let { add(it) }
                    }
                }
            } finally {
                conn.disconnect()
            }
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
