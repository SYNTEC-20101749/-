"""私车公用明细填写、校验及按日费用汇总。"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re

from PyQt5.QtCore import QDate, QSettings, QSize, QTime, Qt, pyqtSignal
from PyQt5.QtGui import QBrush, QColor
from PyQt5.QtWidgets import (
    QAbstractItemView, QGroupBox, QHBoxLayout, QHeaderView, QLabel,
    QDateEdit, QLineEdit, QPushButton, QStyledItemDelegate, QTableWidget,
    QTableWidgetItem, QTimeEdit, QVBoxLayout,
)


PLATE_SETTING = "privateCar/licensePlate"
USER_SETTING = "privateCar/userName"
SUBSIDY_PER_KM = Decimal("1.5")


class TripDateTimeDelegate(QStyledItemDelegate):
    """空白记录保持空白；编辑时用日历或24小时数字时间控件。"""

    def createEditor(self, parent, option, index):
        if index.column() == 0:
            editor = QDateEdit(parent)
            editor.setCalendarPopup(True)
            editor.setDisplayFormat("yyyy-MM-dd")
        else:
            editor = QTimeEdit(parent)
            editor.setDisplayFormat("H:mm")
        editor.setStyleSheet("padding: 0px;")
        return editor

    def setEditorData(self, editor, index):
        text = str(index.data(Qt.EditRole) or "")
        if isinstance(editor, QDateEdit):
            value = QDate.fromString(text, "yyyy-MM-dd")
            editor.setDate(value if value.isValid() else QDate.currentDate())
        else:
            value = QTime.fromString(text, "H:mm")
            editor.setTime(value if value.isValid() else QTime(9, 0))

    def setModelData(self, editor, model, index):
        if isinstance(editor, QDateEdit):
            value = editor.date().toString("yyyy-MM-dd")
        else:
            value = editor.time().toString("H:mm")
        model.setData(index, value, Qt.EditRole)


class LiveExpenseDelegate(QStyledItemDelegate):
    """编辑金额/里程时即提交当前文字，不必离开单元格才更新汇总。"""

    def createEditor(self, parent, option, index):
        editor = super().createEditor(parent, option, index)
        if isinstance(editor, QLineEdit):
            editor.textEdited.connect(lambda text: self.commitData.emit(editor))
        return editor


def calculate_private_car_cost(start: str, end: str) -> tuple[str, str, str]:
    """返回里程、补贴及错误；空值不计算，金额按分四舍五入。"""
    values = []
    for label, raw in (("出发里程数", start), ("结束里程数", end)):
        text = raw.strip()
        if not text:
            values.append(None)
            continue
        if not re.fullmatch(r"\d+(?:\.\d{1,3})?", text):
            return "", "", f"{label}请输入非负数字（最多三位小数）"
        try:
            value = Decimal(text)
        except InvalidOperation:
            return "", "", f"{label}格式不正确"
        values.append(value)
    start_value, end_value = values
    if start_value is None or end_value is None:
        return "", "", ""
    if end_value < start_value:
        return "", "", "结束里程数不能小于出发里程数"
    # 限制明显无效的输入，避免 Decimal 上下文溢出或误填里程计。
    if start_value > Decimal("999999999") or end_value > Decimal("999999999"):
        return "", "", "里程数不能超过 999999999"
    distance = end_value - start_value
    subsidy = (distance * SUBSIDY_PER_KM).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    distance_text = format(distance, "f")
    if "." in distance_text:
        distance_text = distance_text.rstrip("0").rstrip(".")
    return distance_text, format(subsidy, ".2f"), ""


class PrivateCarWidget(QGroupBox):
    """一行起始明细、车牌记忆及实时费用计算。"""

    expenses_changed = pyqtSignal()

    START_COLUMN = 5
    END_COLUMN = 6
    DISTANCE_COLUMN = 7
    SUBSIDY_COLUMN = 8

    def __init__(self, settings: QSettings, parent=None) -> None:
        super().__init__("新代科技私车公用费用统计表", parent)
        self.settings = settings
        layout = QVBoxLayout(self)
        heading = QHBoxLayout()
        heading.addWidget(QLabel("SYNTEC"))
        heading.addStretch(1)
        heading.addWidget(QLabel("车牌："))
        self.plate_edit = QLineEdit()
        self.plate_edit.setPlaceholderText("请输入车牌（自动记忆）")
        self.plate_edit.setMaxLength(20)
        self.plate_edit.setMaximumWidth(260)
        self.plate_edit.setText(str(settings.value(PLATE_SETTING, "") or ""))
        self.plate_edit.textChanged.connect(self._save_plate)
        heading.addWidget(self.plate_edit)
        heading.addWidget(QLabel("使用者："))
        self.user_edit = QLineEdit()
        self.user_edit.setPlaceholderText("请输入使用者（自动记忆）")
        self.user_edit.setMaxLength(40)
        self.user_edit.setMaximumWidth(220)
        self.user_edit.setText(str(settings.value(USER_SETTING, "") or ""))
        self.user_edit.textChanged.connect(self._save_user)
        heading.addWidget(self.user_edit)
        self.add_row_button = QPushButton("新增行")
        self.add_row_button.setProperty("role", "accent")
        self.add_row_button.clicked.connect(self.add_row)
        heading.addWidget(self.add_row_button)
        layout.addLayout(heading)

        self.table = QTableWidget(0, 11)
        self.table.setHorizontalHeaderLabels([
            "日期", "使用人", "出差目的地", "开始时间", "结束时间",
            "出发里程数\n(A)", "结束里程数\n(B)", "行驶里程数\n(B－A)",
            "补贴金额\n(元)", "过路（桥）费\n(元)", "停车费\n(元)",
        ])
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed | QAbstractItemView.AnyKeyPressed)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.table.setWordWrap(True)
        # 与上方日期汇总表共享主窗口样式，避免pt/px混用在高DPI下字号不一致。
        for column in (0, 3, 4):
            self.table.setItemDelegateForColumn(column, TripDateTimeDelegate(self.table))
        for column in (5, 6, 9, 10):
            self.table.setItemDelegateForColumn(column, LiveExpenseDelegate(self.table))
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setMinimumSectionSize(75)
        header.setStretchLastSection(True)
        for column, width in enumerate((155, 95, 180, 125, 125, 130, 130, 130, 115, 145, 105)):
            self.table.horizontalHeaderItem(column).setSizeHint(QSize(width, 64))
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        header.sectionResized.connect(self._fit_table_height)
        self.table.cellChanged.connect(self._on_cell_changed)
        layout.addWidget(self.table)
        self.note_label = QLabel("补贴＝行驶里程×1.5元/公里，仅同步至上方相同日期，不自动新增日期行。对应日期的过路费以本表为准，不重复叠加发票；停车费仅导出到私车Excel。")
        self.note_label.setWordWrap(True)
        layout.addWidget(self.note_label)
        self.add_row()

    def _save_plate(self, text: str) -> None:
        self.settings.setValue(PLATE_SETTING, text.strip())
        self.settings.sync()
        self.expenses_changed.emit()

    def _save_user(self, text: str) -> None:
        self.settings.setValue(USER_SETTING, text.strip())
        self.settings.sync()
        # 更换默认使用者只更新空白或原默认姓名，保留每行手动指定的姓名。
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 1)
            if not item.text().strip() or item.data(Qt.UserRole) == item.text():
                item.setText(text.strip())
                item.setData(Qt.UserRole, text.strip())

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._fit_header_text()

    def _fit_header_text(self) -> None:
        header = self.table.horizontalHeader()
        header.ensurePolished()
        metrics = header.fontMetrics()
        height = 0
        for col in range(self.table.columnCount()):
            item = self.table.horizontalHeaderItem(col)
            lines = item.text().split("\n")
            width = max(metrics.horizontalAdvance(line) for line in lines) + 16
            height = max(height, metrics.lineSpacing() * len(lines) + 16)
            item.setSizeHint(QSize(max(item.sizeHint().width(), width), height))
        # 按当前DPI下实际字体测量，不再把两行表头锁死为64像素。
        header.setFixedHeight(max(height, header.sizeHint().height()))
        self.table.resizeColumnsToContents()
        self._fit_table_height()

    def _fit_table_height(self, *args) -> None:
        # 为所有记录分配高度，新增行不会将之前记录藏入表内滚动条。
        scrollbar_height = self.table.horizontalScrollBar().sizeHint().height()
        self.table.setFixedHeight(
            self.table.horizontalHeader().height()
            + sum(self.table.rowHeight(row) for row in range(self.table.rowCount()))
            + self.table.frameWidth() * 2 + scrollbar_height + 2
        )

    def add_row(self) -> None:
        row = self.table.rowCount()
        was_blocked = self.table.blockSignals(True)
        try:
            self.table.insertRow(row)
            tips = {0: "日期，例如 2026-07-22", 1: "使用人姓名", 2: "出差目的地",
                    3: "开始时间，例如 09:30", 4: "结束时间，例如 17:40",
                    5: "出发里程表读数，例如 44118", 6: "结束里程表读数，例如 44165",
                    7: "自动计算：结束里程－出发里程（公里）", 8: "自动计算：行驶里程×1.5元",
                    9: "手动填写过路（桥）费", 10: "手动填写停车费"}
            for column in range(self.table.columnCount()):
                value = self.user_edit.text().strip() if column == 1 else ""
                item = QTableWidgetItem(value)
                if column == 1:
                    item.setData(Qt.UserRole, value)
                item.setToolTip(tips[column])
                if column in (self.DISTANCE_COLUMN, self.SUBSIDY_COLUMN):
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                    item.setBackground(QBrush(QColor("#E8F5E9")))
                self.table.setItem(row, column, item)
            self.table.setRowHeight(row, 42)
        finally:
            self.table.blockSignals(was_blocked)
        self.table.setCurrentCell(row, 0)
        self._fit_table_height()

    def clear_rows(self) -> None:
        """取消使用时丢弃全部行程，保留已记忆的车牌/默认使用者及一条空行。"""
        was_blocked = self.table.blockSignals(True)
        try:
            self.table.setRowCount(0)
            self.add_row()
        finally:
            self.table.blockSignals(was_blocked)
        self.expenses_changed.emit()

    def _on_cell_changed(self, row: int, column: int) -> None:
        if column not in (self.START_COLUMN, self.END_COLUMN):
            self.expenses_changed.emit()
            return
        start = self.table.item(row, self.START_COLUMN)
        end = self.table.item(row, self.END_COLUMN)
        if start is None or end is None:
            return
        distance, subsidy, error = calculate_private_car_cost(start.text(), end.text())
        was_blocked = self.table.blockSignals(True)
        try:
            for item in (start, end):
                item.setBackground(QBrush(QColor("#FCE4D6" if error else "#FFFFFF")))
                item.setToolTip(error or "里程表读数，非负数字，最多三位小数")
            self.table.item(row, self.DISTANCE_COLUMN).setText(distance)
            self.table.item(row, self.SUBSIDY_COLUMN).setText(subsidy)
        finally:
            self.table.blockSignals(was_blocked)
        self.expenses_changed.emit()

    def collect_rows(self, *, strict: bool = False) -> list[list[str]]:
        """忽略仅含默认姓名的空行；确认时拒绝无日期、无效金额及不完整里程。"""
        rows = []
        for row in range(self.table.rowCount()):
            values = [self.table.item(row, col).text().strip() for col in range(11)]
            if not any(value for col, value in enumerate(values) if col != 1):
                continue
            try:
                date = QDate.fromString(values[0], "yyyy-MM-dd")
                if not date.isValid() or date.toString("yyyy-MM-dd") != values[0]:
                    raise ValueError("请设置有效日期，格式为2026-10-23")
                distance, subsidy, error = calculate_private_car_cost(values[5], values[6])
                if error or not subsidy:
                    raise ValueError(error or "请填写完整的出发和结束里程数")
                for col, label in ((3, "开始时间"), (4, "结束时间")):
                    if values[col] and not QTime.fromString(values[col], "H:mm").isValid():
                        raise ValueError(f"{label}请使用24小时制，例如9:00")
                for col, label in ((9, "过路费"), (10, "停车费")):
                    if values[col] and not re.fullmatch(r"\d{1,9}(?:\.\d{1,2})?", values[col]):
                        raise ValueError(f"{label}请输入非负金额，最多两位小数")
                values[7], values[8] = distance, subsidy
            except ValueError as exc:
                if strict:
                    raise ValueError(f"私车公用表第{row + 1}行：{exc}") from exc
                continue
            rows.append(values)
        return rows

    def collect_daily_totals(self, *, strict: bool = False) -> dict[str, tuple[float, float]]:
        totals = {}
        if strict:
            rows = self.collect_rows(strict=True)
        else:
            # 实时同步只要求有效日期及对应金额，不让停车费、时间或另一金额的
            # 无效/未完成输入抹掉已经算出的补贴。完整校验仍在确认导出时进行。
            rows = []
            for row in range(self.table.rowCount()):
                values = [self.table.item(row, col).text().strip() for col in range(11)]
                date = QDate.fromString(values[0], "yyyy-MM-dd")
                if not date.isValid() or date.toString("yyyy-MM-dd") != values[0]:
                    continue
                valid_amount = False
                for col, digits in ((8, 10), (9, 9)):
                    if re.fullmatch(r"\d{1," + str(digits) + r"}(?:\.\d{1,2})?", values[col]):
                        valid_amount = True
                    else:
                        values[col] = ""
                if valid_amount:
                    rows.append(values)
        for values in rows:
            subsidy, toll = totals.get(values[0], (Decimal("0"), Decimal("0")))
            totals[values[0]] = (subsidy + Decimal(values[8] or "0"), toll + Decimal(values[9] or "0"))
        return {date: (float(subsidy), float(toll)) for date, (subsidy, toll) in totals.items()}