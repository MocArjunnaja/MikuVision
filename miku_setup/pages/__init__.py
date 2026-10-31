"""Satu file per halaman wizard (docs/PLAN_INSTALLER.md bagian 3)."""

from .finish import FinishPage
from .install import InstallPage
from .license import LicensePage
from .location import LocationPage
from .system_check import SystemCheckPage
from .welcome import WelcomePage

PAGES = [WelcomePage, LicensePage, SystemCheckPage, LocationPage, InstallPage, FinishPage]
