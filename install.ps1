<#
.SYNOPSIS
    Installer satu-langkah MikuVision untuk Windows.

.DESCRIPTION
    Menyiapkan semua yang dibutuhkan MikuVision di folder aplikasi ini:
      1. uv (versi dipatok, checksum diverifikasi) di .tools\uv
      2. Python terisolasi di .tools\python dan virtualenv di .venv
      3. PyTorch (CUDA bila ada GPU NVIDIA, CPU bila tidak) + requirements.txt
         (+ rvc-python bila model RVC sudah diletakkan di models\miku_default_rvc)
      4. Kamus unidic untuk MeloTTS
      5. Ollama + model LLM dari config.py (OLLAMA_MODEL)
      6. Shortcut desktop ke GUI
      7. Verifikasi dengan `miku.py --test`

    Aman dijalankan ulang: langkah yang sudah beres dilewati.
    Log lengkap ada di logs\install-<waktu>.log.

.PARAMETER Yes
    Jawab "ya" otomatis untuk semua pertanyaan (instal Git/Ollama lewat winget).

.PARAMETER Cpu
    Paksa PyTorch versi CPU walaupun ada GPU NVIDIA.

.PARAMETER WithRvc
    Pasang rvc-python walau model RVC belum ada. Tanpa opsi ini rvc-python dipasang
    otomatis bila file model RVC ditemukan.

.PARAMETER PythonVersion
    Versi Python env. Default 3.10: fairseq (dependency rvc-python) tidak jalan di 3.11.

.PARAMETER SkipOllama
    Lewati pengecekan Ollama dan pull model.

.PARAMETER SkipShortcut
    Jangan buat shortcut desktop.

.PARAMETER SkipTest
    Jangan jalankan `miku.py --test` di akhir.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File install.ps1
#>
[CmdletBinding()]
param(
    [switch]$Yes,
    [switch]$Cpu,
    [switch]$WithRvc,
    [switch]$SkipOllama,
    [switch]$SkipShortcut,
    [switch]$SkipTest,
    [string]$PythonVersion = "3.10"
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"   # progress bar membuat Invoke-WebRequest sangat lambat
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
[Console]::OutputEncoding = [Text.Encoding]::UTF8

# ---------------------------------------------------------------- konstanta
$UvVersion   = "0.11.2"
$UvSha256    = "171b7ccda1bbd562da6babeffcf533a1c6cc7862cf998da826e1db534fc43e48"
$UvUrl       = "https://github.com/astral-sh/uv/releases/download/$UvVersion/uv-x86_64-pc-windows-msvc.zip"
$TorchVersion = "2.11.0"
$RvcPythonVersion = "0.1.5"   # 0.1.0 memakai API load_model lama yang tidak cocok dengan core/voice_converter.py
$AppName     = "MikuVision"

$Root       = $PSScriptRoot
$ToolsDir   = Join-Path $Root ".tools"
$UvDir      = Join-Path $ToolsDir "uv"
$UvExe      = Join-Path $UvDir "uv.exe"
$VenvDir    = Join-Path $Root ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$RvcDir     = Join-Path $Root "models\miku_default_rvc"
$LogDir     = Join-Path $Root "logs"
$LogFile    = Join-Path $LogDir ("install-{0}.log" -f (Get-Date -Format "yyyyMMdd-HHmmss"))

# Semua data uv (Python, cache unduhan) tinggal di folder aplikasi, bukan di profil C:.
# Cache di drive yang sama dengan .venv membuat uv memakai hardlink, jadi tidak dobel.
$env:UV_PYTHON_INSTALL_DIR = Join-Path $ToolsDir "python"
$env:UV_CACHE_DIR          = Join-Path $ToolsDir "uv-cache"
$env:UV_NO_PROGRESS        = "1"
$env:PYTHONUTF8            = "1"
$env:PYTHONIOENCODING      = "utf-8"

# Variabel yang baru dibuat user belum terlihat oleh proses yang sudah jalan sebelumnya.
# Tanpa ini model Whisper/MeloTTS bisa terunduh ke C: walau HF_HOME sudah diarahkan ke drive lain.
foreach ($name in @("HF_HOME", "OLLAMA_MODELS")) {
    if (-not [Environment]::GetEnvironmentVariable($name, "Process")) {
        $value = [Environment]::GetEnvironmentVariable($name, "User")
        if (-not $value) { $value = [Environment]::GetEnvironmentVariable($name, "Machine") }
        if ($value) { Set-Item -Path "env:$name" -Value $value }
    }
}

# ---------------------------------------------------------------- helper
function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $line = "[{0}] [{1}] {2}" -f (Get-Date -Format "HH:mm:ss"), $Level, $Message
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
    switch ($Level) {
        "WARN"  { Write-Host $line -ForegroundColor Yellow }
        "ERROR" { Write-Host $line -ForegroundColor Red }
        "OK"    { Write-Host $line -ForegroundColor Green }
        default { Write-Host $line }
    }
}

