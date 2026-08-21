from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from .types import InvoiceRecognitionResult

MONEY_PATTERN = r"([0-9][0-9,\s]*(?:\s*\.\s*[0-9]{1,2})?)"
EXPECTED_BUYER_TAX_ID = "91320594688334374M"


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
        "高速通行费行程单": 300,
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
                r"\b[gdcztk]\d{1,4}\b[\s\S]{0,80}?(?:一等座|二等座|商务座|软卧|硬卧|硬座|无座|座)\s*[:：]?\s*([0-9]+(?:\s*\.\s*[0-9]{1,2})?)",
                re.IGNORECASE,
            ),
        ),
        (
            "座位号后冒号金额",
            re.compile(
                r"\b\d{1,2}[A-F]\b\s*[:：]\s*([0-9]+(?:\s*\.\s*[0-9]{1,2})?)\s+(?:\d{6,}\*{2,}\d{4}|\d{18}|\d{17}[\dxX])",
            ),
        ),
        (
            "时间后冒号金额",
            re.compile(
                r"\b\d{2}:\d{2}\b[\s\S]{0,40}?[:：]\s*([0-9]+(?:\s*\.\s*[0-9]{1,2})?)\s+(?:\d{6,}\*{2,}\d{4}|\d{18}|\d{17}[\dxX])",
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
            re.compile(r"(?:通行日期(?:起|止)?|通行时间(?:起|止)?|交易日期|驶入时间|驶出时间)\s*[:：]?\s*(20\d{2}(?:[-/.年]\d{1,2}[-/.月]\d{1,2}日?|\d{4}))"),
        ),
        (
            "通行时间表格日期",
            re.compile(r"(?:通行日期(?:起|止)?|通行时间(?:起|止)?|交易日期)[\s\S]{0,80}?(20\d{2}(?:[-/.年]\d{1,2}[-/.月]\d{1,2}日?|\d{4}))\s+\d{1,2}:\d{2}"),
        ),
    ]

    for label, pattern in patterns:
        match = pattern.search(text)
        if match and match.group(1):
            trip_date = normalize_date_value(match.group(1))
            if trip_date:
                return trip_date, label

    return "", "未命中"


def extract_toll_line_amounts(text: str) -> tuple[float, float, str] | None:
    """从高速票的项目明细行提取不含税金额和税额。

    高速票常见为“经营租赁*通行费 0.72 3% 0.02”。当 OCR 漏读“价税合计”
    标签或货币符号时，仍可据此计算价税合计。
    """
    item_match = re.search(
        r"(?:经营租赁\s*\*?\s*通行费|车辆通行服务|收费公路通行费|\*?通行费\*?)([\s\S]{0,240})",
        text,
        re.IGNORECASE,
    )
    if not item_match:
        return None

    item_text = item_match.group(1)
    tax_rate_match = re.search(r"\d+(?:\s*\.\s*\d+)?\s*%", item_text)
    if not tax_rate_match:
        return None

    # 税额位于税率列之后、底部“合计 / 价税合计”之前。若不截断，扫描顺序
    # 会把价税合计 22.66 一并作为税额候选，进而错误推导出 22.00 元总额。
    tax_text = item_text[tax_rate_match.end():]
    total_label_match = re.search(r"(?:价\s*税\s*合\s*计|合\s*计|小\s*写)", tax_text)
    if total_label_match:
        tax_text = tax_text[:total_label_match.start()]

    amount_values = [
        parse_numeric_value(match.group(0))
        for match in re.finditer(r"\d+\s*\.\s*\d{1,2}", item_text[:tax_rate_match.start()])
    ]
    tax_values = [
        parse_numeric_value(match.group(0))
        for match in re.finditer(r"\d+\s*\.\s*\d{1,2}", tax_text)
    ]
    upper_bound = get_money_upper_bound("高速通行票")
    amount = next((value for value in reversed(amount_values) if 0 < value <= upper_bound), 0.0)
    tax_amount = next((value for value in tax_values if 0 <= value <= upper_bound), 0.0)
    if amount <= 0 or tax_amount < 0:
        return None

    return amount, tax_amount, "高速通行费项目行金额税额"


