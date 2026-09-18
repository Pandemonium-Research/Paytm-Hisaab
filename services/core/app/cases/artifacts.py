"""Write pack JSON/PDF artifacts under HISAAB_PACK_DIR."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from zoneinfo import ZoneInfo
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

def pack_dir() -> Path:
    return Path(os.getenv("HISAAB_PACK_DIR", "/runtime/packs"))


def pack_paths(pack_id: str) -> tuple[Path, Path, str, str]:
    root = pack_dir()
    json_path = root / f"{pack_id}.json"
    pdf_path = root / f"{pack_id}.pdf"
    return json_path, pdf_path, f"/api/packs/{pack_id}.json", f"/api/packs/{pack_id}.pdf"


def public_pdf_url(pack_id: str) -> str:
    return f"/api/packs/{pack_id}.pdf"


def _paragraph(text: str, style) -> Paragraph:
    return Paragraph(escape(str(text)), style)


def write_pdf(path: Path, sections: list[tuple[str, list[str]]]) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(delete=False, dir=path.parent, suffix=".part") as handle:
        temp = Path(handle.name)
    styles = getSampleStyleSheet()
    body = styles["BodyText"]
    heading = styles["Heading2"]
    story = [_paragraph("SYNTHETIC · SIMULATED · PROTOTYPE evidence packet", styles["Title"]), Spacer(1, 12)]
    for title, lines in sections:
        story.append(_paragraph(title, heading))
        for line in lines:
            story.append(_paragraph(line, body))
        story.append(Spacer(1, 8))
    doc = SimpleDocTemplate(str(temp), pagesize=A4, leftMargin=48, rightMargin=48, topMargin=48, bottomMargin=48)
    try:
        doc.build(story)
        data = temp.read_bytes()
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)
    return data


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", delete=False, dir=path.parent, suffix=".part", encoding="utf-8") as handle:
        temp = Path(handle.name)
    try:
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _badge_list(found_by: list[str]) -> str:
    if not found_by:
        return "none"
    return ", ".join(found_by)


def pack_pdf_sections(payload: dict, isolation, lien: dict, business_name: str) -> list[tuple[str, list[str]]]:
    """Readable evidence sections for the PDF export (not a raw dict dump)."""
    from ..schemas.api.skills import IsolateResponse

    if not isinstance(isolation, IsolateResponse):
        isolation = IsolateResponse.model_validate(isolation)

    authority = lien.get("authority") or {}
    authority_line = ", ".join(
        str(authority[key]) for key in ("unit", "city", "state") if authority.get(key)
    ) or "not recorded"

    identity = [
        f"Pack {payload['pack_id']}",
        f"Merchant {payload['merchant_id']} · {business_name}",
        f"Case {payload['case_id']}",
        f"Opened {payload['case_opened_at_ist']}",
        f"Built {payload['pack_built_at_ist']}",
        payload["stamp"],
    ]
    lien_lines = [
        f"Authority: {authority_line}",
        f"Case reference: {lien.get('case_ref', 'n/a')}",
        f"NCRP acknowledgement: {lien.get('ncrp_ack', 'n/a')}",
        f"Disputed UTR: {lien.get('disputed_utr', 'n/a')}",
        f"Disputed amount: {lien.get('disputed_amount', 'n/a')}",
        f"Disputed date: {lien.get('disputed_date', 'n/a')}",
    ]

    if isolation.matched:
        matched_lines = [
            f"Selected transaction {isolation.matched.txn_id}",
            f"UTR {isolation.matched.utr}",
            f"Amount {isolation.matched.amount}",
            f"Timestamp {isolation.matched.ts.astimezone(ZoneInfo('Asia/Kolkata')):%d %b %Y, %H:%M} IST",
            f"Payer {isolation.matched.counterparty_name}",
            f"Independent checks: {_badge_list(isolation.found_by)}",
        ]
    else:
        matched_lines = ["No credit was selected for this dispute."]

    decoy_lines = []
    for index, candidate in enumerate(isolation.same_amount_candidates, start=1):
        decoy_lines.append(
            f"Not chosen {index}: {candidate.txn_id} · UTR {candidate.utr} · "
            f"{candidate.amount} at {candidate.ts.astimezone(ZoneInfo('Asia/Kolkata')):%d %b %Y, %H:%M} IST ({candidate.counterparty_name})"
        )
    if not decoy_lines:
        decoy_lines = ["No other same-amount credits in the trailing seven-day window."]

    if isolation.bill:
        bill_lines = [
            f"Bill {isolation.bill.bill_id} · total {isolation.bill.total}",
        ] + [f"Line {index + 1}: {item}" for index, item in enumerate(isolation.bill.line_items)]
    else:
        bill_lines = ["No validated bill evidence was attached."]

    if isolation.device:
        device_lines = [
            f"Terminal {isolation.device.terminal_id}",
            f"Device {isolation.device.device_id}",
            f"Geo lat {isolation.device.geo.lat} lon {isolation.device.geo.lon}",
        ]
    else:
        device_lines = ["No installed terminal/device/geo evidence at the cutoff."]

    tier_lines = [
        payload["grading_scope"],
        f"Grading: {payload['grading']}",
    ]
    for key in ("1", "2", "3", "4"):
        bucket = payload["tier_totals"][key]
        tier_lines.append(f"Tier {key}: amount {bucket['amount']}, count {bucket['count']}")

    ledger_lines = [
        f"seq {item['seq']} · {item['kind']} · {item['hash']}" for item in payload["ledger_evidence"]
    ] or ["No ledger citations were recorded for this graded packet."]

    return [
        ("Identity", identity),
        ("Lien facts", lien_lines),
        ("Selected payment", matched_lines),
        ("Same-amount candidates (not chosen)", decoy_lines),
        ("Bill evidence", bill_lines),
        ("Device and geo", device_lines),
        (f"Seven-day credit count: {isolation.seven_day_credit_count}", []),
        ("Tier scope (selected payment only)", tier_lines),
        ("Ledger evidence", ledger_lines),
    ]
