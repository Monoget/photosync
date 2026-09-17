package com.pixsynq.app.media

import android.content.Context
import android.net.Uri
import android.provider.MediaStore
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/** One gallery photo as reported by MediaStore. */
data class PhotoItem(
    val mediaId: Long,
    val uri: Uri,
    val displayName: String,
    val sizeBytes: Long,
    val dateTakenMs: Long,
)

/**
 * Reads gallery photos through MediaStore (spec §10 — never hardcoded
 * filesystem paths). Callers must hold the images permission.
 */
class GalleryScanner(context: Context) {

    private val resolver = context.applicationContext.contentResolver

    suspend fun scan(): List<PhotoItem> = withContext(Dispatchers.IO) {
        val projection = arrayOf(
            MediaStore.Images.Media._ID,
            MediaStore.Images.Media.DISPLAY_NAME,
            MediaStore.Images.Media.SIZE,
            MediaStore.Images.Media.DATE_TAKEN,
            MediaStore.Images.Media.DATE_ADDED,
        )
        val photos = mutableListOf<PhotoItem>()
        resolver.query(
            MediaStore.Images.Media.EXTERNAL_CONTENT_URI,
            projection,
            null,
            null,
            "${MediaStore.Images.Media.DATE_TAKEN} DESC",
        )?.use { cursor ->
            val idCol = cursor.getColumnIndexOrThrow(MediaStore.Images.Media._ID)
            val nameCol = cursor.getColumnIndexOrThrow(MediaStore.Images.Media.DISPLAY_NAME)
            val sizeCol = cursor.getColumnIndexOrThrow(MediaStore.Images.Media.SIZE)
            val takenCol = cursor.getColumnIndexOrThrow(MediaStore.Images.Media.DATE_TAKEN)
            val addedCol = cursor.getColumnIndexOrThrow(MediaStore.Images.Media.DATE_ADDED)
            while (cursor.moveToNext()) {
                val id = cursor.getLong(idCol)
                val taken = cursor.getLong(takenCol).takeIf { it > 0 }
                    ?: (cursor.getLong(addedCol) * 1000)
                photos += PhotoItem(
                    mediaId = id,
                    uri = Uri.withAppendedPath(
                        MediaStore.Images.Media.EXTERNAL_CONTENT_URI, id.toString()
                    ),
                    displayName = cursor.getString(nameCol) ?: "photo_$id.jpg",
                    sizeBytes = cursor.getLong(sizeCol),
                    dateTakenMs = taken,
                )
            }
        }
        photos
    }
}
