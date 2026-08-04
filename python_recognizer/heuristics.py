from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from .types import InvoiceRecognitionResult

MONEY_PATTERN = r"([0-9][0-9,\s]*(?:\.[0-9]{1,2})?)"


def normalize_text(input_text: str) -> str:
    return re.sub(r"\s+", " ", input_text).strip()


def parse_numeric_value(value: str) -> float:
    return float(value.replace(",", "").replace(" ", ""))


def approximately_equal(left: float, right: float, tolerance: float = 0.02) -> bool:
    return abs(left - right) <= tolerance


def get_money_upper_bound(category: str) -> float:
    category_limits = {
        "网约车": 300,
        "网约车行程单": 300,
        "高速通行票": 300,
        "火车票": 2000,
        "住宿票": 5000,
        "机票": 5000,
    }
    return category_limits.get(category, 5000)


def sanitize_money_value(value: float, category: str) -> float:
    return value if 0 <= value <= get_money_upper_bound(category) else 0.0


def extract_numeric_field(text: str, patterns: list[tuple[str, re.Pattern[str]]]) -> tuple[float, str]:
    for label, pattern in patterns:
        match = pattern.search(text)
        if match and match.group(1):
            return parse_numeric_value(match.group(1)), label

    return 0.0, "未命中"


def extract_currency_candidates(text: str) -> list[float]:
    values = [
        parse_numeric_value(match.group(1))
        for match in re.finditer(rf"[¥￥]\s*{MONEY_PATTERN}", text)
        if match.group(1)
    ]
    return sorted({value for value in values if value > 0}, reverse=True)


def extract_train_ticket_fare(text: str) -> tuple[float, str]:
    patterns = [
        (
            "车次+座席邻近金额",
            re.compile(
                r"\b[gdcztk]\d{1,4}\b[\s\S]{0,80}?(?:一等座|二等座|商务座|软卧|硬卧|硬座|无座|座)\s*[:：]?\s*([0-9]+(?:\.[0-9]{1,2})?)",
                re.IGNORECASE,
            ),
        ),
        (
            "座位号后冒号金额",
            re.compile(
                r"\b\d{1,2}[A-F]\b\s*[:：]\s*([0-9]+(?:\.[0-9]{1,2})?)\s+(?:\d{6,}\*{2,}\d{4}|\d{18}|\d{17}[\dxX])",
            ),
        ),
        (
            "时间后冒号金额",
            re.compile(
                r"\b\d{2}:\d{2}\b[\s\S]{0,40}?[:：]\s*([0-9]+(?:\.[0-9]{1,2})?)\s+(?:\d{6,}\*{2,}\d{4}|\d{18}|\d{17}[\dxX])",
            ),
        ),
    ]
    return extract_numeric_field(text, patterns)


def extract_train_ticket_trip_date(text: str) -> tuple[str, str]:
    patterns = [
        (
            "车次后乘车日期",
            re.compile(r"\b[gdcztk]\d{1,4}\b[\s\S]{0,160}?(20\d{2}[-/.年]\d{1,2}[-/.月]\d{1,2}日?)", re.IGNORECASE),
        ),
        (
            "乘车日期字段",
            re.compile(r"(?:乘车日期|发车日期|乘车时间|开车时间|发车时间)\s*[:：]?\s*(20\d{2}[-/.年]\d{1,2}[-/.月]\d{1,2}日?)"),
        ),
    ]

    for label, pattern in patterns:
        match = pattern.search(text)
        if match and match.group(1):
            trip_date = normalize_date_value(match.group(1))
            if trip_date:
                return trip_date, label

    return "", "未命中"


def normalize_month_day_value(value: str, year: int) -> str:
    date_parts = re.findall(r"\d+", value)
    if len(date_parts) < 2:
        return ""
    month, day = (int(part) for part in date_parts[:2])
    if not 1 <= month <= 12 or not 1 <= day <= 31:
        return ""
    return f"{year:04d}-{month:02d}-{day:02d}"


