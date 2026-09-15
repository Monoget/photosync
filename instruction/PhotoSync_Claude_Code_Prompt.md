# PhotoSync — Claude Code Master Build Prompt

## Project Goal

Build a production-quality Windows desktop application and Android application called **PhotoSync**.

The core purpose:

> When a trusted Android phone and Windows PC are connected to the same Wi-Fi network, PhotoSync automatically transfers new gallery photos from Android to a user-selected folder on Windows after the user grants the required permissions.

The product should have a modern, polished, trustworthy UI and should feel like a real commercial application rather than a prototype.

---

# 1. Technology Stack

## Windows Desktop

Use:

- Python 3.12+
- PySide6 / Qt 6
- SQLite
- `pathlib` for filesystem paths
- Background workers using QThread/QThreadPool or an appropriate architecture
- HTTP/HTTPS
- WebSocket where useful
- mDNS/Bonjour/local-network discovery using a well-maintained Python library such as `zeroconf`
- PyInstaller for packaging
- Inno Setup or another appropriate Windows installer

**Do NOT use Tkinter.**

The desktop application must remain a native-feeling PySide6 application, not an Electron/web wrapper.

## Android

Use:

- Kotlin
- Jetpack Compose
- Android MediaStore
- Kotlin Coroutines
- Room/SQLite where appropriate
- Android networking APIs
- NSD/mDNS or another suitable LAN discovery mechanism
- Appropriate Android background/foreground execution mechanisms

---

# 2. First-Run Windows Setup

After the user installs the Windows application and opens it for the first time, show a polished setup flow.

Example:

```text
Welcome to PhotoSync

Automatically back up your Android photos
to your Windows PC over Wi-Fi.

[ Get Started ]
```

Then:

```text
Choose where your photos should be stored

PhotoSync will save transferred photos here:

D:\Pictures\PhotoSync

[ Choose Folder ]

[ Continue ]
```

Use a native Windows folder picker through PySide6/Qt.

Requirements:

- User can select any writable folder.
- Validate that the selected folder exists or can be created.
- Validate write permission.
- Remember the selected location.
- Allow the location to be changed later in Settings.
- Never store user photos inside the application installation directory.
- Do not hardcode the destination.
- Store settings/database in an appropriate per-user Windows application-data location.

Example:

```text
Application:
C:\Program Files\PhotoSync\

User data:
%LOCALAPPDATA%\PhotoSync\

Photos:
D:\Pictures\PhotoSync\
```

---

# 3. User Registration

On first launch, include a registration step.

The purpose is to register installations and allow the product owner to provide software-update notifications.

Example:

```text
Register PhotoSync

Name
[________________________]

Email
[________________________]

☐ I agree to the Privacy Policy and understand
  the information PhotoSync collects.

[ Continue ]
```

Clearly disclose what information is collected and why.

Do not silently collect identifying information.

Validate:

- Name
- Email
- Network/API errors

The application must remain usable if the registration API is temporarily unavailable.

---

# 4. Installation Telemetry

After the user completes the required registration/consent flow, the application may send:

```text
installation_id
name
email
desktop_username
application_version
operating_system
os_version
architecture
```

The server may determine the public IP address from the incoming HTTPS request if this is disclosed in the privacy policy and permitted by applicable law.

Do not collect:

- Windows passwords
- Browser cookies
- Clipboard contents
- Personal files
- Unrelated filesystem information
- Photo contents
- Unnecessary personal information

Do not trust an IP address supplied by the client. Determine the source IP server-side.

---

# 5. Installation ID

Generate a random UUID for every installation.

```text
installation_id = UUID
```

Do not use email or Windows username as the primary identifier.

Persist the installation ID locally.

---

# 6. Server Architecture

The desktop application must NEVER connect directly to the production database.

Use:

```text
Windows PhotoSync
        |
      HTTPS
        |
        v
   Your REST API
        |
        v
   Server Database
```

Never:

```text
Windows PhotoSync
        |
        v
Production Database
```

Database credentials must never be included in the desktop application.

Use deployment configuration/environment variables for:

```text
API_BASE_URL
UPDATE_BASE_URL
```

Do not hardcode the production domain in source code.

---

# 7. Registration API

Example:

```text
POST /api/v1/installations/register
```

Example request:

