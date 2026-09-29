#define AppName "Creator Partnership Platform"
#ifndef SourceDir
  #define SourceDir "..\..\dist\windows\CreatorPartnershipPlatform"
#endif

[Setup]
AppId={{2AA86CDF-9A70-46CB-92E1-3D9ED2A72A50}
AppName={#AppName}
AppVersion=1.0.0
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
OutputDir=..\..\dist\windows
OutputBaseFilename=CreatorPartnershipPlatform-Setup
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\{#AppName}"; Filename: "{app}\CreatorPartnershipPlatform.exe"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\CreatorPartnershipPlatform.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Run]
Filename: "{app}\CreatorPartnershipPlatform.exe"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Remove installed program files only. User data under {localappdata}\Capgemini\CreatorPartnershipPlatform is preserved.
Type: filesandordirs; Name: "{app}"
