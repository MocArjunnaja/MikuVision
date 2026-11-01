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
    assert components.install_args(Selection(Path(r"C:\Apps\MikuVision")), platform="win32") == \
        ["-Yes", "-Progress", "-StartMenu", "-SkipShortcut"]
    selection = Selection(Path(r"C:\Apps\MikuVision"), model_dir=Path(r"D:\Miku models"),
                          components={"core", "brain", "vision", "rvc"}, rvc_model=r"D:\a.pth", rvc_index=r"D:\a.index")
    assert components.install_args(selection, platform="win32") == [
        "-Yes", "-Progress", "-StartMenu", "-SkipShortcut", "-ModelDir", r"D:\Miku models", "-WithVision",
        "-RvcModel", r"D:\a.pth", "-RvcIndex", r"D:\a.index"]


def test_install_args_use_options_that_install_ps1_has():
    install_ps1 = (ROOT / "install.ps1").read_text(encoding="utf-8")
    selection = Selection(Path(r"C:\a"), model_dir=Path(r"D:\m"), components={"core", "brain", "vision", "rvc"},
                          rvc_model="x.pth", rvc_index="x.index", build_tools=True)
    for option in (a for a in components.install_args(selection, platform="win32") if a.startswith("-")):
        assert re.search(rf"\[(switch|string)\]\${option[1:]}\b", install_ps1), option


def _folder_check(tmp_path, install_dir, model_dir=None):
    selection = components.Selection(install_dir, model_dir=model_dir)
    return components.validate_selection(selection, lambda p: True, home=tmp_path / "home")


def _fill(folder, *names):
    for name in names:
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")
    return folder


def test_app_folder_must_be_new_empty_or_mikuvision(tmp_path):
    assert _folder_check(tmp_path, tmp_path / "baru" / "MikuVision") is None
    (tmp_path / "kosong").mkdir()
    assert _folder_check(tmp_path, tmp_path / "kosong") is None
    assert _folder_check(tmp_path, _fill(tmp_path / "sisa", "data/memory.json", "logs/a.log")) is None
    assert _folder_check(tmp_path, _fill(tmp_path / "lama", "gui.py", "miku_setup/__init__.py", ".venv/x")) is None
    problem = _folder_check(tmp_path, _fill(tmp_path / "Documents", "skripsi.docx"))
    assert "sudah berisi file lain" in problem and str(tmp_path / "Documents" / "MikuVision") in problem
    assert "clone git" in _folder_check(tmp_path, _fill(tmp_path / "repo", ".git/HEAD", "gui.py", "miku_setup/x"))


def test_drive_root_and_home_are_refused(tmp_path):
    root = Path(tmp_path.anchor)
    assert "tidak boleh langsung" in _folder_check(tmp_path, root)
    (tmp_path / "home").mkdir()
    assert "tidak boleh langsung" in _folder_check(tmp_path, tmp_path / "home")
    assert "Folder model tidak boleh langsung" in _folder_check(tmp_path, tmp_path / "app", model_dir=root)


def test_model_folder_must_be_empty_or_hold_only_model_subfolders(tmp_path):
    ok = _fill(tmp_path / "models", "ollama/blobs/a", "huggingface/hub/b")
    assert _folder_check(tmp_path, tmp_path / "app", model_dir=ok) is None
    problem = _folder_check(tmp_path, tmp_path / "app", model_dir=_fill(tmp_path / "D", "film/a.mkv"))
    assert "Folder model sudah berisi file lain" in problem


def test_build_tools_option_only_with_rvc_and_missing_compiler():
    rvc = Selection(Path(r"C:\a"), components={"core", "brain", "rvc"}, rvc_model="x.pth", rvc_index="x.index")
    assert "-InstallBuildTools" not in components.install_args(rvc, platform="win32")
    rvc.build_tools = True
    assert components.install_args(rvc, platform="win32")[-1] == "-InstallBuildTools"


@windows_paths
def test_build_tools_space_goes_to_the_system_drive():
    selection = Selection(Path(r"D:\Apps\MikuVision"), components={"core", "brain", "rvc"})
    environ = {"SystemDrive": "C:", "LOCALAPPDATA": r"D:\Local"}

    def needs():
        return components.space_needed(selection, gpu=True, ollama_installed=True, environ=environ,
                                       rvc_file_size=lambda path: 0)
    without = needs()
    selection.build_tools = True
    assert needs()["C:"] - without.get("C:", MARGIN_GB * GB) == pytest.approx(components.BUILD_TOOLS_GB * GB)