```json
{
  "installation_id": "...",
  "name": "...",
  "email": "...",
  "desktop_username": "...",
  "application_version": "1.0.0",
  "operating_system": "Windows",
  "os_version": "...",
  "architecture": "x64"
}
```

The server records the request IP.

Use HTTPS only.

Implement:

- Server-side validation
- Rate limiting
- Request size limits
- SQL parameterization/ORM
- Secure error handling
- Structured logging

---

# 8. Server Database

Suggested table:

```text
installations
--------------------------------
id
installation_id
name
email
desktop_username
ip_address
application_version
operating_system
os_version
architecture
first_seen_at
last_seen_at
status
```

Add indexes for:

```text
installation_id
email
first_seen_at
last_seen_at
```

Restrict access to authorized administrators.

Create a reasonable retention/deletion policy for personal data.

---

# 9. Installation Heartbeat

Optionally implement:

```text
POST /api/v1/installations/heartbeat
```

Example:

```json
{
  "installation_id": "...",
  "application_version": "1.0.0"
}
```

The server can update:

- last_seen_at
- source IP
- application_version

Do not send name/email on every heartbeat.

Use a reasonable interval.

If the server is unavailable, PhotoSync must continue working normally.

---

# 10. Android Gallery Permission

On first Android launch:

- Explain why photo/media access is required.
- Request the correct permission for the Android version.
- Handle denial gracefully.
- Support Android's current permission model.
- Provide a way to retry.
- Use MediaStore instead of hardcoded filesystem paths.

The app must never assume permission was granted.

---

# 11. Local Wi-Fi Discovery

When both devices are connected to the same Wi-Fi:

```text
Android
   |
   | local Wi-Fi
   |
Windows
```

The devices should discover each other automatically.

Do not require the user to type an IP address every time.

Use:

- mDNS/NSD
- Local-network discovery
- Device/service announcements

Handle:

- DHCP/IP changes
- Wi-Fi reconnect
- PC sleep/wake
- Android reconnect
- Multiple devices
- Temporary network failures

---

# 12. Secure Device Pairing

Do not create an unauthenticated file receiver.

First pairing should use:

- QR code and/or
- Short pairing code
- Explicit approval on both devices

After pairing:

- Generate stable device identity.
- Store trusted-device information securely.
- Authenticate future connections.
- Reject unknown devices.
- Restrict the receiver to the local network.
- Use HTTPS/TLS where practical.

Never expose a public internet file-transfer endpoint.

---

# 13. Automatic Photo Backup

After pairing:

```text
Android phone
      |
      | Same trusted Wi-Fi
      v
Windows PC
```

PhotoSync should:

1. Detect the trusted PC.
2. Scan Android MediaStore incrementally.
3. Compare with Windows backup state.
4. Identify new photos.
5. Add them to a transfer queue.
6. Transfer automatically.
7. Verify each transfer.
8. Record successful backup state.

Do not transfer the entire gallery every time.

Example:

```text
IMG_001.jpg  Already backed up
IMG_002.jpg  Already backed up
IMG_003.jpg  NEW
IMG_004.jpg  NEW
```

Only IMG_003 and IMG_004 should transfer.

---

# 14. Duplicate Detection

Do not rely only on filenames.

Use appropriate combinations of:

- Device ID
- Android MediaStore ID
- File size
- Modification timestamp
- Date taken
- Content hash when necessary

Suggested database:

```text
photos
--------------------------------
id
device_id
media_id
filename
file_size
date_taken
content_hash
destination_path
status
created_at
completed_at
```

Do not calculate expensive hashes unnecessarily on every scan.

---

# 15. Interrupted Transfer and Resume

If Wi-Fi disconnects:

```text
Transfer
   ↓
Wi-Fi disconnected
   ↓
Pause
   ↓
Wi-Fi restored
   ↓
Resume
```

Handle:

- Wi-Fi disconnect
- PC shutdown
- Android interruption
- PC sleep
- Android battery restrictions
- Partial files
- Corrupted transfers

Use temporary files:

```text
IMG_1234.jpg.part
```

After successful verification:

```text
IMG_1234.jpg
```

Never mark a photo as backed up before successful completion and verification.

---

# 16. Photo Folder Organization

Default organization should be useful.

For example:

```text
PhotoSync/
└── 2026/
    └── 09/
        └── IMG_1234.jpg
```

Allow future configuration for:

- Year/month
- Year/month/day
- Original filename
- Device name
- Custom folder structure

Never modify original Android files.