function Write-Step {
    param([string]$Title)
    Write-Log ""
    Write-Log "==== $Title ===="
}

# Kegagalan yang sudah dijelaskan ke user; dibedakan dari error tak terduga di blok catch utama.
$script:KnownFailure = $null

function Stop-Install {
    param([string]$Message)
    $script:KnownFailure = $Message
    throw $Message
}

# Menjalankan program eksternal; stdout+stderr masuk ke log. Mengembalikan exit code.
function Invoke-Native {
    param([string]$Exe, [string[]]$Arguments, [switch]$Quiet)
    Write-Log ("> {0} {1}" -f (Split-Path $Exe -Leaf), ($Arguments -join " "))
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"   # stderr dari program native bukan error PowerShell
    try {
        & $Exe @Arguments 2>&1 | ForEach-Object {
            $text = "$_"
            # PowerShell 5.1 menampilkan baris stderr kosong sebagai nama tipe exception
            if ($text -eq "System.Management.Automation.RemoteException") { $text = "" }
            Add-Content -Path $LogFile -Value "    $text" -Encoding UTF8
            if (-not $Quiet) { Write-Host "    $text" }
        }
        return $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previous
    }
}

# Menjalankan program dan mengembalikan stdout sebagai string (tanpa menulis ke layar).
function Get-NativeOutput {
    param([string]$Exe, [string[]]$Arguments)
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $out = & $Exe @Arguments 2>$null
        if ($LASTEXITCODE -ne 0) { return $null }
        return ($out -join "`n").Trim()
    } catch {
        return $null
    } finally {
        $ErrorActionPreference = $previous
    }
}

function Confirm-Action {
    param([string]$Question)
    if ($Yes) {
        Write-Log "$Question -> ya (-Yes)"
        return $true
    }
    $answer = Read-Host "$Question (y/n)"
    Write-Log "$Question -> $answer"
    return $answer -match '^(y|ya|yes)$'
}

function Update-SessionPath {
    $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $user = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machine;$user"
}

function Install-WithWinget {
    param([string]$PackageId, [string]$DisplayName)
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Stop-Install "$DisplayName belum terpasang dan winget tidak tersedia. Pasang $DisplayName secara manual lalu jalankan installer ini lagi."
    }
    if (-not (Confirm-Action "$DisplayName belum terpasang. Pasang sekarang lewat winget ($PackageId)?")) {
        Stop-Install "$DisplayName dibutuhkan. Pasang secara manual lalu jalankan installer ini lagi."
    }
    $code = Invoke-Native "winget" @("install", "--id", $PackageId, "-e", "--source", "winget",
        "--accept-package-agreements", "--accept-source-agreements")
    if ($code -ne 0) { Stop-Install "winget gagal memasang $DisplayName (exit $code)." }
    Update-SessionPath
}

# ---------------------------------------------------------------- langkah
function Test-Prerequisites {
    Write-Step "Cek sistem"
    if (-not [Environment]::Is64BitOperatingSystem) { Stop-Install "Butuh Windows 64-bit." }
    Write-Log ("Windows {0}, PowerShell {1}" -f [Environment]::OSVersion.Version, $PSVersionTable.PSVersion)
    Write-Log "Folder aplikasi: $Root"

    $drive = Get-PSDrive -Name ($Root.Substring(0, 1))
    $freeGb = [math]::Round($drive.Free / 1GB, 1)
    Write-Log "Ruang kosong drive $($drive.Name): $freeGb GB"
    # Saat dijalankan ulang, env sudah memakai ruangnya; cukup cek pada instalasi pertama.
    if ($freeGb -lt 12 -and -not (Test-Path $VenvPython)) {
        Write-Log "Butuh sekitar 12 GB (Python env + model). Ruang tersisa $freeGb GB." "WARN"
        if (-not (Confirm-Action "Lanjutkan walau ruang disk mungkin kurang?")) { Stop-Install "Dibatalkan: ruang disk kurang." }
    }

    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        Install-WithWinget "Git.Git" "Git"
        if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
            Stop-Install "Git sudah dipasang tapi belum ada di PATH. Tutup jendela ini, buka lagi, lalu jalankan installer ulang."
        }
    }
    Write-Log "Git: $(Get-NativeOutput 'git' @('--version'))"
}

