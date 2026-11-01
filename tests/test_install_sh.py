"""install.sh: deteksi distro, opsi untuk MikuVision Setup, dan baris progres (tanpa memasang apa pun)."""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
INSTALL_SH = ROOT / "install.sh"
ALL_PACKAGES = "git curl libportaudio2 xdotool wmctrl playerctl xclip build-essential"

pytestmark = pytest.mark.skipif(sys.platform == "win32" or shutil.which("bash") is None,
                                reason="installer Linux, butuh bash")


# Log, model RVC, dan environment.d ke folder sementara: ROOT tetap folder repo (config.py dibaca dari sana)
ISOLATE = 'LOG_DIR="$PWD/logs"; LOG_FILE="$LOG_DIR/install.log"; mkdir -p "$LOG_DIR"; RVC_DIR="$PWD/models/rvc"\n'


def _bash(tmp_path, script, path_prefix=None, flags=""):
    """Jalankan `script` setelah install.sh di-source dengan `flags` (main tidak ikut jalan)."""
    env = dict(os.environ, INSTALL_SH=str(INSTALL_SH), XDG_CONFIG_HOME=str(tmp_path / "config"))
    env.pop("HF_HOME", None)
    env.pop("OLLAMA_MODELS", None)
    if path_prefix:
        env["PATH"] = f"{path_prefix}{os.pathsep}{env['PATH']}"
    # install.sh mem-parse "$@" saat di-source, jadi flags ikut sebagai argumen posisi
    return subprocess.run(["bash", "-c", f'source "$INSTALL_SH" {flags}\n' + ISOLATE + script],
                          cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60)


def _events(stdout):
    return [json.loads(line[len("##MIKU "):]) for line in stdout.splitlines() if line.startswith("##MIKU ")]


def _os_release(tmp_path, text):
    path = tmp_path / "os-release"
    path.write_text(text)
    return path


def test_install_sh_parses():
    assert subprocess.run(["bash", "-n", str(INSTALL_SH)]).returncode == 0


def test_sourcing_does_not_run_the_installer(tmp_path):
    result = _bash(tmp_path, "type pkg_manager >/dev/null && echo ok")
    # main akan mencetak "MikuVision installer - log: ..." lebih dulu
    assert result.stdout.strip() == "ok", result.stdout + result.stderr
    assert not list((tmp_path / "logs").iterdir())


@pytest.mark.parametrize("os_release, expected", [
    ('ID=ubuntu\nID_LIKE=debian\n', "apt"),
    ('ID=linuxmint\nID_LIKE="ubuntu debian"\n', "apt"),
    ('ID=pop\nID_LIKE="ubuntu debian"\n', "apt"),
    ('ID=debian\n', "apt"),
    ('ID=fedora\n', "dnf"),
    ('ID="rocky"\nID_LIKE="rhel centos fedora"\n', "dnf"),
    ('ID=arch\n', "pacman"),
    ('ID=manjaro\nID_LIKE=arch\n', "pacman"),
    ('ID=endeavouros\nID_LIKE=arch\n', "pacman"),
    ('ID="opensuse-tumbleweed"\nID_LIKE="opensuse suse"\n', "zypper"),
    ('ID="opensuse-leap"\nID_LIKE="suse opensuse"\n', "zypper"),
])
def test_pkg_manager_from_os_release(tmp_path, os_release, expected):
    path = _os_release(tmp_path, os_release)
    result = _bash(tmp_path, f'pkg_manager "{path}"')
    assert result.stdout.strip() == expected, result.stderr


def test_unknown_distro_falls_back_to_installed_command(tmp_path):
    path = _os_release(tmp_path, "ID=gentoo\n")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "zypper").write_text("#!/bin/sh\nexit 0\n")
    (bin_dir / "zypper").chmod(0o755)

    assert _bash(tmp_path, f'PATH="{bin_dir}" pkg_manager "{path}"').stdout.strip() == "zypper"
    assert _bash(tmp_path, f'PATH="{tmp_path}/none" pkg_manager "{path}"').stdout.strip() == ""


