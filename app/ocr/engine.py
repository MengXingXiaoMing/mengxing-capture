"""离线 OCR（RapidOCR + onnxruntime），首次调用时才加载模型。"""
from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtGui import QImage


@dataclass
class OcrLine:
    text: str
    score: float
    box: list[list[float]] | None = None


class OcrError(RuntimeError):
    pass


_ENGINE = None
_BACKEND = ""


def _qimage_to_bgr(image: QImage):
    import numpy as np

    img = image.convertToFormat(QImage.Format.Format_RGBA8888)
    w, h = img.width(), img.height()
    ptr = img.bits()
    ptr.setsize(img.sizeInBytes())
    arr = np.frombuffer(ptr, np.uint8).reshape(h, w, 4)
    return arr[:, :, :3][:, :, ::-1].copy()


def _load_engine():
    global _ENGINE, _BACKEND
    if _ENGINE is not None:
        return _ENGINE
    errors: list[str] = []
    try:  # RapidOCR 2.x
        from rapidocr import RapidOCR

        _ENGINE = RapidOCR()
        _BACKEND = "rapidocr"
        return _ENGINE
    except Exception as exc:  # noqa: BLE001
        errors.append(f"rapidocr: {exc}")
    try:  # RapidOCR 1.x
        from rapidocr_onnxruntime import RapidOCR as LegacyOCR

        _ENGINE = LegacyOCR()
        _BACKEND = "rapidocr_onnxruntime"
        return _ENGINE
    except Exception as exc:  # noqa: BLE001
        errors.append(f"rapidocr_onnxruntime: {exc}")
    raise OcrError(
        "OCR 引擎不可用，请先安装离线识别库：\n"
        "  pip install rapidocr onnxruntime\n"
        "（或 pip install rapidocr-onnxruntime）\n\n" + "\n".join(errors)
    )


def is_ready() -> bool:
    try:
        import importlib.util

        return (
            importlib.util.find_spec("rapidocr") is not None
            or importlib.util.find_spec("rapidocr_onnxruntime") is not None
        )
    except Exception:  # noqa: BLE001
        return False


def recognize(image: QImage) -> list[OcrLine]:
    engine = _load_engine()
    arr = _qimage_to_bgr(image)
    lines: list[OcrLine] = []
    if _BACKEND == "rapidocr":
        result = engine(arr)
        texts = getattr(result, "txts", None)
        if texts is None:
            raw = result[0] if isinstance(result, tuple) else result
            texts = [item[1] for item in (raw or [])]
        scores = getattr(result, "scores", None) or []
        boxes = getattr(result, "boxes", None)
        for i, text in enumerate(texts):
            if not text:
                continue
            score = float(scores[i]) if i < len(scores) else 1.0
            box = None
            if boxes is not None and i < len(boxes):
                try:
                    box = [[float(x), float(y)] for x, y in boxes[i]]
                except (TypeError, ValueError):
                    box = None
            lines.append(OcrLine(str(text).strip(), score, box))
    else:
        result, _elapse = engine(arr)
        for item in result or []:
            try:
                box, text, score = item[0], item[1], item[2]
            except (IndexError, TypeError):
                continue
            if not text:
                continue
            lines.append(
                OcrLine(
                    str(text).strip(),
                    float(score),
                    [[float(x), float(y)] for x, y in box] if box is not None else None,
                )
            )
    return [ln for ln in lines if ln.text]


def lines_to_text(lines: list[OcrLine]) -> str:
    return "\n".join(ln.text for ln in lines)