function Install-Uv {
    Write-Step "uv $UvVersion"
    if (Test-Path $UvExe) {
        $current = Get-NativeOutput $UvExe @("--version")
        if ($current -like "uv $UvVersion*") {
            Write-Log "Sudah terpasang: $current" "OK"
            return
        }
        Write-Log "Versi lain ditemukan ($current), diganti."
    }
    New-Item -ItemType Directory -Force -Path $UvDir | Out-Null
    $zip = Join-Path ([IO.Path]::GetTempPath()) "uv-$UvVersion-$PID.zip"
    try {
        Write-Log "Mengunduh $UvUrl"
        Invoke-WebRequest -Uri $UvUrl -OutFile $zip -UseBasicParsing
        $hash = (Get-FileHash -Path $zip -Algorithm SHA256).Hash.ToLower()
        if ($hash -ne $UvSha256) { Stop-Install "Checksum uv tidak cocok (dapat $hash). Unduhan rusak atau dimodifikasi." }
        Expand-Archive -Path $zip -DestinationPath $UvDir -Force
    } finally {
        Remove-Item $zip -ErrorAction SilentlyContinue
    }
    Write-Log "Terpasang: $(Get-NativeOutput $UvExe @('--version'))" "OK"
}

# Exe yang baru dijalankan kadang masih dikunci sebentar (misalnya oleh antivirus), jadi dicoba ulang.
function Remove-VenvDir {
    for ($attempt = 1; (Test-Path $VenvDir); $attempt++) {
        try {
            Remove-Item -Path $VenvDir -Recurse -Force -ErrorAction Stop
        } catch {
            if ($attempt -ge 5) { Stop-Install "Tidak bisa menghapus $VenvDir ($($_.Exception.Message)). Tutup MikuVision lalu coba lagi." }
            Write-Log "File di .venv masih dipakai, coba lagi ($attempt/5)..." "WARN"
            Start-Sleep -Seconds 3
        }
    }
}

function Install-PythonEnv {
    Write-Step "Python $PythonVersion + virtualenv"
    $code = Invoke-Native $UvExe @("python", "install", $PythonVersion, "--no-bin", "--no-registry")
    if ($code -ne 0) { Stop-Install "uv gagal memasang Python $PythonVersion." }

    $basePython = Get-NativeOutput $UvExe @("python", "find", $PythonVersion, "--python-preference", "only-managed")
    if (-not $basePython) { Stop-Install "Python $PythonVersion terpasang tapi tidak ditemukan oleh uv." }

    # Venv dari `uv venv` memakai launcher yang sama untuk python.exe dan pythonw.exe,
    # sehingga shortcut GUI ikut membuka jendela konsol. Venv bawaan Python tidak.
    $venvCfg = Join-Path $VenvDir "pyvenv.cfg"
    if (Test-Path $VenvDir) {
        $venvVersion = $null
        $madeByUv = $false
        # pyvenv.cfg hilang = venv rusak (misalnya pembuatan sebelumnya terputus)
        if ((Test-Path $VenvPython) -and (Test-Path $venvCfg)) {
            $venvVersion = Get-NativeOutput $VenvPython @("-c", "import sys; print('%d.%d' % sys.version_info[:2])")
            $madeByUv = Select-String -Path $venvCfg -Pattern '^uv\s*=' -Quiet
        }
        if ($venvVersion -eq $PythonVersion -and -not $madeByUv) {
            Write-Log ".venv sudah ada (Python $venvVersion)" "OK"
            return
        }
        Write-Log ".venv (Python '$venvVersion') dibuat ulang." "WARN"
    }
    Remove-VenvDir
    $code = Invoke-Native $basePython @("-m", "venv", "--without-pip", $VenvDir)
    if ($code -ne 0) { Stop-Install "Gagal membuat virtualenv di $VenvDir." }
}

