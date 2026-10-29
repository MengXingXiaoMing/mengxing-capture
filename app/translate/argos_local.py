"""轻量 Argos 离线翻译引擎。

直接读取官方 .argosmodel 包（zip 内是 CTranslate2 模型 + SentencePiece 分词器），
不依赖 argostranslate 官方库，从而避免 torch / stanza 这类上百 MB 的重依赖。
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

from ..paths import MODEL_DIR

PKG_DIR = MODEL_DIR / "argos" / "packages"
INDEX_CACHE = MODEL_DIR / "argos" / "index.json"

INDEX_URLS = [
    "https://cdn.jsdelivr.net/gh/argosopentech/argospm-index@main/index.json",
    "https://raw.githubusercontent.com/argosopentech/argospm-index/main/index.json",
    "https://argos-net.com/v1/index.json",
]

CJK_LANGS = {"zh", "ja", "ko"}
_SENT_SPLIT = re.compile(r"(?<=[。！？；!?;])\s*|\n+|(?<=[.])\s+")
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) MengXingCapture/0.1"


class ArgosLocalError(RuntimeError):
    pass


def deps_ready() -> bool:
    return (
        importlib.util.find_spec("ctranslate2") is not None
        and importlib.util.find_spec("sentencepiece") is not None
    )


def deps_hint() -> str:
    return "缺少离线翻译组件，请执行：pip install ctranslate2 sentencepiece"


# --------------------------------------------------------------------- 包管理
def _read_meta(pkg: Path) -> dict | None:
    meta_file = pkg / "metadata.json"
    if not meta_file.is_file():
        return None
    try:
        return json.loads(meta_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def installed_pairs() -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    if not PKG_DIR.is_dir():
        return pairs
    for child in sorted(PKG_DIR.iterdir()):
        if not child.is_dir():
            continue
        meta = _read_meta(child)
        if meta and meta.get("from_code") and meta.get("to_code"):
            pairs.append((str(meta["from_code"]), str(meta["to_code"])))
    return pairs


def has_pair(source: str, target: str) -> bool:
    return (PKG_DIR / f"{source}_{target}").is_dir()


def install_from_file(path: str | Path, on_progress: Callable[[str], None] | None = None) -> tuple[str, str]:
    """安装 .argosmodel（zip）文件，返回语言对。"""
    src = Path(path)
    if not src.is_file():
        raise ArgosLocalError(f"找不到语言包文件：{src}")
    if on_progress:
        on_progress("正在解压语言包…")
    try:
        with zipfile.ZipFile(src) as zf:
            names = zf.namelist()
            meta_name = next(
                (n for n in names if n.endswith("metadata.json") and n.count("/") <= 1), None
            )
            if meta_name is None:
                raise ArgosLocalError("这不是有效的 .argosmodel 文件（缺少 metadata.json）")
            meta = json.loads(zf.read(meta_name).decode("utf-8"))
            root = meta_name.rsplit("/", 1)[0] if "/" in meta_name else ""
            src_code, tgt_code = meta.get("from_code"), meta.get("to_code")
            if not src_code or not tgt_code:
                raise ArgosLocalError("语言包元数据缺少语言代码")
            PKG_DIR.mkdir(parents=True, exist_ok=True)
            dest = PKG_DIR / f"{src_code}_{tgt_code}"

            with tempfile.TemporaryDirectory() as tmp:
                for name in names:
                    if name.endswith("/"):
                        continue
                    if root and not name.startswith(root + "/"):
                        continue
                    if "/stanza/" in name or name.endswith(".pt"):
                        continue  # stanza 分词模型用不到，跳过以节省空间
                    relative = name[len(root) + 1:] if root else name
                    target = Path(tmp) / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(name) as fsrc, target.open("wb") as fdst:
                        shutil.copyfileobj(fsrc, fdst, 1024 * 256)
                filled = Path(tmp)
                tokenizer_ok = (
                    (filled / "sentencepiece.model").is_file()
                    or (filled / "bpe.model").is_file()
                )
                if not (filled / "model").is_dir() or not tokenizer_ok:
                    raise ArgosLocalError("语言包内容不完整（缺少 model 或分词器文件）")
                if dest.exists():
                    shutil.rmtree(dest, ignore_errors=True)
                shutil.move(tmp, str(dest))
    except zipfile.BadZipFile as exc:
        raise ArgosLocalError("语言包文件损坏，请重新下载。") from exc
    _MODELS.pop((str(src_code), str(tgt_code)), None)
    if on_progress:
        on_progress("安装完成")
    return str(src_code), str(tgt_code)


def ensure_index(force: bool = False) -> list[dict]:
    if not force and INDEX_CACHE.is_file():
        age = time.time() - INDEX_CACHE.stat().st_mtime
        if age < 7 * 86400:
            try:
                return json.loads(INDEX_CACHE.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass
    last_error = ""
    for url in INDEX_URLS:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": _UA})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read().decode("utf-8")
            items = json.loads(data)
            if isinstance(items, list) and items:
                INDEX_CACHE.parent.mkdir(parents=True, exist_ok=True)
                INDEX_CACHE.write_text(data, encoding="utf-8")
                return items
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            continue
    if INDEX_CACHE.is_file():
        try:
            return json.loads(INDEX_CACHE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    raise ArgosLocalError(
        "无法获取语言包索引（需要联网一次）。\n"
        "如果本机没有网络，可以在有网的电脑上下载 .argosmodel 文件，再回来用「导入」安装。\n"
        f"错误：{last_error}"
    )


def route_pairs(
    source: str, target: str, available: Callable[[tuple[str, str]], bool]
) -> list[tuple[str, str]] | None:
    """返回可用的翻译路径；没有直接语言包时用英语做中转。"""
    if available((source, target)):
        return [(source, target)]
    if source != "en" and target != "en":
        via = [(source, "en"), ("en", target)]
        if all(available(pair) for pair in via):
            return via
    return None


def installed_route(source: str, target: str) -> list[tuple[str, str]] | None:
    return route_pairs(source, target, lambda pair: has_pair(*pair))


def missing_route_hint(source: str, target: str) -> str:
    installed = set(installed_pairs())
    need: list[str] = []
    if (source, "en") not in installed:
        need.append(f"{source} → en")
    if ("en", target) not in installed:
        need.append(f"en → {target}")
    detail = "、".join(need) if need else f"{source} → {target}"
    return (
        f"还没有 {source} → {target} 的离线语言包。\n"
        f"到「翻译 → Argos 离线语言包」点一下对应按钮即可下载，"
        f"程序会自动补上中转所需的 {detail}。"
    )


def _download_one(item: dict, on_progress: Callable[[str], None] | None = None) -> tuple[str, str]:
    links = item.get("links") or []
    if not links:
        raise ArgosLocalError("该语言包没有可用下载地址。")
    src_code, tgt_code = item.get("from_code"), item.get("to_code")
    url = links[0]
    tmp_file = Path(tempfile.gettempdir()) / f"argos_{src_code}_{tgt_code}.argosmodel"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=120) as resp, tmp_file.open("wb") as fp:
            total = int(resp.headers.get("Content-Length") or 0)
            done = 0
            while True:
                chunk = resp.read(1024 * 512)
                if not chunk:
                    break
                fp.write(chunk)
                done += len(chunk)
                if on_progress and total:
                    on_progress(f"正在下载 {src_code}→{tgt_code} {done * 100 // total}%")
        return install_from_file(tmp_file, on_progress)
    except ArgosLocalError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ArgosLocalError(f"下载失败：{exc}") from exc
    finally:
        tmp_file.unlink(missing_ok=True)


def download_pair(
    source: str, target: str, on_progress: Callable[[str], None] | None = None
) -> tuple[str, str]:
    items = ensure_index()
    available = {
        (i.get("from_code"), i.get("to_code")) for i in items if i.get("from_code")
    }
    route = route_pairs(source, target, lambda pair: pair in available)
    if route is None:
        raise ArgosLocalError(
            f"官方索引里没有可用的 {source} → {target} 路径（直接或经英语中转）。"
        )
    result = (source, target)
    for pair in route:
        if has_pair(*pair):
            continue
        item = next(
            i for i in items
            if (i.get("from_code"), i.get("to_code")) == pair
        )
        if on_progress:
            on_progress(f"正在下载 {pair[0]} → {pair[1]} 语言包…")
        result = _download_one(item, on_progress)
    return result


# --------------------------------------------------------------------- 推理
_MODELS: dict[tuple[str, str], tuple] = {}
_MODEL_ORDER: list[tuple[str, str]] = []


def _load_model(source: str, target: str):
    key = (source, target)
    if key in _MODELS:
        return _MODELS[key]
    if not deps_ready():
        raise ArgosLocalError(deps_hint())
    pkg = PKG_DIR / f"{source}_{target}"
    if not pkg.is_dir():
        raise ArgosLocalError(
            f"缺少 {source} → {target} 的离线语言包。请到「翻译」页面下载或导入。"
        )
    try:
        import ctranslate2
        import sentencepiece as spm
    except Exception as exc:  # noqa: BLE001
        raise ArgosLocalError(deps_hint()) from exc
    try:
        tokenizer_file = pkg / "sentencepiece.model"
        if not tokenizer_file.is_file():
            if (pkg / "bpe.model").is_file():
                raise ArgosLocalError(
                    "这个语言包使用 BPE 分词器，当前离线引擎暂不支持。\n"
                    "可以改用 Ollama 引擎翻译该语言，或换一个语言包。"
                )
            raise ArgosLocalError("语言包缺少分词器文件，请重新下载。")
        tokenizer = spm.SentencePieceProcessor(model_file=str(tokenizer_file))
        translator = ctranslate2.Translator(
            str(pkg / "model"),
            device="cpu",
            compute_type="int8",
            inter_threads=1,
            intra_threads=max(2, min(8, (os.cpu_count() or 4) // 2)),
        )
    except Exception as exc:  # noqa: BLE001
        raise ArgosLocalError(f"加载语言模型失败：{exc}") from exc

    _MODELS[key] = (translator, tokenizer)
    _MODEL_ORDER.append(key)
    while len(_MODEL_ORDER) > 2:  # 最多同时缓存两个语言对，避免占用过多内存
        old = _MODEL_ORDER.pop(0)
        _MODELS.pop(old, None)
    return translator, tokenizer


def split_sentences(text: str) -> list[str]:
    parts = _SENT_SPLIT.split(text)
    return [p.strip() for p in parts if p and p.strip()]


def _clean(text: str, target: str) -> str:
    if target in CJK_LANGS:
        return text.replace("▁", "").strip()
    return text.replace("▁", " ").strip()


def _translate_once(text: str, source: str, target: str) -> str:
    translator, tokenizer = _load_model(source, target)
    sentences = split_sentences(text)
    if not sentences:
        return ""
    batch = [tokenizer.encode(s, out_type=str) for s in sentences]
    try:
        results = translator.translate_batch(batch, beam_size=4, max_decoding_length=512)
    except Exception as exc:  # noqa: BLE001
        raise ArgosLocalError(f"翻译推理失败：{exc}") from exc
    outputs = [_clean(tokenizer.decode(r.hypotheses[0]), target) for r in results]
    joiner = "" if target in CJK_LANGS else " "
    return joiner.join(o for o in outputs if o)


def translate(text: str, source: str, target: str) -> str:
    if not text.strip():
        return ""
    route = installed_route(source, target)
    if route is None:
        raise ArgosLocalError(missing_route_hint(source, target))
    current = text
    for step_source, step_target in route:
        current = _translate_once(current, step_source, step_target)
    return current


def _translate_lines_once(
    lines: list[str],
    source: str,
    target: str,
    on_progress: Callable[[int, int], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> list[str]:
    out = list(lines)
    pending: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        if not line.strip() or not re.search(r"\w", line):
            continue
        pending.append((index, line))
    if not pending:
        return out

    translator, tokenizer = _load_model(source, target)
    chunk = 24
    total = len(pending)
    for start in range(0, total, chunk):
        if should_stop is not None and should_stop():
            raise InterruptedError("cancelled")
        part = pending[start:start + chunk]
        batch = [tokenizer.encode(line, out_type=str) for _i, line in part]
        try:
            results = translator.translate_batch(batch, beam_size=4, max_decoding_length=512)
        except Exception as exc:  # noqa: BLE001
            raise ArgosLocalError(f"翻译推理失败：{exc}") from exc
        for (index, original), result in zip(part, results):
            out[index] = _clean(tokenizer.decode(result.hypotheses[0]), target) or original
        if on_progress:
            on_progress(min(total, start + len(part)), total)
    return out


def translate_lines(
    lines: list[str],
    source: str,
    target: str,
    on_progress: Callable[[int, int], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> list[str]:
    """逐行翻译并保持行对齐（OCR 对照用）；缺直接语言包时经英语中转。"""
    route = installed_route(source, target)
    if route is None:
        raise ArgosLocalError(missing_route_hint(source, target))
    out = list(lines)
    for step_index, (step_source, step_target) in enumerate(route):
        out = _translate_lines_once(
            out, step_source, step_target, on_progress, should_stop
        )
        if should_stop is not None and should_stop():
            raise InterruptedError("cancelled")
    return out
