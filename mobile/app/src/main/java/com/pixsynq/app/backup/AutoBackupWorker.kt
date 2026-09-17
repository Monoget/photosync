package com.pixsynq.app.backup

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import com.pixsynq.app.discovery.PcDiscovery
import com.pixsynq.app.pairing.PairingClient
import com.pixsynq.app.pairing.TrustStore
import kotlinx.coroutines.delay
import kotlinx.coroutines.withTimeoutOrNull
import java.util.concurrent.TimeUnit

/**
 * Periodic background backup (spec §19): WorkManager-scheduled, network
 * constrained, battery-policy compliant — no promise of a forever-running
 * process. Runs only while a trusted PC is reachable on the current Wi-Fi.
 */
class AutoBackupWorker(
    context: Context,
    params: WorkerParameters,
) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result {
        val context = applicationContext
        val trustStore = TrustStore(context)
        val trusted = trustStore.trustedPc ?: return Result.success()
        if (!trustStore.autoBackup) return Result.success()
        val permission = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            Manifest.permission.READ_MEDIA_IMAGES
        } else {
            Manifest.permission.READ_EXTERNAL_STORAGE
        }
        if (ContextCompat.checkSelfPermission(context, permission)
            != PackageManager.PERMISSION_GRANTED
        ) {
            return Result.success()  // user revoked access; nothing to do
        }

        // Find the trusted PC on the current network (bounded discovery).
        val discovery = PcDiscovery(context)
        val client = PairingClient()
        val pc = try {
            discovery.start()
            withTimeoutOrNull(12_000L) {
                var found: com.pixsynq.app.discovery.DiscoveredPc? = null
                while (found == null) {
                    found = discovery.pcs.value.firstOrNull {
                        client.ping(it.host, it.port, trusted)
                    }
                    if (found == null) delay(1000)
                }
                found
            }
        } finally {
            discovery.stop()
        }
        if (pc == null) {
            Log.i(TAG, "Trusted PC not reachable; will retry on next period")
            return Result.success()
        }

        val run = BackupEngine(context).run(pc, trusted)
        Log.i(
            TAG,
            "Auto backup: ${run.uploaded} uploaded, ${run.duplicates} known, " +
                "${run.failed} failed of ${run.total}",
        )
        if (run.uploaded > 0) notifyResult(context, run.uploaded)
        return Result.success()
    }

    private fun notifyResult(context: Context, uploaded: Int) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            ContextCompat.checkSelfPermission(
                context, Manifest.permission.POST_NOTIFICATIONS
            ) != PackageManager.PERMISSION_GRANTED
        ) {
            return
        }
        val manager = context.getSystemService(NotificationManager::class.java)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            manager.createNotificationChannel(
                NotificationChannel(
                    CHANNEL_ID, "Backup", NotificationManager.IMPORTANCE_LOW
                )
            )
        }
        val notification = NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.stat_sys_upload_done)
            .setContentTitle("PixSynq")
            .setContentText(
                "$uploaded photo${if (uploaded == 1) "" else "s"} backed up to your PC"
            )
            .setAutoCancel(true)
            .build()
        manager.notify(1001, notification)
    }

    companion object {
        private const val TAG = "AutoBackupWorker"
        private const val CHANNEL_ID = "backup"
        private const val WORK_NAME = "pixsynq-auto-backup"

        /** Schedule or cancel the periodic job to match the user's toggle. */
        fun sync(context: Context, enabled: Boolean) {
            val manager = WorkManager.getInstance(context)
            if (!enabled) {
                manager.cancelUniqueWork(WORK_NAME)
                return
            }
            val request = PeriodicWorkRequestBuilder<AutoBackupWorker>(
                1, TimeUnit.HOURS
            ).setConstraints(
                Constraints.Builder()
                    .setRequiredNetworkType(NetworkType.UNMETERED)
                    .setRequiresBatteryNotLow(true)
                    .build()
            ).build()
            manager.enqueueUniquePeriodicWork(
                WORK_NAME, ExistingPeriodicWorkPolicy.KEEP, request
            )
        }
    }
}
