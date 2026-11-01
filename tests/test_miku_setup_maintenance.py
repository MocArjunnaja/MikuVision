"""MikuVision Setup fase I4: entri "Apps & features", Perbarui/Perbaiki, dan Hapus."""

import os
import sys
import uuid
from pathlib import Path

import pytest

from miku_setup import maintenance, registry
from miku_setup.components import Selection, install_args
from miku_setup.main import parse_args, requested_mode
from miku_setup.maintenance import RemovalPlan, app_shortcuts, register_install, remove_installation, selection_for
from miku_setup.registry import InstalledApp

windows_only = pytest.mark.skipif(sys.platform != "win32", reason="registry Windows")


def fake_install(root: Path) -> InstalledApp:
    install_dir = root / "MikuVision"
    for name in ("install.ps1", "gui.py", ".venv/Scripts/pythonw.exe", ".tools/mikuvision.ico",
                 "data/memory.json", "data/skills/kopi.yaml",
                 "models/miku_default_rvc/weights/miku_default_rvc.pth"):
        path = install_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x" * 1000)
    (install_dir / ".tools" / "mikuvision.ico").chmod(0o444)  # file read-only tetap terhapus
    (install_dir / "miku_setup").mkdir()
    (install_dir / "miku_setup" / "__init__.py").write_bytes(b"")
    model_dir = root / "models"
    (model_dir / "ollama" / "blobs").mkdir(parents=True)
    (model_dir / "ollama" / "blobs" / "sha256-1").write_bytes(b"m")
    return InstalledApp(install_dir, "1.6.0", model_dir, {"core", "brain", "vision", "rvc"})


@pytest.mark.parametrize("argv, installed, mode", [
    ([], None, "install"),
    ([], "ada", "maintain"),
    (["--update"], "ada", "update"),
    (["--repair"], "ada", "repair"),
    (["--uninstall"], "ada", "uninstall"),
    (["--uninstall"], None, "missing"),
])
def test_requested_mode(argv, installed, mode):
    assert requested_mode(parse_args(argv), installed) == mode


def test_modes_cannot_be_combined():
    with pytest.raises(SystemExit):
        parse_args(["--update", "--uninstall"])


def test_update_and_repair_reuse_the_recorded_choices_without_rvc_files(tmp_path):
    app = fake_install(tmp_path)
    selection = selection_for(app)
    assert selection.install_dir == app.install_dir and selection.model_dir == app.model_dir
    assert selection.components == {"core", "brain", "vision"}
    args = install_args(selection, platform="win32")
    assert "-WithVision" in args and "-ModelDir" in args and "-RvcModel" not in args


def test_registry_values(tmp_path):
    app = fake_install(tmp_path)
    values = registry.entry_values(app, 12345)
    assert values["DisplayName"] == "MikuVision" and values["DisplayVersion"] == "1.6.0"
    assert values["InstallLocation"] == str(app.install_dir)
    assert values["EstimatedSize"] == 12345 and values["NoRepair"] == 1
    assert values["UninstallString"].endswith(" --uninstall")
    assert values["UninstallString"].startswith('"') and str(registry.ENTRY_SCRIPT) in values["ModifyPath"]
    assert values["MikuComponents"] == "brain,core,rvc,vision"
    assert values["MikuModelDir"] == str(app.model_dir)


@windows_only
def test_registry_round_trip(tmp_path):
    key = rf"Software\MikuVisionTest\{uuid.uuid4().hex}"
    app = fake_install(tmp_path)
    try:
        registry.write_entry(app, 10, key_path=key)
        assert registry.read_installed(key_path=key) == app
        app.model_dir = None
        registry.write_entry(app, 10, key_path=key)
        assert registry.read_installed(key_path=key).model_dir is None
    finally:
        assert registry.delete_entry(key_path=key)
    assert registry.read_installed(key_path=key) is None
    assert not registry.delete_entry(key_path=key)


@windows_only
def test_registry_entry_without_the_folder_is_ignored(tmp_path):
    key = rf"Software\MikuVisionTest\{uuid.uuid4().hex}"
    app = InstalledApp(tmp_path / "hilang", "1.6.0")
    try:
        registry.write_entry(app, 10, key_path=key)
        assert registry.read_installed(key_path=key) is None
    finally:
        registry.delete_entry(key_path=key)


def test_register_install_records_rvc_already_in_models(tmp_path):
    app = fake_install(tmp_path)
    written = []
    problem = register_install(Selection(app.install_dir, components={"core", "brain"}), "1.6.0",
                               write=lambda entry, size: written.append((entry, size)))
    assert problem is None
    entry, size_kb = written[0]
    assert entry.components == {"core", "brain", "rvc"} and entry.version == "1.6.0"
    assert size_kb == 7000 // 1024  # 7 file × 1000 byte


