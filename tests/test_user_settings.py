"""Pengaturan user di data/settings.yaml: menimpa config.py dan tetap ada setelah Perbarui."""

import copy
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

import config
from miku_setup.download import safe_extract

ROOT = Path(__file__).resolve().parent.parent


def _namespace(tmp_path):
    return {"BASE_DIR": tmp_path, "CHARACTERS": copy.deepcopy(config.CHARACTERS)}


def test_known_settings_are_applied(tmp_path):
    ns = _namespace(tmp_path)
    warnings = config.apply_user_settings({
        "OLLAMA_MODEL": "qwen3:8b", "OLLAMA_THINK": False, "OLLAMA_NUM_CTX": 16384, "OLLAMA_KEEP_ALIVE": "10m",
        "VISION_NUM_GPU": None, "WHISPER_MODEL": "small", "WHISPER_LANGUAGES": ["ja", "id", "en"],
        "WHISPER_DEVICE": "cpu", "WAKE_PHRASE_ENABLED": False,
    }, ns)
    assert warnings == []
    assert ns["OLLAMA_MODEL"] == "qwen3:8b" and ns["OLLAMA_THINK"] is False and ns["OLLAMA_NUM_CTX"] == 16384
    assert ns["WHISPER_LANGUAGES"] == ("ja", "id", "en") and ns["WHISPER_DEVICE"] == "cpu"
    assert ns["USER_SETTINGS_APPLIED"][0] == "OLLAMA_MODEL"


def test_rvc_settings_change_every_character_that_uses_rvc(tmp_path):
    ns = _namespace(tmp_path)
    assert config.apply_user_settings({"RVC_MODEL_PATH": "models/suara/miku.pth",
                                       "RVC_INDEX_PATH": str(tmp_path / "x.index"),
                                       "RVC_PITCH": 4, "RVC_ENABLED": False}, ns) == []
    rvc = ns["CHARACTERS"]["miku"].rvc_config
    assert rvc.model_path == str(tmp_path / "models" / "suara" / "miku.pth")  # relatif terhadap folder aplikasi
    assert rvc.index_path == str(tmp_path / "x.index") and rvc.f0_up_key == 4 and rvc.enabled is False
    assert config.CHARACTERS["miku"].rvc_config.f0_up_key == 6  # config asli tidak berubah


@pytest.mark.parametrize("values, message", [
    ({"OLLAMA_NUM_CTX": True}, "OLLAMA_NUM_CTX harus int"),
    ({"OLLAMA_NUM_CTX": "8192"}, "OLLAMA_NUM_CTX harus int"),
    ({"OLLAMA_THINK": "tidak"}, "OLLAMA_THINK harus bool atau kosong"),
    ({"WHISPER_DEVICE": "gpu"}, "harus cuda atau cpu"),
    ({"WHISPER_LANGUAGES": []}, "daftar kode bahasa"),
    ({"MODEL_SAKTI": 1}, "MODEL_SAKTI tidak dikenal"),
])
def test_wrong_settings_are_skipped_with_a_reason(tmp_path, values, message):
    ns = _namespace(tmp_path)
    warnings = config.apply_user_settings(values, ns)
    assert len(warnings) == 1 and message in warnings[0]
    assert ns["USER_SETTINGS_APPLIED"] == [] and set(ns) == {"BASE_DIR", "CHARACTERS", "USER_SETTINGS_APPLIED"}


def test_settings_file_must_be_a_mapping(tmp_path):
    assert config.apply_user_settings(["OLLAMA_MODEL"], _namespace(tmp_path)) == ["isinya harus berupa baris NAMA: nilai"]


def _import_config(settings: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ, MIKUVISION_SETTINGS=str(settings), PYTHONIOENCODING="utf-8")
    code = "import config; print('MODEL=' + config.OLLAMA_MODEL)"
    return subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True,
                          encoding="utf-8", timeout=120)


def test_settings_file_is_read_when_config_is_imported(tmp_path):
    settings = tmp_path / "settings.yaml"
    settings.write_text("# model lebih besar\nOLLAMA_MODEL: qwen3:8b\nOLLAMA_NUM_CTX: banyak\n", encoding="utf-8")
    result = _import_config(settings)
    assert "MODEL=qwen3:8b" in result.stdout
    assert "OLLAMA_NUM_CTX harus int" in result.stdout and "(dilewati)" in result.stdout


def test_broken_settings_file_keeps_the_defaults(tmp_path):
    settings = tmp_path / "settings.yaml"
    settings.write_text("OLLAMA_MODEL: [rusak\n", encoding="utf-8")
    result = _import_config(settings)
    assert result.returncode == 0 and "tidak terbaca, diabaikan" in result.stdout
    assert f"MODEL={config.OLLAMA_MODEL}" in result.stdout


def test_example_file_only_uses_known_keys_and_the_defaults():
    """settings.example.yaml: semua kunci dikenal, dan nilai contohnya sama dengan bawaan config.py."""
    yaml = pytest.importorskip("yaml")
    lines = (ROOT / "settings.example.yaml").read_text(encoding="utf-8").splitlines()
    # Kunci di contoh dikomentari ("# OLLAMA_MODEL: ..."): buka komentarnya untuk dicek
    uncommented = "\n".join(line[2:] for line in lines if re.match(r"# [A-Z][A-Z_]+: ", line))
    values = yaml.safe_load(uncommented)
    assert set(values) == set(config.SETTING_TYPES)
    assert config.apply_user_settings(values, {"BASE_DIR": ROOT, "CHARACTERS": copy.deepcopy(config.CHARACTERS)}) == []
    for name in ("OLLAMA_MODEL", "VISION_MODEL", "WHISPER_MODEL", "OLLAMA_NUM_CTX"):
        assert values[name] == getattr(config, name), name


def test_update_keeps_the_settings_file(tmp_path):
    """Perbarui lewat Setup mengekstrak zip rilis di atas instalasi lama: data/ tidak disentuh."""
    install = tmp_path / "MikuVision"
    (install / "data").mkdir(parents=True)
    (install / "data" / "settings.yaml").write_text("OLLAMA_MODEL: qwen3:8b\n", encoding="utf-8")
    (install / "config.py").write_text("# lama\n", encoding="utf-8")
    release = tmp_path / "MikuVision-9.9.9.zip"
    with zipfile.ZipFile(release, "w") as archive:
        archive.writestr("MikuVision-9.9.9/config.py", "# baru\n")
        archive.writestr("MikuVision-9.9.9/settings.example.yaml", "# contoh\n")
    safe_extract(release, install)
    assert (install / "config.py").read_text(encoding="utf-8") == "# baru\n"
    assert (install / "data" / "settings.yaml").read_text(encoding="utf-8") == "OLLAMA_MODEL: qwen3:8b\n"
