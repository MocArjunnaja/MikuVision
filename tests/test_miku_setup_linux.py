"""MikuVision Setup di Linux (PLAN_INSTALLER IL2): cek sistem, argumen install.sh, catatan instalasi, Hapus.

Fungsi murni dites di semua OS; yang memakai path ("/home/...") dan proses Linux dilewati di Windows.
"""

import json
import os
import re
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from miku_setup import checks, components, launch, maintenance, registry, runner
from miku_setup.checks import FAIL, OK, WARN
from miku_setup.components import GB, MARGIN_GB, Selection
from miku_setup.maintenance import RemovalPlan, app_shortcuts, remove_installation
from miku_setup.registry import InstalledApp

ROOT = Path(__file__).resolve().parent.parent

linux_only = pytest.mark.skipif(sys.platform == "win32", reason="path, proses, dan file .desktop Linux")

MINT = 'NAME="Linux Mint"\nID=linuxmint\nID_LIKE="ubuntu debian"\nPRETTY_NAME="Linux Mint 22.3"\n'


# ───────────────────────── cek sistem ─────────────────────────

@pytest.mark.parametrize("text, manager", [
    (MINT, "apt"),
    ('ID=fedora\nPRETTY_NAME="Fedora Linux 42 (Workstation Edition)"\n', "dnf"),
    ("ID=manjaro\nID_LIKE=arch\n", "pacman"),
    ("ID=arch\n", "pacman"),
    ('ID="opensuse-tumbleweed"\nID_LIKE="opensuse suse"\n', "zypper"),
])
def test_package_manager_from_os_release(text, manager):
    assert checks.package_manager(checks.parse_os_release(text), which=lambda name: None) == manager


def test_unknown_distro_falls_back_to_the_command_that_exists():
    release = checks.parse_os_release("ID=nixos\n")
    assert checks.package_manager(release, which=lambda name: "/usr/bin/dnf" if name == "dnf" else None) == "dnf"
    assert checks.package_manager(release, which=lambda name: None) == ""


@pytest.mark.parametrize("machine, manager, status, text", [
    ("x86_64", "apt", OK, "Linux Mint 22.3 64-bit (apt)"),
    ("aarch64", "apt", FAIL, "x86_64"),
    ("x86_64", "", WARN, "package manager tidak dikenali"),
])
def test_check_linux(machine, manager, status, text):
    result = checks.check_linux(machine, checks.parse_os_release(MINT), manager)
    assert result.key == "linux" and result.status == status and text in result.message


@pytest.mark.parametrize("session, status, text", [
    ("x11", OK, "X11"),
    ("wayland", WARN, "butuh X11"),
    ("", WARN, "Tidak diketahui"),
])
def test_check_session(session, status, text):
    result = checks.check_session(session)
    assert result.status == status and text in result.message


PACTL = """\
Source #48
\tState: SUSPENDED
\tName: alsa_output.pci-0000_00_1f.3.analog-stereo.monitor
\tDescription: Monitor of Built-in Audio Analog Stereo
\tProperties:
\t\tdevice.description = "Monitor of Built-in Audio Analog Stereo"
Source #49
\tName: alsa_input.pci-0000_00_1f.3.analog-stereo
\tDescription: Built-in Audio Analog Stereo
"""


def test_parse_pactl_sources_skips_speaker_monitors():
    assert checks.parse_pactl_sources(PACTL) == ["Built-in Audio Analog Stereo"]
    assert checks.parse_pactl_sources(PACTL.split("Source #49")[0]) == []


def test_parse_arecord():
    output = ("**** List of CAPTURE Hardware Devices ****\n"
              "card 1: PCH [HDA Intel PCH], device 0: ALC257 Analog [ALC257 Analog]\n"
              "  Subdevices: 1/1\n")
    assert checks.parse_arecord(output) == ["HDA Intel PCH"]
    assert checks.parse_arecord("") == []


