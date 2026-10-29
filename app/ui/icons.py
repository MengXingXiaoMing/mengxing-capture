"""程序图标（运行时绘制，不依赖外部图片资源）。"""
from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap

from ..paths import CACHE_DIR
from ..theme import ACCENT, BG_CARD, TEXT

DARK = "#23180f"


def checkmark_path() -> str:
    """生成复选框的白色对勾图片，供 QSS 引用（QSS 无法直接画对勾）。"""
    path = CACHE_DIR / "check.png"
    if not path.exists():
        pm = QPixmap(36, 36)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(QColor("#23180f"), 5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.drawPolyline([QPointF(8, 19), QPointF(15, 26), QPointF(28, 10)])
        p.end()
        pm.save(str(path))
    return path.as_posix()


def glyph_icon(name: str, color: str = TEXT) -> QIcon:
    """按名字画一个线性图标（64×64 绘制，交给 Qt 缩放）。"""
    size = 64
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(QColor(color), size * 0.075)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    center = QPointF(size / 2, size / 2)

    if name == "translate":
        radius = size * 0.3
        p.drawEllipse(center, radius, radius)
        p.drawEllipse(center, radius * 0.45, radius)
        p.drawLine(QPointF(center.x() - radius, center.y()), QPointF(center.x() + radius, center.y()))
    elif name == "record":
        p.drawRoundedRect(QRectF(size * 0.15, size * 0.2, size * 0.7, size * 0.46), size * 0.1, size * 0.1)
        p.drawLine(QPointF(size * 0.38, size * 0.8), QPointF(size * 0.62, size * 0.8))
        p.drawLine(QPointF(size * 0.5, size * 0.66), QPointF(size * 0.5, size * 0.8))
        p.setBrush(QColor(color))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(center, size * 0.11, size * 0.11)
    elif name == "settings":
        # 三条滑杆，比齿轮在小尺寸下更容易辨认
        for ratio, knob in ((0.3, 0.62), (0.5, 0.38), (0.7, 0.66)):
            y = size * ratio
            p.drawLine(QPointF(size * 0.22, y), QPointF(size * 0.78, y))
            p.setBrush(QColor(color))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(size * knob, y), size * 0.075, size * 0.075)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
    elif name == "capture":
        margin, length = size * 0.2, size * 0.17
        for x, y, dx, dy in (
            (margin, margin, 1, 1),
            (size - margin, margin, -1, 1),
            (margin, size - margin, 1, -1),
            (size - margin, size - margin, -1, -1),
        ):
            p.drawLine(QPointF(x, y), QPointF(x + dx * length, y))
            p.drawLine(QPointF(x, y), QPointF(x, y + dy * length))
    elif name == "clear":
        p.drawLine(QPointF(size * 0.3, size * 0.3), QPointF(size * 0.7, size * 0.7))
        p.drawLine(QPointF(size * 0.7, size * 0.3), QPointF(size * 0.3, size * 0.7))
    elif name == "copy":
        p.drawRoundedRect(QRectF(size * 0.33, size * 0.33, size * 0.38, size * 0.38), size * 0.06, size * 0.06)
        p.drawRoundedRect(QRectF(size * 0.2, size * 0.2, size * 0.38, size * 0.38), size * 0.06, size * 0.06)
    elif name == "arrow":
        p.drawLine(QPointF(size * 0.26, size * 0.5), QPointF(size * 0.74, size * 0.5))
        p.drawLine(QPointF(size * 0.56, size * 0.32), QPointF(size * 0.74, size * 0.5))
        p.drawLine(QPointF(size * 0.56, size * 0.68), QPointF(size * 0.74, size * 0.5))

    p.end()
    return QIcon(pm)


def app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        pm = QPixmap(size, size)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        radius = size * 0.22
        p.setBrush(QColor(BG_CARD))
        p.setPen(QPen(QColor("#4a3d32"), max(1.0, size * 0.025)))
        p.drawRoundedRect(QRectF(0.5, 0.5, size - 1, size - 1), radius, radius)

        margin = size * 0.24
        length = size * 0.16
        pen = QPen(QColor(ACCENT), max(1.4, size * 0.055))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        left, top = margin, margin * 0.92
        right, bottom = size - margin, size - margin * 0.92
        for x, y, dx, dy in (
            (left, top, 1, 1),
            (right, top, -1, 1),
            (left, bottom, 1, -1),
            (right, bottom, -1, -1),
        ):
            p.drawLine(
                QRectF(x, y, 0, 0).topLeft(),
                QRectF(x + dx * length, y, 0, 0).topLeft(),
            )
            p.drawLine(
                QRectF(x, y, 0, 0).topLeft(),
                QRectF(x, y + dy * length, 0, 0).topLeft(),
            )

        dot = size * 0.115
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(ACCENT))
        p.drawEllipse(QRectF(size / 2 - dot, size / 2 - dot, dot * 2, dot * 2))
        p.end()
        icon.addPixmap(pm)
    return icon
