from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable

import fitz
from PyQt5.QtCore import Qt, QRectF
from PyQt5.QtGui import QImage, QPainter, QTransform
from PyQt5.QtPrintSupport import QPrinter, QPrinterInfo

from python_recognizer.types import InvoiceOrganizeResult


# 汇总合成文件固定使用横向 A5（210 mm × 148 mm）。
A5_WIDTH_POINTS = 595.276
A5_HEIGHT_POINTS = 419.528


def _print_date_sort_key(record) -> tuple[int, datetime, str, str]:
    """按实际发生日期由远及近排列；未识别日期的票据最后打印。"""
    try:
        issue_date = datetime.strptime(record.issue_date, "%Y-%m-%d")
    except (TypeError, ValueError):
        return (1, datetime.max, record.category, record.source_file)
    return (0, issue_date, record.category, record.source_file)


def _pixmap_to_qimage(pixmap: fitz.Pixmap) -> QImage:
    image_format = QImage.Format_RGB888 if pixmap.alpha == 0 else QImage.Format_RGBA8888
    image = QImage(pixmap.samples, pixmap.width, pixmap.height, pixmap.stride, image_format)
    return image.copy()


def build_print_queue(result: InvoiceOrganizeResult) -> list[Path]:
    queue: list[Path] = []
    queue.extend(build_summary_sheet_queue(result))

    for record in sorted(result.records, key=_print_date_sort_key):
        pdf_path = Path(result.source_directory) / record.rename_target
        if not pdf_path.exists():
            continue
        queue.extend([pdf_path] * max(record.print_copies, 0))
    return queue


def build_summary_sheet_queue(result: InvoiceOrganizeResult) -> list[Path]:
    queue: list[Path] = []
    if result.summary_sheet_pdf:
        summary_sheet = Path(result.summary_sheet_pdf)
        if summary_sheet.exists():
            queue.append(summary_sheet)
    return queue


def _get_a5_page_rect(source_rect: fitz.Rect, rotation: int) -> fitz.Rect:
    source_width, source_height = source_rect.width, source_rect.height
    if rotation:
        source_width, source_height = source_height, source_width

    scale = min(A5_WIDTH_POINTS / source_width, A5_HEIGHT_POINTS / source_height)
    width = source_width * scale
    height = source_height * scale
    left = (A5_WIDTH_POINTS - width) / 2
    bottom = (A5_HEIGHT_POINTS - height) / 2
    return fitz.Rect(left, bottom, left + width, bottom + height)


def _choose_a5_rotation(source_rect: fitz.Rect) -> int:
    normal_scale = min(A5_WIDTH_POINTS / source_rect.width, A5_HEIGHT_POINTS / source_rect.height)
    rotated_scale = min(A5_WIDTH_POINTS / source_rect.height, A5_HEIGHT_POINTS / source_rect.width)
    return 90 if rotated_scale > normal_scale else 0


def export_combined_print_pdf(result: InvoiceOrganizeResult) -> Path | None:
    """按一键打印队列生成 A5 的合成 PDF，并保留每份票据的打印份数。"""
    queue = build_print_queue(result)
    if not queue:
        return None

    output_path = Path(result.output_directory) / "汇总合成.pdf"
    if output_path.exists():
        output_path.unlink()

    combined_document = fitz.open()
    try:
        for pdf_path in queue:
            source_document = fitz.open(pdf_path)
            try:
                for page_number, source_page in enumerate(source_document):
                    output_page = combined_document.new_page(width=A5_WIDTH_POINTS, height=A5_HEIGHT_POINTS)
                    rotation = _choose_a5_rotation(source_page.rect)
                    try:
                        output_page.show_pdf_page(
                            _get_a5_page_rect(source_page.rect, rotation),
                            source_document,
                            page_number,
                            rotate=rotation,
                        )
                    except ValueError:
                        # 空白页没有可导入内容，但仍应按打印页数保留为 A5 空白页。
                        pass
            finally:
                source_document.close()
        combined_document.save(str(output_path), garbage=4, deflate=True)
    finally:
        combined_document.close()

    return output_path


