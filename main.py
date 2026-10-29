"""梦星截屏 · 录屏与离线翻译 —— 程序入口。"""
from __future__ import annotations

import ctypes
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

from PyQt6.QtWidgets import QApplication

from app.paths import LOG_DIR

SERVER_NAME = "MengXingCapture-single-instance"
MUTEX_NAME = "MengXingCapture-single-instance-mutex"
ERROR_ALREADY_EXISTS = 183

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_mutex_handle = None


def _setup_dpi() -> None:
    """在创建 QApplication 之前声明 Per-Monitor V2 DPI 感知，保证多屏缩放准确。"""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:  # noqa: BLE001
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:  # noqa: BLE001
            pass


def _install_excepthook() -> None:
    log_file = LOG_DIR / "error.log"

    def hook(exc_type, exc, tb) -> None:
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        try:
            with log_file.open("a", encoding="utf-8") as fp:
                fp.write(f"\n[{datetime.now():%Y-%m-%d %H:%M:%S}]\n{text}")
        except OSError:
            pass
        sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = hook


def _claim_single_instance() -> bool:
    """用命名互斥体抢占单实例；进程退出（包括崩溃）时系统会自动释放。"""
    global _mutex_handle
    _mutex_handle = _kernel32.CreateMutexW(None, False, MUTEX_NAME)
    return ctypes.get_last_error() != ERROR_ALREADY_EXISTS


def _notify_running_instance(timeout_ms: int = 5000) -> bool:
    """通知已经运行的实例显示窗口；上一个实例可能还在启动，这里重试等待。"""
    from PyQt6.QtNetwork import QLocalSocket

    deadline = time.perf_counter() + timeout_ms / 1000
    while True:
        socket = QLocalSocket()
        socket.connectToServer(SERVER_NAME)
        if socket.waitForConnected(250):
            socket.write(b"show")
            socket.waitForBytesWritten(250)
            socket.disconnectFromServer()
            socket.abort()
            return True
        socket.abort()
        if time.perf_counter() >= deadline:
            return False
        time.sleep(0.15)


def _serve_connections(server, controller) -> None:
    """其它实例再次启动时，把已经运行的窗口拉到前台。"""
    while server.hasPendingConnections():
        connection = server.nextPendingConnection()
        if connection is not None:
            connection.disconnectFromServer()
            connection.deleteLater()
    controller.show_window()


def _self_test() -> int:
    from PyQt6.QtGui import QGuiApplication

    from app.capture.screen import grab_virtual, virtual_rect
    from app.ocr.engine import is_ready as ocr_ready
    from app.paths import DATA_DIR, find_ffmpeg
    from app.record.devices import has_encoder
    from app.translate.service import argos_available

    print("== 环境自检 ==")
    print("Python:", sys.version.split()[0])
    print("Qt:", __import__("PyQt6.QtCore", fromlist=["QT_VERSION_STR"]).QT_VERSION_STR)
    print("数据目录:", DATA_DIR)
    ffmpeg = find_ffmpeg()
    print("ffmpeg:", ffmpeg or "未找到")
    if ffmpeg:
        print("libx264:", has_encoder("libx264"))
    print("离线 OCR:", "就绪" if ocr_ready() else "未安装")
    ok, msg = argos_available()
    print("Argos:", ("就绪 · " + msg) if ok else ("未就绪 · " + msg))
    screens = QGuiApplication.screens()
    print("显示器:", [(s.name(), s.geometry().getRect(), s.devicePixelRatio()) for s in screens])
    pixmap, union = grab_virtual()
    print("抓屏:", union.getRect(), "->", pixmap.width(), "x", pixmap.height())
    print("虚拟桌面:", virtual_rect().getRect())
    return 0


def _run() -> int:
    _setup_dpi()
    _install_excepthook()

    if "--self-test" in sys.argv:
        app = QApplication(sys.argv)
        return _self_test()

    from app.theme import build_qss
    from app.ui.icons import checkmark_path

    app = QApplication(sys.argv)
    app.setApplicationName("MengXingCapture")
    app.setApplicationDisplayName("梦星截屏")
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(build_qss(checkmark_path()))

    # 只允许一个实例：再次双击图标时把已有窗口叫出来，而不是再开一个托盘图标
    if not _claim_single_instance():
        if not _notify_running_instance():
            ctypes.windll.user32.MessageBoxW(
                None,
                "梦星截屏已经在运行，请在系统托盘中查看。",
                "梦星截屏",
                0x40,
            )
        return 0

    from PyQt6.QtCore import QTimer
    from PyQt6.QtNetwork import QLocalServer

    from app.application import AppController

    server = QLocalServer(app)
    QLocalServer.removeServer(SERVER_NAME)
    server.listen(SERVER_NAME)

    controller = AppController(app)
    server.newConnection.connect(lambda: _serve_connections(server, controller))
    # 启动过程中如果有别的实例来敲门，这里补处理一次
    QTimer.singleShot(
        0,
        lambda: _serve_connections(server, controller)
        if server.hasPendingConnections()
        else None,
    )

    if "--tray" not in sys.argv:
        controller.show_window()

    if controller.hotkey_failures and "--tray" not in sys.argv:
        controller.notify("部分快捷键注册失败，请到「设置」中更换组合键。")

    return app.exec()


def main() -> int:
    try:
        return _run()
    except Exception:  # noqa: BLE001
        text = traceback.format_exc()
        try:
            with (LOG_DIR / "error.log").open("a", encoding="utf-8") as fp:
                fp.write(f"\n[{datetime.now():%Y-%m-%d %H:%M:%S}]\n{text}")
        except OSError:
            pass
        try:
            ctypes.windll.user32.MessageBoxW(
                None, "启动失败：\n" + text.strip().splitlines()[-1], "梦星截屏", 0x10
            )
        except Exception:  # noqa: BLE001
            pass
        return 1


if __name__ == "__main__":
    sys.exit(main())
