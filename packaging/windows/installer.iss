; Inno Setup script - build with:  iscc /DAppVersion=0.2.0 packaging\windows\installer.iss
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6E3C2A4B-5D1F-4F7A-9C2E-RAJACAPTURE01}
AppName=Raja Capture
AppVersion={#AppVersion}
AppPublisher=Raja Capture
AppPublisherURL=https://github.com/firexsantos/raja-capture
DefaultDirName={autopf}\Raja Capture
DefaultGroupName=Raja Capture
DisableProgramGroupPage=yes
OutputDir=..\..\dist
OutputBaseFilename=RajaCapture-{#AppVersion}-setup
SetupIconFile=..\build\raja-capture.ico
UninstallDisplayIcon={app}\raja-capture.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "autostart"; Description: "Jalankan Raja Capture saat Windows mulai"; GroupDescription: "Lainnya:"; Flags: unchecked

[Files]
Source: "..\..\dist\raja-capture\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Raja Capture"; Filename: "{app}\raja-capture.exe"
Name: "{group}\Uninstall Raja Capture"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Raja Capture"; Filename: "{app}\raja-capture.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "RajaCapture"; ValueData: """{app}\raja-capture.exe"" --tray"; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\raja-capture.exe"; Description: "{cm:LaunchProgram,Raja Capture}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{app}\raja-capture.exe"; Parameters: "--quit"; Flags: runhidden skipifdoesntexist; RunOnceId: "QuitApp"
