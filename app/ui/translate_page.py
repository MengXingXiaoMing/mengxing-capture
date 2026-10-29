"""翻译设置页：离线引擎选择、模型管理、翻译测试。"""
from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import QSize, Qt, QThread, pyqtSignal
from PyQt6.QtGui import QImage, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..config import CONFIG
from ..ocr import engine as ocr_engine
from ..theme import ACCENT, TEXT_DIM
from ..translate import argos_local, ollama_installer, service
from .icons import DARK, glyph_icon
from .widgets import Card, Row

LANG_OPTIONS = [
    ("简体中文", "zh"),
    ("英语", "en"),
    ("日语", "ja"),
    ("韩语", "ko"),
    ("法语", "fr"),
    ("德语", "de"),
    ("西班牙语", "es"),
    ("俄语", "ru"),
]

POPULAR_PAIRS = [
    ("en", "zh"), ("zh", "en"), ("ja", "zh"), ("zh", "ja"),
    ("ko", "zh"), ("zh", "ko"), ("fr", "zh"), ("de", "zh"), ("ru", "zh"),
]

RECOMMENDED_MODELS = [
    ("千问 2.5 3B（推荐，平衡）", "qwen2.5:3b", "约 1.9 GB"),
    ("千问 2.5 7B（质量更好）", "qwen2.5:7b", "约 4.7 GB"),
    ("Llama 3.2 3B", "llama3.2:3b", "约 2.0 GB"),
    ("Gemma 2 2B（体积小）", "gemma2:2b", "约 1.6 GB"),
]

BULK_PAIRS = [
    ("ja", "zh"), ("zh", "ja"), ("ko", "zh"), ("zh", "ko"),
    ("fr", "zh"), ("zh", "fr"), ("de", "zh"), ("zh", "de"),
    ("ru", "zh"), ("zh", "ru"),
]


class FuncTask(QThread):
    ok = pyqtSignal(object)
    failed = pyqtSignal(str)
    progress = pyqtSignal(str)

    def __init__(self, fn: Callable, parent=None) -> None:
        super().__init__(parent)
        self._fn = fn

    def run(self) -> None:  # noqa: D401
        try:
            self.ok.emit(self._fn(self.progress.emit))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


def _pair_label(pair: tuple[str, str]) -> str:
    a, b = pair
    return f"{service.LANG_NAMES.get(a, a)} → {service.LANG_NAMES.get(b, b)}"


