#ifndef AppVersion
  #error AppVersion must be supplied by tools/build_installer.py
#endif
#ifndef PayloadDir
  #error PayloadDir must be supplied by tools/build_installer.py
#endif

[Setup]
AppId={{24381849-02DB-4FCB-A70B-DF2A33C0A864}
AppName=Aki's Rockbox Scrobbler
AppVersion={#AppVersion}
AppPublisher=Achilleus
AppPublisherURL=https://github.com/Achilleus-1
AppSupportURL=https://github.com/Achilleus-1/Akis-Rockbox-Scrobbler/issues
AppUpdatesURL=https://github.com/Achilleus-1/Akis-Rockbox-Scrobbler/releases
DefaultDirName={localappdata}\Programs\Akis-Rockbox-Scrobbler
DefaultGroupName=Aki's Rockbox Scrobbler
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\dist
OutputBaseFilename=Akis-Rockbox-Scrobbler-{#AppVersion}-windows-x64-setup
SetupIconFile=..\assets\app.ico
UninstallDisplayIcon={app}\Akis-Rockbox-Scrobbler.exe
LicenseFile=..\LICENSE
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no

[Tasks]
Name: desktopicon; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "{#PayloadDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Aki's Rockbox Scrobbler"; Filename: "{app}\Akis-Rockbox-Scrobbler.exe"
Name: "{autodesktop}\Aki's Rockbox Scrobbler"; Filename: "{app}\Akis-Rockbox-Scrobbler.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Akis-Rockbox-Scrobbler.exe"; Description: "Launch Aki's Rockbox Scrobbler"; Flags: nowait postinstall skipifsilent

; User data in {localappdata}\RockboxRelay is deliberately preserved on uninstall.
