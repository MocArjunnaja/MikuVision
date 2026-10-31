"""Satu file per halaman wizard (docs/PLAN_INSTALLER.md bagian 3)."""

from .finish import FinishPage
from .install import InstallPage
from .license import LicensePage
from .location import LocationPage
from .maintenance import MaintenancePage
from .system_check import SystemCheckPage
from .uninstall import RemovePage, UninstallPage
from .welcome import WelcomePage

PAGES = [WelcomePage, LicensePage, SystemCheckPage, LocationPage, InstallPage, FinishPage]
# Halaman per mode. "maintain" = Setup dibuka lagi saat sudah terpasang; pilihan di halaman pertama
# menyambungkan halaman mode itu (Wizard.switch_flow). --update/--repair/--uninstall mulai langsung di modenya.
FLOWS = {
    "install": PAGES,
    "maintain": [MaintenancePage],
    "update": [InstallPage, FinishPage],
    "repair": [InstallPage, FinishPage],
    "uninstall": [UninstallPage, RemovePage],
}
