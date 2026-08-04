from __future__ import annotations

from pathlib import Path
from typing import Callable

import fitz
from PyQt5.QtCore import Qt, QRectF
from PyQt5.QtGui import QImage, QPainter, QTransform
from PyQt5.QtPrintSupport import QPrinter, QPrinterInfo

from python_recognizer.types import InvoiceOrganizeResult


def _pixmap_to_qimage(pixmap: fitz.Pixmap) -> QImage:
    image_format = QImage.Format_RGB888 if pixmap.alpha == 0 else QImage.Format_RGBA8888
    image = QImage(pixmap.samples, pixmap.width, pixmap.height, pixmap.stride, image_format)
    return image.copy()


def build_print_queue(result: InvoiceOrganizeResult) -> list[Path]:
    queue: list[Path] = []
    queue.extend(build_summary_sheet_queue(result))

    for record in result.records:
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