"""屏幕捕获工具（基于 Qt，处理高 DPI 与多显示器）。"""
from __future__ import annotations

from PyQt6.QtCore import QRect, QRectF, Qt
from PyQt6.QtGui import QGuiApplication, QImage, QPainter, QPixmap


def virtual_rect() -> QRect:
    rect = QRect()
    for s in QGuiApplication.screens():
        rect = rect.united(s.geometry())
    return rect


def primary_dpr() -> float:
    screen = QGuiApplication.primaryScreen()
    return float(screen.devicePixelRatio()) if screen else 1.0


def grab_virtual() -> tuple[QPixmap, QRect]:
    """抓取整个虚拟桌面。返回 (图片, 逻辑坐标系下的桌面矩形)。"""
    screens = QGuiApplication.screens()
    union = virtual_rect()
    if union.isEmpty() or not screens:
        return QPixmap(), union
    dpr = primary_dpr()
    canvas = QPixmap(max(1, int(union.width() * dpr)), max(1, int(union.height() * dpr)))
    canvas.fill(Qt.GlobalColor.black)
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    for screen in screens:
        shot = screen.grabWindow(0)
        if shot.isNull():
            continue
        g = screen.geometry()
        target = QRectF(
            (g.x() - union.x()) * dpr,
            (g.y() - union.y()) * dpr,
            g.width() * dpr,
            g.height() * dpr,
        )
        painter.drawPixmap(target, shot, QRectF(0, 0, shot.width(), shot.height()))
    painter.end()
    canvas.setDevicePixelRatio(dpr)
    return canvas, union


def crop(pixmap: QPixmap, union: QRect, selection: QRect) -> QPixmap:
    """按逻辑坐标从整屏图里裁剪。"""
    if pixmap.isNull() or selection.isEmpty():
        return QPixmap()
    dpr = pixmap.devicePixelRatio() or 1.0
    x = int(round((selection.x() - union.x()) * dpr))
    y = int(round((selection.y() - union.y()) * dpr))
    w = max(1, int(round(selection.width() * dpr)))
    h = max(1, int(round(selection.height() * dpr)))
    x = max(0, min(x, pixmap.width() - 1))
    y = max(0, min(y, pixmap.height() - 1))
    w = min(w, pixmap.width() - x)
    h = min(h, pixmap.height() - y)
    out = pixmap.copy(x, y, w, h)
    out.setDevicePixelRatio(1.0)
    return out


def to_clipboard(pixmap: QPixmap) -> None:
    clipboard = QGuiApplication.clipboard()
    if clipboard is None:
        return
    img: QImage = pixmap.toImage()
    clipboard.setImage(img)


def save_pixmap(pixmap: QPixmap, path: str) -> bool:
    return pixmap.save(path)
