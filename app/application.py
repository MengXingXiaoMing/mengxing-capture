"""应用控制器：把热键、托盘、截图、录屏、翻译串起来。"""
from __future__ import annotations

from PyQt6.QtCore import QObject, QRect, QTimer
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from .config import CONFIG
from .hotkeys import HotkeyError, HotkeyManager
from .record.recorder import RecordError, Recorder
from .ui.capture_overlay import ScreenshotController
from .ui.main_window import MainWindow
from .ui.record_bar import RecordBar
from .ui.record_frame import RecordFrame
from .ui.region_selector import RegionSelector
from .ui.tray import TrayIcon
from .ui.winutil import DarkTitleBarFilter, bring_to_front, force_topmost

HOTKEY_LABELS = {
    "capture": "截图",
    "translate": "截图翻译",
    "record": "开始/停止录屏",
    "record_pause": "暂停/继续录屏",
    "stop": "停止录屏",
}


class AppController(QObject):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.window = MainWindow(self)
        self._dark_titlebar = DarkTitleBarFilter(app)
        app.installEventFilter(self._dark_titlebar)
        self.recorder = Recorder(self)
        self.record_bar = RecordBar()
        self.screenshots = ScreenshotController(
            on_translate=self._open_translate,
            on_captured=self._on_captured,
            on_record=self._on_overlay_record,
        )
        self.screenshots.on_closed = self._on_overlay_closed
        self.tray = TrayIcon(self)
        self.hotkeys = HotkeyManager(app)
        self._selector: RegionSelector | None = None
        self._record_frame: RecordFrame | None = None
        self._restore_window = False
        self._restore_bar = False
        self._restore_after_record = False

        self.recorder.state_changed.connect(self._on_record_state)
        self.recorder.failed.connect(self._on_record_failed)
        self.recorder.finished.connect(self._on_record_finished)
        self.recorder.tick.connect(self.record_bar.set_elapsed)

        self.record_bar.pause_clicked.connect(self.toggle_pause)
        self.record_bar.stop_clicked.connect(self.stop_record)
        self.record_bar.cancel_clicked.connect(self.cancel_record)

        self.hotkey_failures = self.reload_hotkeys()
        if self.tray_available():
            self.tray.show()

    # ------------------------------------------------------------------ 窗口
    def show_window(self) -> None:
        if self.window.isMinimized():
            self.window.showNormal()
        self.window.show()
        self.window.refresh_recent()
        bring_to_front(self.window)

    def tray_available(self) -> bool:
        return QSystemTrayIcon.isSystemTrayAvailable()

    def notify(self, message: str, timeout: int = 3200) -> None:
        if self.tray_available() and self.tray.isVisible():
            self.tray.showMessage("梦星截屏", message, QSystemTrayIcon.MessageIcon.Information, timeout)
        else:
            self.window.statusBar().showMessage(message, timeout)

    def reload_hotkeys(self) -> list[str]:
        self.hotkeys.unregister_all()
        failures: list[str] = []
        mapping = {
            "capture": self.start_capture,
            "translate": self.start_translate_capture,
            "record": self.toggle_record,
            "record_pause": self.toggle_pause,
            "stop": self.stop_record,
        }
        for key, callback in mapping.items():
            sequence = str(CONFIG.get(f"hotkeys.{key}", "") or "")
            if not sequence:
                continue
            try:
                self.hotkeys.register(key, sequence, self._defer(callback))
            except HotkeyError as exc:
                failures.append(f"{HOTKEY_LABELS.get(key, key)}（{sequence}）：{exc}")
        return failures

    @staticmethod
    def _defer(callback):
        def wrapped() -> None:
            # 全局热键回调发生在原生消息处理里，延迟到下一轮事件循环再弹窗
            QTimer.singleShot(0, callback)

        return wrapped

    # ------------------------------------------------------------------ 截图
    def start_capture(self) -> None:
        self._prepare_overlay()
        self.screenshots.start(hide_widget=self.window, translate=False)

    def start_translate_capture(self) -> None:
        self._prepare_overlay()
        self.screenshots.start(hide_widget=self.window, translate=True)

    def _prepare_overlay(self) -> None:
        self._restore_window = self.window.isVisible()
        self._restore_bar = self.record_bar.isVisible()
        if self._restore_bar:
            self.record_bar.hide()

    def _on_overlay_closed(self) -> None:
        if self._restore_bar and self.recorder.active:
            self.record_bar.show()
        self._restore_bar = False
        if self._restore_window and not self.window.isVisible():
            self.window.show()
        self._restore_window = False

    def _on_captured(self, path: str) -> None:
        self.window.refresh_recent()
        if path:
            self.notify("截图已保存：" + path)
        else:
            self.notify("截图已复制到剪贴板。")

    def _on_overlay_record(self, rect) -> None:
        if self.recorder.active:
            self.notify("正在录制中，请先停止当前录制。")
            return
        self._restore_after_record = self._restore_window
        self._restore_window = False
        self._restore_bar = False
        bounds = (rect.x(), rect.y(), rect.width(), rect.height())
        QTimer.singleShot(260, lambda: self._begin_record(bounds, target="region"))

    def _open_translate(self, pixmap: QPixmap) -> None:
        """截图翻译：把文字识别到主界面输入框并直接翻译，不再弹次级窗口。"""
        self.show_window()
        self.window.show_page(0)
        self.window.translate_page.translate_from_image(pixmap.toImage())

    # ------------------------------------------------------------------ 录屏
    def start_record(self) -> None:
        if self.recorder.active:
            return
        page = self.window.record_page
        page.persist()
        self._restore_after_record = self.window.isVisible()
        target = str(CONFIG.get("record.target", "region"))
        if target == "window":
            rect = page.selected_window_rect()
            if rect is None:
                self.notify("请先在「录屏」页面选择目标窗口。")
                self.show_window()
                self.window.show_page(1)
                return
            self._begin_record(rect)
        elif target == "fullscreen":
            self._begin_record(None)
        else:
            self._restore_window = self.window.isVisible()
            self.window.hide()
            QTimer.singleShot(160, self._pick_region)

    def request_record(self) -> None:
        self.start_record()

    def _pick_region(self) -> None:
        self._selector = RegionSelector()
        self._selector.selected.connect(self._on_region_selected)
        self._selector.cancelled.connect(self._on_region_cancelled)
        self._selector.begin()

    def _on_region_selected(self, rect) -> None:
        self._selector = None
        self._begin_record((rect.x(), rect.y(), rect.width(), rect.height()))

    def _on_region_cancelled(self) -> None:
        self._selector = None
        if self._restore_window:
            self.window.show()
        self._restore_window = False

    def _begin_record(self, rect, target: str | None = None) -> None:
        try:
            options = self.window.record_page.build_options(rect)
            if target:
                options.target = target
            self.recorder.start(options)
        except RecordError as exc:
            self.window.show()
            QMessageBox.warning(self.window, "无法开始录制", str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            self.window.show()
            QMessageBox.warning(self.window, "无法开始录制", str(exc))
            return
        self.window.hide()
        self.record_bar.set_elapsed(0)
        self.record_bar.set_state("recording")
        self.record_bar.show()
        force_topmost(self.record_bar)
        if rect is not None:
            self._show_record_frame(rect)

    def _show_record_frame(self, rect) -> None:
        self._close_record_frame()
        try:
            frame = RecordFrame(QRect(int(rect[0]), int(rect[1]), int(rect[2]), int(rect[3])))
            frame.show()
            self._record_frame = frame
        except Exception:  # noqa: BLE001
            self._record_frame = None

    def _close_record_frame(self) -> None:
        if self._record_frame is not None:
            self._record_frame.close()
            self._record_frame.deleteLater()
            self._record_frame = None

    def toggle_record(self) -> None:
        if self.recorder.active:
            self.stop_record()
        else:
            self.start_record()

    def toggle_pause(self) -> None:
        phase = self.recorder.phase
        if phase == "recording":
            self.recorder.pause()
        elif phase == "paused":
            self.recorder.resume()

    def stop_record(self) -> None:
        if self.recorder.active:
            self.recorder.stop()

    def cancel_record(self) -> None:
        if not self.recorder.active:
            return
        answer = QMessageBox.question(
            None, "放弃录制", "确定要放弃本次录制吗？已录内容不会保存。"
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.recorder.cancel()
            self.record_bar.hide()
            self._close_record_frame()
            if self._restore_after_record:
                self.show_window()
            self._restore_after_record = False

    def _on_record_state(self, state: str) -> None:
        self.record_bar.set_state(state)
        active = state in ("recording", "paused", "pausing", "stopping")
        self.window.set_recording(active)
        if self._record_frame is not None:
            self._record_frame.set_paused(state in ("paused", "pausing"))
        if state == "stopping":
            self.record_bar.set_elapsed(self.recorder.elapsed_seconds())
        if state == "idle":
            self.record_bar.hide()
            self._close_record_frame()

    def _on_record_finished(self, path: str) -> None:
        self.record_bar.hide()
        self._close_record_frame()
        self.window.set_recording(False)
        self.window.refresh_recent()
        self.notify("录屏已保存：" + path, 5000)
        if self._restore_after_record:
            self.show_window()
        self._restore_after_record = False

    def _on_record_failed(self, message: str) -> None:
        self.record_bar.hide()
        self._close_record_frame()
        self.window.set_recording(False)
        self.window.show()
        self._restore_after_record = False
        QMessageBox.warning(self.window, "录制失败", message)

    # ------------------------------------------------------------------ 退出
    def quit(self) -> None:
        if self.recorder.active:
            self.recorder.stop()
        self._close_record_frame()
        self.hotkeys.unregister_all()
        self.tray.hide()
        try:
            self.window.translate_page.shutdown()
            self.window.record_page.shutdown()
            gif_task = getattr(self.window, "_gif_task", None)
            if gif_task is not None and gif_task.isRunning():
                gif_task.wait(5000)
            env_task = getattr(self.window, "_env_task", None)
            if env_task is not None and env_task.isRunning():
                if not env_task.wait(4000):
                    env_task.terminate()
                    env_task.wait(1000)
        except Exception:  # noqa: BLE001
            pass
        self.app.quit()
