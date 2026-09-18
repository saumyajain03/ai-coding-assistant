"""
Generate targeted synthetic PDFs specifically designed for verifying:
1. Text-only PDF -> Text/BM25
2. Image-heavy PDF -> Visual RAG
3. Scanned/image-only PDF -> OCR
4. Mixed PDF -> Multi-modal routing
5. Same image-heavy PDF with ENABLE_VISUAL_RAG=False -> Fallback
"""

import sys
from io import BytesIO
from pathlib import Path

from PIL import ImageFont
from pypdf import PdfReader, PdfWriter

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.generate_test_pdfs import make_image_page, make_text_page_pdf  # noqa: E402

OUTPUT_DIR = Path("data/manual_test/pdf")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

try:
    DEFAULT_FONT = ImageFont.load_default(size=18)
    TITLE_FONT = ImageFont.load_default(size=20)
except Exception:
    DEFAULT_FONT = ImageFont.load_default()
    TITLE_FONT = ImageFont.load_default()


def generate_targeted_text_only():
    """Generates a text-only PDF with answer explicitly in selectable text."""
    p1 = (
        "SentinelForge Cryptographic Storage Protocol Specification.\n"
        "This document defines storage voucher generation and key derivation parameters.\n"
        "TARGET_FACT_01: The primary storage voucher encryption algorithm is AES-256-GCM with PBKDF2.\n"
        "Key rotation is enforced every 90 days with ECDSA-P256 authentication.\n"
        "All voucher signatures must be validated against the local root certificate store."
    )
    p2 = (
        "Cryptographic Key Schedule and Salt Parameters.\n"
        "PBKDF2 iteration count is fixed at 10000 rounds using HMAC-SHA512.\n"
        "Master keys are stored in encrypted non-volatile local storage.\n"
        "Session keys are discarded immediately upon transaction completion."
    )
    pdf_bytes = make_text_page_pdf([p1, p2])
    out = OUTPUT_DIR / "targeted_text_only.pdf"
    out.write_bytes(pdf_bytes)
    print(f"Generated {out}")


def generate_targeted_visual_heavy():
    """Generates an image-heavy PDF where the answer exists ONLY in the diagram image."""
    def draw_bottleneck_diagram(draw, w, h):
        draw.rectangle([20, 20, w - 20, h - 20], outline="black", width=2)
        draw.text(
            (60, 60),
            "SYSTEM PERFORMANCE ANALYSIS & CAPACITY REPORT",
            fill="black",
            font=TITLE_FONT,
        )

        # Draw Throughput Chart
        draw.rectangle([60, 110, 540, 320], fill="lightgray", outline="black", width=2)
        draw.text((80, 130), "Throughput Profile (IOPS vs Latency)", fill="black", font=DEFAULT_FONT)
        draw.line([(100, 280), (500, 280)], fill="black", width=2)  # X axis
        draw.line([(100, 280), (100, 170)], fill="black", width=2)  # Y axis

        # Draw bottleneck box with answer
        draw.rectangle([60, 180, 540, 270], fill="salmon", outline="red", width=2)
        draw.text(
            (80, 200),
            "TARGET_FACT_02: Database Write Lock Bottleneck\nat 4500 IOPS",
            fill="black",
            font=DEFAULT_FONT,
        )

        # Draw recommendation box
        draw.rectangle([60, 350, 540, 460], fill="lightyellow", outline="black", width=2)
        draw.text(
            (80, 370),
            "Architectural Recommendation:\nPartition WAL across SSD arrays for linear scaling.",
            fill="black",
            font=DEFAULT_FONT,
        )

    img_bytes = make_image_page(draw_bottleneck_diagram)
    # Minimal text label to classify as VISUAL_HEAVY_PAGE
    txt_bytes = make_text_page_pdf(
        ["Figure 1: Performance Analysis Diagram and Bottleneck Chart."]
    )

    r_img = PdfReader(BytesIO(img_bytes))
    r_txt = PdfReader(BytesIO(txt_bytes))
    page = r_txt.pages[0]
    page.merge_page(r_img.pages[0])

    writer = PdfWriter()
    writer.add_page(page)

    out = OUTPUT_DIR / "targeted_visual_heavy.pdf"
    buf = BytesIO()
    writer.write(buf)
    out.write_bytes(buf.getvalue())
    print(f"Generated {out}")


