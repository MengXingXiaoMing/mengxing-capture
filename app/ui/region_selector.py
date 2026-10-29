"""区域选择遮罩（录屏取景用）。"""
from __future__ import annotations

from PyQt6.QtCore import QPoint, QRect, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QKeyEvent, QMouseEvent, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QWidget

from ..capture.screen import grab_virtual
from ..theme import ACCENT, TEXT
from .winutil import force_topmost


class RegionSelector(QWidget):
    selected = pyqtSignal(QRect)
    cancelled = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self._shot = QPixmap()
        self._union = QRect()
        self._sel = QRect()
        self._origin: QPoint | None = None
        self._scale = 1.0

    def begin(self) -> None:
        self._shot, self._union = grab_virtual()
        if self._shot.isNull():
            self.cancelled.emit()
            self.close()
            return
        self._scale = self._shot.width() / max(1, self._union.width())
        self.setGeometry(self._union)
        self.show()
        force_topmost(self)
        self.setFocus()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        p.drawPixmap(self.rect(), self._shot)
        p.fillRect(self.rect(), QColor(0, 0, 0, 120))
        if self._sel.width() > 1:
            src = QRectF(
                (self._sel.x() - self._union.x()) * self._scale,
                (self._sel.y() - self._union.y()) * self._scale,
                self._sel.width() * self._scale,
                self._sel.height() * self._scale,
            )
            p.drawPixmap(QRectF(self._sel), self._shot, src)
            p.setPen(QPen(QColor(ACCENT), 1.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(self._sel.adjusted(1, 1, -1, -1))
            text = f"{self._sel.width()} × {self._sel.height()}  ·  松开开始录制"
            p.setFont(QFont("Microsoft YaHei UI", 9))
            metrics = p.fontMetrics()
            w = metrics.horizontalAdvance(text) + 18
            h = metrics.height() + 10
            x = self._sel.left()
            y = self._sel.top() - h - 8
            if y < 4:
                y = self._sel.top() + 8
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 190))
            p.drawRoundedRect(QRectF(x, y, w, h), 6, 6)
            p.setPen(QColor(TEXT))
            p.drawText(QRectF(x, y, w, h), Qt.AlignmentFlag.AlignCenter, text)
        else:
            p.setPen(QColor(TEXT))
            p.setFont(QFont("Microsoft YaHei UI", 12))
            p.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                "\n拖动鼠标框选录制区域  ·  Esc 取消",
            )

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.RightButton:
            self._cancel()
            return
        self._origin = event.position().toPoint()
        self._sel = QRect(self._origin, QSize())
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._origin is not None:
            self._sel = QRect(self._origin, event.position().toPoint()).normalized()
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._origin = None
        if self._sel.width() < 24 or self._sel.height() < 24:
            self._sel = QRect()
            self.update()
            return
        self.selected.emit(self._sel)
        self.close()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self._cancel()
            return
        super().keyPressEvent(event)

    def _cancel(self) -> None:
        self.cancelled.emit()
        self.close()
