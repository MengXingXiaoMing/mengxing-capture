"""收集 Ollama 安装包与模型，生成离线包到 vendor/ollama。

用法（在已安装 Ollama、且本地已有模型的电脑上执行）：

    python build/make_ollama_bundle.py --models qwen3:4b --download-setup

生成：
    vendor/ollama/OllamaSetup.exe        （安装包，1.6 GB 左右）
    vendor/ollama/models/blobs/...        （模型权重）
    vendor/ollama/models/manifests/...    （模型清单）

把 vendor/ollama 一起放到程序目录后，目标机器无需联网即可安装并导入模型。
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "vendor" / "ollama"
OLLAMA_MODELS = Path.home() / ".ollama" / "models"
SETUP_URL = "https://ollama.com/download/OllamaSetup.exe"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) MengXingCapture/0.1"


def parse_model(name: str) -> tuple[str, str]:
    repo, _, tag = name.partition(":")
    return repo.strip(), (tag.strip() or "latest")


def manifest_file(repo: str, tag: str) -> Path:
    base = OLLAMA_MODELS / "manifests" / "registry.ollama.ai"
    if "/" in repo:
        namespace, model = repo.split("/", 1)
        return base / namespace / model / tag
    return base / "library" / repo / tag


def collect_model(name: str) -> int:
    repo, tag = parse_model(name)
    manifest = manifest_file(repo, tag)
    if not manifest.is_file():
        raise SystemExit(f"找不到模型清单：{manifest}\n请先执行 ollama pull {name}")
    data = json.loads(manifest.read_text(encoding="utf-8"))

    digests: list[str] = []
    config = data.get("config") or {}
    if config.get("digest"):
        digests.append(config["digest"])
    for layer in data.get("layers", []):
        if layer.get("digest"):
            digests.append(layer["digest"])

    dest_manifest = OUT_DIR / "models" / "manifests" / manifest.relative_to(
        OLLAMA_MODELS / "manifests"
    )
    dest_manifest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(manifest, dest_manifest)

    total = 0
    for digest in digests:
        blob = OLLAMA_MODELS / "blobs" / digest.replace(":", "-")
        if not blob.is_file():
            print(f"  [警告] 缺少 blob：{blob.name}")
            continue
        target = OUT_DIR / "models" / "blobs" / blob.name
        if not target.exists() or target.stat().st_size != blob.stat().st_size:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(blob, target)
        total += blob.stat().st_size
    print(f"  {name}: {total / 1024 ** 3:.2f} GB")
    return total


def download_setup() -> None:
    dest = OUT_DIR / "OllamaSetup.exe"
    if dest.is_file() and dest.stat().st_size > 100 * 1024 * 1024:
        print(f"  安装包已存在：{dest}（{dest.stat().st_size / 1024 ** 3:.2f} GB）")
        return
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("  正在下载 Ollama 安装包（约 1.6 GB）…")
    req = urllib.request.Request(SETUP_URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as resp, dest.open("wb") as fp:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            fp.write(chunk)
            done += len(chunk)
            if total and done % (64 * 1024 * 1024) < 1024 * 1024:
                print(f"    {done * 100 // total}%  ({done // 1024 ** 2} / {total // 1024 ** 2} MB)")
    print(f"  下载完成：{dest}")


def main() -> int:
    parser = argparse.ArgumentParser(description="收集 Ollama 安装包与模型到 vendor/ollama")
    parser.add_argument(
        "--models",
        nargs="*",
        default=["qwen3:4b"],
        help="要打包的模型名，例如 qwen3:4b qwen2.5:7b",
    )
    parser.add_argument(
        "--download-setup",
        action="store_true",
        help="同时下载 Ollama 安装包（约 1.6 GB）",
    )
    args = parser.parse_args()

    if not OLLAMA_MODELS.is_dir():
        print(f"没有找到 Ollama 模型目录：{OLLAMA_MODELS}")
        print("请先安装 Ollama 并拉取模型，例如：ollama pull qwen3:4b")
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("开始收集模型：")
    total = 0
    for name in args.models:
        try:
            total += collect_model(name)
        except SystemExit as exc:
            print(exc)
            return 1

    if args.download_setup:
        download_setup()

    size = sum(f.stat().st_size for f in OUT_DIR.rglob("*") if f.is_file())
    print()
    print(f"完成：{OUT_DIR}")
    print(f"离线包总大小：{size / 1024 ** 3:.2f} GB")
    print("把 vendor/ollama 目录随程序一起拷贝到目标机器即可离线安装。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
