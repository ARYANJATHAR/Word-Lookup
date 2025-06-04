#define MyAppName "Word Lookup"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Word Lookup"
#define MyAppURL "https://github.com/ARYANJATHAR/QuickWord-AI"
#define MyAppExeName "Word Lookup.exe"

[Setup]
; Basic application information
AppId={{F7A6B47E-0277-4E60-9C4B-F2A76C6E0513}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases

; Directories
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
OutputDir=installer
OutputBaseFilename=WordLookup_Setup_{#MyAppVersion}

; Visual settings
SetupIconFile=app_icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}

; Other settings
Compression=lzma2/ultra64
SolidCompression=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
AllowNoIcons=yes
ShowLanguageDialog=no
DisableWelcomePage=no
DisableProgramGroupPage=yes
CloseApplications=force

; Sign the installer if you have a code signing certificate
; SignTool=signtool sign /f "$certfile" /p "$password" /t http://timestamp.digicert.com $f

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "quicklaunchicon"; Description: "{cm:CreateQuickLaunchIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "startup"; Description: "Start Word Lookup automatically at Windows startup"; GroupDescription: "Windows Startup"

[Files]
; Main application files
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "app_icon.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion isreadme

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{userappdata}\Microsoft\Internet Explorer\Quick Launch\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: quicklaunchicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#MyAppName}"; ValueData: """{app}\{#MyAppExeName}"""; Flags: uninsdeletevalue; Tasks: startup

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent runascurrentuser

[UninstallRun]
Filename: "taskkill.exe"; Parameters: "/f /im ""{#MyAppExeName}"""; Flags: runhidden; RunOnceId: "KillApp"

[Code]
var
  IsUpgrade: Boolean;

function InitializeSetup(): Boolean;
var
  ResultCode: Integer;
  PrevPath: String;
begin
  // Check if app is running and close it
  if FindWindowByClassName('Word Lookup') <> 0 then
  begin
    Exec('taskkill.exe', '/f /im "{#MyAppExeName}"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end;

  // Check if this is an upgrade
  if RegQueryStringValue(HKLM, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{#SetupSetting("AppId")}_is1',
    'UninstallString', PrevPath) then
  begin
    IsUpgrade := True;
  end else
  begin
    IsUpgrade := False;
  end;

  Result := True;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    // Additional post-install tasks if needed
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  AppDataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    // Clean up app data if user confirms
    if MsgBox('Do you want to remove all application data and settings?',
      mbConfirmation, MB_YESNO) = IDYES then
    begin
      AppDataDir := ExpandConstant('{userappdata}') + '\Word Lookup';
      DelTree(AppDataDir, True, True, True);
    end;
  end;
end;