# Memilih build PyTorch: cu128 (default README), cu126 untuk driver lama, cpu tanpa GPU NVIDIA.
function Get-TorchBackend {
    if ($Cpu) {
        Write-Log "-Cpu dipakai: PyTorch versi CPU." "WARN"
        return "cpu"
    }
    $smi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
    if (-not $smi) {
        Write-Log "GPU NVIDIA tidak terdeteksi. Memakai PyTorch CPU: Whisper dan TTS akan jauh lebih lambat. Pertimbangkan WHISPER_MODEL = 'small' di config.py." "WARN"
        return "cpu"
    }
    $gpu = Get-NativeOutput $smi.Source @("--query-gpu=name,driver_version", "--format=csv,noheader")
    $header = Get-NativeOutput $smi.Source @()
    Write-Log "GPU: $gpu"
    if ($header -match "CUDA Version:\s*(\d+)\.(\d+)") {
        $cuda = [version]"$($Matches[1]).$($Matches[2])"
        Write-Log "Driver mendukung CUDA sampai $cuda"
        if ($cuda -ge [version]"12.8") { return "cu128" }
        if ($cuda -ge [version]"12.6") { return "cu126" }
        Write-Log "Driver NVIDIA terlalu lama untuk PyTorch $TorchVersion (butuh CUDA >= 12.6). Memakai CPU; perbarui driver lalu jalankan installer lagi untuk GPU." "WARN"
        return "cpu"
    }
    Write-Log "Versi CUDA dari nvidia-smi tidak terbaca. Memakai cu128." "WARN"
    return "cu128"
}

function Test-RvcModelPresent {
    $weights = Join-Path $RvcDir "weights\miku_default_rvc.pth"
    $index = Get-ChildItem -Path (Join-Path $RvcDir "logs\miku_default_rvc") -Filter "*.index" -ErrorAction SilentlyContinue
    return [bool]((Test-Path $weights) -and $index)
}

function Install-PythonPackages {
    param([string]$Backend)
    Write-Step "PyTorch $TorchVersion ($Backend) + requirements.txt"
    $want = "$TorchVersion+$Backend"
    $installed = Get-NativeOutput $VenvPython @("-c", "import torch; print(torch.__version__)")
    $uvArgs = @("pip", "install", "--python", $VenvPython,
        "-r", (Join-Path $Root "requirements.txt"),
        "torch==$TorchVersion", "torchaudio==$TorchVersion",
        "--torch-backend", $Backend)
    if ($installed -and $installed -ne $want) {
        Write-Log "torch $installed terpasang, diganti ke $want."
        $uvArgs += @("--reinstall-package", "torch", "--reinstall-package", "torchaudio")
    }

    # rvc-python ikut satu resolusi dengan requirements.txt supaya versi numpy/scipy
    # tidak bolak-balik di setiap jalan ulang.
    $script:RvcInstalled = $false
    $rvcWanted = $WithRvc -or (Test-RvcModelPresent)
    if ($rvcWanted) {
        Write-Log "Model RVC ditemukan (atau -WithRvc): rvc-python ikut dipasang."
        $code = Invoke-Native $UvExe ($uvArgs + @("rvc-python==$RvcPythonVersion",
            "--override", (Join-Path $Root "overrides-rvc.txt")))
        if ($code -eq 0) {
            $script:RvcInstalled = $true
        } else {
            Write-Log "rvc-python gagal dipasang. fairseq harus dikompilasi dan butuh 'Visual Studio Build Tools' dengan workload 'Desktop development with C++'. Lanjut tanpa RVC." "WARN"
        }
    }
    if (-not $script:RvcInstalled) {
        $code = Invoke-Native $UvExe $uvArgs
        if ($code -ne 0) { Stop-Install "Instalasi paket Python gagal. Lihat detail di log." }
    }

    $installed = Get-NativeOutput $VenvPython @("-c", "import torch; print(torch.__version__)")
    if ($installed -ne $want) { Stop-Install "torch yang terpasang '$installed', seharusnya '$want'." }
    if ($Backend -ne "cpu") {
        $cudaOk = Get-NativeOutput $VenvPython @("-c", "import torch; print(torch.cuda.is_available())")
        if ($cudaOk -ne "True") { Stop-Install "torch $installed terpasang tapi CUDA tidak bisa dipakai. Perbarui driver NVIDIA, atau jalankan ulang dengan -Cpu." }
    }
    Write-Log "torch $installed siap" "OK"
}

