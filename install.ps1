# Video Studio installer (Windows 10/11, NVIDIA GPU recommended).
# Run from this folder:   powershell -ExecutionPolicy Bypass -File install.ps1
# Creates .venv (app + VieNeu voice) and .venv-whisper (offline transcription), installs ffmpeg if
# missing, and puts a "Video Studio" shortcut on the Desktop. Re-running is safe.
param([switch]$CpuOnly, [switch]$NoShortcut, [switch]$NoOllama)
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

function Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }

# --- Python 3.10-3.12 ---------------------------------------------------------
Step "Tim Python 3.10-3.12"
$py = $null
foreach ($v in "3.12", "3.11", "3.10") {
    try { $p = (& py "-$v" -c "import sys; print(sys.executable)" 2>$null); if ($LASTEXITCODE -eq 0 -and $p) { $py = $p.Trim(); break } } catch {}
}
if (-not $py) { throw "Chua co Python 3.10-3.12. Cai bang: winget install Python.Python.3.12  (roi mo lai PowerShell)" }
Write-Host "Python: $py"

# --- ffmpeg -------------------------------------------------------------------
Step "Kiem tra ffmpeg"
$links = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Links"
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue) -and -not (Test-Path (Join-Path $links "ffmpeg.exe"))) {
    winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements --silent
} else { Write-Host "ffmpeg da co." }

# --- Ollama: offline AI for the script writer (tab "Kich ban"); model gemma3:4b downloads on first use
if (-not $NoOllama) {
    Step "Kiem tra Ollama (AI viet kich ban chay tren may)"
    $ollama = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
    if (-not (Get-Command ollama -ErrorAction SilentlyContinue) -and -not (Test-Path $ollama)) {
        winget install --id Ollama.Ollama -e --accept-source-agreements --accept-package-agreements --silent
    } else { Write-Host "Ollama da co." }
}

# --- .venv: app + VieNeu --------------------------------------------------------
Step "Tao moi truong .venv (ung dung + giong doc VieNeu)"
if (-not (Test-Path ".venv\Scripts\python.exe")) { & $py -m venv .venv }
$app = Resolve-Path ".venv\Scripts\python.exe"
& $app -m pip install --upgrade pip --quiet
if ($CpuOnly) { & $app -m pip install torch==2.8.0 torchaudio==2.8.0 --quiet }
else { & $app -m pip install torch==2.8.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cu128 --quiet }
& $app -m pip install -r requirements-app.txt --quiet
if ($LASTEXITCODE -ne 0) { throw "Cai thu vien cho .venv bi loi" }

# --- .venv-whisper: transcription ---------------------------------------------
Step "Tao moi truong .venv-whisper (chuyen giong noi thanh chu)"
if (-not (Test-Path ".venv-whisper\Scripts\python.exe")) { & $py -m venv .venv-whisper }
$wh = Resolve-Path ".venv-whisper\Scripts\python.exe"
& $wh -m pip install --upgrade pip --quiet
& $wh -m pip install -r requirements-whisper.txt --quiet
if ($LASTEXITCODE -ne 0) { throw "Cai thu vien cho .venv-whisper bi loi" }

# --- check ----------------------------------------------------------------------
Step "Kiem tra"
& $app -c "import torch, vieneu, fastapi; print('torch', torch.__version__, '| CUDA:', torch.cuda.is_available())"
& $wh -c "import faster_whisper; print('faster-whisper', faster_whisper.__version__)"

# --- shortcut -------------------------------------------------------------------
if (-not $NoShortcut) {
    Step "Tao bieu tuong Video Studio tren Desktop"
    $desk = [Environment]::GetFolderPath("Desktop")
    $s = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $desk "Video Studio.lnk"))
    $s.TargetPath = (Resolve-Path ".venv\Scripts\pythonw.exe").Path
    $s.Arguments = "`"$here\launch.py`""
    $s.WorkingDirectory = $here
    $s.Description = "Dung video va tao giong doc (chay an, tat bang nut trong ung dung)"
    $s.IconLocation = "$env:SystemRoot\System32\imageres.dll,18"
    $s.Save()
}

Write-Host "`nXong. Bam dup 'Video Studio' tren Desktop de mo. Lan dau dung, model giong doc (~260 MB) va Whisper large-v3 (~3 GB) se tu tai; AI viet kich ban (gemma3:4b, ~3.4 GB) tai o lan viet dau tien." -ForegroundColor Green
