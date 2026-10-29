"""窗口枚举（ctypes，用于「窗口截图 / 窗口录屏」选择）。"""
from __future__ import annotations

import ctypes
from ctypes import wintypes

from PyQt6.QtCore import QRect
from PyQt6.QtGui import QGuiApplication

user32 = ctypes.windll.user32
dwmapi = ctypes.windll.dwmapi

GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000
DWMWA_EXTENDED_FRAME_BOUNDS = 9

_EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


class WindowInfo:
    __slots__ = ("hwnd", "title", "rect")

    def __init__(self, hwnd: int, title: str, rect: QRect) -> None:
        self.hwnd = hwnd
        self.title = title
        self.rect = rect

    def __repr__(self) -> str:
        return f"<Window {self.title!r} {self.rect}>"


def _window_rect(hwnd: int) -> QRect | None:
    rect = wintypes.RECT()
    ok = False
    try:
        if dwmapi.DwmGetWindowAttribute(
            wintypes.HWND(hwnd),
            ctypes.c_uint(DWMWA_EXTENDED_FRAME_BOUNDS),
            ctypes.byref(rect),
            ctypes.sizeof(rect),
        ) == 0:
            ok = True
    except OSError:
        ok = False
    if not ok:
        if not user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect)):
            return None

    dpr = 1.0
    screen = QGuiApplication.primaryScreen()
    if screen:
        dpr = screen.devicePixelRatio() or 1.0
    left = int(round(rect.left / dpr))
    top = int(round(rect.top / dpr))
    width = int(round((rect.right - rect.left) / dpr))
    height = int(round((rect.bottom - rect.top) / dpr))
    if width <= 60 or height <= 60:
        return None
    return QRect(left, top, width, height)


def window_rect(hwnd: int) -> QRect | None:
    return _window_rect(hwnd)


def list_windows(exclude_pid: int | None = None) -> list[WindowInfo]:
    result: list[WindowInfo] = []
    own = ctypes.windll.kernel32.GetCurrentProcessId()

    def callback(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value.strip()
        if not title or title in ("Program Manager", "Windows 输入体验"):
            return True
        ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        if ex_style & WS_EX_TOOLWINDOW and not (ex_style & WS_EX_APPWINDOW):
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in (own, exclude_pid):
            return True
        rect = _window_rect(hwnd)
        if rect is None:
            return True
        result.append(WindowInfo(int(hwnd), title, rect))
        return True

    user32.EnumWindows(_EnumProc(callback), 0)
    result.sort(key=lambda w: (w.rect.y(), w.rect.x()))
    return result
