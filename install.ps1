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

    Kode keluar: 0 = selesai, 1 = gagal dengan penyebab yang sudah dijelaskan di log,
    2 = error tak terduga.

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

.PARAMETER ModelDir
    Simpan model Ollama di <ModelDir>\ollama dan cache Hugging Face (Whisper, MeloTTS) di
    <ModelDir>\huggingface. OLLAMA_MODELS dan HF_HOME diatur sebagai variabel user, dan
    Ollama yang sedang jalan dinyalakan ulang supaya memakai lokasi baru.

.PARAMETER WithVision
    Unduh juga model visi untuk membaca layar (VISION_MODEL di config.py, sekitar 3,3 GB).

.PARAMETER RvcModel
    File bobot RVC (.pth) yang disalin ke models\miku_default_rvc. Harus bersama -RvcIndex.

.PARAMETER RvcIndex
    File index RVC (.index) yang disalin ke models\miku_default_rvc. Harus bersama -RvcModel.

.PARAMETER StartMenu
    Buat juga shortcut di Start Menu (folder MikuVision).

.PARAMETER Progress
    Untuk MikuVision Setup: selain log biasa, cetak satu baris "##MIKU {json}" per kejadian
    (step, warn, error, done) ke stdout. Lihat docs/PLAN_INSTALLER.md bagian 4.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File install.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File install.ps1 -Yes -ModelDir D:\MikuVision\models -WithVision
