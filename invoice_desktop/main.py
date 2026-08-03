from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PyQt5.QtCore import Qt, QThread, QTimer, QUrl, pyqtSignal
from PyQt5.QtGui import QBrush, QColor, QDesktopServices, QKeySequence
from PyQt5.QtPrintSupport import QPrinter, QPrinterInfo
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFileDialog,
    QGraphicsOpacityEffect,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from invoice_desktop.archive import append_print_archive, get_default_archive_path
from invoice_desktop.printing import build_print_queue, build_summary_sheet_queue, print_pdf_queue
from python_recognizer.types import InvoiceDateSummary, InvoiceOrganizeResult, InvoiceOrganizeSummary
from python_recognizer.workflow import (
    apply_organize_result,
    parse_money_text,
    export_summary_sheet,
    organize_invoice_directory,
)


WARNING_ROW_COLOR = QColor("#FFF7E6")
WARNING_TEXT_COLOR = QColor("#8A5A00")
NORMAL_ROW_COLOR = QColor("#FFFFFF")
SUBSIDY_HEADER_COLOR = QColor("#2F6F98")
APP_VERSION = "1.0.0"
VERSION_UPDATES = [
    (
        "v1.0.0（当前版本）",
        [
            "支持 PDF 发票文本提取与本地 OCR 识别。",
            "支持目录扫描、网约车发票与行程单配对、汇总及重命名。",
            "支持桌面端整理、汇总清单生成、打印与 Excel 归档。",
        ],
    ),
]

APP_STYLE = """
QMainWindow {
    background: #f4efe7;
}
QWidget {
    color: #24384d;
    font-size: 13px;
}
QGroupBox {
    border: 1px solid #d8cdbd;
    border-radius: 18px;
    margin-top: 14px;
    padding: 14px 16px 16px 16px;
    background: #fffaf3;
    font-size: 14px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 6px;
    color: #744e2f;
}
QLabel[role="title"] {
    font-size: 28px;
    font-weight: 700;
    color: #17324d;
}
QLabel[role="subtitle"] {
    color: #6b6257;
    font-size: 13px;
}
QLabel[role="reimbursementReminder"] {
    min-height: 32px;
    padding: 6px 12px;
    border-radius: 10px;
    color: #5c4300;
    background: #FFF1B8;
    font-size: 26px;
    font-weight: 700;
}
QLabel[role="reimbursementReminderCritical"] {
    min-height: 32px;
    padding: 6px 12px;
    border-radius: 10px;
    color: #FFFFFF;
    background: #FF0000;
    font-size: 26px;
    font-weight: 700;
}
QLabel[role="metric"] {
    color: #7c664d;
    font-size: 12px;
}
QLabel[role="metricValue"] {
    color: #17324d;
    font-size: 18px;
    font-weight: 700;
}
QPushButton {
    min-height: 40px;
    padding: 10px 18px;
    border: 1px solid rgba(24, 39, 58, 0.14);
    border-radius: 14px;
    color: #17324d;
    background: #fffdf9;
    font-size: 14px;
    font-weight: 600;
}
QPushButton:hover {
    background: #f7f0e5;
}
QPushButton:pressed {
    background: #efe4d4;
}
QPushButton:disabled {
    color: #9a8e7f;
    background: #f0e9df;
    border-color: rgba(24, 39, 58, 0.08);
}
QPushButton[role="primary"] {
    color: #ffffff;
    border-color: #8d5d2f;
    background: #b86b35;
}
QPushButton[role="primary"]:hover {
    background: #c9773e;
}
QPushButton[role="success"] {
    color: #ffffff;
    border-color: #205b51;
    background: #2f7d6d;
}
QPushButton[role="success"]:hover {
    background: #378975;
}
QPushButton[role="accent"] {
    color: #ffffff;
    border-color: #17496e;
    background: #2f6f98;
}
QPushButton[role="accent"]:hover {
    background: #397ca7;
}
QPushButton[feedback="true"] {
    color: #ffffff;
    border-color: #8d5d2f;
    background: #c9773e;
}
QPushButton[feedback="true"]:hover {
    background: #d28348;
}
QLineEdit {
    min-height: 38px;
    border: 1px solid #d4c7b6;
    border-radius: 12px;
    padding: 0 12px;
    background: #fffdf9;
}
QLineEdit:focus {
    border-color: #b86b35;
}
QTableWidget {
    border: 1px solid #dfd3c4;
    border-radius: 14px;
    background: #ffffff;
    gridline-color: #eadfd1;
    selection-background-color: #f0ddc7;
    selection-color: #17324d;
}
QHeaderView::section {
    background: #efe3d2;
    color: #5f4832;
    padding: 8px;
    border: 0;
    border-right: 1px solid #e1d4c3;
    border-bottom: 1px solid #e1d4c3;
    font-weight: 600;
}
"""


class OrganizeWorker(QThread):
    completed = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(
        self,
        directory: Optional[str] = None,
        *,
        enable_ocr: bool = True,
        apply_changes: bool = False,
        existing_result: Optional[InvoiceOrganizeResult] = None,
    ) -> None:
        super().__init__()
        self.directory = directory
        self.enable_ocr = enable_ocr
        self.apply_changes = apply_changes
        self.existing_result = existing_result

    def run(self) -> None:
        try:
            if self.existing_result is not None:
                result = self.existing_result
            else:
                if not self.directory:
                    raise RuntimeError("未选择待整理目录。")
                result = organize_invoice_directory(self.directory, enable_ocr=self.enable_ocr)

            if self.apply_changes:
                result = apply_organize_result(result)

            self.completed.emit(result)
        except Exception as error:
            self.failed.emit(str(error))


