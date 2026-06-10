"""Render the situation-report markdown to PDF.

Prefers reportlab when installed (nicer typography); otherwise falls back to a small,
dependency-free PDF writer so `/report?format=pdf` always works offline. The fallback
handles headings, bullets, and monospace tables — enough for a clean executive brief.
"""
from __future__ import annotations

import re

PAGE_W, PAGE_H = 612, 792          # US Letter
MARGIN = 54
LEADING = 14


def markdown_to_pdf(md: str, title: str = "Situation Report") -> bytes:
    try:
        return _reportlab_pdf(md, title)
    except Exception:
        return _simple_pdf(md, title)


# ── reportlab path ──────────────────────────────────────────────────────────────
def _reportlab_pdf(md: str, title: str) -> bytes:
    import io

    from reportlab.lib.pagesizes import letter  # noqa
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, title=title)
    styles = getSampleStyleSheet()
    flow = []
    for raw in md.splitlines():
        line = raw.rstrip()
        if not line:
            flow.append(Spacer(1, 6))
            continue
        if line.startswith("### "):
            flow.append(Paragraph(_inline(line[4:]), styles["Heading3"]))
        elif line.startswith("## "):
            flow.append(Paragraph(_inline(line[3:]), styles["Heading2"]))
        elif line.startswith("# "):
            flow.append(Paragraph(_inline(line[2:]), styles["Title"]))
        elif line.lstrip().startswith(("- ", "* ")):
            flow.append(Paragraph("• " + _inline(line.lstrip()[2:]), styles["BodyText"]))
        else:
            flow.append(Paragraph(_inline(line), styles["BodyText"]))
    doc.build(flow)
    return buf.getvalue()


def _inline(s: str) -> str:
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"`(.+?)`", r"<font face='Courier'>\1</font>", s)
    return s


# ── dependency-free fallback ──────────────────────────────────────────────────────
def _strip_inline(s: str) -> str:
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
    s = re.sub(r"`(.+?)`", r"\1", s)
    return s


def _esc(s: str) -> str:
    return s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _wrap(text: str, max_chars: int) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    lines, cur = [], ""
    for w in words:
        if len(cur) + len(w) + 1 <= max_chars:
            cur = f"{cur} {w}".strip()
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _layout(md: str) -> list[list[tuple[str, str, int]]]:
    """Returns pages; each page is a list of (font, text, size) runs already wrapped."""
    pages: list[list[tuple[str, str, int]]] = []
    page: list[tuple[str, str, int]] = []
    y = PAGE_H - MARGIN

    def newpage():
        nonlocal page, y
        pages.append(page)
        page = []
        y = PAGE_H - MARGIN

    def emit(font: str, text: str, size: int):
        nonlocal y
        if y - LEADING < MARGIN:
            newpage()
        page.append((font, text, size))
        y -= LEADING

    for raw in md.splitlines():
        line = raw.rstrip()
        if not line:
            emit("F1", "", 10)
            continue
        font, size, body = "F1", 10, line
        if line.startswith("### "):
            font, size, body = "F2", 11, line[4:]
        elif line.startswith("## "):
            font, size, body = "F2", 13, line[3:]
        elif line.startswith("# "):
            font, size, body = "F2", 16, line[2:]
        elif "|" in line:
            if set(line.replace("|", "").replace(":", "").strip()) <= {"-", " "}:
                continue  # markdown table separator row
            font, size = "F3", 9
        elif line.lstrip().startswith(("- ", "* ")):
            body = "• " + line.lstrip()[2:]
        body = _strip_inline(body)
        max_chars = int((PAGE_W - 2 * MARGIN) / (size * (0.6 if font == "F3" else 0.5)))
        for seg in _wrap(body, max_chars):
            emit(font, seg, size)
    pages.append(page)
    return pages


def _simple_pdf(md: str, title: str) -> bytes:
    pages = _layout(md)
    objects: list[bytes] = []

    def add(b: bytes) -> int:
        objects.append(b)
        return len(objects)  # 1-based object number

    # fonts
    f1 = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    f2 = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")
    f3 = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>")
    font_map = {"F1": f1, "F2": f2, "F3": f3}

    pages_obj_num = len(objects) + 1  # reserve /Pages number
    objects.append(b"")               # placeholder, fill later

    page_nums: list[int] = []
    content_nums: list[int] = []
    for runs in pages:
        lines_out = [b"BT", f"{MARGIN} {PAGE_H - MARGIN} Td".encode()]
        cur_font = None
        first = True
        for font, text, size in runs:
            if not first:
                lines_out.append(f"0 -{LEADING} Td".encode())
            first = False
            if font != cur_font or True:
                lines_out.append(f"/{font} {size} Tf".encode())
                cur_font = font
            lines_out.append(b"(" + _esc(text).encode("latin-1", "replace") + b") Tj")
        lines_out.append(b"ET")
        stream = b"\n".join(lines_out)
        cnum = add(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream))
        content_nums.append(cnum)
        res = (
            b"<< /Font << /F1 %d 0 R /F2 %d 0 R /F3 %d 0 R >> >>"
            % (font_map["F1"], font_map["F2"], font_map["F3"])
        )
        pnum = add(
            b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %d %d] /Resources %s /Contents %d 0 R >>"
            % (pages_obj_num, PAGE_W, PAGE_H, res, cnum)
        )
        page_nums.append(pnum)

    kids = b" ".join(b"%d 0 R" % n for n in page_nums)
    objects[pages_obj_num - 1] = (
        b"<< /Type /Pages /Count %d /Kids [%s] >>" % (len(page_nums), kids)
    )
    catalog = add(b"<< /Type /Catalog /Pages %d 0 R >>" % pages_obj_num)

    # assemble file with xref
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0] * (len(objects) + 1)
    for i, body in enumerate(objects, start=1):
        offsets[i] = len(out)
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref_pos = len(out)
    out += b"xref\n0 %d\n" % (len(objects) + 1)
    out += b"0000000000 65535 f \n"
    for i in range(1, len(objects) + 1):
        out += b"%010d 00000 n \n" % offsets[i]
    out += (
        b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF"
        % (len(objects) + 1, catalog, xref_pos)
    )
    return bytes(out)
