from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
import shutil

from reportlab.lib.pagesizes import A5
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.lib.styles import ParagraphStyle

from .extractors import extract_text
from .heuristics import recognize_invoice_text
from .pairing import extract_filename_pair_info, pair_ride_hailing_documents
from .types import InvoiceDateSummary, InvoiceOrganizeRecord, InvoiceOrganizeResult, InvoiceOrganizeSummary


SPECIAL_RENAME_CATEGORIES = {"网约车行程单", "火车票", "高速通行票"}
DOUBLE_PRINT_CATEGORIES = {"火车票", "住宿票"}
TRANSPORT_CATEGORIES = {"网约车", "火车票"}
TOLL_CATEGORIES = {"高速通行票"}
LODGING_CATEGORIES = {"住宿票"}
UNKNOWN_DATE_LABEL = "未识别日期"


def format_money(value: float) -> str:
    return f"{value:.2f}"


def parse_money_text(value: str) -> float:
    text = value.strip().replace(",", "")
    if not text:
        return 0.0
    try:
        return round(float(text), 2)
    except ValueError:
        return 0.0


def calculate_summary_total(
    result: InvoiceOrganizeResult,
    subsidy_amount: float = 0.0,
    taxi_amount: float = 0.0,
    in_transit_amount: float = 0.0,
) -> float:
    return round(
        result.summary.transport_total
        + taxi_amount
        + result.summary.toll_total
        + result.summary.lodging_total
        + subsidy_amount
        + in_transit_amount,
        2,
    )


def _parse_issue_date(actual_date: str) -> tuple[int, str]:
    if not actual_date:
        return (1, UNKNOWN_DATE_LABEL)
    return (0, actual_date)


def sort_records(records: list[InvoiceOrganizeRecord]) -> None:
    records.sort(key=lambda record: (_parse_issue_date(record.issue_date), record.category, record.source_file))


def summarize_records_by_date(records: list[InvoiceOrganizeRecord]) -> list[InvoiceDateSummary]:
    """按票据实际发生日期归集；字段名为兼容历史数据仍沿用 issue_date。"""
    grouped: dict[str, dict[str, float]] = defaultdict(
        lambda: {
            "transport_total": 0.0,
            "toll_total": 0.0,
            "lodging_amount_total": 0.0,
            "lodging_tax_total": 0.0,
            "lodging_total": 0.0,
        }
    )

    for record in records:
        actual_date = record.issue_date or UNKNOWN_DATE_LABEL
        summary_bucket = grouped[actual_date]

        if record.category in TRANSPORT_CATEGORIES:
            summary_bucket["transport_total"] += record.total_amount
        if record.category in TOLL_CATEGORIES:
            summary_bucket["toll_total"] += record.total_amount
        if record.category in LODGING_CATEGORIES:
            summary_bucket["lodging_amount_total"] += record.amount
            summary_bucket["lodging_tax_total"] += record.tax_amount
            summary_bucket["lodging_total"] += record.total_amount

    rows: list[InvoiceDateSummary] = []
    for actual_date in sorted(grouped, key=_parse_issue_date):
        bucket = grouped[actual_date]
        total = bucket["transport_total"] + bucket["toll_total"] + bucket["lodging_total"]
        rows.append(
            InvoiceDateSummary(
                issue_date=actual_date,
                transport_total=round(bucket["transport_total"], 2),
                toll_total=round(bucket["toll_total"], 2),
                lodging_amount_total=round(bucket["lodging_amount_total"], 2),
                lodging_tax_total=round(bucket["lodging_tax_total"], 2),
                lodging_total=round(bucket["lodging_total"], 2),
                total=round(total, 2),
            )
        )

    return rows


def sanitize_filename_component(value: str) -> str:
    sanitized = value.strip().replace("/", "-").replace("\\", "-").replace(":", "-")
    for invalid_char in '<>"|?*':
        sanitized = sanitized.replace(invalid_char, "")
    return sanitized.strip(" .")


def build_output_directory(base_path: Path) -> Path:
    """在待整理目录内创建固定名称的输出目录，不再追加序号。"""
    return base_path / f"{base_path.name}-NewName"


def replace_output_directory(output_directory: Path) -> None:
    """删除已有输出内容，确保每次整理结果完整替换旧版本。"""
    if output_directory.is_dir():
        shutil.rmtree(output_directory)
    elif output_directory.exists():
        output_directory.unlink()
    output_directory.mkdir(parents=True, exist_ok=True)


