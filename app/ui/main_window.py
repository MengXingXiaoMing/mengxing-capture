"""主窗口：首页 / 录屏 / 翻译 / 设置。"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QSize, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..config import CONFIG
from ..paths import DATA_DIR, find_ffmpeg
from ..theme import ACCENT, TEXT_DIM
from ..translate import ollama_installer
from .icons import DARK, app_icon, glyph_icon
from .record_page import RecordPage
from .translate_page import TranslatePage
from .widgets import Card, DirPicker, KeyCaptureEdit, Row

VERSION = "0.1.0"
GITHUB_URL = "https://github.com/MengXingXiaoMing/mengxing-capture"
OLLAMA_URL = "https://ollama.com/download"
HOTKEY_FIELDS = [
    ("capture", "截图"),
    ("translate", "截图翻译"),
    ("record", "开始/停止录屏"),
    ("record_pause", "暂停/继续"),
    ("stop", "停止录屏"),
]


class GifTask(QThread):
    ok = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, video: str, parent=None) -> None:
        super().__init__(parent)
        self._video = video

    def run(self) -> None:  # noqa: D401
        from ..record.recorder import RecordError, export_gif

        try:
            self.ok.emit(export_gif(self._video))
        except RecordError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class EnvTask(QThread):
    progress = pyqtSignal(str)
    ok = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, fn, parent=None) -> None:
        super().__init__(parent)
        self._fn = fn

    def run(self) -> None:  # noqa: D401
        try:
            self.ok.emit(self._fn(self.progress.emit))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self, controller) -> None:
        super().__init__()
        self.controller = controller
        self._env_task: EnvTask | None = None
        self.setWindowTitle("梦星截屏 · 录屏与离线翻译")
        self.setWindowIcon(app_icon())
        self.resize(620, 400)
        self.setMinimumSize(520, 340)

        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ---------------------------------------------------------- 顶部工具条
        topbar = QFrame()
        topbar.setObjectName("TopBar")
        topbar.setFixedHeight(52)
        top = QHBoxLayout(topbar)
        top.setContentsMargins(16, 0, 16, 0)
        top.setSpacing(4)

        logo = QLabel()
        logo.setPixmap(app_icon().pixmap(22, 22))
        top.addWidget(logo)
        name = QLabel("梦星截屏")
        name.setStyleSheet("font-size:13px;font-weight:600;")
        top.addWidget(name)
        top.addSpacing(14)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self._nav_buttons: list[QPushButton] = []
        for index, (icon_name, tip) in enumerate(
            (("translate", "翻译"), ("record", "录屏"), ("settings", "设置"))
        ):
            btn = QPushButton()
            btn.setObjectName("Tab")
            btn.setCheckable(True)
            btn.setIcon(glyph_icon(icon_name))
            btn.setIconSize(QSize(18, 18))
            btn.setFixedSize(36, 30)
            btn.setToolTip(tip)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _=False, i=index: self.show_page(i))
            self.nav_group.addButton(btn, index)
            top.addWidget(btn)
            self._nav_buttons.append(btn)
        self._nav_buttons[0].setChecked(True)

        top.addStretch(1)
        self.record_state = QLabel()
        self.record_state.setFixedSize(8, 8)
        self.record_state.setStyleSheet(f"background:{ACCENT};border-radius:4px;")
        self.record_state.setToolTip("正在录制")
        self.record_state.setVisible(False)
        top.addWidget(self.record_state)
        top.addSpacing(8)
        self.capture_btn = QPushButton()
        self.capture_btn.setObjectName("Primary")
        self.capture_btn.setIcon(glyph_icon("capture", DARK))
        self.capture_btn.setIconSize(QSize(18, 18))
        self.capture_btn.setFixedSize(42, 30)
        self.capture_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.capture_btn.clicked.connect(self.controller.start_capture)
        top.addWidget(self.capture_btn)
        outer.addWidget(topbar)

        # ---------------------------------------------------------- 内容区
        self.stack = QStackedWidget()
        self.translate_page = TranslatePage()
        self.record_page = RecordPage()
        self.settings_page = self._build_settings()
        self.stack.addWidget(self._wrap(self.translate_page, 14, 12))
        self.stack.addWidget(self._wrap(self.record_page))
        self.stack.addWidget(self._wrap(self.settings_page))
        outer.addWidget(self.stack, 1)

        self.record_page.record_requested.connect(self.controller.request_record)
        self.refresh_hotkey_labels()

    # ------------------------------------------------------------------ 容器
    def _wrap(self, widget: QWidget, side: int = 28, top: int = 24) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        host = QWidget()
        layout = QVBoxLayout(host)
        layout.setContentsMargins(side, top, side, top)
        layout.addWidget(widget)
        scroll.setWidget(host)
        return scroll

    def show_page(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        if 0 <= index < len(self._nav_buttons):
            self._nav_buttons[index].setChecked(True)
        if index == 2:
            self.refresh_recent()

    # ------------------------------------------------------------------ 顶部
    def refresh_hotkey_labels(self) -> None:
        sequence = str(CONFIG.get("hotkeys.capture", "") or "").upper()
        self.capture_btn.setToolTip(f"截图（{sequence}）" if sequence else "未设置截图快捷键")

    def set_recording(self, active: bool) -> None:
        self.record_state.setVisible(active)

    def refresh_recent(self) -> None:
        if not hasattr(self, "recent_list"):
            return
        self.recent_list.clear()
        files: list[Path] = []
        for key in ("capture.save_dir", "record.save_dir"):
            folder = Path(str(CONFIG.get(key, "")))
            if not folder.is_dir():
                continue
            try:
                files.extend(
                    f for f in folder.iterdir()
                    if f.is_file() and f.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".mp4"}
                )
            except OSError:
                continue
        files.sort(key=lambda f: f.stat().st_mtime if f.exists() else 0, reverse=True)
        if not files:
            item = QListWidgetItem("还没有生成任何文件，先从上面的按钮开始吧。")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.recent_list.addItem(item)
            return
        for path in files[:12]:
            try:
                mtime = datetime.fromtimestamp(path.stat().st_mtime).strftime("%m-%d %H:%M")
                size = path.stat().st_size / 1024
                size_text = f"{size / 1024:.1f} MB" if size > 1024 else f"{size:.0f} KB"
            except OSError:
                mtime, size_text = "", ""
            item = QListWidgetItem(f"{path.name}    {mtime}    {size_text}")
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            self.recent_list.addItem(item)

    def _open_recent_item(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.ItemDataRole.UserRole)
        if path and Path(path).exists():
            os.startfile(path)  # noqa: S606

    def _recent_menu(self, pos) -> None:
        item = self.recent_list.itemAt(pos)
        if item is None:
            return
        path = item.data(Qt.ItemDataRole.UserRole)
        if not path or not Path(path).exists():
            return
        menu = QMenu(self)
        open_action = menu.addAction("打开")
        gif_action = None
        if str(path).lower().endswith(".mp4"):
            gif_action = menu.addAction("导出 GIF（宽 720）")
        menu.addSeparator()
        folder_action = menu.addAction("打开所在文件夹")
        chosen = menu.exec(self.recent_list.mapToGlobal(pos))
        if chosen is open_action:
            os.startfile(path)  # noqa: S606
        elif gif_action is not None and chosen is gif_action:
            self._export_gif(str(path))
        elif chosen is folder_action:
            os.startfile(str(Path(path).parent))  # noqa: S606

    def _export_gif(self, video: str) -> None:
        if getattr(self, "_gif_task", None) is not None and self._gif_task.isRunning():
            return
        self.statusBar().showMessage("正在导出 GIF，请稍候…")
        task = GifTask(video, self)
        self._gif_task = task

        def done(gif: str) -> None:
            self.statusBar().showMessage("GIF 已导出：" + gif, 6000)
            self.refresh_recent()

        def failed(message: str) -> None:
            self.statusBar().clearMessage()
            QMessageBox.warning(self, "导出 GIF 失败", message)

        task.ok.connect(done)
        task.failed.connect(failed)
        task.start()

    # ------------------------------------------------------------------ 设置页
    def _build_settings(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        hotkey_card = Card("全局快捷键", "点击输入框后按下组合键")
        self._hotkey_edits: dict[str, KeyCaptureEdit] = {}
        for key, label in HOTKEY_FIELDS:
            edit = KeyCaptureEdit(str(CONFIG.get(f"hotkeys.{key}", "")))
            self._hotkey_edits[key] = edit
            hotkey_card.add(Row(label, edit))
        reset_row = QHBoxLayout()
        reset_row.addStretch(1)
        reset_btn = QPushButton("恢复默认")
        reset_btn.clicked.connect(self._reset_hotkeys)
        reset_row.addWidget(reset_btn)
        hotkey_card.add_layout(reset_row)
        layout.addWidget(hotkey_card)

        capture_card = Card("截图")
        self.shot_dir = DirPicker(str(CONFIG.get("capture.save_dir", "")))
        capture_card.add(Row("保存目录", self.shot_dir))
        self.auto_copy = QCheckBox("截图后自动复制到剪贴板")
        self.auto_copy.setChecked(bool(CONFIG.get("capture.auto_copy", True)))
        capture_card.add(self.auto_copy)
        layout.addWidget(capture_card)

        general_card = Card("通用")
        self.close_to_tray = QCheckBox("关闭窗口时最小化到托盘（快捷键仍然可用）")
        self.close_to_tray.setChecked(bool(CONFIG.get("ui.close_to_tray", True)))
        general_card.add(self.close_to_tray)
        layout.addWidget(general_card)

        env_card = Card("离线翻译环境", "Ollama + 千问模型")
        self.env_status = QLabel()
        self.env_status.setWordWrap(True)
        self.env_status.setStyleSheet(f"color:{TEXT_DIM};font-size:12px;line-height:1.8;")
        env_card.add(self.env_status)

        ollama_link = QLabel(
            f'Ollama 下载页：<a style="color:{ACCENT};" href="{OLLAMA_URL}">{OLLAMA_URL}</a>'
            "（有本地安装包或已装好时会直接用本地的，不重复下载）"
        )
        ollama_link.setOpenExternalLinks(True)
        ollama_link.setWordWrap(True)
        ollama_link.setStyleSheet(f"color:{TEXT_DIM};font-size:12px;")
        env_card.add(ollama_link)

        env_row = QHBoxLayout()
        self.env_hint = QLabel("先检测，已经装好的部分会跳过，不会重复下载。")
        self.env_hint.setObjectName("Hint")
        env_row.addWidget(self.env_hint, 1)
        self.env_btn = QPushButton("检测并一键安装")
        self.env_btn.setObjectName("Primary")
        self.env_btn.clicked.connect(self._setup_offline_env)
        env_row.addWidget(self.env_btn)
        env_card.add_layout(env_row)
        layout.addWidget(env_card)

        self.translate_page.settings_host.setVisible(True)
        layout.addWidget(self.translate_page.settings_host)

        recent_card = Card("最近生成")
        self.recent_list = QListWidget()
        self.recent_list.setMinimumHeight(150)
        self.recent_list.itemDoubleClicked.connect(self._open_recent_item)
        self.recent_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.recent_list.customContextMenuRequested.connect(self._recent_menu)
        recent_card.add(self.recent_list)
        recent_hint = QLabel("双击打开文件；右键可导出 GIF。文件保存在程序目录的 userdata 下。")
        recent_hint.setObjectName("Hint")
        recent_card.add(recent_hint)
        layout.addWidget(recent_card)

        status_card = Card("运行状态")
        ffmpeg_path = find_ffmpeg() or "未找到"
        self.dep_label = QLabel()
        self.dep_label.setWordWrap(True)
        self.dep_label.setStyleSheet(f"color:{TEXT_DIM};font-size:12px;line-height:1.8;")
        status_card.add(self.dep_label)
        data_hint = QLabel(f"数据目录：{DATA_DIR}")
        data_hint.setWordWrap(True)
        data_hint.setObjectName("Hint")
        status_card.add(data_hint)
        layout.addWidget(status_card)

        about_card = Card("简介", "关于本软件")
        intro = QLabel(
            "梦星截屏是一款完全在本机运行的 Windows 截图、录屏与翻译工具。"
            "框选一次即可完成截图标注、截图翻译或区域录屏；"
            "文字识别使用离线 OCR，翻译支持 Argos 本地模型与 Ollama 本地大模型，"
            "截图、录像和待翻译的文字都不会上传到任何服务器。"
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color:{TEXT_DIM};font-size:12px;line-height:1.8;")
        about_card.add(intro)

        author = QLabel(f"作者：詹康明　·　版本 v{VERSION}　·　Python + PyQt6")
        author.setStyleSheet(f"color:{ACCENT};font-size:12px;font-weight:600;")
        about_card.add(author)

        github = QLabel(
            f'GitHub：<a style="color:{ACCENT};" href="{GITHUB_URL}">{GITHUB_URL}</a>'
        )
        github.setOpenExternalLinks(True)
        github.setWordWrap(True)
        github.setStyleSheet(f"color:{TEXT_DIM};font-size:12px;")
        about_card.add(github)

        tips = QLabel("问题排查：日志在 userdata\\logs\\error.log，异常会记录在这里。")
        tips.setObjectName("Hint")
        tips.setWordWrap(True)
        about_card.add(tips)
        layout.addWidget(about_card)

        bottom = QHBoxLayout()
        self.save_status = QLabel()
        self.save_status.setObjectName("Hint")
        bottom.addWidget(self.save_status, 1)
        save_btn = QPushButton("保存设置")
        save_btn.setObjectName("Primary")
        save_btn.clicked.connect(self._save_settings)
        bottom.addWidget(save_btn)
        layout.addLayout(bottom)
        layout.addStretch(1)

        self._refresh_deps(ffmpeg_path)
        self._refresh_env_status()
        return page

    # ------------------------------------------------------------------ 离线翻译环境
    def _target_model(self) -> str:
        return str(CONFIG.get("translate.ollama_model", "") or "") or "qwen3:4b"

    def _refresh_env_status(self) -> None:
        installed = ollama_installer.is_installed()
        local_setup = ollama_installer.has_local_setup()
        local_models = ollama_installer.local_model_names()
        user_models = ollama_installer.user_model_names()
        model = self._target_model()

        if installed:
            ollama_text = "Ollama：已安装（直接使用本地，不再下载）"
        elif local_setup:
            ollama_text = "Ollama：未安装（检测到本地离线包，将直接用本地的安装）"
        else:
            ollama_text = "Ollama：未安装（需要联网下载安装包）"

        if model in user_models:
            model_text = f"模型 {model}：已就绪（本地）"
        elif model in local_models:
            model_text = f"模型 {model}：未安装（离线包里已有，会优先导入本地的）"
        else:
            model_text = f"模型 {model}：未安装（需要联网下载）"

        lines = [ollama_text, model_text]
        if local_models:
            lines.append("离线包模型：" + "、".join(local_models))
        self.env_status.setText("<br>".join(lines))

    def _reset_env_btn(self) -> None:
        self.env_btn.setEnabled(True)
        self.env_btn.setText("检测并一键安装")

    def _setup_offline_env(self) -> None:
        if self._env_task is not None and self._env_task.isRunning():
            return
        model = self._target_model()
        installed = ollama_installer.is_installed()
        if installed and model in ollama_installer.user_model_names():
            self._refresh_env_status()
            self.controller.notify("Ollama 和模型都已就绪，无需安装。")
            QTimer.singleShot(2200, self._reset_env_btn)
            self.env_btn.setText("已就绪")
            return

        self.env_btn.setEnabled(False)
        self.env_btn.setText("正在处理…")

        def work(progress):
            steps: list[str] = []
            if not ollama_installer.is_installed():
                if ollama_installer.has_local_setup():
                    progress("正在用本地离线包安装 Ollama…")
                    ollama_installer.install_installer(ollama_installer.LOCAL_SETUP, progress)
                    steps.append("Ollama 已从离线包安装")
                else:
                    progress("正在下载 Ollama 安装包…")
                    setup = ollama_installer.download_installer(progress)
                    ollama_installer.install_installer(setup, progress)
                    steps.append("Ollama 已下载安装")
            else:
                steps.append("Ollama 已安装")

            if not ollama_installer.service_alive():
                ollama_installer.start_service(progress)

            progress("正在检查模型…")
            if model in ollama_installer.user_model_names():
                steps.append(f"模型 {model} 已存在")
            else:
                if ollama_installer.local_model_names():
                    progress("正在导入离线模型…")
                    ollama_installer.import_local_models(progress)
                if model in ollama_installer.user_model_names():
                    steps.append(f"已从离线包导入 {model}")
                else:
                    progress(f"正在下载模型 {model}…")
                    ollama_installer.pull_model(model, progress)
                    steps.append(f"已下载 {model}")
            return "；".join(steps)

        task = EnvTask(work, self)
        self._env_task = task
        task.progress.connect(self.env_status.setText)
        task.ok.connect(self._on_env_done)
        task.failed.connect(self._on_env_failed)
        task.start()

    def _on_env_done(self, summary: str) -> None:
        self._env_task = None
        self._reset_env_btn()
        self._refresh_env_status()
        if not CONFIG.get("translate.ollama_model"):
            CONFIG.set("translate.ollama_model", self._target_model())
            CONFIG.save()
        self.translate_page._refresh_ollama()
        QMessageBox.information(
            self,
            "离线翻译环境",
            f"已完成：\n{summary}\n\n可以到「翻译」页把引擎切到 Ollama 开始使用。",
        )

    def _on_env_failed(self, message: str) -> None:
        self._env_task = None
        self._reset_env_btn()
        self._refresh_env_status()
        QMessageBox.warning(self, "安装失败", message)

    def _refresh_deps(self, ffmpeg_path: str) -> None:
        from ..ocr.engine import is_ready as ocr_ready
        from ..translate.service import argos_available

        argos_ok, argos_msg = argos_available()
        lines = [
            f"ffmpeg：{ffmpeg_path}",
            f"离线 OCR：{'就绪' if ocr_ready() else '未安装（执行 pip install rapidocr onnxruntime）'}",
            f"Argos 翻译：{('就绪 · ' + argos_msg) if argos_ok else argos_msg}",
        ]
        self.dep_label.setText("<br>".join(lines))

    def _reset_hotkeys(self) -> None:
        from ..config import DEFAULTS

        for key, _label in HOTKEY_FIELDS:
            value = DEFAULTS["hotkeys"][key]
            self._hotkey_edits[key].setText(value)

    def _save_settings(self) -> None:
        for key, edit in self._hotkey_edits.items():
            CONFIG.set(f"hotkeys.{key}", edit.text().strip())
        CONFIG.set("capture.save_dir", str(self.shot_dir.path()))
        CONFIG.set("capture.auto_copy", self.auto_copy.isChecked())
        CONFIG.set("ui.close_to_tray", self.close_to_tray.isChecked())
        CONFIG.save()
        failures = self.controller.reload_hotkeys()
        self.refresh_hotkey_labels()
        self.record_page.persist()
        if failures:
            QMessageBox.warning(
                self, "部分快捷键未生效",
                "以下快捷键被其它程序占用或格式不正确：\n\n" + "\n".join(failures)
                + "\n\n换一个组合键后再保存即可。",
            )
            self.save_status.setText("已保存，但有快捷键冲突")
        else:
            self.save_status.setText("已保存")
            QTimer.singleShot(2600, lambda: self.save_status.setText(""))

    # ------------------------------------------------------------------ 关闭
    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if CONFIG.get("ui.close_to_tray", True) and self.controller.tray_available():
            self.hide()
            self.controller.notify("梦星截屏仍在后台运行，快捷键随时可用。")
            event.ignore()
            return
        self.controller.quit()
        event.accept()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_F5:
            self.refresh_recent()
            return
        super().keyPressEvent(event)
