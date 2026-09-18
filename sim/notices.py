"""Render a synthetic GST show-cause notice as a PDF, and as a phone photo of the paper.

The PDF writer uses only the standard library (Helvetica, one A4 page). The photo variant needs
Pillow and is skipped without it. Every document is watermarked SYNTHETIC SPECIMEN, and every
name, office and reference in it is fictional.
"""

from __future__ import annotations

import textwrap
from datetime import date
from pathlib import Path

PAGE_W, PAGE_H = 595, 842

_ONES = ["", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
         "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen",
         "eighteen", "nineteen"]
_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]


def inr(n: int) -> str:
    """Indian digit grouping: 6098462 -> 60,98,462."""
    s = str(int(n))
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return ",".join(groups + [tail])


def _two(n: int) -> str:
    return _ONES[n] if n < 20 else (_TENS[n // 10] + ("-" + _ONES[n % 10] if n % 10 else ""))


def _three(n: int) -> str:
    hundred, rest = divmod(n, 100)
    parts = []
    if hundred:
        parts.append(f"{_ONES[hundred]} hundred")
    if rest:
        parts.append(_two(rest))
    return " ".join(parts)


def rupees_in_words(n: int) -> str:
    """Indian system: 6098462 -> Rupees sixty lakh ninety-eight thousand four hundred sixty-two."""
    n = int(n)
    if n == 0:
        return "Rupees zero"
    crore, n = divmod(n, 10_000_000)
    lakh, n = divmod(n, 100_000)
    thousand, rest = divmod(n, 1000)
    parts = []
    if crore:
        parts.append(f"{_three(crore)} crore")
    if lakh:
        parts.append(f"{_two(lakh)} lakh")
    if thousand:
        parts.append(f"{_two(thousand)} thousand")
    if rest:
        parts.append(_three(rest))
    return "Rupees " + " ".join(parts)


def dmy(d: date) -> str:
    return d.strftime("%d-%m-%Y")


# ---------------------------------------------------------------- layout


def layout(notice: dict) -> list[tuple]:
    """Blocks shared by the PDF and the photo: ("text", x, y, size, bold, str),
    ("rule", x1, y1, x2, y2) and ("box", x, y, w, h). y runs down from the top edge."""
    blocks: list[tuple] = []
    left, right = 56, PAGE_W - 56
    y = 40

    def text(s, size=10, bold=False, x=left, gap=None):
        nonlocal y
        blocks.append(("text", x, y, size, bold, s))
        y += gap if gap is not None else size * 1.45

    def para(s, size=10):
        nonlocal y
        width = int((right - left) / (size * 0.5))
        for line in textwrap.wrap(s, width):
            text(line, size)
        y += size * 0.6

    text("SYNTHETIC SPECIMEN - NOT A REAL NOTICE. Generated test data for the Paytm Hisaab prototype.",
         7, gap=22)
    text(f"{notice['department'].upper()} (SYNTHETIC)", 15, True, gap=20)
    text(notice["office"], 9.5, gap=16)
    blocks.append(("rule", left, y, right, y))
    y += 18
    text(f"Reference No.: {notice['reference']}", 10, True, gap=0)
    text(f"Date: {dmy(notice['date'])}", 10, True, x=right - 110)
    y += 8
    text("To,")
    text(notice["addressee"], 10, True)
    text(f"Proprietor, {notice['business_name']}")
    text(notice["address"], gap=24)
    text("Subject: Notice to show cause for non-registration under the GST Act, FY 2025-26",
         10.5, True, gap=22)
    text("Sir/Madam,", gap=18)
    claimed = notice["claimed_turnover"]
    para(f"Information received from payment aggregators shows that receipts credited to your "
         f"account through UPI during the period {dmy(notice['period_from'])} to "
         f"{dmy(notice['period_to'])} amount to Rs {inr(claimed)} ({rupees_in_words(claimed)} only).")
    para(f"These receipts exceed the threshold of Rs {inr(notice['threshold'])} for registration "
         f"under section 22 of the Central Goods and Services Tax Act, 2017. You have not obtained "
         f"registration, and you appear liable to pay tax on the said turnover.")
    para(f"You are hereby directed to show cause within thirty days of receipt of this notice, that "
         f"is on or before {dmy(notice['response_due'])}, why tax, interest and penalty should not "
         f"be determined on the above turnover. Please appear with your books of account, bills and "
         f"bank statements in support of your reply.")
    y += 6
    rows = [("Period", f"{notice['period']} ({dmy(notice['period_from'])} to {dmy(notice['period_to'])})"),
            ("Turnover considered", f"Rs {inr(claimed)}"),
            ("Basis", notice["basis"]),
            ("Reply due by", dmy(notice["response_due"]))]
    top = y
    blocks.append(("box", left, top, right - left, 22 * len(rows) + 16))
    y += 12
    for label, value in rows:
        text(label, 10, True, x=left + 10, gap=0)
        text(value, 10, x=left + 160, gap=22)
    y = top + 22 * len(rows) + 48
    text("Sd/-", gap=16)
    text(notice["office"].split(",")[0].replace("Office of the ", ""), 10, True)
    text(notice["office"].split(",", 1)[-1].strip())
    blocks.append(("text", left, PAGE_H - 40, 7, False,
                   "All names, offices and reference numbers in this document are fictional."))
    return blocks


# ---------------------------------------------------------------- PDF


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def write_pdf(notice: dict, path: Path):
    ops = ["q 0.88 g BT /F2 48 Tf 0.819 0.574 -0.574 0.819 85 230 Tm (SYNTHETIC SPECIMEN) Tj ET Q",
           "0 g 0.6 w"]
    for block in layout(notice):
        if block[0] == "text":
            _, x, y, size, bold, s = block
            ops.append(f"BT /{'F2' if bold else 'F1'} {size} Tf 1 0 0 1 {x} {PAGE_H - y - size:.1f} Tm "
                       f"({_esc(s)}) Tj ET")
        elif block[0] == "rule":
            _, x1, y1, x2, y2 = block
            ops.append(f"{x1} {PAGE_H - y1:.1f} m {x2} {PAGE_H - y2:.1f} l S")
        else:
            _, x, y, w, h = block
            ops.append(f"{x} {PAGE_H - y - h:.1f} {w} {h} re S")
    stream = "\n".join(ops).encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_W} {PAGE_H}] "
        f"/Resources << /Font << /F1 4 0 R /F2 5 0 R >> >> /Contents 6 0 R >>".encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
        f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, obj in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n").encode()
    path.write_bytes(bytes(out))