def extract_lodging_start_date(text: str, fallback_year: Optional[int] = None) -> tuple[str, str]:
    """提取酒店入住起始日期；跨夜住宿统一归入入住当天。"""
    patterns = [
        (
            "入住日期字段",
            re.compile(r"(?:入住日期|入住时间|住店日期|抵店日期)\s*[:：]?\s*(20\d{2}[-/.年]\d{1,2}[-/.月]\d{1,2}日?)"),
        ),
        (
            "住宿日期范围起始日",
            re.compile(
                r"(20\d{2}[-/.年]\d{1,2}[-/.月]\d{1,2}日?)\s*(?:至|到|[-~～])\s*20\d{2}[-/.年]\d{1,2}[-/.月]\d{1,2}日?"
            ),
        ),
    ]

    for label, pattern in patterns:
        match = pattern.search(text)
        if match and match.group(1):
            start_date = normalize_date_value(match.group(1))
            if start_date:
                return start_date, label

    if fallback_year is not None:
        short_date_patterns = [
            (
                "入住日期字段（补全年份）",
                re.compile(r"(?:入住日期|入住时间|住店日期|抵店日期)\s*[:：]?\s*(\d{1,2}\s*[-/.月]\s*\d{1,2}日?)"),
            ),
            (
                "住宿日期范围起始日（补全年份）",
                re.compile(r"(\d{1,2}\s*[-/.月]\s*\d{1,2}日?)\s*(?:至|到|[-~～])\s*\d{1,2}\s*[-/.月]\s*\d{1,2}日?"),
            ),
        ]
        for label, pattern in short_date_patterns:
            match = pattern.search(text)
            if match and match.group(1):
                start_date = normalize_month_day_value(match.group(1), fallback_year)
                if start_date:
                    return start_date, label

    return "", "未命中"


def extract_lodging_stay_days(text: str) -> str:
    """提取住宿票据注明的入住天数，用于明细提示栏展示。"""
    match = re.search(r"(?:入住日期|入住时间|入离日期|住店日期)[\s\S]{0,80}?共\s*(\d+)\s*天", text)
    return f"{match.group(1)}天" if match else ""


def extract_toll_trip_date(text: str) -> tuple[str, str]:
    """提取高速通行票的实际通行日期，无法识别时由调用方回退开票日期。"""
    patterns = [
        (
            "通行日期字段",
            re.compile(r"(?:通行日期|通行时间|交易日期|驶入时间|驶出时间)\s*[:：]?\s*(20\d{2}[-/.年]\d{1,2}[-/.月]\d{1,2}日?)"),
        ),
        (
            "通行时间表格日期",
            re.compile(r"(?:通行日期|通行时间|交易日期)[\s\S]{0,80}?(20\d{2}[-/.年]\d{1,2}[-/.月]\d{1,2}日?)\s+\d{1,2}:\d{2}"),
        ),
    ]

    for label, pattern in patterns:
        match = pattern.search(text)
        if match and match.group(1):
            trip_date = normalize_date_value(match.group(1))
            if trip_date:
                return trip_date, label

    return "", "未命中"


def extract_lodging_line_amounts(text: str) -> tuple[float, float, str] | None:
    patterns = [
        (
            "住宿表格行金额税额",
            re.compile(
                rf"(?:\*?(?:住宿服务|房费|客房费|住宿费)\*?)([\s\S]{{0,160}}?)([0-9]+(?:\.[0-9]{{1,2}})?)%\s+([0-9][0-9,\s]*(?:\.[0-9]{{1,2}})?)"
            ),
        ),
        (
            "住宿项目名称到税率列",
            re.compile(
                rf"项目名称[\s\S]{{0,120}}?(?:\*?(?:住宿服务|房费|客房费|住宿费)\*?)([\s\S]{{0,160}}?)([0-9]+(?:\.[0-9]{{1,2}})?)%\s+([0-9][0-9,\s]*(?:\.[0-9]{{1,2}})?)"
            ),
        ),
    ]

    for label, pattern in patterns:
        match = pattern.search(text)
        if not match:
            continue

        numeric_candidates = [
            parse_numeric_value(candidate)
            for candidate in re.findall(r"[0-9]+(?:\.[0-9]{1,6})?", match.group(1))
        ]

        if not numeric_candidates:
            continue

        amount = numeric_candidates[-1]
        tax_amount = parse_numeric_value(match.group(3))
        return amount, tax_amount, label

    return None


def extract_ride_itinerary_amounts(text: str) -> tuple[float, float, float, str] | None:
    patterns = [
        (
            "网约车行程单合计",
            re.compile(r"(?:共计|合计)\s*(?:\d+)\s*单行程[^0-9]{0,8}([0-9]+(?:\.[0-9]{1,2})?)\s*元"),
        ),
        (
            "网约车行程单金额合计",
            re.compile(r"(?:行程单|ITINERARY)[\s\S]{0,120}?(?:合计|总计)\s*([0-9]+(?:\.[0-9]{1,2})?)\s*元", re.IGNORECASE),
        ),
    ]

    for label, pattern in patterns:
        match = pattern.search(text)
        if match and match.group(1):
            total_amount = parse_numeric_value(match.group(1))
            return total_amount, total_amount, 0.0, label

    return None


