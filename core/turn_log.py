"""
Turn Log - satu baris JSON per giliran percakapan di data/logs/turns_YYYYMMDD.jsonl
(dan per aksi berisiko di actions_YYYYMMDD.jsonl, lihat SystemControl.execute_action).

Isinya cukup untuk debugging dan benchmark: input user, tool yang dipanggil beserta
hasilnya, balasan, token dari Ollama, dan latensi. Folder data/ tidak ikut git.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict


class TurnLogger:
    def __init__(self, log_dir: Path, prefix: str = "turns"):
        self.log_dir = Path(log_dir)
        self.prefix = prefix

    def log(self, record: Dict[str, Any]):
        self.log_dir.mkdir(parents=True, exist_ok=True)
        entry = {"ts": datetime.now().isoformat(timespec="seconds"), **record}
        path = self.log_dir / f"{self.prefix}_{datetime.now():%Y%m%d}.jsonl"
        try:
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        except OSError as e:
            # Log tidak boleh menghentikan percakapan
            print(f"[TurnLogger] Gagal menulis log: {e}")
