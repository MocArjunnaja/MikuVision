"""
Membuka aplikasi apa pun yang terdaftar di menu sistem, bukan hanya yang ada di katalog
config.py, lalu mengingatnya (cache) setelah berhasil dibuka.

Urutan open_application:
  1. katalog alias di config.py (ALLOWED_APPS / LINUX_APPS)
  2. cache: aplikasi yang sudah pernah ditemukan dan berhasil dibuka (data/app_cache.json)
  3. daftar aplikasi sistem (menu aplikasi Linux / Start Menu Windows); yang berhasil
     dibuka disimpan ke cache
  4. tidak ketemu: sebutkan aplikasi terpasang yang namanya paling mirip

Hanya aplikasi yang terdaftar di menu yang bisa dibuka, tanpa shell; path atau perintah
bebas dari LLM tidak pernah dijalankan.
"""

import json
import os
import re
import time
import unicodedata
from dataclasses import asdict, dataclass
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# Nama aplikasi berisi kata ini tidak pernah dibuka lewat pencarian: salah dengar
# bisa menjalankan pencopot aplikasi. Hanya nama yang dicek, bukan kata kunci.
BLOCKED_NAME_WORDS = ("uninstall", "uninstaller", "hapus instalasi")

MATCH_THRESHOLD = 50       # skor minimal untuk dianggap cocok
SUGGEST_THRESHOLD = 30     # skor minimal untuk disebut sebagai "yang mirip"
INSTALLED_TTL_SEC = 60     # daftar aplikasi dibaca ulang paling cepat tiap menit


@dataclass(frozen=True)
class AppEntry:
    id: str                              # Linux: id .desktop; Windows: AppID Start Menu
    name: str                            # nama yang tampil di menu
    aliases: Tuple[str, ...] = ()        # nama terjemahan, GenericName
    keywords: Tuple[str, ...] = ()
    process_names: Tuple[str, ...] = ()  # untuk close_application
    path: str = ""                       # file .desktop / .lnk bila ada


def normalize(text: str) -> str:
    """Huruf kecil, tanpa aksen Latin dan tanda baca. Huruf Jepang tetap, termasuk dakuten (ジ)."""
    kept: List[str] = []
    for ch in unicodedata.normalize("NFKD", (text or "").lower()):
        # Hanya tanda di atas huruf Latin (é -> e); ジ = シ + dakuten harus tetap ジ
        if unicodedata.combining(ch) and kept and ord(kept[-1]) < 0x0250:
            continue
        kept.append(ch)
    text = unicodedata.normalize("NFKC", "".join(kept))
    return re.sub(r"[^\w]+", " ", text).strip()


def _score_name(query: str, name: str) -> int:
    if not name:
        return 0
    if query == name:
        return 100
    if query.replace(" ", "") == name.replace(" ", ""):        # "libre office" = "libreoffice"
        return 95
    query_words, name_words = set(query.split()), set(name.split())
    if query_words <= name_words:                               # "writer" -> "libreoffice writer"
        return 80
    if name_words <= query_words:                               # "aplikasi libreoffice" -> "libreoffice"
        return 70
    if len(query) >= 4 and query in name:                       # "office" -> "libreoffice"
        return 50
    ratio = SequenceMatcher(None, query, name).ratio()          # salah ketik / salah dengar
    return int(ratio * 60) if ratio >= 0.8 else int(ratio * 40)


def score(query: str, entry: AppEntry) -> int:
    """Seberapa cocok query (sudah dinormalisasi) dengan aplikasi ini, 0-100."""
    best = max(_score_name(query, normalize(name)) for name in (entry.name, *entry.aliases))
    keywords = {normalize(k) for k in entry.keywords}
    if query in keywords:                                       # "explorer" -> Nemo
        best = max(best, 60)
    return best


def _blocked(entry: AppEntry) -> bool:
    name = entry.name.lower()
    return any(word in name for word in BLOCKED_NAME_WORDS)