class TranslatePage(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._task: FuncTask | None = None
        self._tasks: list[FuncTask] = []
        self._installed: list[tuple[str, str]] = []
        self._pair_buttons: dict[tuple[str, str], QPushButton] = {}
        self._last_src = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        target = str(CONFIG.get("translate.target", "zh"))

        # 主翻译区（参考百度翻译：语言栏 + 输入 + 译文 + 底部按钮）
        main_card = Card()
        main_card.body().setContentsMargins(16, 12, 16, 12)
        main_card.body().setSpacing(8)

        lang_row = QHBoxLayout()
        lang_row.setSpacing(4)
        self.src_combo = QComboBox()
        self.src_combo.setObjectName("Flat")
        self.src_combo.addItem("自动检测", "auto")
        for label, code in LANG_OPTIONS:
            self.src_combo.addItem(label, code)
        self.src_combo.currentIndexChanged.connect(self._on_lang_changed)
        lang_row.addWidget(self.src_combo)

        self.swap_btn = QPushButton("⇄")
        self.swap_btn.setObjectName("Tool")
        self.swap_btn.setFixedSize(30, 26)
        self.swap_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.swap_btn.setToolTip("交换源语言和目标语言")
        self.swap_btn.clicked.connect(self._swap_langs)
        lang_row.addWidget(self.swap_btn)

        self.dst_combo = QComboBox()
        self.dst_combo.setObjectName("Flat")
        for label, code in LANG_OPTIONS:
            self.dst_combo.addItem(label, code)
        self.dst_combo.setCurrentIndex(max(0, self.dst_combo.findData(target)))
        self.dst_combo.currentIndexChanged.connect(self._on_lang_changed)
        lang_row.addWidget(self.dst_combo)
        lang_row.addStretch(1)

        self.engine_combo = QComboBox()
        self.engine_combo.setObjectName("Engine")
        self.engine_combo.addItem("Argos 离线", "argos")
        self.engine_combo.addItem("Ollama 大模型", "ollama")
        engine = str(CONFIG.get("translate.engine", "argos"))
        self.engine_combo.setCurrentIndex(max(0, self.engine_combo.findData(engine)))
        self.engine_combo.currentIndexChanged.connect(self._on_engine_changed)
        self.engine_combo.setFixedWidth(128)
        self.engine_combo.setToolTip("翻译引擎（模型与语言包在「设置」页）")
        lang_row.addWidget(self.engine_combo)
        main_card.add_layout(lang_row)

        self.test_input = QTextEdit()
        self.test_input.setObjectName("Plain")
        self.test_input.setPlaceholderText("请输入文本…（Ctrl + Enter 翻译）")
        self.test_input.setMinimumHeight(110)
        main_card.body().addWidget(self.test_input, 1)

        self.output_divider = QFrame()
        self.output_divider.setObjectName("Divider")
        self.output_divider.setFixedHeight(1)
        self.output_divider.setVisible(False)
        main_card.add(self.output_divider)

        self.test_output = QTextEdit()
        self.test_output.setObjectName("Plain")
        self.test_output.setReadOnly(True)
        self.test_output.setMinimumHeight(100)
        self.test_output.setVisible(False)
        main_card.body().addWidget(self.test_output, 1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        self.test_status = QLabel("")
        self.test_status.setObjectName("Hint")
        btn_row.addWidget(self.test_status, 1)
        clear_btn = QPushButton()
        clear_btn.setObjectName("ToolIcon")
        clear_btn.setIcon(glyph_icon("clear"))
        clear_btn.setIconSize(QSize(15, 15))
        clear_btn.setFixedSize(30, 28)
        clear_btn.setToolTip("清空")
        clear_btn.clicked.connect(self._clear_text_translate)
        btn_row.addWidget(clear_btn)
        self.copy_btn = QPushButton()
        self.copy_btn.setObjectName("ToolIcon")
        self.copy_btn.setIcon(glyph_icon("copy"))
        self.copy_btn.setIconSize(QSize(15, 15))
        self.copy_btn.setFixedSize(30, 28)
        self.copy_btn.setToolTip("复制译文")
        self.copy_btn.setEnabled(False)
        self.copy_btn.clicked.connect(self._copy_translation)
        btn_row.addWidget(self.copy_btn)
        translate_btn = QPushButton()
        translate_btn.setObjectName("Primary")
        translate_btn.setIcon(glyph_icon("arrow", DARK))
        translate_btn.setIconSize(QSize(16, 16))
        translate_btn.setFixedSize(52, 28)
        translate_btn.setToolTip("翻译（Ctrl + Enter）")
        translate_btn.clicked.connect(self._run_test)
        btn_row.addWidget(translate_btn)
        main_card.add_layout(btn_row)

        layout.addWidget(main_card, 1)

        shortcut = QShortcut(QKeySequence("Ctrl+Return"), self.test_input)
        shortcut.activated.connect(self._run_test)

        # 语言包与模型设置：由「设置」页接管展示，这里只负责构建
        self.settings_host = QWidget()
        self.settings_layout = QVBoxLayout(self.settings_host)
        self.settings_layout.setContentsMargins(0, 0, 0, 0)
        self.settings_layout.setSpacing(14)

        # Argos
        self.argos_card = Card("Argos 离线语言包")
        status_row = QHBoxLayout()
        self.argos_status = QLabel("正在检查…")
        self.argos_status.setObjectName("Hint")
        self.argos_status.setWordWrap(True)
        status_row.addWidget(self.argos_status, 1)
        import_btn = QPushButton("导入 .argosmodel")
        import_btn.clicked.connect(self._import_argos)
        status_row.addWidget(import_btn)
        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self._refresh_argos)
        status_row.addWidget(refresh_btn)
        self.argos_card.add_layout(status_row)

        self.installed_list = QListWidget()
        self.installed_list.setMaximumHeight(96)
        self.argos_card.add(self.installed_list)

        grid_host = QWidget()
        self.pairs_grid = QGridLayout(grid_host)
        self.pairs_grid.setContentsMargins(0, 0, 0, 0)
        self.pairs_grid.setSpacing(8)
        for index, pair in enumerate(POPULAR_PAIRS):
            btn = QPushButton(_pair_label(pair) + "  下载")
            btn.clicked.connect(lambda _=False, p=pair, b=btn: self._download_pair(p, b))
            self.pairs_grid.addWidget(btn, index // 3, index % 3)
            self._pair_buttons[pair] = btn
        self.argos_card.add(grid_host)

        self.argos_hint = QLabel(
            "首次使用需联网下载一次语言包，之后全程离线。没有网络时，可把 .argosmodel "
            "文件拷到本机，用「导入」安装。"
        )
        self.argos_hint.setObjectName("Hint")
        self.argos_hint.setWordWrap(True)
        self.argos_card.add(self.argos_hint)

        self.bulk_btn = QPushButton()
        self._reset_bulk_btn()
        self.bulk_btn.clicked.connect(self._download_bulk)
        self.argos_card.add(self.bulk_btn)
        self.settings_layout.addWidget(self.argos_card)

        # Ollama
        self.ollama_card = Card("Ollama 本地大模型")
        url_row = QWidget()
        url_layout = QHBoxLayout(url_row)
        url_layout.setContentsMargins(0, 0, 0, 0)
        url_layout.setSpacing(8)
        self.ollama_url = QLineEdit(str(CONFIG.get("translate.ollama_url", "http://127.0.0.1:11434")))
        self.ollama_url.editingFinished.connect(self._save_ollama_url)
        url_layout.addWidget(self.ollama_url, 1)
        detect_btn = QPushButton("检测模型")
        detect_btn.clicked.connect(self._refresh_ollama)
        url_layout.addWidget(detect_btn)
        self.ollama_card.add(Row("服务地址", url_row))

        self.ollama_model = QComboBox()
        self.ollama_model.currentIndexChanged.connect(self._save_ollama_model)
        self.ollama_card.add(Row("使用模型", self.ollama_model))
        self.ollama_status = QLabel("尚未检测。可点下方按钮自动下载安装 Ollama。")
        self.ollama_status.setObjectName("Hint")
        self.ollama_status.setWordWrap(True)
        self.ollama_card.add(self.ollama_status)

        install_row = QHBoxLayout()
        self.ollama_install_btn = QPushButton("自动下载并安装 Ollama（约 1.6 GB）")
        self.ollama_install_btn.setObjectName("Primary")
        self.ollama_install_btn.clicked.connect(self._auto_install_ollama)
        install_row.addWidget(self.ollama_install_btn)

        self.ollama_start_btn = QPushButton("启动 Ollama 服务")
        self.ollama_start_btn.clicked.connect(self._start_ollama_service)
        self.ollama_start_btn.setVisible(False)
        install_row.addWidget(self.ollama_start_btn)
        install_row.addStretch(1)
        self.ollama_card.add_layout(install_row)

        self.pull_row = QWidget()
        pull_layout = QHBoxLayout(self.pull_row)
        pull_layout.setContentsMargins(0, 0, 0, 0)
        pull_layout.setSpacing(8)
        self.model_combo = QComboBox()
        for label, name, size in RECOMMENDED_MODELS:
            self.model_combo.addItem(f"{label} · {size}", name)
        pull_layout.addWidget(self.model_combo, 1)
        self.pull_btn = QPushButton("下载模型")
        self.pull_btn.clicked.connect(self._pull_model)
        pull_layout.addWidget(self.pull_btn)
        self.ollama_card.add(self.pull_row)

        import_row = QHBoxLayout()
        self.import_btn = QPushButton("从离线包导入模型")
        self.import_btn.clicked.connect(self._import_models)
        self.import_btn.setVisible(False)
        import_row.addWidget(self.import_btn)
        import_row.addStretch(1)
        self.ollama_card.add_layout(import_row)

        self.ollama_hint = QLabel(
            "安装包来自 ollama.com，安装后模型同样下载到本机，之后可完全离线使用。"
            "如果网络无法访问，可手动安装 Ollama 后回到这里点「检测模型」。"
        )
        self.ollama_hint.setObjectName("Hint")
        self.ollama_hint.setWordWrap(True)
        self.ollama_card.add(self.ollama_hint)

        self.local_hint = QLabel("")
        self.local_hint.setObjectName("Hint")
        self.local_hint.setWordWrap(True)
        self.local_hint.setVisible(False)
        self.ollama_card.add(self.local_hint)
        self.settings_layout.addWidget(self.ollama_card)

        self._on_engine_changed()
        self._update_ollama_controls()
        self._refresh_argos()
        self._refresh_ollama()

    # ------------------------------------------------------------------ 引擎
    def _on_engine_changed(self) -> None:
        engine = self.engine_combo.currentData()
        CONFIG.set("translate.engine", engine)
        CONFIG.save()
        is_argos = engine == "argos"
        self.argos_card.setVisible(is_argos)
        self.ollama_card.setVisible(not is_argos)
        if not is_argos:
            self._update_ollama_controls()

    def _refresh_argos(self) -> None:
        self.argos_status.setText("正在检查 Argos 组件…")

        def work(_progress):
            installed = service.argos_installed_pairs()
            ready, message = service.argos_available()
            return installed, ready, message

        self._run_task(work, self._on_argos_status)

    def _on_argos_status(self, data) -> None:
        installed, ready, message = data
        self._installed = installed
        self.installed_list.clear()
        for pair in installed:
            self.installed_list.addItem("已安装：" + _pair_label(pair))
        self.installed_list.setVisible(bool(installed))
        for pair, button in self._pair_buttons.items():
            usable = argos_local.installed_route(pair[0], pair[1]) is not None
            if usable:
                button.setText(_pair_label(pair) + "  可用")
                button.setEnabled(False)
            else:
                button.setText(_pair_label(pair) + "  下载")
                button.setEnabled(True)
        if ready:
            self.argos_status.setText(f"就绪（{message}）")
            self.argos_status.setStyleSheet(f"color:{ACCENT};")
        else:
            self.argos_status.setText(f"未就绪：{message}")
            self.argos_status.setStyleSheet(f"color:{TEXT_DIM};")

    def _download_pair(self, pair: tuple[str, str], button: QPushButton) -> None:
        if any(t.isRunning() for t in self._tasks):
            return
        button.setEnabled(False)
        button.setText(_pair_label(pair) + "  下载中…")

        def work(progress):
            service.argos_download_pair(pair[0], pair[1], progress)
            return True

        task = self._run_task(work, lambda _r: self._after_download(pair, button))
        task.progress.connect(lambda text: button.setText(text))
        task.failed.connect(lambda _m: self._reset_pair_button(pair, button))

    def _reset_pair_button(self, pair: tuple[str, str], button: QPushButton) -> None:
        if pair in self._installed:
            button.setText(_pair_label(pair) + "  已安装")
            button.setEnabled(False)
        else:
            button.setText(_pair_label(pair) + "  下载")
            button.setEnabled(True)

    def _after_download(self, pair: tuple[str, str], button: QPushButton) -> None:
        button.setEnabled(True)
        button.setText(_pair_label(pair) + "  已安装")
        self._refresh_argos()

    def _reset_bulk_btn(self) -> None:
        self.bulk_btn.setText("补齐常用语言包：日 / 韩 / 法 / 德 / 俄（约 500 MB）")
        self.bulk_btn.setEnabled(True)

    def _download_bulk(self) -> None:
        if any(t.isRunning() for t in self._tasks):
            return
        self.bulk_btn.setEnabled(False)

        def work(progress):
            done = 0
            for source, target in BULK_PAIRS:
                progress(f"正在补齐 {source}→{target}（{done}/{len(BULK_PAIRS)}）")
                service.argos_download_pair(source, target)
                done += 1
            return done

        task = self._run_task(work, self._on_bulk_done)
        task.progress.connect(self.bulk_btn.setText)
        task.failed.connect(lambda _m: self._reset_bulk_btn())

    def _on_bulk_done(self, count) -> None:
        self._reset_bulk_btn()
        self.argos_status.setText(f"已补齐 {count} 组语言对，现在支持日 / 韩 / 法 / 德 / 俄 / 西。")
        self.argos_status.setStyleSheet(f"color:{ACCENT};")
        self._refresh_argos()

    def _import_argos(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 Argos 语言包", "", "Argos 模型 (*.argosmodel);;所有文件 (*.*)"
        )
        if not path:
            return
        self.argos_status.setText("正在安装语言包…")

        def work(_progress):
            service.argos_install_from_file(path)
            return path

        self._run_task(work, lambda _r: self._refresh_argos())

    # ------------------------------------------------------------------ Ollama
    def _save_ollama_url(self) -> None:
        CONFIG.set("translate.ollama_url", self.ollama_url.text().strip())
        CONFIG.save()

    def _save_ollama_model(self) -> None:
        if self.ollama_model.currentData() is not None:
            CONFIG.set("translate.ollama_model", self.ollama_model.currentData())
            CONFIG.save()

    def _refresh_ollama(self) -> None:
        self._save_ollama_url()
        url = self.ollama_url.text().strip()
        self.ollama_status.setText("正在连接 Ollama…")

        def work(_progress):
            return service.ollama_models(url)

        self._run_task(work, self._on_ollama_models)

    def _on_ollama_models(self, models: list) -> None:
        current = str(CONFIG.get("translate.ollama_model", ""))
        self.ollama_model.blockSignals(True)
        self.ollama_model.clear()
        for name in models:
            self.ollama_model.addItem(name, name)
        self.ollama_model.blockSignals(False)
        self._update_ollama_controls(bool(models))
        if not models:
            if not ollama_installer.is_installed():
                self.ollama_status.setText("未检测到 Ollama。可直接点下方按钮自动下载并安装。")
            else:
                self.ollama_status.setText(
                    "Ollama 已安装但服务未响应。点「检测模型」重试，或手动运行 ollama serve。"
                )
            self.ollama_status.setStyleSheet(f"color:{TEXT_DIM};")
            return
        idx = self.ollama_model.findData(current) if current else -1
        if idx < 0:
            idx = next(
                (i for i, name in enumerate(models) if "qwen" in name.lower()), 0
            )
        self.ollama_model.setCurrentIndex(idx)
        self.ollama_status.setText(f"已连接，发现 {len(models)} 个本地模型。")
        self.ollama_status.setStyleSheet(f"color:{ACCENT};")

    def _update_ollama_controls(self, alive: bool = False) -> None:
        installed = ollama_installer.is_installed()
        local_setup = ollama_installer.has_local_setup()
        local_models = ollama_installer.local_model_names()

        self.ollama_install_btn.setVisible(not installed)
        self.ollama_install_btn.setText(
            "使用本地离线包安装 Ollama"
            if local_setup
            else "自动下载并安装 Ollama（约 1.6 GB）"
        )
        self.ollama_start_btn.setVisible(installed and not alive)
        self.pull_row.setVisible(installed)
        self.ollama_hint.setVisible(not installed)
        self.import_btn.setVisible(bool(local_models))

        if local_models:
            text = "检测到离线模型：" + "、".join(local_models) + "，无网络也能直接导入使用。"
            if local_setup:
                text += "（安装包也已打包在 vendor/ollama）"
            self.local_hint.setText(text)
            self.local_hint.setStyleSheet(f"color:{ACCENT};font-size:12px;")
            self.local_hint.setVisible(True)
        else:
            self.local_hint.setVisible(False)

    def _import_models(self) -> None:
        self.import_btn.setEnabled(False)
        self.ollama_status.setText("正在导入离线模型…")

        def work(progress):
            count = ollama_installer.import_local_models(progress)
            ollama_installer.start_service(progress)
            return count

        task = self._run_task(work, self._on_import_done)
        task.progress.connect(self.ollama_status.setText)
        task.failed.connect(lambda _m: self.import_btn.setEnabled(True))

    def _on_import_done(self, count) -> None:
        self.import_btn.setEnabled(True)
        self.ollama_status.setText(f"已导入离线模型（{count} 个文件），正在刷新列表…")
        self.ollama_status.setStyleSheet(f"color:{ACCENT};")
        self._refresh_ollama()

    def _start_ollama_service(self) -> None:
        self.ollama_start_btn.setEnabled(False)
        self.ollama_status.setText("正在启动 Ollama 服务…")

        def work(progress):
            return ollama_installer.start_service(progress)

        task = self._run_task(work, self._on_service_started)
        task.progress.connect(self.ollama_status.setText)
        task.failed.connect(lambda _m: self.ollama_start_btn.setEnabled(True))

    def _on_service_started(self, ok) -> None:
        self.ollama_start_btn.setEnabled(True)
        if ok:
            self.ollama_status.setText("Ollama 服务已启动。")
            self.ollama_status.setStyleSheet(f"color:{ACCENT};")
            self._update_ollama_controls(True)
            self._refresh_ollama()
        else:
            self.ollama_status.setText("启动失败，可手动运行 ollama serve 后重试。")
            self.ollama_status.setStyleSheet(f"color:{ACCENT};")

    def _auto_install_ollama(self) -> None:
        self.ollama_install_btn.setEnabled(False)
        self.ollama_status.setStyleSheet(f"color:{TEXT_DIM};")
        self.ollama_status.setText("准备下载 Ollama 安装包…")

        def work(progress):
            if ollama_installer.has_local_setup():
                ollama_installer.install_installer(ollama_installer.LOCAL_SETUP, progress)
            else:
                setup = ollama_installer.download_installer(progress)
                ollama_installer.install_installer(setup, progress)
            ollama_installer.start_service(progress)
            return ollama_installer.import_local_models(progress)

        task = self._run_task(work, self._on_install_done)
        task.progress.connect(self.ollama_status.setText)
        task.failed.connect(lambda _m: self.ollama_install_btn.setEnabled(True))

    def _on_install_done(self, imported) -> None:
        self.ollama_install_btn.setEnabled(True)
        if imported:
            self.ollama_status.setText(
                f"Ollama 已安装并启动，已从离线包导入模型（{imported} 个文件）。"
            )
        else:
            self.ollama_status.setText("Ollama 已安装并启动，请选择模型并下载。")
        self.ollama_status.setStyleSheet(f"color:{ACCENT};")
        self._update_ollama_controls(True)
        self._refresh_ollama()

    def _pull_model(self) -> None:
        model = self.model_combo.currentData()
        if not model:
            return
        self.pull_btn.setEnabled(False)
        self.ollama_status.setStyleSheet(f"color:{TEXT_DIM};")
        self.ollama_status.setText(f"准备下载 {model}…")

        def work(progress):
            ollama_installer.pull_model(model, progress)
            return model

        task = self._run_task(work, self._on_pull_done)
        task.progress.connect(self.ollama_status.setText)
        task.failed.connect(lambda _m: self.pull_btn.setEnabled(True))

    def _on_pull_done(self, model) -> None:
        self.pull_btn.setEnabled(True)
        self.ollama_status.setText(f"模型 {model} 已就绪。")
        self.ollama_status.setStyleSheet(f"color:{ACCENT};")
        self._refresh_ollama()

    # ------------------------------------------------------------------ 截图翻译
    def translate_from_image(self, image: QImage) -> None:
        """把截图里识别出的文字填进输入框，然后直接翻译。"""
        self.test_status.setText("正在识别文字…")
        self.test_output.clear()
        self.output_divider.setVisible(False)
        self.test_output.setVisible(False)
        self.copy_btn.setEnabled(False)

        def work(_progress):
            lines = ocr_engine.recognize(image)
            return "\n".join(line.text for line in lines if line.text.strip())

        self._run_task(work, self._on_ocr_done)

    def _on_ocr_done(self, text: str) -> None:
        if not text.strip():
            self.test_status.setText("没有识别到文字，请重新框选清晰的文字区域。")
            return
        self.test_input.setPlainText(text)
        self._run_test()

    # ------------------------------------------------------------------ 文本翻译
    def _on_lang_changed(self) -> None:
        target = self.dst_combo.currentData()
        if not target:
            return
        CONFIG.set("translate.target", target)
        CONFIG.save()

    def _swap_langs(self) -> None:
        source = self.src_combo.currentData()
        target = self.dst_combo.currentData()
        if not source or not target:
            return
        if source == "auto":
            # 自动检测时：用当前输入判断语言，没有输入就沿用上次结果，最后兜底中英互换
            text = self.test_input.toPlainText().strip()
            source = service.detect_language(text) if text else ""
            if not source:
                source = self._last_src
            if not source or source == target:
                source = "en" if target != "en" else "zh"
        src_index = self.src_combo.findData(target)
        dst_index = self.dst_combo.findData(source)
        if src_index < 0 or dst_index < 0:
            return
        self.src_combo.blockSignals(True)
        self.dst_combo.blockSignals(True)
        self.src_combo.setCurrentIndex(src_index)
        self.dst_combo.setCurrentIndex(dst_index)
        self.src_combo.blockSignals(False)
        self.dst_combo.blockSignals(False)
        self._on_lang_changed()
        if self.test_input.toPlainText().strip():
            self._run_test()

    def _clear_text_translate(self) -> None:
        self.test_input.clear()
        self.test_output.clear()
        self.output_divider.setVisible(False)
        self.test_output.setVisible(False)
        self.copy_btn.setEnabled(False)
        self.test_status.setText("")

    def _copy_translation(self) -> None:
        text = self.test_output.toPlainText().strip()
        if not text:
            self.test_status.setText("还没有可复制的译文。")
            return
        QApplication.clipboard().setText(text)
        self.test_status.setText("译文已复制到剪贴板。")

    # ------------------------------------------------------------------ 测试
    def _run_test(self) -> None:
        text = self.test_input.toPlainText().strip()
        if not text:
            self.test_status.setText("请先输入要翻译的文字。")
            return
        engine = str(self.engine_combo.currentData())
        source = str(self.src_combo.currentData() or "auto")
        target = str(self.dst_combo.currentData() or "zh")
        self._save_ollama_url()
        options = {
            "model": CONFIG.get("translate.ollama_model", ""),
            "url": self.ollama_url.text().strip(),
        }
        self.test_status.setText("翻译中…")
        self.test_output.clear()

        def work(progress):
            src, tgt = service.resolve_pair(text, source, target)
            lines = [ln for ln in text.splitlines() if ln.strip()]
            task = service.TranslationTask(engine, **options)
            result = task.translate_lines(
                lines, src, tgt, on_progress=lambda c, t: progress(f"翻译中… {c}/{t}")
            )
            return src, tgt, result

        task = self._run_task(work, self._on_test_done)
        task.progress.connect(self.test_status.setText)

    def _on_test_done(self, data) -> None:
        src, tgt, result = data
        self._last_src = src
        self.test_status.setText(
            "完成："
            + " → ".join([service.LANG_NAMES.get(src, src), service.LANG_NAMES.get(tgt, tgt)])
        )
        self.test_output.setPlainText("\n".join(result))
        self.output_divider.setVisible(True)
        self.test_output.setVisible(True)
        self.copy_btn.setEnabled(True)
        index = self.dst_combo.findData(tgt)
        if index >= 0 and self.dst_combo.currentData() != tgt:
            self.dst_combo.blockSignals(True)
            self.dst_combo.setCurrentIndex(index)
            self.dst_combo.blockSignals(False)
            CONFIG.set("translate.target", tgt)
            CONFIG.save()

    # ------------------------------------------------------------------ 任务
    def _run_task(self, fn: Callable, on_ok: Callable) -> FuncTask:
        task = FuncTask(fn, self)
        self._tasks.append(task)
        task.ok.connect(on_ok)
        task.failed.connect(self._on_task_failed)
        task.finished.connect(lambda: self._cleanup(task))
        task.start()
        return task

    def _cleanup(self, task: FuncTask) -> None:
        if task in self._tasks:
            self._tasks.remove(task)
        task.deleteLater()

    def _on_task_failed(self, message: str) -> None:
        first = message.splitlines()[0] if message else "未知错误"
        if self.argos_card.isVisible():
            self.argos_status.setText(first)
            self.argos_status.setStyleSheet(f"color:{ACCENT};")
        elif self.ollama_card.isVisible():
            self.ollama_status.setText(first)
            self.ollama_status.setStyleSheet(f"color:{ACCENT};")
        self.test_status.setText("失败：" + first)

    def shutdown(self) -> None:
        """退出前等待后台线程，避免 QThread 仍在运行时析构导致崩溃。"""
        for task in list(self._tasks):
            if task.isRunning() and not task.wait(6000):
                task.terminate()
                task.wait(1000)
