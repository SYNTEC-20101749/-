from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class InvoiceRecognitionResult:
    source_file: str
    text_source: str
    ocr_used: bool
    number: str
    vendor: str
    amount: float
    tax_amount: float
    total_amount: float
    issue_date: str
    category: str
    text_length: int
    notes: str
    matched_rules: dict[str, str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class RideHailingPairCandidate:
    source_file: str
    category: str
    vendor: str
    issue_date: str
    total_amount: float
    file_stem: str
    pair_id: str
    doc_type: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class RideHailingPairResult:
    match_key: str
    confidence: str
    amount: float
    invoice_file: str
    itinerary_file: str
    invoice_vendor: str
    itinerary_vendor: str
    issue_date: str
    notes: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class InvoiceOrganizeRecord:
    source_file: str
    source_path: str
    category: str
    number: str
    vendor: str
    issue_date: str
    amount: float
    tax_amount: float
    total_amount: float
    text_source: str
    ocr_used: bool
    rename_target: str
    print_copies: int
    printed: bool
    pair_key: str
    pair_status: str
    review_status: str
    warnings: list[str]
    hints: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class InvoiceDateSummary:
    issue_date: str
    transport_total: float
    toll_total: float
    lodging_amount_total: float
    lodging_tax_total: float
    lodging_total: float
    total: float

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class InvoiceOrganizeSummary:
    total_files: int
    recognized_files: int
    review_required: int
    transport_total: float
    toll_total: float
    lodging_amount_total: float
    lodging_tax_total: float
    lodging_total: float

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["daily_breakdown"] = [item.to_dict() for item in self.daily_breakdown]
        return payload

    daily_breakdown: list[InvoiceDateSummary]


@dataclass
class InvoiceOrganizeResult:
    source_directory: str
    output_directory: str
    applied: bool
    summary_sheet_pdf: str
    summary: InvoiceOrganizeSummary
    ride_hailing_pairs: list[RideHailingPairResult]
    records: list[InvoiceOrganizeRecord]

    def to_dict(self) -> dict[str, object]:
        return {
            "source_directory": self.source_directory,
            "output_directory": self.output_directory,
            "applied": self.applied,
            "summary_sheet_pdf": self.summary_sheet_pdf,
            "summary": self.summary.to_dict(),
            "ride_hailing_pairs": [pair.to_dict() for pair in self.ride_hailing_pairs],
            "records": [record.to_dict() for record in self.records],
        }
