from __future__ import annotations

from datetime import date, timedelta
from email import message_from_bytes
from email.header import decode_header
from pathlib import Path
import imaplib
import re
import shutil
from typing import Optional
import zipfile

from python_recognizer.extractors import extract_text
from python_recognizer.heuristics import recognize_invoice_text
from python_recognizer.pairing import pair_ride_hailing_documents
from python_recognizer.workflow import build_rename_target


INVOICE_KEYWORDS = ("发票", "invoice", "票根", "12306", "滴滴", "高德", "出行", "酒店", "通行")
EXCLUDED_DOCUMENT_KEYWORDS = ("结账单", "结算单", "消费明细", "费用明细", "订单明细", "付款凭证", "支付凭证")
INVOICE_CATEGORIES = {"网约车", "网约车行程单", "火车票", "高速通行票", "高速通行费行程单", "住宿票", "机票"}


def _decode_header_value(value: Optional[str]) -> str:
    if not value:
        return ""
    parts: list[str] = []
    for fragment, encoding in decode_header(value):
        if isinstance(fragment, bytes):
            parts.append(fragment.decode(encoding or "utf-8", errors="replace"))
        else:
            parts.append(fragment)
    return "".join(parts)


def _safe_filename(value: str) -> str:
    value = re.sub(r'[<>:"/\\|?*]+', "_", value).strip(" .")
    return value or "未命名附件.pdf"


def _is_invoice_message(message) -> bool:
    searchable = " ".join(
        [
            _decode_header_value(message.get("Subject")),
            _decode_header_value(message.get("From")),
        ]
    ).casefold()
    return any(keyword.casefold() in searchable for keyword in INVOICE_KEYWORDS)


def _write_pdf(destination: Path, uid: str, original_name: str, payload: bytes, copied_names: set[str]) -> int:
    file_name = _safe_filename(original_name)
    if not file_name.lower().endswith(".pdf"):
        file_name = f"{file_name}.pdf"
    target_name = f"{uid}_{file_name}"
    target = destination / target_name
    index = 2
    while target.name.casefold() in copied_names or target.exists():
        target = destination / f"{uid}_{Path(file_name).stem}_{index}.pdf"
        index += 1
    target.write_bytes(payload)
    copied_names.add(target.name.casefold())
    return 1


def _is_excluded_document(file_name: str, text: str) -> bool:
    searchable = f"{file_name} {text[:1200]}".casefold()
    return any(keyword.casefold() in searchable for keyword in EXCLUDED_DOCUMENT_KEYWORDS)


def _unique_target_path(target_path: Path) -> Path:
    if not target_path.exists():
        return target_path
    index = 2
    while True:
        candidate = target_path.with_name(f"{target_path.stem}_{index}{target_path.suffix}")
        if not candidate.exists():
            return candidate
        index += 1


def _mail_uid_from_file_name(file_name: str) -> str:
    """提取下载阶段加入的邮件 UID；同一封邮件附件优先相互配对。"""
    match = re.match(r"(\d+)_", file_name)
    return match.group(1) if match else ""


def _match_toll_itineraries(recognized_files: dict[str, tuple[Path, object]]) -> dict[str, tuple[str, float]]:
    """为高速通行费行程单查找对应发票，避免将其误命名为网约车行程单。"""
    invoices = [
        (source_file, result)
        for source_file, (_, result) in recognized_files.items()
        if result.category == "高速通行票" and result.number
    ]
    matches: dict[str, tuple[str, float]] = {}

    for source_file, (_, itinerary) in recognized_files.items():
        if itinerary.category != "高速通行费行程单":
            continue

        candidates = [(invoice_file, invoice) for invoice_file, invoice in invoices if itinerary.number and invoice.number == itinerary.number]
        if not candidates:
            source_uid = _mail_uid_from_file_name(source_file)
            candidates = [
                (invoice_file, invoice)
                for invoice_file, invoice in invoices
                if source_uid and _mail_uid_from_file_name(invoice_file) == source_uid
            ]
        if not candidates and itinerary.total_amount > 0:
            candidates = [
                (invoice_file, invoice)
                for invoice_file, invoice in invoices
                if abs(invoice.total_amount - itinerary.total_amount) < 0.01
            ]

        if len(candidates) == 1:
            _, invoice = candidates[0]
            matches[source_file] = (invoice.number, invoice.total_amount)

    return matches