def reconcile_amounts(
    total_amount: float,
    amount: float,
    tax_amount: float,
    category: str,
) -> tuple[float, float, float, bool]:
    """根据金额加税额校验价税合计，修正 OCR 遗漏的小数尾数。"""
    if amount <= 0 or tax_amount < 0 or tax_amount > amount * 0.25:
        return total_amount, amount, tax_amount, False

    calculated_total = round(amount + tax_amount, 2)
    if calculated_total <= 0 or calculated_total > get_money_upper_bound(category):
        return total_amount, amount, tax_amount, False

    if not approximately_equal(total_amount, calculated_total):
        return calculated_total, amount, tax_amount, True
    return total_amount, amount, tax_amount, False


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


def extract_ride_hailing_invoice_line_amounts(text: str) -> tuple[float, float, str] | None:
    """从网约车电子发票项目行提取不含税金额和税额。

    部分电子发票 OCR 会将底部“价税合计（小写）”标签拆散，导致常规总额
    规则无法命中。项目行通常仍保留“客运服务费 22.00 3% 0.66”的结构，
    可据此可靠重建价税合计。发生优惠抵扣时，一张票会有正、负两条客运
    服务项目，必须逐条汇总，不能只取首条项目金额。
    """
    item_pattern = re.compile(
        r"(?:交通运输服务|客运服务费|客运服务|网约车服务|出租汽车客运服务)(?P<detail>[\s\S]{0,240}?)(?=(?:交通运输服务|客运服务费|客运服务|网约车服务|出租汽车客运服务)|合\s*计|价\s*税\s*合\s*计|$)",
        re.IGNORECASE,
    )
    upper_bound = get_money_upper_bound("网约车")
    money_pattern = re.compile(r"(?<![\d.])-?\d+\s*\.\s*\d{1,2}(?![\d.])")
    line_amounts: list[float] = []
    line_tax_amounts: list[float] = []

    for item_match in item_pattern.finditer(text):
        item_text = item_match.group("detail")
        tax_rate_match = re.search(r"\d+(?:\s*\.\s*\d+)?\s*%", item_text)
        if not tax_rate_match:
            continue

        amount_values = [
            parse_numeric_value(match.group(0))
            for match in money_pattern.finditer(item_text[:tax_rate_match.start()])
        ]
        tax_values = [
            parse_numeric_value(match.group(0))
            for match in money_pattern.finditer(item_text[tax_rate_match.end():])
        ]
        if not amount_values or not tax_values:
            continue

        line_amount = amount_values[-1]
        line_tax_amount = tax_values[0]
        if abs(line_amount) <= upper_bound and abs(line_tax_amount) <= upper_bound:
            line_amounts.append(line_amount)
            line_tax_amounts.append(line_tax_amount)

    if not line_amounts:
        return None

    return round(sum(line_amounts), 2), round(sum(line_tax_amounts), 2), "网约车项目行金额税额汇总"


