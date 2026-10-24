from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PyQt5.QtCore import QDate, QSettings, QTime, Qt
from PyQt5.QtWidgets import QApplication

from invoice_desktop.private_car import PLATE_SETTING, USER_SETTING, PrivateCarWidget, calculate_private_car_cost


class PrivateCarCalculationTests(unittest.TestCase):
    def test_example_distance_and_subsidy(self):
        self.assertEqual(calculate_private_car_cost("44118", "44165"), ("47", "70.50", ""))

    def test_decimal_rounding(self):
        self.assertEqual(calculate_private_car_cost("100", "100.01"), ("0.01", "0.02", ""))

    def test_zero_distance(self):
        self.assertEqual(calculate_private_car_cost("0", "0"), ("0", "0.00", ""))

    def test_missing_reading_stays_blank(self):
        for start, end in (("", ""), ("44118", ""), ("", "44165")):
            self.assertEqual(calculate_private_car_cost(start, end), ("", "", ""))

    def test_invalid_readings_do_not_produce_subsidy(self):
        for start, end in (("abc", "100"), ("-1", "1"), ("NaN", "2"),
                           ("1", "0"), ("1.0001", "2"), ("0", "1000000000")):
            with self.subTest(start=start, end=end):
                distance, subsidy, error = calculate_private_car_cost(start, end)
                self.assertEqual((distance, subsidy), ("", ""))
                self.assertTrue(error)


class PrivateCarWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings_path = str(Path(self.temp.name) / "settings.ini")
        self.settings = QSettings(self.settings_path, QSettings.IniFormat)
        self.widget = PrivateCarWidget(self.settings)
        self.addCleanup(self.widget.close)

    def test_one_empty_row_and_editable_inputs(self):
        table = self.widget.table
        self.assertEqual(table.rowCount(), 1)
        self.assertEqual(table.columnCount(), 11)
        for column in range(11):
            item = table.item(0, column)
            self.assertEqual(item.text(), "")
            self.assertEqual(bool(item.flags() & Qt.ItemIsEditable), column not in (7, 8))

    def test_add_row_preserves_data_and_calculates_independently(self):
        table = self.widget.table
        table.item(0, 0).setText("2026-07-22")
        table.item(0, 1).setText("李伟")
        table.item(0, 2).setText("苏州欧朗普瑞、博智慧达")
        table.item(0, 3).setText("09:30")
        table.item(0, 4).setText("17:40")
        table.item(0, 5).setText("44118")
        table.item(0, 6).setText("44165")
        table.item(0, 9).setText("88")
        table.item(0, 10).setText("10")
        self.assertEqual([table.item(0, c).text() for c in (7, 8)], ["47", "70.50"])
        self.widget.add_row_button.click()
        self.assertEqual(table.rowCount(), 2)
        self.assertTrue(all(table.item(1, c).text() == "" for c in range(11)))
        table.item(1, 5).setText("50")
        table.item(1, 6).setText("60")
        self.assertEqual(table.item(1, 8).text(), "15.00")
        self.assertEqual(table.item(0, 8).text(), "70.50")
        self.assertEqual(table.item(0, 9).text(), "88")

    def test_edit_clear_error_and_recover(self):
        table = self.widget.table
        table.item(0, 5).setText("44118")
        table.item(0, 6).setText("44165")
        table.item(0, 6).setText("44166")
        self.assertEqual(table.item(0, 8).text(), "72.00")
        table.item(0, 6).setText("")
        self.assertEqual(table.item(0, 8).text(), "")
        table.item(0, 6).setText("1")
        self.assertEqual(table.item(0, 8).text(), "")
        self.assertIn("不能小于", table.item(0, 6).toolTip())
        table.item(0, 6).setText("44165")
        self.assertEqual(table.item(0, 8).text(), "70.50")
        self.assertNotIn("不能小于", table.item(0, 6).toolTip())

    def test_license_plate_is_remembered_by_new_settings_instance(self):
        self.widget.plate_edit.setText("苏U930FQ")
        another_settings = QSettings(self.settings_path, QSettings.IniFormat)
        self.assertEqual(another_settings.value(PLATE_SETTING), "苏U930FQ")
        another = PrivateCarWidget(another_settings)
        self.addCleanup(another.close)
        self.assertEqual(another.plate_edit.text(), "苏U930FQ")
        self.assertEqual(another.table.rowCount(), 1)

    def test_user_is_remembered_and_populates_rows_without_overwriting_manual_name(self):
        self.widget.user_edit.setText("李伟")
        table = self.widget.table
        self.assertEqual(table.item(0, 1).text(), "李伟")
        table.item(0, 1).setText("王明")
        self.widget.add_row()
        self.assertEqual(table.item(1, 1).text(), "李伟")
        self.widget.user_edit.setText("张三")
        self.assertEqual(table.item(0, 1).text(), "王明")
        self.assertEqual(table.item(1, 1).text(), "张三")
        another_settings = QSettings(self.settings_path, QSettings.IniFormat)
        self.assertEqual(another_settings.value(USER_SETTING), "张三")
        another = PrivateCarWidget(another_settings)
        self.addCleanup(another.close)
        self.assertEqual(another.user_edit.text(), "张三")
        self.assertEqual(another.table.item(0, 1).text(), "张三")

    def test_date_and_24_hour_time_editors(self):
        table = self.widget.table
        for column, value, expected in (
            (0, QDate(2026, 10, 23), "2026-10-23"),
            (3, QTime(9, 0), "9:00"),
            (4, QTime(23, 59), "23:59"),
        ):
            delegate = table.itemDelegateForColumn(column)
            index = table.model().index(0, column)
            from PyQt5.QtWidgets import QStyleOptionViewItem
            editor = delegate.createEditor(table, QStyleOptionViewItem(), index)
            delegate.setEditorData(editor, index)
            if column == 0:
                self.assertTrue(editor.calendarPopup())
                editor.setDate(value)
            else:
                self.assertEqual(editor.displayFormat(), "H:mm")
                editor.setTime(value)
            delegate.setModelData(editor, table.model(), index)
            self.assertEqual(table.item(0, column).text(), expected)
            editor.deleteLater()

    def test_headers_fit_and_all_three_rows_remain_visible(self):
        self.widget.resize(1500, 600)
        self.widget.show()
        self.app.processEvents()
        table = self.widget.table
        table.item(0, 2).setText("原有目的地")
        original_height = table.height()
        self.widget.add_row_button.click()
        self.widget.add_row_button.click()
        self.app.processEvents()
        self.assertEqual(table.rowCount(), 3)
        self.assertEqual(table.item(0, 2).text(), "原有目的地")
        self.assertGreaterEqual(table.height() - original_height, 84)
        self.assertGreaterEqual(table.viewport().height(), sum(table.rowHeight(row) for row in range(3)))
        header = table.horizontalHeader()
        for column in range(table.columnCount()):
            self.assertGreaterEqual(header.sectionSize(column), header.sectionSizeHint(column))
        self.assertGreaterEqual(header.height(), header.sizeHint().height())
        metrics = header.fontMetrics()
        for col in range(table.columnCount()):
            lines = table.horizontalHeaderItem(col).text().split("\n")
            self.assertGreaterEqual(header.sectionSize(col), max(metrics.horizontalAdvance(line) for line in lines) + 8)
            self.assertGreaterEqual(header.height(), metrics.lineSpacing() * len(lines) + 8)

    def test_private_table_and_editors_match_date_summary_font_size(self):
        from invoice_desktop.main import MainWindow
        from PyQt5.QtWidgets import QStyleOptionViewItem

        with patch("invoice_desktop.main.QSettings", return_value=self.settings):
            window = MainWindow()
        self.addCleanup(window.close)
        window.show()
        window.date_summary_group.show()
        window.private_car_checkbox.setChecked(True)
        self.app.processEvents()
        summary = window.date_table
        private = window.private_car_widget.table

        def font_size(widget):
            widget.ensurePolished()
            return widget.font().pixelSize(), widget.font().pointSizeF()

        self.assertEqual(font_size(private), font_size(summary))
        self.assertEqual(font_size(private.horizontalHeader()), font_size(summary.horizontalHeader()))
        # 日期、时间、里程和费用在编辑状态下也不应切回另一套字号。
        for column in (0, 1, 2, 3, 4, 5, 6, 9, 10):
            with self.subTest(column=column):
                index = private.model().index(0, column)
                editor = private.itemDelegate(index).createEditor(private.viewport(), QStyleOptionViewItem(), index)
                self.assertEqual(font_size(editor), font_size(summary))
                editor.deleteLater()
        header = private.horizontalHeader()
        metrics = header.fontMetrics()
        for column in range(private.columnCount()):
            lines = private.horizontalHeaderItem(column).text().split("\n")
            self.assertGreaterEqual(header.sectionSize(column), max(metrics.horizontalAdvance(line) for line in lines) + 8)
            self.assertGreaterEqual(header.height(), metrics.lineSpacing() * len(lines) + 8)

    def test_checkbox_visibility_and_busy_states_in_main_window(self):
        from invoice_desktop.main import MainWindow

        with patch("invoice_desktop.main.QSettings", return_value=self.settings):
            window = MainWindow()
        self.addCleanup(window.close)
        window.show()
        self.app.processEvents()
        window.toggle_date_summary_button.click()
        self.app.processEvents()
        self.assertTrue(window.private_car_checkbox.isVisible())
        self.assertFalse(window.private_car_checkbox.isChecked())
        self.assertFalse(window.private_car_widget.isVisible())
        window.private_car_checkbox.click()
        self.app.processEvents()
        self.assertTrue(window.private_car_widget.isVisible())
        window.private_car_widget.table.item(0, 1).setText("李伟")
        window._set_busy(True)
        self.assertFalse(window.private_car_checkbox.isEnabled())
        self.assertFalse(window.private_car_widget.isEnabled())
        window._set_busy(False)
        self.assertTrue(window.private_car_widget.isEnabled())
        window.private_car_checkbox.click()
        self.assertFalse(window.private_car_widget.isVisible())
        window.private_car_checkbox.click()
        self.assertEqual(window.private_car_widget.table.item(0, 1).text(), "")


if __name__ == "__main__":
    unittest.main()