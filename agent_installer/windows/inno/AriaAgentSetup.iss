#define MyAppName "Aria Agent"
#define MyAppVersion GetStringFileInfo(AddBackslash(SourcePath) + "..\..\dist\AriaAgent\AriaAgent.exe", "ProductVersion")
#define MyAppPublisher "Project Aria"
#define MyAppExeName "AriaAgent.exe"

[Setup]
AppId={{2F831D73-8272-40C9-B08B-5F2A8D54A001}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\AriaAgent
DefaultGroupName=Aria Agent
OutputDir=..\output
OutputBaseFilename=AriaAgentSetup
Compression=lzma
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=admin

[Files]
Source: "..\dist\AriaAgent\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\Aria Agent"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Audio Device Setup"; Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -File \"{app}\agent_installer\windows\scripts\detect_audio.ps1\""

[Run]
Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -File \"{app}\agent_installer\windows\scripts\install_prereqs.ps1\""; StatusMsg: "Installing prerequisites..."; Flags: runhidden waituntilterminated
Filename: "{app}\{#MyAppExeName}"; Description: "Launch Aria Agent"; Flags: nowait postinstall skipifsilent
