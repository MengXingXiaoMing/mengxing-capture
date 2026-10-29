"""基于 ffmpeg 的屏幕录制（区域 / 全屏 / 窗口），支持暂停续录与音频混流。"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QElapsedTimer, QObject, QProcess, QTimer, pyqtSignal

from ..config import CONFIG
from ..paths import CACHE_DIR, find_ffmpeg
from ..record.audio import LoopbackRecorder, loopback_available
from ..record.devices import has_encoder
from ..capture.screen import primary_dpr


def even(value: int) -> int:
    return max(2, value - (value % 2))


@dataclass
class RecordOptions:
    target: str = "region"                  # region / fullscreen / window
    rect: tuple[int, int, int, int] | None = None
    fps: int = 30
    crf: int = 23
    preset: str = "veryfast"
    system_audio: str = ""
    mic: str = ""
    camera: str = ""
    camera_size: int = 260
    camera_corner: str = "br"
    draw_cursor: bool = True
    output_dir: Path = field(default_factory=lambda: Path(CONFIG.get("record.save_dir")))


class RecordError(RuntimeError):
    pass


class Recorder(QObject):
    state_changed = pyqtSignal(str)     # recording / paused / stopping / idle
    failed = pyqtSignal(str)
    finished = pyqtSignal(str)          # 成品文件
    tick = pyqtSignal(int)              # 已录制秒数
    ready = pyqtSignal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._proc: QProcess | None = None
        self._opts: RecordOptions | None = None
        self._session: Path | None = None
        self._final_path = Path(".")
        self._segments: list[Path] = []
        self._audios: list[Path] = []
        self._audio: LoopbackRecorder | None = None
        self._phase = "idle"
        self._elapsed = QElapsedTimer()
        self._accumulated_ms = 0
        self._timer = QTimer(self)
        self._timer.setInterval(400)
        self._timer.timeout.connect(self._on_tick)
        self._use_x264 = True
        self._last_error = ""

    # ------------------------------------------------------------------ 属性
    @property
    def phase(self) -> str:
        return self._phase

    @property
    def active(self) -> bool:
        return self._phase in ("recording", "paused", "stopping")

    def elapsed_seconds(self) -> int:
        ms = self._accumulated_ms
        if self._phase == "recording" and self._elapsed.isValid():
            ms += self._elapsed.elapsed()
        return max(0, ms // 1000)

    # ------------------------------------------------------------------ 启动
    def start(self, options: RecordOptions) -> None:
        if self.active:
            raise RecordError("已经在录制中")
        exe = find_ffmpeg()
        if not exe:
            raise RecordError(
                "没有找到 ffmpeg。\n\n"
                "解决办法（任选其一）：\n"
                "1. 执行 pip install imageio-ffmpeg（本程序会自动使用它自带的 ffmpeg）；\n"
                "2. 把 ffmpeg.exe 放到程序目录的 tools/ffmpeg/ 下；\n"
                "3. 把 ffmpeg 加入系统 PATH。"
            )
        if options.target != "fullscreen" and options.rect is None:
            raise RecordError("请先选择要录制的区域或窗口")
        self._opts = options
        self._use_x264 = has_encoder("libx264")
        self._segments.clear()
        self._audios.clear()
        self._accumulated_ms = 0
        self._last_error = ""
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._session = CACHE_DIR / f"rec_{stamp}"
        self._session.mkdir(parents=True, exist_ok=True)
        self._final_path = (Path(options.output_dir) / f"录屏_{stamp}.mp4").resolve()
        self._phase = "recording"
        self._elapsed.start()
        self._timer.start()
        self._start_segment()
        self.state_changed.emit("recording")

    def _start_segment(self) -> None:
        assert self._opts is not None and self._session is not None
        index = len(self._segments)
        seg = self._session / f"seg_{index:03d}.mp4"
        if self._opts.system_audio:
            wav = self._session / f"seg_{index:03d}.wav"
            self._audio = LoopbackRecorder(wav)
            self._audio.failed.connect(self._on_audio_failed)
            self._audio.start()
            self._audios.append(wav)
        args = self._build_args(self._opts, seg)
        proc = QProcess(self)
        proc.setProgram(find_ffmpeg() or "ffmpeg")
        proc.setArguments(args)
        proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        proc.readyReadStandardOutput.connect(self._drain)
        proc.finished.connect(lambda code, _st: self._on_segment_finished(code))
        self._proc = proc
        proc.start()
        if not proc.waitForStarted(4000):
            self._fail("无法启动 ffmpeg 进程，请检查安装是否完整。")
            return
        self._segments.append(seg)
        QTimer.singleShot(700, self._verify_running)

    def _on_audio_failed(self, message: str) -> None:
        self._last_error = message

    def _stop_audio(self) -> None:
        audio = self._audio
        self._audio = None
        if audio is not None:
            audio.stop()

    def _verify_running(self) -> None:
        if self._phase != "recording" or self._proc is None:
            return
        if self._proc.state() == QProcess.ProcessState.NotRunning:
            code = self._proc.exitCode()
            if code != 0:
                self._fail(self._last_error or f"ffmpeg 启动失败（退出码 {code}）")

    def _build_args(self, opts: RecordOptions, out_path: Path) -> list[str]:
        args = ["-hide_banner", "-y"]
        args += ["-f", "gdigrab", "-framerate", str(opts.fps),
                 "-draw_mouse", "1" if opts.draw_cursor else "0"]
        if opts.target != "fullscreen" and opts.rect:
            # 选区是 Qt 逻辑坐标，gdigrab 需要物理像素，按屏幕缩放换算
            dpr = primary_dpr()
            x, y, w, h = opts.rect
            x, y = int(round(x * dpr)), int(round(y * dpr))
            w, h = int(round(w * dpr)), int(round(h * dpr))
            args += ["-offset_x", str(x), "-offset_y", str(y),
                     "-video_size", f"{even(w)}x{even(h)}"]
        args += ["-i", "desktop"]

        audio_idx: list[int] = []
        idx = 1
        if opts.mic:
            args += ["-f", "dshow", "-audio_buffer_size", "50", "-i", f"audio={opts.mic}"]
            audio_idx.append(idx)
            idx += 1
        cam_idx = None
        if opts.camera:
            args += ["-f", "dshow", "-i", f"video={opts.camera}"]
            cam_idx = idx
            idx += 1

        filters = ["[0:v]scale=trunc(iw/2)*2:trunc(ih/2)*2[base]"]
        if cam_idx is not None:
            pos_map = {
                "br": "W-w-24:H-h-24",
                "bl": "24:H-h-24",
                "tr": "W-w-24:24",
                "tl": "24:24",
            }
            pos = pos_map.get(opts.camera_corner, "W-w-24:H-h-24")
            filters.append(f"[{cam_idx}:v]scale={even(opts.camera_size)}:-2[cam]")
            filters.append(f"[base][cam]overlay={pos}[vout]")
        else:
            filters.append("[base]null[vout]")

        if len(audio_idx) == 2:
            filters.append(
                f"[{audio_idx[0]}:a]aformat=sample_fmts=fltp:sample_rates=48000:"
                f"channel_layouts=stereo[a1]"
            )
            filters.append(
                f"[{audio_idx[1]}:a]aformat=sample_fmts=fltp:sample_rates=48000:"
                f"channel_layouts=stereo[a2]"
            )
            filters.append("[a1][a2]amix=inputs=2:duration=longest:dropout_transition=0[aout]")
        elif len(audio_idx) == 1:
            filters.append(
                f"[{audio_idx[0]}:a]aformat=sample_fmts=fltp:sample_rates=48000:"
                f"channel_layouts=stereo[aout]"
            )

        args += ["-filter_complex", ";".join(filters), "-map", "[vout]"]
        if audio_idx:
            args += ["-map", "[aout]"]

        if self._use_x264:
            args += ["-c:v", "libx264", "-preset", opts.preset, "-crf", str(opts.crf),
                     "-pix_fmt", "yuv420p", "-g", str(max(2, opts.fps * 2))]
        else:
            args += ["-c:v", "mpeg4", "-q:v", "4", "-pix_fmt", "yuv420p"]
        if audio_idx:
            args += ["-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2"]
        args += ["-movflags", "+faststart", str(out_path)]
        return args

    # ------------------------------------------------------------------ 暂停/停止
    def pause(self) -> None:
        if self._phase != "recording":
            return
        self._phase = "pausing"
        self._accumulated_ms += self._elapsed.elapsed()
        self.state_changed.emit("pausing")
        self._stop_audio()
        self._graceful_stop()

    def resume(self) -> None:
        if self._phase != "paused":
            return
        self._phase = "recording"
        self._elapsed.start()
        self._start_segment()
        self.state_changed.emit("recording")

    def stop(self) -> None:
        if not self.active or self._phase == "stopping":
            return
        if self._phase == "recording":
            self._accumulated_ms += self._elapsed.elapsed()
        self._phase = "stopping"
        self._timer.stop()
        self.state_changed.emit("stopping")
        self._stop_audio()
        if self._proc is not None and self._proc.state() != QProcess.ProcessState.NotRunning:
            self._graceful_stop()
        else:
            self._finalize()

    def cancel(self) -> None:
        """放弃本次录制并清理临时文件。"""
        self._phase = "idle"
        self._timer.stop()
        self._stop_audio()
        if self._proc is not None and self._proc.state() != QProcess.ProcessState.NotRunning:
            self._proc.kill()
            self._proc.waitForFinished(2000)
        self._proc = None
        if self._session and self._session.exists():
            shutil.rmtree(self._session, ignore_errors=True)
        self.state_changed.emit("idle")

    def _graceful_stop(self) -> None:
        proc = self._proc
        if proc is None:
            return
        try:
            proc.write(b"q\n")
            proc.closeWriteChannel()
        except Exception:  # noqa: BLE001
            pass
        if not proc.waitForFinished(5000):
            proc.terminate()
            if not proc.waitForFinished(2500):
                proc.kill()
                proc.waitForFinished(1500)

    def _drain(self) -> None:
        if self._proc is None:
            return
        data = bytes(self._proc.readAllStandardOutput()).decode("utf-8", errors="ignore")
        for line in data.splitlines():
            low = line.lower()
            if "error" in low or "invalid" in low or "unable" in low or "could not" in low:
                self._last_error = line.strip()[:400]

    def _on_segment_finished(self, code: int) -> None:
        if self._phase == "pausing":
            self._phase = "paused"
            self.state_changed.emit("paused")
            return
        if self._phase == "stopping":
            self._finalize()
            return
        if self._phase == "recording" and code != 0:
            self._fail(self._last_error or f"录制意外中断（退出码 {code}）")

    # ------------------------------------------------------------------ 收尾
    def _finalize(self) -> None:
        session = self._session
        segments = [s for s in self._segments if s.exists() and s.stat().st_size > 1024]
        audios = [a for a in self._audios if a.exists() and a.stat().st_size > 1024]
        self._proc = None
        if not segments or session is None:
            self._fail("没有生成有效的录制文件，请检查显卡驱动或换一个录制区域重试。")
            return
        out = self._final_path
        out.parent.mkdir(parents=True, exist_ok=True)
        try:
            if audios:
                self._combine_with_audio(segments, audios, session, out)
            elif len(segments) == 1:
                shutil.move(str(segments[0]), str(out))
            else:
                self._concat_video(segments, session, out)
        except (OSError, RecordError) as exc:
            self._fail(f"合并录像失败：{exc}")
            return
        shutil.rmtree(session, ignore_errors=True)
        self._phase = "idle"
        self.state_changed.emit("idle")
        self.finished.emit(str(out))

    def _combine_with_audio(
        self, segments: list[Path], audios: list[Path], session: Path, out: Path
    ) -> None:
        exe = find_ffmpeg()
        if not exe:
            raise RecordError("ffmpeg 不可用")
        video_part = session / "video_part.mp4"
        if len(segments) == 1:
            shutil.copy2(segments[0], video_part)
        else:
            self._concat_video(segments, session, video_part)

        audio_part = session / "system_part.wav"
        if len(audios) == 1:
            shutil.copy2(audios[0], audio_part)
        else:
            self._concat_wav(audios, session, audio_part)

        if self._opts is not None and self._opts.mic:
            args = [
                exe, "-hide_banner", "-y", "-i", str(video_part), "-i", str(audio_part),
                "-filter_complex",
                "[0:a][1:a]amix=inputs=2:duration=longest:dropout_transition=0[a]",
                "-map", "0:v", "-map", "[a]", "-c:v", "copy",
                "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out),
            ]
        else:
            args = [
                exe, "-hide_banner", "-y", "-i", str(video_part), "-i", str(audio_part),
                "-map", "0:v", "-map", "1:a", "-c:v", "copy",
                "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out),
            ]
        ok, err = self._run_ffmpeg(args, session)
        if not ok or not out.exists() or out.stat().st_size < 1024:
            raise RecordError(f"音视频合并失败。\n{err}")

    def _concat_wav(self, audios: list[Path], session: Path, out: Path) -> None:
        list_file = session / "wav_list.txt"
        list_file.write_text(
            "\n".join(f"file '{a.name}'" for a in audios) + "\n", encoding="utf-8"
        )
        exe = find_ffmpeg()
        if not exe:
            raise RecordError("ffmpeg 不可用")
        base = [exe, "-hide_banner", "-y", "-f", "concat", "-safe", "0", "-i", "wav_list.txt"]
        ok, err1 = self._run_ffmpeg(base + ["-c", "copy", str(out)], session)
        if not ok or not out.exists() or out.stat().st_size < 1024:
            ok, err2 = self._run_ffmpeg(base + ["-c:a", "pcm_s16le", str(out)], session)
            if not ok:
                raise RecordError(f"音频合并失败。\n{err2 or err1}")

    def _concat_video(self, segments: list[Path], session: Path, out: Path) -> None:
        list_file = session / "list.txt"
        lines = []
        for seg in segments:
            name = seg.name.replace("'", r"'\''")
            lines.append(f"file '{name}'")
        list_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        exe = find_ffmpeg()
        if not exe:
            raise RecordError("ffmpeg 不可用")
        base = [exe, "-hide_banner", "-y", "-f", "concat", "-safe", "0", "-i", "list.txt"]
        ok, err1 = self._run_ffmpeg(base + ["-c", "copy", "-movflags", "+faststart", str(out)], session)
        if not ok or not out.exists() or out.stat().st_size < 1024:
            ok, err2 = self._run_ffmpeg(
                base
                + ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                   "-c:a", "aac", "-movflags", "+faststart", str(out)],
                session,
            )
            if not ok:
                raise RecordError(f"ffmpeg 合并失败。\n{err2 or err1}")

    @staticmethod
    def _run_ffmpeg(args: list[str], cwd: Path) -> tuple[bool, str]:
        try:
            proc = subprocess.run(
                args, cwd=str(cwd), capture_output=True, timeout=600,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            err = proc.stderr.decode("utf-8", errors="ignore")[-900:]
            return proc.returncode == 0, err
        except (OSError, subprocess.SubprocessError) as exc:
            return False, str(exc)

    def _fail(self, message: str) -> None:
        self._phase = "idle"
        self._timer.stop()
        self._stop_audio()
        if self._proc is not None and self._proc.state() != QProcess.ProcessState.NotRunning:
            self._proc.kill()
            self._proc.waitForFinished(1000)
        self._proc = None
        if self._session and self._session.exists():
            shutil.rmtree(self._session, ignore_errors=True)
        self.state_changed.emit("idle")
        self.failed.emit(message)

    def _on_tick(self) -> None:
        self.tick.emit(self.elapsed_seconds())


def export_gif(video_path: str, fps: int = 12, width: int = 720) -> str:
    """把 mp4 转成 GIF，返回 gif 路径。"""
    exe = find_ffmpeg()
    if not exe:
        raise RecordError("ffmpeg 不可用，无法导出 GIF")
    src = Path(video_path)
    dst = src.with_suffix(".gif")
    vf = (
        f"fps={fps},scale={width}:-1:flags=lanczos,split[s0][s1];"
        f"[s0]palettegen=max_colors=192[p];[s1][p]paletteuse=dither=bayer"
    )
    proc = subprocess.run(
        [exe, "-hide_banner", "-y", "-i", str(src), "-vf", vf, str(dst)],
        capture_output=True, timeout=900,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if proc.returncode != 0 or not dst.exists():
        raise RecordError("GIF 导出失败：" + proc.stderr.decode("utf-8", errors="ignore")[-300:])
    return str(dst)


def format_duration(seconds: int) -> str:
    h, rem = divmod(max(0, seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