function Install-Unidic {
    Write-Step "Kamus unidic (MeloTTS Jepang)"
    $dicdir = Get-NativeOutput $VenvPython @("-c", "import unidic; print(unidic.DICDIR)")
    if (-not $dicdir) { Stop-Install "Paket unidic tidak terpasang." }
    if (Test-Path (Join-Path $dicdir "mecabrc")) {
        Write-Log "Sudah diunduh: $dicdir" "OK"
        return
    }
    Write-Log "Mengunduh kamus (sekitar 500 MB, sekali saja)..."
    $code = Invoke-Native $VenvPython @("-m", "unidic", "download") -Quiet
    if ($code -ne 0 -or -not (Test-Path (Join-Path $dicdir "mecabrc"))) {
        Stop-Install "Gagal mengunduh kamus unidic. Coba manual: .venv\Scripts\python.exe -m unidic download"
    }
    Write-Log "Kamus unidic siap" "OK"
}

function Test-Imports {
    Write-Step "Cek import modul"
    $code = Invoke-Native $VenvPython @("-c",
        "import torch, faster_whisper, melo.api, customtkinter, pygame, ollama, sounddevice, webrtcvad; print('import OK')")
    if ($code -ne 0) { Stop-Install "Ada modul yang gagal di-import. Lihat log." }
}

function Get-OllamaExe {
    $cmd = Get-Command ollama -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $default = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
    if (Test-Path $default) { return $default }
    return $null
}

function Test-OllamaServer {
    try {
        Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/version" -TimeoutSec 3 | Out-Null
        return $true
    } catch {
        return $false
    }
}

function Get-ConfiguredModel {
    $match = Select-String -Path (Join-Path $Root "config.py") -Pattern '^\s*OLLAMA_MODEL\s*=\s*"([^"]+)"' | Select-Object -First 1
    if (-not $match) { Stop-Install "OLLAMA_MODEL tidak ditemukan di config.py." }
    return $match.Matches[0].Groups[1].Value
}

function Install-OllamaModel {
    Write-Step "Ollama + model LLM"
    $ollama = Get-OllamaExe
    if (-not $ollama) {
        Install-WithWinget "Ollama.Ollama" "Ollama"
        $ollama = Get-OllamaExe
        if (-not $ollama) { Stop-Install "Ollama sudah dipasang tapi ollama.exe tidak ditemukan. Buka jendela baru lalu jalankan installer lagi." }
    }
    Write-Log "Ollama: $(Get-NativeOutput $ollama @('--version'))"
    if ($env:OLLAMA_MODELS) { Write-Log "Lokasi model Ollama (OLLAMA_MODELS): $env:OLLAMA_MODELS" }

    if (-not (Test-OllamaServer)) {
        Write-Log "Server Ollama belum jalan, menyalakan..."
        $app = Join-Path (Split-Path $ollama) "ollama app.exe"
        if (Test-Path $app) {
            Start-Process -FilePath $app
        } else {
            Start-Process -FilePath $ollama -ArgumentList "serve" -WindowStyle Hidden
        }
        $deadline = (Get-Date).AddSeconds(45)
        while (-not (Test-OllamaServer)) {
            if ((Get-Date) -gt $deadline) { Stop-Install "Server Ollama tidak merespons di 127.0.0.1:11434. Buka aplikasi Ollama lalu jalankan installer lagi." }
            Start-Sleep -Seconds 2
        }
    }

    $model = Get-ConfiguredModel
    $tags = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 10
    $names = @($tags.models | ForEach-Object { $_.name })
    if ($names -contains $model) {
        Write-Log "Model $model sudah ada" "OK"
        return
    }
    Write-Log "Mengunduh model $model (beberapa GB)..."
    $code = Invoke-Native $ollama @("pull", $model) -Quiet
    if ($code -ne 0) { Stop-Install "ollama pull $model gagal." }
    Write-Log "Model $model siap" "OK"
}

function Show-RvcStatus {
    Write-Step "Suara Miku (RVC, opsional)"
    if (-not (Test-RvcModelPresent)) {
        Write-Log "Model RVC tidak di-bundle. Tanpa RVC, Miku memakai suara MeloTTS Jepang. Letakkan model sendiri (lihat README bagian 'Suara Miku (RVC)') lalu jalankan installer lagi."
    } elseif ($script:RvcInstalled) {
        Write-Log "Model RVC ditemukan dan rvc-python terpasang." "OK"
    } else {
        Write-Log "Model RVC ditemukan tapi rvc-python tidak terpasang; Miku memakai suara MeloTTS." "WARN"
    }
}

