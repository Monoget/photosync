package com.photosync.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Computer
import androidx.compose.material.icons.filled.PhoneAndroid
import androidx.compose.material.icons.filled.Wifi
import androidx.compose.material.icons.filled.WifiOff
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.Card
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.photosync.app.discovery.DiscoveredPc

/**
 * Main screen (spec section 18). Phase 5: gallery permission flow,
 * MediaStore stats, and working "Backup Now" with progress.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HomeScreen(viewModel: HomeViewModel = viewModel()) {
    val state by viewModel.uiState.collectAsStateWithLifecycle()
    var pairTarget by remember { mutableStateOf<DiscoveredPc?>(null) }
    val permissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { viewModel.onPermissionResult() }

    pairTarget?.let { target ->
        PairDialog(
            pc = target,
            status = state.pairingStatus,
            onSubmit = { code -> viewModel.pair(target, code) },
            onDismiss = {
                pairTarget = null
                viewModel.dismissPairingError()
            },
        )
        // Close the dialog once pairing succeeds.
        if (state.pairedPc != null && state.pairingStatus == PairingStatus.IDLE) {
            pairTarget = null
        }
    }

    Scaffold(
        topBar = { TopAppBar(title = { Text("PhotoSync") }) },
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .verticalScroll(rememberScrollState())
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            ConnectionCard(state, onPair = { pairTarget = it })
            if (!state.hasPermission) {
                PermissionCard(
                    onRequest = {
                        permissionLauncher.launch(HomeViewModel.REQUIRED_PERMISSION)
                    },
                )
            }
            AutoBackupCard()
            StatsCard(state)
            if (state.backup.running) {
                BackupProgressCard(state.backup)
            }
            Button(
                onClick = { viewModel.backupNow() },
                enabled = state.connected && state.hasPermission && !state.backup.running,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text(if (state.backup.running) "Backing Up…" else "Backup Now")
            }
            LastBackupText(state)
        }
    }
}

@Composable
private fun ConnectionCard(state: HomeUiState, onPair: (DiscoveredPc) -> Unit) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(
                    Icons.Default.PhoneAndroid,
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.primary,
                )
                Spacer(Modifier.size(8.dp))
                Text("This Phone", style = MaterialTheme.typography.titleMedium)
            }
            val paired = state.pairedPc
            when {
                paired != null && state.connected -> StatusRow(
                    icon = Icons.Default.CheckCircle,
                    text = "Connected to ${paired.pcName}",
                    tint = MaterialTheme.colorScheme.primary,
                )
                paired != null -> StatusRow(
                    icon = Icons.Default.WifiOff,
                    text = "Paired with ${paired.pcName} — not reachable right now",
                )
                state.pcs.isNotEmpty() -> state.pcs.forEach { PcRow(it, onPair) }
                state.searching -> StatusRow(
                    icon = Icons.Default.Wifi,
                    text = "Searching for your Windows PC…",
                )
                else -> StatusRow(
                    icon = Icons.Default.WifiOff,
                    text = "Not connected to a Windows PC",
                )
            }
        }
    }
}

@Composable
private fun PcRow(pc: DiscoveredPc, onPair: (DiscoveredPc) -> Unit) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Icon(
            Icons.Default.Computer,
            contentDescription = null,
            tint = MaterialTheme.colorScheme.primary,
        )
        Spacer(Modifier.size(8.dp))
        Column(Modifier.weight(1f)) {
            Text(pc.displayName)
            Text(
                "Found on your Wi-Fi • Not paired",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        Button(onClick = { onPair(pc) }) { Text("Pair") }
    }
}

@Composable
private fun PairDialog(
    pc: DiscoveredPc,
    status: PairingStatus,
    onSubmit: (String) -> Unit,
    onDismiss: () -> Unit,
) {
    var code by remember { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Pair with ${pc.displayName}") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text(
                    "On your PC, open Devices → \"Pair a Device\" and enter " +
                        "the 6-digit code shown there.",
                )
                OutlinedTextField(
                    value = code,
                    onValueChange = { code = it.filter { c -> c.isDigit() }.take(6) },
                    label = { Text("Pairing code") },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                    singleLine = true,
                )
                when (status) {
                    PairingStatus.WRONG_CODE -> Text(
                        "That code wasn't accepted. Check it and try again.",
                        color = MaterialTheme.colorScheme.error,
                    )
                    PairingStatus.FAILED -> Text(
                        "Couldn't reach the PC. Check that both devices are " +
                            "on the same Wi-Fi.",
                        color = MaterialTheme.colorScheme.error,
                    )
                    PairingStatus.IN_PROGRESS -> Text("Pairing…")
                    PairingStatus.IDLE -> {}
                }
            }
        },
        confirmButton = {
            Button(
                onClick = { onSubmit(code) },
                enabled = code.length == 6 && status != PairingStatus.IN_PROGRESS,
            ) { Text("Pair") }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text("Cancel") }
        },
    )
}

@Composable
private fun StatusRow(
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    text: String,
    tint: androidx.compose.ui.graphics.Color = MaterialTheme.colorScheme.onSurfaceVariant,
) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Icon(icon, contentDescription = null, tint = tint)
        Spacer(Modifier.size(8.dp))
        Text(text, color = tint)
    }
}

@Composable
private fun AutoBackupCard() {
    Card(modifier = Modifier.fillMaxWidth()) {
        Row(
            Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Text("Automatic Backup", style = MaterialTheme.typography.titleMedium)
            Switch(checked = false, onCheckedChange = null, enabled = false)
        }
    }
}

@Composable
private fun PermissionCard(onRequest: () -> Unit) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("Photo access needed", style = MaterialTheme.typography.titleMedium)
            Text(
                "PhotoSync needs access to your photos to back them up to " +
                    "your PC. Photos are only ever sent to the PC you paired.",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Button(onClick = onRequest) { Text("Allow Access") }
        }
    }
}

@Composable
private fun StatsCard(state: HomeUiState) {
    val total = state.photoCount
    val backedUp = state.backedUpCount
    Card(modifier = Modifier.fillMaxWidth()) {
        Row(
            Modifier
                .fillMaxWidth()
                .padding(16.dp),
            horizontalArrangement = Arrangement.SpaceEvenly,
        ) {
            Stat("Photos", total?.toString() ?: "—")
            Stat("Backed Up", backedUp?.toString() ?: "—")
            Stat(
                "Pending",
                if (total != null && backedUp != null) {
                    (total - backedUp).coerceAtLeast(0).toString()
                } else "—",
            )
        }
    }
}

@Composable
private fun BackupProgressCard(progress: BackupProgress) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(
                "Backing up ${progress.done} / ${progress.total}",
                style = MaterialTheme.typography.titleMedium,
            )
            LinearProgressIndicator(
                progress = {
                    if (progress.total == 0) 0f
                    else progress.done.toFloat() / progress.total
                },
                modifier = Modifier.fillMaxWidth(),
            )
            if (progress.failed > 0) {
                Text(
                    "${progress.failed} file(s) could not be transferred",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.error,
                )
            }
        }
    }
}

@Composable
private fun LastBackupText(state: HomeUiState) {
    val text = when {
        state.pairedPc == null -> "Pair this phone with your Windows PC to enable backup."
        state.lastBackupMs != null -> {
            val formatted = remember(state.lastBackupMs) {
                java.text.DateFormat.getDateTimeInstance(
                    java.text.DateFormat.MEDIUM, java.text.DateFormat.SHORT,
                ).format(java.util.Date(state.lastBackupMs))
            }
            "Last backup: $formatted"
        }
        else -> "No backups yet — tap Backup Now when connected."
    }
    Text(
        text,
        style = MaterialTheme.typography.bodySmall,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
}

@Composable
private fun Stat(label: String, value: String) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(value, style = MaterialTheme.typography.headlineSmall)
        Spacer(Modifier.height(4.dp))
        Text(
            label,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}