def test_root_needs_match_install_sh():
    present = {"git", "curl", "xdotool", "wmctrl", "playerctl", "xclip", "g++"}
    which = lambda name: f"/usr/bin/{name}" if name in present else None  # noqa: E731
    assert checks.root_needs(rvc=True, ollama_installed=True, which=which, has_lib=lambda name: True) == []
    present -= {"git", "xclip", "g++"}
    assert checks.root_needs(rvc=False, ollama_installed=False, which=which, has_lib=lambda name: False) == \
        ["git", "PortAudio", "xclip", "Ollama"]
    assert "g++" in checks.root_needs(rvc=True, ollama_installed=True, which=which, has_lib=lambda name: True)


def test_install_sh_installs_the_same_tools():
    install_sh = (ROOT / "install.sh").read_text(encoding="utf-8")
    for tool in checks.REQUIRED_TOOLS:
        assert f"command -v {tool} >/dev/null || required+=({tool})" in install_sh
    assert f'for tool in {" ".join(checks.DESKTOP_TOOLS)}; do' in install_sh
    assert f"have_lib {checks.PORTAUDIO_LIB}" in install_sh


@pytest.mark.parametrize("needs, pkexec, status, text", [
    ([], None, OK, "Tidak perlu"),
    (["git", "Ollama"], "/usr/bin/pkexec", OK, "git, Ollama"),
    (["Ollama"], None, FAIL, "pkexec tidak ada"),
])
def test_check_root(needs, pkexec, status, text):
    result = checks.check_root(needs, pkexec)
    assert result.key == "root" and result.status == status and text in result.message


MOUNTS = """\
/dev/nvme0n1p2 / ext4 rw,relatime 0 0
tmpfs /run tmpfs rw 0 0
/dev/nvme0n1p5 /home ext4 rw 0 0
/dev/sda1 /media/arjun/Data\\040Kuliah fuseblk rw,user_id=0 0 0
/dev/sdb1 /home/arjun/usb vfat rw 0 0
/dev/sdc1 /home/arjun/usb ntfs3 rw 0 0
"""


@linux_only
@pytest.mark.parametrize("path, mount", [
    ("/usr/share/ollama/.ollama/models", ("/", "ext4")),
    ("/home/arjun/.local/share/mikuvision/app", ("/home", "ext4")),
    ("/homework", ("/", "ext4")),
    ("/media/arjun/Data Kuliah/MikuVision", ("/media/arjun/Data Kuliah", "fuseblk")),
    ("/home/arjun/usb/MikuVision", ("/home/arjun/usb", "ntfs3")),  # mount yang ditumpuk: yang terakhir
])
def test_mount_of_picks_the_deepest_mount(path, mount):
    assert checks.mount_of(Path(path), checks.parse_mounts(MOUNTS)) == mount


def test_ollama_service_models_dir():
    home_of = {"ollama": "/usr/share/ollama"}.get
    assert checks.service_models_dir({"LoadState": "not-found"}, home_of) is None
    show = checks.parse_systemctl_show("Environment=PATH=/usr/bin\nUser=ollama\nLoadState=loaded\n")
    assert checks.service_models_dir(show, home_of) == Path("/usr/share/ollama/.ollama/models")
    show["Environment"] = 'PATH=/usr/bin "OLLAMA_MODELS=/data/model ollama"'
    assert checks.service_models_dir(show, home_of) == Path("/data/model ollama")
    show = {"LoadState": "loaded", "User": "lain"}
    assert checks.service_models_dir(show, lambda user: None) == Path("/usr/share/ollama/.ollama/models")


# ───────────────────────── komponen dan argumen install.sh ─────────────────────────

def test_default_install_dir_on_linux():
    assert components.default_install_dir({"HOME": "/home/a"}, platform="linux") == \
        Path("/home/a/.local/share/mikuvision/app")
    assert components.default_install_dir({"XDG_DATA_HOME": "/data"}, platform="linux") == \
        Path("/data/mikuvision/app")


