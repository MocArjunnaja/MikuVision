"""install.ps1: baris progres untuk MikuVision Setup dan opsi baru (tanpa memasang apa pun)."""

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
INSTALL_PS1 = ROOT / "install.ps1"
# powershell = Windows PowerShell 5.1 yang dipakai install.bat; pwsh = PowerShell 7
SHELLS = [s for s in ("powershell", "pwsh") if shutil.which(s)]

pytestmark = pytest.mark.skipif(sys.platform != "win32" or not SHELLS,
                                reason="installer Windows, butuh PowerShell")

ALL_STEPS = ["Test-Prerequisites", "Set-ModelDir", "Copy-RvcModel", "Install-Uv", "Install-PythonEnv",
             "Install-PythonPackages", "Install-Unidic", "Test-Imports", "Install-OllamaModel",
             "Install-VisionModel", "Show-RvcStatus", "New-Shortcuts", "Invoke-SelfTest"]


def _q(path) -> str:
    """Path untuk string PowerShell berkutip tunggal."""
    return str(path).replace("'", "''")


def _run(args, shell=None):
    shell = shell or SHELLS[0]
    result = subprocess.run([shell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", *args],
                            capture_output=True, timeout=120)
    return result.returncode, result.stdout.decode("utf-8"), result.stderr.decode("utf-8", "replace")


def _source(tmp_path, body, flags=""):
    """Jalankan `body` setelah install.ps1 di-source (instalasi tidak jalan); log ke tmp_path."""
    script = f". '{_q(INSTALL_PS1)}' {flags}\n$LogFile = '{_q(tmp_path / 'install.log')}'\n{body}"
    code, out, err = _run(["-Command", script])
    assert code == 0, out + err
    return out


def _events(stdout):
    return [json.loads(line[len("##MIKU "):]) for line in stdout.splitlines() if line.startswith("##MIKU ")]


@pytest.mark.parametrize("shell", SHELLS)
def test_install_ps1_parses(shell):
    code, out, err = _run(["-Command",
                           f"$e = $null; [void][Management.Automation.Language.Parser]::ParseFile("
                           f"'{_q(INSTALL_PS1)}', [ref]$null, [ref]$e); $e.Count"], shell)
    assert code == 0 and out.strip() == "0", out + err


def test_install_ps1_is_ascii():
    # PowerShell 5.1 membaca script tanpa BOM sebagai ANSI: huruf non-ASCII di file jadi rusak
    assert all(byte < 0x80 for byte in INSTALL_PS1.read_bytes())


@pytest.mark.parametrize("shell", SHELLS)
def test_selfcheck_emits_progress_json(shell):
    code, out, err = _run(["-File", str(INSTALL_PS1), "-SelfCheck"], shell)
    assert code == 0, out + err

    events = _events(out)
    assert [e["event"] for e in events] == ["step", "warn", "done"]
    assert events[0] == {"event": "step", "index": 1, "total": 1, "title": "Self-check ミク"}
    assert events[1] == {"event": "warn", "message": "Peringatan contoh"}
    assert events[2] == {"event": "done", "ok": True}
    # Log biasa tetap tercetak di samping baris mesin
    assert "[WARN] Peringatan contoh" in out


def test_progress_lines_only_with_progress_flag(tmp_path):
    body = 'Write-Step "Contoh"\nWrite-Log "awas" "WARN"\nWrite-Log "jejak stack" "ERROR" -NoEvent'
    assert _events(_source(tmp_path, body)) == []

    events = _events(_source(tmp_path, "$script:StepTotal = 4\n" + body, "-Progress"))
    assert events == [
        {"event": "step", "index": 1, "total": 4, "title": "Contoh"},
        {"event": "warn", "message": "awas"},
    ]


DEFAULT_STEPS = ["Test-Prerequisites", "Install-Uv", "Install-PythonEnv", "Install-PythonPackages",
                 "Install-Unidic", "Test-Imports", "Install-OllamaModel", "Show-RvcStatus",
                 "New-Shortcuts", "Invoke-SelfTest"]


@pytest.mark.parametrize("flags, expected", [
    ("", DEFAULT_STEPS),
    ("-ModelDir D:\\m -RvcModel a.pth -RvcIndex a.index -WithVision -StartMenu", ALL_STEPS),
    ("-SkipOllama -WithVision", [s for s in DEFAULT_STEPS if s not in ("Install-OllamaModel", "Invoke-SelfTest")]),
    ("-SkipTest", DEFAULT_STEPS[:-1]),
    ("-SkipShortcut", [s for s in DEFAULT_STEPS if s != "New-Shortcuts"]),
    ("-SkipShortcut -StartMenu", DEFAULT_STEPS),
])
def test_install_steps(tmp_path, flags, expected):
    assert _source(tmp_path, "(Get-InstallSteps) -join ','", flags).strip().split(",") == expected


def test_every_step_writes_one_step_header(tmp_path):
    # Total di baris "step" dihitung dari Get-InstallSteps; satu Write-Step per langkah
    body = (
        "$ast = [Management.Automation.Language.Parser]::ParseFile($PSCommandPath_, [ref]$null, [ref]$null)\n"
        "foreach ($f in $ast.FindAll({ $args[0] -is [Management.Automation.Language.FunctionDefinitionAst] }, $true)) {\n"
        "  $n = @($f.Body.FindAll({ $args[0] -is [Management.Automation.Language.CommandAst] -and "
        "$args[0].GetCommandName() -eq 'Write-Step' }, $true)).Count\n"
        "  \"$($f.Name)=$n\"\n"
        "}"
    ).replace("$PSCommandPath_", f"'{_q(INSTALL_PS1)}'")
    counts = dict(line.split("=") for line in _source(tmp_path, body).split())
    assert {name: counts.get(name) for name in ALL_STEPS} == {name: "1" for name in ALL_STEPS}
    assert {name for name, n in counts.items() if n != "0"} == set(ALL_STEPS)


def test_rvc_index_name_matches_config():
    config = (ROOT / "config.py").read_text(encoding="utf-8")
    from_config = re.search(r'index_path=str\(RVC_MODELS_DIR / .*"([^"]+\.index)"\)', config).group(1)
    from_installer = re.search(r'^\$RvcIndexName = "([^"]+)"', INSTALL_PS1.read_text(), re.M).group(1)
    assert from_installer == from_config


def test_config_value_reads_vision_model(tmp_path):
    config = (ROOT / "config.py").read_text(encoding="utf-8")
    expected = re.search(r'^VISION_MODEL = "([^"]+)"', config, re.M).group(1)
    assert _source(tmp_path, "Get-ConfigValue VISION_MODEL").strip() == expected


def _rvc_files(tmp_path, model_name="miku.pth", index_name="trained_v2.index"):
    source = tmp_path / "unduhan"
    source.mkdir()
    (source / model_name).write_bytes(b"bobot")
    (source / index_name).write_bytes(b"index")
    return source / model_name, source / index_name


def test_copy_rvc_model(tmp_path):
    model, index = _rvc_files(tmp_path)
    rvc_dir = tmp_path / "models" / "miku_default_rvc"
    out = _source(tmp_path, f"$RvcDir = '{_q(rvc_dir)}'\n$RvcModel = '{_q(model)}'\n$RvcIndex = '{_q(index)}'\n"
                            "Copy-RvcModel\nTest-RvcModelPresent")

    assert out.strip().splitlines()[-1] == "True"
    assert (rvc_dir / "weights" / "miku_default_rvc.pth").read_bytes() == b"bobot"
    index_name = "added_IVF4457_Flat_nprobe_1_miku_default_rvc_v2.index"
    assert (rvc_dir / "logs" / "miku_default_rvc" / index_name).read_bytes() == b"index"


@pytest.mark.parametrize("model, index, message", [
    ("miku.pth", "", "harus dipakai bersama"),
    ("miku.zip", "trained.index", "harus berakhiran .pth"),
    ("hilang.pth", "trained.index", "tidak ditemukan"),
])
def test_copy_rvc_model_rejects(tmp_path, model, index, message):
    _rvc_files(tmp_path, "miku.pth", "trained.index")
    (tmp_path / "unduhan" / "miku.zip").write_bytes(b"zip")
    source = tmp_path / "unduhan"
    rvc_dir = tmp_path / "models"
    model_path = _q(source / model) if model else ""
    index_path = _q(source / index) if index else ""
    out = _source(tmp_path, f"$RvcDir = '{_q(rvc_dir)}'\n$RvcModel = '{model_path}'\n$RvcIndex = '{index_path}'\n"
                            'try { Copy-RvcModel } catch { "GAGAL: $KnownFailure" }')
    assert "GAGAL: " in out and message in out
    assert not (rvc_dir / "weights").exists()


# Variabel user tidak pernah diubah di test: Set-UserEnvironment diganti pencatat
FAKE_USER_ENV = '$UserEnv = @()\nfunction Set-UserEnvironment { param($Name, $Value) $script:UserEnv += "$Name=$Value" }\n'


def test_set_model_dir(tmp_path):
    models = tmp_path / "Miku models"
    out = _source(tmp_path, FAKE_USER_ENV + f"$ModelDir = '{_q(models)}'\nSet-ModelDir\n"
                  "$env:OLLAMA_MODELS\n$env:HF_HOME\n$UserEnv -join ';'\n$OllamaModelsChanged")

    ollama, hf_home, user_env, changed = out.strip().splitlines()[-4:]
    assert ollama == str(models / "ollama") and hf_home == str(models / "huggingface")
    assert user_env == f"OLLAMA_MODELS={models / 'ollama'};HF_HOME={models / 'huggingface'}"
    assert changed == "True"
    assert (models / "ollama").is_dir() and (models / "huggingface").is_dir()


def test_set_model_dir_rejects_quote(tmp_path):
    out = _source(tmp_path, FAKE_USER_ENV + "$ModelDir = 'D:\\a\"b'\n"
                  'try { Set-ModelDir } catch { "GAGAL: $KnownFailure" }\n$UserEnv.Count')
    assert "GAGAL: Folder model tidak boleh berisi tanda kutip" in out
    assert out.strip().splitlines()[-1] == "0"


@pytest.mark.parametrize("header, expected", [
    ("| NVIDIA-SMI 560.94     Driver Version: 560.94     CUDA Version: 12.6     |", "12.6"),
    ("| NVIDIA-SMI 621.01     KMD Version: 621.01     CUDA UMD Version: 13.5     |", "13.5"),
    ("NVIDIA-SMI has failed", ""),
])
def test_driver_cuda_version(tmp_path, header, expected):
    out = _source(tmp_path, f"$v = Get-DriverCudaVersion '{header}'; if ($v) {{ '{{0}}.{{1}}' -f $v.Major, $v.Minor }}")
    assert out.strip() == expected


@pytest.mark.parametrize("output, locked", [
    # Potongan nyata logs\install-*.log: rename di cache uv ditolak saat antivirus memindai
    ("failed to rename file from\n  D:\\x\\.tools\\uv-cache\\.tmpiTQ7ad to\n  D:\\x\\archive-v0\\Gj:\n"
     "  Access is denied. (os error 5)", True),
    ("The process cannot access the file because it is being used by another process. (os error 32)", True),
    ("error: command 'cl.exe' failed: None\nhint: This usually indicates a problem with the package", False),
])
def test_file_lock_error(tmp_path, output, locked):
    out = _source(tmp_path, f"Test-FileLockError '{_q(output)}'")
    assert out.strip() == str(locked)