def normalize_date_value(value: str) -> str:
    date_parts = re.findall(r"\d+", value)
    if len(date_parts) < 3:
        return ""
    year, month, day = date_parts[:3]
    return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"


def extract_ride_itinerary_trip_date(text: str) -> tuple[str, str]:
    patterns = [
        (
            "行程时间日期",
            re.compile(r"(?:行程时间|行程日期|乘车时间|用车时间|上车时间|出发时间)\s*[:：]?\s*(20\d{2}[-/.年]\d{1,2}[-/.月]\d{1,2}日?)"),
        ),
        (
            "行程时间范围日期",
            re.compile(r"(?:行程时间|行程日期)[\s\S]{0,30}?(20\d{2}[-/.年]\d{1,2}[-/.月]\d{1,2}日?)[\s\S]{0,20}?(?:至|到|-)"),
        ),
        (
            "上车时间表格日期",
            re.compile(r"(?:上车时间|出发时间)[\s\S]{0,80}?(20\d{2}[-/.年]\d{1,2}[-/.月]\d{1,2}日?)\s+\d{1,2}:\d{2}"),
        ),
    ]

    for label, pattern in patterns:
        match = pattern.search(text)
        if match and match.group(1):
            trip_date = normalize_date_value(match.group(1))
            if trip_date:
                return trip_date, label

    return "", "未命中"


def derive_invoice_category(text: str, attachment_name: str, vendor: str) -> str:
    corpus = f"{text} {attachment_name} {vendor}"
    rules: list[tuple[re.Pattern[str], str]] = [
        (re.compile(r"(行程单|AMAP\s+ITINERARY|高德地图.*打车|滴滴.*行程单)", re.IGNORECASE), "网约车行程单"),
        (re.compile(r"(火车票|铁路电子客票|铁路车票|电子客票|高铁|动车|铁路|国内旅客运输服务|12306|95306|\b[gdcztk]\d{1,4}\b|一等座|二等座|商务座)", re.IGNORECASE), "火车票"),
        (re.compile(r"(网约车|滴滴|出行服务|出租汽车|出租车|打车|客运服务|代驾|出行人|出发地|到达地|交通工具类型|行程起点|行程终点|里程费|时长费)", re.IGNORECASE), "网约车"),
        (re.compile(r"(住宿|酒店|宾馆|旅店|客房|房费|住宿服务)", re.IGNORECASE), "住宿票"),
        (re.compile(r"(通行费|高速|收费公路|etc|过路费|车辆通行服务|通行服务)", re.IGNORECASE), "高速通行票"),
        (re.compile(r"(航空运输电子客票|机票|航班|航空公司|民航|航空运输服务)", re.IGNORECASE), "机票"),
        (re.compile(r"(餐饮|餐费|饭店|餐厅|美食)", re.IGNORECASE), "餐饮"),
        (re.compile(r"(加油|燃油|石油|石化)", re.IGNORECASE), "加油票"),
        (re.compile(r"(办公|文具|打印|耗材)", re.IGNORECASE), "办公"),
    ]

    for pattern, category in rules:
        if pattern.search(corpus):
            return category

    return "待核验"


def extract_named_party(text: str, section_label: str) -> str:
    escaped_label = re.escape(section_label)
    patterns = [
        re.compile(
            rf"{escaped_label}[\s\S]{{0,120}}?名称[:：]?\s*([\u4e00-\u9fa5A-Za-z0-9()（）·\-]{4,80}?(?:公司|中心|酒店|宾馆|商店|超市|集团|科技|电子|服务部))"
        ),
        re.compile(
            rf"{escaped_label}[\s\S]{{0,160}}?([\u4e00-\u9fa5A-Za-z0-9()（）·\-]{4,80}?(?:公司|中心|酒店|宾馆|商店|超市|集团|科技|电子|服务部))"
        ),
    ]

    for pattern in patterns:
        match = pattern.search(text)
        if match:
            return match.group(1)

    return ""


def extract_vendor_name(text: str, source_file: str) -> str:
    railway_vendor_patterns = [
        re.compile(r"电子发票（中国铁路）"),
        re.compile(r"中国铁路"),
        re.compile(r"铁路电子客票"),
    ]

    for pattern in railway_vendor_patterns:
        if pattern.search(text):
            return "电子发票（中国铁路）"

    ride_vendor_patterns = [
        re.compile(r"(高德地图)[—-]?打车", re.IGNORECASE),
        re.compile(r"(滴滴出行|滴滴)"),
        re.compile(r"(曹操出行|T3出行|美团打车|阳光出行)"),
    ]

    for pattern in ride_vendor_patterns:
        match = pattern.search(text)
        if match:
            return match.group(1)

    buyer_name = extract_named_party(text, "购买方信息")
    if buyer_name:
        return buyer_name

    seller_name = extract_named_party(text, "销售方信息")
    if seller_name:
        return seller_name

    company_names = re.findall(
        r"([\u4e00-\u9fa5A-Za-z0-9()（）·\-]{4,80}?(?:公司|中心|酒店|宾馆|商店|超市|集团|科技|电子|服务部))",
        text,
    )
    for company_name in company_names:
        if company_name not in {"购买方信息", "销售方信息"}:
            return company_name

    return Path(source_file).stem


