"""枚举 Windows 上的 DirectShow 音视频设备（麦克风、摄像头、虚拟声卡）。"""
from __future__ import annotations

import re
import subprocess

from ..paths import find_ffmpeg

_DEVICE_RE = re.compile(r'"([^"]+)"\s+\((audio|video)\)')

_SYSTEM_AUDIO_HINTS = (
    "virtual-audio-capturer",
    "stereo mix",
    "立体声混音",
    "what u hear",
    "wave out mix",
    "vb-audio",
    "cable output",
    "voicemeeter",
    "loopback",
)


def list_devices() -> tuple[list[str], list[str]]:
    """返回 (音频设备, 视频设备)。找不到 ffmpeg 时返回空列表。"""
    exe = find_ffmpeg()
    if not exe:
        return [], []
    try:
        proc = subprocess.run(
            [exe, "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        output = (proc.stderr or "") + (proc.stdout or "")
    except (OSError, subprocess.SubprocessError):
        return [], []
    audio: list[str] = []
    video: list[str] = []
    for name, kind in _DEVICE_RE.findall(output):
        name = name.strip()
        if not name or name.lower().startswith("alternative name"):
            continue
        target = audio if kind == "audio" else video
        if name not in target:
            target.append(name)
    return audio, video


def find_system_audio(audio_devices: list[str]) -> str:
    for device in audio_devices:
        low = device.lower()
        if any(hint in low for hint in _SYSTEM_AUDIO_HINTS):
            return device
    return ""


def guess_microphones(audio_devices: list[str]) -> list[str]:
    system = find_system_audio(audio_devices)
    return [d for d in audio_devices if d != system]


def has_encoder(name: str = "libx264") -> bool:
    exe = find_ffmpeg()
    if not exe:
        return False
    try:
        proc = subprocess.run(
            [exe, "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return name in ((proc.stdout or "") + (proc.stderr or ""))
    except (OSError, subprocess.SubprocessError):
        return False
