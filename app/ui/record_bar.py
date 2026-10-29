"""录屏时的悬浮控制条。"""
from __future__ import annotations

from PyQt6.QtCore import QPoint, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QGuiApplication, QMouseEvent, QPainter
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QWidget

from ..record.recorder import format_duration
from ..theme import ACCENT, BG_CARD, BORDER, TEXT, TEXT_DIM


class _Dot(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(12, 12)
        self._on = True
        self._timer = QTimer(self)
        self._timer.setInterval(650)
        self._timer.timeout.connect(self._blink)
        self._timer.start()

    def _blink(self) -> None:
        self._on = not self._on
        self.update()

    def set_paused(self, paused: bool) -> None:
        if paused:
            self._timer.stop()
            self._on = False
        else:
            self._timer.start()
            self._on = True
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        color = QColor(ACCENT if self._on else "#6f4433")
        p.setBrush(color)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(1, 1, 10, 10)


class RecordBar(QWidget):
    pause_clicked = pyqtSignal()
    stop_clicked = pyqtSignal()
    cancel_clicked = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._drag: QPoint | None = None
        self._state = "recording"

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        card = QFrame()
        card.setObjectName("RecBar")
        card.setStyleSheet(
            f"""
            QFrame#RecBar {{
                background: rgba(38,33,29,240);
                border: 1px solid {BORDER};
                border-radius: 24px;
            }}
            """
        )
        outer.addWidget(card)
        row = QHBoxLayout(card)
        row.setContentsMargins(16, 8, 10, 8)
        row.setSpacing(10)

        self._dot = _Dot()
        row.addWidget(self._dot)
        self._time = QLabel("00:00")
        self._time.setStyleSheet(
            f"color:{TEXT};font-size:15px;font-weight:600;font-family:Consolas,monospace;"
        )
        row.addWidget(self._time)
        self._hint = QLabel("录制中")
        self._hint.setStyleSheet(f"color:{TEXT_DIM};font-size:12px;")
        row.addWidget(self._hint)

        self._pause_btn = QPushButton("暂停")
        self._pause_btn.setObjectName("Tool")
        self._pause_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pause_btn.clicked.connect(self.pause_clicked.emit)
        row.addWidget(self._pause_btn)

        stop_btn = QPushButton("停止")
        stop_btn.setObjectName("Primary")
        stop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        stop_btn.clicked.connect(self.stop_clicked.emit)
        row.addWidget(stop_btn)

        close_btn = QPushButton("×")
        close_btn.setObjectName("Tool")
        close_btn.setFixedWidth(26)
        close_btn.setToolTip("放弃本次录制")
        close_btn.clicked.connect(self.cancel_clicked.emit)
        row.addWidget(close_btn)

        self.adjustSize()
        self._place()

    def _place(self) -> None:
        screen = QGuiApplication.screenAt(QGuiApplication.primaryScreen().geometry().center())
        avail = (screen or QGuiApplication.primaryScreen()).availableGeometry()
        self.adjustSize()
        x = avail.center().x() - self.width() // 2
        y = avail.bottom() - self.height() - 56
        self.move(max(avail.left() + 8, x), max(avail.top() + 8, y))

    def set_elapsed(self, seconds: int) -> None:
        self._time.setText(format_duration(seconds))

    def set_state(self, state: str) -> None:
        self._state = state
        if state in ("pausing", "paused"):
            self._dot.set_paused(True)
            self._hint.setText("已暂停")
            self._pause_btn.setText("继续")
        elif state == "stopping":
            self._dot.set_paused(True)
            self._hint.setText("正在保存…")
            self._pause_btn.setEnabled(False)
        else:
            self._dot.set_paused(False)
            self._hint.setText("录制中")
            self._pause_btn.setText("暂停")
            self._pause_btn.setEnabled(True)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._drag is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._drag = None
        super().mouseReleaseEvent(event)
