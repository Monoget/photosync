# PhotoSync — Full Project Report

**Date:** 2026-09-15
**Repository:** https://github.com/Monoget/photosync (private, branch `main`)
**Status:** All 11 development phases of the specification
(`instruction/PhotoSync_Claude_Code_Prompt.md`, §36) implemented and verified.
**Tests:** 74 passing.

---

## 1. What PhotoSync is

PhotoSync automatically backs up photos from an Android phone to a
user-chosen folder on a Windows PC whenever both devices are on the same
Wi-Fi network. There is no cloud in the photo path — transfers are direct,
LAN-only, and TLS-encrypted. An optional (self-hosted) server handles
installation registration and software-update notifications; photo backup
never depends on it.

### End-to-end user flow

1. **Windows:** install PhotoSync → first-run flow: Welcome → Register
   (name/email + privacy consent) → Choose photo folder → Ready.
2. **Android:** install the app → grant photo access (rationale shown,
   denial handled gracefully with retry).
3. Both devices **discover each other automatically** on the same Wi-Fi
   (mDNS/NSD), by name, with live status in both UIs.
4. **Pair once:** the PC shows a single-use 6-digit code (plus a QR
   payload); the phone submits it over pinned TLS and receives a bearer
   token. Both sides store the trust relationship.
5. **Backup:** manual ("Backup Now") or automatic (hourly background job +
   instant run when the trusted PC appears). Only new photos transfer;
   files land in `<destination>/YYYY/MM/`, verified before visible.
6. The PC lives in the **system tray**, shows live stats/history, and
   checks the update server for new releases.

---

## 2. Repository layout

```
D:\Drive-Application
├── desktop/          Windows app — Python 3.12, PySide6/Qt 6
│   ├── main.py, app.py            entry + bootstrap (wizard, tray, wiring)
│   ├── ui/                        windows, pages, dialogs, widgets, styles,
│   │                              tray.py, resources/icons.py
│   ├── core/                      models, protocol constants, services
│   │                              (registration, version, update_checker,
│   │                              telemetry)
│   ├── infrastructure/            database, networking (receiver),
│   │                              discovery, storage, security, configuration
│   └── .venv/                     dev virtualenv (not in git)
├── mobile/           Android app — Kotlin 2.1.21, Jetpack Compose,
│   │                 AGP 8.11.1, Gradle 8.13, compileSdk 36, minSdk 26
│   └── app/src/main/java/com/photosync/app/
│       ├── ui/                    HomeScreen, HomeViewModel, theme
│       ├── discovery/             NSD register + browse
│       ├── pairing/               TrustStore, PairingClient
│       ├── transfer/              UploadClient (resume/retry/sync-check)
│       ├── media/                 GalleryScanner (MediaStore)
│       ├── backup/                BackupEngine, BackupStateDb,
│       │                          AutoBackupWorker (WorkManager)
│       └── net/                   PinnedHttp (fingerprint-pinned TLS)
├── server/           Flask API + admin dashboard (registration, heartbeat,
│                     update feed) + add_release.py publishing CLI
├── installer/        photosync.spec (PyInstaller), PhotoSync.iss (Inno
│                     Setup), build.ps1
├── tests/            unit/, integration/, server/ — 74 tests
├── instruction/      the original build specification
├── pyproject.toml, requirements.txt, README.md
```

---

## 3. Architecture

### Desktop (Windows)

- **UI layer** (`ui/`): PySide6 main window with sidebar navigation
  (Dashboard, Devices, Backup History, Settings, About), custom themed
  first-run wizard, pairing dialog, update dialog, system tray. No
  networking or database code in widgets; workers signal the GUI thread.
- **Core layer** (`core/`): models, protocol constants, pure services
  (validation, semantic version compare, update checking, telemetry).
- **Infrastructure layer** (`infrastructure/`):
  - `networking/receiver.py` — the HTTPS receiver server (see §4/§5).
  - `discovery/service.py` — zeroconf announce + browse.
  - `database/db.py` — SQLite with `PRAGMA user_version` migrations;
    `DeviceStore` and `PhotoStore` open one connection per call, so
    receiver worker threads are safe.
  - `security/identity.py` — persistent self-signed EC (P-256) TLS
    certificate; its SHA-256 fingerprint is the PC's identity.
  - `storage/` — destination validation, filename sanitization,
    year/month organization with collision uniquification.
  - `configuration/` — per-user paths, atomic JSON settings store with
    installation UUID, start-with-Windows registry helper.

