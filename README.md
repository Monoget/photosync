# PhotoSync

Automatically back up Android photos to a Windows PC over local Wi-Fi.

- `desktop/` — Windows desktop app (Python 3.12, PySide6/Qt 6)
- `mobile/` — Android app (Kotlin 2.1, Jetpack Compose, AGP 8.11, Gradle 8.13)
- `server/` — registration/heartbeat/update API + admin dashboard (Flask)
- `tests/` — unit, integration, and server tests
- `installer/` — PyInstaller spec, Inno Setup script, build script
- `instruction/` — product/build specification

## Run the desktop app (development)

```powershell
cd desktop
python -m venv .venv
.venv\Scripts\pip install -r ..\requirements.txt
.venv\Scripts\python main.py
```

User data (settings, database, logs) is stored in `%LOCALAPPDATA%\PhotoSync`.
Photos are stored in a user-selected folder chosen during first-run setup.

## Tests

```powershell
desktop\.venv\Scripts\pip install pytest
desktop\.venv\Scripts\python -m pytest
```

## Build the Android app

```powershell
cd mobile
$env:JAVA_HOME = "C:\Program Files\Android\Android Studio\jbr"
.\gradlew.bat assembleDebug
```

APK output: `mobile\app\build\outputs\apk\debug\app-debug.apk`.
`mobile/local.properties` is machine-specific (Android SDK path) and not
meant for version control.

### Signed release APK

```powershell
python mobile\generate_keystore.py    # one-time; creates keystore + credentials
cd mobile
.\gradlew.bat assembleRelease         # -> app\build\outputs\apk\release\app-release.apk
```

`photosync-release.keystore` and `keystore.properties` are git-ignored —
**back them up**; losing the keystore means installed apps can never be
updated. Without them, `assembleRelease` produces an unsigned build.

## Build the Windows release

```powershell
desktop\.venv\Scripts\pip install pyinstaller
powershell -File installer\build.ps1
```

This produces `dist\PhotoSync\PhotoSync.exe` and, when Inno Setup's `iscc`
is on PATH, the installer at `installer\output\PhotoSync-<version>-Setup.exe`.

**Authenticode signing** is built into the pipeline: set either
`CODESIGN_THUMBPRINT` (certificate in the CurrentUser store — EV token or
Azure Trusted Signing) or `CODESIGN_PFX` + `CODESIGN_PFX_PASSWORD`, and
`build.ps1` signs and timestamps both the exe and the installer
(`installer\sign.ps1` can also sign any file directly). Until a
certificate from a CA is configured, builds are unsigned and SmartScreen
will warn. After signing, record the installer's SHA-256 and publish it
to the update feed with `server\add_release.py`.

## Run the server

```powershell
pip install -r server\requirements.txt
$env:ADMIN_USER = "admin"; $env:ADMIN_PASSWORD = "<strong password>"
python server\app.py     # dev only; deploy behind HTTPS in production
```

The desktop app picks up the server via the `API_BASE_URL` /
`UPDATE_BASE_URL` environment variables (or the `api_base_url` /
`update_base_url` settings) — no domain is hardcoded. Without them,
registration stays local and update checks are disabled; photo backup is
never affected.

## Status

- Phase 1 (Foundation) — **done.** Desktop: PySide6 shell with sidebar
  navigation, light/dark theme tokens, rotating file logging, per-user data
  paths. Android: Compose app with Material 3 theme (dynamic color on 12+)
  and a static Phase-1 home screen; debug APK builds.
- Phase 2 (Windows Setup) — **done.** First-run flow (Welcome → Register →
  Choose Folder → Ready) with privacy disclosure and consent, name/email
  validation, folder validation (creatable + writable), atomic JSON settings
  persistence in `%LOCALAPPDATA%\PhotoSync`, per-installation UUID, and
  destination change in Settings. Registration is stored locally marked
  `pending` until the registration API exists (spec §32: telemetry must
  never block backup).
- Phase 3 (Discovery) — **done.** Desktop announces `_photosync._tcp` via
  zeroconf and browses for phones (`_photosync-m._tcp`); Android registers
  itself via NSD and browses for PCs, with sequential resolve queuing. Both
  UIs show live network status: the desktop Devices page lists discovered
  phones and the dashboard shows a device count; the Android home screen
  shows "Searching…" / discovered PC. Verified with a real mDNS loopback
  integration test.
