from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import fitz
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Table

from python_recognizer.extractors import extract_text
from python_recognizer.trip_summary import build_trip_daily_breakdown, extract_ride_trip_amounts
from python_recognizer.types import InvoiceRecognitionResult, RideHailingPairResult
from python_recognizer.workflow import export_summary_sheet, organize_invoice_directory, summarize_records_by_date


ITINERARY_TEXT = """滴滴出行 行程报销单
申请日期：2026-09-05
行程起止日期：2026-08-31 至 2026-09-04
共2笔行程，合计22.90元
序号 车型 上车时间 城市 起点 终点 里程(公里) 金额(元) 备注
1 滴滴轻享 08-31 15:00 周一 苏州市 科技园西门 苏州园区站进站口 4.1 12.60
2 快车 09-04 18:07 周五 苏州市 地铁站2口 园区万科南门 1.5 10.30
"""


def recognition(category, issue_date, total_amount):
    return InvoiceRecognitionResult(
        source_file="", text_source="pdf_text", ocr_used=False,
        number="12345678901234567890", vendor="滴滴", amount=total_amount,
        tax_amount=0.0, total_amount=total_amount, issue_date=issue_date,
        category=category, buyer_tax_id="91320594688334374M",
        lodging_invoice_type="", ride_start_time="", ride_end_time="",
        text_length=100, notes="", matched_rules={},
    )


class TripSummaryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.base = Path(self.directory.name)

    def make_result(self, text=ITINERARY_TEXT, *, total=22.9, paired=True, train_date="2026-09-01"):
        paths = [self.base / name for name in ("invoice.pdf", "itinerary.pdf", "train1.pdf", "train2.pdf")]
        values = {
            "invoice.pdf": recognition("网约车", "2026-09-05", total),
            "itinerary.pdf": recognition("网约车行程单", "2026-08-31", total),
            "train1.pdf": recognition("火车票", train_date, 67.0),
            "train2.pdf": recognition("火车票", "2026-09-16", 22.3),
        }
        pairs = [RideHailingPairResult(
            match_key="ride-1", confidence="high", amount=total,
            invoice_file="invoice.pdf", itinerary_file="itinerary.pdf",
            invoice_vendor="滴滴", itinerary_vendor="滴滴", issue_date="2026-09-05", notes="",
        )] if paired else []
        with patch("python_recognizer.workflow.pair_ride_hailing_documents", return_value=pairs), \
             patch("python_recognizer.workflow.iter_source_pdf_files", return_value=paths), \
             patch("python_recognizer.workflow.extract_text", side_effect=lambda path, **_: (text if path.name == "itinerary.pdf" else path.name, "pdf_text", False)), \
             patch("python_recognizer.workflow.recognize_invoice_text", side_effect=lambda _, path: deepcopy(values[Path(path).name])):
            return organize_invoice_directory(self.base)

    def export_rows(self, result, **kwargs):
        with patch("python_recognizer.workflow.Table", wraps=Table) as tables:
            export_summary_sheet(result, **kwargs)
        rows = []
        for call in tables.call_args_list:
            data = call.args[0]
            if data and len(data[0]) == 9:
                rows.extend([[cell.getPlainText() for cell in row] for row in data[1:]])
        return {row[0]: row for row in rows}

    def test_split_across_dates_only_changes_generated_trip_table(self):
        result = self.make_result()
        original = deepcopy(result.to_dict())
        rows = self.export_rows(result)
        self.assertEqual(rows["2026-08-31"][1], "12.60")
        self.assertEqual(rows["2026-09-04"][1], "10.30")
        self.assertEqual(rows["2026-09-01"][1], "67.00")
        self.assertEqual(rows["2026-09-16"][1], "22.30")
        self.assertEqual(rows["小计"][1], "112.20")
        self.assertEqual(rows["总计"][1], "112.20")
        original["summary_sheet_pdf"] = result.summary_sheet_pdf
        self.assertEqual(result.to_dict(), original)

    def test_multiple_rides_on_same_day_are_added(self):
        result = self.make_result(ITINERARY_TEXT.replace("09-04 18:07", "08-31 18:07"))
        rows = self.export_rows(result)
        self.assertEqual(rows["2026-08-31"][1], "22.90")
        self.assertNotIn("2026-09-04", rows)

    def test_multiple_rides_and_train_on_same_day_are_added(self):
        text = ITINERARY_TEXT.replace("共2笔", "共3笔").replace("合计22.90", "合计32.90")
        text += "3 快车 09-04 20:07 周五 苏州市 苏州站 园区万科南门 2.5 10.00\n"
        result = self.make_result(text, total=32.9, train_date="2026-09-04")
        rows = self.export_rows(result)
        self.assertEqual(rows["2026-08-31"][1], "12.60")
        self.assertEqual(rows["2026-09-04"][1], "87.30")
        self.assertEqual(rows["总计"][1], "122.20")

    def test_incomplete_or_inconsistent_itinerary_keeps_original_amount(self):
        for text in (
            ITINERARY_TEXT.replace("10.30", ""),
            ITINERARY_TEXT.replace("10.30", "10.31"),
            ITINERARY_TEXT.replace("共2笔", "共3笔"),
            ITINERARY_TEXT.replace("09-04 18:07", "02-30 18:07"),
            "无法识别行程明细",
        ):
            with self.subTest(text=text):
                rows = self.export_rows(self.make_result(text))
                self.assertEqual(rows["2026-08-31"][1], "22.90")
                self.assertNotIn("2026-09-04", rows)
                self.assertEqual(rows["总计"][1], "112.20")

    def test_unpaired_itinerary_does_not_add_another_charge(self):
        rows = self.export_rows(self.make_result(paired=False))
        self.assertEqual(rows["2026-09-05"][1], "22.90")
        self.assertNotIn("2026-09-04", rows)
        self.assertEqual(rows["总计"][1], "112.20")

    def test_non_transport_fees_and_original_records_are_unchanged(self):
        result = self.make_result()
        template = result.records[0]
        extra = [
            replace(template, source_file="toll.pdf", category="高速通行票", total_amount=15.5),
            replace(template, source_file="hotel.pdf", category="住宿票", amount=100.0, tax_amount=6.0, total_amount=106.0),
            replace(template, source_file="hotel-public.pdf", category="住宿票", lodging_invoice_type="普票", amount=80.0, tax_amount=0.0, total_amount=80.0),
        ]
        records = result.records + extra
        original = deepcopy(records)
        daily = summarize_records_by_date(records)
        trip_daily = build_trip_daily_breakdown(daily, records, result.ride_hailing_pairs, {"itinerary.pdf": ITINERARY_TEXT})
        before = {item.issue_date: item for item in daily}
        after = {item.issue_date: item for item in trip_daily}
        for day, item in before.items():
            for name in ("toll_total", "lodging_amount_total", "lodging_tax_total", "lodging_public_total", "lodging_total", "ride_hailing_interval"):
                self.assertEqual(getattr(after[day], name), getattr(item, name))
        self.assertEqual(round(sum(item.total for item in trip_daily), 2), round(sum(item.total for item in daily), 2))
        self.assertEqual(records, original)

    def test_two_pairs_accumulate_without_duplicate_pair_charge(self):
        result = self.make_result()
        records = result.records + [
            replace(item, source_file="second-" + item.source_file)
            for item in result.records if item.category in {"网约车", "网约车行程单"}
        ]
        pair = result.ride_hailing_pairs[0]
        pairs = [pair, pair, replace(pair, invoice_file="second-invoice.pdf", itinerary_file="second-itinerary.pdf")]
        daily = build_trip_daily_breakdown(
            summarize_records_by_date(records), records, pairs,
            {"itinerary.pdf": ITINERARY_TEXT, "second-itinerary.pdf": ITINERARY_TEXT},
        )
        amounts = {item.issue_date: item.transport_total for item in daily}
        self.assertEqual(amounts["2026-08-31"], 25.2)
        self.assertEqual(amounts["2026-09-04"], 20.6)
        self.assertEqual(round(sum(amounts.values()), 2), 135.1)

    def test_repeated_export_uses_cached_split_and_keeps_manual_values(self):
        result = self.make_result()
        daily = deepcopy(result.trip_daily_breakdown)
        with patch("python_recognizer.workflow.extract_text", side_effect=AssertionError("不得重复 OCR")):
            first = self.export_rows(result, subsidy_amount=10.0, daily_manual_values={"2026-09-04": ("2", 3.0, 10.0)})
            second = self.export_rows(result, subsidy_amount=10.0, daily_manual_values={"2026-09-04": ("2", 3.0, 10.0)})
        self.assertEqual(first, second)
        self.assertEqual(first["2026-09-04"][1:3], ["10.30", "3.00"])
        self.assertEqual(first["总计"][1], "127.20")
        self.assertEqual(result.trip_daily_breakdown, daily)

    def test_manual_or_legacy_result_without_split_uses_existing_rows(self):
        result = self.make_result()
        result.trip_daily_breakdown = None
        rows = self.export_rows(result)
        self.assertEqual(rows["2026-08-31"][1], "22.90")
        self.assertNotIn("2026-09-04", rows)

    def test_real_pdf_extraction_recognition_pairing_and_export(self):
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        itinerary_path = self.base / "12345678901234567890-22.90行程单.pdf"
        invoice_path = self.base / "12345678901234567890-22.90.pdf"
        texts = {
            itinerary_path: ITINERARY_TEXT,
            invoice_path: "电子发票（普通发票）\n发票号码：12345678901234567890\n开票日期：2026-09-05\n购买方 纳税人识别号：91320594688334374M\n销售方 滴滴出行\n*运输服务*客运服务\n金额 22.23 税额 0.67\n价税合计（小写）￥22.90",
        }
        for path, text in texts.items():
            document = canvas.Canvas(str(path), pagesize=(1000, 600))
            document.setFont("STSong-Light", 10)
            for index, line in enumerate(text.splitlines()):
                document.drawString(30, 570 - index * 24, line)
            document.save()

        extracted, _, _ = extract_text(itinerary_path, enable_ocr=False)
        self.assertEqual(extract_ride_trip_amounts(extracted, "2026-08-31"), [("2026-08-31", 12.6), ("2026-09-04", 10.3)])
        result = organize_invoice_directory(self.base, enable_ocr=False)
        self.assertEqual(len(result.ride_hailing_pairs), 1)
        rows = self.export_rows(result)
        self.assertEqual(rows["2026-08-31"][1], "12.60")
        self.assertEqual(rows["2026-09-04"][1], "10.30")
        with fitz.open(result.summary_sheet_pdf) as document:
            pdf_text = "".join(page.get_text() for page in document)
        self.assertIn("2026-09-04", pdf_text)
        self.assertIn("10.30", pdf_text)

    def test_pdf_with_date_time_weekday_on_separate_lines(self):
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        path = self.base / "multiline.pdf"
        document = canvas.Canvas(str(path), pagesize=(850, 600))
        document.setFont("STSong-Light", 10)
        for index, line in enumerate(ITINERARY_TEXT.splitlines()[:5]):
            document.drawString(20, 570 - index * 18, line)
        rows = [
            ["1", "滴滴轻享", ("08-31", "15:00", "周一"), "苏州市", "科技园西门", "苏州园区站进站口", "4.1", "12.60"],
            ["2", "快车", ("09-04", "18:07", "周五"), "苏州市", "地铁站2口", "园区万科南门", "1.5", "10.30"],
        ]
        for y, row in zip((432.595, 357.595), rows):
            for x, value in zip((30, 75, 155, 245, 320, 455, 620, 710), row):
                if isinstance(value, tuple):
                    for offset, text in zip((14, 0, -14), value):
                        document.drawString(x, y + offset, text)
                else:
                    document.drawString(x, y, value)
        document.save()
        text, _, _ = extract_text(path, enable_ocr=False)
        self.assertIn("08-31 1 滴滴轻享 15:00", text)
        rows = self.export_rows(self.make_result(text))
        self.assertEqual(rows["2026-08-31"][1], "12.60")
        self.assertEqual(rows["2026-09-04"][1], "10.30")


