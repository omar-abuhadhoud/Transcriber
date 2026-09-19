; Transcriber setup wizard.
;
; Build with installer\build_installer.ps1, which passes the version in from
; transcriber\version.py so the tag, the exe's version resource and the app's own
; update check can never disagree.
;
; The wizard is deliberately tiny (~10 MB). It carries only the app's own source and
; fetches the two heavy pieces on demand:
;
;     the private Python runtime  ~45 MB download, ~4.6 GB installed
;     the model weights           ~5.3 GB
;
; Both are installed under {localappdata}\Transcriber, OUTSIDE the program folder that
; this installer replaces. That is what makes an update cheap: the program folder is
; overwritten, the runtime and the weights are detected and kept, and the download is
; a few megabytes rather than ten gigabytes.

#define AppName        "Transcriber"
#define AppPublisher   "Omar Abuhadhoud"
#define AppUrl         "https://github.com/omar-abuhadhoud/Transcriber"

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

; Pinned standalone CPython. Unlike python.org's embeddable zip this build includes
; tkinter, which customtkinter needs, and it is self-contained: no registry entries, no
; clash with any Python the user already has, and removing the folder removes it.
#define PyVersion   "3.11.16"
#define PyTag       "20260901"
#define PyArchive   "cpython-3.11.16+20260901-x86_64-pc-windows-msvc-install_only.tar.gz"
#define PyUrl       "https://github.com/astral-sh/python-build-standalone/releases/download/20260901/cpython-3.11.16%2B20260901-x86_64-pc-windows-msvc-install_only.tar.gz"