def _scaled_area(image: QImage, target_rect: QRectF) -> float:
    scaled = image.scaled(
        int(target_rect.width()),
        int(target_rect.height()),
        Qt.KeepAspectRatio,
        Qt.SmoothTransformation,
    )
    return float(scaled.width() * scaled.height())


def _choose_best_orientation(image: QImage, target_rect: QRectF) -> QImage:
    rotated = image.transformed(QTransform().rotate(90))

    if _scaled_area(rotated, target_rect) > _scaled_area(image, target_rect):
        return rotated

    return image


def _draw_page(page: fitz.Page, printer: QPrinter, painter: QPainter) -> None:
    pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
    image = _pixmap_to_qimage(pixmap)

    target_rect = QRectF(printer.pageRect(QPrinter.DevicePixel))
    best_image = _choose_best_orientation(image, target_rect)
    scaled_image = best_image.scaled(
        int(target_rect.width()),
        int(target_rect.height()),
        Qt.KeepAspectRatio,
        Qt.SmoothTransformation,
    )
    x = target_rect.x() + (target_rect.width() - scaled_image.width()) / 2
    y = target_rect.y() + (target_rect.height() - scaled_image.height()) / 2
    painter.drawImage(QRectF(x, y, scaled_image.width(), scaled_image.height()), scaled_image)


def print_pdf_file(pdf_path: Path, printer: QPrinter, painter: QPainter, first_page: bool) -> bool:
    document = fitz.open(pdf_path)

    try:
        for page in document:
            if first_page:
                first_page = False
            else:
                printer.newPage()
            _draw_page(page, printer, painter)
    finally:
        document.close()

    return first_page


def print_organize_result(
    result: InvoiceOrganizeResult,
    progress_callback: Callable[[int, int, Path], None] | None = None,
) -> int:
    queue = build_print_queue(result)
    return print_pdf_queue(queue, progress_callback=progress_callback)


def print_summary_sheet(
    result: InvoiceOrganizeResult,
    progress_callback: Callable[[int, int, Path], None] | None = None,
) -> int:
    queue = build_summary_sheet_queue(result)
    return print_pdf_queue(queue, progress_callback=progress_callback)


def print_pdf_queue(
    queue: list[Path],
    progress_callback: Callable[[int, int, Path], None] | None = None,
    printer_name: str | None = None,
) -> int:
    printer_info = QPrinterInfo.defaultPrinter()
    if printer_name:
        printer_info = next(
            (
                available_printer
                for available_printer in QPrinterInfo.availablePrinters()
                if available_printer.printerName() == printer_name
            ),
            QPrinterInfo(),
        )

    if printer_info.isNull():
        selected_name = printer_name or "默认打印机"
        if printer_name:
            raise RuntimeError(f"选择的打印机不可用：{selected_name}。请重新选择打印机。")
        raise RuntimeError("未检测到默认打印机，请先在 Windows 中设置默认打印机。")

    if not queue:
        raise RuntimeError("没有可打印的文件。请先执行整理，确保输出目录里已有 PDF。")

    printer = QPrinter(printer_info, QPrinter.HighResolution)
    printer.setPageSize(QPrinter.A5)
    printer.setFullPage(False)
    printer.setColorMode(QPrinter.Color)
    printer.setCopyCount(1)

    painter = QPainter()
    if not painter.begin(printer):
        raise RuntimeError(f"无法启动打印任务：{printer_info.printerName()}")

    try:
        first_page = True
        total_jobs = len(queue)
        for index, pdf_path in enumerate(queue, start=1):
            first_page = print_pdf_file(pdf_path, printer, painter, first_page)
            if progress_callback is not None:
                progress_callback(index, total_jobs, pdf_path)
    finally:
        painter.end()

    return len(queue)