@linux_only
def test_install_args_on_linux():
    assert components.install_args(Selection(Path("/a")), platform="linux") == \
        ["--yes", "--progress", "--menu-entry", "--skip-shortcut", "--sudo-cmd", "pkexec"]
    selection = Selection(Path("/a"), model_dir=Path("/m/Miku models"), components={"core", "brain", "vision", "rvc"},
                          rvc_model="/x/a.pth", rvc_index="/x/a.index")
    assert components.install_args(selection, platform="linux") == [
        "--yes", "--progress", "--menu-entry", "--skip-shortcut", "--sudo-cmd", "pkexec",
        "--model-dir", "/m/Miku models", "--with-vision", "--rvc-model", "/x/a.pth", "--rvc-index", "/x/a.index"]


def test_install_args_use_options_that_install_sh_has():
    install_sh = (ROOT / "install.sh").read_text(encoding="utf-8")
    selection = Selection(Path("/a"), model_dir=Path("/m"), components={"core", "brain", "vision", "rvc"},
                          rvc_model="x.pth", rvc_index="x.index")
    for option in (a for a in components.install_args(selection, platform="linux") if a.startswith("--")):
        assert re.search(rf"^\s+{re.escape(option)}(\|-y)?\)", install_sh, re.M), option


@linux_only
def test_install_command_on_linux_runs_install_sh_with_bash():
    assert runner.install_command(Path("/a b"), ["--yes"], platform="linux") == ["bash", "/a b/install.sh", "--yes"]


@linux_only
@pytest.mark.parametrize("install_dir, model_dir, problem", [
    ("/home/a/Miku$Vision", None, "tidak boleh berisi karakter"),
    ("/home/a/100%", None, "tidak boleh berisi karakter"),
    ("/home/a/MikuVision", "/m/a\\b", "Folder model tidak boleh"),
    ("MikuVision", None, "harus path lengkap"),
    ("/opt/MikuVision", None, "di dalam folder home"),
    ("/media/a/Data/MikuVision", None, "partisi Windows"),
])
def test_validate_folders_on_linux(install_dir, model_dir, problem):
    selection = Selection(Path(install_dir), model_dir=Path(model_dir) if model_dir else None)
    writable = lambda path: not str(path).startswith("/opt")  # noqa: E731
    filesystem = lambda path: "fuseblk" if str(path).startswith("/media") else "ext4"  # noqa: E731
    assert problem in components.validate_selection(selection, writable, platform="linux", filesystem=filesystem)


@linux_only
def test_models_may_live_on_a_windows_partition():
    selection = Selection(Path("/home/a/MikuVision"), model_dir=Path("/media/a/Data/models"))
    filesystem = lambda path: "fuseblk" if str(path).startswith("/media") else "ext4"  # noqa: E731
    assert components.validate_selection(selection, lambda p: True, platform="linux", filesystem=filesystem) is None


@linux_only
def test_ollama_system_service_keeps_its_models(monkeypatch):
    service = Path("/usr/share/ollama/.ollama/models")
    monkeypatch.setattr(checks, "ollama_service_dir", lambda: service)
    selection = Selection(Path("/home/a/MikuVision"), model_dir=Path("/media/a/models"))
    assert components.model_locations(selection, {"HOME": "/home/a"}) == (service, Path("/media/a/models/huggingface"))
    monkeypatch.setattr(checks, "ollama_service_dir", lambda: None)
    assert components.model_locations(selection, {"HOME": "/home/a"})[0] == Path("/media/a/models/ollama")