def generate_targeted_scanned():
    """Generates a scanned PDF where the answer exists ONLY in rasterized pixel text (no text layer)."""
    def draw_scanned_incident(draw, w, h):
        draw.rectangle([30, 30, w - 30, h - 30], outline="gray", width=2)
        draw.text((50, 60), "INCIDENT RESPONSE POST-MORTEM REPORT", fill="black", font=TITLE_FONT)
        draw.text((50, 100), "Classification: INTERNAL SECURITY ONLY", fill="darkred", font=DEFAULT_FONT)
        draw.text(
            (50, 150),
            "TARGET_FACT_03: The root cause was an expired\nmTLS client certificate on gateway node 4.",
            fill="black",
            font=DEFAULT_FONT,
        )
        draw.text(
            (50, 220),
            "Action Taken: Gateway node 4 re-keyed with new 30-day certificate authority.",
            fill="black",
            font=DEFAULT_FONT,
        )
        draw.text(
            (50, 270),
            "Preventative Measure: Automated certificate expiry alerts set to 14 days in advance.",
            fill="black",
            font=DEFAULT_FONT,
        )

    def draw_scanned_page2(draw, w, h):
        draw.rectangle([30, 30, w - 30, h - 30], outline="gray", width=2)
        draw.text((50, 60), "APPENDIX A: NETWORK TELEMETRY LOGS", fill="black", font=TITLE_FONT)
        draw.text(
            (50, 120),
            "Packet capture confirms handshake failures between 10:14 UTC and 10:22 UTC.",
            fill="black",
            font=DEFAULT_FONT,
        )

    writer = PdfWriter()
    for fn in [draw_scanned_incident, draw_scanned_page2]:
        p_bytes = make_image_page(fn)
        r = PdfReader(BytesIO(p_bytes))
        writer.add_page(r.pages[0])

    out = OUTPUT_DIR / "targeted_scanned.pdf"
    buf = BytesIO()
    writer.write(buf)
    out.write_bytes(buf.getvalue())
    print(f"Generated {out}")


def generate_targeted_mixed():
    """Generates a 3-page mixed PDF: Page 1 text, Page 2 scanned, Page 3 text + diagram."""
    writer = PdfWriter()

    # Page 1: Normal text
    p1 = (
        "SentinelForge Cluster Node Topology.\n"
        "This chapter describes the network configuration of the cluster ingress nodes.\n"
        "TARGET_FACT_04A: Ingress traffic is processed by Node Alpha on port 8443 with TLS 1.3.\n"
        "All external packets undergo strict rate-limiting prior to routing."
    )
    r1 = PdfReader(BytesIO(make_text_page_pdf([p1])))
    writer.add_page(r1.pages[0])

    # Page 2: Scanned maintenance notice (image only)
    def draw_page2(draw, w, h):
        draw.rectangle([20, 20, w - 20, h - 20], outline="gray", width=2)
        draw.text((40, 60), "MAINTENANCE ANNOUNCEMENT -- HARDWARE RETIREMENT", fill="black", font=TITLE_FONT)
        draw.text(
            (40, 130),
            "TARGET_FACT_04B: Node Beta was decommissioned\ndue to memory hardware fault.",
            fill="black",
            font=DEFAULT_FONT,
        )
        draw.text(
            (40, 200),
            "Replacement server Node Gamma is scheduled for deployment on Friday.",
            fill="black",
            font=DEFAULT_FONT,
        )

    r2 = PdfReader(BytesIO(make_image_page(draw_page2)))
    writer.add_page(r2.pages[0])

    # Page 3: Text + Flowchart
    p3 = (
        "Section 3.3 Failover Sequencing and State Recovery.\n"
        "When an active ingress node becomes unresponsive, health probes trigger automatic failover.\n"
        "The failover sequence guarantees zero session loss by replaying uncommitted WAL entries.\n"
        "Examine the flowchart below for state recovery transitions."
    )

    def draw_flowchart(draw, w, h):
        draw.rectangle([100, 300, 220, 360], fill="lightblue", outline="black", width=2)
        draw.text((115, 320), "Active Node Fail", fill="black")
        draw.rectangle([280, 300, 400, 360], fill="lightgreen", outline="black", width=2)
        draw.text((295, 320), "Promote Standby", fill="black")
        draw.line([(220, 330), (280, 330)], fill="black", width=3)

    r3_txt = PdfReader(BytesIO(make_text_page_pdf([p3])))
    r3_img = PdfReader(BytesIO(make_image_page(draw_flowchart)))
    p3_page = r3_txt.pages[0]
    p3_page.merge_page(r3_img.pages[0])
    writer.add_page(p3_page)

    out = OUTPUT_DIR / "targeted_mixed.pdf"
    buf = BytesIO()
    writer.write(buf)
    out.write_bytes(buf.getvalue())
    print(f"Generated {out}")


if __name__ == "__main__":
    generate_targeted_text_only()
    generate_targeted_visual_heavy()
    generate_targeted_scanned()
    generate_targeted_mixed()
    print("All 4 targeted test PDFs generated successfully!")