def build_rename_target(
    source_file: str,
    category: str,
    number: str,
    total_amount: float,
    vendor: str,
    issue_date: str,
    output_folder_name: str,
) -> str:
    stem_number = sanitize_filename_component(number) if number else ""
    stem_vendor = sanitize_filename_component(vendor) if vendor else "未识别"
    date_part = issue_date or "未识别日期"
    amount_part = format_money(total_amount)

    if category == "网约车行程单" and stem_number:
        return str(Path(output_folder_name) / f"{stem_number}-{amount_part}行程单.pdf")

    if stem_number:
        base_name = f"{stem_number}-{amount_part}"
    else:
        base_name = f"{stem_vendor}-{date_part}-{amount_part}"

    if category in SPECIAL_RENAME_CATEGORIES:
        base_name = f"{base_name}-{sanitize_filename_component(category)}"

    return str(Path(output_folder_name) / f"{base_name}.pdf")


def determine_print_copies(category: str) -> int:
    return 2 if category in DOUBLE_PRINT_CATEGORIES else 1


def pair_lookup(results: list) -> dict[str, tuple[str, str]]:
    lookup: dict[str, tuple[str, str]] = {}
    for pair in results:
        lookup[pair.invoice_file] = (pair.match_key, pair.confidence)
        lookup[pair.itinerary_file] = (pair.match_key, pair.confidence)
    return lookup


def correct_ride_hailing_amount_from_filename(record_result, file_name: str) -> None:
    _, filename_amount, _ = extract_filename_pair_info(file_name)
    if filename_amount is None or record_result.category not in {"网约车", "网约车行程单"}:
        return

    record_result.total_amount = round(filename_amount, 2)

    if record_result.category == "网约车行程单":
        record_result.amount = round(filename_amount, 2)
        record_result.tax_amount = 0.0
        return

    if record_result.amount > 0 and record_result.amount <= record_result.total_amount:
        record_result.tax_amount = round(record_result.total_amount - record_result.amount, 2)
    elif record_result.tax_amount > 0 and record_result.tax_amount <= record_result.total_amount:
        record_result.amount = round(record_result.total_amount - record_result.tax_amount, 2)
    else:
        record_result.amount = record_result.total_amount
        record_result.tax_amount = 0.0


def build_review_warnings(number: str, category: str, amount: float, total_amount: float, pair_status: str) -> list[str]:
    warnings: list[str] = []
    if not number and category not in {"网约车行程单", "火车票"}:
        warnings.append("缺少发票号码")
    if total_amount <= 0:
        warnings.append("总金额未识别")
    if category == "待核验":
        warnings.append("票据类型待核验")
    if category == "网约车行程单" and pair_status == "unpaired":
        warnings.append("网约车行程单未配对")
    if category == "网约车" and total_amount <= 0 and amount <= 0:
        warnings.append("网约车金额未识别")
    return warnings


def resolve_duplicate_rename_targets(records: list[InvoiceOrganizeRecord]) -> None:
    counts = Counter(record.rename_target for record in records)
    next_index: dict[str, int] = {}

    for record in records:
        if counts[record.rename_target] == 1:
            continue

        original_target = record.rename_target
        next_index[original_target] = next_index.get(original_target, 0) + 1
        original_path = Path(original_target)
        stem = original_path.stem
        suffix = original_path.suffix
        record.rename_target = str(original_path.parent / f"{stem}_{next_index[original_target]}{suffix}")
        record.warnings.append("重命名目标重复，已追加序号")
        if record.review_status == "ok":
            record.review_status = "review_required"


def _build_table_style(include_header: bool = True) -> TableStyle:
    commands: list[tuple[object, ...]] = [
        ("FONTNAME", (0, 0), (-1, -1), "STSong-Light"),
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("LEADING", (0, 0), (-1, -1), 10),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D5DFEA")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    if include_header:
        commands.extend(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E9F3F9")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#17324D")),
            ]
        )
    return TableStyle(commands)


def format_display_date(date_value: str) -> str:
    parts = date_value.split("-")
    if len(parts) != 3:
        return date_value
    try:
        year, month, day = (int(part) for part in parts)
    except ValueError:
        return date_value
    return f"{year}-{month}-{day}"


def build_trip_summary_title(result: InvoiceOrganizeResult) -> str:
    dates = [item.issue_date for item in result.summary.daily_breakdown if item.issue_date and item.issue_date != UNKNOWN_DATE_LABEL]
    folder_name = Path(result.source_directory).name or "出差"

    if not dates:
        date_part = "未识别日期"
    else:
        unique_dates = sorted(set(dates), key=_parse_issue_date)
        if len(unique_dates) == 1:
            date_part = format_display_date(unique_dates[0])
        else:
            date_part = f"{format_display_date(unique_dates[0])}至{format_display_date(unique_dates[-1])}"

    return f"{date_part} {folder_name}出差清单"