# ---------------------------------------------------------------- phone photo


def _font(size: float, bold: bool):
    from PIL import ImageFont

    names = (["arialbd.ttf", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"] if bold
             else ["arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf"])
    for name in names:
        try:
            return ImageFont.truetype(name, int(size))
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=int(size))
    except TypeError:
        return ImageFont.load_default()


def write_photo(notice: dict, path: Path) -> bool:
    """A slightly rotated, unevenly lit phone photo of the printed notice. Needs Pillow."""
    try:
        from PIL import Image, ImageDraw, ImageFilter, ImageOps
    except ImportError:
        return False

    scale = 2.0
    page = Image.new("RGB", (int(PAGE_W * scale), int(PAGE_H * scale)), (250, 247, 238))
    draw = ImageDraw.Draw(page)

    mark = Image.new("L", page.size, 0)
    mark_draw, mark_font = ImageDraw.Draw(mark), _font(58 * scale, True)
    left, top, right, bottom = mark_draw.textbbox((0, 0), "SYNTHETIC SPECIMEN", font=mark_font)
    mark_draw.text(((page.width - right + left) / 2, (page.height - bottom + top) / 2),
                   "SYNTHETIC SPECIMEN", font=mark_font, fill=60)
    mark = mark.rotate(35, resample=Image.BICUBIC, center=(page.width / 2, page.height / 2))
    page.paste((200, 196, 188), mask=mark)

    ink = (32, 30, 36)
    for block in layout(notice):
        if block[0] == "text":
            _, x, y, size, bold, s = block
            draw.text((x * scale, y * scale), s, font=_font(size * scale * 1.05, bold), fill=ink)
        elif block[0] == "rule":
            _, x1, y1, x2, y2 = block
            draw.line([(x1 * scale, y1 * scale), (x2 * scale, y2 * scale)], fill=ink, width=2)
        else:
            _, x, y, w, h = block
            draw.rectangle([x * scale, y * scale, (x + w) * scale, (y + h) * scale], outline=ink, width=2)

    table = (74, 62, 52)
    canvas = Image.new("RGB", (int(page.width * 1.12), int(page.height * 1.08)), table)
    canvas.paste(page, (int(page.width * 0.06), int(page.height * 0.04)))
    canvas = canvas.rotate(-2.3, resample=Image.BICUBIC, fillcolor=table)

    w, h = canvas.size
    quad = (w * 0.02, h * 0.00, w * 0.00, h * 1.00, w * 1.00, h * 0.99, w * 0.97, h * 0.01)
    canvas = canvas.transform((w, h), Image.QUAD, quad, resample=Image.BICUBIC, fillcolor=table)

    glow = Image.radial_gradient("L").resize((int(w * 1.8), int(h * 1.8)))
    cx, cy = int(w * 0.9 - w * 0.38), int(h * 0.9 - h * 0.30)
    light = ImageOps.invert(glow.crop((cx, cy, cx + w, cy + h)))
    shade = Image.new("RGB", (w, h), (0, 0, 0))
    canvas = Image.composite(canvas, Image.blend(canvas, shade, 0.35), light)
    canvas = canvas.filter(ImageFilter.GaussianBlur(0.7)).resize((1080, int(1080 * h / w)))
    canvas.save(path, "JPEG", quality=72)
    return True
