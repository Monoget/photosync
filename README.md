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
- Next: Phase 4 (pairing: QR/code, device identity, trust storage). See
  `instruction/PhotoSync_Claude_Code_Prompt.md`, section 36.
