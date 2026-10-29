"""Windows 全局热键（RegisterHotKey，无第三方依赖）。"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from typing import Callable

from PyQt6.QtCore import QAbstractNativeEventFilter, QCoreApplication

WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

_MODS = {
    "ctrl": MOD_CONTROL,
    "control": MOD_CONTROL,
    "alt": MOD_ALT,
    "shift": MOD_SHIFT,
    "win": MOD_WIN,
    "meta": MOD_WIN,
}

_KEYS = {
    "backspace": 0x08, "tab": 0x09, "enter": 0x0D, "return": 0x0D,
    "esc": 0x1B, "escape": 0x1B, "space": 0x20,
    "pageup": 0x21, "pagedown": 0x22, "end": 0x23, "home": 0x24,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "insert": 0x2D, "delete": 0x2E,
    "-": 0xBD, "=": 0xBB, "[": 0xDB, "]": 0xDD, "\\": 0xDC,
    ";": 0xBA, "'": 0xDE, ",": 0xBC, ".": 0xBE, "/": 0xBF, "`": 0xC0,
}
for _i in range(1, 25):
    _KEYS[f"f{_i}"] = 0x6F + _i


class HotkeyError(RuntimeError):
    pass


def parse_hotkey(text: str) -> tuple[int, int]:
    parts = [p.strip().lower() for p in text.replace(" ", "").split("+") if p.strip()]
    if not parts:
        raise HotkeyError("热键为空")
    mods = 0
    vk = None
    for p in parts:
        if p in _MODS:
            mods |= _MODS[p]
        elif len(p) == 1 and p.isalnum():
            vk = ord(p.upper())
        elif p in _KEYS:
            vk = _KEYS[p]
        else:
            raise HotkeyError(f"无法识别的按键：{p}")
    if vk is None:
        raise HotkeyError("热键缺少主键")
    return mods, vk


class HotkeyManager(QAbstractNativeEventFilter):
    def __init__(self, app: QCoreApplication) -> None:
        super().__init__()
        self._app = app
        self._callbacks: dict[int, Callable[[], None]] = {}
        self._by_name: dict[str, int] = {}
        self._next_id = 0x4C58  # 'LX'
        self._user32 = ctypes.windll.user32
        self._installed = False

    def _ensure_installed(self) -> None:
        if not self._installed:
            self._app.installNativeEventFilter(self)
            self._installed = True

    def register(self, name: str, sequence: str, callback: Callable[[], None]) -> None:
        if not sequence.strip():
            return
        mods, vk = parse_hotkey(sequence)
        hid = self._next_id
        self._next_id += 1
        if not self._user32.RegisterHotKey(None, hid, mods | MOD_NOREPEAT, vk):
            err = ctypes.get_last_error()
            raise HotkeyError(f"热键 {sequence} 注册失败（可能已被其它程序占用）")
        self._callbacks[hid] = callback
        self._by_name[name] = hid
        self._ensure_installed()

    def unregister(self, name: str) -> None:
        hid = self._by_name.pop(name, None)
        if hid is None:
            return
        self._user32.UnregisterHotKey(None, hid)
        self._callbacks.pop(hid, None)

    def unregister_all(self) -> None:
        for name in list(self._by_name):
            self.unregister(name)

    def nativeEventFilter(self, eventType, message):  # noqa: N802
        et = bytes(eventType).decode(errors="ignore") if not isinstance(eventType, str) else eventType
        if et in ("windows_generic_MSG", "windows_dispatcher_MSG"):
            try:
                msg = wintypes.MSG.from_address(int(message))
            except (TypeError, ValueError):
                return False, 0
            if msg.message == WM_HOTKEY:
                cb = self._callbacks.get(int(msg.wParam))
                if cb is not None:
                    cb()
                    return True, 0
        return False, 0
