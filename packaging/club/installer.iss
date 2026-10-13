; Modified 2026-10-13: standalone, per-user PhotoLab Club distribution.
#ifndef StageDir
  #define StageDir "stage"
#endif
#ifndef ReleaseDir
  #define ReleaseDir "release"
#endif
[Setup]
AppId={{8B88B8B3-3ED0-4F35-9CC7-76D9C1842CB0}
AppName=PhotoLab Club Briançonnais
AppVersion=0.5.0
AppVerName=PhotoLab Club Briançonnais 0.5.0
AppPublisher=PhotoLab Club — projet indépendant
AppPublisherURL=https://github.com/bouyous/photolab-club-brianconnais
AppSupportURL=https://github.com/bouyous/photolab-club-brianconnais/issues
AppUpdatesURL=https://github.com/bouyous/photolab-club-brianconnais/releases
DefaultDirName={localappdata}\Programs\PhotoLabClub
DefaultGroupName=PhotoLab Club Briançonnais
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\lightcraft.exe
SetupIconFile=..\..\assets\club\club.ico
LicenseFile={#StageDir}\LICENSE-APACHE
InfoBeforeFile=INSTALLATION.txt
OutputDir={#ReleaseDir}
OutputBaseFilename=PhotoLab-Club-0.5.0-Windows-x64-Setup
Compression=lzma2/normal
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
VersionInfoVersion=0.5.0.0
VersionInfoDescription=PhotoLab Club Briançonnais — installateur Windows

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "Créer un raccourci sur le bureau"; GroupDescription: "Raccourcis :"; Flags: unchecked

[Files]
Source: "{#StageDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\PhotoLab Club Briançonnais"; Filename: "{app}\lightcraft.exe"; WorkingDir: "{app}"
Name: "{group}\Licences et modifications"; Filename: "{app}\LICENCES-CLUB.md"
Name: "{group}\Désinstaller PhotoLab Club"; Filename: "{uninstallexe}"
Name: "{autodesktop}\PhotoLab Club Briançonnais"; Filename: "{app}\lightcraft.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\lightcraft.exe"; Description: "Lancer PhotoLab Club Briançonnais"; Flags: nowait postinstall skipifsilent