@linux_only
def test_space_per_mount_on_linux(monkeypatch):
    monkeypatch.setattr(checks, "ollama_service_dir", lambda: Path("/usr/share/ollama/.ollama/models"))
    monkeypatch.setattr(components, "drive_of", lambda path: "/home" if str(path).startswith("/home") else "/")
    monkeypatch.setattr(components, "model_present", lambda models_dir, model: False)
    selection = Selection(Path("/home/a/.local/share/mikuvision/app"), components={"core", "brain", "vision"})
    needs = components.space_needed(selection, gpu=True, ollama_installed=False, environ={"HOME": "/home/a"})
    assert {drive: round(size / GB, 1) for drive, size in needs.items()} == {
        "/home": round(components.CORE_APP_GB + components.SPEECH_MODELS_GB + MARGIN_GB, 1),
        # Ollama di /usr/local, model layanan sistem di /usr/share/ollama
        "/": round(components.OLLAMA_APP_GB + components.LLM_GB + components.VISION_GB + MARGIN_GB, 1),
    }


@linux_only
def test_model_folders_from_the_environment_d_file(tmp_path):
    env_file = tmp_path / "environment.d" / "60-mikuvision.conf"
    env_file.parent.mkdir()
    env_file.write_text("HF_HOME=/data/hf\nOLLAMA_MODELS=/data/ollama\n")
    environ = {"HOME": "/home/a", "XDG_CONFIG_HOME": str(tmp_path)}
    assert checks.huggingface_dir(environ) == Path("/data/hf")
    assert checks.ollama_models_dir(environ) == Path("/data/ollama")
    assert checks.huggingface_dir(dict(environ, HF_HOME="/env/hf")) == Path("/env/hf")
    env_file.unlink()
    assert checks.huggingface_dir(environ) == Path("/home/a/.cache/huggingface")


@linux_only
def test_unreadable_service_folder_asks_the_running_ollama(tmp_path, monkeypatch):
    monkeypatch.setattr(checks, "_denied", lambda path: True)
    monkeypatch.setattr(checks, "ollama_api_models", lambda: {"qwen3:4b-instruct", "llama3:latest"})
    assert checks.model_present(tmp_path, "qwen3:4b-instruct")
    assert checks.model_present(tmp_path, "llama3")
    assert not checks.model_present(tmp_path, "qwen3-vl:4b-instruct")
    monkeypatch.setattr(checks, "ollama_api_models", lambda: None)  # Ollama tidak jalan: dianggap belum ada
    assert not checks.model_present(tmp_path, "qwen3:4b-instruct")


@linux_only
def test_drive_of_is_a_mount_point(tmp_path):
    mount = checks.drive_of(tmp_path / "belum" / "ada")
    assert str(tmp_path.resolve()).startswith(mount.rstrip("/") + "/")
    assert os.path.ismount(mount)
    assert checks.filesystem_of(tmp_path)


# ───────────────────────── catatan instalasi dan menu ─────────────────────────