#>
[CmdletBinding()]
param(
    [switch]$Yes,
    [switch]$Cpu,
    [switch]$WithRvc,
    [switch]$SkipOllama,
    [switch]$SkipShortcut,
    [switch]$SkipTest,
    [string]$PythonVersion = "3.10",
    [string]$ModelDir = "",
    [switch]$WithVision,
    [string]$RvcModel = "",
    [string]$RvcIndex = "",
    [switch]$StartMenu,
    [switch]$Progress,
    # Untuk tests/test_install_ps1.py: hanya memancarkan tiga baris ##MIKU lalu keluar
    [Parameter(DontShow)]
    [switch]$SelfCheck
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
# Nama file index yang dibaca config.py (RVCConfig.index_path); -RvcIndex disalin dengan nama ini
$RvcIndexName = "added_IVF4457_Flat_nprobe_1_miku_default_rvc_v2.index"
# Cadangan tanpa winget: installer resmi Ollama (Inno Setup, per-user tanpa admin)
$OllamaSetupUrl = "https://ollama.com/download/OllamaSetup.exe"
$OllamaSigner   = "CN=Ollama Inc.,*"

$Root       = $PSScriptRoot
$ToolsDir   = Join-Path $Root ".tools"
$UvDir      = Join-Path $ToolsDir "uv"
$UvExe      = Join-Path $UvDir "uv.exe"
$VenvDir    = Join-Path $Root ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$RvcDir     = Join-Path $Root "models\miku_default_rvc"
$LogDir     = if ($SelfCheck) { Join-Path ([IO.Path]::GetTempPath()) "mikuvision-selfcheck" } else { Join-Path $Root "logs" }
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
# -Progress: baris mesin untuk wizard, satu JSON per baris (stdout UTF-8)
$script:StepIndex = 0
$script:StepTotal = 0

function Write-ProgressEvent {
    param([Collections.IDictionary]$Data)
    if (-not ($Progress -or $SelfCheck)) { return }
    [Console]::Out.WriteLine("##MIKU " + ($Data | ConvertTo-Json -Compress))
}

function Write-Log {
    # -NoEvent: baris penutup error (jejak stack, lokasi log) tidak menimpa pesan error di wizard
    param([string]$Message, [string]$Level = "INFO", [switch]$NoEvent)
    $line = "[{0}] [{1}] {2}" -f (Get-Date -Format "HH:mm:ss"), $Level, $Message
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
    switch ($Level) {
        "WARN"  { Write-Host $line -ForegroundColor Yellow }
        "ERROR" { Write-Host $line -ForegroundColor Red }
        "OK"    { Write-Host $line -ForegroundColor Green }
        default { Write-Host $line }
    }
    if ($Level -in @("WARN", "ERROR") -and -not $NoEvent) {
        Write-ProgressEvent ([ordered]@{ event = $Level.ToLower(); message = $Message })
    }
}

function Write-Step {
    param([string]$Title)
    $script:StepIndex++
    Write-Log ""
    Write-Log "==== $Title ===="
    Write-ProgressEvent ([ordered]@{ event = "step"; index = $script:StepIndex; total = $script:StepTotal; title = $Title })
}

# Kegagalan yang sudah dijelaskan ke user; dibedakan dari error tak terduga di blok catch utama.
$script:KnownFailure = $null

function Stop-Install {
    param([string]$Message)
    $script:KnownFailure = $Message
    throw $Message
}

# Menjalankan program eksternal; stdout+stderr masuk ke log. Mengembalikan exit code.
# Teks keluarannya disimpan di $script:NativeOutput untuk diperiksa pemanggil.
function Invoke-Native {
    param([string]$Exe, [string[]]$Arguments, [switch]$Quiet)
    Write-Log ("> {0} {1}" -f (Split-Path $Exe -Leaf), ($Arguments -join " "))
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"   # stderr dari program native bukan error PowerShell
    $lines = New-Object System.Collections.Generic.List[string]
    try {
        & $Exe @Arguments 2>&1 | ForEach-Object {
            $text = "$_"
            # PowerShell 5.1 menampilkan baris stderr kosong sebagai nama tipe exception
            if ($text -eq "System.Management.Automation.RemoteException") { $text = "" }
            $lines.Add($text)
            Add-Content -Path $LogFile -Value "    $text" -Encoding UTF8
            if (-not $Quiet) { Write-Host "    $text" }
        }
        return $LASTEXITCODE
    } finally {
        $script:NativeOutput = $lines -join "`n"
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

# Dipisah supaya test bisa menggantinya tanpa mengubah variabel user sungguhan
function Set-UserEnvironment {
    param([string]$Name, [string]$Value)
    [Environment]::SetEnvironmentVariable($Name, $Value, "User")
}

function Resolve-UserPath {
    param([string]$Path)
    return $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Path)
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

# File yang baru diekstrak uv kadang masih dikunci antivirus saat di-rename ("Access is denied.
# (os error 5)"); dijalankan sekali lagi, cache yang sudah terunduh dipakai ulang.
function Test-FileLockError {
    param([string]$Output)
    return $Output -match "os error (5|32)\)"
}

function Invoke-UvInstall {
    param([string[]]$Arguments)
    $code = Invoke-Native $UvExe $Arguments
    if ($code -ne 0 -and (Test-FileLockError $script:NativeOutput)) {
        Write-Log "File di cache uv dikunci program lain (biasanya antivirus). Dicoba sekali lagi..." "WARN"
        Start-Sleep -Seconds 5
        $code = Invoke-Native $UvExe $Arguments
    }
    return $code
}

# ---------------------------------------------------------------- langkah
# Setiap fungsi langkah memanggil Write-Step tepat sekali (dicek tests/test_install_ps1.py),
# supaya total langkah di -Progress sama dengan daftar dari Get-InstallSteps.
function Get-InstallSteps {
    $steps = @("Test-Prerequisites")
    if ($ModelDir) { $steps += "Set-ModelDir" }
    if ($RvcModel -or $RvcIndex) { $steps += "Copy-RvcModel" }
    $steps += @("Install-Uv", "Install-PythonEnv", "Install-PythonPackages", "Install-Unidic", "Test-Imports")
    if (-not $SkipOllama) {
        $steps += "Install-OllamaModel"
        if ($WithVision) { $steps += "Install-VisionModel" }
    }
    $steps += "Show-RvcStatus"
    if (-not $SkipShortcut -or $StartMenu) { $steps += "New-Shortcuts" }
    if (-not ($SkipTest -or $SkipOllama)) { $steps += "Invoke-SelfTest" }
    return $steps
}

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

# -ModelDir: dijalankan sebelum Ollama dan miku.py --test, yang membaca kedua variabel ini.
function Set-ModelDir {
    Write-Step "Folder model"
    if ($ModelDir.Contains('"')) { Stop-Install "Folder model tidak boleh berisi tanda kutip: $ModelDir" }
    $base = Resolve-UserPath $ModelDir
    $targets = [ordered]@{
        OLLAMA_MODELS = Join-Path $base "ollama"
        HF_HOME       = Join-Path $base "huggingface"
    }
    foreach ($name in $targets.Keys) {
        $path = $targets[$name]
        try {
            New-Item -ItemType Directory -Force -Path $path | Out-Null
        } catch {
            Stop-Install "Folder $path tidak bisa dibuat: $($_.Exception.Message)"
        }
        $previous = [Environment]::GetEnvironmentVariable($name, "User")
        if ($previous -ne $path) {
            Set-UserEnvironment $name $path
            if ($name -eq "OLLAMA_MODELS") { $script:OllamaModelsChanged = $true }
            if ($previous) { Write-Log "$name sebelumnya $previous. Isinya tidak dipindah; model yang belum ada di folder baru akan diunduh lagi." "WARN" }
        }
        Set-Item -Path "env:$name" -Value $path
        Write-Log "$name = $path" "OK"
    }
}

function Copy-RvcModel {
    Write-Step "Model RVC"
    if (-not ($RvcModel -and $RvcIndex)) {
        Stop-Install "-RvcModel dan -RvcIndex harus dipakai bersama: file bobot .pth dan file .index."
    }
    $copies = @(
        @{ Source = $RvcModel; Extension = ".pth";   Target = Join-Path $RvcDir "weights\miku_default_rvc.pth" },
        @{ Source = $RvcIndex; Extension = ".index"; Target = Join-Path $RvcDir "logs\miku_default_rvc\$RvcIndexName" }
    )
    foreach ($copy in $copies) {
        $source = Resolve-UserPath $copy.Source
        if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { Stop-Install "File RVC tidak ditemukan: $source" }
        if ([IO.Path]::GetExtension($source) -ne $copy.Extension) {
            Stop-Install "File RVC harus berakhiran $($copy.Extension): $source"
        }
        New-Item -ItemType Directory -Force -Path (Split-Path $copy.Target) | Out-Null
        if ((Resolve-UserPath $copy.Target) -eq $source) {
            Write-Log "Sudah di tempatnya: $source" "OK"
            continue
        }
        Copy-Item -LiteralPath $source -Destination $copy.Target -Force
        Write-Log "Disalin: $source -> $($copy.Target)" "OK"
    }
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

# Versi CUDA tertinggi yang didukung driver, dari header `nvidia-smi`. Driver lama menulis
# "CUDA Version: 12.8", driver baru (621) "CUDA UMD Version: 13.5".
function Get-DriverCudaVersion {
    param([string]$Header)
    if ($Header -match "CUDA (?:UMD )?Version:\s*(\d+)\.(\d+)") {
        return [version]"$($Matches[1]).$($Matches[2])"
    }
    return $null
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
    Write-Log "GPU: $gpu"
    $cuda = Get-DriverCudaVersion (Get-NativeOutput $smi.Source @())
    if ($cuda) {
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
    Write-Step "PyTorch $TorchVersion + requirements.txt"
    $Backend = Get-TorchBackend
    $script:TorchBackend = $Backend
    $want = "$TorchVersion+$Backend"
    Write-Log "Build PyTorch: $want"
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
        $code = Invoke-UvInstall ($uvArgs + @("rvc-python==$RvcPythonVersion",
            "--override", (Join-Path $Root "overrides-rvc.txt")))
        if ($code -eq 0) {
            $script:RvcInstalled = $true
        } elseif (Test-FileLockError $script:NativeOutput) {
            Write-Log "rvc-python gagal dipasang: file di cache uv masih dikunci program lain (biasanya antivirus). Lanjut tanpa RVC; jalankan installer lagi untuk mencoba ulang." "WARN"
        } else {
            Write-Log "rvc-python gagal dipasang. fairseq harus dikompilasi dan butuh 'Visual Studio Build Tools' dengan workload 'Desktop development with C++'. Lanjut tanpa RVC." "WARN"
        }
    }
    if (-not $script:RvcInstalled) {
        $code = Invoke-UvInstall $uvArgs
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

# Ollama membaca OLLAMA_MODELS hanya saat start: setelah -ModelDir mengubahnya, matikan dulu
# (aplikasi tray dan server), lalu Install-OllamaModel menyalakannya lagi dengan lokasi baru.
function Stop-Ollama {
    Get-Process -Name "ollama app", "ollama", "llama-server" -ErrorAction SilentlyContinue |
        Stop-Process -Force -ErrorAction SilentlyContinue
    $deadline = (Get-Date).AddSeconds(15)
    while (Test-OllamaServer) {
        if ((Get-Date) -gt $deadline) { Stop-Install "Ollama tidak bisa dimatikan. Tutup Ollama dari system tray lalu jalankan installer lagi." }
        Start-Sleep -Seconds 1
    }
}

function Test-OllamaSetupSignature {
    param([string]$Path)
    if (-not (Test-Path $Path)) { return $false }
    $signature = Get-AuthenticodeSignature -FilePath $Path
    return ($signature.Status -eq "Valid") -and ($signature.SignerCertificate.Subject -like $OllamaSigner)
}

# Tanpa winget (Windows LTSC, sebagian laptop kantor): installer resmi dari ollama.com,
# dipasang diam-diam ke %LOCALAPPDATA%\Programs\Ollama. Setelah selesai, installer itu sendiri
# menyalakan aplikasi Ollama.
function Install-OllamaFromWebsite {
    if (-not (Confirm-Action "Ollama belum terpasang dan winget tidak tersedia. Unduh dan pasang Ollama dari ollama.com (sekitar 1,7 GB)?")) {
        Stop-Install "Ollama dibutuhkan. Pasang dari https://ollama.com/download lalu jalankan installer ini lagi."
    }
    New-Item -ItemType Directory -Force -Path $ToolsDir | Out-Null
    $setup = Join-Path $ToolsDir "OllamaSetup.exe"
    if (-not (Test-OllamaSetupSignature $setup)) {
        $partial = "$setup.part"
        Write-Log "Mengunduh $OllamaSetupUrl"
        try {
            Invoke-WebRequest -Uri $OllamaSetupUrl -OutFile $partial -UseBasicParsing
        } catch {
            Remove-Item $partial -ErrorAction SilentlyContinue
            Stop-Install "Gagal mengunduh installer Ollama: $($_.Exception.Message)"
        }
        Move-Item -Force -Path $partial -Destination $setup
        if (-not (Test-OllamaSetupSignature $setup)) {
            Remove-Item $setup -ErrorAction SilentlyContinue
            Stop-Install "Tanda tangan digital installer Ollama tidak valid. Unduhan rusak atau dimodifikasi."
        }
    }
    Write-Log "Memasang Ollama tanpa jendela..."
    # WaitForExit, bukan Start-Process -Wait: -Wait ikut menunggu aplikasi Ollama yang dinyalakan installer
    $process = Start-Process -FilePath $setup -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART" -PassThru
    $null = $process.Handle   # tanpa ini ExitCode kosong setelah proses selesai
    $process.WaitForExit()
    if ($process.ExitCode -ne 0) { Stop-Install "Installer Ollama gagal (exit $($process.ExitCode))." }
    Remove-Item $setup -ErrorAction SilentlyContinue
    Update-SessionPath
}

function Get-ConfigValue {
    param([string]$Name)
    $match = Select-String -Path (Join-Path $Root "config.py") -Pattern "^\s*$Name\s*=\s*`"([^`"]+)`"" | Select-Object -First 1
    if (-not $match) { Stop-Install "$Name tidak ditemukan di config.py." }
    return $match.Matches[0].Groups[1].Value
}

function Invoke-OllamaPull {
    param([string]$Model)
    $tags = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 10
    $names = @($tags.models | ForEach-Object { $_.name })
    if ($names -contains $Model) {
        Write-Log "Model $Model sudah ada" "OK"
        return
    }
    Write-Log "Mengunduh model $Model (beberapa GB)..."
    $code = Invoke-Native $script:OllamaExe @("pull", $Model) -Quiet
    if ($code -ne 0) { Stop-Install "ollama pull $Model gagal." }
    Write-Log "Model $Model siap" "OK"
}

function Install-OllamaModel {
    Write-Step "Ollama + model LLM"
    $ollama = Get-OllamaExe
    if (-not $ollama) {
        if (Get-Command winget -ErrorAction SilentlyContinue) {
            Install-WithWinget "Ollama.Ollama" "Ollama"
        } else {
            Install-OllamaFromWebsite
        }
        $ollama = Get-OllamaExe
        if (-not $ollama) { Stop-Install "Ollama sudah dipasang tapi ollama.exe tidak ditemukan. Buka jendela baru lalu jalankan installer lagi." }
    }
    $script:OllamaExe = $ollama
    Write-Log "Ollama: $(Get-NativeOutput $ollama @('--version'))"
    if ($env:OLLAMA_MODELS) { Write-Log "Lokasi model Ollama (OLLAMA_MODELS): $env:OLLAMA_MODELS" }

    if ($script:OllamaModelsChanged -and (Test-OllamaServer)) {
        Write-Log "Ollama sedang jalan dengan lokasi model lama; dinyalakan ulang."
        Stop-Ollama
    }
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

    Invoke-OllamaPull (Get-ConfigValue "OLLAMA_MODEL")
}

function Install-VisionModel {
    Write-Step "Model visi (membaca layar)"
    Invoke-OllamaPull (Get-ConfigValue "VISION_MODEL")
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

function New-AppIcon {
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
    return $icon
}

function New-AppShortcut {
    param([string]$LnkPath, [string]$Icon)
    $shell = New-Object -ComObject WScript.Shell
    $lnk = $shell.CreateShortcut($LnkPath)
    $lnk.TargetPath = Join-Path $VenvDir "Scripts\pythonw.exe"
    $lnk.Arguments = '"' + (Join-Path $Root "gui.py") + '"'
    $lnk.WorkingDirectory = $Root
    $lnk.Description = "$AppName - asisten desktop Hatsune Miku"
    if (Test-Path $Icon) { $lnk.IconLocation = $Icon }
    $lnk.Save()
    Write-Log "Shortcut: $LnkPath" "OK"
}

function New-Shortcuts {
    Write-Step "Shortcut"
    $icon = New-AppIcon
    if (-not $SkipShortcut) {
        New-AppShortcut (Join-Path ([Environment]::GetFolderPath("Desktop")) "$AppName.lnk") $icon
    }
    if ($StartMenu) {
        $folder = Join-Path ([Environment]::GetFolderPath("Programs")) $AppName
        New-Item -ItemType Directory -Force -Path $folder | Out-Null
        New-AppShortcut (Join-Path $folder "$AppName.lnk") $icon
    }
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

# Di-source oleh test (". .\install.ps1"): hanya fungsi yang dimuat, instalasi tidak jalan
if ($MyInvocation.InvocationName -eq ".") { return }

# ---------------------------------------------------------------- main
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
Write-Log "$AppName installer - log: $LogFile"

if ($SelfCheck) {
    # Jalur yang sama dengan instalasi (Write-Step, Write-Log WARN, akhir main), tanpa memasang apa pun.
    # Judul berisi huruf Jepang supaya test ikut memeriksa UTF-8; file ini sendiri tetap ASCII
    # karena PowerShell 5.1 membaca script tanpa BOM sebagai ANSI.
    $script:StepTotal = 1
    Write-Step ("Self-check " + [char]0x30DF + [char]0x30AF)
    Write-Log "Peringatan contoh" "WARN"
    Write-ProgressEvent ([ordered]@{ event = "done"; ok = $true })
    exit 0
}

$steps = Get-InstallSteps
$script:StepTotal = $steps.Count
if ($SkipOllama) { Write-Log "-SkipOllama: Ollama dilewati." "WARN" }
if ($SkipShortcut) { Write-Log "-SkipShortcut: shortcut desktop dilewati." }
if ($SkipTest -or $SkipOllama) { Write-Log "Verifikasi miku.py --test dilewati." "WARN" }

try {
    foreach ($step in $steps) { & $step }
} catch {
    if ($script:KnownFailure) {
        Write-Log $script:KnownFailure "ERROR"
        $exitCode = 1
    } else {
        Write-Log ("Error tak terduga: {0}" -f $_.Exception.Message) "ERROR"
        Write-Log $_.ScriptStackTrace "ERROR" -NoEvent
        $exitCode = 2
    }
    Write-Log "Instalasi berhenti. Perbaiki masalah di atas lalu jalankan installer lagi (langkah yang sudah beres akan dilewati)." "ERROR" -NoEvent
    Write-Log "Log lengkap: $LogFile" "ERROR" -NoEvent
    Write-ProgressEvent ([ordered]@{ event = "done"; ok = $false })
    exit $exitCode
}

Write-Log ""
Write-Log "Instalasi selesai. Buka '$AppName' dari desktop, atau jalankan: .venv\Scripts\python.exe gui.py" "OK"
Write-ProgressEvent ([ordered]@{ event = "done"; ok = $true })
exit 0