function New-DesktopShortcut {
    Write-Step "Shortcut desktop"
    $icon = Join-Path $ToolsDir "mikuvision.ico"
    $iconScript = @"
import sys
from PIL import Image
import config
sheet = Image.open(config.MIKU_SPRITE_SHEET).convert('RGBA')
frame = sheet.crop((0, 0, config.MIKU_FRAME_W, config.MIKU_FRAME_H))
side = max(frame.size)
square = Image.new('RGBA', (side, side), (0, 0, 0, 0))
square.paste(frame, ((side - frame.width) // 2, (side - frame.height) // 2))
square.save(sys.argv[1], sizes=[(256, 256), (64, 64), (48, 48), (32, 32), (16, 16)])
"@
    Push-Location $Root
    try {
        $code = Invoke-Native $VenvPython @("-c", $iconScript, $icon) -Quiet
    } finally {
        Pop-Location
    }
    if ($code -ne 0) { Write-Log "Ikon gagal dibuat, shortcut memakai ikon Python." "WARN" }

    $desktop = [Environment]::GetFolderPath("Desktop")
    $lnkPath = Join-Path $desktop "$AppName.lnk"
    $shell = New-Object -ComObject WScript.Shell
    $lnk = $shell.CreateShortcut($lnkPath)
    $lnk.TargetPath = Join-Path $VenvDir "Scripts\pythonw.exe"
    $lnk.Arguments = '"' + (Join-Path $Root "gui.py") + '"'
    $lnk.WorkingDirectory = $Root
    $lnk.Description = "$AppName - asisten desktop Hatsune Miku"
    if (Test-Path $icon) { $lnk.IconLocation = $icon }
    $lnk.Save()
    Write-Log "Shortcut: $lnkPath" "OK"
}

function Invoke-SelfTest {
    Write-Step "Verifikasi: miku.py --test"
    Write-Log "Jalankan pertama kali mengunduh Whisper large-v3-turbo (sekitar 1,6 GB) bila belum ada di cache Hugging Face."
    if ($env:HF_HOME) {
        Write-Log "Cache Hugging Face (HF_HOME): $env:HF_HOME"
    } else {
        Write-Log "Cache Hugging Face: $env:USERPROFILE\.cache\huggingface (atur HF_HOME untuk memindahkannya)"
    }
    Push-Location $Root
    try {
        $code = Invoke-Native $VenvPython @("miku.py", "--test")
    } finally {
        Pop-Location
    }
    $passed = Select-String -Path $LogFile -Pattern "Test mode - Initialization successful" -SimpleMatch -Quiet
    if ($code -ne 0 -or -not $passed) { Stop-Install "miku.py --test gagal (exit $code). Lihat log." }
    Write-Log "miku.py --test lulus" "OK"
    if ($script:RvcInstalled -and -not (Select-String -Path $LogFile -Pattern "RVC ready" -SimpleMatch -Quiet)) {
        Write-Log "rvc-python terpasang tapi RVC gagal dimuat; cari '[VoiceConverter]' di log. Miku memakai suara MeloTTS." "WARN"
    }
}

# ---------------------------------------------------------------- main
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
Write-Log "$AppName installer - log: $LogFile"

try {
    Test-Prerequisites
    Install-Uv
    Install-PythonEnv
    $script:TorchBackend = Get-TorchBackend
    Install-PythonPackages $script:TorchBackend
    Install-Unidic
    Test-Imports
    if ($SkipOllama) { Write-Log "-SkipOllama: Ollama dilewati." "WARN" } else { Install-OllamaModel }
    Show-RvcStatus
    if ($SkipShortcut) { Write-Log "-SkipShortcut: shortcut dilewati." } else { New-DesktopShortcut }
    if ($SkipTest -or $SkipOllama) { Write-Log "Verifikasi miku.py --test dilewati." "WARN" } else { Invoke-SelfTest }
} catch {
    if ($script:KnownFailure) {
        Write-Log $script:KnownFailure "ERROR"
    } else {
        Write-Log ("Error tak terduga: {0}" -f $_.Exception.Message) "ERROR"
        Write-Log $_.ScriptStackTrace "ERROR"
    }
    Write-Log "Instalasi berhenti. Perbaiki masalah di atas lalu jalankan installer lagi (langkah yang sudah beres akan dilewati)." "ERROR"
    Write-Log "Log lengkap: $LogFile" "ERROR"
    exit 1
}

Write-Log ""
Write-Log "Instalasi selesai. Buka '$AppName' dari desktop, atau jalankan: .venv\Scripts\python.exe gui.py" "OK"
exit 0