def _filter_and_rename_downloads(output_directory: Path) -> int:
    """只保留发票/行程单 PDF，并按现有发票管理系统规则重命名。"""
    recognized_files: dict[str, tuple[Path, object]] = {}

    # 先完整识别所有附件，不能边识别边改名；网约车行程单需要在下一步使用
    # 对应发票的号码命名，规则与“分析汇总”完全一致。
    for file_path in list(output_directory.glob("*.pdf")):
        try:
            text, _, _ = extract_text(file_path, enable_ocr=True)
            result = recognize_invoice_text(text, str(file_path))
        except Exception:
            file_path.unlink(missing_ok=True)
            continue

        if _is_excluded_document(file_path.name, text) or result.category not in INVOICE_CATEGORIES:
            file_path.unlink(missing_ok=True)
            continue
        recognized_files[file_path.name] = (file_path, result)

    # 复用分析汇总相同的配对器：按行程编号优先，其次金额配对。
    paired_invoice_numbers: dict[str, str] = {}
    for pair in pair_ride_hailing_documents(output_directory, enable_ocr=True):
        invoice_item = recognized_files.get(pair.invoice_file)
        if invoice_item is not None and invoice_item[1].number:
            paired_invoice_numbers[pair.itinerary_file] = invoice_item[1].number

    toll_itinerary_matches = _match_toll_itineraries(recognized_files)

    retained_count = 0
    for source_file, (file_path, result) in recognized_files.items():
        toll_number, toll_amount = toll_itinerary_matches.get(source_file, ("", 0.0))
        number = paired_invoice_numbers.get(source_file, toll_number or result.number)
        total_amount = toll_amount if toll_number and toll_amount > 0 else result.total_amount

        target_relative_path = build_rename_target(
            file_path.name,
            result.category,
            number,
            total_amount,
            result.vendor,
            result.issue_date,
            ".",
        )
        target_path = _unique_target_path(output_directory / Path(target_relative_path).name)
        if file_path != target_path:
            file_path.rename(target_path)
        retained_count += 1
    return retained_count


def fetch_qq_invoice_attachments(
    *,
    account: str,
    authorization_code: str,
    start_date: date,
    end_date: date,
) -> tuple[Path, int]:
    """按收件日期（闭区间）抓取 QQ 邮箱中的 PDF 发票附件。"""
    if start_date > end_date:
        raise ValueError("起始日期不能晚于结束日期。")
    if not account or not authorization_code:
        raise ValueError("请填写 QQ 邮箱账号和 IMAP 授权码。")

    output_directory = Path.home() / "Desktop" / f"发票{start_date:%Y-%m-%d}至{end_date:%Y-%m-%d}"
    if output_directory.exists():
        shutil.rmtree(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)

    since_value = start_date.strftime("%d-%b-%Y")
    before_value = (end_date + timedelta(days=1)).strftime("%d-%b-%Y")
    copied_count = 0
    copied_names: set[str] = set()

    client = imaplib.IMAP4_SSL("imap.qq.com", 993)
    try:
        # QQ 邮箱 IMAP 使用授权码登录，授权码不会写入日志或输出文件。
        client.login(account, authorization_code)
        client.select("INBOX", readonly=True)
        status, data = client.uid("SEARCH", None, "SINCE", since_value, "BEFORE", before_value)
        if status != "OK":
            raise RuntimeError("无法查询指定日期范围内的邮件。")

        for uid_bytes in data[0].split():
            uid = uid_bytes.decode("ascii", errors="ignore")
            status, message_data = client.uid("FETCH", uid, "(RFC822)")
            if status != "OK" or not message_data:
                continue
            raw_message = next((item[1] for item in message_data if isinstance(item, tuple) and len(item) > 1), None)
            if not raw_message:
                continue
            message = message_from_bytes(raw_message)
            for part in message.walk():
                if part.is_multipart():
                    continue
                file_name = _decode_header_value(part.get_filename())
                if not file_name:
                    continue
                payload = part.get_payload(decode=True)
                if not payload:
                    continue
                suffix = Path(file_name).suffix.lower()
                if suffix == ".pdf":
                    copied_count += _write_pdf(output_directory, uid, file_name, payload, copied_names)
                elif suffix == ".zip":
                    try:
                        archive_path = output_directory / f"{uid}_{_safe_filename(file_name)}"
                        archive_path.write_bytes(payload)
                        with zipfile.ZipFile(archive_path) as archive:
                            for entry in archive.infolist():
                                if entry.is_dir() or not entry.filename.lower().endswith(".pdf"):
                                    continue
                                copied_count += _write_pdf(output_directory, uid, Path(entry.filename).name, archive.read(entry), copied_names)
                    except zipfile.BadZipFile:
                        continue
                    finally:
                        if 'archive_path' in locals() and archive_path.exists():
                            archive_path.unlink()
    finally:
        try:
            client.logout()
        except Exception:
            pass

    retained_count = _filter_and_rename_downloads(output_directory)
    return output_directory, retained_count