- Phase 4 (Pairing) — **done.** The desktop runs a TLS receiver
  (`ThreadingHTTPServer` + a persistent self-signed EC certificate;
  discovery now advertises its port). Pairing: the PC shows a single-use
  6-digit code + QR (Devices → "Pair a Device"), the phone submits it over
  HTTPS with the certificate fingerprint pinned trust-on-first-use, and on
  success receives a bearer token. Trust is stored in SQLite on the PC
  (token hash only) and SharedPreferences on the phone. Wrong codes are
  rate-limited (5 attempts), the receiver serves private/loopback addresses
  only, and the phone re-verifies the pairing with an authenticated ping
  whenever the network view changes — "Connected to <PC>" is live status.
- Phase 5 (Basic Transfer) — **done.** Android: gallery permission flow
  (READ_MEDIA_IMAGES on 13+, READ_EXTERNAL_STORAGE below), MediaStore
  scanner, and a streaming upload client (SHA-256 computed first, then a
  fixed-length streamed POST over pinned TLS); "Backup Now" runs the whole
  gallery sequentially with live progress, and one bad file never stops the
  run. Desktop: authenticated `/api/v1/upload` streams to a `.part` temp
  file, verifies size + SHA-256, atomically renames into
  `<dest>/YYYY/MM/` (sanitized filenames, uniquified collisions), records
  photos/transfers rows, and skips already-received (device, media id)
  pairs as duplicates. Dashboard shows live photo count/bytes/last-backup;
  Backup History lists transfers.
- Phase 6 (Incremental Sync) — **done.** The phone keeps per-PC backup
  state in its own SQLite database and reconciles it with the PC through
  `POST /api/v1/sync/check` (batched media-id lists) before uploading, so
  only genuinely new photos cross the wire; if the check fails it falls
  back to uploading and lets the PC dedup. The receiver also dedups by
  content hash + size (spec §14): the same bytes under a new MediaStore id
  are recorded as an alias without writing a second file, and disk stats
  count distinct files. Phone stats (Photos / Backed Up / Pending) are now
  persistent.
- Phase 7 (Reliability) — **done.** Resumable uploads: deterministic
  `.part` files per (device, media id), `X-PhotoSync-Total-Size`/`Offset`
  headers, a `GET /api/v1/upload/offset` query, whole-file hash
  verification before the atomic rename, 409 on offset mismatch, stale
  `.part` cleanup at start, a disk-space guard (507), and a receiver pause
  flag. The phone retries up to 3 times with backoff, resuming from the
  server's offset.
- Phase 8 (Automatic Backup) — **done.** The backup pipeline lives in
  `BackupEngine`, shared by the UI and `AutoBackupWorker` (WorkManager,
  hourly, unmetered network + battery-not-low, bounded 12s discovery,
  optional completion notification). In-app, the trusted PC appearing on
  Wi-Fi triggers a run at most every 15 minutes. The Automatic Backup
  switch is live and persisted.
- Phase 9 (Updates & Server) — **done.** Flask server: registration
  (server-side IP capture, validation, rate limiting), name/email-free
  heartbeat, update feed, and a Basic-auth admin dashboard with install
  stats. Desktop: semantic version comparison, background update checks
  (env-configured URL, honors auto/notify settings, no re-nagging about a
  dismissed version), and a verified updater — HTTPS-only download,
  SHA-256 check, installer launched as its own process.
- Phase 10 (UI Polish) — **done.** Live light/dark theme switcher,
  programmatic app icon, styled inputs/combo boxes, settings for updates
  and startup behavior.
- Phase 11 (Installer & Release) — **done.** System tray (Open,
  Pause/Resume Backup, Exit), close-to-tray when "run in background" is
  on, start-with-Windows registry toggle, PyInstaller spec + Inno Setup
  script + `installer\build.ps1`, and the verified `dist\PhotoSync`
  bundle.

All 11 phases of `instruction/PhotoSync_Claude_Code_Prompt.md` §36 are
implemented.
