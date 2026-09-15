# PhotoSync

Automatically back up Android photos to a Windows PC over local Wi-Fi.

- `desktop/` — Windows desktop app (Python 3.12, PySide6/Qt 6)
- `mobile/` — Android app (Kotlin 2.1, Jetpack Compose, AGP 8.11, Gradle 8.13)
- `tests/` — unit and integration tests
- `installer/` — PyInstaller + Windows installer assets — pending
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
- Next: Phase 7 (reliability: resume, retry, partial files, reconnection).
  See `instruction/PhotoSync_Claude_Code_Prompt.md`, section 36.
