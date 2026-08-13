from __future__ import annotations

import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

try:
    from chinese_calendar import is_holiday
except ImportError:
    is_holiday = None

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PyQt5.QtCore import QDate, QSettings, Qt, QThread, QTimer, QUrl, pyqtSignal
from PyQt5.QtGui import QBrush, QColor, QDesktopServices, QKeySequence
from PyQt5.QtPrintSupport import QPrinter, QPrinterInfo
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QAction,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDateEdit,
    QFileDialog,
    QFormLayout,
    QGraphicsOpacityEffect,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QInputDialog,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from invoice_desktop.archive import append_print_archive, get_default_archive_path
from invoice_desktop.mail_fetcher import fetch_qq_invoice_attachments
from invoice_desktop.printing import build_print_queue, build_summary_sheet_queue, export_combined_print_pdf, print_pdf_queue
from invoice_desktop.secrets_store import protect_secret, unprotect_secret
from python_recognizer.types import InvoiceDateSummary, InvoiceOrganizeResult, InvoiceOrganizeSummary
from python_recognizer.workflow import (
    apply_organize_result,
    collect_summary_issues,
    parse_money_text,
    export_summary_sheet,
    organize_invoice_directory,
)


WARNING_ROW_COLOR = QColor("#FFF7E6")
WARNING_TEXT_COLOR = QColor("#C62828")
NORMAL_ROW_COLOR = QColor("#FFFFFF")
SUBTOTAL_ROW_COLOR = QColor("#E8F5E9")
SUBSIDY_HEADER_COLOR = QColor("#2F6F98")
APP_VERSION = "1.0.7"
DEFAULT_PUBLIC_DISK_ADDRESS = r"\\18.18.1.2"
PUBLIC_DISK_UPLOAD_DIRECTORY_SETTING = "publicDisk/uploadDirectory"
TRIP_FORM_URL = "https://scloud.syntecclub.com/LoginForm.aspx"
MAIL_ACCOUNT_SETTING = "mailFetch/account"
MAIL_AUTH_CODE_SETTING = "mailFetch/authCodeProtected"
AUTO_START_VALUE_NAME = "SYNTEC-InvoiceManager"
VSCODE_EXECUTABLE_LOCATIONS = (
    Path.home() / "AppData" / "Local" / "Programs" / "Microsoft VS Code" / "Code.exe",
    Path(r"C:\Program Files\Microsoft VS Code\Code.exe"),
    Path(r"C:\Program Files (x86)\Microsoft VS Code\Code.exe"),
)
VERSION_UPDATES = [
    (
        "v1.0.7（当前版本）",
        [
            "新增 QQ 邮箱发票抓取：按收件日期下载、筛选并按现有规则重命名 PDF。",
            "邮箱抓取前增加 VS Code 安装检测，并支持初始化清除保存的 QQ 邮箱账号与 IMAP 授权码。",
            "修正高速通行费电子发票命名，使用票面发票号码而非发票代码；配套行程单使用对应发票号码命名。",
        ],
    ),
    (
        "v1.0.6",
        [
            "公共盘上传会包含带发票号码的票据及配套行程单，并排除汇总文件。",
            "打印机设定与开机自启动调整为顶部“设定”菜单下的独立弹窗。",
        ],
    ),
    (
        "v1.0.5",
        [
            "新增每日网约车打车间隔统计，并写入行程单提示与归档备注。",
            "新增 Windows 开机自启动开关。",
        ],
    ),
    (
        "v1.0.4",
        [
            "局域公共盘上传目标可自由选择，并自动记忆上次成功使用的文件夹。",
        ],
    ),
    (
        "v1.0.3",
        [
            "移除 QQ 邮箱拉取发票功能，保留本地文件夹整理流程。",
            "优化界面自适应、按日期小计显示和局域公共盘上传规则。",
            "生成汇总清单改为覆盖既有归档文件。",
        ],
    ),
    (
        "v1.0.2",
        [
            "新增 PDF 上传到局域公共盘入口，可将输出 PDF 复制到公共盘发票上传目录。",
        ],
    ),
    (
        "v1.0.1",
        [
            "新增“关于”入口，可查看当前版本号与版本更新信息。",
        ],
    ),
    (
        "v1.0.0",
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
    font-size: 20px;
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
    font-size: 18px;
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
QPushButton[role="tripForm"] {
    color: #24324A;
    border: 2px solid #F4B400;
    background: #FFF3C4;
    font-weight: 700;
}
QPushButton[role="tripForm"]:hover {
    background: #FFE69A;
    border-color: #D69200;
}
QPushButton[role="qqMail"] {
    color: #FFFFFF;
    border: 2px solid #7B1FA2;
    background: #9C27B0;
    font-weight: 700;
}
QPushButton[role="qqMail"]:hover {
    background: #B238C6;
    border-color: #65117F;
}
QPushButton[role="danger"] {
    color: #ffffff;
    border-color: #b71c1c;
    background: #d32f2f;
}
QPushButton[role="danger"]:hover {
    background: #e53935;
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


class MailFetchWorker(QThread):
    completed = pyqtSignal(str, int)
    failed = pyqtSignal(str)

    def __init__(self, account: str, authorization_code: str, start_date, end_date) -> None:
        super().__init__()
        self.account = account
        self.authorization_code = authorization_code
        self.start_date = start_date
        self.end_date = end_date

    def run(self) -> None:
        try:
            output_directory, copied_count = fetch_qq_invoice_attachments(
                account=self.account,
                authorization_code=self.authorization_code,
                start_date=self.start_date,
                end_date=self.end_date,
            )
            self.completed.emit(str(output_directory), copied_count)
        except Exception as error:
            self.failed.emit(str(error))


class MailInvoiceFetchDialog(QDialog):
    def __init__(self, settings: QSettings, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("邮箱发票抓取")
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        notice = QLabel("此功能需要电脑有安装 VSCODE 2022 版本，且有配置AI环境。")
        notice.setStyleSheet("color: #C62828; font-weight: 700;")
        layout.addWidget(notice)
        layout.addWidget(QLabel("通过 QQ 邮箱 IMAP 安全抓取；授权码使用 Windows 当前用户加密保存。"))

        form = QFormLayout()
        self.account_input = QLineEdit(str(settings.value(MAIL_ACCOUNT_SETTING, "") or ""))
        self.auth_code_input = QLineEdit(unprotect_secret(str(settings.value(MAIL_AUTH_CODE_SETTING, "") or "")))
        self.auth_code_input.setEchoMode(QLineEdit.Password)
        self.start_date_input = QDateEdit(QDate.currentDate())
        self.end_date_input = QDateEdit(QDate.currentDate())
        for date_input in (self.start_date_input, self.end_date_input):
            date_input.setCalendarPopup(True)
            date_input.setDisplayFormat("yyyy-MM-dd")
        form.addRow("QQ 邮箱账号：", self.account_input)
        form.addRow("IMAP 授权码：", self.auth_code_input)
        form.addRow("抓取起始日期：", self.start_date_input)
        form.addRow("抓取结束日期：", self.end_date_input)
        layout.addLayout(form)
        layout.addWidget(QLabel("日期范围为左闭右闭；将生成桌面“发票起始日期至结束日期”文件夹。"))
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).setText("确认抓取")
        self.buttons.button(QDialogButtonBox.Cancel).setText("取消")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        footer_row = QHBoxLayout()
        self.initialize_button = QPushButton("初始化")
        self.initialize_button.setProperty("role", "danger")
        self.initialize_button.setToolTip("清除已保存的 QQ 邮箱账号与 IMAP 授权码")
        self.initialize_button.clicked.connect(self.initialize_mail_settings)
        footer_row.addWidget(self.initialize_button)
        footer_row.addStretch(1)
        footer_row.addWidget(self.buttons)
        layout.addLayout(footer_row)

    def values(self):
        return (
            self.account_input.text().strip(),
            self.auth_code_input.text(),
            self.start_date_input.date().toPyDate(),
            self.end_date_input.date().toPyDate(),
        )

    @staticmethod
    def is_vscode_installed() -> bool:
        """检测 Visual Studio Code 是否已安装，兼容用户安装和系统安装。"""
        if shutil.which("code") or shutil.which("Code.exe"):
            return True
        return any(executable.is_file() for executable in VSCODE_EXECUTABLE_LOCATIONS)

    def accept(self) -> None:
        account, authorization_code, start_date, end_date = self.values()
        if not self.is_vscode_installed():
            QMessageBox.warning(
                self,
                "未检测到 VS Code",
                "此电脑未检测到 Visual Studio Code（VSCODE 2022）。\n"
                "请先安装并完成 AI 环境配置后，再执行邮箱发票抓取。",
            )
            return
        if not account or not authorization_code:
            QMessageBox.warning(self, "信息不完整", "请填写 QQ 邮箱账号和 IMAP 授权码。")
            return
        if start_date > end_date:
            QMessageBox.warning(self, "日期错误", "起始日期不能晚于结束日期。")
            return
        self.settings.setValue(MAIL_ACCOUNT_SETTING, account)
        self.settings.setValue(MAIL_AUTH_CODE_SETTING, protect_secret(authorization_code))
        self.settings.sync()
        super().accept()

    def initialize_mail_settings(self) -> None:
        """清除当前用户保存的 QQ 邮箱账号和加密授权码。"""
        self.settings.remove(MAIL_ACCOUNT_SETTING)
        self.settings.remove(MAIL_AUTH_CODE_SETTING)
        self.settings.sync()
        self.account_input.clear()
        self.auth_code_input.clear()
        QMessageBox.information(self, "初始化完成", "已清除保存的 QQ 邮箱账号和 IMAP 授权码。")


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
        printer_name: str,
    ) -> None:
        super().__init__()
        self.result = result
        self.queue = queue
        self.unique_files = unique_files
        self.taxi_amount = taxi_amount
        self.subsidy_amount = subsidy_amount
        self.in_transit_amount = in_transit_amount
        self.travel_in_transit = travel_in_transit
        self.printer_name = printer_name

    def _emit_progress(self, current: int, total: int, pdf_path: Path) -> None:
        self.progress.emit(current, total, pdf_path.name)

    def run(self) -> None:
        try:
            printed_jobs = print_pdf_queue(
                self.queue,
                progress_callback=self._emit_progress,
                printer_name=self.printer_name,
            )
        except Exception as error:
            self.failed.emit(str(error))
            return

        self.completed.emit(printed_jobs, "", "")


class PublicDiskUploadDialog(QDialog):
    def __init__(
        self,
        output_directory: Path,
        initial_public_disk_address: str,
        invoice_pdf_names: list[str],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.output_directory = output_directory
        self.setWindowTitle("PDF上传到局域公共盘")
        self.resize(680, 460)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        output_label = QLabel(f"输出文件夹：{output_directory}")
        output_label.setWordWrap(True)
        layout.addWidget(output_label)

        self.file_list = QListWidget()
        for file_name in sorted(invoice_pdf_names, key=str.casefold):
            file_path = output_directory / file_name
            if file_path.is_file() and file_path.suffix.lower() == ".pdf":
                self.file_list.addItem(file_name)
        layout.addWidget(self.file_list, 1)

        address_label = QLabel("上传目标文件夹")
        self.address_input = QLineEdit(initial_public_disk_address)
        self.choose_target_button = QPushButton("选择文件夹")
        self.choose_target_button.setProperty("role", "accent")
        self.choose_target_button.clicked.connect(self.choose_target_directory)
        address_row = QHBoxLayout()
        address_row.addWidget(self.address_input, 1)
        address_row.addWidget(self.choose_target_button)
        layout.addWidget(address_label)
        layout.addLayout(address_row)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).setText("YES")
        self.buttons.button(QDialogButtonBox.Cancel).setText("NO")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def public_disk_address(self) -> str:
        return self.address_input.text().strip()

    def choose_target_directory(self) -> None:
        selected_directory = QFileDialog.getExistingDirectory(
            self,
            "选择局域公共盘上传文件夹",
            self.public_disk_address() or DEFAULT_PUBLIC_DISK_ADDRESS,
        )
        if selected_directory:
            self.address_input.setText(selected_directory)

    def listed_pdf_files(self) -> list[Path]:
        files = []
        for row_index in range(self.file_list.count()):
            file_path = self.output_directory / self.file_list.item(row_index).text()
            if file_path.suffix.lower() == ".pdf":
                files.append(file_path)
        return files


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.current_result: Optional[InvoiceOrganizeResult] = None
        self.worker: Optional[OrganizeWorker] = None
        self.mail_fetch_worker: Optional[MailFetchWorker] = None
        self.print_worker: Optional[PrintWorker] = None
        self.print_progress_dialog: Optional[QProgressDialog] = None
        self.current_print_task_label = "打印任务"
        self.manual_summary_mode = False
        self.default_directory = str(Path.home() / "Desktop")
        self.manual_summary_source_directory = str(Path.home() / "Desktop" / "手动汇总")
        self.manual_output_directory = str(Path.home() / "Desktop" / "手动汇总清单输出")
        self.selected_directory = self.default_directory
        self.settings = QSettings("SYNTEC", "InvoiceManager")
        self.selected_printer_name = self._load_selected_printer_name()
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
        self.settings_dialog = self._build_settings_dialog()
        self.auto_start_settings_dialog = self._build_auto_start_settings_dialog()
        self._build_menu_bar()
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

    def _build_menu_bar(self) -> None:
        """创建标准软件菜单栏，菜单项用于打开对应的设定或说明窗口。"""
        menu_bar = self.menuBar()
        menu_bar.setNativeMenuBar(False)

        self.settings_menu = menu_bar.addMenu("设定")
        self.printer_settings_action = QAction("打印机设定", self)
        self.printer_settings_action.triggered.connect(self.show_printer_settings)
        self.settings_menu.addAction(self.printer_settings_action)
        self.auto_start_action = QAction("开机自启动", self)
        self.auto_start_action.triggered.connect(self.show_auto_start_settings)
        self.settings_menu.addAction(self.auto_start_action)

        self.help_menu = menu_bar.addMenu("帮助")
        self.about_action = QAction("关于 / 更新说明", self)
        self.about_action.triggered.connect(self.show_about)
        self.help_menu.addAction(self.about_action)

    def _build_settings_dialog(self) -> QDialog:
        dialog = QDialog(self)
        dialog.setWindowTitle("打印机设定")
        dialog.setModal(True)
        dialog.resize(620, 230)

        root_layout = QVBoxLayout(dialog)
        root_layout.setSpacing(12)
        printer_group = QGroupBox("打印机设定")
        printer_layout = QVBoxLayout(printer_group)
        printer_layout.setSpacing(10)

        description = QLabel("选择打印机后，系统会记住本次选择，下次启动继续使用。")
        description.setWordWrap(True)
        printer_layout.addWidget(description)

        printer_row = QHBoxLayout()
        self.printer_button = QPushButton("选择打印机")
        self.printer_button.setProperty("role", "accent")
        self.printer_button.clicked.connect(self.choose_printer)
        self.printer_status_label = QLabel()
        self.printer_status_label.setProperty("role", "subtitle")
        self._update_printer_status_label()
        printer_row.addWidget(self.printer_button)
        printer_row.addWidget(self.printer_status_label, 1)
        printer_layout.addLayout(printer_row)
        root_layout.addWidget(printer_group)
        root_layout.addStretch(1)

        close_button = QPushButton("关闭")
        close_button.clicked.connect(dialog.accept)
        root_layout.addWidget(close_button, 0, Qt.AlignRight)
        return dialog

    def _build_auto_start_settings_dialog(self) -> QDialog:
        dialog = QDialog(self)
        dialog.setWindowTitle("开机自启动")
        dialog.setModal(True)
        dialog.resize(620, 230)

        root_layout = QVBoxLayout(dialog)
        root_layout.setSpacing(12)
        auto_start_group = QGroupBox("开机自启动")
        auto_start_layout = QVBoxLayout(auto_start_group)
        auto_start_layout.setSpacing(10)
        auto_start_description = QLabel("开启后，当前 Windows 用户登录时会自动启动发票管理系统。")
        auto_start_description.setWordWrap(True)
        auto_start_layout.addWidget(auto_start_description)
        self.auto_start_checkbox = QCheckBox("开启开机自启动")
        self.auto_start_checkbox.setChecked(self._is_auto_start_enabled())
        self.auto_start_checkbox.toggled.connect(self.set_auto_start_enabled)
        auto_start_layout.addWidget(self.auto_start_checkbox)
        root_layout.addWidget(auto_start_group)
        root_layout.addStretch(1)

        close_button = QPushButton("关闭")
        close_button.clicked.connect(dialog.accept)
        root_layout.addWidget(close_button, 0, Qt.AlignRight)
        return dialog

    def show_printer_settings(self) -> None:
        self.settings_dialog.exec_()

    def show_auto_start_settings(self) -> None:
        self.auto_start_settings_dialog.exec_()

    @staticmethod
    def _auto_start_command() -> str:
        if getattr(sys, "frozen", False):
            return f'"{Path(sys.executable).resolve()}"'
        return f'"{Path(sys.executable).resolve()}" -m invoice_desktop.main'

    def _is_auto_start_enabled(self) -> bool:
        if sys.platform != "win32":
            return False
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
                value, _ = winreg.QueryValueEx(key, AUTO_START_VALUE_NAME)
            return value == self._auto_start_command()
        except (FileNotFoundError, OSError):
            return False

    def set_auto_start_enabled(self, enabled: bool) -> None:
        if sys.platform != "win32":
            QMessageBox.warning(self, "不支持", "开机自启动仅支持 Windows。")
            return
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_SET_VALUE,
            ) as key:
                if enabled:
                    winreg.SetValueEx(key, AUTO_START_VALUE_NAME, 0, winreg.REG_SZ, self._auto_start_command())
                else:
                    try:
                        winreg.DeleteValue(key, AUTO_START_VALUE_NAME)
                    except FileNotFoundError:
                        pass
        except OSError as error:
            self._sync_auto_start_controls(not enabled)
            QMessageBox.critical(self, "设置失败", f"无法更新开机自启动设置：\n{error}")
            return

        self._sync_auto_start_controls(enabled)
        self.status_bar.showMessage("已开启开机自启动。" if enabled else "已关闭开机自启动。")

    def _sync_auto_start_controls(self, enabled: bool) -> None:
        self.auto_start_checkbox.blockSignals(True)
        self.auto_start_checkbox.setChecked(enabled)
        self.auto_start_checkbox.blockSignals(False)

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
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(self.reimbursement_reminder_label)
        return container

    @staticmethod
    def _shift_month(year: int, month: int, offset: int) -> tuple[int, int]:
        month_index = year * 12 + month - 1 + offset
        return month_index // 12, month_index % 12 + 1

    def _get_reimbursement_period(self, current_date):
        if current_date.day >= 21:
            start_date = current_date.replace(day=26)
            next_year, next_month = self._shift_month(current_date.year, current_date.month, 1)
            deadline = current_date.replace(year=next_year, month=next_month, day=20)
        else:
            previous_year, previous_month = self._shift_month(current_date.year, current_date.month, -1)
            start_date = current_date.replace(year=previous_year, month=previous_month, day=26)
            deadline = current_date.replace(day=20)
        return start_date, deadline

    def _update_reimbursement_reminder(self) -> None:
        current_date = datetime.now().date()
        start_date, deadline = self._get_reimbursement_period(current_date)
        remaining_days = (deadline - current_date).days
        should_blink = remaining_days <= 10
        background_role = "reimbursementReminderCritical" if should_blink else "reimbursementReminder"
        self.reimbursement_reminder_label.setProperty("role", background_role)
        self.reimbursement_reminder_label.setText(
            f"报销周期：{start_date:%Y年%m月%d日} 至 {deadline:%Y年%m月%d日}　"
            f"距离本期报销截止还有 "
            f"<span style=\"font-size: 36px; font-weight: 700;\">{remaining_days} 天</span>"
            f"（截止日：{deadline:%Y年%m月%d日}）"
        )
        self.reimbursement_reminder_label.style().unpolish(self.reimbursement_reminder_label)
        self.reimbursement_reminder_label.style().polish(self.reimbursement_reminder_label)
        self.reminder_blink_state = True
        self.reimbursement_reminder_opacity.setOpacity(1.0)
        if should_blink:
            self.reminder_blink_timer.start()
        else:
            self.reminder_blink_timer.stop()

    def _toggle_reimbursement_reminder(self) -> None:
        if self.reimbursement_reminder_label.property("role") != "reimbursementReminderCritical":
            self.reimbursement_reminder_opacity.setOpacity(1.0)
            return
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

        self.upload_public_disk_button = QPushButton("pdf上传到局域公共盘")
        self.upload_public_disk_button.setProperty("role", "success")
        self.upload_public_disk_button.clicked.connect(self.upload_pdfs_to_public_disk)

        self.open_archive_button = QPushButton("生成汇总清单并打开")
        self.open_archive_button.setProperty("role", "success")
        self.open_archive_button.clicked.connect(self.generate_archive_excel)

        self.trip_form_button = QPushButton("✈  出差单填写")
        self.trip_form_button.setProperty("role", "tripForm")
        self.trip_form_button.clicked.connect(self.open_trip_form)

        self.qq_mail_button = QPushButton("✉  打开QQ邮箱")
        self.qq_mail_button.setProperty("role", "qqMail")
        self.qq_mail_button.clicked.connect(self.open_qq_mail)

        self.mail_fetch_button = QPushButton("邮箱发票抓取")
        self.mail_fetch_button.setProperty("role", "primary")
        self.mail_fetch_button.clicked.connect(self.fetch_mail_invoices)

        self.phase_label = QLabel("当前状态：等待分析")
        self.phase_label.setProperty("role", "subtitle")

        button_row.addWidget(self.choose_button)
        button_row.addWidget(self.directory_status_label)
        button_row.addWidget(self.analyze_button)
        button_row.addWidget(self.toggle_date_summary_button)
        button_row.addWidget(self.open_archive_button)
        button_row.addWidget(self.open_output_button)
        button_row.addWidget(self.upload_public_disk_button)
        button_row.addWidget(self.print_button)
        button_row.addWidget(self.manual_summary_button)
        button_row.addWidget(self.print_summary_button)
        button_row.addStretch(1)
        button_row.addWidget(self.trip_form_button)
        button_row.addWidget(self.qq_mail_button)
        button_row.addWidget(self.mail_fetch_button)

        layout.addLayout(button_row)
        layout.addWidget(self.phase_label)
        return group

    @staticmethod
    def _available_printer_names() -> list[str]:
        return sorted(
            {
                printer.printerName()
                for printer in QPrinterInfo.availablePrinters()
                if printer.printerName()
            },
            key=str.casefold,
        )

    def _load_selected_printer_name(self) -> str:
        available_names = self._available_printer_names()
        saved_name = str(self.settings.value("printer/name", "") or "")
        if saved_name in available_names:
            return saved_name

        default_printer = QPrinterInfo.defaultPrinter()
        if not default_printer.isNull() and default_printer.printerName() in available_names:
            return default_printer.printerName()
        return available_names[0] if available_names else ""

    def _update_printer_status_label(self) -> None:
        if self.selected_printer_name:
            self.printer_status_label.setText(f"当前：{self.selected_printer_name}")
        else:
            self.printer_status_label.setText("未检测到打印机")

    def choose_printer(self) -> None:
        printer_names = self._available_printer_names()
        if not printer_names:
            QMessageBox.warning(self, "未检测到打印机", "Windows 当前没有可用打印机。")
            return

        current_index = max(printer_names.index(self.selected_printer_name), 0) if self.selected_printer_name in printer_names else 0
        selected_name, accepted = QInputDialog.getItem(
            self,
            "选择打印机",
            "打印机：",
            printer_names,
            current_index,
            False,
        )
        if not accepted or not selected_name:
            return

        self.selected_printer_name = selected_name
        self.settings.setValue("printer/name", selected_name)
        self.settings.sync()
        self._update_printer_status_label()
        self.status_bar.showMessage(f"已选择打印机：{selected_name}，下次启动将继续使用。")

    def _build_date_summary_group(self) -> QGroupBox:
        group = QGroupBox("按日期汇总")
        layout = QVBoxLayout(group)

        self.date_table = QTableWidget(0, 11)
        self.date_table.setHorizontalHeaderLabels(
            ["日期", "假别", "大众运输", "出租车费用", "过路费", "住宿不含税", "住宿税额", "住宿（普票全额）", "住宿合计", "在途", "出差补贴"]
        )
        self.date_table.horizontalHeaderItem(10).setForeground(QBrush(SUBSIDY_HEADER_COLOR))
        self.date_table.setEditTriggers(QTableWidget.DoubleClicked | QTableWidget.EditKeyPressed | QTableWidget.AnyKeyPressed)
        self.date_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.date_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.date_table.verticalHeader().setVisible(False)
        self.date_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.date_table.setMinimumHeight(120)
        self.date_table.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
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
        self.table.setWordWrap(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._detail_column_widths = [90, 78, 72, 72, 72, 150, 135, 170, 170, 62, 90, 90, 150]
        self._detail_column_min_widths = [76, 64, 62, 62, 62, 110, 100, 110, 110, 52, 72, 72, 90]
        self._detail_flexible_columns = (5, 7, 8, 12)
        self._adapt_detail_table_columns()
        layout.addWidget(self.table)
        return group

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "table"):
            self._adapt_detail_table_columns()
            self.table.resizeRowsToContents()
        if hasattr(self, "date_table"):
            self.date_table.resizeRowsToContents()

    def _adapt_detail_table_columns(self) -> None:
        """在可用宽度内分配列宽，空间不足时保留水平滚动，避免内容被截断。"""
        if not hasattr(self, "table"):
            return

        available_width = max(self.table.viewport().width(), 0)
        minimum_total = sum(self._detail_column_min_widths)
        widths = list(self._detail_column_widths)
        if available_width >= minimum_total:
            extra_width = available_width - sum(widths)
            if extra_width > 0:
                flexible_count = len(self._detail_flexible_columns)
                per_column, remainder = divmod(extra_width, flexible_count)
                for position, column_index in enumerate(self._detail_flexible_columns):
                    widths[column_index] += per_column + (1 if position < remainder else 0)
        else:
            widths = list(self._detail_column_min_widths)

        for column_index, width in enumerate(widths):
            self.table.setColumnWidth(column_index, width)

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

    def open_trip_form(self) -> None:
        if not QDesktopServices.openUrl(QUrl(TRIP_FORM_URL)):
            QMessageBox.warning(self, "无法打开出差单", f"无法打开出差单填写入口：\n{TRIP_FORM_URL}")

    def open_qq_mail(self) -> None:
        if not QDesktopServices.openUrl(QUrl("https://mail.qq.com/")):
            QMessageBox.warning(self, "无法打开 QQ 邮箱", "无法打开 QQ 邮箱网页登录页。")

    def fetch_mail_invoices(self) -> None:
        dialog = MailInvoiceFetchDialog(self.settings, self)
        if dialog.exec_() != QDialog.Accepted:
            return
        account, authorization_code, start_date, end_date = dialog.values()
        self.mail_fetch_worker = MailFetchWorker(account, authorization_code, start_date, end_date)
        self.mail_fetch_worker.completed.connect(self._on_mail_fetch_completed)
        self.mail_fetch_worker.failed.connect(self._on_mail_fetch_failed)
        self.mail_fetch_worker.finished.connect(self._on_mail_fetch_finished)
        self._set_busy(True)
        self.phase_label.setText("当前状态：正在抓取 QQ 邮箱发票，请稍候")
        self.mail_fetch_worker.start()

    def _on_mail_fetch_completed(self, output_directory: str, copied_count: int) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(output_directory))
        self.phase_label.setText(f"当前状态：已抓取 {copied_count} 个发票 PDF")
        QMessageBox.information(self, "抓取完成", f"已抓取 {copied_count} 个 PDF 发票：\n{output_directory}")

    def _on_mail_fetch_failed(self, message: str) -> None:
        self.phase_label.setText("当前状态：邮箱发票抓取失败")
        QMessageBox.critical(self, "抓取失败", message)

    def _on_mail_fetch_finished(self) -> None:
        self.mail_fetch_worker = None
        self._set_busy(False)

    def generate_archive_excel(self) -> None:
        if self.current_result is None or not self.current_result.applied:
            QMessageBox.warning(self, "缺少汇总结果", "请先执行“分析汇总”，生成整理结果后再生成归档 Excel。")
            return

        self._refresh_summary_artifacts()
        if self.current_result is None:
            return

        archive_path = get_default_archive_path(self.current_result.source_directory)
        try:
            append_print_archive(
                self.current_result,
                archive_path=archive_path,
                printed_jobs=0,
                unique_files=0,
                taxi_amount=self._get_taxi_amount(),
                subsidy_amount=self._get_subsidy_amount(),
                in_transit_amount=self._get_in_transit_amount(),
                travel_in_transit=self._get_travel_in_transit(),
            )
        except Exception as error:
            QMessageBox.critical(self, "归档生成失败", str(error))
            self.status_bar.showMessage("归档 Excel 生成失败。")
            return

        QDesktopServices.openUrl(QUrl.fromLocalFile(str(archive_path)))
        self.status_bar.showMessage(f"已生成并打开归档 Excel：{archive_path}")

    def upload_pdfs_to_public_disk(self) -> None:
        if self.current_result is None or not self.current_result.applied:
            QMessageBox.warning(self, "输出目录未生成", "请先执行“分析汇总”，生成输出文件后再上传。")
            return

        self._refresh_summary_artifacts()
        output_directory = Path(self.current_result.output_directory)
        if not output_directory.exists():
            QMessageBox.warning(self, "输出目录不存在", f"暂未找到输出目录：\n{output_directory}")
            return

        invoice_numbers = {record.number for record in self.current_result.records if record.number}
        invoice_pdf_names = [
            file_path.name
            for file_path in output_directory.iterdir()
            if (
                file_path.is_file()
                and file_path.suffix.lower() == ".pdf"
                and any(invoice_number in file_path.name for invoice_number in invoice_numbers)
            )
        ]
        dialog = PublicDiskUploadDialog(
            output_directory,
            self._load_public_disk_upload_directory(),
            invoice_pdf_names,
            self,
        )
        if dialog.exec_() != QDialog.Accepted:
            self.status_bar.showMessage("已取消上传到局域公共盘。")
            return

        pdf_files = dialog.listed_pdf_files()
        if not pdf_files:
            QMessageBox.warning(self, "没有 PDF 文件", "当前输出文件夹中没有可上传的 PDF 文件。")
            return

        try:
            target_directory = self._resolve_public_disk_upload_directory(dialog.public_disk_address())
            copied_count = 0
            for source_path in pdf_files:
                shutil.copy2(source_path, target_directory / source_path.name)
                copied_count += 1
        except Exception as error:
            QMessageBox.critical(self, "上传失败", str(error))
            self.status_bar.showMessage("上传到局域公共盘失败。")
            return

        self.settings.setValue(PUBLIC_DISK_UPLOAD_DIRECTORY_SETTING, str(target_directory))
        self.settings.sync()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target_directory)))
        self.status_bar.showMessage(f"已复制 {copied_count} 个 PDF 到局域公共盘。")
        QMessageBox.information(
            self,
            "上传完成",
            f"已复制 {copied_count} 个 PDF 到：\n{target_directory}",
        )

    def _load_public_disk_upload_directory(self) -> str:
        return str(self.settings.value(PUBLIC_DISK_UPLOAD_DIRECTORY_SETTING, DEFAULT_PUBLIC_DISK_ADDRESS) or DEFAULT_PUBLIC_DISK_ADDRESS)

    def _resolve_public_disk_upload_directory(self, public_disk_address: str) -> Path:
        cleaned_address = self._normalize_unc_address(public_disk_address)
        if not cleaned_address:
            raise RuntimeError("请选择或填写局域公共盘上传目标文件夹。")

        target_directory = Path(cleaned_address)
        if not target_directory.exists() or not target_directory.is_dir():
            raise RuntimeError(f"无法访问上传目标文件夹：\n{target_directory}")
        return target_directory

    def _normalize_unc_address(self, public_disk_address: str) -> str:
        cleaned_address = public_disk_address.strip().strip('"').strip("'").replace("/", "\\").rstrip("\\")
        if cleaned_address.startswith("\\") and not cleaned_address.startswith("\\\\"):
            cleaned_address = f"\\{cleaned_address}"
        return cleaned_address

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

        available_printer_names = self._available_printer_names()
        if not self.selected_printer_name or self.selected_printer_name not in available_printer_names:
            QMessageBox.warning(self, "未选择可用打印机", "请选择当前可用的打印机后再打印。")
            self.choose_printer()
            return

        selected_printer_name = self.selected_printer_name
        if not selected_printer_name:
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
                f"将发送打印任务到：{selected_printer_name}\n"
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
            printer_name=selected_printer_name,
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
        printer_name: str,
        task_label: str,
    ) -> None:
        if self.current_result is None:
            return

        self.current_print_task_label = task_label
        self._set_busy(True)
        self.phase_label.setText(f"当前状态：正在提交{task_label}")
        self.status_bar.showMessage(f"正在向 {printer_name} 发送{task_label}，请稍候...")

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
            printer_name=printer_name,
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
        self.status_bar.showMessage(f"已发送 {printed_jobs} 份{self.current_print_task_label}到已选打印机。")
        QMessageBox.information(
            self,
            "打印已提交",
            (
                f"已发送 {printed_jobs} 份{self.current_print_task_label}到已选打印机，纸张默认 A5。\n"
                "如需归档，请点击“生成汇总清单并打开”。"
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
        self.printer_button.setEnabled(not busy)
        self.analyze_button.setEnabled(not busy)
        self.manual_summary_button.setEnabled(not busy)
        self.print_button.setEnabled(not busy)
        self.print_summary_button.setEnabled(not busy)
        self.toggle_date_summary_button.setEnabled(not busy)
        self.confirm_subsidy_button.setEnabled(not busy)
        self.add_date_row_button.setEnabled(not busy and self.manual_summary_mode)
        self.remove_date_row_button.setEnabled(not busy and self.manual_summary_mode and self._date_data_row_count() > 0)
        self.open_output_button.setEnabled(not busy)
        self.upload_public_disk_button.setEnabled(not busy)
        self.open_archive_button.setEnabled(not busy)
        self.trip_form_button.setEnabled(not busy)
        self.qq_mail_button.setEnabled(not busy)
        self.mail_fetch_button.setEnabled(not busy)
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
        self.printer_button.setEnabled(is_idle)
        self.print_button.setEnabled(is_idle and has_applied_result)
        self.print_summary_button.setEnabled(is_idle and has_applied_result)
        self.confirm_subsidy_button.setEnabled(is_idle and has_applied_result)
        self.open_output_button.setEnabled(is_idle and has_applied_result)
        self.upload_public_disk_button.setEnabled(is_idle and has_applied_result)
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
        summary_issues, _ = collect_summary_issues(result)
        summary_column_indexes = {
            "transport_total": 2,
            "toll_total": 4,
            "lodging_amount_total": 5,
            "lodging_tax_total": 6,
            "lodging_public_total": 7,
        }
        self.updating_date_table = True
        self.date_table.setRowCount(len(rows) + 2)

        for row_index, item in enumerate(rows):
            travel_in_transit, taxi_amount, subsidy_amount = self.date_manual_values.get(item.issue_date, ("", 0.0, 0.0))
            values = [
                item.issue_date,
                self._get_day_type(item.issue_date),
                f"{item.transport_total:.2f}",
                f"{taxi_amount:.2f}" if taxi_amount else "",
                f"{item.toll_total:.2f}",
                f"{item.lodging_amount_total:.2f}",
                f"{item.lodging_tax_total:.2f}",
                f"{item.lodging_public_total:.2f}",
                f"{item.lodging_total:.2f}",
                travel_in_transit,
                f"{subsidy_amount:.2f}" if subsidy_amount else "",
            ]
            for column_index, value in enumerate(values):
                cell_item = self._build_date_table_item(value, editable=self._is_date_table_column_editable(column_index))
                column_key = next((key for key, index in summary_column_indexes.items() if index == column_index), "")
                issues = summary_issues.get((item.issue_date, column_key), []) if column_key else []
                if issues:
                    cell_item.setBackground(QBrush(QColor("#FCE4D6")))
                    cell_item.setForeground(QBrush(QColor("#C62828")))
                    cell_item.setToolTip("\n".join(issues))
                self.date_table.setItem(row_index, column_index, cell_item)

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
        current_date = datetime.now().strftime("%Y-%m-%d")
        return [current_date, self._get_day_type(current_date), "", "", "", "", "", "", "", "", ""]

    def _focus_first_manual_cell(self) -> None:
        if self._date_data_row_count() == 0:
            return

        focus_column = 0 if self.manual_summary_mode else 3
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
            return column_index in {0, 2, 3, 4, 5, 6, 7, 8, 9, 10}
        return column_index in {3, 9, 10}

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
            travel_item = self.date_table.item(row_index, 9)
            if date_item is None:
                continue
            issue_date = date_item.text().strip()
            travel_in_transit = travel_item.text().strip() if travel_item is not None else ""
            taxi_amount = self._parse_date_table_money(row_index, 3)
            subsidy_amount = self._parse_date_table_money(row_index, 10)
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
        for row_index in range(data_row_count):
            date_item = self.date_table.item(row_index, 0)
            date_value = date_item.text().strip() if date_item is not None else ""
            self.date_table.setItem(
                row_index,
                1,
                self._build_date_table_item(self._get_day_type(date_value), editable=False),
            )
        subtotal_row = data_row_count
        total_row = data_row_count + 1
        money_totals = [
            round(sum(self._parse_date_table_money(row_index, column_index) for row_index in range(data_row_count)), 2)
            for column_index in [2, 3, 4, 5, 6, 7, 8, 10]
        ]
        in_transit_total = round(
            sum(parse_money_text(self.date_table.item(row_index, 9).text()) for row_index in range(data_row_count) if self.date_table.item(row_index, 9) is not None),
            2,
        )
        transport_subtotal = round(money_totals[0] + money_totals[1], 2)
        combined_subsidy_total = round(in_transit_total + money_totals[7], 2)
        grand_total = round(transport_subtotal + money_totals[2] + money_totals[6] + combined_subsidy_total, 2)

        subtotal_values = [
            "小计",
            "",
            f"{transport_subtotal:.2f}",
            f"{money_totals[1]:.2f}",
            f"{money_totals[2]:.2f}",
            f"{money_totals[3]:.2f}",
            f"{money_totals[4]:.2f}",
            f"{money_totals[5]:.2f}",
            f"{money_totals[6]:.2f}",
            "",
            f"{combined_subsidy_total:.2f}",
        ]
        total_values = ["总计", "", f"{grand_total:.2f}", "", "", "", "", "", "", "", ""]

        for column_index, value in enumerate(subtotal_values):
            self.date_table.setItem(subtotal_row, column_index, self._build_date_table_item(value, editable=False, summary=True))
        for column_index, value in enumerate(total_values):
            self.date_table.setItem(total_row, column_index, self._build_date_table_item(value, editable=False, summary=True))
        for column_index in range(self.date_table.columnCount()):
            subtotal_item = self.date_table.item(subtotal_row, column_index)
            if subtotal_item is not None:
                subtotal_item.setBackground(QBrush(SUBTOTAL_ROW_COLOR))
        self.date_table.resizeRowsToContents()

        self.updating_date_table = False

    def _on_date_table_cell_changed(self, row_index: int, column_index: int) -> None:
        if self.updating_date_table or row_index >= self._date_data_row_count():
            return
        if not self.manual_summary_mode and column_index not in {3, 9, 10}:
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
                "；".join(
                    [
                        *record.hints,
                        *(
                            [f"行程时间：{record.ride_start_time}-{record.ride_end_time}"]
                            if record.ride_start_time and record.ride_end_time
                            else []
                        ),
                        *([f"住宿票种：{record.lodging_invoice_type}"] if record.lodging_invoice_type else []),
                        *([f"购方税号：{record.buyer_tax_id}"] if record.buyer_tax_id else []),
                        *record.warnings,
                    ]
                ),
            ]

            row_background = WARNING_ROW_COLOR if (record.review_status != "ok" or record.warnings) else NORMAL_ROW_COLOR
            row_foreground = WARNING_TEXT_COLOR if (record.review_status != "ok" or record.warnings) else None

            for column_index, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setBackground(QBrush(row_background))
                if row_foreground is not None:
                    item.setForeground(QBrush(row_foreground))
                self.table.setItem(row_index, column_index, item)
        self._adapt_detail_table_columns()
        self.table.resizeRowsToContents()
        for row_index in range(self.table.rowCount()):
            self.table.setRowHeight(row_index, max(self.table.rowHeight(row_index), 32))

    @staticmethod
    def _get_day_type(issue_date: str) -> str:
        """按周末及中国法定节假日标记明细行的假别。"""
        try:
            actual_date = datetime.strptime(issue_date, "%Y-%m-%d").date()
        except ValueError:
            return "未识别"

        if actual_date.weekday() >= 5:
            return "假日"
        if is_holiday is not None and is_holiday(actual_date):
            return "假日"
        return "平日"

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
                    "transport_total": self._parse_date_table_money(row_index, 2),
                    "taxi_amount": self._parse_date_table_money(row_index, 3),
                    "toll_total": self._parse_date_table_money(row_index, 4),
                    "lodging_amount_total": self._parse_date_table_money(row_index, 5),
                    "lodging_tax_total": self._parse_date_table_money(row_index, 6),
                    "lodging_public_total": self._parse_date_table_money(row_index, 7),
                    "lodging_total": self._parse_date_table_money(row_index, 8),
                    "travel_in_transit": text_values[9],
                    "subsidy_amount": self._parse_date_table_money(row_index, 10),
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
                    "lodging_public_total": 0.0,
                    "lodging_total": 0.0,
                },
            )
            bucket["transport_total"] += float(row["transport_total"])
            bucket["toll_total"] += float(row["toll_total"])
            bucket["lodging_amount_total"] += float(row["lodging_amount_total"])
            bucket["lodging_tax_total"] += float(row["lodging_tax_total"])
            bucket["lodging_public_total"] += float(row["lodging_public_total"])
            bucket["lodging_total"] += float(row["lodging_total"])

        daily_breakdown = [
            InvoiceDateSummary(
                issue_date=issue_date,
                transport_total=round(bucket["transport_total"], 2),
                toll_total=round(bucket["toll_total"], 2),
                lodging_amount_total=round(bucket["lodging_amount_total"], 2),
                lodging_tax_total=round(bucket["lodging_tax_total"], 2),
                lodging_public_total=round(bucket["lodging_public_total"], 2),
                lodging_total=round(bucket["lodging_total"], 2),
                ride_hailing_interval="",
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
            lodging_public_total=round(sum(bucket["lodging_public_total"] for bucket in grouped_rows.values()), 2),
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
        export_combined_print_pdf(self.current_result)

def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())