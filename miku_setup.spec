# PyInstaller: MikuVisionSetup.exe satu file tanpa jendela konsol (docs/PLAN_INSTALLER.md bagian 7).
#     pip install -r requirements-setup.txt
#     pyinstaller miku_setup.spec        ->  dist\MikuVisionSetup.exe
# Di Linux spec yang sama menghasilkan dist/MikuVisionSetup (ikon diabaikan). Pakai Python dari distro, bukan
# dari uv: Tk python-build-standalone tanpa Xft (lihat release-setup.yml, job linux).
# Tanpa UPX: UPX sering membuat antivirus menandai exe.
from PyInstaller.utils.hooks import collect_data_files

datas = [
    ("miku_setup/assets/dry_run_stdout.txt", "miku_setup/assets"),
    # welcome.py membaca sprite dari <root>/assets/avatar, seperti di repo
    ("assets/avatar/miku_smart_sheet.png", "assets/avatar"),
] + collect_data_files("customtkinter")

a = Analysis(
    ["MikuVisionSetup.py"],
    datas=datas,
    hiddenimports=["PIL._tkinter_finder"],
    # Paket aplikasi yang mungkin terpasang di env build tapi tidak dipakai Setup
    excludes=["torch", "numpy", "scipy", "pandas", "matplotlib", "faster_whisper", "ollama"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name="MikuVisionSetup",
    icon="miku_setup/assets/mikuvision.ico",
    console=False,
    upx=False,
)
