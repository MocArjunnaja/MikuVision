"""MikuVision Setup: komponen, ruang disk per drive, validasi halaman 4, argumen install.ps1."""

import re
import sys
from pathlib import Path

import pytest

from miku_setup import components
from miku_setup.components import GB, MARGIN_GB, Selection

ROOT = Path(__file__).resolve().parent.parent

windows_paths = pytest.mark.skipif(sys.platform != "win32", reason="path dan drive Windows (C:, D:)")


def test_model_names_match_config():
    config = (ROOT / "config.py").read_text(encoding="utf-8")
    assert re.search(r'^OLLAMA_MODEL = "([^"]+)"', config, re.M).group(1) == components.LLM_MODEL
    assert re.search(r'^VISION_MODEL = "([^"]+)"', config, re.M).group(1) == components.VISION_MODEL


@windows_paths
def test_default_install_dir_is_per_user():
    assert components.default_install_dir({"LOCALAPPDATA": r"C:\Users\a\AppData\Local"}) == \
        Path(r"C:\Users\a\AppData\Local\Programs\MikuVision")


ENV = {"LOCALAPPDATA": r"C:\Users\a\AppData\Local", "USERPROFILE": r"C:\Users\a"}


def _gb(needs):
    return {drive: round(size / GB, 1) for drive, size in needs.items()}


@windows_paths
def test_fresh_install_on_c_counts_everything():
    selection = Selection(Path(r"C:\Users\a\AppData\Local\Programs\MikuVision"))
    needs = components.space_needed(selection, gpu=True, ollama_installed=False, environ=ENV)
    expected = components.CORE_APP_GB + components.SPEECH_MODELS_GB + components.OLLAMA_APP_GB \
        + components.LLM_GB + MARGIN_GB
    assert _gb(needs) == {"C:": round(expected, 1)}


@windows_paths
def test_model_folder_on_d_and_cpu_only():
    selection = Selection(Path(r"C:\Apps\MikuVision"), model_dir=Path(r"D:\MikuVision\models"),
                          components={"core", "brain", "vision"})
    needs = components.space_needed(selection, gpu=False, ollama_installed=True, environ=ENV)
    assert _gb(needs) == {
        "C:": round(components.CORE_APP_GB_CPU + MARGIN_GB, 1),
        "D:": round(components.SPEECH_MODELS_GB + components.LLM_GB + components.VISION_GB + MARGIN_GB, 1),
    }


@windows_paths
def test_models_already_downloaded_are_not_counted(tmp_path):
    library = tmp_path / "manifests" / "registry.ollama.ai" / "library"
    for name, tag in (("qwen3", "4b-instruct"), ("qwen3-vl", "4b-instruct")):
        (library / name).mkdir(parents=True, exist_ok=True)
        (library / name / tag).write_text("{}")
    env = dict(ENV, OLLAMA_MODELS=str(tmp_path))
    selection = Selection(Path(r"C:\Apps\MikuVision"), components={"core", "brain", "vision"})
    needs = components.space_needed(selection, gpu=True, ollama_installed=True, environ=env)
    # Hanya folder aplikasi dan cache Hugging Face; kedua model Ollama tidak diunduh lagi
    assert _gb(needs) == {"C:": round(components.CORE_APP_GB + components.SPEECH_MODELS_GB + MARGIN_GB, 1)}


@windows_paths
def test_rvc_files_count_on_the_app_drive():
    selection = Selection(Path(r"D:\MikuVision"), model_dir=Path(r"D:\MikuVision\models"),
                          components={"core", "brain", "rvc"}, rvc_model="a.pth", rvc_index="a.index")
    needs = components.space_needed(selection, gpu=True, ollama_installed=True, environ=ENV,
                                    rvc_file_size=lambda path: int(0.5 * GB))
    assert _gb(needs)["D:"] == round(components.CORE_APP_GB + components.RVC_APP_GB + 1.0
                                     + components.SPEECH_MODELS_GB + components.LLM_GB + MARGIN_GB, 1)


@windows_paths
@pytest.mark.parametrize("install_dir, model_dir, problem", [
    ("", None, "belum diisi"),
    ('C:\\Apps\\Miku"Vision', None, "tanda kutip"),
    ("MikuVision", None, "lengkap dengan drive"),
    (r"C:\Program Files\MikuVision", None, "tidak bisa ditulis"),
    (r"C:\Apps\MikuVision", 'D:\\mo"dels', "Folder model tidak boleh"),
])
def test_validate_folders(install_dir, model_dir, problem):
    selection = Selection(Path(install_dir) if install_dir else "", model_dir=Path(model_dir) if model_dir else None)
    writable = lambda path: "Program Files" not in str(path)  # noqa: E731
    assert problem in components.validate_selection(selection, writable)


def test_validate_rvc_files(tmp_path):
    model, index = tmp_path / "miku.pth", tmp_path / "miku.index"
    model.write_bytes(b"x")
    index.write_bytes(b"x")
    selection = Selection(tmp_path / "MikuVision", components={"core", "brain", "rvc"})
    assert "Pilih file bobot" in components.validate_selection(selection, lambda p: True)
    selection.rvc_model, selection.rvc_index = str(index), str(model)
    assert "harus file .pth" in components.validate_selection(selection, lambda p: True)
    selection.rvc_model, selection.rvc_index = str(model), str(index)
    assert components.validate_selection(selection, lambda p: True) is None


def test_is_writable(tmp_path):
    assert components.is_writable(tmp_path / "belum" / "ada")
    assert not list(tmp_path.iterdir())  # file uji dihapus lagi


def test_install_args():
    assert components.install_args(Selection(Path(r"C:\Apps\MikuVision"))) == \
        ["-Yes", "-Progress", "-StartMenu", "-SkipShortcut"]
    selection = Selection(Path(r"C:\Apps\MikuVision"), model_dir=Path(r"D:\Miku models"),
                          components={"core", "brain", "vision", "rvc"}, rvc_model=r"D:\a.pth", rvc_index=r"D:\a.index")
    assert components.install_args(selection) == [
        "-Yes", "-Progress", "-StartMenu", "-SkipShortcut", "-ModelDir", r"D:\Miku models", "-WithVision",
        "-RvcModel", r"D:\a.pth", "-RvcIndex", r"D:\a.index"]


def test_install_args_use_options_that_install_ps1_has():
    install_ps1 = (ROOT / "install.ps1").read_text(encoding="utf-8")
    selection = Selection(Path(r"C:\a"), model_dir=Path(r"D:\m"), components={"core", "brain", "vision", "rvc"},
                          rvc_model="x.pth", rvc_index="x.index")
    for option in (a for a in components.install_args(selection) if a.startswith("-")):
        assert re.search(rf"\[(switch|string)\]\${option[1:]}\b", install_ps1), option
