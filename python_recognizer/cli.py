from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .extractors import extract_text
from .heuristics import recognize_invoice_text
from .pairing import pair_ride_hailing_documents
from .workflow import apply_organize_result, organize_invoice_directory


def prompt_for_pdf_file() -> Path:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception as error:
        raise RuntimeError(
            "未提供 PDF 路径，且无法打开文件选择窗口。请直接传入 PDF 路径。"
        ) from error

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    try:
        selected_file = filedialog.askopenfilename(
            title="选择要识别的发票 PDF",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
        )
    finally:
        root.destroy()

    if not selected_file:
        raise RuntimeError("你没有选择任何 PDF 文件。")

    return Path(selected_file)


def prompt_for_directory() -> Path:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception as error:
        raise RuntimeError(
            "未提供目录路径，且无法打开目录选择窗口。请直接传入目录路径。"
        ) from error

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    try:
        selected_dir = filedialog.askdirectory(title="选择网约车发票与行程单所在目录")
    finally:
        root.destroy()

    if not selected_dir:
        raise RuntimeError("你没有选择任何目录。")

    return Path(selected_dir)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="本地发票识别原型：读取 PDF 并输出结构化 JSON")
    parser.add_argument("file", type=Path, nargs="?", help="要识别的 PDF 文件路径；不传时会弹出选择窗口")
    parser.add_argument(
        "--pair-dir",
        type=Path,
        nargs="?",
        const=Path("."),
        help="扫描目录中的 PDF，并自动配对网约车发票与行程单；不传路径时会弹出选择窗口",
    )
    parser.add_argument(
        "--organize-dir",
        type=Path,
        nargs="?",
        const=Path("."),
        help="扫描目录中的 PDF，输出识别结果、汇总、重命名方案和打印份数；不传路径时会弹出选择窗口",
    )
    parser.add_argument("--apply-organize", action="store_true", help="执行整理结果：创建日期目录并复制重命名后的文件")
    parser.add_argument("--pretty", action="store_true", help="格式化输出 JSON")
    parser.add_argument("--no-ocr", action="store_true", help="禁用 OCR 兜底，只使用 PDF 文本层")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.organize_dir:
            target_dir = prompt_for_directory() if args.organize_dir == Path(".") else args.organize_dir
            result = organize_invoice_directory(target_dir, enable_ocr=not args.no_ocr)
            if args.apply_organize:
                result = apply_organize_result(result)
            payload: object = result.to_dict()
        elif args.pair_dir:
            target_dir = prompt_for_directory() if args.pair_dir == Path(".") else args.pair_dir
            results = pair_ride_hailing_documents(target_dir, enable_ocr=not args.no_ocr)
            payload: object = [result.to_dict() for result in results]
        else:
            target_file = args.file or prompt_for_pdf_file()
            text, text_source, ocr_used = extract_text(target_file, enable_ocr=not args.no_ocr)
            result = recognize_invoice_text(text, str(target_file))
            result.text_source = text_source
            result.ocr_used = ocr_used
            payload = result.to_dict()
    except Exception as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1

    indent = 2 if args.pretty else None
    print(json.dumps(payload, ensure_ascii=False, indent=indent))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())