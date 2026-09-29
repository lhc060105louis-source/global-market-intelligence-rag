#define AppName "KOL合作管理平台"
#ifndef SourceDir
  #define SourceDir "..\..\dist\windows\KOL合作管理平台"
#endif

[Setup]
AppId={{2AA86CDF-9A70-46CB-92E1-3D9ED2A72A50}
AppName={#AppName}
AppVersion=1.0.0
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
OutputDir=..\..\dist\windows
OutputBaseFilename=KOL合作管理平台-Setup
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\{#AppName}"; Filename: "{app}\{#AppName}.exe"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#AppName}.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; Flags: unchecked

[Run]
Filename: "{app}\{#AppName}.exe"; Description: "启动 {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Remove installed program files only. User data under {localappdata}\KOL合作管理平台 is intentionally preserved.
Type: filesandordirs; Name: "{app}"
