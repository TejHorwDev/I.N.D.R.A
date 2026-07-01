[Setup]
AppName=INDRA AI
AppVersion=1.0
AppPublisher=Avash Lab
DefaultDirName={autopf}\INDRA
DefaultGroupName=INDRA AI
UninstallDisplayIcon={app}\INDRA.exe
Compression=lzma2
SolidCompression=yes
OutputDir=dist
OutputBaseFilename=INDRA_Setup_v1.1
PrivilegesRequired=lowest

[Files]
Source: "build_dist\INDRA\INDRA.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "build_dist\INDRA\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\INDRA AI"; Filename: "{app}\INDRA.exe"
Name: "{autodesktop}\INDRA AI"; Filename: "{app}\INDRA.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop icon"; GroupDescription: "Additional icons:"

[Run]
Filename: "{app}\INDRA.exe"; Description: "Launch INDRA AI"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{userappdata}\INDRA"
