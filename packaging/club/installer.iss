; Modified 2026-10-13: standalone, per-user PhotoLab Club distribution.
#ifndef StageDir
  #define StageDir "stage"
#endif
#ifndef ReleaseDir
  #define ReleaseDir "release"
#endif
[Setup]
AppId={{8B88B8B3-3ED0-4F35-9CC7-76D9C1842CB0}
AppName=Laboratoire du Photo Club Briançonnais
AppVersion=0.5.1
AppVerName=Laboratoire du Photo Club Briançonnais 0.5.1
AppPublisher=Laboratoire du Photo Club Briançonnais — projet indépendant
AppPublisherURL=https://github.com/bouyous/laboratoire-photo-club-brianconnais
AppSupportURL=https://github.com/bouyous/laboratoire-photo-club-brianconnais/issues
AppUpdatesURL=https://github.com/bouyous/laboratoire-photo-club-brianconnais/releases
DefaultDirName={localappdata}\Programs\PhotoLabClub
DefaultGroupName=Laboratoire du Photo Club Briançonnais
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
DisableProgramGroupPage=yes
UsePreviousGroup=no
UninstallDisplayIcon={app}\lightcraft.exe
SetupIconFile=..\..\assets\club\club.ico
LicenseFile={#StageDir}\LICENSE-APACHE
InfoBeforeFile=INSTALLATION.txt
OutputDir={#ReleaseDir}
OutputBaseFilename=Laboratoire-Photo-Club-0.5.1-Windows-x64-Setup
Compression=lzma2/normal
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
VersionInfoVersion=0.5.1.0
VersionInfoDescription=Laboratoire du Photo Club Briançonnais — installateur Windows

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "Créer un raccourci sur le bureau"; GroupDescription: "Raccourcis :"; Flags: unchecked

[Files]
Source: "{#StageDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Laboratoire du Photo Club Briançonnais"; Filename: "{app}\lightcraft.exe"; WorkingDir: "{app}"
Name: "{group}\Licences et modifications"; Filename: "{app}\LICENCES-CLUB.md"
Name: "{group}\Désinstaller le Laboratoire du club"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Laboratoire du Photo Club Briançonnais"; Filename: "{app}\lightcraft.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\lightcraft.exe"; Description: "Lancer Laboratoire du Photo Club Briançonnais"; Flags: nowait postinstall skipifsilent

[InstallDelete]
Type: files; Name: "{userprograms}\PhotoLab Club Briançonnais\PhotoLab Club Briançonnais.lnk"
Type: files; Name: "{userprograms}\PhotoLab Club Briançonnais\Licences et modifications.lnk"
Type: files; Name: "{userprograms}\PhotoLab Club Briançonnais\Désinstaller PhotoLab Club.lnk"
Type: dirifempty; Name: "{userprograms}\PhotoLab Club Briançonnais"
Type: files; Name: "{userdesktop}\PhotoLab Club Briançonnais.lnk"
