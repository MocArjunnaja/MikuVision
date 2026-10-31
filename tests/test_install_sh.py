"""install.sh: deteksi package manager dan nama paket per distro (tanpa memasang apa pun)."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

INSTALL_SH = Path(__file__).resolve().parent.parent / "install.sh"
ALL_PACKAGES = "git curl libportaudio2 xdotool wmctrl playerctl xclip build-essential"

pytestmark = pytest.mark.skipif(sys.platform == "win32" or shutil.which("bash") is None,
                                reason="installer Linux, butuh bash")


def _bash(tmp_path, script, path_prefix=None):
    """Jalankan `script` setelah install.sh di-source (main tidak ikut jalan)."""
    env = dict(os.environ, INSTALL_SH=str(INSTALL_SH))
    if path_prefix:
        env["PATH"] = f"{path_prefix}{os.pathsep}{env['PATH']}"
    # Tanpa argumen posisi: install.sh mem-parse "$@" saat di-source
    return subprocess.run(["bash", "-c", 'source "$INSTALL_SH"\n' + script],
                          cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60)


def _os_release(tmp_path, text):
    path = tmp_path / "os-release"
    path.write_text(text)
    return path


def test_install_sh_parses():
    assert subprocess.run(["bash", "-n", str(INSTALL_SH)]).returncode == 0


def test_sourcing_does_not_run_the_installer(tmp_path):
    result = _bash(tmp_path, "type pkg_manager >/dev/null && echo ok")
    assert result.stdout.strip() == "ok", result.stderr
    assert not (tmp_path / "logs").exists()


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
mkdir -p "$LOG_DIR"
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