def extract_ride_itinerary_amounts(text: str) -> tuple[float, float, float, str] | None:
    patterns = [
        (
            "网约车行程单合计",
            re.compile(r"(?:共计|合计)\s*(?:\d+)\s*单行程[^0-9]{0,16}([0-9]+(?:\s*\.\s*[0-9]{1,2})?)\s*元"),
        ),
        (
            "高德行程单合计",
            re.compile(r"共计\s*\d+\s*单行程[，,、；;：:\s]*(?:合计|总计)?\s*([0-9]+(?:\s*\.\s*[0-9]{1,2})?)\s*元", re.IGNORECASE),
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


def extract_toll_itinerary_amount(text: str) -> tuple[float, str]:
    """提取高速通行费行程单的总费用，用于与对应电子发票配对。"""
    cumulative_amount_match = re.search(
        r"累计金额\s*(?:\(元\)|（元）)?([\s\S]{0,240}?)(?=购方名称|$)",
        text,
        re.IGNORECASE,
    )
    if cumulative_amount_match:
        upper_bound = get_money_upper_bound("高速通行费行程单")
        amount_candidates = [
            parse_numeric_value(candidate)
            for candidate in re.findall(r"\d+(?:\s*\.\s*\d{1,2})?", cumulative_amount_match.group(1))
        ]
        valid_amounts = [amount for amount in amount_candidates if 0 < amount <= upper_bound]
        if valid_amounts:
            return valid_amounts[0], "通行费行程单累计金额"

    patterns = [
        (
            "通行费行程单金额",
            re.compile(r"(?:通行费(?:金额|合计)?|费用(?:合计|金额)?|应收金额|实收金额|支付金额|合计)\s*[:：]?\s*[¥￥]?\s*([0-9]+(?:\s*\.\s*[0-9]{1,2})?)"),
        ),
        (
            "通行费行程单货币金额",
            re.compile(r"[¥￥]\s*([0-9]+(?:\s*\.\s*[0-9]{1,2})?)"),
        ),
    ]
    return extract_numeric_field(text, patterns)


def normalize_date_value(value: str) -> str:
    compact_match = re.fullmatch(r"(20\d{2})(\d{2})(\d{2})", value.strip())
    if compact_match:
        year, month, day = (int(part) for part in compact_match.groups())
        if 1 <= month <= 12 and 1 <= day <= 31:
            return f"{year:04d}-{month:02d}-{day:02d}"
    date_parts = re.findall(r"\d+", value)
    if len(date_parts) < 3:
        return ""
    year, month, day = date_parts[:3]
    return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"


def extract_ride_itinerary_trip_date(text: str) -> tuple[str, str]:
    patterns = [
        (
            "行程时间日期",
            re.compile(r"(?:行程时间|行程日期|行程起止日期|乘车时间|用车时间|上车时间|出发时间)\s*[:：]?\s*(20\d{2}[-/.年]\d{1,2}[-/.月]\d{1,2}日?)"),
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


def extract_ride_trip_times(text: str) -> tuple[str, str]:
    """提取行程单表格中的最早、最晚用车时间。"""
    time_values = re.findall(
        r"(?<!\d)(?:20\d{2}[-/.年])?\d{1,2}[-/.月]\d{1,2}日?\s*(\d{1,2}:\d{2})(?::\d{2})?",
        text,
    )
    if time_values:
        valid_times = [
            value
            for value in time_values
            if int(value.split(":")[0]) < 24 and int(value.split(":")[1]) < 60
        ]
        if valid_times:
            return min(valid_times), max(valid_times)

    start_match = re.search(r"(?:上车时间|出发时间|开始时间)\s*[:：]?\s*(\d{1,2}:\d{2})", text)
    end_match = re.search(r"(?:下车时间|到达时间|结束时间)\s*[:：]?\s*(\d{1,2}:\d{2})", text)
    if start_match and end_match:
        return start_match.group(1), end_match.group(1)
    return "", ""


def derive_invoice_category(text: str, attachment_name: str, vendor: str) -> str:
    # 高德行程单在配对重命名后也会使用对应的 20 位发票号码，因此必须先看
    # 票面标题；“高德地图—打车—行程单 / AMAP ITINERARY”是行程单强特征。
    if re.search(r"(?:高德地图.{0,12}打车.{0,12}行程单|AMAP\s+ITINERARY)", text, re.IGNORECASE):
        return "网约车行程单"

    # 部分打车平台会把电子发票附件命名为“发票号码-金额-行程单.pdf”。
    # 票面明确是电子发票且包含客运服务项目时，应以票面内容为准，不能被
    # 文件名中的“行程单”误判，否则两份文件都会成为行程单而无法配对。
    # OCR 偶尔会漏掉标题时，16/20 位电子发票号码也能明确区分该类附件；
    # 真正的高德行程单不包含电子发票号码。
    if re.search(r"(?<!\d)(?:\d{16}|\d{20})[-_]\d+(?:\.\d{1,2})?(?:[-_])?行程单", attachment_name):
        return "网约车"

    if re.search(r"(?:电子发票|全电发票|数电发票)", text, re.IGNORECASE) and re.search(
        r"(?:交通运输服务|客运服务费|客运服务|网约车服务|出租汽车客运服务)",
        text,
        re.IGNORECASE,
    ):
        return "网约车"

    corpus = f"{text} {attachment_name} {vendor}"
    rules: list[tuple[re.Pattern[str], str]] = [
        (
            re.compile(
                r"(?:通行费|高速|收费公路|etc|过路费|车辆通行服务|通行服务).{0,100}汇总单|汇总单.{0,100}(?:通行费|高速|收费公路|etc|过路费|车辆通行服务|通行服务)",
                re.IGNORECASE,
            ),
            "高速通行费行程单",
        ),
        (
            re.compile(
                r"(?:通行费|高速|收费公路|etc|过路费|车辆通行服务|通行服务).{0,100}行程单|行程单.{0,100}(?:通行费|高速|收费公路|etc|过路费|车辆通行服务|通行服务)",
                re.IGNORECASE,
            ),
            "高速通行费行程单",
        ),
        (re.compile(r"(行程单|AMAP\s+ITINERARY|高德地图.*打车|滴滴.*行程单)", re.IGNORECASE), "网约车行程单"),
        (re.compile(r"(火车票|铁路电子客票|铁路车票|电子客票|高铁|动车|铁路|国内旅客运输服务|12306|95306|\b[gdcztk]\d{1,4}\b|一等座|二等座|商务座)", re.IGNORECASE), "火车票"),
        (re.compile(r"(网约车|滴滴|出行服务|出租汽车|出租车|打车|客运服务|代驾|出行人|出发地|到达地|交通工具类型|行程起点|行程终点|里程费|时长费)", re.IGNORECASE), "网约车"),
        (re.compile(r"(住宿|酒店|宾馆|旅店|客房|房费|住宿服务)", re.IGNORECASE), "住宿票"),
        (re.compile(r"(通行费|高速|收费公路|etc|过路费|车辆通行服务|通行服务|通行日期起|经营租赁\*?通行费)", re.IGNORECASE), "高速通行票"),
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


def extract_buyer_tax_id(text: str) -> str:
    """提取购买方统一社会信用代码或纳税人识别号，避免误取销售方税号。"""
    full_compact_text = re.sub(r"\s+", "", text).upper()
    # 目标购方税号直接命中即可确认；不依赖 PDF 文本层是否保留“购买方信息”字段标签。
    if EXPECTED_BUYER_TAX_ID in full_compact_text:
        return EXPECTED_BUYER_TAX_ID

    buyer_section = re.search(
        r"购\s*买\s*方(?:\s*信\s*息)?\s*([\s\S]{0,800}?)(?=销\s*售\s*方(?:\s*信\s*息)?|项目名称|货物或应税劳务|$)",
        text,
        re.IGNORECASE,
    )
    candidate_text = buyer_section.group(1) if buyer_section else text
    compact_candidate = re.sub(r"\s+", "", candidate_text).upper()
    field_pattern = re.compile(
        r"(?:统一社会信用代码|纳税人识别号|税号)(?:/|／|、|及|或)*(?:统一社会信用代码|纳税人识别号|税号)?[:：]?([0-9A-Z]{15,20})"
    )
    match = field_pattern.search(compact_candidate)
    if match:
        return match.group(1)

    # 部分 PDF 文本层会把字段标签集中排在前方、税号值排在公司名称之后；
    # 仅在购买方区块内回退提取，避免误取销售方税号。
    trailing_letter_match = re.search(r"(?<![0-9A-Z])([0-9]{14,19}[A-Z])", compact_candidate)
    if trailing_letter_match:
        return trailing_letter_match.group(1)

    fallback_match = re.search(r"(?<![0-9A-Z])([0-9A-Z]{15,20})(?![0-9A-Z])", compact_candidate)
    return fallback_match.group(1) if fallback_match else ""


def derive_lodging_invoice_type(text: str, category: str) -> str:
    if category != "住宿票":
        return ""
    if re.search(r"(?:增值税)?\s*专\s*用\s*发\s*票|专\s*票", text, re.IGNORECASE):
        return "专票"
    if re.search(r"(?:增值税)?\s*(?:电子)?\s*普\s*通\s*发\s*票|普\s*票", text, re.IGNORECASE):
        return "普票"
    return "待核验"


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


def extract_invoice_number(text: str) -> tuple[str, str]:
    """提取发票号码，且绝不把发票代码当作发票号码。"""
    # 江苏省车辆通行费电子发票等传统电子票同时显示“发票代码（12 位）”和
    # “发票号码（8 位）”。PDF 文本层有时将两个标签排在前面、数值排在后面，
    # 甚至颠倒字段与数值的读取顺序；此时不能相信单个字段的邻近关系。
    # 若票面同时包含两个标签，8 位的非日期数字即为该版式的发票号码。
    if re.search(r"发\s*票\s*代\s*码", text) and re.search(r"发\s*票\s*(?:号\s*码|号|号码|票号)", text):
        conventional_numbers = [
            candidate
            for candidate in re.findall(r"(?<!\d)(\d{8})(?!\d)", text)
            if not re.fullmatch(r"20\d{6}", candidate)
        ]
        if conventional_numbers:
            return conventional_numbers[0], "代码号码同屏8位发票号码"

    patterns = [
        (
            "发票号码字段",
            re.compile(r"发\s*票\s*(?:号\s*码|号|号码|票号)\s*[:：]?\s*([0-9]{8,20})", re.IGNORECASE),
        ),
        (
            "票据号码字段",
            re.compile(r"票\s*据\s*(?:号\s*码|号)\s*[:：]?\s*([0-9]{8,20})", re.IGNORECASE),
        ),
    ]
    # 部分电子发票的 PDF 文本层会按绘制顺序输出：先出现“发票号码：”标签，
    # 再在文末单独输出其数值，导致标签与号码无法相邻匹配。新版电子发票号码
    # 通常为 16 或 20 位；发票代码通常为 10～12 位，故只允许该长度回退，
    # 同时排除统一社会信用代码常见的 18 位，避免误命中购销方税号。
    electronic_invoice_numbers = re.findall(r"(?<!\d)(?:\d{16}|\d{20})(?!\d)", text)
    # 高速通行费电子发票的发票代码常为 12 位、发票号码为 20 位。PDF/OCR
    # 偶尔会把“代码”标签错读为“号码”，因此电子票优先使用 16/20 位候选。
    if electronic_invoice_numbers and re.search(r"(?:电子发票|全电发票|数电发票|通行费|高速|收费公路)", text, re.IGNORECASE):
        return electronic_invoice_numbers[0], "电子发票号码长度优先"

    for label, pattern in patterns:
        match = pattern.search(text)
        if match:
            return match.group(1), label

    if electronic_invoice_numbers:
        return electronic_invoice_numbers[0], "电子发票号码长度回退"

    return "", "未命中"


def extract_tax_inclusive_total(text: str) -> tuple[float, str]:
    """定向提取票面“价税合计（小写）”的含税金额。

    电子发票的 PDF 文本层经常按坐标而非视觉顺序输出，通用金额规则在
    “价税合计”附近跨越到项目明细时，可能误取数量 1 或某项金额。此处只
    接受该标签后紧邻的人民币金额，作为网约车发票的最高优先级总额来源。
    """
    label_pattern = r"价\s*税\s*合\s*计\s*(?:[（(]\s*小\s*写\s*[）)])?"
    money_pattern = r"([0-9][0-9,\s]*(?:\s*\.\s*[0-9]{1,2})?)"
    patterns = [
        (
            "价税合计小写人民币金额",
            re.compile(rf"{label_pattern}\s*[:：]?\s*[¥￥]\s*{money_pattern}"),
        ),
        (
            "价税合计小写邻近人民币金额",
            re.compile(rf"{label_pattern}[^¥￥0-9]{{0,48}}[¥￥]\s*{money_pattern}"),
        ),
        (
            "价税合计小写邻近小数金额",
            re.compile(rf"{label_pattern}[^0-9]{{0,48}}([0-9]+\s*\.\s*[0-9]{{1,2}})"),
        ),
        (
            "价税合计小写前置人民币金额",
            re.compile(rf"[¥￥]\s*{money_pattern}[^¥￥0-9]{{0,48}}{label_pattern}"),
        ),
    ]
    return extract_numeric_field(text, patterns)


def extract_invoice_tax_rate(text: str) -> float:
    """提取发票项目行的税率，用于项目金额文字层缺失时反算税额。"""
    item_match = re.search(
        r"(?:交通运输服务|客运服务费|客运服务|网约车服务|出租汽车客运服务)[\s\S]{0,240}?(\d+(?:\s*\.\s*\d+)?)\s*%",
        text,
        re.IGNORECASE,
    )
    if not item_match:
        return 0.0
    tax_rate = parse_numeric_value(item_match.group(1)) / 100
    return tax_rate if 0 < tax_rate <= 0.2 else 0.0


def recognize_invoice_text(text: str, source_file: str) -> InvoiceRecognitionResult:
    compact_text = normalize_text(text)
    date_match = re.search(r"(20\d{2}[-/.年]\d{1,2}[-/.月]\d{1,2}日?)", compact_text)
    fallback_year = int(re.search(r"20\d{2}", date_match.group(1)).group()) if date_match else None
    lodging_line_amounts = extract_lodging_line_amounts(compact_text)
    ride_hailing_invoice_line_amounts = extract_ride_hailing_invoice_line_amounts(compact_text)
    toll_line_amounts = extract_toll_line_amounts(compact_text)
    toll_itinerary_amount, toll_itinerary_amount_rule = extract_toll_itinerary_amount(compact_text)
    ride_itinerary_amounts = extract_ride_itinerary_amounts(compact_text)
    ride_itinerary_trip_date, ride_itinerary_trip_date_rule = extract_ride_itinerary_trip_date(compact_text)
    ride_start_time, ride_end_time = extract_ride_trip_times(compact_text)
    train_ticket_trip_date, train_ticket_trip_date_rule = extract_train_ticket_trip_date(compact_text)
    lodging_start_date, lodging_start_date_rule = extract_lodging_start_date(compact_text, fallback_year)
    lodging_stay_days = extract_lodging_stay_days(compact_text)
    toll_trip_date, toll_trip_date_rule = extract_toll_trip_date(compact_text)

    resolved_number, number_rule = extract_invoice_number(compact_text)

    total_amount, total_rule = extract_numeric_field(
        compact_text,
        [
            ("票价直接命中", re.compile(rf"票价\s*[:：]?\s*[¥￥]?\s*{MONEY_PATTERN}")),
            ("票价邻近货币符号", re.compile(rf"票价[^0-9¥￥]{{0,12}}[¥￥]\s*{MONEY_PATTERN}")),
            (
                "价税合计小写金额",
                re.compile(
                    rf"价\s*税\s*合\s*计[\s\S]{{0,96}}?(?:\(\s*小\s*写\s*\)|（\s*小\s*写\s*）|小\s*写)[^0-9¥￥]{{0,16}}[¥￥]?\s*{MONEY_PATTERN}"
                ),
            ),
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
    tax_inclusive_total, tax_inclusive_total_rule = extract_tax_inclusive_total(compact_text)
    if tax_inclusive_total > 0:
        total_amount = tax_inclusive_total
        total_rule = tax_inclusive_total_rule
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
        amount = lodging_line_amounts[0]
        tax_amount = lodging_line_amounts[1]
        amount_rule = lodging_line_amounts[2]
        tax_rule = lodging_line_amounts[2]

    vendor = extract_vendor_name(compact_text, source_file)
    category = derive_invoice_category(compact_text, source_file, vendor)
    buyer_tax_id = extract_buyer_tax_id(compact_text)
    lodging_invoice_type = derive_lodging_invoice_type(compact_text, category)

    # 一张网约车电子发票中，带“￥/¥”的金额通常包括不含税金额、税额及
    # 价税合计；其中最大值必然是价税合计。PDF 坐标乱序导致“价税合计”
    # 标签与金额无法相邻时，以该规则作为可靠兜底。
    currency_total_candidates = [
        candidate
        for candidate in extract_currency_candidates(compact_text)
        if sanitize_money_value(candidate, category) > 0
    ]
    if category == "网约车" and currency_total_candidates:
        maximum_currency_amount = currency_total_candidates[0]
        if total_amount <= 0 or maximum_currency_amount > total_amount:
            total_amount = maximum_currency_amount
            total_rule = "网约车人民币金额最大值（价税合计候选）"

    if toll_line_amounts and category == "高速通行票":
        amount = toll_line_amounts[0]
        tax_amount = toll_line_amounts[1]
        total_amount = round(amount + tax_amount, 2)
        amount_rule = toll_line_amounts[2]
        tax_rule = toll_line_amounts[2]
        total_rule = "高速通行费金额加税额推导"

    if ride_hailing_invoice_line_amounts and category == "网约车":
        amount = ride_hailing_invoice_line_amounts[0]
        tax_amount = ride_hailing_invoice_line_amounts[1]
        amount_rule = ride_hailing_invoice_line_amounts[2]
        tax_rule = ride_hailing_invoice_line_amounts[2]
        # 票面“价税合计”是法定含税总额，优先级高于项目行累加结果。项目
        # 行可能包含优惠抵扣、折行或 OCR 漏读，不能反向覆盖价税合计。
        has_explicit_invoice_total = total_rule.startswith("价税合计")
        if tax_amount > 0 and not has_explicit_invoice_total:
            total_amount = round(amount + tax_amount, 2)
            total_rule = "网约车金额加税额推导"
        elif not total_amount:
            total_amount = amount
            total_rule = "网约车项目行金额"

    if category == "网约车" and total_amount > 0 and amount <= 0:
        tax_rate = extract_invoice_tax_rate(compact_text)
        if tax_rate:
            amount = round(total_amount / (1 + tax_rate), 2)
            tax_amount = round(total_amount - amount, 2)
            amount_rule = "价税合计按税率反算金额"
            tax_rule = "价税合计按税率反算税额"

    if ride_itinerary_amounts and category == "网约车行程单":
        # 行程单“共计…单行程，合计 xx.xx 元”是实际支付总额。PDF 文本层
        # 可能从文件名或明细表头先读到旧金额，不能让这些候选值覆盖合计。
        total_amount = ride_itinerary_amounts[0]
        amount = ride_itinerary_amounts[1]
        tax_amount = ride_itinerary_amounts[2]
        total_rule = ride_itinerary_amounts[3]
        amount_rule = ride_itinerary_amounts[3]
        tax_rule = ride_itinerary_amounts[3]

    if category == "高速通行费行程单" and toll_itinerary_amount > 0:
        total_amount = toll_itinerary_amount
        amount = toll_itinerary_amount
        tax_amount = 0.0
        total_rule = toll_itinerary_amount_rule
        amount_rule = toll_itinerary_amount_rule

    total_amount = sanitize_money_value(total_amount, category)
    tax_amount = sanitize_money_value(tax_amount, category)
    amount = sanitize_money_value(amount, category)
    missing_ride_tax_with_total = (
        category == "网约车" and tax_amount == 0 and amount > 0 and total_amount > amount
    )
    # “价税合计”通常最可靠，但 PDF 坐标乱序时也可能误取数量 1.00。
    # 若其小于已识别的项目金额加税额，则该值不可能是含税总额，恢复一致性
    # 校验以避免将 1.00 作为二十多元网约车发票的总额。
    has_explicit_ride_hailing_total = (
        category == "网约车"
        and total_rule.startswith("价税合计")
        and (amount <= 0 or tax_amount < 0 or approximately_equal(total_amount, round(amount + tax_amount, 2)))
    )
    if missing_ride_tax_with_total or has_explicit_ride_hailing_total:
        total_corrected = False
    else:
        total_amount, amount, tax_amount, total_corrected = reconcile_amounts(total_amount, amount, tax_amount, category)
    if total_corrected:
        total_rule = "金额加税额一致性校正"
    currency_candidates = [
        candidate
        for candidate in extract_currency_candidates(compact_text)
        if sanitize_money_value(candidate, category) > 0
    ]

    train_fare, train_fare_rule = extract_train_ticket_fare(compact_text) if category == "火车票" else (0.0, "未命中")
    train_fare = sanitize_money_value(train_fare, category)

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
    elif category in {"高速通行票", "高速通行费行程单"} and toll_trip_date:
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
        buyer_tax_id=buyer_tax_id,
        lodging_invoice_type=lodging_invoice_type,
        ride_start_time=ride_start_time if category == "网约车行程单" else "",
        ride_end_time=ride_end_time if category == "网约车行程单" else "",
        text_length=len(compact_text),
        notes=compact_text[:180],
        matched_rules={
            "total_amount": total_rule,
            "amount": amount_rule,
            "tax_amount": tax_rule,
            "number": number_rule,
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
                if category in {"高速通行票", "高速通行费行程单"} and toll_trip_date
                else "开票日期"
            ),
        },
    )
