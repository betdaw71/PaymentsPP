#!/usr/bin/env python3
"""Generate AvaPay INR trader operations PDF (English)."""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Image,
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

BASE = Path(__file__).resolve().parent
ASSETS = BASE / "assets"
OUT = BASE / "AvaPay-Trader-Operations-Guide-INR.pdf"


def build_styles():
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="CoverTitle",
            parent=styles["Title"],
            fontSize=26,
            leading=32,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#1a1d21"),
            spaceAfter=12,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CoverSub",
            parent=styles["Normal"],
            fontSize=13,
            leading=18,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#4f5761"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="H1",
            parent=styles["Heading1"],
            fontSize=16,
            leading=22,
            textColor=colors.HexColor("#3390ec"),
            spaceBefore=18,
            spaceAfter=10,
        )
    )
    styles.add(
        ParagraphStyle(
            name="H2",
            parent=styles["Heading2"],
            fontSize=12,
            leading=16,
            textColor=colors.HexColor("#1a1d21"),
            spaceBefore=12,
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Body",
            parent=styles["Normal"],
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#1a1d21"),
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Caption",
            parent=styles["Normal"],
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#616a75"),
            alignment=TA_CENTER,
            spaceAfter=14,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Note",
            parent=styles["Normal"],
            fontSize=9,
            leading=13,
            textColor=colors.HexColor("#4f5761"),
            backColor=colors.HexColor("#f6f6f7"),
            borderPadding=8,
            spaceAfter=10,
        )
    )
    return styles


def bullet_list(styles, items):
    return ListFlowable(
        [ListItem(Paragraph(item, styles["Body"]), leftIndent=12) for item in items],
        bulletType="bullet",
        start="•",
        leftIndent=18,
    )


def add_image(story, path: Path, caption: str, styles, max_width=16.5 * cm):
    if not path.exists():
        story.append(Paragraph(f"<i>Image missing: {path.name}</i>", styles["Body"]))
        return
    img = Image(str(path))
    iw, ih = img.imageWidth, img.imageHeight
    scale = min(max_width / iw, 1.0)
    img.drawWidth = iw * scale
    img.drawHeight = ih * scale
    story.append(img)
    story.append(Paragraph(caption, styles["Caption"]))