def export_summary_sheet(
    result: InvoiceOrganizeResult,
    subsidy_amount: float = 0.0,
    taxi_amount: float = 0.0,
    travel_in_transit: str = "",
    daily_manual_values: dict[str, tuple[str, float, float]] | None = None,
) -> InvoiceOrganizeResult:
    output_directory = Path(result.output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)

    summary_pdf_path = output_directory / "汇总清单.pdf"
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))

    document = SimpleDocTemplate(
        str(summary_pdf_path),
        pagesize=A5,
        leftMargin=20,
        rightMargin=20,
        topMargin=24,
        bottomMargin=24,
        title=build_trip_summary_title(result),
    )
    title_style = ParagraphStyle(
        "TitleStyle",
        fontName="STSong-Light",
        fontSize=14,
        leading=18,
        textColor=colors.HexColor("#17324D"),
        spaceAfter=10,
    )
    body_style = ParagraphStyle(
        "BodyStyle",
        fontName="STSong-Light",
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#24384E"),
    )
    section_style = ParagraphStyle(
        "SectionStyle",
        fontName="STSong-Light",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#17324D"),
        spaceBefore=8,
        spaceAfter=6,
    )

    manual_values = daily_manual_values or {}
    daily_rows = [["日期", "大众运输", "出租车费用", "过路费", "住宿不含税", "住宿税额", "住宿合计", "在途", "出差补贴"]]
    subsidy_total = 0.0
    taxi_total = 0.0
    in_transit_total = 0.0
    for item in result.summary.daily_breakdown:
        item_travel_in_transit, item_taxi_amount, item_subsidy_amount = manual_values.get(item.issue_date, ("", 0.0, 0.0))
        taxi_total += item_taxi_amount
        subsidy_total += item_subsidy_amount
        in_transit_total += parse_money_text(item_travel_in_transit)
        daily_rows.append(
            [
                item.issue_date,
                format_money(item.transport_total),
                format_money(item_taxi_amount) if item_taxi_amount else "",
                format_money(item.toll_total),
                format_money(item.lodging_amount_total),
                format_money(item.lodging_tax_total),
                format_money(item.lodging_total),
                item_travel_in_transit,
                format_money(item_subsidy_amount) if item_subsidy_amount else "",
            ]
        )
    daily_rows.append(
        [
            "小计",
            format_money(result.summary.transport_total + taxi_total),
            format_money(taxi_total),
            format_money(result.summary.toll_total),
            format_money(result.summary.lodging_amount_total),
            format_money(result.summary.lodging_tax_total),
            format_money(result.summary.lodging_total),
            "",
            format_money(subsidy_total + in_transit_total),
        ]
    )
    effective_taxi_amount = taxi_amount if taxi_amount else taxi_total
    effective_in_transit_amount = in_transit_total
    daily_rows.append(["总计", format_money(calculate_summary_total(result, subsidy_amount, effective_taxi_amount, effective_in_transit_amount)), "", "", "", "", "", "", ""])
    subtotal_row_index = len(result.summary.daily_breakdown) + 1

    daily_table_style = _build_table_style()
    daily_table_style.add("BACKGROUND", (1, subtotal_row_index), (1, subtotal_row_index), colors.HexColor("#F9E3B8"))
    daily_table_style.add("TEXTCOLOR", (1, subtotal_row_index), (1, subtotal_row_index), colors.HexColor("#8A4B12"))
    daily_table_style.add("FONTNAME", (1, subtotal_row_index), (1, subtotal_row_index), "STSong-Light")
    daily_table_style.add("FONTSIZE", (1, subtotal_row_index), (1, subtotal_row_index), 8.5)

    checklist_rows = [
        ["□ 填写TQM报销"],
        ["□ PDF文件上传"],
        ["□ 考勤申请"],
    ]

    story = [
        Paragraph(build_trip_summary_title(result), title_style),
        Spacer(1, 10),
        Table(
            daily_rows,
            colWidths=[40, 34, 34, 32, 38, 34, 38, 32, 34],
            repeatRows=1,
            style=daily_table_style,
        ),
        Spacer(1, 10),
        Paragraph("报销流程检查", section_style),
        Table(
            checklist_rows,
            colWidths=[316],
            style=TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), "STSong-Light"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("LEADING", (0, 0), (-1, -1), 12),
                    ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#24384E")),
                    ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                    ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#D8CDBD")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#E7DBCC")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ]
            ),
        ),
        Spacer(1, 8),
        Paragraph(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", body_style),
    ]
    document.build(story)

    result.summary_sheet_pdf = str(summary_pdf_path)
    return result


