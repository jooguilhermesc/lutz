; Lutz Research — Inno Setup installer script
; Docs: https://jrsoftware.org/ishelp/

#define AppName      "Lutz Research"
#define AppVersion   "0.3.0"
#define AppPublisher "João Guilherme"
#define AppURL       "https://github.com/jooguilhermesc/lutz"
#define AppSupportURL "https://github.com/jooguilhermesc/lutz/issues"
#define AppExeName   "lutz.exe"
#define AppLauncherName "lutz-ui.exe"

[Setup]
AppId={{B3F2A1D7-4E8C-4F1B-9A2E-1C3D5E7F9B0A}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppSupportURL}
AppUpdatesURL={#AppURL}/releases
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
AllowNoIcons=yes
LicenseFile=..\..\LICENSE
OutputDir=..\..\dist\installer
OutputBaseFilename=lutz-setup-windows-x64
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
WizardSizePercent=110
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\{#AppExeName}
ChangesEnvironment=yes

[Languages]
Name: "english";            MessagesFile: "compiler:Default.isl"
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon";    Description: "Criar atalho na Área de Trabalho";   GroupDescription: "Atalhos adicionais:"; Flags: unchecked
Name: "addtopath";      Description: "Adicionar lutz ao PATH do sistema";  GroupDescription: "Opções avançadas:";   Flags: unchecked

[Files]
; Main CLI binary (PyInstaller one-file output)
Source: "..\..\dist\lutz.exe"; DestDir: "{app}"; Flags: ignoreversion

; Silent launcher: opens lutz web + browser without showing a console window
Source: "lutz-ui.exe";         DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

[Icons]
; Start Menu
Name: "{group}\{#AppName}";                   Filename: "{app}\{#AppLauncherName}"; \
      Comment: "Abrir a interface web do Lutz Research"
Name: "{group}\Lutz (linha de comando)";       Filename: "{app}\{#AppExeName}"; \
      Comment: "Lutz Research — CLI"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"

; Desktop icon (optional task)
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppLauncherName}"; Tasks: desktopicon

[Registry]
; Add to PATH if the user opted in
Root: HKCU; Subkey: "Environment"; ValueType: expandsz; ValueName: "Path"; \
     ValueData: "{olddata};{app}"; Check: NeedsAddPath('{app}'); Tasks: addtopath

[Run]
; Offer to launch the app immediately after installation
Filename: "{app}\{#AppLauncherName}"; \
     Description: "Abrir o {#AppName} agora"; \
     Flags: nowait postinstall skipifsilent unchecked

[UninstallRun]
; Make sure no lutz server is running when uninstalling
Filename: "taskkill"; Parameters: "/F /IM lutz.exe /IM lutz-ui.exe"; \
     Flags: runhidden skipifdoesntexist

[Code]
// Helper: checks whether the given path is already in the user PATH.
function NeedsAddPath(Param: string): boolean;
var
  OrigPath: string;
begin
  if not RegQueryStringValue(HKEY_CURRENT_USER, 'Environment', 'Path', OrigPath) then
  begin
    Result := True;
    exit;
  end;
  Result := Pos(';' + Uppercase(Param) + ';', ';' + Uppercase(OrigPath) + ';') = 0;
end;
