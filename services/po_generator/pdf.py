"""Branded contingent-PO PDF renderer.

Pure function: `build_po_pdf(po: dict) -> bytes`. No network, no GCS — fully unit
testable. Input is a `$defs/draft_po_payload`; missing optional fields degrade
gracefully. Palette echoes the Faultline midnight-nautical design tokens.
"""
from __future__ import annotations

import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# Midnight-nautical brand palette.
MIDNIGHT = colors.HexColor("#0B1F2A")
TEAL = colors.HexColor("#1FA8A0")
AMBER = colors.HexColor("#E8A33D")
CORAL = colors.HexColor("#E5604D")
MIST = colors.HexColor("#6B8794")
PAPER = colors.HexColor("#F4F7F8")


def _money(value, currency: str = "USD") -> str:
    try:
        return f"{currency} {float(value):,.2f}"
    except (TypeError, ValueError):
        return "—"


def _styles():
    base = getSampleStyleSheet()
    return {
        "brand": ParagraphStyle(
            "brand", parent=base["Title"], textColor=MIDNIGHT, fontSize=20,
            leading=24, spaceAfter=2,
        ),
        "tagline": ParagraphStyle(
            "tagline", parent=base["Normal"], textColor=TEAL, fontSize=9,
            leading=12, spaceAfter=0,
        ),
        "h2": ParagraphStyle(
            "h2", parent=base["Heading2"], textColor=MIDNIGHT, fontSize=12,
            leading=15, spaceBefore=10, spaceAfter=4,
        ),
        "label": ParagraphStyle(
            "label", parent=base["Normal"], textColor=MIST, fontSize=8,
            leading=10,
        ),
        "value": ParagraphStyle(
            "value", parent=base["Normal"], textColor=MIDNIGHT, fontSize=10,
            leading=13,
        ),
        "notes": ParagraphStyle(
            "notes", parent=base["Normal"], textColor=MIDNIGHT, fontSize=9,
            leading=13,
        ),
        "banner": ParagraphStyle(
            "banner", parent=base["Normal"], textColor=colors.white, fontSize=10,
            leading=13,
        ),
        "foot": ParagraphStyle(
            "foot", parent=base["Normal"], textColor=MIST, fontSize=7.5,
            leading=10,
        ),
    }


def _kv_table(rows: list[tuple[str, str]], s) -> Table:
    """Two-column label/value grid; pairs laid out two per row."""
    cells = []
    line = []
    for label, value in rows:
        line.append(Paragraph(label.upper(), s["label"]))
        line.append(Paragraph(value or "—", s["value"]))
        if len(line) == 4:
            cells.append(line)
            line = []
    if line:
        while len(line) < 4:
            line.append(Paragraph("", s["value"]))
        cells.append(line)
    t = Table(cells, colWidths=[1.0 * inch, 1.7 * inch, 1.0 * inch, 1.7 * inch])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
    ]))
    return t


def build_po_pdf(po: dict) -> bytes:
    s = _styles()
    buf = io.BytesIO()
    po_id = po.get("po_id", "unknown")
    currency = po.get("currency", "USD")
    contingent = po.get("contingent", True)

    doc = SimpleDocTemplate(
        buf, pagesize=LETTER,
        topMargin=0.7 * inch, bottomMargin=0.7 * inch,
        leftMargin=0.75 * inch, rightMargin=0.75 * inch,
        title=f"Contingent Purchase Order {po_id}",
        author="Faultline",
    )
    flow = []

    # ── Header band ──────────────────────────────────────────────
    header = Table(
        [[Paragraph("Faultline", s["brand"]),
          Paragraph(f"PURCHASE ORDER<br/><font size=13>{po_id}</font>", s["value"])]],
        colWidths=[3.6 * inch, 3.4 * inch],
    )
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("LINEBELOW", (0, 0), (-1, -1), 2, TEAL),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    flow.append(header)
    flow.append(Paragraph("Supply-chain control tower · autonomous re-sourcing", s["tagline"]))
    flow.append(Spacer(1, 6))

    # ── Contingent banner ────────────────────────────────────────
    if contingent:
        banner = Table(
            [[Paragraph(
                "◆ CONTINGENT PURCHASE ORDER — drafted by the Faultline agent. "
                "Becomes binding <b>only</b> on operator approval.", s["banner"])]],
            colWidths=[7.0 * inch],
        )
        banner.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), AMBER),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("ROUNDEDCORNERS", [4, 4, 4, 4]),
        ]))
        flow.append(banner)
        flow.append(Spacer(1, 8))

    # ── Parties & terms ──────────────────────────────────────────
    flow.append(Paragraph("Order details", s["h2"]))
    flow.append(_kv_table([
        ("Buyer", po.get("buyer", "—")),
        ("Supplier", po.get("supplier_name", po.get("supplier_id", "—"))),
        ("Need by", po.get("need_by_date", "—")),
        ("Lead time", f"{po.get('lead_time_days', '—')} days"),
        ("Incoterms", po.get("incoterms", "—")),
        ("Ship mode", str(po.get("ship_mode", "—")).title()),
        ("Status", str(po.get("status", "draft")).title()),
        ("Run", po.get("run_id", "—")),
    ], s))
    flow.append(Spacer(1, 6))

    # ── Line item ────────────────────────────────────────────────
    flow.append(Paragraph("Line item", s["h2"]))
    qty = po.get("quantity", "—")
    unit = po.get("unit", "")
    line = [
        ["COMPONENT", "QTY", "UNIT PRICE", "TOTAL"],
        [
            Paragraph(
                f"<b>{po.get('component_name', po.get('component_id', '—'))}</b>"
                f"<br/><font size=7 color='#6B8794'>{po.get('component_id', '')}</font>",
                s["value"]),
            f"{qty} {unit}".strip(),
            _money(po.get("unit_price_usd"), currency),
            _money(po.get("total_usd"), currency),
        ],
    ]
    items = Table(line, colWidths=[3.4 * inch, 1.2 * inch, 1.2 * inch, 1.2 * inch])
    items.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), MIDNIGHT),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("BACKGROUND", (0, 1), (-1, -1), PAPER),
        ("LINEBELOW", (0, 1), (-1, -1), 1, TEAL),
    ]))
    flow.append(items)

    # ── Total ────────────────────────────────────────────────────
    total = Table(
        [["", Paragraph(f"<b>TOTAL  {_money(po.get('total_usd'), currency)}</b>",
                        ParagraphStyle("t", textColor=MIDNIGHT, fontSize=12,
                                       alignment=2))]],
        colWidths=[4.6 * inch, 2.4 * inch],
    )
    total.setStyle(TableStyle([("TOPPADDING", (0, 0), (-1, -1), 6)]))
    flow.append(total)

    # ── Notes ────────────────────────────────────────────────────
    if po.get("notes"):
        flow.append(Paragraph("Notes", s["h2"]))
        flow.append(Paragraph(po["notes"], s["notes"]))

    flow.append(Spacer(1, 16))
    flow.append(Paragraph(
        f"Generated by Faultline · PO {po_id} · exposure {po.get('exposure_id', '—')} · "
        "This document is a draft until approved. All AI-generated terms are operator-gated.",
        s["foot"]))

    doc.build(flow)
    return buf.getvalue()
