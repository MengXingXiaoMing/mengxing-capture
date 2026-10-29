"""全屏截图遮罩：框选 + 标注编辑二合一。

设计说明：
- 所有标注坐标都使用「相对选区左上角的逻辑坐标」，导出时按 DPI 缩放绘制，
  保证在 125%/150% 缩放的屏幕上标注位置仍然准确。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
)
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QPushButton,
    QWidget,
)

from ..capture.screen import crop, grab_virtual, save_pixmap, to_clipboard
from ..config import CONFIG
from ..theme import ACCENT, BORDER, TEXT
from .winutil import force_topmost

TOOL_SELECT = "select"
TOOL_RECT = "rect"
TOOL_ELLIPSE = "ellipse"
TOOL_ARROW = "arrow"
TOOL_PEN = "pen"
TOOL_HIGHLIGHT = "highlight"
TOOL_MOSAIC = "mosaic"
TOOL_TEXT = "text"
TOOL_NUMBER = "number"

HANDLE_SIZE = 8
HANDLE_HIT = 14
MIN_SELECTION = 32

_RESIZE_CURSORS = {
    0: Qt.CursorShape.SizeFDiagCursor,
    1: Qt.CursorShape.SizeVerCursor,
    2: Qt.CursorShape.SizeBDiagCursor,
    3: Qt.CursorShape.SizeHorCursor,
    4: Qt.CursorShape.SizeHorCursor,
    5: Qt.CursorShape.SizeBDiagCursor,
    6: Qt.CursorShape.SizeVerCursor,
    7: Qt.CursorShape.SizeFDiagCursor,
}

PALETTE = [
    ("#ff4d4f", "红"),
    ("#ff9c2e", "橙"),
    ("#ffd93d", "黄"),
    ("#4ecb71", "绿"),
    ("#4aa8ff", "蓝"),
    ("#ffffff", "白"),
]


@dataclass
class Annotation:
    tool: str
    rect: QRectF = field(default_factory=QRectF)
    points: list[QPointF] = field(default_factory=list)
    text: str = ""
    color: QColor = field(default_factory=lambda: QColor("#ff4d4f"))
    width: int = 3
    number: int = 0
    font_size: int = 16


def _pixelate(source: QPixmap, target: QRectF, scale: float, block: int = 12) -> QPixmap:
    """从原图取出区域并做马赛克。target 为逻辑坐标，scale 为像素/逻辑像素比。"""
    x = int(target.x() * scale)
    y = int(target.y() * scale)
    w = max(1, int(target.width() * scale))
    h = max(1, int(target.height() * scale))
    x = max(0, min(x, source.width() - 1))
    y = max(0, min(y, source.height() - 1))
    w = min(w, source.width() - x)
    h = min(h, source.height() - y)
    piece = source.copy(x, y, w, h)
    small_w = max(1, w // block)
    small_h = max(1, h // block)
    small = piece.scaled(
        small_w, small_h, Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    return small.scaled(
        w, h, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.FastTransformation
    )


class CaptureOverlay(QWidget):
    translate_requested = pyqtSignal(QPixmap)
    record_requested = pyqtSignal(QRect)
    closed = pyqtSignal()
    captured = pyqtSignal(str)  # 保存后的文件路径（为空表示仅复制）

    def __init__(self, auto_translate: bool = False) -> None:
        super().__init__()
        self._auto_translate = auto_translate
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Window
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.CrossCursor)

        self._shot = QPixmap()
        self._union = QRect()
        self._dpr = 1.0
        self._sel = QRect()
        self._origin: QPoint | None = None
        self._dragging = False
        self._mode = "select"          # select / edit
        self._tool = TOOL_SELECT
        self._drag_mode: str | None = None      # move / resize
        self._resize_handle = -1
        self._sel_before = QRect()
        self._press_pos = QPoint()
        self._color = QColor(PALETTE[0][0])
        self._line_width = 3
        self._items: list[Annotation] = []
        self._active: Annotation | None = None
        self._number_seq = 0
        self._crop_pixmap = QPixmap()
        self._toolbar: QWidget | None = None
        self._buttons: dict[str, QPushButton] = {}
        self._src_scale = 1.0

    # ------------------------------------------------------------------ 启动
    def begin(self) -> None:
        self._shot, self._union = grab_virtual()
        if self._shot.isNull() or self._union.isEmpty():
            self.close()
            return
        self._dpr = self._shot.devicePixelRatio() or 1.0
        self._src_scale = self._shot.width() / max(1, self._union.width())
        self.setGeometry(self._union)
        self.show()
        force_topmost(self)
        self.setFocus()

    # ------------------------------------------------------------------ 绘制
    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        if self._shot.isNull():
            return
        p.drawPixmap(self.rect(), self._shot)

        if self._mode == "select":
            p.fillRect(self.rect(), QColor(0, 0, 0, 118))
            if not self._sel.isNull() and self._sel.width() > 1:
                self._draw_region(p, self._sel)
                self._draw_size_badge(p, self._sel)
            else:
                p.setPen(QColor(TEXT))
                p.setFont(QFont("Microsoft YaHei UI", 12))
                p.drawText(
                    self.rect().adjusted(0, 60, 0, 0),
                    Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                    "拖动鼠标框选区域  ·  双击截取全屏  ·  Esc / 右键取消",
                )
        else:
            p.fillRect(self.rect(), QColor(0, 0, 0, 150))
            if not self._crop_pixmap.isNull():
                p.drawPixmap(self._sel, self._crop_pixmap)
            if not self._sel.isNull():
                p.save()
                p.translate(self._sel.topLeft())
                p.setClipRect(QRect(0, 0, self._sel.width(), self._sel.height()))
                for item in self._items:
                    self._draw_annotation(p, item, self._crop_pixmap, self._dpr)
                if self._active is not None:
                    self._draw_annotation(p, self._active, self._crop_pixmap, self._dpr)
                p.restore()
                self._draw_selection_frame(p, self._sel)
                self._draw_size_badge(p, self._sel, inside=True)

    def _draw_selection_frame(self, p: QPainter, rect: QRect) -> None:
        """选框一直可见：橙色描边 + 八个可拖拽控制点。"""
        p.setPen(QPen(QColor(ACCENT), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(rect.adjusted(0, 0, -1, -1))
        p.setPen(QPen(QColor(ACCENT), 1.5))
        p.setBrush(QColor("#ffffff"))
        half = HANDLE_SIZE / 2
        for point in self._handle_points():
            p.drawRect(
                QRectF(point.x() - half, point.y() - half, HANDLE_SIZE, HANDLE_SIZE)
            )

    def _draw_region(self, p: QPainter, rect: QRect) -> None:
        src = QRectF(
            (rect.x() - self._union.x()) * self._src_scale,
            (rect.y() - self._union.y()) * self._src_scale,
            rect.width() * self._src_scale,
            rect.height() * self._src_scale,
        )
        p.drawPixmap(QRectF(rect), self._shot, src)
        p.setPen(QPen(QColor(ACCENT), 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(rect.adjusted(1, 1, -1, -1))
        # 四角高亮
        p.setPen(QPen(QColor(ACCENT), 3))
        n = 14
        for cx, cy, dx, dy in (
            (rect.left(), rect.top(), 1, 1),
            (rect.right(), rect.top(), -1, 1),
            (rect.left(), rect.bottom(), 1, -1),
            (rect.right(), rect.bottom(), -1, -1),
        ):
            p.drawLine(QPoint(cx, cy), QPoint(cx + dx * n, cy))
            p.drawLine(QPoint(cx, cy), QPoint(cx, cy + dy * n))

    def _draw_size_badge(self, p: QPainter, rect: QRect, inside: bool = False) -> None:
        text = f"{int(rect.width() * self._dpr)} × {int(rect.height() * self._dpr)}"
        font = QFont("Microsoft YaHei UI", 9)
        p.setFont(font)
        metrics = p.fontMetrics()
        w = metrics.horizontalAdvance(text) + 16
        h = metrics.height() + 8
        if inside:
            x = rect.left() + 8
            y = rect.top() + 8
        else:
            x = rect.left()
            y = rect.top() - h - 6
            if y < 4:
                y = rect.top() + 6
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 180))
        p.drawRoundedRect(QRectF(x, y, w, h), 5, 5)
        p.setPen(QColor(TEXT))
        p.drawText(QRectF(x, y, w, h), Qt.AlignmentFlag.AlignCenter, text)

    # ------------------------------------------------------------------ 选框调整
    def _handle_points(self) -> list[QPoint]:
        r = self._sel
        xs = (r.left(), r.center().x(), r.right())
        ys = (r.top(), r.center().y(), r.bottom())
        points: list[QPoint] = []
        for iy, y in enumerate(ys):
            for ix, x in enumerate(xs):
                if ix == 1 and iy == 1:
                    continue
                points.append(QPoint(x, y))
        return points

    def _hit_handle(self, pos: QPoint) -> int | None:
        half = HANDLE_HIT // 2
        for index, point in enumerate(self._handle_points()):
            if QRect(point.x() - half, point.y() - half, HANDLE_HIT, HANDLE_HIT).contains(pos):
                return index
        return None

    def _compute_resize(self, pos: QPoint) -> QRect:
        r = QRect(self._sel_before)
        index = self._resize_handle
        if index in (0, 3, 5):
            r.setLeft(min(pos.x(), r.right() - MIN_SELECTION + 1))
        elif index in (2, 4, 7):
            r.setRight(max(pos.x(), r.left() + MIN_SELECTION - 1))
        if index in (0, 1, 2):
            r.setTop(min(pos.y(), r.bottom() - MIN_SELECTION + 1))
        elif index in (5, 6, 7):
            r.setBottom(max(pos.y(), r.top() + MIN_SELECTION - 1))
        r.setLeft(max(0, r.left()))
        r.setTop(max(0, r.top()))
        r.setRight(min(self.width() - 1, r.right()))
        r.setBottom(min(self.height() - 1, r.bottom()))
        return r.normalized()

    def _clamp_rect(self, rect: QRect) -> QRect:
        r = QRect(rect)
        if r.left() < 0:
            r.moveLeft(0)
        if r.top() < 0:
            r.moveTop(0)
        if r.right() > self.width() - 1:
            r.moveRight(self.width() - 1)
        if r.bottom() > self.height() - 1:
            r.moveBottom(self.height() - 1)
        return r

    def _shift_items(self, dx: float, dy: float) -> None:
        for item in self._items:
            item.rect = item.rect.translated(dx, dy)
            if item.points:
                item.points = [point + QPointF(dx, dy) for point in item.points]

    def _update_cursor(self, pos: QPoint | None = None) -> None:
        if self._mode != "edit" or self._tool != TOOL_SELECT:
            self.setCursor(Qt.CursorShape.CrossCursor)
            return
        if pos is not None:
            handle = self._hit_handle(pos)
            if handle is not None:
                self.setCursor(_RESIZE_CURSORS.get(handle, Qt.CursorShape.SizeAllCursor))
                return
            if self._sel.contains(pos):
                self.setCursor(Qt.CursorShape.SizeAllCursor)
                return
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def _restart_selection(self, pos: QPoint) -> None:
        self._mode = "select"
        self._items.clear()
        self._active = None
        self._crop_pixmap = QPixmap()
        self._number_seq = 0
        self._drag_mode = None
        self._origin = pos
        self._dragging = True
        self._sel = QRect(pos, QSize())
        if self._toolbar is not None:
            self._toolbar.hide()
        self._update_cursor()
        self.update()

    # ------------------------------------------------------------------ 标注绘制
    def _draw_annotation(
        self, p: QPainter, item: Annotation, source: QPixmap, scale: float
    ) -> None:
        tool = item.tool
        if tool == TOOL_MOSAIC:
            r = item.rect.normalized()
            if r.width() < 2 or r.height() < 2:
                return
            mosaic = _pixelate(source, r, scale)
            if not mosaic.isNull():
                p.drawPixmap(r, mosaic, QRectF(0, 0, mosaic.width(), mosaic.height()))
            return

        pen = QPen(item.color, item.width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        if tool == TOOL_HIGHLIGHT:
            c = QColor(item.color)
            c.setAlpha(110)
            pen = QPen(c, max(10, item.width * 4))
            pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)

        if tool == TOOL_RECT:
            p.drawRect(item.rect.normalized())
        elif tool == TOOL_ELLIPSE:
            p.drawEllipse(item.rect.normalized())
        elif tool == TOOL_ARROW:
            if len(item.points) >= 2:
                self._draw_arrow(p, item.points[0], item.points[1], item)
        elif tool == TOOL_PEN:
            if len(item.points) >= 2:
                path = QPainterPath(item.points[0])
                for pt in item.points[1:]:
                    path.lineTo(pt)
                p.drawPath(path)
        elif tool == TOOL_HIGHLIGHT:
            if len(item.points) >= 2:
                path = QPainterPath(item.points[0])
                for pt in item.points[1:]:
                    path.lineTo(pt)
                p.drawPath(path)
        elif tool == TOOL_TEXT:
            self._draw_text(p, item)
        elif tool == TOOL_NUMBER:
            self._draw_number(p, item)

    def _draw_arrow(self, p: QPainter, a: QPointF, b: QPointF, item: Annotation) -> None:
        p.drawLine(a, b)
        angle = math.atan2(b.y() - a.y(), b.x() - a.x())
        size = max(11.0, item.width * 4.2)
        spread = math.radians(26)
        p1 = QPointF(
            b.x() - size * math.cos(angle - spread), b.y() - size * math.sin(angle - spread)
        )
        p2 = QPointF(
            b.x() - size * math.cos(angle + spread), b.y() - size * math.sin(angle + spread)
        )
        p.setBrush(item.color)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPolygon(QPolygonF([b, p1, p2]))
        p.setBrush(Qt.BrushStyle.NoBrush)

    def _draw_text(self, p: QPainter, item: Annotation) -> None:
        font = QFont("Microsoft YaHei UI", item.font_size)
        p.setFont(font)
        metrics = p.fontMetrics()
        lines = item.text.split("\n")
        w = max(metrics.horizontalAdvance(line) for line in lines) + 12
        h = metrics.height() * len(lines) + 8
        box = QRectF(item.rect.topLeft(), QPointF(item.rect.x() + w, item.rect.y() + h))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 150))
        p.drawRoundedRect(box, 4, 4)
        p.setPen(item.color)
        y = item.rect.y() + 4 + metrics.ascent()
        for line in lines:
            p.drawText(QPointF(item.rect.x() + 6, y), line)
            y += metrics.height()

    def _draw_number(self, p: QPainter, item: Annotation) -> None:
        radius = max(11.0, item.width * 5.0)
        center = item.rect.center()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(item.color)
        p.drawEllipse(center, radius, radius)
        p.setPen(QColor("#23180f"))
        font = QFont("Microsoft YaHei UI", int(radius * 0.95), QFont.Weight.Bold)
        p.setFont(font)
        p.drawText(
            QRectF(center.x() - radius, center.y() - radius, radius * 2, radius * 2),
            Qt.AlignmentFlag.AlignCenter,
            str(item.number),
        )

    # ------------------------------------------------------------------ 鼠标
    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.RightButton:
            if self._mode == "edit":
                self._reset_to_select()
            else:
                self.close()
            return
        pos = event.position().toPoint()
        if self._mode == "select":
            self._origin = pos
            self._sel = QRect(pos, QSize())
            self._dragging = True
            return

        # 编辑模式：选择工具用于移动选框 / 拖控制点改变大小
        if self._tool == TOOL_SELECT:
            handle = self._hit_handle(pos)
            if handle is not None:
                self._drag_mode = "resize"
                self._resize_handle = handle
                self._sel_before = QRect(self._sel)
                self._press_pos = pos
                return
            if self._sel.contains(pos):
                self._drag_mode = "move"
                self._sel_before = QRect(self._sel)
                self._press_pos = pos
                self.setCursor(Qt.CursorShape.SizeAllCursor)
                return
            self._restart_selection(pos)
            return

        if not self._sel.contains(pos):
            return
        local = QPointF(pos) - QPointF(self._sel.topLeft())
        item = Annotation(tool=self._tool, color=QColor(self._color), width=self._line_width)
        if self._tool in (TOOL_RECT, TOOL_ELLIPSE, TOOL_MOSAIC):
            item.rect = QRectF(local, local)
        elif self._tool in (TOOL_ARROW, TOOL_PEN, TOOL_HIGHLIGHT):
            item.points = [local]
        elif self._tool == TOOL_TEXT:
            self._add_text(local)
            return
        elif self._tool == TOOL_NUMBER:
            self._number_seq += 1
            item.number = self._number_seq
            item.rect = QRectF(local, local)
            self._items.append(item)
            self.update()
            return
        self._active = item
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        pos = event.position().toPoint()
        if self._mode == "select":
            if self._dragging and self._origin is not None:
                self._sel = QRect(self._origin, pos).normalized()
                self.update()
            return

        if self._drag_mode == "move":
            delta = pos - self._press_pos
            new_rect = self._clamp_rect(self._sel_before.translated(delta))
            if new_rect != self._sel:
                self._sel = new_rect
                self._crop_pixmap = crop(self._shot, self._union, self._sel)
                self._layout_toolbar()
                self.update()
            return

        if self._drag_mode == "resize":
            new_rect = self._compute_resize(pos)
            if new_rect != self._sel:
                dx = new_rect.x() - self._sel.x()
                dy = new_rect.y() - self._sel.y()
                if dx or dy:
                    self._shift_items(-dx, -dy)
                self._sel = new_rect
                self._crop_pixmap = crop(self._shot, self._union, self._sel)
                self._layout_toolbar()
                self.update()
            return

        if self._active is None:
            self._update_cursor(pos)
            return
        local = QPointF(pos) - QPointF(self._sel.topLeft())
        item = self._active
        if item.tool in (TOOL_RECT, TOOL_ELLIPSE, TOOL_MOSAIC):
            item.rect = QRectF(item.rect.topLeft(), local).normalized()
        elif item.tool in (TOOL_ARROW, TOOL_PEN, TOOL_HIGHLIGHT):
            if item.tool == TOOL_PEN:
                item.points.append(local)
            elif item.tool == TOOL_ARROW:
                item.points = [item.points[0], local]
            else:
                item.points.append(local)
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._mode == "select":
            self._dragging = False
            if self._sel.width() < 5 or self._sel.height() < 5:
                self._sel = QRect()
                self._origin = None
                self.update()
                return
            self._enter_edit()
            return

        if self._drag_mode is not None:
            self._drag_mode = None
            self._crop_pixmap = crop(self._shot, self._union, self._sel)
            self._layout_toolbar()
            self._update_cursor(event.position().toPoint())
            self.update()
            return

        if self._active is not None:
            item = self._active
            self._active = None
            if item.tool in (TOOL_RECT, TOOL_ELLIPSE, TOOL_MOSAIC):
                if item.rect.width() > 2 and item.rect.height() > 2:
                    self._items.append(item)
            elif item.tool == TOOL_ARROW:
                if len(item.points) >= 2 and (
                    abs(item.points[0].x() - item.points[1].x()) > 2
                    or abs(item.points[0].y() - item.points[1].y()) > 2
                ):
                    self._items.append(item)
            elif item.points:
                self._items.append(item)
            self.update()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._mode == "select":
            self._sel = self.rect()
            self._enter_edit()
            return
        self._copy_and_close()

    # ------------------------------------------------------------------ 状态切换
    def _enter_edit(self) -> None:
        self._mode = "edit"
        self._drag_mode = None
        self._resize_handle = -1
        self._crop_pixmap = crop(self._shot, self._union, self._sel)
        self._update_cursor()
        self._build_toolbar()
        self._layout_toolbar()
        self.update()
        if self._auto_translate:
            QTimer.singleShot(120, self._request_translate)

    def _reset_to_select(self) -> None:
        self._mode = "select"
        self._items.clear()
        self._active = None
        self._crop_pixmap = QPixmap()
        self._number_seq = 0
        self._sel = QRect()
        self._origin = None
        self._drag_mode = None
        self._resize_handle = -1
        self._update_cursor()
        if self._toolbar is not None:
            self._toolbar.hide()
        self.update()

    # ------------------------------------------------------------------ 工具栏
    def _build_toolbar(self) -> None:
        if self._toolbar is not None:
            self._toolbar.show()
            return
        bar = QWidget(self)
        bar.setObjectName("AnnoBar")
        bar.setStyleSheet(
            f"""
            QWidget#AnnoBar {{
                background: rgba(38,33,29,238);
                border: 1px solid {BORDER};
                border-radius: 10px;
            }}
            """
        )
        outer = QHBoxLayout(bar)
        outer.setContentsMargins(8, 6, 8, 6)
        outer.setSpacing(4)

        tools = [
            (TOOL_SELECT, "选择"),
            (TOOL_RECT, "矩形"),
            (TOOL_ELLIPSE, "椭圆"),
            (TOOL_ARROW, "箭头"),
            (TOOL_PEN, "画笔"),
            (TOOL_HIGHLIGHT, "高亮"),
            (TOOL_MOSAIC, "马赛克"),
            (TOOL_TEXT, "文字"),
            (TOOL_NUMBER, "序号"),
        ]
        for key, label in tools:
            btn = QPushButton(label)
            btn.setObjectName("Tool")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _=False, k=key: self._set_tool(k))
            outer.addWidget(btn)
            self._buttons[key] = btn
        self._buttons[TOOL_SELECT].setChecked(True)

        outer.addSpacing(6)
        for color_hex, name in PALETTE:
            dot = QPushButton()
            dot.setFixedSize(18, 18)
            dot.setToolTip(name)
            dot.setCursor(Qt.CursorShape.PointingHandCursor)
            dot.setStyleSheet(
                f"QPushButton{{background:{color_hex};border-radius:9px;"
                f"border:2px solid {'#ffffff' if name == '红' else 'transparent'};}}"
            )
            dot.clicked.connect(lambda _=False, c=color_hex, b=dot: self._set_color(c, b))
            outer.addWidget(dot)

        outer.addSpacing(6)
        undo = QPushButton("撤销")
        undo.setObjectName("Tool")
        undo.clicked.connect(self._undo)
        outer.addWidget(undo)

        for label, slot, obj in (
            ("重选", self._reset_to_select, "Tool"),
            ("翻译", self._request_translate, "Tool"),
            ("录屏", self._request_record, "Tool"),
        ):
            b = QPushButton(label)
            b.setObjectName(obj)
            b.clicked.connect(slot)
            outer.addWidget(b)

        copy_btn = QPushButton("复制")
        copy_btn.setObjectName("Primary")
        copy_btn.clicked.connect(self._copy_and_close)
        outer.addWidget(copy_btn)

        save_btn = QPushButton("保存")
        save_btn.setObjectName("Tool")
        save_btn.clicked.connect(self._save)
        outer.addWidget(save_btn)

        close_btn = QPushButton("×")
        close_btn.setObjectName("Tool")
        close_btn.setFixedSize(30, 30)
        close_btn.clicked.connect(self.close)
        outer.addWidget(close_btn)

        self._toolbar = bar
        bar.adjustSize()
        bar.show()
        bar.raise_()

    def _layout_toolbar(self) -> None:
        if self._toolbar is None or self._sel.isNull():
            return
        self._toolbar.adjustSize()
        size = self._toolbar.sizeHint()
        x = self._sel.left()
        y = self._sel.bottom() + 10
        if y + size.height() > self.height() - 4:
            y = self._sel.top() - size.height() - 10
        if y < 4:
            y = max(4, self._sel.center().y() - size.height() // 2)
        x = max(4, min(x, self.width() - size.width() - 4))
        self._toolbar.setGeometry(x, y, size.width(), size.height())

    def _set_tool(self, key: str) -> None:
        self._tool = key
        for k, btn in self._buttons.items():
            btn.setChecked(k == key)
        self._update_cursor()

    def _set_color(self, color_hex: str, button: QPushButton) -> None:
        self._color = QColor(color_hex)
        for b in self._toolbar.findChildren(QPushButton) if self._toolbar else []:
            if b is not button and b.width() == 18:
                b.setStyleSheet(b.styleSheet().replace("2px solid #ffffff", "2px solid transparent"))
        button.setStyleSheet(
            f"QPushButton{{background:{color_hex};border-radius:9px;border:2px solid #ffffff;}}"
        )

    def _add_text(self, pos: QPointF) -> None:
        text, ok = QInputDialog.getMultiLineText(self, "添加文字", "输入标注文字：", "")
        if ok and text.strip():
            item = Annotation(
                tool=TOOL_TEXT,
                rect=QRectF(pos, pos),
                text=text.strip(),
                color=QColor(self._color),
                font_size=max(12, self._line_width * 5),
            )
            self._items.append(item)
            self.update()

    def _undo(self) -> None:
        if self._items:
            popped = self._items.pop()
            if popped.tool == TOOL_NUMBER:
                self._number_seq = max(0, self._number_seq - 1)
            self.update()

    # ------------------------------------------------------------------ 输出
    def _render_output(self) -> QPixmap:
        if self._crop_pixmap.isNull():
            return QPixmap()
        dpr = self._dpr
        out = QPixmap(self._crop_pixmap.size())
        out.fill(Qt.GlobalColor.transparent)
        p = QPainter(out)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        p.drawPixmap(0, 0, self._crop_pixmap)
        p.scale(dpr, dpr)
        for item in self._items:
            self._draw_annotation(p, item, self._crop_pixmap, 1.0)
        p.end()
        out.setDevicePixelRatio(1.0)
        return out

    def _copy_and_close(self) -> None:
        pix = self._render_output()
        if pix.isNull():
            self.close()
            return
        to_clipboard(pix)
        self.captured.emit("")
        self.close()

    def _save(self) -> QPixmap:
        pix = self._render_output()
        if pix.isNull():
            return pix
        folder = Path(CONFIG.get("capture.save_dir", ""))
        folder.mkdir(parents=True, exist_ok=True)
        default = folder / f"截图_{datetime.now():%Y%m%d_%H%M%S}.png"
        path, _ = QFileDialog.getSaveFileName(
            self, "保存截图", str(default), "PNG 图片 (*.png);;JPEG 图片 (*.jpg)"
        )
        if path:
            if save_pixmap(pix, path):
                if CONFIG.get("capture.auto_copy", True):
                    to_clipboard(pix)
                self.captured.emit(path)
                self.close()
        return pix

    def _request_translate(self) -> None:
        pix = self._render_output()
        if pix.isNull():
            return
        self.hide()
        self.translate_requested.emit(pix)
        QTimer.singleShot(200, self.close)

    def _request_record(self) -> None:
        if self._sel.isNull():
            return
        rect = self._sel.translated(self._union.topLeft())
        self.hide()
        self.record_requested.emit(rect)
        QTimer.singleShot(200, self.close)

    # ------------------------------------------------------------------ 键盘
    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        key = event.key()
        if key == Qt.Key.Key_Escape:
            if self._mode == "edit":
                self._reset_to_select()
            else:
                self.close()
            return
        if self._mode == "edit":
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._copy_and_close()
                return
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                if key == Qt.Key.Key_C:
                    self._copy_and_close()
                    return
                if key == Qt.Key.Key_S:
                    self._save()
                    return
                if key == Qt.Key.Key_Z:
                    self._undo()
                    return
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802
        self.closed.emit()
        super().closeEvent(event)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        # 覆盖多显示器时确保窗口位于最上层
        force_topmost(self)
        self.setFocus(Qt.FocusReason.OtherFocusReason)


class ScreenshotController:
    """负责隐藏主窗口 → 延迟抓屏 → 弹出遮罩，避免把自己截进去。"""

    def __init__(self, on_translate=None, on_captured=None, on_record=None) -> None:
        self._overlay: CaptureOverlay | None = None
        self._on_translate = on_translate
        self._on_captured = on_captured
        self._on_record = on_record
        self._translate_mode = False
        self.on_closed = None

    @property
    def busy(self) -> bool:
        return self._overlay is not None

    def start(
        self, hide_widget: QWidget | None = None, delay: int = 160, translate: bool = False
    ) -> None:
        if self._overlay is not None:
            self._overlay.raise_()
            return
        self._translate_mode = translate
        if hide_widget is not None and hide_widget.isVisible():
            hide_widget.hide()
            QTimer.singleShot(delay, self._open)
        else:
            QTimer.singleShot(60, self._open)

    def _open(self) -> None:
        self._overlay = CaptureOverlay(auto_translate=self._translate_mode)
        self._overlay.closed.connect(self._on_closed)
        if self._on_translate is not None:
            self._overlay.translate_requested.connect(self._on_translate)
        if self._on_captured is not None:
            self._overlay.captured.connect(self._on_captured)
        if self._on_record is not None:
            self._overlay.record_requested.connect(self._on_record)
        self._overlay.begin()

    def _on_closed(self) -> None:
        self._overlay = None
        if self.on_closed is not None:
            self.on_closed()

    def cancel(self) -> None:
        if self._overlay is not None:
            self._overlay.close()
