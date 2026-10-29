"""Win32 窗口辅助：强制置顶 / 抢前台焦点 / 深色标题栏。

Windows 会阻止后台进程随意抢前台，这里用 AttachThreadInput 的常规做法提升成功率，
让全屏截图遮罩、录屏控制条、翻译浮层始终出现在最前面。
标题栏默认是系统白底，这里用 DWM 属性把它改成与界面一致的深色。
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes

from PyQt6.QtCore import QEvent, QObject
from PyQt6.QtWidgets import QWidget

from ..theme import BG_SOFT, BORDER, TEXT

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
dwmapi = ctypes.windll.dwmapi

HWND_TOPMOST = wintypes.HWND(-1)
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_SHOWWINDOW = 0x0040
SW_RESTORE = 9

DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_USE_IMMERSIVE_DARK_MODE_OLD = 19
DWMWA_BORDER_COLOR = 34
DWMWA_CAPTION_COLOR = 35
DWMWA_TEXT_COLOR = 36


def _colorref(color: str) -> int:
    """#rrggbb 转 Windows 的 COLORREF（0x00bbggrr）。"""
    value = color.lstrip("#")
    red, green, blue = int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
    return (blue << 16) | (green << 8) | red


def apply_dark_titlebar(widget) -> None:
    """把窗口标题栏改成深色；系统版本不支持时静默忽略。"""
    if widget is None:
        return
    try:
        hwnd = wintypes.HWND(int(widget.winId()))
    except (TypeError, ValueError, AttributeError):
        return
    try:
        enabled = ctypes.c_int(1)
        for attribute in (DWMWA_USE_IMMERSIVE_DARK_MODE, DWMWA_USE_IMMERSIVE_DARK_MODE_OLD):
            if (
                dwmapi.DwmSetWindowAttribute(
                    hwnd, attribute, ctypes.byref(enabled), ctypes.sizeof(enabled)
                )
                == 0
            ):
                break
        # 下面三项只有 Windows 11 支持，旧系统会返回错误，忽略即可
        for attribute, color in (
            (DWMWA_CAPTION_COLOR, BG_SOFT),
            (DWMWA_TEXT_COLOR, TEXT),
            (DWMWA_BORDER_COLOR, BORDER),
        ):
            value = ctypes.c_int(_colorref(color))
            dwmapi.DwmSetWindowAttribute(
                hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value)
            )
    except Exception:  # noqa: BLE001
        pass


class DarkTitleBarFilter(QObject):
    """给所有 Qt 顶层窗口（主窗口、浮层、对话框）自动套用深色标题栏。"""

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.Show and isinstance(obj, QWidget) and obj.isWindow():
            apply_dark_titlebar(obj)
        return False


def _activate(hwnd) -> None:
    """把窗口拉到最前并尽量抢到前台焦点（Windows 会限制后台进程抢焦点）。"""
    user32.BringWindowToTop(hwnd)
    foreground = user32.GetForegroundWindow()
    if foreground and int(foreground) != int(hwnd):
        fg_thread = user32.GetWindowThreadProcessId(wintypes.HWND(foreground), None)
        cur_thread = kernel32.GetCurrentThreadId()
        if fg_thread and fg_thread != cur_thread:
            user32.AttachThreadInput(cur_thread, fg_thread, True)
            user32.SetForegroundWindow(hwnd)
            user32.AttachThreadInput(cur_thread, fg_thread, False)
        else:
            user32.SetForegroundWindow(hwnd)
    user32.SetActiveWindow(hwnd)
    user32.SetFocus(hwnd)


def bring_to_front(widget) -> None:
    """把普通窗口还原并显示到前台，不改变它的置顶属性。"""
    if widget is None:
        return
    try:
        hwnd = wintypes.HWND(int(widget.winId()))
    except (TypeError, ValueError, AttributeError):
        return
    try:
        user32.ShowWindow(hwnd, SW_RESTORE)
        _activate(hwnd)
    except Exception:  # noqa: BLE001
        pass


def force_topmost(widget) -> None:
    """把 Qt 窗口提到最前并尝试激活，失败时静默忽略。"""
    if widget is None:
        return
    try:
        hwnd = wintypes.HWND(int(widget.winId()))
    except (TypeError, ValueError, AttributeError):
        return
    try:
        user32.SetWindowPos(
            hwnd, HWND_TOPMOST, 0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW,
        )
        _activate(hwnd)
    except Exception:  # noqa: BLE001
        pass