def test_empty_rvc_folder_from_the_release_zip_is_not_rvc(tmp_path):
    install_dir = tmp_path / "MikuVision"
    (install_dir / "models" / "miku_default_rvc" / "weights").mkdir(parents=True)
    (install_dir / "models" / "miku_default_rvc" / "weights" / ".gitkeep").write_bytes(b"")
    written = []
    register_install(Selection(install_dir), "1.6.0", write=lambda entry, size: written.append(entry))
    assert written[0].components == {"core", "brain"}


def test_hardlinked_files_count_once(tmp_path):
    cache = tmp_path / ".tools" / "uv-cache" / "torch.pyd"
    cache.parent.mkdir(parents=True)
    cache.write_bytes(b"x" * 5000)
    venv = tmp_path / ".venv" / "torch.pyd"
    venv.parent.mkdir()
    os.link(cache, venv)
    (tmp_path / "gui.py").write_bytes(b"y" * 100)
    assert maintenance.folder_size(tmp_path) == 5100


def test_register_install_failure_is_only_a_warning(tmp_path):
    def broken(entry, size):
        raise PermissionError("akses ditolak")
    problem = register_install(Selection(tmp_path), "1.6.0", write=broken)
    assert registry.ENTRY_PLACE in problem and "akses ditolak" in problem


@windows_only
def test_shortcuts_pointing_elsewhere_are_kept(tmp_path):
    app = fake_install(tmp_path)
    start_menu = tmp_path / "Start Menu" / "MikuVision"
    start_menu.mkdir(parents=True)
    (start_menu / "MikuVision.lnk").write_bytes(b"lnk")
    desktop = tmp_path / "Desktop" / "MikuVision.lnk"
    desktop.parent.mkdir()
    desktop.write_bytes(b"lnk")
    targets = {desktop: str(app.install_dir / ".venv" / "Scripts" / "pythonw.exe")}
    found = app_shortcuts(app.install_dir, lambda lnk: targets.get(lnk, ""), start_menu, desktop)
    assert found == [start_menu / "MikuVision.lnk", desktop]
    targets[desktop] = r"D:\repo\MikuVision\.venv\Scripts\pythonw.exe"  # shortcut milik clone git user
    assert app_shortcuts(app.install_dir, lambda lnk: targets[lnk], start_menu, desktop) == \
        [start_menu / "MikuVision.lnk"]


def _remove(app, plan, shortcuts=(), env=None):
    deleted_entry, deleted_env = [], []
    env = env or {}
    problems = remove_installation(app, plan, shortcuts=list(shortcuts),
                                   delete_entry=lambda: deleted_entry.append(True),
                                   user_env=env.get, delete_user_env=deleted_env.extend)
    return problems, bool(deleted_entry), deleted_env


def test_uninstall_keeps_data_and_models_by_default(tmp_path):
    app = fake_install(tmp_path)
    lnk = tmp_path / "MikuVision.lnk"
    lnk.write_bytes(b"lnk")
    problems, entry_deleted, env_deleted = _remove(app, RemovalPlan(), [lnk])
    assert problems == [] and entry_deleted and env_deleted == []
    assert sorted(p.name for p in app.install_dir.iterdir()) == ["data"]
    assert (app.install_dir / "data" / "skills" / "kopi.yaml").is_file()
    assert (app.model_dir / "ollama" / "blobs" / "sha256-1").is_file()
    assert not lnk.exists()


def test_uninstall_everything_also_clears_model_variables(tmp_path):
    app = fake_install(tmp_path)
    env = {"OLLAMA_MODELS": str(app.model_dir / "ollama"), "HF_HOME": r"D:\hf_home_lain"}
    problems, entry_deleted, env_deleted = _remove(app, RemovalPlan(data=True, models=True), env=env)
    assert problems == [] and entry_deleted
    assert not app.install_dir.exists() and not app.model_dir.exists()
    assert env_deleted == ["OLLAMA_MODELS"]  # HF_HOME menunjuk ke tempat lain


def test_models_in_default_locations_are_never_removed(tmp_path):
    app = fake_install(tmp_path)
    app.model_dir = None
    problems, _, env_deleted = _remove(app, RemovalPlan(data=True, models=True))
    assert problems == [] and env_deleted == []
    assert (tmp_path / "models" / "ollama" / "blobs" / "sha256-1").is_file()


def test_locked_files_keep_the_registry_entry_for_another_try(tmp_path, monkeypatch):
    app = fake_install(tmp_path)
    real = maintenance.remove_tree

    def locked(path):
        return f"{path}: sedang dipakai" if path.name == ".venv" else real(path)
    monkeypatch.setattr(maintenance, "remove_tree", locked)
    problems, entry_deleted, _ = _remove(app, RemovalPlan())
    assert len(problems) == 1 and ".venv" in problems[0]
    assert not entry_deleted and (app.install_dir / ".venv").exists()
    # Tanda MikuVision dibiarkan, jadi Hapus yang diulang masih mengenali foldernya
    assert (app.install_dir / "gui.py").is_file() and (app.install_dir / "miku_setup").is_dir()


