"""出差清单专用的网约车按日分摊，不修改发票记录或原有汇总。"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal
import re

from .types import InvoiceDateSummary, InvoiceOrganizeRecord, RideHailingPairResult


FULL_DATE = r"20\d{2}\s*[-/.年]\s*\d{1,2}\s*[-/.月]\s*\d{1,2}日?"
OPTIONAL_TIME = r"(?:\s+\d{1,2}[:：]\d{2}(?:[:：]\d{2})?)?"
TRIP_DATETIME = re.compile(
    r"(?<!\d)(?:(?P<year>20\d{2})\s*[-/.年]\s*)?"
    r"(?P<month>\d{1,2})\s*[-/.月]\s*(?P<day>\d{1,2})日?\s*"
    # 日期/时间分行时，坐标排序可能将同一行的“序号 车型”插在二者之间。
    r"(?:\d{1,4}\s+[\u4e00-\u9fffA-Za-z][\u4e00-\u9fffA-Za-z0-9·（）()\-]{0,15}\s+)?"
    r"(?P<hour>\d{1,2})\s*[:：]\s*(?P<minute>\d{2})(?:\s*[:：]\s*\d{2})?"
)
NUMBER = r"\d+(?:\s*\.\s*\d{1,2})?"
MILEAGE_AND_FARE = re.compile(
    rf"(?<!\S)({NUMBER})\s+(?:[¥￥]\s*)?({NUMBER})(?:\s*元)?(?=\s|$)"
)


def _cents(value: float) -> int:
    return int(Decimal(str(value)).quantize(Decimal("0.01")) * 100)


def _date_value(value: str) -> date:
    return date(*(int(part) for part in re.findall(r"\d+", value)[:3]))


def extract_ride_trip_amounts(text: str, reference_date: str) -> list[tuple[str, float]]:
    """读取行程表每行的日期与金额；不将页头合计、里程或下一行序号当费用。"""
    text = text.replace("．", ".").replace("\u3000", " ")
    range_match = re.search(
        rf"(?:行程起止日期|行程日期|行程时间)\s*[:：]?\s*({FULL_DATE}){OPTIONAL_TIME}"
        rf"\s*(?:至|到|~|～|—|–|-)\s*({FULL_DATE}){OPTIONAL_TIME}",
        text,
    )
    start_date = end_date = None
    try:
        if range_match:
            start_date, end_date = (_date_value(value) for value in range_match.groups())
            if end_date < start_date:
                return []
        reference_year = start_date.year if start_date else _date_value(reference_date).year
    except (ValueError, TypeError):
        reference_year = None

    # 页头的行程起止时间不是实际乘车行；只从表头之后读取逐笔记录。
    header = re.search(r"(?:上车时间|出发时间|乘车时间)", text)
    body = text[header.end():] if header else text
    matches = list(TRIP_DATETIME.finditer(body))
    if not matches:
        return []
    count_match = re.search(r"共(?:计)?\s*(\d+)\s*(?:笔|单|个)?\s*行程", text)
    if count_match and len(matches) != int(count_match.group(1)):
        return []

    trips: list[tuple[str, float]] = []
    for index, match in enumerate(matches):
        if int(match.group("hour")) > 23 or int(match.group("minute")) > 59:
            return []
        year = int(match.group("year")) if match.group("year") else reference_year
        if year is None:
            return []
        try:
            if not match.group("year") and start_date and end_date:
                # 月日格式跨年时，以页头起止日期确定真实年份，而非一律用申请年份。
                candidates = []
                for candidate_year in range(start_date.year, end_date.year + 1):
                    try:
                        candidate = date(candidate_year, int(match.group("month")), int(match.group("day")))
                    except ValueError:
                        continue
                    if start_date <= candidate <= end_date:
                        candidates.append(candidate)
                if len(candidates) != 1:
                    return []
                trip_date = candidates[0]
            else:
                trip_date = date(year, int(match.group("month")), int(match.group("day")))
            if start_date and end_date and not start_date <= trip_date <= end_date:
                return []
        except ValueError:
            return []

        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        row = body[match.end():end]
        row = re.split(r"(?:合计|总计|共计|温馨提示|说明[:：]|备注[:：]|序号|申请日期|行程起止日期)", row, maxsplit=1)[0]
        # 下一个日期前可能含有下一行的“序号 车型”，必须在找末尾金额前移除。
        row = re.sub(r"\s+\d+\s+[^\d\s]\S*(?:\s+[^\d\s]\S*)*\s*$", "", row)
        # 使用重叠匹配，避免地址内单独的数字吞掉后面的里程/金额组合。
        amounts = [
            MILEAGE_AND_FARE.match(row, position)
            for position in range(len(row))
            if position == 0 or row[position - 1].isspace()
        ]
        amounts = [value for value in amounts if value is not None]
        if not amounts:
            return []
        amount = float(re.sub(r"\s+", "", amounts[-1].group(2)))
        trips.append((trip_date.isoformat(), amount))

    return trips


def build_trip_daily_breakdown(
    daily_breakdown: list[InvoiceDateSummary],
    records: list[InvoiceOrganizeRecord],
    pairs: list[RideHailingPairResult],
    itinerary_texts: dict[str, str],
) -> list[InvoiceDateSummary]:
    """仅替换清单中的已配对网约车交通金额，其他费用及原始数据保持不变。"""
    rows = {item.issue_date: replace(item) for item in daily_breakdown}
    by_file = {record.source_file: record for record in records}
    used_invoices: set[str] = set()
    used_itineraries: set[str] = set()

    def add_transport(issue_date: str, cents: int) -> None:
        if issue_date not in rows:
            rows[issue_date] = InvoiceDateSummary(issue_date, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, "", 0.0)
        row = rows[issue_date]
        row.transport_total = (_cents(row.transport_total) + cents) / 100
        row.total = (_cents(row.total) + cents) / 100

    for pair in pairs:
        invoice = by_file.get(pair.invoice_file)
        itinerary = by_file.get(pair.itinerary_file)
        if invoice is None or itinerary is None:
            continue
        if invoice.category != "网约车" or itinerary.category != "网约车行程单":
            continue
        if invoice.source_file in used_invoices or itinerary.source_file in used_itineraries:
            continue
        trips = extract_ride_trip_amounts(itinerary_texts.get(itinerary.source_file, ""), itinerary.issue_date)
        trip_total = sum(_cents(amount) for _, amount in trips)
        # 明细不完整、金额不一致或无法配对时保留原归集，绝不部分拆分造成漏计。
        if not trips or trip_total <= 0 or trip_total != _cents(invoice.total_amount) or trip_total != _cents(itinerary.total_amount):
            continue
        add_transport(invoice.issue_date or "未识别日期", -trip_total)
        for trip_date, amount in trips:
            add_transport(trip_date, _cents(amount))
        used_invoices.add(invoice.source_file)
        used_itineraries.add(itinerary.source_file)

    return [rows[key] for key in sorted(rows, key=lambda value: (value == "未识别日期", value))]