[Setup]
; Never change AppId: it is how every future build recognises this install and upgrades
; it in place instead of installing a second copy alongside.
AppId={{0F349481-A505-42A1-B0D9-B1C18D80EB83}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppUrl}
AppSupportURL={#AppUrl}/issues
AppUpdatesURL={#AppUrl}/releases
VersionInfoVersion={#AppVersion}
VersionInfoProductName={#AppName}

; Per-user install: no UAC prompt on install or on update, which is what lets the app
; apply an update by itself without an administrator dialog.
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; Hidden when upgrading, shown on a first install.
DisableDirPage=auto
UsePreviousAppDir=yes

ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0

OutputDir=build
OutputBaseFilename=TranscriberSetup-{#AppVersion}
SetupIconFile=..\icon.ico
UninstallDisplayIcon={app}\app\icon.ico
UninstallDisplayName={#AppName} {#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
WizardSizePercent=120

; Lets the wizard notice a running copy and offer to close it before replacing files.
CloseApplications=yes
RestartApplications=no
AppMutex=TranscriberAppRunningMutex

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &Desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
; The app's own source. Small, and the only thing an update actually replaces.
Source: "stage\app\*"; DestDir: "{app}\app"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "provision.py"; DestDir: "{app}\installer"; Flags: ignoreversion

[Dirs]
Name: "{localappdata}\{#AppName}"
Name: "{localappdata}\{#AppName}\logs"
Name: "{localappdata}\{#AppName}\state"

[Icons]
; Both shortcuts point at the runtime's renamed interpreter, created by provision.py,
; so the taskbar shows "Transcriber" instead of a generic Python process.
Name: "{group}\{#AppName}"; Filename: "{localappdata}\{#AppName}\runtime\Transcriber.exe"; \
    Parameters: """{app}\app\main.py"""; WorkingDir: "{app}\app"; IconFilename: "{app}\app\icon.ico"
Name: "{autodesktop}\{#AppName}"; Filename: "{localappdata}\{#AppName}\runtime\Transcriber.exe"; \
    Parameters: """{app}\app\main.py"""; WorkingDir: "{app}\app"; IconFilename: "{app}\app\icon.ico"; \
    Tasks: desktopicon

[Registry]
; uninsdeletekey, not uninsdeletevalue: the key is ours alone, and removing the values
; one by one leaves the empty key behind for the next version to find.
Root: HKCU; Subkey: "Software\{#AppName}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\{#AppName}"; ValueType: string; ValueName: "InstallPath"; \
    ValueData: "{app}"
Root: HKCU; Subkey: "Software\{#AppName}"; ValueType: string; ValueName: "Version"; \
    ValueData: "{#AppVersion}"

[UninstallDelete]
; Python writes .pyc caches next to the source after installation. Setup never recorded
; them, so without this the folders they sit in survive the uninstall.
Type: filesandordirs; Name: "{app}\app"
Type: filesandordirs; Name: "{app}\installer"
Type: dirifempty; Name: "{app}"

[Run]
Filename: "{localappdata}\{#AppName}\runtime\Transcriber.exe"; Parameters: """{app}\app\main.py"""; \
    WorkingDir: "{app}\app"; Description: "Start {#AppName}"; \
    Flags: nowait postinstall skipifsilent

[Code]
var
  StatusPage: TWizardPage;
  StatusMemo: TNewMemo;
  ProvisionPage: TOutputProgressWizardPage;

  PreviousVersion: String;
  RuntimeReady: Boolean;
  BigModelReady: Boolean;
  SmallModelReady: Boolean;

function DataDir(): String;
begin
  Result := ExpandConstant('{localappdata}\{#AppName}');
end;

function RuntimeDir(): String;
begin
  Result := DataDir() + '\runtime';
end;

function RuntimePython(): String;
begin
  Result := RuntimeDir() + '\python.exe';
end;

function ModelDir(const Subdir: String): String;
begin
  Result := DataDir() + '\models\' + Subdir;
end;

{ ---------------------------------------------------------------- detection ----- }

{ Display-only mirror of the app's own rule (config.json plus any .safetensors).
  provision.py, which asks the engine classes themselves, makes the real decision --
  this exists so the wizard can tell the user what it is about to download BEFORE a
  runtime capable of answering that question exists. }
function ModelPresent(const Subdir: String): Boolean;
var
  Search: TFindRec;
  Directory: String;
begin
  Result := False;
  Directory := ModelDir(Subdir);
  if not FileExists(Directory + '\config.json') then
    Exit;

  if FindFirst(Directory + '\*.safetensors', Search) then
  begin
    try
      Result := True;
    finally
      FindClose(Search);
    end;
  end;
end;

{ The version recorded by whichever build installed last, read from our own key
  rather than Inno's uninstall entry so it survives a manual reinstall. }
function DetectPreviousVersion(): String;
var
  Value: String;
begin
  Result := '';
  if RegQueryStringValue(HKEY_CURRENT_USER, 'Software\{#AppName}', 'Version', Value) then
    Result := Value;
end;

procedure RefreshDetection();
begin
  PreviousVersion := DetectPreviousVersion();
  RuntimeReady := FileExists(RuntimePython());
  BigModelReady := ModelPresent('qwen3-asr-1.7b');
  SmallModelReady := ModelPresent('qwen3-asr-0.6b');
end;

{ How the installed version relates to the one being installed:
    -2  nothing installed yet
    <0  the installed one is older -- a normal update
     0  the same version -- a repair or a reinstall
    >0  the installed one is newer -- a downgrade }
function PreviousComparedToThis(): Integer;
var
  Installed, Incoming: Int64;
begin
  if PreviousVersion = '' then
  begin
    Result := -2;
    Exit;
  end;

  if StrToVersion(PreviousVersion, Installed) and StrToVersion('{#AppVersion}', Incoming) then
    Result := ComparePackedVersion(Installed, Incoming)
  else
    { An unparsable recorded version should not stop anyone installing. }
    Result := 0;
end;

function HeadlineFor(const Comparison: Integer): String;
begin
  if Comparison = -2 then
    Result := 'Installing Transcriber {#AppVersion}'
  else if Comparison < 0 then
    Result := 'Updating Transcriber ' + PreviousVersion + '  ->  {#AppVersion}'
  else if Comparison = 0 then
    Result := 'Reinstalling Transcriber {#AppVersion}'
  else
    Result := 'Installing Transcriber {#AppVersion} over the newer ' + PreviousVersion;
end;

{ ------------------------------------------------------------------- status ----- }

procedure BuildStatusText();
var
  Keep, Fetch, Text: String;
  Megabytes: Integer;
begin
  Keep := '';
  Fetch := '';
  Megabytes := 0;

  if RuntimeReady then
    Keep := Keep + '    GPU runtime (Python {#PyVersion} + PyTorch, about 4.6 GB)' + #13#10
  else
  begin
    Fetch := Fetch + '    GPU runtime (Python {#PyVersion} + PyTorch)   about 2.5 GB' + #13#10;
    Megabytes := Megabytes + 2560;
  end;

  if BigModelReady then
    Keep := Keep + '    Qwen3-ASR 1.7B weights (3.8 GB)' + #13#10
  else
  begin
    Fetch := Fetch + '    Qwen3-ASR 1.7B weights                        about 3.8 GB' + #13#10;
    Megabytes := Megabytes + 3891;
  end;

  if SmallModelReady then
    Keep := Keep + '    Qwen3-ASR 0.6B weights (1.5 GB)' + #13#10
  else
  begin
    Fetch := Fetch + '    Qwen3-ASR 0.6B weights                        about 1.5 GB' + #13#10;
    Megabytes := Megabytes + 1536;
  end;

  Text := HeadlineFor(PreviousComparedToThis()) + #13#10 + #13#10;

  if Keep <> '' then
    Text := Text + 'Already on this computer, will be kept:' + #13#10 + Keep + #13#10;

  if Fetch <> '' then
  begin
    Text := Text + 'Will be downloaded:' + #13#10 + Fetch + #13#10;
    Text := Text + 'Total download: roughly ' + IntToStr(Megabytes div 1024) + '.' +
            IntToStr(((Megabytes mod 1024) * 10) div 1024) + ' GB.' + #13#10 +
            'Downloads that finish are kept, so setup can be run again if the ' +
            'connection drops.' + #13#10;
  end
  else
    Text := Text + 'Everything else is already installed. Only the application ' +
            'itself will be updated, so this will take a few seconds.' + #13#10;

  StatusMemo.Text := Text;
end;

procedure CreateStatusPage();
begin
  StatusPage := CreateCustomPage(wpSelectTasks,
    'What setup will do',
    'Transcriber keeps its runtime and speech models outside the program folder, so ' +
    'an update never downloads them twice.');

  StatusMemo := TNewMemo.Create(StatusPage);
  StatusMemo.Parent := StatusPage.Surface;
  StatusMemo.SetBounds(0, 0, StatusPage.SurfaceWidth, StatusPage.SurfaceHeight);
  StatusMemo.ScrollBars := ssVertical;
  StatusMemo.ReadOnly := True;
  StatusMemo.Color := clBtnFace;
end;

{ ---------------------------------------------------------------- provision ----- }

{ Unpacks the standalone runtime with Windows' own tar.exe (present since Windows 10
  1803), which avoids shipping an archiver or depending on a newer Inno than the build
  machine may have. }
function ExtractRuntime(const Archive: String): Boolean;
var
  ResultCode: Integer;
  Staging: String;
begin
  Staging := DataDir() + '\runtime-staging';

  DelTree(Staging, True, True, True);
  if not ForceDirectories(Staging) then
  begin
    MsgBox('Setup could not create ' + Staging + '.', mbCriticalError, MB_OK);
    Result := False;
    Exit;
  end;

  if not Exec(ExpandConstant('{sys}\tar.exe'), '-xzf "' + Archive + '" -C "' + Staging + '"',
              '', SW_HIDE, ewWaitUntilTerminated, ResultCode) or (ResultCode <> 0) then
  begin
    MsgBox('Setup could not unpack the Python runtime (tar exit code ' +
           IntToStr(ResultCode) + ').', mbCriticalError, MB_OK);
    DelTree(Staging, True, True, True);
    Result := False;
    Exit;
  end;

  { The archive contains a single top-level "python" folder. }
  DelTree(RuntimeDir(), True, True, True);
  if not RenameFile(Staging + '\python', RuntimeDir()) then
  begin
    MsgBox('Setup could not move the Python runtime into ' + RuntimeDir() + '.',
           mbCriticalError, MB_OK);
    DelTree(Staging, True, True, True);
    Result := False;
    Exit;
  end;

  DelTree(Staging, True, True, True);
  Result := True;
end;

function SplitProgressLine(const Line: String; var Percent: Integer;
  var Message: String; var Done: Boolean; var ExitCode: Integer): Boolean;
var
  Head, Rest: String;
  Bar: Integer;
begin
  Result := False;
  Done := False;
  Rest := Trim(Line);
  Bar := Pos('|', Rest);
  if Bar = 0 then
    Exit;

  Head := Copy(Rest, 1, Bar - 1);
  Rest := Copy(Rest, Bar + 1, Length(Rest));

  if CompareText(Head, 'DONE') = 0 then
  begin
    Done := True;
    Bar := Pos('|', Rest);
    if Bar = 0 then
    begin
      ExitCode := StrToIntDef(Rest, 1);
      Message := '';
    end
    else
    begin
      ExitCode := StrToIntDef(Copy(Rest, 1, Bar - 1), 1);
      Message := Copy(Rest, Bar + 1, Length(Rest));
    end;
    Result := True;
    Exit;
  end;

  Percent := StrToIntDef(Head, -1);
  if Percent < 0 then
    Exit;
  Message := Rest;
  Result := True;
end;

{ Runs provision.py and follows it.
  Inno cannot read a running process's stdout, so provision.py mirrors its current step
  into a small file that it rewrites atomically, and this polls that file. Completion is
  signalled by a DONE line rather than by waiting on the process, and cmd.exe appends a
  DONE of its own so that even a hard crash ends the wait. }
function RunProvision(): Boolean;
var
  ProgressFile, ExitFile, LogFile, Command, Line, Message: String;
  Lines: TArrayOfString;
  Percent, ExitCode, ResultCode, Waited, Grace: Integer;
  Done: Boolean;
begin
  ProgressFile := DataDir() + '\state\setup-progress.txt';
  ExitFile := DataDir() + '\state\setup-exit.txt';
  LogFile := DataDir() + '\logs\setup-' + '{#AppVersion}' + '.log';
  DeleteFile(ProgressFile);
  DeleteFile(ExitFile);

  { /V:ON and !ERRORLEVEL! rather than %ERRORLEVEL%: in a single &-chained command line
    the percent form is expanded when the line is parsed, which is before python has
    even started, and would always report the previous command's code.

    The exit file is only a backstop. provision.py writes its own DONE line, with a
    message, on every path it can still run code on; this catches the ones where it
    cannot, such as the interpreter being killed outright. }
  Command := '/S /V:ON /C ""' + RuntimePython() + '" -u "' +
             ExpandConstant('{app}\installer\provision.py') + '"' +
             ' --app-dir "' + ExpandConstant('{app}\app') + '"' +
             ' --runtime-dir "' + RuntimeDir() + '"' +
             ' --install-dir "' + ExpandConstant('{app}') + '"' +
             ' --app-version "{#AppVersion}"' +
             ' --progress-file "' + ProgressFile + '"' +
             ' > "' + LogFile + '" 2>&1' +
             ' & > "' + ExitFile + '" echo !ERRORLEVEL!"';

  if not Exec(ExpandConstant('{cmd}'), Command, '', SW_HIDE, ewNoWait, ResultCode) then
  begin
    MsgBox('Setup could not start the component installer.', mbCriticalError, MB_OK);
    Result := False;
    Exit;
  end;

  Percent := 0;
  ExitCode := 0;
  Message := '';
  Done := False;
  Waited := 0;
  Grace := 0;

  { Six hours: a first install on a slow connection downloads about 8 GB. }
  while (not Done) and (Waited < 6 * 60 * 60 * 4) do
  begin
    Sleep(250);
    Waited := Waited + 1;

    if LoadStringsFromFile(ProgressFile, Lines) and (GetArrayLength(Lines) > 0) then
    begin
      Line := Lines[0];
      if SplitProgressLine(Line, Percent, Message, Done, ExitCode) then
      begin
        if not Done then
        begin
          ProvisionPage.SetProgress(Percent, 100);
          ProvisionPage.SetText(Message, 'Detailed progress is written to ' + LogFile);
        end;
      end;
    end;

    { The process has ended. Give provision.py a moment to have its own, more
      descriptive, DONE line noticed before falling back to the bare exit code. }
    if (not Done) and FileExists(ExitFile) then
    begin
      Grace := Grace + 1;
      if Grace > 8 then
      begin
        if LoadStringsFromFile(ExitFile, Lines) and (GetArrayLength(Lines) > 0) then
          ExitCode := StrToIntDef(Trim(Lines[0]), 1)
        else
          ExitCode := 1;
        Message := '';
        Done := True;
      end;
    end;

    WizardForm.Refresh();
  end;

  if not Done then
  begin
    MsgBox('Setup timed out waiting for the components to install.' + #13#10 +
           'The log is at ' + LogFile, mbCriticalError, MB_OK);
    Result := False;
    Exit;
  end;

  if ExitCode <> 0 then
  begin
    if Message = '' then
      Message := 'The component installer stopped with code ' + IntToStr(ExitCode) + '.';
    MsgBox(Message + #13#10 + #13#10 + 'The full log is at:' + #13#10 + LogFile,
           mbCriticalError, MB_OK);
    Result := False;
    Exit;
  end;

  Result := True;
end;

{ ------------------------------------------------------------------- events ----- }

function OnDownloadProgress(const Url, FileName: String; const Progress, ProgressMax: Int64): Boolean;
begin
  Result := True;
end;

procedure InitializeWizard();
begin
  RefreshDetection();
  CreateStatusPage();

  ProvisionPage := CreateOutputProgressPage('Installing components',
    'The GPU runtime and the speech models are being set up. Anything already ' +
    'installed is detected and kept.');
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if (StatusPage <> nil) and (CurPageID = StatusPage.ID) then
  begin
    RefreshDetection();
    BuildStatusText();
  end;
end;

{ Fetches the runtime archive into Setup's temporary folder.

  Deliberately not done from NextButtonClick: Inno never fires that during a silent
  install, and a silent install is exactly how the app applies its own updates, so the
  download has to hang off a step that runs in both modes. }
function DownloadRuntime(): Boolean;
begin
  Result := True;
  ProvisionPage.SetText('Downloading the Python runtime (about 45 MB)...', '');
  try
    DownloadTemporaryFile('{#PyUrl}', '{#PyArchive}', '', @OnDownloadProgress);
  except
    MsgBox('Setup could not download the Python runtime.' + #13#10 + #13#10 +
           GetExceptionMessage + #13#10 + #13#10 +
           'Check the internet connection and run setup again.', mbCriticalError, MB_OK);
    Result := False;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep <> ssPostInstall then
    Exit;

  ProvisionPage.Show();
  try
    ProvisionPage.SetProgress(0, 100);

    if not RuntimeReady then
    begin
      if not DownloadRuntime() then
        RaiseException('The Python runtime could not be downloaded.');

      ProvisionPage.SetText('Unpacking the Python runtime...', '');
      if not ExtractRuntime(ExpandConstant('{tmp}\{#PyArchive}')) then
        RaiseException('The Python runtime could not be installed.');
      RuntimeReady := True;
    end;

    ProvisionPage.SetText('Checking what is already installed...', '');
    if not RunProvision() then
      RaiseException('Setup could not install the required components.');
  finally
    ProvisionPage.Hide();
  end;
end;

{ ---------------------------------------------------------------- uninstall ----- }

var
  RemovePage: TNewNotebookPage;
  KeepModelsCheck: TNewCheckBox;
  KeepRuntimeCheck: TNewCheckBox;
  ContinueButton: TNewButton;
  DeleteModels: Boolean;
  DeleteRuntime: Boolean;

{ Recursive size of a folder, in megabytes, so the uninstaller can state what it is
  actually offering to delete instead of quoting a number from the documentation. }
function DirSizeMb(const Directory: String): Integer;
var
  Search: TFindRec;
  Total: Int64;
begin
  Total := 0;
  if FindFirst(Directory + '\*', Search) then
  begin
    try
      repeat
        if (Search.Name = '.') or (Search.Name = '..') then
          Continue;
        if (Search.Attributes and FILE_ATTRIBUTE_DIRECTORY) <> 0 then
          Total := Total + Int64(DirSizeMb(Directory + '\' + Search.Name)) * 1048576
        else
          Total := Total + (Int64(Search.SizeHigh) shl 32) + Int64(Search.SizeLow);
      until not FindNext(Search);
    finally
      FindClose(Search);
    end;
  end;
  Result := Integer(Total div 1048576);
end;

function SizeCaption(const Megabytes: Integer): String;
begin
  if Megabytes >= 1024 then
    Result := IntToStr(Megabytes div 1024) + '.' +
              IntToStr(((Megabytes mod 1024) * 10) div 1024) + ' GB'
  else
    Result := IntToStr(Megabytes) + ' MB';
end;

{ A real page on the uninstaller's own form, rather than a message box, so removing
  Transcriber asks the same kind of question the installer does. Both boxes default to
  keeping the data: a reinstall then costs nothing, and nobody loses a 10 GB download
  by clicking through an uninstall. }
procedure InitializeUninstallProgressForm();
var
  Intro: TNewStaticText;
  Note: TNewStaticText;
  SavedName, SavedDescription: String;
  SavedCancelEnabled: Boolean;
  SavedCancelResult: Integer;
  ModelsMb, RuntimeMb: Integer;
  ModelsDir, RuntimeFolder: String;
begin
  DeleteModels := False;
  DeleteRuntime := False;

  if UninstallSilent then
    Exit;

  ModelsDir := DataDir() + '\models';
  RuntimeFolder := RuntimeDir();
  if not DirExists(ModelsDir) and not DirExists(RuntimeFolder) then
    Exit;

  ModelsMb := DirSizeMb(ModelsDir);
  RuntimeMb := DirSizeMb(RuntimeFolder);

  RemovePage := TNewNotebookPage.Create(UninstallProgressForm);
  RemovePage.Notebook := UninstallProgressForm.InnerNotebook;
  RemovePage.Parent := UninstallProgressForm.InnerNotebook;
  RemovePage.Align := alClient;

  Intro := TNewStaticText.Create(UninstallProgressForm);
  Intro.Parent := RemovePage;
  Intro.Top := UninstallProgressForm.StatusLabel.Top;
  Intro.Left := UninstallProgressForm.StatusLabel.Left;
  Intro.Width := UninstallProgressForm.StatusLabel.Width;
  Intro.Height := ScaleY(34);
  Intro.AutoSize := False;
  Intro.WordWrap := True;
  Intro.ShowAccelChar := False;
  Intro.Caption := 'Transcriber will be removed. Its downloaded data is kept unless ' +
                   'you tick it below.';

  KeepModelsCheck := TNewCheckBox.Create(UninstallProgressForm);
  KeepModelsCheck.Parent := RemovePage;
  KeepModelsCheck.Left := Intro.Left;
  KeepModelsCheck.Top := Intro.Top + Intro.Height + ScaleY(14);
  KeepModelsCheck.Width := Intro.Width;
  KeepModelsCheck.Height := ScaleY(20);
  KeepModelsCheck.Checked := False;
  KeepModelsCheck.Enabled := DirExists(ModelsDir);
  if KeepModelsCheck.Enabled then
    KeepModelsCheck.Caption := 'Also delete the speech models (' + SizeCaption(ModelsMb) + ')'
  else
    KeepModelsCheck.Caption := 'Speech models (not installed)';

  KeepRuntimeCheck := TNewCheckBox.Create(UninstallProgressForm);
  KeepRuntimeCheck.Parent := RemovePage;
  KeepRuntimeCheck.Left := Intro.Left;
  KeepRuntimeCheck.Top := KeepModelsCheck.Top + ScaleY(26);
  KeepRuntimeCheck.Width := Intro.Width;
  KeepRuntimeCheck.Height := ScaleY(20);
  KeepRuntimeCheck.Checked := False;
  KeepRuntimeCheck.Enabled := DirExists(RuntimeFolder);
  if KeepRuntimeCheck.Enabled then
    KeepRuntimeCheck.Caption := 'Also delete the GPU runtime, Python and PyTorch (' +
                                SizeCaption(RuntimeMb) + ')'
  else
    KeepRuntimeCheck.Caption := 'GPU runtime (not installed)';

  Note := TNewStaticText.Create(UninstallProgressForm);
  Note.Parent := RemovePage;
  Note.Left := Intro.Left;
  Note.Top := KeepRuntimeCheck.Top + ScaleY(34);
  Note.Width := Intro.Width;
  Note.Height := ScaleY(44);
  Note.AutoSize := False;
  Note.WordWrap := True;
  Note.ShowAccelChar := False;
  Note.Caption := 'Leaving these in place means a future install of Transcriber ' +
                  'finds them and starts without downloading anything. They are in ' +
                  DataDir() + '.';

  SavedName := UninstallProgressForm.PageNameLabel.Caption;
  SavedDescription := UninstallProgressForm.PageDescriptionLabel.Caption;
  UninstallProgressForm.PageNameLabel.Caption := 'Remove Transcriber';
  UninstallProgressForm.PageDescriptionLabel.Caption :=
    'Choose what to delete along with the program.';
  UninstallProgressForm.InnerNotebook.ActivePage := RemovePage;

  { The uninstall form carries only a Cancel button, so the one that confirms this
    page has to be built here and placed beside it. }
  ContinueButton := TNewButton.Create(UninstallProgressForm);
  ContinueButton.Parent := UninstallProgressForm;
  ContinueButton.Width := UninstallProgressForm.CancelButton.Width;
  ContinueButton.Height := UninstallProgressForm.CancelButton.Height;
  ContinueButton.Top := UninstallProgressForm.CancelButton.Top;
  ContinueButton.Left := UninstallProgressForm.CancelButton.Left -
                         UninstallProgressForm.CancelButton.Width - ScaleX(8);
  ContinueButton.Caption := SetupMessage(msgButtonNext);
  ContinueButton.ModalResult := mrOk;
  ContinueButton.Default := True;

  SavedCancelEnabled := UninstallProgressForm.CancelButton.Enabled;
  UninstallProgressForm.CancelButton.Enabled := True;
  SavedCancelResult := UninstallProgressForm.CancelButton.ModalResult;
  UninstallProgressForm.CancelButton.ModalResult := mrCancel;

  if UninstallProgressForm.ShowModal = mrCancel then
    Abort();

  DeleteModels := KeepModelsCheck.Enabled and KeepModelsCheck.Checked;
  DeleteRuntime := KeepRuntimeCheck.Enabled and KeepRuntimeCheck.Checked;

  { Hand the form back the way it was, or the removal progress that follows is drawn
    onto our page with a Next button still sitting on it. }
  ContinueButton.Visible := False;
  UninstallProgressForm.CancelButton.Enabled := SavedCancelEnabled;
  UninstallProgressForm.CancelButton.ModalResult := SavedCancelResult;
  UninstallProgressForm.PageNameLabel.Caption := SavedName;
  UninstallProgressForm.PageDescriptionLabel.Caption := SavedDescription;
  UninstallProgressForm.InnerNotebook.ActivePage := UninstallProgressForm.InnerPage;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Data: String;
  Failed: String;
begin
  if CurUninstallStep <> usPostUninstall then
    Exit;

  Data := DataDir();
  if not DirExists(Data) then
    Exit;

  Failed := '';

  { Nothing below touches UninstallProgressForm.

    It used to set StatusLabel.Caption before each deletion. Those two lines ran only
    when a box was ticked, and reaching back into the form here -- after its controls
    were repurposed for the page above and it has finished its modal turn -- aborted
    this procedure. The visible result was the exact opposite of what was asked for:
    tick "delete the models" and the models survived, along with the logs below and the
    entry in Add/Remove Programs, because nothing after the failing line ran.

    Deleting what the user asked to delete must not depend on drawing a caption. }
  if DeleteModels then
  begin
    if not DelTree(Data + '\models', True, True, True) then
      Failed := Failed + #13#10 + '    ' + Data + '\models';
  end;

  if DeleteRuntime then
  begin
    if not DelTree(RuntimeDir(), True, True, True) then
      Failed := Failed + #13#10 + '    ' + RuntimeDir();
  end;

  DelTree(Data + '\logs', True, True, True);
  DelTree(Data + '\recovery_tmp', True, True, True);
  DeleteFile(Data + '\state\setup-progress.txt');
  DeleteFile(Data + '\state\setup-exit.txt');

  { install.json is the record of what is in this folder -- which packages the runtime
    was built from, which weights are complete. Deleting it while the runtime and the
    weights stay would throw away the very thing that lets the next install skip them,
    so it only goes when there is nothing left for it to describe. }
  if DeleteModels and DeleteRuntime then
    DelTree(Data + '\state', True, True, True);

  { Removed only if empty, so anything kept stays exactly where it was. }
  RemoveDir(Data + '\state');
  RemoveDir(Data);

  { Said out loud, because a silent failure here is how gigabytes survive an uninstall
    that the user believed had removed them. }
  if Failed <> '' then
    MsgBox('Transcriber was removed, but these could not be deleted:' + #13#10 +
           Failed + #13#10 + #13#10 +
           'Something is usually still holding them open. Restart and delete the ' +
           'folder by hand to reclaim the space.', mbError, MB_OK);
end;
