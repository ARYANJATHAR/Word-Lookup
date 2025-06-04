[Setup]
AppName=Word Lookup
AppVersion=1.0
DefaultDirName={pf}\Word Lookup
DefaultGroupName=Word Lookup
OutputDir=installer
OutputBaseFilename=WordLookupSetup
SetupIconFile=app_icon.ico
UninstallDisplayIcon={app}\Word Lookup.exe
PrivilegesRequired=admin

[Files]
Source: "dist\Word Lookup.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "app_icon.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: ".env"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Word Lookup"; Filename: "{app}\Word Lookup.exe"
Name: "{commondesktop}\Word Lookup"; Filename: "{app}\Word Lookup.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Run]
Filename: "{app}\Word Lookup.exe"; Description: "Launch Word Lookup"; Flags: postinstall nowait runascurrentuser