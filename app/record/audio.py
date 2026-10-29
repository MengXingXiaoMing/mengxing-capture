"""WASAPI loopback 系统声音采集：直接抓扬声器输出，无需「立体声混音」。"""
from __future__ import annotations

import wave
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

try:
    import pyaudiowpatch as pyaudio
except ImportError:  # pragma: no cover
    pyaudio = None

TARGET_RATE = 48000
TARGET_CHANNELS = 2
CHUNK = 1024


def loopback_available() -> bool:
    if pyaudio is None:
        return False
    api = None
    try:
        api = pyaudio.PyAudio()
        api.get_default_wasapi_loopback()
        return True
    except Exception:  # noqa: BLE001
        return False
    finally:
        if api is not None:
            api.terminate()


class LoopbackRecorder(QThread):
    """把系统播放的声音写成 16bit PCM WAV。"""

    failed = pyqtSignal(str)

    def __init__(self, path: Path, parent=None) -> None:
        super().__init__(parent)
        self._path = path
        self._stop = False
        self._error = ""

    @property
    def error(self) -> str:
        return self._error

    def stop(self, timeout_ms: int = 4000) -> None:
        self._stop = True
        if not self.wait(timeout_ms):
            self.terminate()
            self.wait(1000)

    def run(self) -> None:  # noqa: D401
        if pyaudio is None:
            self._error = "缺少 PyAudioWPatch，无法采集系统声音"
            self.failed.emit(self._error)
            return
        api = None
        stream = None
        try:
            api = pyaudio.PyAudio()
            info = api.get_default_wasapi_loopback()
            rate = int(info.get("defaultSampleRate") or TARGET_RATE)
            channels = max(1, min(TARGET_CHANNELS, int(info.get("maxInputChannels") or 2)))
            stream = api.open(
                format=pyaudio.paInt16,
                channels=channels,
                rate=rate,
                frames_per_buffer=CHUNK,
                input=True,
                input_device_index=info["index"],
            )
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with wave.open(str(self._path), "wb") as wav:
                wav.setnchannels(channels)
                wav.setsampwidth(2)
                wav.setframerate(rate)
                while not self._stop:
                    data = stream.read(CHUNK, exception_on_overflow=False)
                    wav.writeframes(data)
        except Exception as exc:  # noqa: BLE001
            self._error = f"系统声音采集失败：{exc}"
            self.failed.emit(self._error)
        finally:
            if stream is not None:
                try:
                    stream.stop_stream()
                    stream.close()
                except Exception:  # noqa: BLE001
                    pass
            if api is not None:
                api.terminate()