class PrintWorker(QThread):
    progress = pyqtSignal(int, int, str)
    status = pyqtSignal(str)
    completed = pyqtSignal(int, str, str)
    failed = pyqtSignal(str)

    def __init__(
        self,
        result: InvoiceOrganizeResult,
        *,
        queue: list[Path],
        unique_files: int,
        taxi_amount: float,
        subsidy_amount: float,
        in_transit_amount: float,
        travel_in_transit: str,
    ) -> None:
        super().__init__()
        self.result = result
        self.queue = queue
        self.unique_files = unique_files
        self.taxi_amount = taxi_amount
        self.subsidy_amount = subsidy_amount
        self.in_transit_amount = in_transit_amount
        self.travel_in_transit = travel_in_transit

    def _emit_progress(self, current: int, total: int, pdf_path: Path) -> None:
        self.progress.emit(current, total, pdf_path.name)

    def run(self) -> None:
        try:
            printed_jobs = print_pdf_queue(self.queue, progress_callback=self._emit_progress)
        except Exception as error:
            self.failed.emit(str(error))
            return

        archive_path = get_default_archive_path()
        archive_warning = ""
        self.status.emit("正在写入归档 Excel...")
        try:
            archive_path = append_print_archive(
                self.result,
                printed_jobs=printed_jobs,
                unique_files=self.unique_files,
                taxi_amount=self.taxi_amount,
                subsidy_amount=self.subsidy_amount,
                in_transit_amount=self.in_transit_amount,
                travel_in_transit=self.travel_in_transit,
            )
        except Exception as error:
            archive_warning = f"\n归档写入失败：{error}\n默认档案位置：{archive_path}"

        self.completed.emit(printed_jobs, str(archive_path), archive_warning)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.current_result: Optional[InvoiceOrganizeResult] = None
        self.worker: Optional[OrganizeWorker] = None
        self.print_worker: Optional[PrintWorker] = None
        self.print_progress_dialog: Optional[QProgressDialog] = None
        self.current_print_task_label = "打印任务"
        self.manual_summary_mode = False
        self.default_directory = str(Path.home() / "Desktop")
        self.manual_summary_source_directory = str(Path.home() / "Desktop" / "手动汇总")
        self.manual_output_directory = str(Path.home() / "Desktop" / "手动汇总清单输出")
        self.selected_directory = self.default_directory
        self.date_manual_values: dict[str, tuple[str, float, float]] = {}
        self.updating_date_table = False
        self.reminder_blink_state = True
        self.reminder_blink_timer = QTimer(self)
        self.reminder_blink_timer.setInterval(600)
        self.reminder_blink_timer.timeout.connect(self._toggle_reimbursement_reminder)

        self.setWindowTitle("发票管理系统")
        self.resize(1540, 940)
        self.setStyleSheet(APP_STYLE)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(18, 18, 18, 18)
        root_layout.setSpacing(12)

        root_layout.addWidget(self._build_header())
        root_layout.addWidget(self._build_action_group())
        self.date_summary_group = self._build_date_summary_group()
        self.date_summary_group.hide()
        root_layout.addWidget(self.date_summary_group)
        root_layout.addWidget(self._build_detail_group(), 1)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("选择目录后，先执行分析汇总。")
        self._reset_result_views()
        self._update_action_buttons()

    def _build_header(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(6, 0, 6, 0)
        layout.setSpacing(4)

        title = QLabel("发票整理与打印")
        title.setProperty("role", "title")
        subtitle = QLabel("选择文件夹后执行分析汇总，系统会同步完成重命名；确认汇总后可直接打印。")
        subtitle.setProperty("role", "subtitle")
        self.reimbursement_reminder_label = QLabel()
        self.reimbursement_reminder_label.setWordWrap(True)
        self.reimbursement_reminder_opacity = QGraphicsOpacityEffect(self.reimbursement_reminder_label)
        self.reimbursement_reminder_opacity.setOpacity(1.0)
        self.reimbursement_reminder_label.setGraphicsEffect(self.reimbursement_reminder_opacity)
        self._update_reimbursement_reminder()
        self.reminder_blink_timer.start()
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(self.reimbursement_reminder_label)
        return container

    @staticmethod
    def _shift_month(year: int, month: int, offset: int) -> tuple[int, int]:
        month_index = year * 12 + month - 1 + offset
        return month_index // 12, month_index % 12 + 1

    def _get_reimbursement_period(self, current_date):
        if current_date.day >= 26:
            start_date = current_date.replace(day=26)
            next_year, next_month = self._shift_month(current_date.year, current_date.month, 1)
            deadline = current_date.replace(year=next_year, month=next_month, day=25)
        else:
            previous_year, previous_month = self._shift_month(current_date.year, current_date.month, -1)
            start_date = current_date.replace(year=previous_year, month=previous_month, day=26)
            deadline = current_date.replace(day=25)
        return start_date, deadline

    def _update_reimbursement_reminder(self) -> None:
        current_date = datetime.now().date()
        start_date, deadline = self._get_reimbursement_period(current_date)
        remaining_days = (deadline - current_date).days
        background_role = "reimbursementReminderCritical" if remaining_days <= 10 else "reimbursementReminder"
        self.reimbursement_reminder_label.setProperty("role", background_role)
        self.reimbursement_reminder_label.setText(
            f"报销周期：{start_date:%Y年%m月%d日} 至 {deadline:%Y年%m月%d日}　"
            f"距离本期报销截止还有 "
            f"<span style=\"font-size: 36px; font-weight: 700;\">{remaining_days} 天</span>"
            f"（截止日：{deadline:%Y年%m月%d日}）"
        )
        self.reimbursement_reminder_label.style().unpolish(self.reimbursement_reminder_label)
        self.reimbursement_reminder_label.style().polish(self.reimbursement_reminder_label)

    def _toggle_reimbursement_reminder(self) -> None:
        self.reminder_blink_state = not self.reminder_blink_state
        self.reimbursement_reminder_opacity.setOpacity(1.0 if self.reminder_blink_state else 0.35)

    def _build_action_group(self) -> QGroupBox:
        group = QGroupBox("操作步骤")
        layout = QVBoxLayout(group)
        layout.setSpacing(10)

        button_row = QHBoxLayout()
        button_row.setSpacing(10)

        self.choose_button = QPushButton("选择文件夹")
        self.choose_button.setProperty("role", "accent")
        self.choose_button.clicked.connect(self.choose_directory)

        self.directory_status_label = QLabel("未选择时默认使用桌面")
        self.directory_status_label.setProperty("role", "subtitle")

        self.analyze_button = QPushButton("分析汇总")
        self.analyze_button.setProperty("role", "primary")
        self.analyze_button.clicked.connect(self.analyze_directory)

        self.manual_summary_button = QPushButton("手动填写汇总")
        self.manual_summary_button.setProperty("role", "accent")
        self.manual_summary_button.clicked.connect(self.toggle_manual_summary_mode)

        self.print_button = QPushButton("一键打印")
        self.print_button.setProperty("role", "success")
        self.print_button.clicked.connect(self.print_all_documents)

        self.print_summary_button = QPushButton("只打印汇总清单")
        self.print_summary_button.setProperty("role", "accent")
        self.print_summary_button.clicked.connect(self.print_summary_sheet_only)

        self.toggle_date_summary_button = QPushButton("填写补贴/出租车")
        self.toggle_date_summary_button.setProperty("role", "primary")
        self.toggle_date_summary_button.clicked.connect(self.toggle_date_summary)

        self.open_output_button = QPushButton("打开输出目录")
        self.open_output_button.setProperty("role", "success")
        self.open_output_button.clicked.connect(self.open_output_directory)

        self.open_archive_button = QPushButton("打开归档 Excel")
        self.open_archive_button.setProperty("role", "success")
        self.open_archive_button.clicked.connect(self.open_archive_excel)

        self.about_button = QPushButton("关于")
        self.about_button.setProperty("role", "accent")
        self.about_button.clicked.connect(self.show_about)

        button_row.addWidget(self.choose_button)
        button_row.addWidget(self.directory_status_label)
        button_row.addWidget(self.analyze_button)
        button_row.addWidget(self.toggle_date_summary_button)
        button_row.addWidget(self.print_button)
        button_row.addWidget(self.open_archive_button)
        button_row.addWidget(self.open_output_button)
        button_row.addWidget(self.manual_summary_button)
        button_row.addWidget(self.print_summary_button)
        button_row.addWidget(self.about_button)
        button_row.addStretch(1)

        self.phase_label = QLabel("当前状态：等待分析")
        self.phase_label.setProperty("role", "subtitle")

        layout.addLayout(button_row)
        layout.addWidget(self.phase_label)
        return group

    def _build_date_summary_group(self) -> QGroupBox:
        group = QGroupBox("按日期汇总")
        layout = QVBoxLayout(group)

        self.date_table = QTableWidget(0, 9)
        self.date_table.setHorizontalHeaderLabels(
            ["日期", "大众运输", "出租车费用", "过路费", "住宿不含税", "住宿税额", "住宿合计", "在途", "出差补贴"]
        )
        self.date_table.horizontalHeaderItem(8).setForeground(QBrush(SUBSIDY_HEADER_COLOR))
        self.date_table.setEditTriggers(QTableWidget.DoubleClicked | QTableWidget.EditKeyPressed | QTableWidget.AnyKeyPressed)
        self.date_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.date_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.date_table.verticalHeader().setVisible(False)
        self.date_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.date_table.cellChanged.connect(self._on_date_table_cell_changed)
        layout.addWidget(self.date_table)

        confirm_row = QHBoxLayout()
        self.add_date_row_button = QPushButton("新增日期行")
        self.add_date_row_button.setProperty("role", "accent")
        self.add_date_row_button.clicked.connect(self.add_manual_date_row)
        self.remove_date_row_button = QPushButton("删除日期行")
        self.remove_date_row_button.setProperty("role", "accent")
        self.remove_date_row_button.clicked.connect(self.remove_manual_date_row)
        confirm_row.addWidget(self.add_date_row_button)
        confirm_row.addWidget(self.remove_date_row_button)
        confirm_row.addStretch(1)
        self.confirm_subsidy_button = QPushButton("确认补贴/出租车 (Enter/回车)")
        self.confirm_subsidy_button.setProperty("role", "accent")
        self.confirm_subsidy_button.setShortcut(QKeySequence(Qt.Key_Return))
        self.confirm_subsidy_button.setAutoDefault(True)
        self.confirm_subsidy_button.clicked.connect(self.confirm_subsidy_updates)
        confirm_row.addWidget(self.confirm_subsidy_button)
        layout.addLayout(confirm_row)
        return group

    def _build_detail_group(self) -> QGroupBox:
        group = QGroupBox("发票明细")
        layout = QVBoxLayout(group)

        self.table = QTableWidget(0, 13)
        self.table.setHorizontalHeaderLabels(
            [
                "日期",
                "类别",
                "总额",
                "金额",
                "税额",
                "供应商/平台",
                "发票号",
                "原文件名",
                "目标文件名",
                "打印份数",
                "配对状态",
                "复核状态",
                "提示",
            ]
        )
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(7, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(8, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(12, QHeaderView.Stretch)
        layout.addWidget(self.table)
        return group

    def choose_directory(self) -> None:
        initial_directory = self.selected_directory or self.default_directory
        selected_directory = QFileDialog.getExistingDirectory(self, "选择待整理发票目录", initial_directory)
        if selected_directory:
            self.selected_directory = selected_directory
            self.directory_status_label.setText(f"已选择：{Path(selected_directory).name}")
            self._reset_result_views()
            self._update_action_buttons()
            self.phase_label.setText("当前状态：目录已切换，请重新执行分析汇总")

    def analyze_directory(self) -> None:
        directory = self.selected_directory.strip()
        if not directory:
            QMessageBox.warning(self, "未选择目录", "请先选择待整理发票目录。")
            return

        self._run_worker(directory=directory, apply_changes=True, existing_result=None)

    def open_output_directory(self) -> None:
        if self.current_result is None or not self.current_result.applied:
            QMessageBox.warning(self, "输出目录未生成", "请先执行“分析汇总”。")
            return

        QDesktopServices.openUrl(QUrl.fromLocalFile(self.current_result.output_directory))

    def open_archive_excel(self) -> None:
        archive_path = get_default_archive_path()
        if not archive_path.exists():
            QMessageBox.warning(self, "归档文件不存在", f"暂未找到归档 Excel：\n{archive_path}\n\n请先执行一次打印归档。")
            return

        QDesktopServices.openUrl(QUrl.fromLocalFile(str(archive_path)))

    def show_about(self) -> None:
        update_text = "\n\n".join(
            f"{version}\n" + "\n".join(f"• {item}" for item in changes)
            for version, changes in VERSION_UPDATES
        )
        QMessageBox.about(
            self,
            "关于发票管理系统",
            f"<h2>发票管理系统</h2>"
            f"<p>当前版本：<b>v{APP_VERSION}</b></p>"
            f"<p><b>版本更新信息</b></p>"
            f"<p>{update_text.replace(chr(10), '<br>')}</p>",
        )

    def toggle_date_summary(self) -> None:
        should_show = not self.date_summary_group.isVisible()
        self.date_summary_group.setVisible(should_show)
        self.toggle_date_summary_button.setText("收起补贴/出租车填写" if should_show else "填写补贴/出租车")
        if should_show:
            self._focus_first_manual_cell()

    def toggle_manual_summary_mode(self) -> None:
        if self.manual_summary_mode:
            self.manual_summary_mode = False
            self._reset_result_views()
            self.status_bar.showMessage("已退出手动汇总模式。")
            self._update_action_buttons()
            self._update_manual_summary_controls()
            return

        if self.current_result is not None or self.date_table.rowCount() > 0 or self.table.rowCount() > 0:
            confirmation = QMessageBox.question(
                self,
                "切换手动汇总",
                "进入手动汇总模式后，将不再使用当前分析汇总数据。是否继续？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if confirmation != QMessageBox.Yes:
                return

        self.manual_summary_mode = True
        self.current_result = self._build_manual_summary_result([])
        self.table.setRowCount(0)
        self.date_summary_group.show()
        self.toggle_date_summary_button.setText("收起补贴/出租车填写")
        self._fill_manual_date_table()
        self._refresh_summary_artifacts()
        self.phase_label.setText("当前状态：手动汇总模式")
        self.status_bar.showMessage("已进入手动汇总模式，可以新增日期行并手动填写金额。")
        self._update_action_buttons()
        self._update_manual_summary_controls()
        self._focus_first_manual_cell()

    def add_manual_date_row(self) -> None:
        if not self.manual_summary_mode:
            self.toggle_manual_summary_mode()
            if not self.manual_summary_mode:
                return

        self.updating_date_table = True
        insert_row = self._date_data_row_count()
        self.date_table.insertRow(insert_row)
        for column_index, value in enumerate(self._build_empty_manual_row_values()):
            self.date_table.setItem(insert_row, column_index, self._build_date_table_item(value, editable=True))
        self.updating_date_table = False
        self._refresh_date_totals()
        self.date_table.setCurrentCell(insert_row, 0)
        item = self.date_table.item(insert_row, 0)
        if item is not None:
            self.date_table.editItem(item)

    def remove_manual_date_row(self) -> None:
        if not self.manual_summary_mode:
            QMessageBox.warning(self, "当前不是手动模式", "请先进入“手动填写汇总”模式。")
            return

        current_row = self.date_table.currentRow()
        if current_row < 0 or current_row >= self._date_data_row_count():
            QMessageBox.warning(self, "未选择日期行", "请选择要删除的手动日期行。")
            return

        self.updating_date_table = True
        self.date_table.removeRow(current_row)
        self.updating_date_table = False
        self._refresh_date_totals()

    def confirm_subsidy_updates(self) -> None:
        if self.current_result is None or not self.current_result.applied:
            QMessageBox.warning(self, "缺少结果", "请先执行“分析汇总”，再确认补贴和出租车费用。")
            return

        self._commit_date_table_editor()
        self._refresh_date_totals()
        self._refresh_summary_artifacts()
        self._flash_confirm_subsidy_button()
        self.status_bar.showMessage("已确认补贴和出租车费用，并更新打印汇总清单。")

    def _commit_date_table_editor(self) -> None:
        focus_widget = QApplication.focusWidget()
        if focus_widget is not None and focus_widget is not self.confirm_subsidy_button:
            focus_widget.clearFocus()
            self.confirm_subsidy_button.setFocus()
            QApplication.processEvents()

    def _flash_confirm_subsidy_button(self) -> None:
        self.confirm_subsidy_button.setProperty("feedback", True)
        self.confirm_subsidy_button.style().unpolish(self.confirm_subsidy_button)
        self.confirm_subsidy_button.style().polish(self.confirm_subsidy_button)
        self.confirm_subsidy_button.update()
        QTimer.singleShot(220, self._reset_confirm_subsidy_button_feedback)

    def _reset_confirm_subsidy_button_feedback(self) -> None:
        self.confirm_subsidy_button.setProperty("feedback", False)
        self.confirm_subsidy_button.style().unpolish(self.confirm_subsidy_button)
        self.confirm_subsidy_button.style().polish(self.confirm_subsidy_button)
        self.confirm_subsidy_button.update()

    def print_all_documents(self) -> None:
        self._print_with_queue(summary_only=False)

    def print_summary_sheet_only(self) -> None:
        self._print_with_queue(summary_only=True)

    def _print_with_queue(self, *, summary_only: bool) -> None:
        if self.current_result is None:
            QMessageBox.warning(self, "缺少结果", "请先完成分析和重命名。")
            return

        if not self.current_result.applied:
            QMessageBox.warning(self, "未生成整理文件", "请先执行“分析汇总”，生成整理后的 PDF，再进行打印。")
            return

        self._refresh_summary_artifacts()

        default_printer = QPrinterInfo.defaultPrinter()
        if default_printer.isNull():
            QMessageBox.critical(self, "打印失败", "未检测到默认打印机，请先在 Windows 中设置默认打印机。")
            return

        queue = build_summary_sheet_queue(self.current_result) if summary_only else build_print_queue(self.current_result)
        if not queue:
            QMessageBox.warning(
                self,
                "没有可打印文件",
                "未找到可打印的汇总清单 PDF。" if summary_only else "整理结果中没有找到可打印的 PDF。",
            )
            return

        unique_files = len({path.as_posix() for path in queue})
        task_label = "汇总清单" if summary_only else "打印任务"
        confirmation = QMessageBox.question(
            self,
            "确认打印",
            (
                f"将发送打印任务到默认打印机：{default_printer.printerName()}\n"
                f"打印内容：{task_label}\n"
                f"纸张：A5\n"
                f"打印文件数：{unique_files}\n"
                f"打印总份数：{len(queue)}\n\n"
                "是否继续打印？"
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if confirmation != QMessageBox.Yes:
            self.status_bar.showMessage("已取消打印。")
            return

        taxi_amount = self._get_taxi_amount()
        subsidy_amount = self._get_subsidy_amount()
        in_transit_amount = self._get_in_transit_amount()
        travel_in_transit = self._get_travel_in_transit()
        self._start_print_worker(
            queue=queue,
            unique_files=unique_files,
            total_jobs=len(queue),
            taxi_amount=taxi_amount,
            subsidy_amount=subsidy_amount,
            in_transit_amount=in_transit_amount,
            travel_in_transit=travel_in_transit,
            task_label=task_label,
        )

    def _start_print_worker(
        self,
        *,
        queue: list[Path],
        unique_files: int,
        total_jobs: int,
        taxi_amount: float,
        subsidy_amount: float,
        in_transit_amount: float,
        travel_in_transit: str,
        task_label: str,
    ) -> None:
        if self.current_result is None:
            return

        self.current_print_task_label = task_label
        self._set_busy(True)
        self.phase_label.setText(f"当前状态：正在提交{task_label}")
        self.status_bar.showMessage(f"正在向默认打印机发送{task_label}，请稍候...")

        progress_dialog = QProgressDialog("正在准备打印...", None, 0, total_jobs, self)
        progress_dialog.setWindowTitle("打印进度")
        progress_dialog.setWindowModality(Qt.WindowModal)
        progress_dialog.setMinimumDuration(0)
        progress_dialog.setAutoClose(False)
        progress_dialog.setAutoReset(False)
        progress_dialog.setCancelButton(None)
        progress_dialog.setFixedSize(560, 150)
        progress_dialog.setValue(0)
        progress_dialog.show()
        self.print_progress_dialog = progress_dialog

        self.print_worker = PrintWorker(
            self.current_result,
            queue=queue,
            unique_files=unique_files,
            taxi_amount=taxi_amount,
            subsidy_amount=subsidy_amount,
            in_transit_amount=in_transit_amount,
            travel_in_transit=travel_in_transit,
        )
        self.print_worker.progress.connect(self._on_print_progress)
        self.print_worker.status.connect(self._on_print_status)
        self.print_worker.completed.connect(self._on_print_completed)
        self.print_worker.failed.connect(self._on_print_failed)
        self.print_worker.finished.connect(self._on_print_worker_finished)
        self.print_worker.start()

    def _on_print_progress(self, current: int, total: int, file_name: str) -> None:
        if self.print_progress_dialog is not None:
            self.print_progress_dialog.setMaximum(total)
            self.print_progress_dialog.setValue(current)
            self.print_progress_dialog.setLabelText(f"正在发送{self.current_print_task_label} {current}/{total}\n{file_name}")
        self.status_bar.showMessage(f"正在发送{self.current_print_task_label} {current}/{total}：{file_name}")

    def _on_print_status(self, message: str) -> None:
        if self.print_progress_dialog is not None:
            self.print_progress_dialog.setLabelText(message)
        self.status_bar.showMessage(message)

    def _on_print_completed(self, printed_jobs: int, archive_path: str, archive_warning: str) -> None:
        self.phase_label.setText(f"当前状态：{self.current_print_task_label}已提交")
        self.status_bar.showMessage(
            f"已发送 {printed_jobs} 份{self.current_print_task_label}到默认打印机"
            + ("，并写入归档。" if not archive_warning else "，但归档未写入。")
        )
        QMessageBox.information(
            self,
            "打印已提交",
            (
                f"已发送 {printed_jobs} 份{self.current_print_task_label}到默认打印机，纸张默认 A5。\n"
                f"归档文件：{archive_path}"
                f"{archive_warning}"
            ),
        )

    def _on_print_failed(self, message: str) -> None:
        self.phase_label.setText(f"当前状态：{self.current_print_task_label}失败")
        self.status_bar.showMessage(f"{self.current_print_task_label}失败。")
        QMessageBox.critical(self, "打印失败", message)

    def _on_print_worker_finished(self) -> None:
        if self.print_progress_dialog is not None:
            self.print_progress_dialog.close()
            self.print_progress_dialog.deleteLater()
            self.print_progress_dialog = None
        self.print_worker = None
        self._set_busy(False)

    def _run_worker(
        self,
        *,
        directory: str,
        apply_changes: bool,
        existing_result: Optional[InvoiceOrganizeResult],
    ) -> None:
        self._set_busy(True)
        if apply_changes:
            self.phase_label.setText("当前状态：正在分析汇总并执行重命名")
            self.status_bar.showMessage("正在分析汇总、重命名并生成清单，请稍候...")
        else:
            self.phase_label.setText("当前状态：正在分析汇总")
            self.status_bar.showMessage("正在分析目录并汇总金额，请稍候...")

        self.worker = OrganizeWorker(
            directory,
            enable_ocr=True,
            apply_changes=apply_changes,
            existing_result=existing_result,
        )
        self.worker.completed.connect(self._on_completed)
        self.worker.failed.connect(self._on_failed)
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.start()

    def _on_completed(self, result: InvoiceOrganizeResult) -> None:
        self.manual_summary_mode = False
        self.current_result = result
        self._fill_date_table(result)
        self._fill_table(result)

        if result.applied:
            self._refresh_summary_artifacts()
            self.phase_label.setText("当前状态：已完成重命名，可以打印")
            self.status_bar.showMessage(
                f"重命名完成：已生成 {result.output_directory}，现在可以直接打印。"
            )
        else:
            self.phase_label.setText("当前状态：分析完成")
            self.status_bar.showMessage(
                f"分析完成：{result.summary.total_files} 个文件，待复核 {result.summary.review_required} 个。"
            )

        self._update_action_buttons()
        self._update_manual_summary_controls()

    def _on_failed(self, message: str) -> None:
        QMessageBox.critical(self, "处理失败", message)
        self.phase_label.setText("当前状态：处理失败")
        self.status_bar.showMessage("处理失败。")

    def _on_worker_finished(self) -> None:
        self.worker = None
        self._set_busy(False)

    def _set_busy(self, busy: bool) -> None:
        self.choose_button.setEnabled(not busy)
        self.analyze_button.setEnabled(not busy)
        self.manual_summary_button.setEnabled(not busy)
        self.print_button.setEnabled(not busy)
        self.print_summary_button.setEnabled(not busy)
        self.toggle_date_summary_button.setEnabled(not busy)
        self.confirm_subsidy_button.setEnabled(not busy)
        self.add_date_row_button.setEnabled(not busy and self.manual_summary_mode)
        self.remove_date_row_button.setEnabled(not busy and self.manual_summary_mode and self._date_data_row_count() > 0)
        self.open_output_button.setEnabled(not busy)
        self.open_archive_button.setEnabled(not busy)
        self.date_table.setEnabled(not busy)
        if not busy:
            self._update_action_buttons()
            self._update_manual_summary_controls()

    def _update_action_buttons(self) -> None:
        has_result = self.current_result is not None
        has_applied_result = has_result and self.current_result.applied
        is_idle = self.worker is None and self.print_worker is None
        self.manual_summary_button.setText("退出手动汇总" if self.manual_summary_mode else "手动填写汇总")
        self.manual_summary_button.setEnabled(is_idle)
        self.print_button.setEnabled(is_idle and has_applied_result)
        self.print_summary_button.setEnabled(is_idle and has_applied_result)
        self.confirm_subsidy_button.setEnabled(is_idle and has_applied_result)
        self.open_output_button.setEnabled(is_idle and has_applied_result)
        self.open_archive_button.setEnabled(is_idle)

    def _update_manual_summary_controls(self) -> None:
        is_idle = self.worker is None and self.print_worker is None
        self.add_date_row_button.setVisible(self.manual_summary_mode)
        self.remove_date_row_button.setVisible(self.manual_summary_mode)
        self.add_date_row_button.setEnabled(is_idle and self.manual_summary_mode)
        self.remove_date_row_button.setEnabled(is_idle and self.manual_summary_mode and self._date_data_row_count() > 0)

    def _reset_result_views(self) -> None:
        self.current_result = None
        self.manual_summary_mode = False
        self.date_manual_values = {}
        self.date_table.setRowCount(0)
        self.table.setRowCount(0)
        self.date_summary_group.hide()
        self.toggle_date_summary_button.setText("填写补贴/出租车")
        self.phase_label.setText("当前状态：等待分析")
        self._update_manual_summary_controls()

    def _fill_date_table(self, result: InvoiceOrganizeResult) -> None:
        rows = result.summary.daily_breakdown
        self.updating_date_table = True
        self.date_table.setRowCount(len(rows) + 2)

        for row_index, item in enumerate(rows):
            travel_in_transit, taxi_amount, subsidy_amount = self.date_manual_values.get(item.issue_date, ("", 0.0, 0.0))
            values = [
                item.issue_date,
                f"{item.transport_total:.2f}",
                f"{taxi_amount:.2f}" if taxi_amount else "",
                f"{item.toll_total:.2f}",
                f"{item.lodging_amount_total:.2f}",
                f"{item.lodging_tax_total:.2f}",
                f"{item.lodging_total:.2f}",
                travel_in_transit,
                f"{subsidy_amount:.2f}" if subsidy_amount else "",
            ]
            for column_index, value in enumerate(values):
                self.date_table.setItem(
                    row_index,
                    column_index,
                    self._build_date_table_item(value, editable=self._is_date_table_column_editable(column_index)),
                )

        for row_index in range(len(rows), len(rows) + 2):
            for column_index in range(self.date_table.columnCount()):
                self.date_table.setItem(row_index, column_index, self._build_date_table_item("", editable=False, summary=True))

        self.updating_date_table = False
        self._refresh_date_totals()

    def _fill_manual_date_table(self) -> None:
        self.updating_date_table = True
        self.date_table.setRowCount(3)
        for column_index, value in enumerate(self._build_empty_manual_row_values()):
            self.date_table.setItem(0, column_index, self._build_date_table_item(value, editable=True))
        for row_index in range(1, 3):
            for column_index in range(self.date_table.columnCount()):
                self.date_table.setItem(row_index, column_index, self._build_date_table_item("", editable=False, summary=True))
        self.updating_date_table = False
        self._refresh_date_totals()

    def _build_empty_manual_row_values(self) -> list[str]:
        return [datetime.now().strftime("%Y-%m-%d"), "", "", "", "", "", "", "", ""]

    def _focus_first_manual_cell(self) -> None:
        if self._date_data_row_count() == 0:
            return

        focus_column = 0 if self.manual_summary_mode else 2
        self.date_table.setCurrentCell(0, focus_column)
        manual_item = self.date_table.item(0, focus_column)
        if manual_item is not None:
            self.date_table.editItem(manual_item)

    def _build_date_table_item(self, value: str, *, editable: bool, summary: bool = False) -> QTableWidgetItem:
        item = QTableWidgetItem(value)
        if not editable:
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        item.setBackground(QBrush(NORMAL_ROW_COLOR))
        if summary:
            item.setForeground(QBrush(QColor("#5F4832")))
        return item

    def _is_date_table_column_editable(self, column_index: int) -> bool:
        if self.manual_summary_mode:
            return 0 <= column_index <= 8
        return column_index in {2, 7, 8}

    def _date_data_row_count(self) -> int:
        return max(self.date_table.rowCount() - 2, 0)

    def _parse_date_table_money(self, row_index: int, column_index: int) -> float:
        item = self.date_table.item(row_index, column_index)
        if item is None:
            return 0.0
        text = item.text().strip().replace(",", "")
        if not text:
            return 0.0
        try:
            return round(float(text), 2)
        except ValueError:
            return 0.0

    def _sync_date_manual_values(self) -> None:
        values: dict[str, tuple[str, float, float]] = {}
        for row_index in range(self._date_data_row_count()):
            date_item = self.date_table.item(row_index, 0)
            travel_item = self.date_table.item(row_index, 7)
            if date_item is None:
                continue
            issue_date = date_item.text().strip()
            travel_in_transit = travel_item.text().strip() if travel_item is not None else ""
            taxi_amount = self._parse_date_table_money(row_index, 2)
            subsidy_amount = self._parse_date_table_money(row_index, 8)
            existing_travel, existing_taxi, existing_subsidy = values.get(issue_date, ("", 0.0, 0.0))
            combined_travel = "；".join(part for part in [existing_travel, travel_in_transit] if part)
            values[issue_date] = (
                combined_travel,
                round(existing_taxi + taxi_amount, 2),
                round(existing_subsidy + subsidy_amount, 2),
            )
        self.date_manual_values = values

    def _refresh_date_totals(self) -> None:
        if self.updating_date_table or self.date_table.rowCount() < 2:
            return

        self.updating_date_table = True
        self._sync_date_manual_values()

        data_row_count = self._date_data_row_count()
        subtotal_row = data_row_count
        total_row = data_row_count + 1
        money_totals = [
            round(sum(self._parse_date_table_money(row_index, column_index) for row_index in range(data_row_count)), 2)
            for column_index in [1, 2, 3, 4, 5, 6, 8]
        ]
        in_transit_total = round(
            sum(parse_money_text(self.date_table.item(row_index, 7).text()) for row_index in range(data_row_count) if self.date_table.item(row_index, 7) is not None),
            2,
        )
        transport_subtotal = round(money_totals[0] + money_totals[1], 2)
        combined_subsidy_total = round(in_transit_total + money_totals[6], 2)
        grand_total = round(transport_subtotal + money_totals[2] + money_totals[5] + combined_subsidy_total, 2)

        subtotal_values = [
            "小计",
            f"{transport_subtotal:.2f}",
            f"{money_totals[1]:.2f}",
            f"{money_totals[2]:.2f}",
            f"{money_totals[3]:.2f}",
            f"{money_totals[4]:.2f}",
            f"{money_totals[5]:.2f}",
            "",
            f"{combined_subsidy_total:.2f}",
        ]
        total_values = ["总计", f"{grand_total:.2f}", "", "", "", "", "", "", ""]

        for column_index, value in enumerate(subtotal_values):
            self.date_table.setItem(subtotal_row, column_index, self._build_date_table_item(value, editable=False, summary=True))
        for column_index, value in enumerate(total_values):
            self.date_table.setItem(total_row, column_index, self._build_date_table_item(value, editable=False, summary=True))

        self.updating_date_table = False

    def _on_date_table_cell_changed(self, row_index: int, column_index: int) -> None:
        if self.updating_date_table or row_index >= self._date_data_row_count():
            return
        if not self.manual_summary_mode and column_index not in {2, 7, 8}:
            return
        self._refresh_date_totals()
        if self.manual_summary_mode:
            self.status_bar.showMessage("手动汇总已修改，请点击“确认补贴/出租车”更新打印汇总清单。")
        elif self.current_result is not None and self.current_result.applied:
            self.status_bar.showMessage("补贴、在途或出租车费用已修改，请点击“确认补贴/出租车”更新打印汇总清单。")

    def _fill_table(self, result: InvoiceOrganizeResult) -> None:
        self.table.setRowCount(len(result.records))
        self.table.horizontalHeaderItem(8).setText("重命名文件名" if result.applied else "目标文件名")

        for row_index, record in enumerate(result.records):
            values = [
                record.issue_date or "未识别日期",
                record.category,
                f"{record.total_amount:.2f}",
                f"{record.amount:.2f}",
                f"{record.tax_amount:.2f}",
                record.vendor,
                record.number,
                record.source_file,
                Path(record.rename_target).name,
                str(record.print_copies),
                record.pair_status,
                record.review_status,
                "；".join(record.warnings),
            ]

            row_background = WARNING_ROW_COLOR if (record.review_status != "ok" or record.warnings) else NORMAL_ROW_COLOR
            row_foreground = WARNING_TEXT_COLOR if (record.review_status != "ok" or record.warnings) else None

            for column_index, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setBackground(QBrush(row_background))
                if row_foreground is not None:
                    item.setForeground(QBrush(row_foreground))
                self.table.setItem(row_index, column_index, item)

    def _get_subsidy_amount(self) -> float:
        self._sync_date_manual_values()
        return round(sum(subsidy_amount for _, _, subsidy_amount in self.date_manual_values.values()), 2)

    def _get_in_transit_amount(self) -> float:
        self._sync_date_manual_values()
        return round(sum(parse_money_text(travel_in_transit) for travel_in_transit, _, _ in self.date_manual_values.values()), 2)

    def _get_taxi_amount(self) -> float:
        self._sync_date_manual_values()
        return round(sum(taxi_amount for _, taxi_amount, _ in self.date_manual_values.values()), 2)

    def _get_travel_in_transit(self) -> str:
        self._sync_date_manual_values()
        parts = [
            f"{issue_date}：{travel_in_transit}"
            for issue_date, (travel_in_transit, _, _) in self.date_manual_values.items()
            if travel_in_transit
        ]
        return "；".join(parts)

    def _collect_manual_summary_rows(self) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for row_index in range(self._date_data_row_count()):
            text_values = []
            for column_index in range(self.date_table.columnCount()):
                item = self.date_table.item(row_index, column_index)
                text_values.append(item.text().strip() if item is not None else "")

            if not any(text_values):
                continue

            rows.append(
                {
                    "issue_date": text_values[0],
                    "transport_total": self._parse_date_table_money(row_index, 1),
                    "taxi_amount": self._parse_date_table_money(row_index, 2),
                    "toll_total": self._parse_date_table_money(row_index, 3),
                    "lodging_amount_total": self._parse_date_table_money(row_index, 4),
                    "lodging_tax_total": self._parse_date_table_money(row_index, 5),
                    "lodging_total": self._parse_date_table_money(row_index, 6),
                    "travel_in_transit": text_values[7],
                    "subsidy_amount": self._parse_date_table_money(row_index, 8),
                }
            )
        return rows

    def _build_manual_summary_result(self, rows: list[dict[str, object]]) -> InvoiceOrganizeResult:
        grouped_rows: dict[str, dict[str, float]] = {}
        for row in rows:
            issue_date = str(row["issue_date"])
            bucket = grouped_rows.setdefault(
                issue_date,
                {
                    "transport_total": 0.0,
                    "toll_total": 0.0,
                    "lodging_amount_total": 0.0,
                    "lodging_tax_total": 0.0,
                    "lodging_total": 0.0,
                },
            )
            bucket["transport_total"] += float(row["transport_total"])
            bucket["toll_total"] += float(row["toll_total"])
            bucket["lodging_amount_total"] += float(row["lodging_amount_total"])
            bucket["lodging_tax_total"] += float(row["lodging_tax_total"])
            bucket["lodging_total"] += float(row["lodging_total"])

        daily_breakdown = [
            InvoiceDateSummary(
                issue_date=issue_date,
                transport_total=round(bucket["transport_total"], 2),
                toll_total=round(bucket["toll_total"], 2),
                lodging_amount_total=round(bucket["lodging_amount_total"], 2),
                lodging_tax_total=round(bucket["lodging_tax_total"], 2),
                lodging_total=round(bucket["lodging_total"], 2),
                total=round(bucket["transport_total"] + bucket["toll_total"] + bucket["lodging_total"], 2),
            )
            for issue_date, bucket in grouped_rows.items()
        ]
        summary = InvoiceOrganizeSummary(
            total_files=0,
            recognized_files=0,
            review_required=0,
            transport_total=round(sum(bucket["transport_total"] for bucket in grouped_rows.values()), 2),
            toll_total=round(sum(bucket["toll_total"] for bucket in grouped_rows.values()), 2),
            lodging_amount_total=round(sum(bucket["lodging_amount_total"] for bucket in grouped_rows.values()), 2),
            lodging_tax_total=round(sum(bucket["lodging_tax_total"] for bucket in grouped_rows.values()), 2),
            lodging_total=round(sum(bucket["lodging_total"] for bucket in grouped_rows.values()), 2),
            daily_breakdown=daily_breakdown,
        )
        return InvoiceOrganizeResult(
            source_directory=self.manual_summary_source_directory,
            output_directory=self.manual_output_directory,
            applied=True,
            summary_sheet_pdf=str(Path(self.manual_output_directory) / "汇总清单.pdf"),
            summary=summary,
            ride_hailing_pairs=[],
            records=[],
        )

    def _refresh_summary_artifacts(self) -> None:
        if self.manual_summary_mode:
            manual_rows = self._collect_manual_summary_rows()
            self.current_result = self._build_manual_summary_result(manual_rows)

        if self.current_result is None or not self.current_result.applied:
            return
        self._sync_date_manual_values()
        export_summary_sheet(
            self.current_result,
            subsidy_amount=self._get_subsidy_amount(),
            taxi_amount=self._get_taxi_amount(),
            travel_in_transit=self._get_travel_in_transit(),
            daily_manual_values=self.date_manual_values,
        )

def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())