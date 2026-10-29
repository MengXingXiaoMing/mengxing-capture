"""配置读写（JSON，放在 userdata/config.json）。"""
from __future__ import annotations

import copy
import json
from typing import Any

from .paths import CONFIG_FILE, DEFAULT_CAPTURE_DIR, DEFAULT_RECORD_DIR

DEFAULTS: dict[str, Any] = {
    "hotkeys": {
        "capture": "ctrl+alt+a",
        "translate": "ctrl+alt+t",
        "record": "ctrl+alt+r",
        "record_pause": "ctrl+alt+p",
        "stop": "ctrl+alt+s",
    },
    "capture": {
        "save_dir": str(DEFAULT_CAPTURE_DIR),
        "auto_copy": True,
    },
    "record": {
        "save_dir": str(DEFAULT_RECORD_DIR),
        "fps": 30,
        "crf": 23,
        "preset": "veryfast",
        "target": "region",          # region / fullscreen / window
        "audio_system": True,
        "audio_mic": "",
        "camera": "",
        "camera_size": 260,
        "camera_corner": "br",
        "draw_cursor": True,
    },
    "translate": {
        "engine": "argos",           # argos / ollama
        "target": "zh",              # 目标语言
        "source": "auto",
        "ollama_url": "http://127.0.0.1:11434",
        "ollama_model": "",
        "font_size": 15,
    },
    "ui": {
        "close_to_tray": True,
    },
}


def _deep_merge(base: dict, patch: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


class Config:
    def __init__(self) -> None:
        self._data = copy.deepcopy(DEFAULTS)
        self.load()

    def load(self) -> None:
        if CONFIG_FILE.is_file():
            try:
                saved = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                if isinstance(saved, dict):
                    self._data = _deep_merge(DEFAULTS, saved)
            except (OSError, json.JSONDecodeError):
                pass

    def save(self) -> None:
        try:
            CONFIG_FILE.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError:
            pass

    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self._data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def set(self, dotted: str, value: Any) -> None:
        parts = dotted.split(".")
        node = self._data
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value

    @property
    def data(self) -> dict:
        return self._data


CONFIG = Config()