@pytest.fixture
def home(tmp_path, monkeypatch):
    """XDG_DATA_HOME, XDG_CONFIG_HOME, dan Desktop di tmp_path; file asli user tidak tersentuh."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "share"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    monkeypatch.setattr(launch, "desktop_dir", lambda: desktop)
    monkeypatch.setattr(maintenance, "desktop_dir", lambda: desktop)
    return tmp_path


def fake_install(root: Path) -> InstalledApp:
    install_dir = root / "share" / "mikuvision" / "app"
    for name in ("install.sh", "run.sh", "gui.py", ".venv/bin/python", ".tools/mikuvision.png", "data/memory.json"):
        path = install_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")
    return InstalledApp(install_dir, "1.7.0", root / "Model Miku", {"core", "brain", "vision"})


@linux_only
def test_install_record_round_trip(home):
    app = fake_install(home)
    registry.write_entry(app, 1234)
    record = json.loads((home / "share" / "mikuvision" / "install.json").read_text())
    assert record["version"] == "1.7.0" and record["size_kb"] == 1234
    assert record["components"] == ["brain", "core", "vision"]
    assert registry.read_installed() == app
    apps = home / "share" / "applications"
    setup = (apps / registry.SETUP_DESKTOP).read_text()
    uninstall = (apps / registry.UNINSTALL_DESKTOP).read_text()
    assert "Name=MikuVision Setup" in setup and "Name=Hapus MikuVision" in uninstall
    assert f"Icon={app.install_dir}/.tools/mikuvision.png" in setup
    assert uninstall.splitlines()[4].endswith(" --uninstall") and str(registry.ENTRY_SCRIPT) in uninstall
    assert registry.delete_entry()
    assert not list(apps.glob("mikuvision*.desktop")) and registry.read_installed() is None
    assert not registry.delete_entry()


@linux_only
def test_record_without_install_sh_is_ignored(home):
    app = fake_install(home)
    registry.write_entry(app, 1)
    (app.install_dir / "install.sh").unlink()
    assert registry.read_installed() is None
    (home / "share" / "mikuvision" / "install.json").write_text("{rusak")
    assert registry.read_installed() is None


@pytest.mark.parametrize("parts, line", [
    (["/opt/MikuVisionSetup", "--uninstall"], "/opt/MikuVisionSetup --uninstall"),
    (["/home/a/Miku Vision/.tools/MikuVisionSetup"], '"/home/a/Miku Vision/.tools/MikuVisionSetup"'),
    (["/a/b$c", "50%"], '"/a/b\\\\$c" 50%%'),
])
def test_desktop_exec_quoting(parts, line):
    assert registry.desktop_exec(parts) == line


@linux_only
def test_shortcuts_of_another_clone_are_kept(home):
    app = fake_install(home)
    apps = home / "share" / "applications"
    apps.mkdir(parents=True)
    menu = apps / "mikuvision.desktop"
    desktop = home / "Desktop" / "MikuVision.desktop"
    for entry, root in ((menu, app.install_dir), (desktop, Path("/media/a/Data Kuliah/MikuVision"))):
        entry.write_text(f'[Desktop Entry]\nName=MikuVision\nExec=/bin/bash "{root}/run.sh"\nPath={root}\n')
    assert maintenance.desktop_target(desktop) == "/media/a/Data Kuliah/MikuVision/run.sh"
    assert app_shortcuts(app.install_dir) == [menu]
    (apps / "lain.desktop").write_text(f'[Desktop Entry]\nExec=/bin/bash "{app.install_dir}/run.sh"\n')
    assert app_shortcuts(app.install_dir) == [menu]  # hanya nama file milik MikuVision


@linux_only
def test_uninstall_on_linux(home):
    app = fake_install(home)
    registry.write_entry(app, 1)
    launch_problem = launch.create_desktop_shortcut(app.install_dir)
    assert launch_problem == f"{home / 'share' / 'applications' / 'mikuvision.desktop'} tidak ditemukan"
    menu = home / "share" / "applications" / "mikuvision.desktop"
    menu.write_text(f'[Desktop Entry]\nExec=/bin/bash "{app.install_dir}/run.sh"\n')
    assert launch.create_desktop_shortcut(app.install_dir) is None
    assert (home / "Desktop" / "MikuVision.desktop").read_text() == menu.read_text()
    other = home / "share" / "applications" / "lain.desktop"
    other.write_text("[Desktop Entry]\n")
    (app.model_dir / "huggingface").mkdir(parents=True)
    env_file = home / "config" / "environment.d" / "60-mikuvision.conf"
    env_file.parent.mkdir(parents=True)
    env_file.write_text(f"HF_HOME={app.model_dir}/huggingface\nOLLAMA_MODELS=/usr/share/ollama/models\n")

    assert remove_installation(app, RemovalPlan(models=True)) == []
    assert sorted(p.name for p in app.install_dir.iterdir()) == ["data"]
    assert not menu.exists() and not (home / "Desktop" / "MikuVision.desktop").exists()
    assert other.exists()  # folder applications dipakai aplikasi lain
    assert not app.model_dir.exists()
    assert env_file.read_text() == "OLLAMA_MODELS=/usr/share/ollama/models\n"
    assert registry.read_installed() is None
    assert not (home / "share" / "applications" / registry.UNINSTALL_DESKTOP).exists()
    assert (home / "share" / "mikuvision").is_dir()  # bisa berisi venv clone git di NTFS


@linux_only
def test_environment_d_file_without_variables_left_is_removed(tmp_path):
    env_file = tmp_path / "60-mikuvision.conf"
    env_file.write_text("HF_HOME=/a\nOLLAMA_MODELS=/b\n")
    maintenance.remove_env_file_vars(env_file, ["HF_HOME", "OLLAMA_MODELS"])
    assert not env_file.exists()
    maintenance.remove_env_file_vars(env_file, ["HF_HOME"])  # file tidak ada: tidak apa-apa


@linux_only
def test_frozen_setup_is_not_counted_as_running(tmp_path, monkeypatch):
    install_dir = tmp_path / "app"
    setup = install_dir / ".tools" / "MikuVisionSetup"

    class Process:
        def __init__(self, pid, name, exe):
            self.info = {"pid": pid, "name": name, "exe": exe}
    # Binary satu file PyInstaller: bootloader dan proses Python memakai exe yang sama
    processes = [Process(os.getppid(), "MikuVisionSetup", str(setup)),
                 Process(10**7, "python3.10", str(install_dir / ".tools" / "python" / "bin" / "python3.10"))]
    psutil = pytest.importorskip("psutil")
    monkeypatch.setattr(psutil, "process_iter", lambda attrs: processes)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(setup))
    assert maintenance.running_processes(install_dir) == ["python3.10"]


# ───────────────────────── menjalankan dan membatalkan ─────────────────────────

@linux_only
def test_launch_runs_run_sh_in_its_own_session(tmp_path):
    (tmp_path / "run.sh").write_text('echo "$$ $(ps -o sid= -p $$)" > started.txt\n')
    assert launch.launch(tmp_path) is None
    deadline = time.time() + 10
    while not (tmp_path / "started.txt").is_file() or not (tmp_path / "started.txt").read_text().strip():
        assert time.time() < deadline, "run.sh tidak jalan"
        time.sleep(0.05)
    pid, sid = (tmp_path / "started.txt").read_text().split()
    assert pid == sid  # pemimpin sesi sendiri: tetap jalan setelah Setup ditutup
    assert launch.launch(tmp_path / "hilang") == f"{tmp_path / 'hilang' / 'run.sh'} tidak ditemukan"


@linux_only
def test_cancel_kills_the_whole_process_group(tmp_path):
    """install.sh menjalankan uv, python, dan ollama pull sebagai anak; Batal ikut menghentikan mereka."""
    script = tmp_path / "install.sh"
    script.write_text(textwrap.dedent("""\
        sleep 60 &
        echo $! > child.txt
        wait
    """))
    process = subprocess.Popen(["bash", str(script)], cwd=tmp_path, start_new_session=True)
    deadline = time.time() + 10
    while not (tmp_path / "child.txt").is_file() or not (tmp_path / "child.txt").read_text().strip():
        assert time.time() < deadline, "skrip tidak mulai"
        time.sleep(0.05)
    child = int((tmp_path / "child.txt").read_text())
    runner.kill_group(process, wait=1)
    process.wait(timeout=10)
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            os.kill(child, 0)
        except ProcessLookupError:
            break
        time.sleep(0.05)
    else:
        pytest.fail("anak proses masih jalan")


# ───────────────────────── entry ─────────────────────────

@linux_only
def test_setup_logs_and_relaunch_on_linux(tmp_path, monkeypatch):
    from miku_setup import main as entry

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert entry.log_dir() == tmp_path / "mikuvision" / "setup"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert entry.relaunch_outside(tmp_path, ["--uninstall"]) is False  # file yang berjalan boleh dihapus