def test_running_processes_only_lists_programs_from_the_install_folder(tmp_path, monkeypatch):
    install_dir = tmp_path / "MikuVision"

    class Process:
        def __init__(self, pid, name, exe):
            self.info = {"pid": pid, "name": name, "exe": exe}
    processes = [Process(1, "pythonw.exe", str(install_dir / ".venv" / "Scripts" / "pythonw.exe")),
                 Process(2, "pythonw.exe", str(install_dir / ".tools" / "python" / "pythonw.exe")),
                 Process(3, "python.exe", str(tmp_path / "lain" / "python.exe")),
                 Process(4, "System", None)]
    psutil = pytest.importorskip("psutil")
    monkeypatch.setattr(psutil, "process_iter", lambda attrs: processes)
    assert maintenance.running_processes(install_dir) == ["pythonw.exe"]


@pytest.mark.parametrize("platform", ["win32", "linux"])
def test_the_setup_exe_own_bootloader_is_not_counted(tmp_path, monkeypatch, platform):
    """Modify dari "Apps & features" membuka MikuVisionSetup.exe di folder .tools: dua proses, exe sama."""
    install_dir = tmp_path / "MikuVision"
    setup_exe = install_dir / ".tools" / "MikuVisionSetup.exe"
    setup_exe.parent.mkdir(parents=True)
    setup_exe.write_bytes(b"exe")

    class Process:
        def __init__(self, pid, name, exe):
            self.info = {"pid": pid, "name": name, "exe": exe}
    processes = [Process(os.getpid() + 1, "MikuVisionSetup.exe", str(setup_exe)),  # bootloader
                 Process(os.getpid(), "MikuVisionSetup.exe", str(setup_exe)),
                 Process(os.getpid() + 2, "pythonw.exe", str(install_dir / ".venv" / "Scripts" / "pythonw.exe"))]
    psutil = pytest.importorskip("psutil")
    monkeypatch.setattr(psutil, "process_iter", lambda attrs: processes)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(setup_exe))
    monkeypatch.setattr(sys, "platform", platform)
    assert maintenance.running_processes(install_dir) == ["pythonw.exe"]


def test_uninstall_refuses_a_folder_that_is_not_mikuvision(tmp_path):
    """Entri registry yang menunjuk ke folder berisi file user: isinya tidak disentuh."""
    folder = tmp_path / "Documents"
    (folder / "skripsi").mkdir(parents=True)
    (folder / "skripsi" / "bab1.docx").write_bytes(b"penting")
    (folder / "install.ps1").write_bytes(b"x")  # cukup untuk read_installed, tapi bukan MikuVision
    problems, entry_deleted, _ = _remove(InstalledApp(folder, "1.6.0"), RemovalPlan(data=True))
    assert len(problems) == 1 and "tidak tampak seperti folder MikuVision" in problems[0]
    assert (folder / "skripsi" / "bab1.docx").read_bytes() == b"penting" and not entry_deleted


def test_model_removal_only_deletes_what_the_installer_made(tmp_path):
    app = fake_install(tmp_path)
    (app.model_dir / "huggingface" / "hub").mkdir(parents=True)
    (app.model_dir / "foto-liburan").mkdir()
    (app.model_dir / "foto-liburan" / "pantai.jpg").write_bytes(b"jpg")
    problems, _, _ = _remove(app, RemovalPlan(models=True))
    assert problems == []
    assert not (app.model_dir / "ollama").exists() and not (app.model_dir / "huggingface").exists()
    assert (app.model_dir / "foto-liburan" / "pantai.jpg").read_bytes() == b"jpg"


def test_uninstall_leaves_files_that_are_not_mikuvision(tmp_path):
    """Instalasi v1.6.0-v1.7.0 di folder yang sudah berisi file user: hanya isi MikuVision yang dihapus."""
    app = fake_install(tmp_path)
    (app.install_dir / "skripsi").mkdir()
    (app.install_dir / "skripsi" / "bab1.docx").write_bytes(b"penting")
    (app.install_dir / "foto.jpg").write_bytes(b"jpg")
    problems, entry_deleted, _ = _remove(app, RemovalPlan(data=True))
    assert problems == [] and entry_deleted
    assert sorted(p.name for p in app.install_dir.iterdir()) == ["foto.jpg", "skripsi"]
    assert (app.install_dir / "skripsi" / "bab1.docx").read_bytes() == b"penting"


def test_app_entries_cover_everything_in_the_release_zip():
    """Zip rilis = git archive: setiap entri tingkat atas repo harus terdaftar, atau Hapus meninggalkannya."""
    import subprocess
    root = Path(__file__).resolve().parents[1]
    try:
        files = subprocess.run(["git", "ls-files"], cwd=root, capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("butuh git dan repo")
    top = {line.split("/", 1)[0] for line in files.splitlines() if line}
    assert top and top <= maintenance.APP_ENTRIES, sorted(top - maintenance.APP_ENTRIES)