---

# 17. Windows UI

Build a beautiful modern PySide6 interface.

Main dashboard:

```text
PhotoSync                              ⚙

Connected Device
──────────────────────────────────────
📱 My Android Phone
● Connected • Same Wi-Fi

Backup
──────────────────────────────────────
1,248 Photos
8.4 GB

██████████████░░░░ 78%

156 / 200 photos

Destination
──────────────────────────────────────
D:\Pictures\PhotoSync

[ Open Folder ]

Last Backup
──────────────────────────────────────
Today • 9:21 AM
```

Pages:

- Dashboard
- Devices
- Backup History
- Settings
- About

Include:

- Connection state
- Transfer state
- Progress
- Number of files
- Amount transferred
- Last backup
- Destination
- Errors
- Empty states
- Loading states

Use:

- Modern typography
- Consistent spacing
- Icons
- Rounded cards where appropriate
- Subtle animations
- Good visual hierarchy
- Light/dark theme

Avoid old-fashioned WinForms-style design.

---

# 18. Android UI

Use Jetpack Compose.

Main screen:

```text
PhotoSync

📱 My Android Phone

● Connected to Windows PC

Automatic Backup
                 ON

Photos
1,248

Backed Up
1,120

Pending
128

[ Backup Now ]

Last Backup
Today • 9:21 AM
```

Include:

- Permission status
- Wi-Fi status
- PC connection
- Automatic backup
- Progress
- Pending count
- Last backup
- Settings
- Trusted PC

Keep the interface simple.

---

# 19. Android Background Operation

Respect modern Android background-execution and battery policies.

Do not assume an Android process can run forever in the background.

Use appropriate mechanisms such as:

- Foreground service where justified
- WorkManager for appropriate scheduled work
- Network availability constraints
- Battery-aware behavior

The user should be guided if Android battery optimization prevents reliable background backup.

Do not promise impossible background behavior.

---

# 20. Windows Startup and System Tray

Provide:

```text
Start PhotoSync with Windows     ON
Run in background                ON
Automatic backup                 ON
```

Support system tray:

```text
PhotoSync

Open
Pause Backup
Resume Backup
Settings
Exit
```

Do not consume unnecessary resources when no device is available.

---

# 21. SQLite Database

Use SQLite on Windows.

Suggested tables:

```text
devices
photos
transfers
settings
```

Example:

```text
devices
--------------------------------
id
device_id
name
platform
public_key
paired_at
last_seen
is_trusted
```

```text
photos
--------------------------------
id
device_id
media_id
filename
file_size
date_taken
content_hash
destination_path
status
created_at
completed_at
```

```text
transfers
--------------------------------
id
photo_id
started_at
completed_at
bytes_transferred
status
error_message
```

```text
settings
--------------------------------
key
value
```

Use schema migrations.

Do not store secrets in source code.

---

# 22. Transfer Protocol

Create a small documented protocol.

Example:

```text
DISCOVERY
PAIR_REQUEST
PAIR_RESPONSE
AUTHENTICATE
SYNC_REQUEST
SYNC_RESPONSE
TRANSFER_START
TRANSFER_CHUNK
TRANSFER_COMPLETE
TRANSFER_VERIFY
SYNC_COMPLETE
```

Use REST plus WebSocket where appropriate.

Version the protocol:

```text
protocol_version = 1
```

---

# 23. Software Update System

The Windows app must check your official update API periodically.

Example:

```text
GET /api/v1/updates/latest?platform=windows&architecture=x64
```

Example response:

```json
{
  "version": "1.1.0",
  "minimum_supported_version": "1.0.0",
  "release_date": "2026-09-15",
  "mandatory": false,
  "title": "PhotoSync 1.1.0",
  "message": "Improved transfer reliability and performance.",
  "download_url": "https://YOUR-DOMAIN.example/downloads/PhotoSync-1.1.0.exe",
  "release_notes_url": "https://YOUR-DOMAIN.example/releases/1.1.0",
  "sha256": "..."
}
```

Do not hardcode the real production domain.

Use:

```text
API_BASE_URL
UPDATE_BASE_URL
```

Use proper semantic version comparison.

Example:

```text
1.10.0 > 1.9.0
```

---

# 24. New Version Windows Notification

When a new version is available:

```text
PhotoSync

PhotoSync 1.1.0 is now available.

Improved transfer speed and reliability.

[ View Update ]
```

