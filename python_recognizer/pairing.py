from __future__ import annotations

import re
from pathlib import Path

from .extractors import extract_text
from .heuristics import recognize_invoice_text
from .types import RideHailingPairCandidate, RideHailingPairResult


FILENAME_PAIR_PATTERN = re.compile(
    r"(?P<pair_id>\d{12,24})[-_](?P<amount>\d+(?:\.\d{1,2})?)(?P<doc_type>发票|行程单)",
    re.IGNORECASE,
)
RIDE_HAILING_FILENAME_PATTERN = re.compile(
    r"[【\[]?(?P<pair_id>[^】\]\-]+)-(?P<amount>\d+(?:\.\d{1,2})?)元-\d+个行程[】\]]?.*?(?P<doc_type>发票|行程单)",
    re.IGNORECASE,
)


def infer_doc_type(file_name: str, category: str) -> str:
    if "行程单" in file_name or category == "网约车行程单":
        return "itinerary"
    if "发票" in file_name or category == "网约车":
        return "invoice"
    return "unknown"


def extract_filename_pair_info(file_name: str) -> tuple[str, float | None, str]:
    match = FILENAME_PAIR_PATTERN.search(file_name) or RIDE_HAILING_FILENAME_PATTERN.search(file_name)
    if not match:
        return "", None, "unknown"

    pair_id = match.group("pair_id")
    amount = float(match.group("amount"))
    doc_type = "invoice" if match.group("doc_type") == "发票" else "itinerary"
    return pair_id, amount, doc_type


def build_ride_hailing_candidate(file_path: Path, *, enable_ocr: bool = False) -> RideHailingPairCandidate | None:
    text, _, _ = extract_text(file_path, enable_ocr=enable_ocr)
    result = recognize_invoice_text(text, str(file_path))

    if result.category not in {"网约车", "网约车行程单"}:
        return None

    pair_id, filename_amount, filename_doc_type = extract_filename_pair_info(file_path.name)
    doc_type = filename_doc_type if filename_doc_type != "unknown" else infer_doc_type(file_path.name, result.category)
    total_amount = filename_amount or result.total_amount or result.amount or 0.0

    return RideHailingPairCandidate(
        source_file=file_path.name,
        category=result.category,
        vendor=result.vendor,
        issue_date=result.issue_date,
        total_amount=total_amount,
        file_stem=file_path.stem,
        pair_id=pair_id,
        doc_type=doc_type,
    )


def confidence_from_pair(invoice: RideHailingPairCandidate, itinerary: RideHailingPairCandidate) -> tuple[str, str]:
    checks: list[str] = []

    if invoice.pair_id and itinerary.pair_id and invoice.pair_id == itinerary.pair_id:
        checks.append("文件名编号一致")
    if abs(invoice.total_amount - itinerary.total_amount) < 0.01:
        checks.append("金额一致")
    if invoice.issue_date and itinerary.issue_date and invoice.issue_date == itinerary.issue_date:
        checks.append("日期一致")
    if invoice.vendor and itinerary.vendor and invoice.vendor == itinerary.vendor:
        checks.append("平台一致")

    if "文件名编号一致" in checks and "金额一致" in checks:
        return "high", "，".join(checks)
    if "金额一致" in checks:
        return "medium", "，".join(checks)
    return "low", "，".join(checks) if checks else "仅基于弱规则匹配"


def pair_ride_hailing_documents(directory: str | Path, *, enable_ocr: bool = False) -> list[RideHailingPairResult]:
    base_path = Path(directory)
    if not base_path.exists() or not base_path.is_dir():
        raise NotADirectoryError(f"目录不存在: {base_path}")

    candidates = [
        candidate
        for file_path in sorted(base_path.glob("*.pdf"))
        for candidate in [build_ride_hailing_candidate(file_path, enable_ocr=enable_ocr)]
        if candidate is not None
    ]

    invoices = [candidate for candidate in candidates if candidate.doc_type == "invoice"]
    itineraries = [candidate for candidate in candidates if candidate.doc_type == "itinerary"]
    results: list[RideHailingPairResult] = []
    used_itineraries: set[str] = set()

    for invoice in invoices:
        matched_itinerary: RideHailingPairCandidate | None = None

        if invoice.pair_id:
            pair_id_matches = [
                itinerary
                for itinerary in itineraries
                if itinerary.source_file not in used_itineraries and itinerary.pair_id == invoice.pair_id
            ]
            exact_matches = [
                itinerary
                for itinerary in pair_id_matches
                if abs(itinerary.total_amount - invoice.total_amount) < 0.01
            ]
            if len(exact_matches) == 1:
                matched_itinerary = exact_matches[0]
            elif len(pair_id_matches) == 1:
                matched_itinerary = pair_id_matches[0]

        if matched_itinerary is None:
            amount_matches = [
                itinerary
                for itinerary in itineraries
                if itinerary.source_file not in used_itineraries and abs(itinerary.total_amount - invoice.total_amount) < 0.01
            ]
            if len(amount_matches) == 1:
                matched_itinerary = amount_matches[0]

        if matched_itinerary is None:
            continue

        used_itineraries.add(matched_itinerary.source_file)
        confidence, notes = confidence_from_pair(invoice, matched_itinerary)
        results.append(
            RideHailingPairResult(
                match_key=invoice.pair_id or f"{invoice.total_amount:.2f}",
                confidence=confidence,
                amount=invoice.total_amount,
                invoice_file=invoice.source_file,
                itinerary_file=matched_itinerary.source_file,
                invoice_vendor=invoice.vendor,
                itinerary_vendor=matched_itinerary.vendor,
                issue_date=matched_itinerary.issue_date or invoice.issue_date,
                notes=notes,
            )
        )

    return results