def organize_invoice_directory(directory: str | Path, *, enable_ocr: bool = False) -> InvoiceOrganizeResult:
    base_path = Path(directory)
    if not base_path.exists() or not base_path.is_dir():
        raise NotADirectoryError(f"目录不存在: {base_path}")

    output_directory = build_output_directory(base_path)
    output_folder_name = output_directory.name
    pair_results = pair_ride_hailing_documents(base_path, enable_ocr=enable_ocr)
    pair_status_lookup = pair_lookup(pair_results)
    records: list[InvoiceOrganizeRecord] = []

    for file_path in sorted(base_path.glob("*.pdf")):
        text, text_source, ocr_used = extract_text(file_path, enable_ocr=enable_ocr)
        result = recognize_invoice_text(text, str(file_path))
        result.text_source = text_source
        result.ocr_used = ocr_used
        correct_ride_hailing_amount_from_filename(result, file_path.name)

        pair_key, pair_confidence = pair_status_lookup.get(file_path.name, ("", "unpaired"))
        rename_target = build_rename_target(
            file_path.name,
            result.category,
            result.number,
            result.total_amount,
            result.vendor,
            result.issue_date,
            output_folder_name,
        )
        warnings = build_review_warnings(
            result.number,
            result.category,
            result.amount,
            result.total_amount,
            pair_confidence,
        )
        hints = [f"住宿天数：{result.matched_rules['lodging_stay_days']}"] if result.matched_rules.get("lodging_stay_days") else []
        review_status = "review_required" if warnings else "ok"

        records.append(
            InvoiceOrganizeRecord(
                source_file=file_path.name,
                source_path=str(file_path),
                category=result.category,
                number=result.number,
                vendor=result.vendor,
                issue_date=result.issue_date,
                amount=result.amount,
                tax_amount=result.tax_amount,
                total_amount=result.total_amount,
                text_source=result.text_source,
                ocr_used=result.ocr_used,
                rename_target=rename_target,
                print_copies=determine_print_copies(result.category),
                printed=False,
                pair_key=pair_key,
                pair_status=pair_confidence,
                review_status=review_status,
                warnings=warnings,
                hints=hints,
            )
        )

    record_by_source_file = {record.source_file: record for record in records}
    for pair in pair_results:
        invoice_record = record_by_source_file.get(pair.invoice_file)
        itinerary_record = record_by_source_file.get(pair.itinerary_file)

        if invoice_record is None or itinerary_record is None:
            continue

        if itinerary_record.category != "网约车行程单":
            continue

        if itinerary_record.issue_date:
            invoice_record.issue_date = itinerary_record.issue_date

        if not invoice_record.number:
            continue

        itinerary_record.rename_target = build_rename_target(
            itinerary_record.source_file,
            itinerary_record.category,
            invoice_record.number,
            itinerary_record.total_amount,
            itinerary_record.vendor,
            itinerary_record.issue_date,
            output_folder_name,
        )

    resolve_duplicate_rename_targets(records)
    sort_records(records)

    summary = InvoiceOrganizeSummary(
        total_files=len(records),
        recognized_files=sum(1 for record in records if record.category != "待核验"),
        review_required=sum(1 for record in records if record.review_status == "review_required"),
        transport_total=round(
            sum(record.total_amount for record in records if record.category in TRANSPORT_CATEGORIES),
            2,
        ),
        toll_total=round(
            sum(record.total_amount for record in records if record.category in TOLL_CATEGORIES),
            2,
        ),
        lodging_amount_total=round(
            sum(record.amount for record in records if record.category in LODGING_CATEGORIES),
            2,
        ),
        lodging_tax_total=round(
            sum(record.tax_amount for record in records if record.category in LODGING_CATEGORIES),
            2,
        ),
        lodging_total=round(
            sum(record.total_amount for record in records if record.category in LODGING_CATEGORIES),
            2,
        ),
        daily_breakdown=summarize_records_by_date(records),
    )

    return InvoiceOrganizeResult(
        source_directory=str(base_path),
        output_directory=str(output_directory),
        applied=False,
        summary_sheet_pdf="",
        summary=summary,
        ride_hailing_pairs=pair_results,
        records=records,
    )


def apply_organize_result(result: InvoiceOrganizeResult) -> InvoiceOrganizeResult:
    output_directory = Path(result.output_directory)
    replace_output_directory(output_directory)

    for record in result.records:
        source_path = Path(record.source_path)
        target_path = Path(result.source_directory) / record.rename_target
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target_path)

    result.applied = True
    return export_summary_sheet(result)