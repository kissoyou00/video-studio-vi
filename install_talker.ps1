# Optional add-on: talking model (the model's photo lip-syncs to the voice-over) with SadTalker.
# Run from this folder:   powershell -ExecutionPolicy Bypass -File install_talker.ps1
# (install.ps1 -WithTalking runs it too.) Creates talker\ (git-ignored): SadTalker code at a pinned
# commit, its own Python environment talker\.venv and ~1.5 GB of checkpoints. Re-running is safe.
param([switch]$CpuOnly)
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here
function Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }

$commit = "cd4c0465ae0b54a6f85af57f5c65fec9fe23e7f8"
$root = Join-Path $here "talker"
$code = Join-Path $root "sadtalker"
New-Item -ItemType Directory -Force $root | Out-Null

Step "Tai ma nguon SadTalker"
if (-not (Test-Path (Join-Path $code ".git"))) { git clone -q https://github.com/OpenTalker/SadTalker.git $code }
git -C $code fetch -q origin $commit 2>$null
git -C $code checkout -q $commit

Step "Tao moi truong talker\.venv"
$py = $null
foreach ($v in "3.12", "3.11", "3.10") {
    try { $p = (& py "-$v" -c "import sys; print(sys.executable)" 2>$null); if ($LASTEXITCODE -eq 0 -and $p) { $py = $p.Trim(); break } } catch {}
}
if (-not $py) { throw "Chua co Python 3.10-3.12" }
$venv = Join-Path $root ".venv"
if (-not (Test-Path "$venv\Scripts\python.exe")) { & $py -m venv $venv }
$tp = "$venv\Scripts\python.exe"
& $tp -m pip install --upgrade pip --quiet
if ($CpuOnly) { & $tp -m pip install torch==2.8.0 torchvision==0.23.0 --quiet }
else { & $tp -m pip install torch==2.8.0 torchvision==0.23.0 --index-url https://download.pytorch.org/whl/cu128 --quiet }
# SadTalker's own pins are for Python 3.8; these are the newer versions it runs with (patches below).
# basicsr/gfpgan (face enhancer) and gradio (web demo) are not needed.
& $tp -m pip install "numpy<2" face_alignment imageio imageio-ffmpeg librosa numba pydub scipy kornia tqdm yacs pyyaml joblib scikit-image facexlib av safetensors --quiet

Step "Sua SadTalker cho thu vien moi"
& $tp (Join-Path $here "helpers\patch_sadtalker.py") $code

Step "Tai checkpoint (~1.5 GB, chi tai mot lan)"
$ck = Join-Path $code "checkpoints"
$gw = Join-Path $code "gfpgan\weights"
New-Item -ItemType Directory -Force $ck, $gw | Out-Null
$files = @(
    @("https://github.com/OpenTalker/SadTalker/releases/download/v0.0.2-rc/mapping_00109-model.pth.tar", "$ck\mapping_00109-model.pth.tar"),
    @("https://github.com/OpenTalker/SadTalker/releases/download/v0.0.2-rc/mapping_00229-model.pth.tar", "$ck\mapping_00229-model.pth.tar"),
    @("https://github.com/OpenTalker/SadTalker/releases/download/v0.0.2-rc/SadTalker_V0.0.2_256.safetensors", "$ck\SadTalker_V0.0.2_256.safetensors"),
    @("https://github.com/xinntao/facexlib/releases/download/v0.1.0/alignment_WFLW_4HG.pth", "$gw\alignment_WFLW_4HG.pth"),
    @("https://github.com/xinntao/facexlib/releases/download/v0.1.0/detection_Resnet50_Final.pth", "$gw\detection_Resnet50_Final.pth")
)
foreach ($f in $files) {
    if (-not (Test-Path $f[1]) -or (Get-Item $f[1]).Length -lt 1000) {
        Write-Host "  $($f[1] | Split-Path -Leaf)"
        curl.exe -L --fail --retry 3 -s -o $f[1] $f[0]
        if ($LASTEXITCODE) { throw "Tai loi: $($f[0])" }
    }
}
Write-Host "`nXong phan nguoi mau nhep mieng." -ForegroundColor Green
