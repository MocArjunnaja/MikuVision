"""
Long-Term Memory - fakta tentang user yang bertahan antar sesi.

Disimpan sebagai JSON {key: {"value": ..., "updated": ...}} di data/ (tidak ikut git).
Fakta terbaru disisipkan ke system prompt, jadi Miku bisa menjawab
"kapan ulang tahunku?" tanpa harus memanggil tool.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

from config import LONG_TERM_MEMORY_FILE, MEMORY_PROMPT_MAX_FACTS
from core.tools import registry

# Batas panjang supaya satu fakta tidak menghabiskan konteks 8k
MAX_KEY_CHARS = 60
MAX_VALUE_CHARS = 300


class LongTermMemory:
    """Penyimpanan key-value sederhana berbasis file JSON."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def _load(self) -> Dict[str, Dict[str, str]]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            print(f"[LongTermMemory] Gagal membaca {self.path}: {e}")
            return {}

    def _save(self, facts: Dict[str, Dict[str, str]]):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(facts, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _normalize_key(key: str) -> str:
        return " ".join(key.strip().lower().split())[:MAX_KEY_CHARS]

    def remember(self, key: str, value: str) -> Tuple[bool, str]:
        key, value = self._normalize_key(key), value.strip()[:MAX_VALUE_CHARS]
        if not key or not value:
            return False, "Key dan value tidak boleh kosong"
        facts = self._load()
        facts[key] = {"value": value, "updated": datetime.now().isoformat(timespec="seconds")}
        self._save(facts)
        return True, f"Diingat: {key} = {value}"

    def recall(self, key: str = "") -> Tuple[bool, str]:
        facts = self._load()
        key = self._normalize_key(key)
        if not key:
            if not facts:
                return True, "Belum ada yang diingat"
            return True, "; ".join(f"{k}: {v['value']}" for k, v in facts.items())
        matches = {k: v for k, v in facts.items() if key in k}
        if not matches:
            return False, f"Tidak ada ingatan tentang '{key}'"
        return True, "; ".join(f"{k}: {v['value']}" for k, v in matches.items())

    def forget(self, key: str) -> Tuple[bool, str]:
        facts = self._load()
        key = self._normalize_key(key)
        if key not in facts:
            return False, f"Tidak ada ingatan '{key}'"
        del facts[key]
        self._save(facts)
        return True, f"Dilupakan: {key}"

    def recent_facts(self, limit: int = MEMORY_PROMPT_MAX_FACTS) -> List[Tuple[str, str]]:
        facts = self._load()
        newest = sorted(facts.items(), key=lambda kv: kv[1].get("updated", ""), reverse=True)
        return [(k, v["value"]) for k, v in newest[:limit]]

    def as_prompt(self) -> str:
        facts = self.recent_facts()
        if not facts:
            return ""
        lines = "\n".join(f"- {k}: {v}" for k, v in facts)
        return f"## Things you remember about the user (long-term memory)\n{lines}"


store = LongTermMemory(LONG_TERM_MEMORY_FILE)


@registry.register(
    name="remember",
    description="Save an important fact about the user for future sessions (name, birthday, "
                "preferences, schedule). ALWAYS call this when the user says 'ingat', 'tolong ingat', "
                "'覚えて', '覚えておいて' or 'remember'; only saying you will remember is not enough. "
                "key = short label, value = the fact. Examples: '私の誕生日は5月5日だよ。覚えておいてね' -> "
                "remember(key='誕生日', value='5月5日'); 'ingat ya, aku kuliah di ITS' -> "
                "remember(key='kampus', value='ITS').",
)
def remember(key: str, value: str) -> Tuple[bool, str]:
    return store.remember(key, value)


@registry.register(
    name="recall_memory",
    description="Look up facts saved with remember. Empty key returns everything.",
)
def recall_memory(key: str = "") -> Tuple[bool, str]:
    return store.recall(key)


@registry.register(
    name="forget",
    description="Delete a saved fact when the user asks to forget it ('lupakan', '忘れて').",
)
def forget(key: str) -> Tuple[bool, str]:
    return store.forget(key)