### Android

- Jetpack Compose + Material 3 (dynamic color on Android 12+), single
  activity, `HomeViewModel` exposing a combined `StateFlow`.
- `BackupEngine` holds the whole backup pipeline and is shared by the UI
  and the background `AutoBackupWorker` (WorkManager: hourly, unmetered
  network, battery-not-low; bounded 12-second discovery; optional
  completion notification with `POST_NOTIFICATIONS` requested on 13+).
- MediaStore only — no hardcoded filesystem paths.

### Server (optional, self-hosted)

Flask + SQLite. The desktop app never touches the server database
directly — only this API (spec §6). Deploy behind HTTPS. No production
domain appears anywhere in source; clients find the server via
`API_BASE_URL` / `UPDATE_BASE_URL` environment variables or settings.

---

## 4. Protocol reference (LAN, `protocol_version = 1`)

mDNS service types (RFC 6763 limits service names to 15 bytes):

| Role | Service type | TXT records |
|---|---|---|
| PC (receiver) | `_photosync._tcp.local.` | protocol, name, platform, app_version |
| Phone | `_photosync-m._tcp.local.` | protocol, name, platform |

HTTPS endpoints on the PC receiver (self-signed cert, fingerprint-pinned
by the phone; **private/loopback source addresses only**):

| Endpoint | Auth | Purpose |
|---|---|---|
| `GET /api/v1/info` | none | PC name, platform, protocol, version, pc_id |
| `POST /api/v1/pair` | pairing code | body: device_id, name, platform, code → token |
| `GET /api/v1/ping` | Bearer | trust verification; updates last_seen |
| `POST /api/v1/sync/check` | Bearer | body: media_ids[] (≤1000) → `needed` subset |
| `POST /api/v1/upload` | Bearer | photo bytes (see below) |
| `GET /api/v1/upload/offset?media_id=` | Bearer | resume point, or `complete: true` |

Upload headers: `X-PhotoSync-Media-Id`, `X-PhotoSync-Filename`
(URL-encoded UTF-8), `X-PhotoSync-Sha256`, `X-PhotoSync-Date-Taken`
(epoch ms), `X-PhotoSync-Total-Size`, `X-PhotoSync-Offset`. The body is
raw bytes for `[offset, offset+Content-Length)`. Responses: partial ack,
success, `duplicate: true`, `409` offset mismatch (with actual offset),
`507` insufficient disk space, `503` while paused from the tray.

### Backup pipeline (incremental)

1. Scan MediaStore.
2. Skip everything in the phone's local per-PC `backed_up` SQLite table.
3. Reconcile the remainder with the PC via `sync/check` in batches of
   500; ids the PC already has are marked locally without uploading. A
   failed check falls back to uploading (the PC dedups).
4. Upload the rest sequentially; per-photo SHA-256 is computed first so
   the PC can verify. Up to 3 attempts with backoff; retries resume from
   the server's offset. One bad file never aborts the run.
5. The PC streams to `<dest>/.photosync-tmp/<device>_<media>.part`,
   verifies length + SHA-256 over the whole file, then atomically renames
   into `<dest>/YYYY/MM/` and only then records the photo as completed.

### Duplicate detection (spec §14)

- Primary: `(device_id, media_id)` uniqueness.
- Secondary: same content hash + size under a *new* media id (MediaStore
  re-index, restored phone) is recorded as an alias to the existing file —
  no second copy on disk; dashboard stats count distinct files.

---

## 5. Security model

- **Transport:** all phone↔PC traffic is TLS. The PC's identity is a
  persistent self-signed EC certificate; the phone pins its SHA-256
  fingerprint at pairing (trust-on-first-use, justified by the pairing
  code) and requires an exact match forever after.
- **Pairing:** single-use 6-digit codes, constant-time comparison,
  session invalidated after 5 wrong attempts, explicit user action on
  both devices.
- **Authorization:** per-device bearer tokens; the PC stores only SHA-256
  hashes of tokens.
- **Attack-surface limits:** receiver serves RFC-1918/loopback/link-local
  sources only; 64 KB JSON body cap; 2 GB upload cap; filenames sanitized
  against path traversal (verified by test); uploads can never escape the
  destination root.
- **Updates (spec §25):** HTTPS-only download, SHA-256 verification with
  the file discarded on mismatch, installer runs as its own process so
  the running exe can be replaced. (Authenticode signing still TODO.)
