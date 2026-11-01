"""MikuVision Setup: cek sistem dari keluaran perintah (tanpa menjalankan perintahnya)."""

import subprocess
import sys
from pathlib import Path

import pytest

from miku_setup import checks
from miku_setup.checks import FAIL, OK, WARN, Gpu


@pytest.mark.parametrize("machine, version, status, text", [
    ("AMD64", "10.0.26300", OK, "Windows 11 64-bit (build 26300)"),
    ("AMD64", "10.0.19045", OK, "Windows 10 64-bit (build 19045)"),
    ("x86", "10.0.19045", FAIL, "32-bit"),
    ("AMD64", "6.3.9600", FAIL, "Windows 10 atau 11"),
    ("ARM64", "10.0.26100", WARN, "ARM64"),
    ("AMD64", "", WARN, "tidak terbaca"),
])
def test_check_windows(machine, version, status, text):
    result = checks.check_windows(machine, version)
    assert result.status == status and text in result.message


NVIDIA_SMI = "NVIDIA GeForce RTX 4050 Laptop GPU, 621.01, 6141 MiB\n"


def test_parse_nvidia_smi():
    assert checks.parse_nvidia_smi(NVIDIA_SMI) == [Gpu("NVIDIA GeForce RTX 4050 Laptop GPU", "621.01", 6141)]
    two = "NVIDIA GeForce GTX 1650, 551.86, 4096 MiB\r\nNVIDIA GeForce RTX 3060, 551.86, 12288 MiB\r\n"
    assert [g.vram_mib for g in checks.parse_nvidia_smi(two)] == [4096, 12288]


@pytest.mark.parametrize("output", ["", "NVIDIA-SMI has failed because it couldn't communicate", "a, b, c"])
def test_parse_nvidia_smi_ignores_other_output(output):
    assert checks.parse_nvidia_smi(output) == []


def test_gpu_with_6_gb_card_has_enough_vram():
    gpu, vram = checks.check_gpu(checks.parse_nvidia_smi(NVIDIA_SMI))
    assert gpu.status == OK and "RTX 4050" in gpu.message
    assert vram.status == OK and vram.message == "6,0 GB"


def test_small_vram_warns_and_the_largest_gpu_counts():
    results = checks.check_gpu([Gpu("Intel", "1", 512), Gpu("GTX 1650", "551.86", 4096)])
    assert results[0].message.startswith("GTX 1650")
    assert results[1].status == WARN and "tidak muat" in results[1].message


@pytest.mark.parametrize("gpus", [None, []])
def test_without_nvidia_gpu_only_warns(gpus):
    results = checks.check_gpu(gpus)
    assert [r.status for r in results] == [WARN] and "CPU" in results[0].message


def test_check_disk():
    ok = checks.check_disk({"C:": 10.8e9, "D:": 3.9e9}, {"C:": 61.2e9, "D:": 100.6e9})
    assert ok.status == OK
    assert ok.message == "C: butuh 10,8 GB, kosong 61,2 GB, D: butuh 3,9 GB, kosong 100,6 GB"
    short = checks.check_disk({"C:": 10.8e9, "D:": 3.9e9}, {"C:": 8e9, "D:": 100e9})
    assert short.status == FAIL and short.message.startswith("Ruang kurang di C:")


def test_check_internet_names_the_blocked_site():
    assert checks.check_internet({"pypi.org": None, "ollama.com": None}).status == OK
    blocked = checks.check_internet({"pypi.org": None, "huggingface.co": "timed out"})
    assert blocked.status == FAIL and "huggingface.co" in blocked.message and "pypi.org" not in blocked.message


@pytest.mark.parametrize("output, names", [
    ("Microphone Array (Realtek(R) Audio)\r\nSpeakers (Realtek(R) Audio)\r\n", ["Microphone Array (Realtek(R) Audio)"]),
    ("Mikrofon (USB Audio Device)\nSpeaker\n", ["Mikrofon (USB Audio Device)"]),
    ("Speakers (Realtek(R) Audio)\nHeadphones\n", []),
])
def test_parse_microphones(output, names):
    assert checks.parse_microphones(output) == names


def test_check_microphone():
    assert checks.check_microphone(["Microphone Array"]).status == OK
    assert checks.check_microphone([]).status == WARN
    assert "Tidak bisa dicek" in checks.check_microphone(None).message


def test_non_ascii_user_folder_warns():
    assert checks.check_user_path(r"C:\Users\arjun\AppData\Local").status == OK
    result = checks.check_user_path(r"C:\Users\Siti Nurhaliza Ñ\AppData\Local")
    assert result.status == WARN and "D:\\MikuVision" in result.message


def test_ollama_found_on_path_or_default_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(checks.shutil, "which", lambda name: None)
    assert checks.find_ollama({"LOCALAPPDATA": str(tmp_path)}) is None
    exe = tmp_path / "Programs" / "Ollama" / "ollama.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"")
    assert checks.find_ollama({"LOCALAPPDATA": str(tmp_path)}) == str(exe)
    assert checks.check_ollama(str(exe)).message.startswith("Sudah terpasang")


def test_model_present_reads_ollama_manifests(tmp_path):
    manifest = tmp_path / "manifests" / "registry.ollama.ai" / "library" / "qwen3" / "4b-instruct"
    manifest.parent.mkdir(parents=True)
    manifest.write_text("{}")
    assert checks.model_present(tmp_path, "qwen3:4b-instruct")
    assert not checks.model_present(tmp_path, "qwen3-vl:4b-instruct")
    assert not checks.model_present(tmp_path, "qwen3")  # tag bawaan "latest"


def test_model_locations_follow_user_variables():
    env = {"USERPROFILE": r"C:\Users\a", "OLLAMA_MODELS": r"D:\ollama_models"}
    assert checks.ollama_models_dir(env) == Path(r"D:\ollama_models")
    assert checks.huggingface_dir(env) == Path(r"C:\Users\a") / ".cache" / "huggingface"


def test_format_gb():
    assert checks.format_gb(12_345_678_901) == "12,3 GB"


@pytest.mark.skipif(sys.platform != "win32", reason="vswhere Visual Studio hanya di Windows")
def test_find_build_tools_uses_vswhere(tmp_path):
    environ = {"ProgramFiles(x86)": str(tmp_path)}
    assert checks.find_build_tools(environ) is False  # vswhere tidak ada: Visual Studio belum pernah dipasang
    vswhere = tmp_path / "Microsoft Visual Studio" / "Installer" / "vswhere.exe"
    vswhere.parent.mkdir(parents=True)
    vswhere.write_bytes(b"")
    calls = []

    def run(output):
        def fake(command, **kwargs):
            calls.append(command)
            return subprocess.CompletedProcess(command, 0, stdout=output, stderr=b"")
        return fake
    assert checks.find_build_tools(environ, run=run(b"C:\\VS\\BuildTools\r\n")) is True
    assert calls[-1][1:] == ["-products", "*", "-requires", checks.VC_TOOLS, "-property", "installationPath"]
    assert checks.find_build_tools(environ, run=run(b"")) is False  # Visual Studio tanpa workload C++

    def broken(command, **kwargs):
        raise OSError("vswhere rusak")
    assert checks.find_build_tools(environ, run=broken) is False
