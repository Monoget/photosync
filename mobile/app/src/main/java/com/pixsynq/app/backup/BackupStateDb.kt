package com.pixsynq.app.backup

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper

/**
 * Local record of which gallery photos are already backed up to which PC
 * (spec §13: compare with backup state, transfer only new photos).
 */
class BackupStateDb(context: Context) :
    SQLiteOpenHelper(context.applicationContext, "backup_state.db", null, 1) {

    override fun onCreate(db: SQLiteDatabase) {
        db.execSQL(
            """
            CREATE TABLE backed_up (
                media_id INTEGER NOT NULL,
                pc_id TEXT NOT NULL,
                uploaded_at INTEGER NOT NULL,
                PRIMARY KEY (media_id, pc_id)
            )
            """.trimIndent()
        )
    }

    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) = Unit

    fun backedUpIds(pcId: String): Set<Long> {
        val ids = mutableSetOf<Long>()
        readableDatabase.rawQuery(
            "SELECT media_id FROM backed_up WHERE pc_id = ?", arrayOf(pcId)
        ).use { cursor ->
            while (cursor.moveToNext()) ids += cursor.getLong(0)
        }
        return ids
    }

    fun markBackedUp(pcId: String, mediaIds: Collection<Long>) {
        if (mediaIds.isEmpty()) return
        val now = System.currentTimeMillis()
        val db = writableDatabase
        db.beginTransaction()
        try {
            for (id in mediaIds) {
                db.insertWithOnConflict(
                    "backed_up",
                    null,
                    ContentValues().apply {
                        put("media_id", id)
                        put("pc_id", pcId)
                        put("uploaded_at", now)
                    },
                    SQLiteDatabase.CONFLICT_IGNORE,
                )
            }
            db.setTransactionSuccessful()
        } finally {
            db.endTransaction()
        }
    }

    fun count(pcId: String): Int =
        readableDatabase.rawQuery(
            "SELECT COUNT(*) FROM backed_up WHERE pc_id = ?", arrayOf(pcId)
        ).use { cursor ->
            if (cursor.moveToFirst()) cursor.getInt(0) else 0
        }
}