def main():
    styles = build_styles()
    doc = SimpleDocTemplate(
        str(OUT),
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title="AvaPay Trader Operations Guide (INR)",
        author="AvaPay",
    )
    story = []

    # Cover
    story.append(Spacer(1, 3 * cm))
    story.append(Paragraph("AvaPay", styles["CoverTitle"]))
    story.append(Paragraph("Trader Operations Guide", styles["CoverTitle"]))
    story.append(Spacer(1, 0.5 * cm))
    story.append(
        Paragraph(
            "India (INR) · English · Merchant &amp; trader back-office",
            styles["CoverSub"],
        )
    )
    story.append(Spacer(1, 1 * cm))
    story.append(
        Paragraph(
            "This document explains day-to-day work in the AvaPay trader cabinet: "
            "managing INR payment details, processing Orders In and Orders Out, "
            "and keeping your USDT working balance healthy.",
            styles["CoverSub"],
        )
    )
    story.append(PageBreak())

    # 1 Overview
    story.append(Paragraph("1. Platform overview", styles["H1"]))
    story.append(
        Paragraph(
            "AvaPay connects pay-in and pay-out traffic for the Indian market. "
            "As a <b>trader</b>, you provide live INR receiving accounts (UPI / bank / card, "
            "depending on your payment system) and execute payouts when Orders Out are assigned to you. "
            "Your earnings and risk are tracked in <b>USDT</b> on the Balance page; "
            "order tables show both <b>INR</b> amounts and <b>USD/USDT</b> equivalents.",
            styles["Body"],
        )
    )
    story.append(Paragraph("Main menu sections", styles["H2"]))
    story.append(
        bullet_list(
            styles,
            [
                "<b>Orders In</b> — incoming customer deposits in INR assigned to your payment details.",
                "<b>Orders Out</b> — outgoing payouts in INR you must send to the customer.",
                "<b>Payment Details</b> — your active INR accounts (cards, UPI IDs, bank accounts).",
                "<b>SMS</b> — optional SMS confirmations linked to devices (if enabled for your traffic).",
                "<b>Balance</b> — USDT wallet: available, frozen, deposit address, withdraw/transfer.",
                "<b>Transactions</b> — ledger of freezes, charges, deposits, transfers.",
                "<b>Withdrawals</b> — USDT withdrawal requests.",
            ],
        )
    )
    story.append(Spacer(1, 6))
    story.append(
        Paragraph(
            "<b>Header chips:</b> <i>Balance</i> (available USDT), <i>Income</i>, and <i>Frozen</i> "
            "give a quick snapshot without opening the Balance tab.",
            styles["Note"],
        )
    )

    # 2 Orders In
    story.append(PageBreak())
    story.append(Paragraph("2. Orders In (pay-in)", styles["H1"]))
    story.append(
        Paragraph(
            "Use <b>Orders In</b> to monitor deposits. When a payer sends INR to your active payment detail, "
            "a new row appears with status <b>New</b>. Confirm receipt according to your process; "
            "the platform updates status to <b>Completed</b>, <b>Expired</b>, or other terminal states.",
            styles["Body"],
        )
    )
    story.append(Paragraph("Summary row (above the table)", styles["H2"]))
    story.append(
        bullet_list(
            styles,
            [
                "<b>Total USD amount</b> — sum of USDT/USD value for the current filter result.",
                "<b>Total commission</b> — your commission on the filtered set.",
                "<b>Frozen / Hold</b> — funds temporarily locked (snowflake icon); watch this during active disputes.",
            ],
        )
    )
    story.append(Paragraph("Table columns (typical INR flow)", styles["H2"]))
    story.append(
        bullet_list(
            styles,
            [
                "<b>Status / completion time</b> — colored badge (e.g. Completed, Expired) and processing duration.",
                "<b>Expires</b> — countdown while the payer must complete payment (for active statuses).",
                "<b>Amount</b> — order size in <b>INR</b> (example: ₹10,001.00 INR).",
                "<b>Amount (USDT)</b> — converted value in USD/USDT for accounting.",
                "<b>Payment system</b> — rail (e.g. UPI, IMPS, card-to-card).",
                "<b>Payment details</b> — which of your accounts received the transfer.",
                "<b>ID</b> — click to copy the order UUID.",
            ],
        )
    )
    story.append(Spacer(1, 8))
    add_image(
        story,
        ASSETS / "01-orders-in.png",
        "Figure 1 — Orders In: filters, INR/USDT amounts, and status badges.",
        styles,
    )
    story.append(
        Paragraph(
            "<b>Tip:</b> Keep auto-refresh enabled (e.g. 10s) during busy hours. "
            "Use <b>Search</b> by order ID and <b>Advanced filters</b> for date range and status.",
            styles["Note"],
        )
    )

    # 3 Payment Details
    story.append(PageBreak())
    story.append(Paragraph("3. Payment Details (INR accounts)", styles["H1"]))
    story.append(
        Paragraph(
            "Every INR account you expose to traffic is a <b>payment detail</b>. "
            "Only details with correct <b>directions</b> (In / Out) and healthy <b>status</b> receive orders.",
            styles["Body"],
        )
    )
    story.append(Paragraph("Creating and maintaining details", styles["H2"]))
    story.append(
        bullet_list(
            styles,
            [
                "Click <b>Create</b> to add a new detail (owner name, payment system, limits).",
                "Use green arrow buttons under <b>Directions</b> to enable <b>Pay-in (In)</b> and/or <b>Pay-out (Out)</b>.",
                "<b>Balance</b> shows remaining capacity on the detail in local currency (INR).",
                "<b>Volume</b> — current period usage vs limit; <b>Total volume</b> — lifetime processed amount.",
                "If status is <b>Blocked by automation</b>, fix limits or contact support before re-enabling traffic.",
            ],
        )
    )
    add_image(
        story,
        ASSETS / "02-payment-details.png",
        "Figure 2 — Payment Details: directions, INR balance, and volume limits.",
        styles,
    )
    story.append(
        Paragraph(
            "<b>INR example:</b> Owner “Mumbai UPI Drop”, payment system UPI, "
            "balance ₹500,000.00, volume 0 / ₹30,000,000.00 per period — detail ready for pay-in until the cap is reached.",
            styles["Note"],
        )
    )

    # 4 Orders Out
    story.append(PageBreak())
    story.append(Paragraph("4. Orders Out (pay-out)", styles["H1"]))
    story.append(
        Paragraph(
            "On <b>Orders Out</b> you fulfill withdrawals: send the exact <b>INR</b> amount to the "
            "destination shown in <b>Payment details</b> / destination fields, then confirm in the platform "
            "when your process requires it. Statuses include <b>Completed</b>, <b>Expired</b>, and <b>Manual check</b>.",
            styles["Body"],
        )
    )
    story.append(
        bullet_list(
            styles,
            [
                "Summary chips at the top mirror Orders In (totals and frozen count).",
                "Pay attention to <b>Manual check</b> — orders waiting for operator or trader action.",
                "Export is available for reconciliation with your bank/UPI statements.",
            ],
        )
    )
    add_image(
        story,
        ASSETS / "03-orders-out.png",
        "Figure 3 — Orders Out: payout amounts in INR and completion statuses.",
        styles,
    )

    # 5 Balance
    story.append(PageBreak())
    story.append(Paragraph("5. Balance &amp; USDT collateral", styles["H1"]))
    story.append(
        Paragraph(
            "Trading in INR is collateralized in <b>USDT</b>. Your <b>available balance</b> must stay above "
            "the minimum required by operations (the dashboard may show a warning if balance is too low).",
            styles["Body"],
        )
    )
    story.append(
        bullet_list(
            styles,
            [
                "<b>Available balance</b> — USDT you can use for new exposure or withdraw.",
                "<b>Frozen balance</b> — USDT locked while orders are open or under review (snowflake icon).",
                "<b>Insurance deposit</b> — additional collateral if configured for your account.",
                "<b>Deposit address</b> — send USDT on the supported network; use Copy, then refresh after confirmations.",
                "<b>Withdraw</b> — request USDT payout to your external wallet.",
                "<b>Transfer</b> — move USDT inside the platform (if enabled for your role).",
            ],
        )
    )
    add_image(
        story,
        ASSETS / "04-balance.png",
        "Figure 4 — Balance: USDT wallet, frozen funds, and deposit address.",
        styles,
    )
    story.append(
        Paragraph(
            "<b>Important:</b> If you see “Balance is too low — make a deposit as soon as possible”, "
            "top up via the deposit address before accepting high INR volume. "
            "Typical minimums are set by operations (e.g. 999 USDT); confirm with your team lead.",
            styles["Note"],
        )
    )

    # 6 Daily workflow
    story.append(PageBreak())
    story.append(Paragraph("6. Recommended daily workflow (INR)", styles["H1"]))
    story.append(
        bullet_list(
            styles,
            [
                "1. Open <b>Balance</b> — confirm available USDT and frozen amount.",
                "2. Open <b>Payment Details</b> — enable In/Out on healthy accounts; disable blocked or full details.",
                "3. Monitor <b>Orders In</b> — complete or escalate before expiry.",
                "4. Monitor <b>Orders Out</b> — send INR payouts on time; resolve Manual check items.",
                "5. Review <b>Transactions</b> at end of shift for freezes and commissions.",
                "6. Use <b>Withdrawals</b> only after reconciling INR activity with your statements.",
            ],
        )
    )

    story.append(Paragraph("7. Status reference (quick)", styles["H1"]))
    story.append(
        bullet_list(
            styles,
            [
                "<b>Completed</b> — order finished successfully.",
                "<b>Expired</b> — payer or trader did not complete in time.",
                "<b>New / Money sent by user</b> — active pay-in states; watch expires column.",
                "<b>Manual check</b> — needs human review before completion.",
                "<b>Cannot process</b> — technical or risk block; contact support.",
            ],
        )
    )

    story.append(Spacer(1, 24))
    story.append(
        Paragraph(
            "© AvaPay · Trader Operations Guide (INR) · For authorized traders only.",
            styles["Caption"],
        )
    )

    doc.build(story)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
