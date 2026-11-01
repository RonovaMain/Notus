; Notus — Inno Setup script.
; Built by CI:  ISCC.exe /DMyAppVersion=<version> installer\installer.iss
; Input : dist\Notus\   (PyInstaller --onedir output + backend\ with llama-server and the CUDA/MSVC DLLs)
; Output: Output\Notus-Setup-<version>.exe

#define MyAppName "Notus"
#ifndef MyAppVersion
  #define MyAppVersion "0.1.0"
#endif
#define MyAppPublisher "RonovaDev"
; TODO: put the real link to your repository here (same as REPO_URL in notus/__init__.py)
#define MyAppURL "https://github.com/RonovaMain/Notus"
#define MyAppExeName "Notus.exe"
#define SourceDir "..\dist\Notus"

[Setup]
AppId={{79A788D8-C80A-4A05-9436-D1C232D1D1F1}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
; Per-user install by default (no admin rights, nothing outside the app folder);
; the user may still choose "for all users" in the first dialog.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\Output
OutputBaseFilename=Notus-Setup-{#MyAppVersion}
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/max
SolidCompression=yes
LZMANumBlockThreads=4
WizardStyle=modern
CloseApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; Everything is copied into the app folder: Python runtime, Qt, llama.cpp backend (Vulkan + CPU variants) and
; Visual C++ runtime DLLs. Nothing is installed system-wide and nothing is written to the registry
; (except the uninstall entry that Windows itself needs).
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{autoprograms}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Chats, settings and the model list live in %APPDATA%\Notus and are kept on purpose.
Type: filesandordirs; Name: "{app}"

[CustomMessages]
english.NoVulkan=No Vulkan graphics driver was detected, so Notus will run in CPU-only mode.%nAfter you install or update your graphics driver, GPU acceleration starts working without reinstalling Notus.
russian.NoVulkan=Графический драйвер с поддержкой Vulkan не найден, поэтому Notus будет работать только на процессоре.%nПосле установки или обновления драйвера видеокарты ускорение заработает без переустановки Notus.

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssPostInstall) and (not WizardSilent) then
    if not FileExists(ExpandConstant('{sys}\vulkan-1.dll')) then
      MsgBox(CustomMessage('NoVulkan'), mbInformation, MB_OK);
end;
