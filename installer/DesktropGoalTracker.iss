#define AppName "DesktropGoalTracker"
#define AppVersion "0.1.1"
#define AppExe "DesktropGoalTracker.exe"

[Setup]
AppId={{96B13F90-BFEF-4D70-A27B-F5EDB23F7B35}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=DesktropGoalTracker
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\dist
OutputBaseFilename=DesktropGoalTracker-Setup-0.1.1
SetupIconFile=..\sysadmin-codex\widget\app-icon.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
AppMutex=Local\DesktropGoalTrackerTray
VersionInfoVersion={#AppVersion}.0
VersionInfoDescription=Installazione DesktropGoalTracker

[Languages]
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"

[Tasks]
Name: "autostart"; Description: "Avvia DesktropGoalTracker con Windows"; GroupDescription: "Opzioni di avvio:"
Name: "desktopicon"; Description: "Crea un collegamento sul desktop"; GroupDescription: "Collegamenti:"; Flags: unchecked

[Files]
Source: "..\dist\DesktropGoalTracker\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\DesktropGoalTracker"; Filename: "{app}\{#AppExe}"; Parameters: "--tray"; WorkingDir: "{app}"
Name: "{autodesktop}\DesktropGoalTracker"; Filename: "{app}\{#AppExe}"; Parameters: "--tray"; WorkingDir: "{app}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "DesktropGoalTracker"; ValueData: """{app}\{#AppExe}"" --tray"; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\{#AppExe}"; Parameters: "--tray"; Description: "Avvia DesktropGoalTracker"; Flags: nowait postinstall skipifsilent
