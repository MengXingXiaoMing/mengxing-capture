"""复用的小部件。"""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class Card(QFrame):
    def __init__(self, title: str = "", subtitle: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(18, 16, 18, 16)
        self._layout.setSpacing(10)
        if title:
            head = QHBoxLayout()
            head.setSpacing(8)
            label = QLabel(title)
            label.setObjectName("SectionTitle")
            head.addWidget(label)
            if subtitle:
                sub = QLabel(subtitle)
                sub.setObjectName("Hint")
                head.addWidget(sub)
            head.addStretch(1)
            self._layout.addLayout(head)

    def body(self) -> QVBoxLayout:
        return self._layout

    def add(self, widget: QWidget) -> QWidget:
        self._layout.addWidget(widget)
        return widget

    def add_layout(self, layout) -> None:
        self._layout.addLayout(layout)


class Row(QWidget):
    """左边说明 + 中间控件 + 右侧附加控件。"""

    def __init__(self, label: str, widget: QWidget, hint: str = "", parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        text = QLabel(label)
        text.setFixedWidth(96)
        layout.addWidget(text)
        layout.addWidget(widget, 1)
        if hint:
            hint_label = QLabel(hint)
            hint_label.setObjectName("Hint")
            layout.addWidget(hint_label)


class DirPicker(QWidget):
    changed = pyqtSignal(str)

    def __init__(self, path: str = "", parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.edit = QLineEdit(path)
        layout.addWidget(self.edit, 1)
        browse = QPushButton("选择…")
        browse.clicked.connect(self._browse)
        layout.addWidget(browse)

    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "选择保存目录", self.edit.text())
        if folder:
            self.edit.setText(folder)
            self.changed.emit(folder)

    def path(self) -> Path:
        return Path(self.edit.text().strip() or ".")


class KeyCaptureEdit(QLineEdit):
    """点击后按下组合键即可录入热键。"""

    def __init__(self, sequence: str = "", parent=None) -> None:
        super().__init__(sequence, parent)
        self.setPlaceholderText("点击后按下组合键")
        self.setReadOnly(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = event.key()
        if key in (Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_Meta):
            return
        if key == Qt.Key.Key_Escape:
            self.clearFocus()
            return
        mods = event.modifiers()
        parts: list[str] = []
        if mods & Qt.KeyboardModifier.ControlModifier:
            parts.append("ctrl")
        if mods & Qt.KeyboardModifier.AltModifier:
            parts.append("alt")
        if mods & Qt.KeyboardModifier.ShiftModifier:
            parts.append("shift")
        if mods & Qt.KeyboardModifier.MetaModifier:
            parts.append("win")
        text = event.text().strip().lower()
        name = ""
        if text and text.isalnum() and len(text) == 1:
            name = text
        else:
            mapping = {
                Qt.Key.Key_F1: "f1", Qt.Key.Key_F2: "f2", Qt.Key.Key_F3: "f3",
                Qt.Key.Key_F4: "f4", Qt.Key.Key_F5: "f5", Qt.Key.Key_F6: "f6",
                Qt.Key.Key_F7: "f7", Qt.Key.Key_F8: "f8", Qt.Key.Key_F9: "f9",
                Qt.Key.Key_F10: "f10", Qt.Key.Key_F11: "f11", Qt.Key.Key_F12: "f12",
                Qt.Key.Key_Space: "space", Qt.Key.Key_Print: "print",
                Qt.Key.Key_Insert: "insert", Qt.Key.Key_Delete: "delete",
                Qt.Key.Key_Home: "home", Qt.Key.Key_End: "end",
                Qt.Key.Key_PageUp: "pageup", Qt.Key.Key_PageDown: "pagedown",
            }
            name = mapping.get(key, "")
        if not name or not parts:
            return
        self.setText("+".join(parts + [name]))