def find(query: str, entries: List[AppEntry]) -> Tuple[Optional[AppEntry], List[AppEntry]]:
    """(aplikasi yang cocok, kandidat bila ambigu). Keduanya kosong bila tidak ada yang cocok."""
    scored = sorted(((score(query, e), e) for e in entries if not _blocked(e)),
                    key=lambda item: item[0], reverse=True)
    if not scored or scored[0][0] < MATCH_THRESHOLD:
        return None, []
    top = scored[0][0]
    tied = [e for s, e in scored if s == top]
    # Nama persis menang; di bawah itu, beberapa aplikasi dengan skor sama = tanyakan user
    if top == 100 or len(tied) == 1:
        return tied[0], []
    return None, tied


class AppCache:
    """Aplikasi yang sudah dipelajari: nama yang diucapkan user -> aplikasi di menu.

    Dipisah per OS: folder data/ bisa dipakai bersama Windows dan Linux (dual-boot).
    """

    def __init__(self, path: Path, os_name: str):
        self.path = Path(path)
        self.os_name = os_name

    def _load(self) -> Dict[str, Dict[str, dict]]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save(self, data: Dict[str, Dict[str, dict]]):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)

    def get(self, query: str) -> Optional[dict]:
        return self._load().get(self.os_name, {}).get(query)

    def put(self, query: str, entry: AppEntry):
        data = self._load()
        record = {k: v for k, v in asdict(entry).items() if k in ("id", "name", "process_names")}
        record["learned"] = date.today().isoformat()
        data.setdefault(self.os_name, {})[query] = record
        self._save(data)

    def drop(self, query: str) -> bool:
        data = self._load()
        if data.get(self.os_name, {}).pop(query, None) is None:
            return False
        self._save(data)
        return True

    def items(self) -> List[Tuple[str, dict]]:
        return sorted(self._load().get(self.os_name, {}).items())


class AppLauncher:
    """Cari aplikasi di cache lalu di menu sistem, buka, dan pelajari yang berhasil."""

    def __init__(self, desktop, cache: AppCache):
        self.desktop = desktop
        self.cache = cache
        self._installed: List[AppEntry] = []
        self._installed_at = 0.0

    def installed(self) -> List[AppEntry]:
        if not self._installed or time.time() - self._installed_at > INSTALLED_TTL_SEC:
            try:
                self._installed = self.desktop.list_installed_apps()
            except Exception as e:
                print(f"[AppSearch] Gagal membaca daftar aplikasi: {e}")
                self._installed = []
            self._installed_at = time.time()
        return self._installed

    def open(self, app_name: str) -> Optional[Tuple[bool, str, Optional[int]]]:
        """(sukses, pesan, PID) bila aplikasi ditemukan atau ambigu; None bila tidak ada yang cocok."""
        query = normalize(app_name)
        if not query:
            return None

        cached = self.cache.get(query)
        if cached:
            entry = next((e for e in self.installed() if e.id == cached.get("id")), None)
            if entry:
                return self._launch(entry, query)
            # Sudah dihapus dari sistem: lupakan lalu cari lagi
            self.cache.drop(query)

        match, candidates = find(query, self.installed())
        if match:
            return self._launch(match, query)
        if candidates:
            names = ", ".join(e.name for e in candidates[:5])
            return False, f"'{app_name}' cocok dengan beberapa aplikasi: {names}. Tanyakan user yang mana.", None
        return None

    def _launch(self, entry: AppEntry, query: str) -> Tuple[bool, str, Optional[int]]:
        success, message, pid = self.desktop.launch_entry(entry)
        if success:
            # Dipelajari hanya bila benar-benar terbuka
            self.cache.put(query, entry)
        return success, message, pid

    def suggestions(self, app_name: str, limit: int = 3) -> List[str]:
        query = normalize(app_name)
        if not query:
            return []
        scored = sorted(((score(query, e), e.name) for e in self.installed() if not _blocked(e)), reverse=True)
        return [name for s, name in scored[:limit] if s >= SUGGEST_THRESHOLD]

    def process_names(self, app_name: str) -> Set[str]:
        """Nama proses aplikasi yang pernah dibuka lewat pencarian, untuk close_application."""
        cached = self.cache.get(normalize(app_name))
        return set(cached.get("process_names", [])) if cached else set()
