from __future__ import annotations

from functools import lru_cache
from pathlib import Path


MIN_DIRECT_TEXT_LENGTH = 40


@lru_cache(maxsize=1)
def _get_ocr_engine():
    """在同一进程内复用 OCR 模型，避免每个扫描件重复初始化 ONNX 会话。"""
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError as error:
        raise RuntimeError(
            "缺少 OCR 依赖，请先执行: pip install -r requirements-python.txt"
        ) from error
    return RapidOCR()


def extract_pdf_text(file_path: Path) -> str:
    try:
        import fitz
    except ImportError as error:
        raise RuntimeError(
            "缺少 PyMuPDF 依赖，请先执行: pip install -r requirements-python.txt"
        ) from error

    document = fitz.open(file_path)
    pages: list[str] = []

    try:
        for page in document:
            # 发票 PDF 的文本对象通常按绘制顺序保存，而非票面阅读顺序。若
            # 直接读取，右下角“价税合计（小写）”的金额可能出现在标签之前
            # 或被插入其他表格字段，导致金额识别失败。按坐标排序可使标签和
            # 紧邻金额按票面顺序输出，例如“价税合计（小写）￥22.66”。
            words = page.get_text("words")
            words.sort(key=lambda word: (round(word[1] / 2), word[0]))
            pages.append(" ".join(word[4] for word in words))
    finally:
        document.close()

    return "\n".join(pages)


def extract_pdf_ocr_text(file_path: Path) -> str:
    try:
        import fitz
        import numpy as np
    except ImportError as error:
        raise RuntimeError(
            "缺少 OCR 依赖，请先执行: pip install -r requirements-python.txt"
        ) from error

    engine = _get_ocr_engine()
    document = fitz.open(file_path)
    pages: list[str] = []

    try:
        for page in document:
            pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            channel_count = 3 if pixmap.n < 4 else 4
            image = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
                pixmap.height,
                pixmap.width,
                channel_count,
            )
            result, _ = engine(image)

            if not result:
                continue

            page_text = "\n".join(
                str(item[1]).strip()
                for item in result
                if isinstance(item, (list, tuple)) and len(item) > 1 and str(item[1]).strip()
            )
            if page_text:
                pages.append(page_text)
    finally:
        document.close()

    return "\n".join(pages)


def extract_text(file_path: str | Path, *, enable_ocr: bool = True) -> tuple[str, str, bool]:
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {path}")

    if path.suffix.lower() != ".pdf":
        raise ValueError("当前原型仅支持 PDF 文件。")

    text = extract_pdf_text(path)
    normalized_length = len("".join(text.split()))

    if normalized_length >= MIN_DIRECT_TEXT_LENGTH or not enable_ocr:
        return text, "pdf_text", False

    ocr_text = extract_pdf_ocr_text(path)
    if ocr_text.strip():
        return ocr_text, "ocr", True

    return text, "pdf_text", False
