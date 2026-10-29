"""录制区域指示框。

- 始终置顶显示，让用户随时看到正在录哪一块
- 鼠标穿透，不会挡住点击
- 外扩 3 像素绘制边框，边框落在录制区域之外，不会被录进视频
- 尽量使用 WDA_EXCLUDEFROMCAPTURE 进一步确保不出现在截图/录制里
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes

from PyQt6.QtCore import QPointF, QRect, QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from ..theme import ACCENT

BORDER = 3
PAUSE_COLOR = "#ffd93d"

GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_NOACTIVATE = 0x08000000
WDA_EXCLUDEFROMCAPTURE = 0x00000011


class RecordFrame(QWidget):
    def __init__(self, rect: QRect) -> None:
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._paused = False
        self.setGeometry(rect.adjusted(-BORDER, -BORDER, BORDER, BORDER))

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._apply_win32()

    def _apply_win32(self) -> None:
        try:
            user32 = ctypes.windll.user32
            hwnd = wintypes.HWND(int(self.winId()))
            ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE)
            try:
                user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)
            except Exception:  # noqa: BLE001
                pass
        except Exception:  # noqa: BLE001
            pass

    def set_paused(self, paused: bool) -> None:
        if self._paused != paused:
            self._paused = paused
            self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        color = QColor(PAUSE_COLOR if self._paused else ACCENT)
        rect = QRectF(self.rect())
        half = BORDER / 2

        p.setPen(QPen(color, BORDER))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(rect.adjusted(half, half, -half, -half))

        # 四角加长，增强可辨识度（仍位于录制区域之外）
        pen = QPen(color, BORDER)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        p.setPen(pen)
        length = 26.0
        left, top = half, half
        right, bottom = rect.width() - half, rect.height() - half
        for cx, cy, dx, dy in (
            (left, top, 1, 1),
            (right, top, -1, 1),
            (left, bottom, 1, -1),
            (right, bottom, -1, -1),
        ):
            p.drawLine(QPointF(cx, cy), QPointF(cx + dx * length, cy))
            p.drawLine(QPointF(cx, cy), QPointF(cx, cy + dy * length))
