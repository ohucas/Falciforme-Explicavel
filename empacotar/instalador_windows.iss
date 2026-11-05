; Compile depois de gerar dist\FalciformeExplicavel no Windows.
#define NomeApp "Falciforme Explicável"
#define VersaoApp "0.4.0"

[Setup]
AppId={{A8707C40-F6AD-40BD-BEE1-00A26D8F7901}
AppName={#NomeApp}
AppVersion={#VersaoApp}
DefaultDirName={localappdata}\Programs\FalciformeExplicavel
DefaultGroupName={#NomeApp}
PrivilegesRequired=lowest
OutputDir=..\instalador
OutputBaseFilename=InstalarFalciformeExplicavel
SetupIconFile=..\assets\icone.ico
UninstallDisplayIcon={app}\FalciformeExplicavel.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Files]
Source: "..\dist\FalciformeExplicavel\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userdesktop}\{#NomeApp}"; Filename: "{app}\FalciformeExplicavel.exe"; WorkingDir: "{app}"
Name: "{userprograms}\{#NomeApp}"; Filename: "{app}\FalciformeExplicavel.exe"; WorkingDir: "{app}"

[Run]
Filename: "{app}\FalciformeExplicavel.exe"; Description: "Abrir {#NomeApp}"; Flags: nowait postinstall skipifsilent
