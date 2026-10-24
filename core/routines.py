"""
Routines - rangkaian tool yang diputar dengan satu perintah ("mode belajar").

Contoh bawaan ada di routines.example.yaml (ikut repo). Routine milik user
ditulis di data/routines.yaml (tidak ikut git) dan menimpa contoh dengan nama sama.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from config import ROUTINES_EXAMPLE_FILE, ROUTINES_FILE
from core.tools import registry

# Routine tidak boleh memanggil routine lain (mencegah loop tanpa akhir)
FORBIDDEN_STEP_ACTIONS = {"run_routine", "list_routines"}


@dataclass
class Routine:
    name: str
    description: str = ""
    steps: List[Dict[str, Any]] = field(default_factory=list)


def _read_file(path: Path) -> List[Routine]:
    if not path.exists():
        return []
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as e:
        print(f"[Routines] Gagal membaca {path}: {e}")
        return []
    routines = []
    for raw in data.get("routines", []):
        if isinstance(raw, dict) and raw.get("name"):
            routines.append(Routine(str(raw["name"]), str(raw.get("description", "")), list(raw.get("steps") or [])))
    return routines


def load_routines(files: Tuple[Path, ...] = (ROUTINES_EXAMPLE_FILE, ROUTINES_FILE)) -> Dict[str, Routine]:
    """Routine per nama (huruf kecil); file belakangan menimpa yang sebelumnya."""
    routines: Dict[str, Routine] = {}
    for path in files:
        for routine in _read_file(path):
            routines[routine.name.lower()] = routine
    return routines


def validate(routine: Routine) -> Optional[str]:
    """Pesan error bila ada langkah yang tidak valid, None bila aman dijalankan."""
    if not routine.steps:
        return f"Routine '{routine.name}' tidak punya langkah"
    for i, step in enumerate(routine.steps, 1):
        action = step.get("action") if isinstance(step, dict) else None
        if not action:
            return f"Langkah {i} tidak punya 'action'"
        if action in FORBIDDEN_STEP_ACTIONS:
            return f"Langkah {i}: routine tidak boleh memanggil {action}"
        if registry.get_tool(action) is None:
            return f"Langkah {i}: tool '{action}' tidak dikenal"
    return None


def find_routine(name: str, routines: Optional[Dict[str, Routine]] = None) -> Optional[Routine]:
    routines = load_routines() if routines is None else routines
    key = name.strip().lower()
    if key in routines:
        return routines[key]
    partial = [r for k, r in routines.items() if key and key in k]
    return partial[0] if len(partial) == 1 else None


# Dipanggil lewat registry dengan instance SystemControl sebagai `self`,
# sehingga setiap langkah melewati execute_action (termasuk gerbang konfirmasi).
@registry.register(
    name="run_routine",
    description="Run a saved routine (a named sequence of actions) such as 'mode belajar'. "
                "Use when the user asks for a routine or mode by name. Call list_routines if unsure of the name.",
)
def run_routine(self, name: str) -> Tuple[bool, str]:
    routine = find_routine(name)
    if routine is None:
        available = ", ".join(r.name for r in load_routines().values()) or "-"
        return False, f"Routine '{name}' tidak ditemukan. Tersedia: {available}"
    error = validate(routine)
    if error:
        return False, error

    report = []
    for step in routine.steps:
        ok, msg = self.execute_action(step["action"], step.get("params") or {})
        report.append(f"{'✅' if ok else '❌'} {step['action']}: {msg}")
        if not ok:
            return False, f"Routine '{routine.name}' berhenti di langkah gagal: " + " | ".join(report)
    return True, f"Routine '{routine.name}' selesai: " + " | ".join(report)


@registry.register(name="list_routines", description="List the saved routines and what they do.")
def list_routines() -> Tuple[bool, str]:
    routines = load_routines()
    if not routines:
        return True, "Belum ada routine. Salin routines.example.yaml ke data/routines.yaml."
    return True, "; ".join(f"{r.name}: {r.description or len(r.steps)}" for r in routines.values())
