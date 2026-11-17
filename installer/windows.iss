; Build on Windows with Inno Setup 6.3+. Never contains a router key.
#ifndef AppVersion
  #define AppVersion "0.7.5"
#endif
#ifndef ReleaseDir
  #error ReleaseDir is required
#endif
#ifndef ArtifactDir
  #error ArtifactDir is required
#endif
[Setup]
AppId={{F77206AD-8049-4B46-B591-13310985F1AE}
AppName=Photonicat
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\Photonicat
DefaultGroupName=Photonicat
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#ArtifactDir}
OutputBaseFilename=Photonicat-{#AppVersion}-Windows-x64-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\photonicat.exe
CloseApplications=yes
[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; Flags: unchecked
Name: "autostart"; Description: "{cm:StartupTask}"; Flags: unchecked
[CustomMessages]
english.StartupTask=Start Photonicat when I sign in (tray icon only)
russian.StartupTask=Запускать Photonicat при входе в систему (только значок в трее)
[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Photonicat"; ValueData: """{app}\photonicat.exe"" --autostart"; Tasks: autostart; Flags: uninsdeletevalue
[Files]
Source: "{#ReleaseDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{autoprograms}\Photonicat"; Filename: "{app}\photonicat.exe"
Name: "{autodesktop}\Photonicat"; Filename: "{app}\photonicat.exe"; Tasks: desktopicon
[Run]
Filename: "{app}\photonicat.exe"; Description: "{cm:LaunchProgram,Photonicat}"; Flags: nowait postinstall skipifsilent
[Code]
var StartupTaskInitialized: Boolean;

function OwnStartupEntry: Boolean;
var Value: String;
begin
  Result := RegQueryStringValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'Photonicat', Value)
    and (CompareText(Value, ExpandConstant('"{app}\photonicat.exe" --autostart')) = 0);
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if (CurPageID = wpSelectTasks) and not StartupTaskInitialized and not WizardSilent then begin
    StartupTaskInitialized := True;
    if OwnStartupEntry then WizardSelectTasks('autostart')
    else WizardSelectTasks('!autostart');
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssPostInstall) and not WizardIsTaskSelected('autostart') and OwnStartupEntry then
    RegDeleteValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'Photonicat');
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if (CurUninstallStep = usUninstall) and OwnStartupEntry then
    RegDeleteValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'Photonicat');
end;
