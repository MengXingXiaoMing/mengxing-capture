"""离线翻译引擎的统一入口：Argos 本地模型 与 Ollama 本地大模型。"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Callable

from . import argos_local


class TranslateError(RuntimeError):
    pass


LANG_NAMES = {
    "zh": "简体中文",
    "zh-tw": "繁体中文",
    "en": "英语",
    "ja": "日语",
    "ko": "韩语",
    "fr": "法语",
    "de": "德语",
    "es": "西班牙语",
    "ru": "俄语",
    "pt": "葡萄牙语",
    "it": "意大利语",
    "ar": "阿拉伯语",
}


def detect_language(text: str) -> str:
    if re.search(r"[\u0600-\u06ff]", text):
        return "ar"
    if re.search(r"[\u0400-\u04ff]", text):
        return "ru"
    if re.search(r"[\uac00-\ud7af]", text):
        return "ko"
    if re.search(r"[\u3040-\u30ff]", text):
        return "ja"
    if re.search(r"[\u4e00-\u9fff]", text):
        return "zh"
    return "en"


def resolve_pair(text: str, source: str, target: str) -> tuple[str, str]:
    src = detect_language(text) if source in ("", "auto") else source
    tgt = target
    if src == tgt:
        tgt = "en" if src != "en" else "zh"
    return src, tgt


# --------------------------------------------------------------------- Argos
def argos_available() -> tuple[bool, str]:
    try:
        if not argos_local.deps_ready():
            return False, argos_local.deps_hint()
        pairs = argos_local.installed_pairs()
        if not pairs:
            return False, "组件已就绪，但还没有语言包（到下方下载或导入）"
        return True, "已安装 " + "、".join(f"{a}→{b}" for a, b in pairs[:6])
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def argos_installed_pairs() -> list[tuple[str, str]]:
    try:
        return argos_local.installed_pairs()
    except Exception:  # noqa: BLE001
        return []


def argos_translate(text: str, source: str, target: str) -> str:
    try:
        return argos_local.translate(text, source, target)
    except argos_local.ArgosLocalError as exc:
        raise TranslateError(str(exc)) from exc


def argos_install_from_file(path: str) -> None:
    try:
        argos_local.install_from_file(path)
    except argos_local.ArgosLocalError as exc:
        raise TranslateError(str(exc)) from exc


def argos_download_pair(
    source: str, target: str, on_progress: Callable[[str], None] | None = None
) -> None:
    try:
        argos_local.download_pair(source, target, on_progress)
    except argos_local.ArgosLocalError as exc:
        raise TranslateError(str(exc)) from exc


def argos_list_available() -> list[tuple[str, str]]:
    try:
        return [(i["from_code"], i["to_code"]) for i in argos_local.ensure_index()]
    except (argos_local.ArgosLocalError, KeyError) as exc:
        raise TranslateError(str(exc)) from exc


# -------------------------------------------------------------------- Ollama
def ollama_models(url: str) -> list[str]:
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/api/tags", timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return [m.get("name", "") for m in data.get("models", []) if m.get("name")]
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return []


def _ollama_request(url: str, model: str, prompt: str, timeout: int = 180) -> str:
    body = json.dumps(
        {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "think": False,
            "options": {"temperature": 0, "num_predict": 1024},
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        url.rstrip("/") + "/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")[:300]
        raise TranslateError(f"Ollama 返回错误 {exc.code}：{detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise TranslateError(
            "连接 Ollama 失败，请确认已启动 Ollama 服务（默认 http://127.0.0.1:11434）。\n"
            f"错误：{exc}"
        ) from exc
    return str(data.get("response", "")).strip()


def ollama_translate_block(
    lines: list[str], source: str, target: str, model: str, url: str
) -> list[str]:
    src_name = LANG_NAMES.get(source, source)
    tgt_name = LANG_NAMES.get(target, target)
    numbered = "\n".join(f"{i + 1}. {line}" for i, line in enumerate(lines))
    prompt = (
        f"你是翻译引擎。把下面的 {src_name} 文本逐行翻译成{tgt_name}。\n"
        "要求：\n"
        "1. 严格保持行数与顺序，每行以「序号. 」开头；\n"
        "2. 只输出译文，不要解释、不要加空行；\n"
        "3. 专有名词、代码、数字保持原样。\n\n"
        f"{numbered}"
    )
    raw = _ollama_request(url, model, prompt)
    result: dict[int, str] = {}
    for line in raw.splitlines():
        m = re.match(r"^\s*(\d+)[.、:：]\s*(.*)$", line)
        if m:
            result[int(m.group(1))] = m.group(2).strip()
        elif result:
            last = max(result)
            result[last] += " " + line.strip()
    if len(result) < max(1, len(lines)) // 2:
        raise TranslateError("Ollama 返回格式无法解析，请换一个指令跟随更好的模型。")
    return [result.get(i + 1, "") or lines[i] for i in range(len(lines))]


# -------------------------------------------------------------------- 统一接口
class TranslationTask:
    """按配置选择引擎执行翻译。"""

    def __init__(self, engine: str, **options) -> None:
        self.engine = engine
        self.options = options

    def translate_lines(
        self,
        lines: list[str],
        source: str,
        target: str,
        on_progress: Callable[[int, int], None] | None = None,
        should_stop: Callable[[], bool] | None = None,
    ) -> list[str]:
        if not any(line.strip() for line in lines):
            return ["" for _ in lines]

        if self.engine == "ollama":
            model = self.options.get("model") or ""
            url = self.options.get("url") or "http://127.0.0.1:11434"
            if not model:
                raise TranslateError("未选择 Ollama 模型，请到「翻译」页面检测并选择。")
            return ollama_translate_block(lines, source, target, model, url)

        try:
            return argos_local.translate_lines(
                lines, source, target, on_progress, should_stop
            )
        except argos_local.ArgosLocalError as exc:
            raise TranslateError(str(exc)) from exc
