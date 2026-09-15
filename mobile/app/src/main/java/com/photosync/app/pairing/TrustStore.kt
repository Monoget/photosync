package com.photosync.app.pairing

import android.content.Context
import androidx.core.content.edit
import org.json.JSONObject
import java.util.UUID

/** The Windows PC this phone trusts after pairing. */
data class TrustedPc(
    val pcId: String,
    val pcName: String,
    val fingerprint: String,
    val token: String,
)

/**
 * Persistent device identity and trusted-PC record.
 *
 * Backed by SharedPreferences; the auth token is a per-pairing secret
 * for this app only (Room isn't warranted for a single record).
 */
class TrustStore(context: Context) {

    private val prefs =
        context.applicationContext.getSharedPreferences("photosync", Context.MODE_PRIVATE)

    /** Stable random identity for this installation. */
    val deviceId: String
        get() = prefs.getString(KEY_DEVICE_ID, null) ?: UUID.randomUUID().toString()
            .also { prefs.edit { putString(KEY_DEVICE_ID, it) } }

    var trustedPc: TrustedPc?
        get() = prefs.getString(KEY_TRUSTED_PC, null)?.let {
            runCatching {
                val json = JSONObject(it)
                TrustedPc(
                    pcId = json.getString("pcId"),
                    pcName = json.getString("pcName"),
                    fingerprint = json.getString("fingerprint"),
                    token = json.getString("token"),
                )
            }.getOrNull()
        }
        set(value) = prefs.edit {
            if (value == null) {
                remove(KEY_TRUSTED_PC)
            } else {
                putString(
                    KEY_TRUSTED_PC,
                    JSONObject()
                        .put("pcId", value.pcId)
                        .put("pcName", value.pcName)
                        .put("fingerprint", value.fingerprint)
                        .put("token", value.token)
                        .toString(),
                )
            }
        }

    private companion object {
        const val KEY_DEVICE_ID = "device_id"
        const val KEY_TRUSTED_PC = "trusted_pc"
    }
}