def derive_amounts_from_candidates(candidates: list[float]) -> tuple[float, float, float, dict[str, str]] | None:
    normalized_candidates = sorted({value for value in candidates if value > 0}, reverse=True)

    for total in normalized_candidates:
        for amount in normalized_candidates:
            if amount >= total:
                continue

            derived_tax = round(total - amount, 2)
            matching_tax = next(
                (candidate for candidate in normalized_candidates if approximately_equal(candidate, derived_tax)),
                None,
            )

            if derived_tax > 0 and (matching_tax is not None or derived_tax <= total * 0.2):
                return total, amount, matching_tax or derived_tax, {
                    "total_amount": "货币候选推导",
                    "amount": "总额减税额推导",
                    "tax_amount": "货币候选匹配税额" if matching_tax is not None else "总额减金额推导",
                }

    return None


def recognize_invoice_text(text: str, source_file: str) -> InvoiceRecognitionResult:
    compact_text = normalize_text(text)
    date_match = re.search(r"(20\d{2}[-/.年]\d{1,2}[-/.月]\d{1,2}日?)", compact_text)
    fallback_year = int(re.search(r"20\d{2}", date_match.group(1)).group()) if date_match else None
    lodging_line_amounts = extract_lodging_line_amounts(compact_text)
    ride_itinerary_amounts = extract_ride_itinerary_amounts(compact_text)
    ride_itinerary_trip_date, ride_itinerary_trip_date_rule = extract_ride_itinerary_trip_date(compact_text)
    train_ticket_trip_date, train_ticket_trip_date_rule = extract_train_ticket_trip_date(compact_text)
    lodging_start_date, lodging_start_date_rule = extract_lodging_start_date(compact_text, fallback_year)
    lodging_stay_days = extract_lodging_stay_days(compact_text)
    toll_trip_date, toll_trip_date_rule = extract_toll_trip_date(compact_text)

    explicit_number_match = re.search(r"(?:发票号码|票据号码|号码)[:：]?\s*([0-9]{8,20})", compact_text)
    generic_number_match = re.search(r"\b([0-9]{8,20})\b", compact_text)

    total_amount, total_rule = extract_numeric_field(
        compact_text,
        [
            ("票价直接命中", re.compile(rf"票价\s*[:：]?\s*[¥￥]?\s*{MONEY_PATTERN}")),
            ("票价邻近货币符号", re.compile(rf"票价[^0-9¥￥]{{0,12}}[¥￥]\s*{MONEY_PATTERN}")),
            (
                "价税合计直接命中",
                re.compile(rf"(?:价税合计(?:\(小写\)|（小写）)?|合计金额|小写|票价)\s*[:：]?\s*[¥￥]?\s*{MONEY_PATTERN}"),
            ),
            (
                "价税合计邻近货币符号",
                re.compile(rf"(?:价税合计(?:\(小写\)|（小写）)?|合计金额|小写|票价)[^0-9¥￥]{{0,16}}[¥￥]?\s*{MONEY_PATTERN}"),
            ),
        ],
    )
    tax_amount, tax_rule = extract_numeric_field(
        compact_text,
        [
            ("税额直接命中", re.compile(rf"(?:税额合计|税额|税金)\s*[:：]?\s*[¥￥]?\s*{MONEY_PATTERN}")),
            ("税额邻近货币符号", re.compile(rf"(?:税额合计|税额|税金)[^0-9¥￥]{{0,12}}[¥￥]?\s*{MONEY_PATTERN}")),
        ],
    )
    amount, amount_rule = extract_numeric_field(
        compact_text,
        [
            ("金额直接命中", re.compile(rf"(?:不含税金额|金额合计|金额小计|金额)\s*[:：]?\s*[¥￥]?\s*{MONEY_PATTERN}")),
            ("金额邻近货币符号", re.compile(rf"(?:不含税金额|金额合计|金额小计)[^0-9¥￥]{{0,12}}[¥￥]?\s*{MONEY_PATTERN}")),
        ],
    )

    if lodging_line_amounts:
        amount = amount or lodging_line_amounts[0]
        tax_amount = tax_amount or lodging_line_amounts[1]
        if amount_rule == "未命中":
            amount_rule = lodging_line_amounts[2]
        if tax_rule == "未命中":
            tax_rule = lodging_line_amounts[2]

    vendor = extract_vendor_name(compact_text, source_file)
    category = derive_invoice_category(compact_text, source_file, vendor)

    if ride_itinerary_amounts and category == "网约车行程单":
        total_amount = total_amount or ride_itinerary_amounts[0]
        amount = amount if amount > 1 else ride_itinerary_amounts[1]
        tax_amount = tax_amount or ride_itinerary_amounts[2]
        if total_rule == "未命中":
            total_rule = ride_itinerary_amounts[3]
        if amount_rule == "未命中" or amount <= 1:
            amount_rule = ride_itinerary_amounts[3]

    total_amount = sanitize_money_value(total_amount, category)
    tax_amount = sanitize_money_value(tax_amount, category)
    amount = sanitize_money_value(amount, category)
    currency_candidates = [
        candidate
        for candidate in extract_currency_candidates(compact_text)
        if sanitize_money_value(candidate, category) > 0
    ]

    train_fare, train_fare_rule = extract_train_ticket_fare(compact_text) if category == "火车票" else (0.0, "未命中")
    train_fare = sanitize_money_value(train_fare, category)

    if explicit_number_match:
        resolved_number = explicit_number_match.group(1)
    elif category == "网约车行程单":
        resolved_number = ""
    else:
        resolved_number = generic_number_match.group(1) if generic_number_match else ""

    fallback_total_amount = total_amount or train_fare or (currency_candidates[0] if currency_candidates else 0.0)
    fallback_tax_amount = tax_amount or 0.0
    derived_amount_from_total = round(fallback_total_amount - fallback_tax_amount, 2) if fallback_total_amount and fallback_tax_amount else 0.0
    candidate_derived = derive_amounts_from_candidates(currency_candidates)

    resolved_amount = amount or derived_amount_from_total or (candidate_derived[1] if candidate_derived else 0.0)
    resolved_tax_amount = (
        fallback_tax_amount
        or (round(fallback_total_amount - resolved_amount, 2) if fallback_total_amount and resolved_amount else 0.0)
        or (candidate_derived[2] if candidate_derived else 0.0)
    )
    resolved_total_amount = fallback_total_amount or (candidate_derived[0] if candidate_derived else 0.0)

    if not total_amount and candidate_derived:
        total_rule = candidate_derived[3]["total_amount"]
    elif not total_amount and currency_candidates:
        total_rule = "货币候选最大值"

    if not amount and candidate_derived:
        amount_rule = candidate_derived[3]["amount"]
    elif not amount and derived_amount_from_total:
        amount_rule = "总额减税额推导"

    if not tax_amount and candidate_derived:
        tax_rule = candidate_derived[3]["tax_amount"]
    elif not tax_amount and resolved_tax_amount:
        tax_rule = "总额减金额推导"

    issue_date = ""
    if date_match:
        issue_date = normalize_date_value(date_match.group(1))

    if category in {"网约车", "网约车行程单"} and ride_itinerary_trip_date:
        issue_date = ride_itinerary_trip_date
    elif category == "火车票" and train_ticket_trip_date:
        issue_date = train_ticket_trip_date
    elif category == "住宿票" and lodging_start_date:
        issue_date = lodging_start_date
    elif category == "高速通行票" and toll_trip_date:
        issue_date = toll_trip_date

    return InvoiceRecognitionResult(
        source_file=Path(source_file).name,
        text_source="pdf_text",
        ocr_used=False,
        number=resolved_number,
        vendor=vendor,
        amount=resolved_amount,
        tax_amount=resolved_tax_amount,
        total_amount=resolved_total_amount or round(resolved_amount + resolved_tax_amount, 2),
        issue_date=issue_date,
        category=category,
        text_length=len(compact_text),
        notes=compact_text[:180],
        matched_rules={
            "total_amount": total_rule,
            "amount": amount_rule,
            "tax_amount": tax_rule,
            "train_fare": train_fare_rule,
            "lodging_stay_days": lodging_stay_days,
            "issue_date": (
                ride_itinerary_trip_date_rule
                if category in {"网约车", "网约车行程单"}
                else train_ticket_trip_date_rule
                if category == "火车票"
                else lodging_start_date_rule
                if category == "住宿票" and lodging_start_date
                else toll_trip_date_rule
                if category == "高速通行票" and toll_trip_date
                else "开票日期"
            ),
        },
    )
