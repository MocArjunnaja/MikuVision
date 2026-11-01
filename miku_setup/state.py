"""Keadaan wizard yang dibagi semua halaman."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from .checks import CheckResult
from .components import Selection
from .maintenance import RemovalPlan
from .registry import InstalledApp


@dataclass
class SetupState:
    selection: Selection
    log_path: Path
    dry_run: bool = True
    dry_run_fail: bool = False          # --dry-run-fail: putar ulang log yang berakhir dengan error
    license_accepted: bool = False
    results: List[CheckResult] = field(default_factory=list)
    gpu: bool = True
    ollama_installed: bool = False
    build_tools_present: Optional[bool] = None  # dicek sekali saat RVC pertama kali dicentang (Windows)
    install_ok: Optional[bool] = None   # None = belum selesai
    last_error: str = ""
    warnings: List[str] = field(default_factory=list)
    # Linux: izin di halaman 4 untuk memasang paket sistem dan Ollama lewat pkexec
    root_consent: bool = False
    desktop_shortcut: bool = True
    launch_now: bool = True
    # install, maintain (Setup dibuka lagi), update, repair, uninstall
    mode: str = "install"
    installed: Optional[InstalledApp] = None
    latest_version: str = ""
    version: str = ""                   # versi yang baru dipasang (dari version.json rilis)
    removal: RemovalPlan = field(default_factory=RemovalPlan)
    removal_problems: List[str] = field(default_factory=list)