class RideTripParserTests(unittest.TestCase):
    def test_month_day_rows_with_addresses_containing_numbers(self):
        self.assertEqual(extract_ride_trip_amounts(ITINERARY_TEXT, "2026-08-31"), [("2026-08-31", 12.6), ("2026-09-04", 10.3)])

    def test_full_dates_with_seconds_do_not_need_reference_year(self):
        text = "上车时间 城市 起点 终点 里程 金额 2026-08-31 15:00:00 苏州 A B 4.1 12.60 2026-09-04 18:07:30 苏州 C D 1.5 10.30"
        self.assertEqual(extract_ride_trip_amounts(text, ""), [("2026-08-31", 12.6), ("2026-09-04", 10.3)])

    def test_cross_year_month_day_rows(self):
        text = ITINERARY_TEXT.replace("2026-08-31", "2026-12-31").replace("2026-09-04", "2027-01-04").replace("08-31 15:00", "12-31 15:00").replace("09-04 18:07", "01-04 18:07")
        self.assertEqual(extract_ride_trip_amounts(text, "2026-12-31"), [("2026-12-31", 12.6), ("2027-01-04", 10.3)])

    def test_cross_year_range_with_time_includes_correct_year(self):
        text = ITINERARY_TEXT.replace("2026-08-31", "2026-12-31 00:00:00").replace("2026-09-04", "2027-01-04 23:59:59").replace("08-31 15:00", "12-31 15:00").replace("09-04 18:07", "01-04 18:07")
        self.assertEqual(extract_ride_trip_amounts(text, "2026-12-31"), [("2026-12-31", 12.6), ("2027-01-04", 10.3)])

    def test_integer_fares_and_decimal_ocr_whitespace(self):
        text = ITINERARY_TEXT.replace("12.60", "12").replace("10.30", "10 . 30")
        self.assertEqual(extract_ride_trip_amounts(text, "2026-08-31"), [("2026-08-31", 12.0), ("2026-09-04", 10.3)])

    def test_repeated_page_header_and_footer_total(self):
        text = ITINERARY_TEXT.replace("2 快车", "\n序号 车型 上车时间 城市 起点 终点 里程 金额\n2 快车")
        text += "\n合计 22.90 元 温馨提示：本行程单仅供报销参考"
        self.assertEqual(extract_ride_trip_amounts(text, "2026-08-31"), [("2026-08-31", 12.6), ("2026-09-04", 10.3)])

    def test_invalid_date_time_or_missing_year_is_not_guessed(self):
        for text, reference in (
            ("上车时间 08-31 15:00 A B 4.1 12.60", ""),
            ("上车时间 2026-02-30 15:00 A B 4.1 12.60", ""),
            ("上车时间 2026-08-31 25:00 A B 4.1 12.60", ""),
            ("上车时间 2026-08-31 15:70 A B 4.1 12.60", ""),
        ):
            with self.subTest(text=text):
                self.assertEqual(extract_ride_trip_amounts(text, reference), [])


if __name__ == "__main__":
    unittest.main()