; DocAnalyser Inno Setup Script
; ================================
; This script creates a Windows installer for DocAnalyser
;
; To build the installer:
; 1. Install Inno Setup from https://jrsoftware.org/isinfo.php
; 2. Open this file in Inno Setup Compiler
; 3. Click Build > Compile (or press Ctrl+F9)
; 4. The installer will be created in the Output folder

#define MyAppName "DocAnalyser"
#define MyAppVersion "1.2.0"
#define MyAppPublisher "Ian Lucas"
#define MyAppURL "https://github.com/ilucas1a/DocAnalyser-beta"
#define MyAppExeName "DocAnalyser.exe"

; Path to PyInstaller dist output
#define SourcePath "C:\Ian\Python\GetTextFromYouTube\DocAnalyzer_DEV\dist\DocAnalyser"

; Path to the .ico file (in the installer folder)
#define IconPath "C:\Ian\Python\GetTextFromYouTube\DocAnalyzer_DEV\installer\DocAnalyzer.ico"

[Setup]
; Unique AppId - generated GUID for this application
; IMPORTANT: Do not change this between versions, or Windows will treat updates as separate apps
AppId={{7F3A9B2E-4D1C-4E8F-B6A5-2C9D0E7F1A3B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

; Installation directories
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}

; Output settings
OutputDir=C:\Ian\Python\GetTextFromYouTube\DocAnalyzer_DEV\installer\output
OutputBaseFilename=DocAnalyser_Setup_{#MyAppVersion}

; Compression (lzma2 gives best compression)
Compression=lzma2
SolidCompression=yes

; Installer appearance
SetupIconFile={#IconPath}
UninstallDisplayIcon={app}\{#MyAppExeName}
WizardStyle=modern

; Privileges (don't require admin unless necessary)
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

; Allow user to choose install location
DisableProgramGroupPage=yes

; Minimum Windows version (Windows 10)
MinVersion=10.0

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Main application and all files from the dist folder
Source: "{#SourcePath}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Start Menu shortcut
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"

; Desktop shortcut (if selected during install)
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; Option to run the app after installation
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Clean up any cache files created inside the install folder (if any)
Type: filesandordirs; Name: "{app}\cache"
Type: filesandordirs; Name: "{app}\logs"

[Code]
// Offer to remove user data on uninstall
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{userappdata}\DocAnalyser_Beta');
    if DirExists(DataDir) then
    begin
      if MsgBox('Do you want to remove your DocAnalyser settings and document library?' + #13#10 + #13#10 +
                'Location: ' + DataDir + #13#10 + #13#10 +
                'Click No to keep your data (recommended if you plan to reinstall).',
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
      begin
        DelTree(DataDir, True, True, True);
      end;
    end;
  end;
end;