- **Server:** parameterized SQL, input validation, per-IP rate limiting,
  request size caps, Basic-auth admin dashboard (404 when credentials are
  unconfigured), client IPs taken from the connection — never from the
  payload.
- **Telemetry & privacy (spec §4, §9, §32):** collected only after
  explicit consent: name, email, Windows username, app version, OS info;
  server records request IP. Heartbeats carry no name/email. Nothing else
  is ever collected. All of it is best-effort — backup works fully
  offline from the server.

---

## 6. Data locations

| What | Where |
|---|---|
| Windows app (installed) | `C:\Program Files\PhotoSync\` |
| Settings, SQLite DB, logs, TLS identity | `%LOCALAPPDATA%\PhotoSync\` |
| Photos | user-chosen folder (default `~\Pictures\PhotoSync`), organized `YYYY/MM/` |
| In-flight transfers | `<destination>\.photosync-tmp\*.part` (auto-cleaned after 7 days) |
| Phone backup state | app-private SQLite `backup_state.db` |
| Phone trust/settings | app-private SharedPreferences |

Logs rotate daily (14 kept) and never contain tokens, keys, or personal
data. Uninstall never touches user data or photos.

---

## 7. Build & run

### Desktop (development)

```powershell
cd desktop
python -m venv .venv
.venv\Scripts\pip install -r ..\requirements.txt
.venv\Scripts\python main.py
```

### Tests (74)

```powershell
desktop\.venv\Scripts\pip install pytest flask
desktop\.venv\Scripts\python -m pytest        # from repo root
```

### Android

```powershell
cd mobile
$env:JAVA_HOME = "C:\Program Files\Android\Android Studio\jbr"
.\gradlew.bat assembleDebug
# APK: mobile\app\build\outputs\apk\debug\app-debug.apk
```

### Windows release

```powershell
desktop\.venv\Scripts\pip install pyinstaller
powershell -File installer\build.ps1
# Bundle:    dist\PhotoSync\PhotoSync.exe          (build verified working)
# Installer: installer\output\PhotoSync-0.1.0-Setup.exe (needs Inno Setup's iscc)
```

Release checklist: build → Authenticode-sign the installer → record its
SHA-256 → upload → publish to the update feed:

```powershell
python server\add_release.py --version 1.1.0 --url https://<host>/PhotoSync-1.1.0.exe --sha256 <hex>
```

### Server

```powershell
pip install -r server\requirements.txt
$env:ADMIN_USER = "admin"; $env:ADMIN_PASSWORD = "<strong password>"
python server\app.py      # dev; deploy behind HTTPS in production
```

Point clients at it with `API_BASE_URL` / `UPDATE_BASE_URL` (env vars or
the `api_base_url` / `update_base_url` settings).

---

## 8. Phase-by-phase commit map

| Commit | Phases | Contents |
|---|---|---|
| `ba48240` | 1–2 | PySide6 shell + theme + logging; Android Compose shell; first-run flow (register/consent, folder picker), atomic settings store, installation UUID |
| `e23bad5` | 3 | mDNS/NSD discovery both directions, live status in both UIs, real-mDNS integration test |
| `2d88a8e` | 4 | TLS identity, SQLite schema (devices/photos/transfers), pairing (code + QR, pinning, tokens), pair dialog, trusted-device UI |
| `947419a` | 5 | Gallery permission flow, MediaStore scanner, streaming uploads, `.part` + verify + `YYYY/MM`, dashboard stats, backup history |
| `d6dd27e` | 6 | Phone-side backup state DB, `sync/check` reconciliation, content-hash alias dedup, persistent stats |
| `f1329a8` | 7–8 | Resume/retry/offset protocol, stale-part cleanup, disk guard, pause; BackupEngine + WorkManager auto backup + notifications |
| `aebe7cb` | 9 | Flask server (register/heartbeat/updates/admin/rate limit), version compare, update checker, verified updater, telemetry client |
| `175f17e` | 10–11 | Theme switcher, app icon, tray, close-to-tray, start-with-Windows, PyInstaller + Inno Setup + build script, README docs |

---

## 9. Test coverage summary

- **App shell & setup:** navigation, theming, settings round-trip and
  corrupt-file recovery, installation-ID stability, registration and
  folder validation, full wizard flow.
- **Discovery:** service-info parsing, UI wiring, and a real-mDNS
  loopback integration test (announce + discover).
- **Pairing (against the live TLS server):** info endpoint, wrong/right
  code, single-use codes, 5-attempt lockout, ping auth, identity
  persistence, DB migrations idempotence, local-address guard.
- **Transfer:** upload success, wire-level duplicate skip, hash-mismatch
  rejection with no residue, auth required, path-traversal neutralized,
  year/month organization and collision naming.
- **Incremental sync:** `sync/check` semantics + auth + validation,
  hash-alias dedup (one file on disk, both ids backed up).
- **Reliability:** two-chunk resume with offset query, offset-mismatch
  409, post-resume hash failure cleanup, pause 503/resume, stale-part
  cleanup, part-path safety.
- **Updates:** version-comparison table (incl. `1.10.0 > 1.9.0`),
  checker matrix (newer/older/skipped/mandatory/disabled/server-down).
- **Server:** register + re-register upsert, validation, server-side IP
  capture, heartbeat, update feed, admin auth (disabled/401/200), rate
  limiting.
- **Packaging:** startup-registry round-trip (isolated key); the frozen
  PyInstaller exe was launched and verified initializing.

Android correctness is verified by clean compilation of every phase plus
the shared-logic design (the pipeline lives in `BackupEngine`, mirrored by
the server-side tests of every endpoint it calls). On-device testing is
listed below.

---

## 10. Known limitations / recommended next steps

1. **Windows code signing** — the signing *pipeline* is in place
   (`installer/sign.ps1`, auto-invoked by `build.ps1` when
   `CODESIGN_THUMBPRINT` or `CODESIGN_PFX`+`CODESIGN_PFX_PASSWORD` are
   set), but removing SmartScreen warnings requires purchasing an
   Authenticode certificate: an **EV certificate** (~$300–500/yr,
   immediate SmartScreen reputation) or **Azure Trusted Signing**
   (~$10/mo, identity-validated) for instant trust; a standard OV
   certificate (~$100–400/yr) signs the app but reputation builds over
   downloads. Until then, builds are unsigned and SmartScreen warns.
2. **Android release signing** — **done.** `mobile/generate_keystore.py`
   created a 4096-bit RSA release keystore; `assembleRelease` produces a
   signed, minified APK (1.5 MB). The keystore and `keystore.properties`
   are git-ignored — **back them up**: losing the keystore permanently
   breaks app updates for existing installs. Sideload installs still show
   Android's one-time "unknown sources" prompt (only Play Store
   distribution avoids that).
3. **Server deployment** — `server/` is ready but not hosted. Deploy
   behind HTTPS, set `ADMIN_USER`/`ADMIN_PASSWORD`, then point clients
   via `API_BASE_URL`/`UPDATE_BASE_URL`.
4. **QR scanning** — the PC displays a QR (ip/port/fingerprint/code) but
   the phone currently enters the code manually; adding CameraX + ML Kit
   scanning would also pre-pin the fingerprint (removing TOFU).
5. **Video support** — photos only for now (spec treats video as
   optional); `GalleryScanner` and the protocol need no structural
   change to add it.
6. **On-device manual test pass** — the spec §35 manual matrix (real
   phone + PC: Wi-Fi drop mid-transfer, sleep/wake, drive disconnect,
   large galleries) should be run before a public release.
7. **Nice-to-haves** — configurable folder schemes (spec §16 lists
   year/month/day, device-name…), diagnostic-log export button (logs
   already rotate in `%LOCALAPPDATA%\PhotoSync\logs`), heartbeat while
   running (currently at app start, throttled to 24 h).

---

## 11. Key implementation notes (for future maintenance)

- `_photosync-m` (not `-mobile`): RFC 6763 caps mDNS service names at
  15 bytes — zeroconf enforces it.
- `Path("")` stringifies to `"."`; destination validation guards this.
- Qt signals are the only bridge from worker threads (zeroconf callbacks,
  HTTP handler threads) to the GUI — never touch widgets off-thread.
- SQLite is used connection-per-call for thread safety; migrations run
  via `PRAGMA user_version`.
- The receiver's advertised port is the real bound HTTPS socket, so
  discovery and transfer can never disagree.
- Dashboard photo counts use `DISTINCT destination_path` so hash-alias
  records don't inflate stats.
- Long git commit messages on this machine: use `git commit -F <file>`
  (PowerShell here-strings mangled quotes/angle brackets once).
