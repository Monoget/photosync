; Inno Setup script for PhotoSync.
; Build the PyInstaller bundle first (see build.ps1), then compile this.

#define AppName "PhotoSync"
#define AppVersion "0.1.0"
#define AppExe "PhotoSync.exe"

[Setup]
AppId={{8F4B7C64-52A1-4C3B-9E1D-PhotoSync001}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=PhotoSync
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputBaseFilename=PhotoSync-{#AppVersion}-Setup
OutputDir=output
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
; User data (settings, DB, photos) lives outside Program Files and is
; never touched by install or uninstall.
UninstallDisplayIcon={app}\{#AppExe}
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; Flags: unchecked
Name: "startup"; Description: "Start {#AppName} when Windows starts"; Flags: unchecked

[Files]
Source: "..\dist\PhotoSync\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
    ValueType: string; ValueName: "{#AppName}"; ValueData: """{app}\{#AppExe}"""; \
    Flags: uninsdeletevalue; Tasks: startup

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch {#AppName}"; \
    Flags: nowait postinstall skipifsilent
