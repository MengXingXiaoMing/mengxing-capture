"""系统托盘。"""
from __future__ import annotations

from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon

from .icons import app_icon


class TrayIcon(QSystemTrayIcon):
    def __init__(self, controller) -> None:
        super().__init__(app_icon())
        self.controller = controller
        self.setToolTip("梦星截屏 · 录屏与离线翻译")

        menu = QMenu()
        self._capture = QAction("截图", menu)
        self._capture.triggered.connect(controller.start_capture)
        menu.addAction(self._capture)

        self._translate = QAction("截图翻译", menu)
        self._translate.triggered.connect(controller.start_translate_capture)
        menu.addAction(self._translate)

        self._record = QAction("开始录屏", menu)
        self._record.triggered.connect(controller.toggle_record)
        menu.addAction(self._record)

        self._pause = QAction("暂停录制", menu)
        self._pause.triggered.connect(controller.toggle_pause)
        self._pause.setVisible(False)
        menu.addAction(self._pause)

        menu.addSeparator()
        self._open = QAction("打开主界面", menu)
        self._open.triggered.connect(controller.show_window)
        menu.addAction(self._open)

        menu.addSeparator()
        self._quit = QAction("退出", menu)
        self._quit.triggered.connect(controller.quit)
        menu.addAction(self._quit)

        menu.aboutToShow.connect(self._sync)
        self.setContextMenu(menu)
        self._menu = menu
        self.activated.connect(self._on_activated)

    def _sync(self) -> None:
        phase = self.controller.recorder.phase
        active = self.controller.recorder.active
        self._record.setText("停止录屏" if active else "开始录屏")
        self._pause.setVisible(active)
        if phase == "paused":
            self._pause.setText("继续录制")
        elif phase == "recording":
            self._pause.setText("暂停录制")
        else:
            self._pause.setText("暂停录制")
        self._pause.setEnabled(phase in ("recording", "paused"))

    def _on_activated(self, reason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.DoubleClick,
            QSystemTrayIcon.ActivationReason.Trigger,
        ):
            self.controller.show_window()
