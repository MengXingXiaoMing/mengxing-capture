"""Ollama 自动下载安装、服务启动与模型拉取。"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Callable

from ..paths import APP_ROOT, DATA_DIR

SETUP_URL = "https://ollama.com/download/OllamaSetup.exe"
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) MengXingCapture/0.1"
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_DETACHED = getattr(subprocess, "DETACHED_PROCESS", 0)

Progress = Callable[[str], None] | None

VENDOR_DIR = APP_ROOT / "vendor" / "ollama"
LOCAL_SETUP = VENDOR_DIR / "OllamaSetup.exe"
LOCAL_MODELS = VENDOR_DIR / "models"


class OllamaInstallError(RuntimeError):
    pass


def _candidates() -> list[Path]:
    local = os.environ.get("LOCALAPPDATA", "")
    paths = []
    if local:
        paths += [
            Path(local) / "Programs" / "Ollama" / "ollama.exe",
            Path(local) / "Programs" / "Ollama" / "ollama app.exe",
        ]
    paths += [
        Path("C:/Program Files/Ollama/ollama.exe"),
        Path("C:/Program Files (x86)/Ollama/ollama.exe"),
    ]
    return paths


def find_ollama() -> str | None:
    found = shutil.which("ollama")
    if found:
        return found
    for path in _candidates():
        if path.is_file():
            return str(path)
    return None


def is_installed() -> bool:
    return find_ollama() is not None


def has_local_setup() -> bool:
    return LOCAL_SETUP.is_file()


def _scan_models(models_root: Path) -> list[str]:
    manifests = models_root / "manifests"
    if not manifests.is_dir():
        return []
    names: list[str] = []
    for path in manifests.rglob("*"):
        if not path.is_file() or path.name.startswith("."):
            continue
        try:
            relative = path.relative_to(manifests).parts
        except ValueError:
            continue
        if len(relative) < 3:
            continue
        registry = relative[0]
        if "library" in relative:
            index = relative.index("library")
            parts = list(relative[index + 1:])
        else:
            parts = [relative[1]] + list(relative[2:])
        if not registry.startswith("registry.") or not parts:
            continue
        if len(parts) >= 2:
            model = f"{'/'.join(parts[:-1])}:{parts[-1]}"
        else:
            model = parts[0]
        names.append(model)
    return sorted(set(names))


def local_model_names() -> list[str]:
    """vendor/ollama/models 里打包好的模型名。"""
    return _scan_models(LOCAL_MODELS)


def user_model_names() -> list[str]:
    """当前用户 ~/.ollama/models 里已安装的模型名（不依赖服务）。"""
    return _scan_models(Path.home() / ".ollama" / "models")


def import_local_models(on_progress: Progress = None) -> int:
    """把离线包里的模型合并到 ~/.ollama/models，返回复制的文件数。"""
    if not LOCAL_MODELS.is_dir():
        return 0
    dest_root = Path.home() / ".ollama" / "models"
    copied = 0
    for sub in ("blobs", "manifests"):
        src = LOCAL_MODELS / sub
        if not src.is_dir():
            continue
        for item in src.rglob("*"):
            if not item.is_file():
                continue
            relative = item.relative_to(src)
            target = dest_root / sub / relative
            if target.exists() and target.stat().st_size == item.stat().st_size:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)
            copied += 1
            if on_progress and copied % 8 == 0:
                on_progress(f"正在导入离线模型…（{copied} 个文件）")
    if on_progress:
        on_progress(f"离线模型导入完成（{copied} 个文件）")
    return copied


def service_alive(url: str = "http://127.0.0.1:11434") -> bool:
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/api/tags", timeout=2):
            return True
    except Exception:  # noqa: BLE001
        return False


def download_installer(on_progress: Progress = None, should_stop: Callable[[], bool] | None = None) -> Path:
    dest = DATA_DIR / "downloads" / "OllamaSetup.exe"
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(SETUP_URL, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp, dest.open("wb") as fp:
            total = int(resp.headers.get("Content-Length") or 0)
            done = 0
            last_pct = -1
            while True:
                if should_stop is not None and should_stop():
                    raise OllamaInstallError("已取消")
                chunk = resp.read(1024 * 512)
                if not chunk:
                    break
                fp.write(chunk)
                done += len(chunk)
                if total and on_progress:
                    pct = done * 100 // total
                    if pct != last_pct:
                        last_pct = pct
                        on_progress(
                            f"正在下载安装包 {pct}%"
                            f"（{done // 1048576} / {total // 1048576} MB）"
                        )
    except OllamaInstallError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise OllamaInstallError(
            "下载 Ollama 安装包失败，请检查网络，或手动到 https://ollama.com/download 安装。\n"
            f"错误：{exc}"
        ) from exc
    if not dest.is_file() or dest.stat().st_size < 10 * 1024 * 1024:
        raise OllamaInstallError("安装包下载不完整，请重试。")
    return dest


def install_installer(setup: Path, on_progress: Progress = None) -> None:
    if on_progress:
        on_progress("正在安装 Ollama（约 1-2 分钟）…")
    try:
        proc = subprocess.run(
            [str(setup), "/VERYSILENT", "/NORESTART", "/SUPPRESSMSGBOXES"],
            capture_output=True,
            timeout=900,
            creationflags=_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise OllamaInstallError(f"启动安装程序失败：{exc}") from exc
    if proc.returncode not in (0, 3010):
        detail = (proc.stderr or b"").decode("utf-8", errors="ignore")[-300:]
        raise OllamaInstallError(f"安装程序返回错误码 {proc.returncode}。{detail}")
    for _ in range(90):
        if is_installed():
            return
        time.sleep(1)
    raise OllamaInstallError("安装完成但未找到 ollama.exe，请重启电脑后再试。")


def start_service(on_progress: Progress = None, url: str = "http://127.0.0.1:11434") -> bool:
    if service_alive(url):
        return True
    exe = find_ollama()
    if not exe:
        return False
    if on_progress:
        on_progress("正在启动 Ollama 服务…")
    try:
        subprocess.Popen(
            [exe, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=_NO_WINDOW | _DETACHED,
        )
    except OSError:
        return False
    for _ in range(30):
        if service_alive(url):
            return True
        time.sleep(1)
    return False


def pull_model(
    model: str,
    on_progress: Progress = None,
    should_stop: Callable[[], bool] | None = None,
) -> None:
    exe = find_ollama()
    if not exe:
        raise OllamaInstallError("未找到 ollama 命令，请先安装 Ollama。")
    if on_progress:
        on_progress(f"正在下载模型 {model}…")
    try:
        proc = subprocess.Popen(
            [exe, "pull", model],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            creationflags=_NO_WINDOW,
        )
    except OSError as exc:
        raise OllamaInstallError(f"启动 ollama pull 失败：{exc}") from exc

    buffer = b""
    assert proc.stdout is not None
    while True:
        if should_stop is not None and should_stop():
            proc.kill()
            raise OllamaInstallError("已取消")
        chunk = proc.stdout.read(256)
        if not chunk:
            break
        buffer += chunk
        if len(buffer) > 4096:
            buffer = buffer[-2048:]
        text = buffer.decode("utf-8", errors="ignore")
        percents = re.findall(r"(\d{1,3})%", text)
        if percents and on_progress:
            on_progress(f"正在下载模型 {percents[-1]}%")
    code = proc.wait()
    if code != 0:
        raise OllamaInstallError("模型下载失败，请确认 Ollama 服务已启动并检查网络。")
    if on_progress:
        on_progress("模型下载完成")