Clicking should show:

```text
A new version is available

PhotoSync 1.1.0

What's new:
• Faster photo transfers
• Better Wi-Fi reconnection
• Improved reliability

[ Update Now ] [ Later ]
```

Do not repeatedly nag about the same version after Later.

Add Settings:

```text
Check for updates automatically     ON
Notify me about new versions       ON
```

---

# 25. Secure Updates

Never blindly execute downloaded files.

Before an update:

1. Download over HTTPS.
2. Verify SHA-256.
3. Prefer digitally signed Windows releases.
4. Verify Authenticode signature where practical.
5. Reject failed verification.
6. Preserve configuration.
7. Preserve SQLite database.
8. Preserve installation ID.
9. Preserve trusted devices.
10. Use a separate updater process when replacing the running executable.

Update failure must not destroy the existing installation.

---

# 26. Windows Installer

Create a proper installer.

Use:

- PyInstaller for application packaging
- Inno Setup or equivalent for installation

Installer should:

- Install application
- Create Start Menu shortcut
- Optionally create desktop shortcut
- Offer startup behavior
- Not store photos in Program Files
- Preserve user data
- Handle upgrades

First launch:

```text
Install
 ↓
Welcome
 ↓
Register
 ↓
Choose Photo Backup Folder
 ↓
Ready
 ↓
Pair Android
```

---

# 27. Python Desktop Architecture

Suggested structure:

```text
PhotoSync/
├── desktop/
│   ├── main.py
│   ├── app.py
│   │
│   ├── ui/
│   │   ├── windows/
│   │   ├── pages/
│   │   ├── dialogs/
│   │   ├── widgets/
│   │   ├── resources/
│   │   └── styles/
│   │
│   ├── core/
│   │   ├── models/
│   │   ├── services/
│   │   ├── interfaces/
│   │   └── protocol/
│   │
│   └── infrastructure/
│       ├── database/
│       ├── networking/
│       ├── discovery/
│       ├── storage/
│       ├── security/
│       └── configuration/
│
├── android/
│
├── tests/
│   ├── unit/
│   └── integration/
│
├── installer/
├── pyproject.toml
├── requirements.txt
└── README.md
```

Do not put networking/database logic directly into PySide6 widgets.

---

# 28. PySide6 Rules

1. Never block the GUI thread.
2. File transfers must run in background workers.
3. Network operations must not freeze the UI.
4. Gallery synchronization must not freeze the UI.
5. Hashing must run outside the GUI thread.
6. Use signals/slots for worker-to-UI communication.
7. Make long-running operations cancellable.
8. Never use `time.sleep()` on the GUI thread.
9. Use `pathlib`.
10. Handle SQLite thread safety correctly.
11. Keep UI and business logic separate.
12. Test the PyInstaller executable, not only source execution.

---

# 29. Reliability

Handle:

- PC unavailable
- Android unavailable
- Wrong Wi-Fi
- IP changes
- Permission denied
- Destination folder deleted
- Drive disconnected
- Insufficient disk space
- Duplicate filename
- Partial file
- File changed during transfer
- Android restart
- Windows restart
- PC sleep
- Wi-Fi interruption
- Large galleries
- Thousands of photos
- Large videos if video support is added

One bad file must never crash the entire backup.

---

# 30. Performance

Support large galleries efficiently.

Use:

- Incremental MediaStore scanning
- Pagination
- Streaming
- Chunked transfers
- Bounded concurrency
- Background processing
- Efficient SQLite queries

Do not load thousands of full-resolution images into memory.

---

# 31. Logging

Implement structured logging.

Log useful diagnostic events:

- Discovery
- Pairing
- Connection
- Authentication
- Sync
- Transfer failures
- Folder errors
- Permission problems

Never log:

- Passwords
- Private keys
- Authentication tokens
- Sensitive personal information

Provide a way to export diagnostic logs.

---

# 32. Privacy

Provide a Privacy Policy link during registration.

Clearly explain:

- Name collection
- Email collection
- Desktop username collection
- IP address collection
- Purpose of collection
- Retention
- Administrative access
- Update notifications
- User deletion rights where applicable

Do not collect information unrelated to the product.

Keep telemetry separate from photo transfer.

If the telemetry/update server is unavailable:

```text
Server unavailable
       ↓
Retry later
       ↓
PhotoSync still works
```

