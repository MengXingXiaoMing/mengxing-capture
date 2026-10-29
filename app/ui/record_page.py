"""录屏设置页。"""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ..capture.windows import list_windows, window_rect
from ..config import CONFIG
from ..paths import find_ffmpeg
from ..record.audio import loopback_available
from ..record.devices import find_system_audio, guess_microphones, list_devices
from ..record.recorder import RecordOptions, even
from ..theme import TEXT_DIM
from .widgets import Card, DirPicker, Row

CRF_PRESETS = [("高清（文件较大）", 18), ("标准", 23), ("省空间", 28)]


class DeviceScanTask(QThread):
    done = pyqtSignal(list, list)

    def run(self) -> None:  # noqa: D401
        audio, video = list_devices()
        self.done.emit(audio, video)


class RecordPage(QWidget):
    record_requested = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._audio_devices: list[str] = []
        self._video_devices: list[str] = []
        self._scan_task: DeviceScanTask | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        head = QHBoxLayout()
        title = QLabel("录屏")
        title.setObjectName("Title")
        head.addWidget(title)
        hint = QLabel("区域 / 全屏 / 窗口 · 支持暂停续录、麦克风与系统声音")
        hint.setObjectName("Subtitle")
        head.addWidget(hint)
        head.addStretch(1)
        self.start_btn = QPushButton("开始录制")
        self.start_btn.setObjectName("Primary")
        self.start_btn.setMinimumWidth(130)
        self.start_btn.clicked.connect(self._on_start)
        head.addWidget(self.start_btn)
        layout.addLayout(head)

        # 范围
        card = Card("录制范围")
        self.target_combo = QComboBox()
        self.target_combo.addItem("区域录制（拖动框选）", "region")
        self.target_combo.addItem("全屏录制", "fullscreen")
        self.target_combo.addItem("指定窗口", "window")
        current = str(CONFIG.get("record.target", "region"))
        index = max(0, self.target_combo.findData(current))
        self.target_combo.setCurrentIndex(index)
        self.target_combo.currentIndexChanged.connect(self._on_target_changed)
        card.add(Row("录制目标", self.target_combo))

        self.window_combo = QComboBox()
        self.window_combo.setEnabled(current == "window")
        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.clicked.connect(self.refresh_windows)
        win_row = QWidget()
        win_layout = QHBoxLayout(win_row)
        win_layout.setContentsMargins(0, 0, 0, 0)
        win_layout.setSpacing(8)
        win_layout.addWidget(self.window_combo, 1)
        win_layout.addWidget(self.refresh_btn)
        self.window_row = Row("目标窗口", win_row)
        card.add(self.window_row)
        self.window_hint = QLabel("提示：窗口录制时请尽量不要移动或最小化窗口。")
        self.window_hint.setObjectName("Hint")
        self.window_hint.setVisible(current == "window")
        card.add(self.window_hint)
        layout.addWidget(card)

        # 画面
        card = Card("画面")
        self.fps_combo = QComboBox()
        for label, value in (("24 帧", 24), ("30 帧（推荐）", 30), ("60 帧", 60)):
            self.fps_combo.addItem(label, value)
        fps = int(CONFIG.get("record.fps", 30))
        self.fps_combo.setCurrentIndex(max(0, self.fps_combo.findData(fps)))
        card.add(Row("帧率", self.fps_combo))

        self.quality_combo = QComboBox()
        for label, value in CRF_PRESETS:
            self.quality_combo.addItem(label, value)
        crf = int(CONFIG.get("record.crf", 23))
        self.quality_combo.setCurrentIndex(max(0, self.quality_combo.findData(crf)))
        card.add(Row("画质", self.quality_combo))

        self.cursor_check = QCheckBox("录制鼠标指针")
        self.cursor_check.setChecked(bool(CONFIG.get("record.draw_cursor", True)))
        card.add(self.cursor_check)
        layout.addWidget(card)

        # 声音
        card = Card("声音", "离线调用 ffmpeg，不上传任何数据")
        self.sys_audio_check = QCheckBox("录制系统声音（自动捕获扬声器输出）")
        self.sys_audio_check.setChecked(bool(CONFIG.get("record.audio_system", True)))
        card.add(self.sys_audio_check)
        self.sys_audio_hint = QLabel("正在检测音频设备…")
        self.sys_audio_hint.setObjectName("Hint")
        self.sys_audio_hint.setWordWrap(True)
        card.add(self.sys_audio_hint)

        self.mic_combo = QComboBox()
        mic_row = QWidget()
        mic_layout = QHBoxLayout(mic_row)
        mic_layout.setContentsMargins(0, 0, 0, 0)
        mic_layout.setSpacing(8)
        mic_layout.addWidget(self.mic_combo, 1)
        refresh_audio = QPushButton("重新检测")
        refresh_audio.clicked.connect(self.scan_devices)
        mic_layout.addWidget(refresh_audio)
        card.add(Row("麦克风", mic_row))
        layout.addWidget(card)

        # 摄像头
        card = Card("摄像头画中画")
        self.camera_combo = QComboBox()
        card.add(Row("摄像头", self.camera_combo))
        size_row = QWidget()
        size_layout = QHBoxLayout(size_row)
        size_layout.setContentsMargins(0, 0, 0, 0)
        self.camera_slider = QSlider(Qt.Orientation.Horizontal)
        self.camera_slider.setRange(160, 480)
        self.camera_slider.setValue(int(CONFIG.get("record.camera_size", 260)))
        self.camera_size_label = QLabel(f"{self.camera_slider.value()} px")
        self.camera_size_label.setFixedWidth(56)
        self.camera_slider.valueChanged.connect(
            lambda v: self.camera_size_label.setText(f"{v} px")
        )
        size_layout.addWidget(self.camera_slider, 1)
        size_layout.addWidget(self.camera_size_label)
        card.add(Row("画面宽度", size_row))
        self.corner_combo = QComboBox()
        for label, value in (("右下角", "br"), ("左下角", "bl"), ("右上角", "tr"), ("左上角", "tl")):
            self.corner_combo.addItem(label, value)
        corner = str(CONFIG.get("record.camera_corner", "br"))
        self.corner_combo.setCurrentIndex(max(0, self.corner_combo.findData(corner)))
        card.add(Row("位置", self.corner_combo))
        layout.addWidget(card)

        # 输出
        card = Card("保存")
        self.dir_picker = DirPicker(str(CONFIG.get("record.save_dir", "")))
        card.add(Row("保存目录", self.dir_picker))
        layout.addWidget(card)

        bottom = QHBoxLayout()
        self.status = QLabel()
        self.status.setObjectName("Hint")
        bottom.addWidget(self.status, 1)
        layout.addLayout(bottom)
        layout.addStretch(1)

        self.refresh_windows()
        self.scan_devices()
        self._on_target_changed()

    # ------------------------------------------------------------------ 设备
    def _on_target_changed(self) -> None:
        is_window = self.target_combo.currentData() == "window"
        self.window_row.setVisible(is_window)
        self.window_combo.setEnabled(is_window)
        self.refresh_btn.setEnabled(is_window)
        self.window_hint.setVisible(is_window)
        if is_window and self.window_combo.count() == 0:
            self.refresh_windows()

    def refresh_windows(self) -> None:
        current = self.window_combo.currentData()
        self.window_combo.clear()
        for info in list_windows():
            self.window_combo.addItem(f"{info.title[:42]}", info.hwnd)
        if current is not None:
            idx = self.window_combo.findData(current)
            if idx >= 0:
                self.window_combo.setCurrentIndex(idx)

    def scan_devices(self) -> None:
        if self._scan_task is not None and self._scan_task.isRunning():
            return
        if not find_ffmpeg():
            self.sys_audio_hint.setText(
                "未找到 ffmpeg，无法录制视频/音频。执行 pip install imageio-ffmpeg 后重启即可。"
            )
            return
        self.sys_audio_hint.setText("正在检测音频设备…")
        self._scan_task = DeviceScanTask()
        self._scan_task.done.connect(self._on_devices)
        self._scan_task.start()

    def _on_devices(self, audio: list, video: list) -> None:
        self._audio_devices = audio
        self._video_devices = video
        system = find_system_audio(audio)
        if loopback_available():
            self.sys_audio_hint.setText(
                "将直接采集扬声器输出（WASAPI 回环），无需「立体声混音」或虚拟声卡。"
            )
            self.sys_audio_check.setEnabled(True)
        else:
            extra = f"；检测到回环设备：{system}" if system else ""
            self.sys_audio_hint.setText(
                "当前无法采集系统声音：缺少音频输出设备或 PyAudioWPatch 组件。"
                "请确认扬声器正常工作后重启本程序。" + extra
            )
            self.sys_audio_check.setEnabled(False)
            self.sys_audio_check.setChecked(False)

        saved_mic = str(CONFIG.get("record.audio_mic", ""))
        self.mic_combo.clear()
        self.mic_combo.addItem("不录制麦克风", "")
        for name in guess_microphones(audio):
            self.mic_combo.addItem(name, name)
        if saved_mic:
            idx = self.mic_combo.findData(saved_mic)
            if idx >= 0:
                self.mic_combo.setCurrentIndex(idx)

        saved_cam = str(CONFIG.get("record.camera", ""))
        self.camera_combo.clear()
        self.camera_combo.addItem("不使用摄像头", "")
        for name in video:
            self.camera_combo.addItem(name, name)
        if saved_cam:
            idx = self.camera_combo.findData(saved_cam)
            if idx >= 0:
                self.camera_combo.setCurrentIndex(idx)

    # ------------------------------------------------------------------ 开始
    def _on_start(self) -> None:
        self.persist()
        target = str(self.target_combo.currentData())
        if target == "window" and self.window_combo.currentData() is None:
            self.status.setText("请先选择一个窗口，或点「刷新」重新获取窗口列表。")
            return
        self.record_requested.emit()

    def persist(self) -> None:
        CONFIG.set("record.target", self.target_combo.currentData())
        CONFIG.set("record.fps", self.fps_combo.currentData())
        CONFIG.set("record.crf", self.quality_combo.currentData())
        CONFIG.set("record.audio_system", self.sys_audio_check.isChecked())
        CONFIG.set("record.audio_mic", self.mic_combo.currentData() or "")
        CONFIG.set("record.camera", self.camera_combo.currentData() or "")
        CONFIG.set("record.camera_size", self.camera_slider.value())
        CONFIG.set("record.camera_corner", self.corner_combo.currentData())
        CONFIG.set("record.draw_cursor", self.cursor_check.isChecked())
        CONFIG.set("record.save_dir", str(self.dir_picker.path()))
        CONFIG.save()

    def build_options(self, rect: tuple[int, int, int, int] | None) -> RecordOptions:
        self.persist()
        target = str(self.target_combo.currentData())
        system_audio = ""
        if self.sys_audio_check.isChecked() and self.sys_audio_check.isEnabled():
            system_audio = "loopback"
        return RecordOptions(
            target=target,
            rect=rect,
            fps=int(self.fps_combo.currentData()),
            crf=int(self.quality_combo.currentData()),
            preset="veryfast",
            system_audio=system_audio,
            mic=str(self.mic_combo.currentData() or ""),
            camera=str(self.camera_combo.currentData() or ""),
            camera_size=even(self.camera_slider.value()),
            camera_corner=str(self.corner_combo.currentData()),
            draw_cursor=self.cursor_check.isChecked(),
            output_dir=Path(self.dir_picker.path()),
        )

    def selected_window_rect(self) -> tuple[int, int, int, int] | None:
        hwnd = self.window_combo.currentData()
        if hwnd is None:
            return None
        rect = window_rect(int(hwnd))
        if rect is None:
            return None
        return (rect.x(), rect.y(), rect.width(), rect.height())

    def shutdown(self) -> None:
        if self._scan_task is not None and self._scan_task.isRunning():
            if not self._scan_task.wait(6000):
                self._scan_task.terminate()
                self._scan_task.wait(1000)
