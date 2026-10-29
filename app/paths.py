"""应用路径管理。

所有运行数据（配置、模型、日志、截图、录像）默认都放在程序目录下，
保证绿色便携、不写入系统目录，卸载时删掉文件夹即可。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


APP_ROOT = _app_root()
RESOURCE_DIR = APP_ROOT / "assets"
TOOLS_DIR = APP_ROOT / "tools"


def _pick_data_dir() -> Path:
    """优先使用程序目录下的 userdata（便携），不可写时回退到用户目录。"""
    portable = APP_ROOT / "userdata"
    try:
        portable.mkdir(parents=True, exist_ok=True)
        probe = portable / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return portable
    except OSError:
        base = Path(os.environ.get("APPDATA", Path.home())) / "MengXingCapture"
        base.mkdir(parents=True, exist_ok=True)
        return base


DATA_DIR = _pick_data_dir()
CONFIG_FILE = DATA_DIR / "config.json"
MODEL_DIR = DATA_DIR / "models"
LOG_DIR = DATA_DIR / "logs"
CACHE_DIR = DATA_DIR / "cache"
DEFAULT_CAPTURE_DIR = DATA_DIR / "captures"
DEFAULT_RECORD_DIR = DATA_DIR / "recordings"

for _d in (MODEL_DIR, LOG_DIR, CACHE_DIR, DEFAULT_CAPTURE_DIR, DEFAULT_RECORD_DIR):
    _d.mkdir(parents=True, exist_ok=True)


def ffmpeg_candidates() -> list[Path]:
    """按优先级返回可用的 ffmpeg 路径。"""
    exe = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    return [
        TOOLS_DIR / "ffmpeg" / exe,
        APP_ROOT / exe,
    ]


def find_ffmpeg() -> str | None:
    import shutil

    for p in ffmpeg_candidates():
        if p.is_file():
            return str(p)
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:  # imageio-ffmpeg 自带的静态构建，pip 安装后即可离线使用
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None