Registration/telemetry must never prevent photo backup.

---

# 33. Admin Dashboard

Create a private authenticated server dashboard.

Useful statistics:

```text
Total installations
Active installations
New installations today
New installations this week
Version distribution
Old versions
Operating system distribution
Last seen
```

Example:

```text
PhotoSync Installations

Total:          1,284
Active:         1,041
Version 1.1.0:    812
Version 1.0.0:    229
```

Never expose this data publicly.

---

# 34. Security

Use:

- HTTPS
- Server-side validation
- Rate limiting
- Request limits
- Parameterized SQL/ORM
- Secure authentication
- Secure local device pairing
- Secure update verification
- No database credentials in client
- No private API secrets in executable
- Protected admin dashboard

Do not disable certificate validation as a shortcut.

---

# 35. Testing

## Unit tests

Test:

- Duplicate detection
- Version comparison
- Folder organization
- Sync state
- Transfer state machine
- Retry logic
- Settings persistence

## Integration tests

Test:

- SQLite
- Discovery
- Pairing
- Authentication
- File transfer
- Interrupted transfer
- Resume
- Verification
- Registration API
- Update API

## Manual tests

Test:

- Fresh Windows install
- First-run registration
- Folder selection
- Folder change
- Android permission granted
- Permission denied
- Pairing
- Same Wi-Fi
- Different Wi-Fi
- Wi-Fi disconnect during transfer
- PC sleep/wake
- Android restart
- Windows restart
- Destination drive unavailable
- Large gallery
- Update notification
- Update installation

---

# 36. Development Phases

## Phase 1 — Foundation

- Windows Python project
- PySide6 shell
- Android project
- Navigation
- Theme
- Logging
- Dependencies

## Phase 2 — Windows Setup

- First-run flow
- Registration
- Folder picker
- Folder validation
- Settings persistence
- Destination settings

## Phase 3 — Discovery

- mDNS/NSD
- Device discovery
- Connection status

## Phase 4 — Pairing

- QR/pairing code
- Device identity
- Trust storage
- Authentication

## Phase 5 — Basic Transfer

- MediaStore scan
- Metadata
- Transfer queue
- Windows receiver
- File saving

## Phase 6 — Incremental Sync

- SQLite
- Backup state
- Duplicate detection
- New-photo-only transfer

## Phase 7 — Reliability

- Resume
- Retry
- Partial files
- Verification
- Reconnection

## Phase 8 — Automatic Backup

- Same-Wi-Fi detection
- Background behavior
- Automatic synchronization
- Notifications

## Phase 9 — Updates

- Update API
- Version comparison
- Windows notifications
- Secure download
- Update verification
- Updater

## Phase 10 — UI Polish

- Animations
- Empty states
- Error states
- Light/dark mode
- Responsive layouts
- Icons
- Progress visualization

## Phase 11 — Installer and Release

- PyInstaller
- Windows installer
- Startup
- System tray
- Upgrade testing
- Documentation

---

# 37. Development Rules

Before coding:

1. Inspect the existing repository/project.
2. Identify technologies and current structure.
3. Create an implementation plan.
4. Identify risks.
5. Identify Android background limitations.
6. Identify Windows packaging requirements.
7. Identify security/privacy requirements.
8. Then implement incrementally.

Do NOT immediately generate the entire application.

At each major phase:

- Build Windows app.
- Build Android app.
- Run tests.
- Fix compilation/runtime errors.
- Summarize implementation.
- State remaining work.

Do not use fake/mock functionality in the final implementation unless clearly isolated as a development stub.

Do not hardcode:

- IP addresses
- Backup folders
- Credentials
- API secrets
- Production database credentials
- Production domain

Do not make telemetry mandatory for core photo backup unless the product/legal requirements explicitly require it and the UI clearly communicates this.

---

# 38. First Task for Claude

Start by inspecting the repository and environment.

Do NOT immediately build the whole application.

First return:

1. Current project structure
2. Detected technologies
3. Recommended architecture
4. Recommended Python/PySide6 structure
5. Android architecture
6. Server/API architecture
7. Database architecture
8. Update architecture
9. Security/privacy risks
10. Implementation phases
11. Exact first implementation step

Then begin with the smallest sensible implementation step and verify it builds/runs before moving forward.

The final product should be:

**Beautiful + Native-feeling + Secure + Reliable + Fast + Maintainable + Production-ready.**
