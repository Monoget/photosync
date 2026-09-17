; Inno Setup script for PixSynq.
; Build the PyInstaller bundle first (see build.ps1), then compile this.

#define AppName "PixSynq"
#define AppVersion "0.1.1"
#define AppExe "PixSynq.exe"

[Setup]
AppId={{8F4B7C64-52A1-4C3B-9E1D-PixSynq001}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=PixSynq
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputBaseFilename=PixSynq-{#AppVersion}-Setup
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
Source: "..\dist\PixSynq\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

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