@pytest.mark.parametrize("pm, expected", [
    ("apt", "git curl libportaudio2 xdotool wmctrl playerctl xclip build-essential"),
    ("dnf", "git curl portaudio xdotool wmctrl playerctl xclip gcc-c++ make"),
    ("pacman", "git curl portaudio xdotool wmctrl playerctl xclip base-devel"),
    ("zypper", "git curl libportaudio2 xdotool wmctrl playerctl xclip gcc-c++ make"),
    ("", ALL_PACKAGES),  # tidak dikenal: nama Debian apa adanya
])
def test_pkg_names(tmp_path, pm, expected):
    result = _bash(tmp_path, f'pkg_names "{pm}" {ALL_PACKAGES} | tr "\\n" " "')
    assert result.stdout.split() == expected.split(), result.stderr


@pytest.mark.parametrize("pm, expected", [
    ("apt", "sudo apt-get install -y"),
    ("dnf", "sudo dnf install -y"),
    ("pacman", "sudo pacman -S --needed --noconfirm"),
    ("zypper", "sudo zypper --non-interactive install"),
    ("", ""),
])
def test_pkg_install_cmd(tmp_path, pm, expected):
    assert _bash(tmp_path, f'pkg_install_cmd "{pm}"').stdout.strip() == expected


def _fake_bin(tmp_path, *names):
    """Folder berisi `sudo` palsu (mencatat argumennya) dan package manager palsu."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("sudo", *names):
        (bin_dir / name).write_text('#!/bin/sh\necho "$@" >> "$FAKE_LOG"\n')
        (bin_dir / name).chmod(0o755)
    return bin_dir


CHECK_SYSTEM = '''
export FAKE_LOG="$PWD/sudo.log"
have_lib() { return 1; }          # PortAudio dianggap belum ada
pkg_manager() { echo "%s"; }
YES=1
check_system
'''


def test_check_system_installs_with_mapped_names(tmp_path):
    bin_dir = _fake_bin(tmp_path, "pacman")
    result = _bash(tmp_path, CHECK_SYSTEM % "pacman", path_prefix=bin_dir)

    commands = (tmp_path / "sudo.log").read_text().splitlines()
    assert len(commands) == 1, result.stdout + result.stderr
    argv = commands[0].split()
    assert argv[:4] == ["pacman", "-S", "--needed", "--noconfirm"]
    assert "portaudio" in argv and "libportaudio2" not in argv
    assert "Package manager: pacman" in result.stdout
    assert "Paket wajib belum ada: portaudio" in result.stdout


def test_check_system_without_known_manager_stops_with_package_names(tmp_path):
    bin_dir = _fake_bin(tmp_path)
    result = _bash(tmp_path, CHECK_SYSTEM % "", path_prefix=bin_dir)

    assert result.returncode == 1
    assert "Package manager tidak dikenali" in result.stdout
    assert "Paket wajib belum terpasang: " in result.stdout and "libportaudio2" in result.stdout
    assert not (tmp_path / "sudo.log").exists()


@pytest.mark.parametrize("pm, expected", [
    ("apt", "pkexec apt-get install -y"),
    ("pacman", "pkexec pacman -S --needed --noconfirm"),
])
def test_pkg_install_cmd_uses_sudo_cmd(tmp_path, pm, expected):
    assert _bash(tmp_path, f'pkg_install_cmd "{pm}"', flags="--sudo-cmd pkexec").stdout.strip() == expected


# ───────────────────────── --progress (MikuVision Setup, docs/PLAN_INSTALLER.md fase IL1) ─────────────────────────

def test_self_check_emits_progress_json(tmp_path):
    result = subprocess.run(["bash", str(INSTALL_SH), "--self-check"], capture_output=True, text=True, timeout=60,
                            env=dict(os.environ, TMPDIR=str(tmp_path)))
    assert result.returncode == 0, result.stdout + result.stderr

    events = _events(result.stdout)
    assert events == [
        {"event": "step", "index": 1, "total": 1, "title": "Self-check ミク"},
        {"event": "warn", "message": "Peringatan contoh"},
        {"event": "done", "ok": True},
    ]
    # Log biasa tetap tercetak di samping baris mesin; log self-check di TMPDIR, bukan di repo
    assert "[WARN] Peringatan contoh" in result.stdout
    assert list((tmp_path / "mikuvision-selfcheck").glob("install-*.log"))


def test_progress_lines_only_with_progress_flag(tmp_path):
    body = 'step "Contoh"\nlog WARN \'awas "kutip" \\ miring\'\nNO_EVENT=1 log ERROR "jejak"\nlog INFO "biasa"'
    assert _events(_bash(tmp_path, body).stdout) == []

    events = _events(_bash(tmp_path, "STEP_TOTAL=4\n" + body, flags="--progress").stdout)
    assert events == [
        {"event": "step", "index": 1, "total": 4, "title": "Contoh"},
        {"event": "warn", "message": 'awas "kutip" \\ miring'},
    ]


def test_die_reports_the_cause_then_done_and_exits_1(tmp_path):
    result = _bash(tmp_path, 'die "Contoh gagal"', flags="--progress")

    assert result.returncode == 1
    assert _events(result.stdout) == [{"event": "error", "message": "Contoh gagal"},
                                      {"event": "done", "ok": False}]
    assert "Instalasi berhenti" in result.stdout


def test_unexpected_error_exits_2(tmp_path):
    # Variabel tak terdefinisi di bawah set -u menghentikan bash tanpa lewat die
    result = _bash(tmp_path, 'trap on_exit EXIT\necho "$variabel_tidak_ada"', flags="--progress")

    assert result.returncode == 2
    events = _events(result.stdout)
    assert events[0]["event"] == "error" and "Error tak terduga" in events[0]["message"]
    assert events[-1] == {"event": "done", "ok": False}


def test_success_exit_code_is_0_after_trap(tmp_path):
    result = _bash(tmp_path, "trap on_exit EXIT\nFINISHED=1\nexit 0", flags="--progress")
    assert result.returncode == 0 and _events(result.stdout) == []


DEFAULT_STEPS = ["check_system", "install_uv", "install_python_env", "install_python_packages", "install_unidic",
                 "check_imports", "install_ollama_model", "show_rvc_status", "create_launcher", "run_self_test"]
ALL_STEPS = ["check_system", "set_model_dir", "copy_rvc_model", "install_uv", "install_python_env",
             "install_python_packages", "install_unidic", "check_imports", "install_ollama_model",
             "install_vision_model", "show_rvc_status", "create_launcher", "run_self_test"]


@pytest.mark.parametrize("flags, expected", [
    ("", DEFAULT_STEPS),
    ("--model-dir /m --rvc-model a.pth --rvc-index a.index --with-vision --menu-entry", ALL_STEPS),
    ("--skip-ollama --with-vision", [s for s in DEFAULT_STEPS if s not in ("install_ollama_model", "run_self_test")]),
    ("--skip-test", DEFAULT_STEPS[:-1]),
    ("--skip-shortcut", [s for s in DEFAULT_STEPS if s != "create_launcher"]),
    ("--skip-shortcut --menu-entry", DEFAULT_STEPS),
])
def test_install_steps(tmp_path, flags, expected):
    assert _bash(tmp_path, "install_steps", flags=flags).stdout.split() == expected


def test_every_step_function_calls_step_once(tmp_path):
    # Total di baris "step" dihitung dari install_steps; satu step per langkah, fungsi lain tidak memanggilnya
    script = ('for f in $(compgen -A function); do\n'
              '  n=$(declare -f "$f" | sed -n "2,\\$p" | grep -cE "^[[:space:]]*step ")\n'
              '  echo "$f=$n"\n'
              'done')
    counts = dict(line.split("=") for line in _bash(tmp_path, script).stdout.split())
    assert {name: counts.get(name) for name in ALL_STEPS} == {name: "1" for name in ALL_STEPS}
    # main memanggil step hanya untuk --self-check, sama seperti install.ps1
    assert {name for name, n in counts.items() if n != "0"} == set(ALL_STEPS) | {"main"}


def test_rvc_index_name_matches_config():
    config = (ROOT / "config.py").read_text(encoding="utf-8")
    from_config = re.search(r'index_path=str\(RVC_MODELS_DIR / .*"([^"]+\.index)"\)', config).group(1)
    from_installer = re.search(r'^RVC_INDEX_NAME="([^"]+)"', INSTALL_SH.read_text(), re.M).group(1)
    assert from_installer == from_config


@pytest.mark.parametrize("name", ["OLLAMA_MODEL", "VISION_MODEL"])
def test_config_value(tmp_path, name):
    config = (ROOT / "config.py").read_text(encoding="utf-8")
    expected = re.search(rf'^{name} = "([^"]+)"', config, re.M).group(1)
    assert _bash(tmp_path, f"config_value {name}").stdout.strip() == expected


def _rvc_files(tmp_path, model_name="miku.pth", index_name="trained_v2.index"):
    source = tmp_path / "unduhan"
    source.mkdir()
    (source / model_name).write_bytes(b"bobot")
    (source / index_name).write_bytes(b"index")
    return source / model_name, source / index_name


def test_copy_rvc_model(tmp_path):
    model, index = _rvc_files(tmp_path, "Miku.PTH")
    result = _bash(tmp_path, "copy_rvc_model\nrvc_model_present && echo ADA",
                   flags=f"--rvc-model '{model}' --rvc-index '{index}'")

    assert result.stdout.strip().splitlines()[-1] == "ADA", result.stdout + result.stderr
    rvc_dir = tmp_path / "models" / "rvc"
    assert (rvc_dir / "weights" / "miku_default_rvc.pth").read_bytes() == b"bobot"
    index_name = "added_IVF4457_Flat_nprobe_1_miku_default_rvc_v2.index"
    assert (rvc_dir / "logs" / "miku_default_rvc" / index_name).read_bytes() == b"index"

    # Dijalankan lagi dengan file yang sudah di tempatnya
    again = _bash(tmp_path, "copy_rvc_model", flags=f"--rvc-model '{rvc_dir / 'weights' / 'miku_default_rvc.pth'}' "
                                                    f"--rvc-index '{index}'")
    assert "Sudah di tempatnya" in again.stdout and again.returncode == 0


@pytest.mark.parametrize("model, index, message", [
    ("miku.pth", "", "harus dipakai bersama"),
    ("miku.zip", "trained.index", "harus berakhiran .pth"),
    ("hilang.pth", "trained.index", "tidak ditemukan"),
])
def test_copy_rvc_model_rejects(tmp_path, model, index, message):
    _rvc_files(tmp_path, "miku.pth", "trained.index")
    (tmp_path / "unduhan" / "miku.zip").write_bytes(b"zip")
    flags = f"--rvc-model '{tmp_path / 'unduhan' / model}'" + (f" --rvc-index '{tmp_path / 'unduhan' / index}'"
                                                              if index else "")
    result = _bash(tmp_path, "copy_rvc_model", flags=flags)

    assert result.returncode == 1 and message in result.stdout
    assert not (tmp_path / "models" / "rvc" / "weights").exists()


def _env_file(tmp_path):
    return tmp_path / "config" / "environment.d" / "60-mikuvision.conf"


def test_set_model_dir(tmp_path):
    models = tmp_path / "Miku models"
    result = _bash(tmp_path, 'set_model_dir\necho "HF=$HF_HOME"', flags=f"--model-dir '{models}'")

    assert f"HF={models / 'huggingface'}" in result.stdout, result.stdout + result.stderr
    assert (models / "huggingface").is_dir()
    # OLLAMA_MODELS baru diatur di install_ollama_model (tergantung layanan sistem atau bukan)
    assert _env_file(tmp_path).read_text() == f"HF_HOME={models / 'huggingface'}\n"

    moved = tmp_path / "lain"
    again = _bash(tmp_path, "set_model_dir", flags=f"--model-dir '{moved}'")
    assert f"HF_HOME sebelumnya {models / 'huggingface'}" in again.stdout
    assert _env_file(tmp_path).read_text() == f"HF_HOME={moved / 'huggingface'}\n"


def test_set_model_dir_rejects_quote(tmp_path):
    result = _bash(tmp_path, "set_model_dir", flags="--model-dir '/a\"b'")
    assert result.returncode == 1 and "tidak boleh berisi tanda kutip" in result.stdout
    assert not _env_file(tmp_path).exists()


def test_load_model_env_fills_only_unset_variables(tmp_path):
    _env_file(tmp_path).parent.mkdir(parents=True)
    _env_file(tmp_path).write_text("HF_HOME=/data/hf\nOLLAMA_MODELS=/data/ollama\nLAIN=x\n")
    script = 'load_model_env\necho "$HF_HOME|$OLLAMA_MODELS|${LAIN:-}"'

    assert _bash(tmp_path, script).stdout.strip() == "/data/hf|/data/ollama|"
    assert _bash(tmp_path, "export HF_HOME=/punya/user\n" + script).stdout.strip() == "/punya/user|/data/ollama|"


# install_ollama_model tanpa jaringan dan tanpa Ollama sungguhan: fungsi yang menyentuh sistem diganti
OLLAMA_STUBS = '''
config_value() { echo "qwen3:4b-instruct"; }
ollama_pull() { echo "PULL $1"; }
wait_ollama() { :; }
stop_user_ollama() { echo "STOP"; }
ollama_service_models_dir() { echo /usr/share/ollama/.ollama/models; }
'''


def _fake_ollama(tmp_path):
    bin_dir = tmp_path / "ollama-bin"
    bin_dir.mkdir()
    (bin_dir / "ollama").write_text('#!/bin/sh\necho "ollama $* OLLAMA_MODELS=$OLLAMA_MODELS" >> "$FAKE_LOG"\n')
    (bin_dir / "ollama").chmod(0o755)
    return bin_dir


def test_model_dir_keeps_models_of_the_ollama_system_service(tmp_path):
    script = (f'export FAKE_LOG="$PWD/ollama.log"\n{OLLAMA_STUBS}'
              'ollama_system_service() { return 0; }\nollama_up() { return 0; }\n'
              'MODEL_DIR="$PWD/models-baru"\ninstall_ollama_model')
    result = _bash(tmp_path, script, path_prefix=_fake_ollama(tmp_path), flags="--progress")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "modelnya tetap di /usr/share/ollama/.ollama/models" in result.stdout
    assert "PULL qwen3:4b-instruct" in result.stdout
    assert not _env_file(tmp_path).exists() and not (tmp_path / "models-baru" / "ollama").exists()


def test_model_dir_moves_models_of_a_user_run_ollama(tmp_path):
    # Ollama milik user sedang jalan dengan lokasi lama: dimatikan, lalu dinyalakan dengan OLLAMA_MODELS baru
    script = (f'export FAKE_LOG="$PWD/ollama.log"\n{OLLAMA_STUBS}'
              'ollama_system_service() { return 1; }\n'
              'UP=1\nollama_up() { return $((1 - UP)); }\nstop_user_ollama() { echo STOP; UP=0; }\n'
              'MODEL_DIR="$PWD/models-baru"\ninstall_ollama_model\nwait')
    result = _bash(tmp_path, script, path_prefix=_fake_ollama(tmp_path))

    ollama_dir = tmp_path / "models-baru" / "ollama"
    assert result.returncode == 0, result.stdout + result.stderr
    assert "STOP" in result.stdout and ollama_dir.is_dir()
    assert _env_file(tmp_path).read_text() == f"OLLAMA_MODELS={ollama_dir}\n"
    assert f"ollama serve OLLAMA_MODELS={ollama_dir}" in (tmp_path / "ollama.log").read_text()


def test_launcher_menu_only_with_skip_shortcut_and_menu_entry(tmp_path):
    home = tmp_path / "home"
    (home / "Desktop").mkdir(parents=True)
    script = (f'export HOME="{home}" XDG_DATA_HOME="{home}/.local/share"\nVENV_PY=/bin/false\nTOOLS_DIR="$PWD/tools"\n'
              "create_launcher")
    menu = home / ".local" / "share" / "applications" / "mikuvision.desktop"

    _bash(tmp_path, script, flags="--skip-shortcut --menu-entry")
    assert menu.is_file() and f'Exec=/bin/bash "{ROOT / "run.sh"}"' in menu.read_text()
    assert not (home / "Desktop" / "MikuVision.desktop").exists()

    _bash(tmp_path, script)
    assert (home / "Desktop" / "MikuVision.desktop").is_file()


def test_run_sh_exports_the_model_folders(tmp_path):
    # Salinan run.sh di folder sementara: run.sh pindah ke foldernya sendiri dan menulis data/logs/gui.log di sana
    app = tmp_path / "app"
    (app / ".venv" / "bin").mkdir(parents=True)
    shutil.copy(ROOT / "run.sh", app / "run.sh")
    (app / ".venv" / "bin" / "python").write_text('#!/bin/sh\necho "HF=$HF_HOME OLLAMA=$OLLAMA_MODELS ARGS=$*"\n')
    (app / ".venv" / "bin" / "python").chmod(0o755)
    _env_file(tmp_path).parent.mkdir(parents=True)
    _env_file(tmp_path).write_text("HF_HOME=/data/hf\nOLLAMA_MODELS=/data/ollama\n")
    env = {k: v for k, v in os.environ.items() if k not in ("HF_HOME", "OLLAMA_MODELS", "MIKU_VENV")}
    env["XDG_CONFIG_HOME"] = str(tmp_path / "config")

    subprocess.run(["bash", str(app / "run.sh")], env=env, capture_output=True, timeout=30)

    assert "HF=/data/hf OLLAMA=/data/ollama ARGS=gui.py" in (app / "data" / "logs" / "gui.log").read_text()
