$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$iconScript = Join-Path $root 'sysadmin-codex\widget\create_icon.py'
python $iconScript
if ($LASTEXITCODE -ne 0) { throw 'Creazione icona non riuscita' }
python -m PyInstaller --noconfirm --clean --distpath (Join-Path $root 'dist') --workpath (Join-Path $root 'build\pyinstaller') (Join-Path $PSScriptRoot 'DesktropGoalTracker.spec')
if ($LASTEXITCODE -ne 0) { throw 'Creazione applicazione non riuscita' }
$compiler = Join-Path $root 'build-tools\inno\portable\ISCC.exe'
if (-not (Test-Path -LiteralPath $compiler)) { $compiler = (Get-Command ISCC.exe -ErrorAction Stop).Source }
& $compiler (Join-Path $PSScriptRoot 'DesktropGoalTracker.iss')
if ($LASTEXITCODE -ne 0) { throw 'Creazione installer non riuscita' }
