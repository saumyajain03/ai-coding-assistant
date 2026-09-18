"""
Generator script to produce synthetic, deterministic PDF test documents
for SentinelForge Phase 2 manual validation.
"""

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw
from pypdf import PdfReader, PdfWriter

OUTPUT_DIR = Path("data/manual_test/pdf")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def make_text_page_pdf(pages_text: list[str]) -> bytes:
    """Constructs a valid PDF with selectable text streams using raw PDF syntax."""
    n = len(pages_text)
    kids_str = " ".join([f"{3 + 3*i} 0 R" for i in range(n)])

    body: list[str] = []
    body.append("1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
    body.append(f"2 0 obj\n<< /Type /Pages /Kids [{kids_str}] /Count {n} >>\nendobj\n")

    for i, text in enumerate(pages_text):
        p_obj_id = 3 + 3 * i
        c_obj_id = 4 + 3 * i
        f_obj_id = 5 + 3 * i

        stream_lines = ["BT", "/F1 12 Tf", "50 720 Td"]
        for line in text.split("\n"):
            clean_line = (
                line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            )
            stream_lines.append(f"({clean_line}) Tj")
            stream_lines.append("0 -18 Td")
        stream_lines.append("ET")
        stream_content = "\n".join(stream_lines)
        stream_bytes = stream_content.encode("latin1")

        body.append(
            f"{p_obj_id} 0 obj\n"
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Contents {c_obj_id} 0 R /Resources << /Font << /F1 {f_obj_id} 0 R >> >> >>\n"
            f"endobj\n"
        )
        body.append(
            f"{c_obj_id} 0 obj\n"
            f"<< /Length {len(stream_bytes)} >>\n"
            f"stream\n"
            f"{stream_content}\n"
            f"endstream\n"
            f"endobj\n"
        )
        body.append(
            f"{f_obj_id} 0 obj\n"
            f"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\n"
            f"endobj\n"
        )

    pdf_header = "%PDF-1.4\n"
    full_body = "".join(body)

    offsets: list[int] = []
    curr = len(pdf_header.encode("latin1"))
    for obj_str in body:
        offsets.append(curr)
        curr += len(obj_str.encode("latin1"))

    xref_offset = curr
    num_objects = len(body) + 1

    xref = [f"xref\n0 {num_objects}\n0000000000 65535 f \n"]
    for off in offsets:
        xref.append(f"{off:010d} 00000 n \n")
    xref_str = "".join(xref)

    trailer = (
        f"trailer\n<< /Size {num_objects} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n"
    )

    return (pdf_header + full_body + xref_str + trailer).encode("latin1")


def make_image_page(draw_fn, width=612, height=792) -> bytes:
    """Creates a single-page PDF containing a rendered image."""
    img = Image.new("RGB", (width, height), color="white")
    draw = ImageDraw.Draw(img)
    draw_fn(draw, width, height)

    buf = BytesIO()
    img.save(buf, format="PDF")
    return buf.getvalue()


# =====================================================================
# 1. Normal Text PDF (5 pages)
# =====================================================================
def generate_normal_text_pdf():
    pages = [
        (
            "SentinelForge Architecture Overview\n"
            "SentinelForge is an autonomous security analysis platform built for private environments.\n"
            "It operates with zero external cloud dependencies, ensuring source code never leaks.\n"
            "Key architectural pillars include deterministic AST parsing, tri-store RAG retrieval,\n"
            "and isolated subprocess execution for security analysis.\n"
            "CONF_OVERVIEW_PAGE1: Privacy-first architecture guarantees zero external cloud telemetry."
        ),
        (
            "Authentication Architecture and Token Lifecycle\n"
            "The authentication subsystem provides cryptographic token generation and validation.\n"
            "AuthService implements JSON Web Tokens (JWT) using HMAC-SHA256 signature verification.\n"
            "Tokens contain subject IDs, authorization scopes, and issuance timestamps.\n"
            "Clock skew tolerance is enforced to prevent replay attacks and expired credential exploitation.\n"
            "CONF_AUTH_PAGE2: AuthService validates cryptographic JWT tokens and prevents clock skew."
        ),
        (
            "Database Architecture and Unified Storage Responsibilities\n"
            "SentinelForge coordinates a unified tri-store storage layer to deliver hybrid retrieval.\n"
            "Relational metadata, canonical page records, and knowledge graph edges are persisted in SQLite.\n"
            "Dense semantic embeddings are stored locally within an embedded ChromaDB collection.\n"
            "In-memory BM25 indexes keyword frequency for exact symbol and syntax matching.\n"
            "CONF_STORAGE_PAGE3: Tri-store storage layer coordinates SQLite, ChromaDB, and in-memory BM25."
        ),
        (
            "Defensive Sandbox Architecture and Execution Limits\n"
            "The defensive sandbox enforces strict process isolation for executing external commands.\n"
            "Execution limits cap CPU runtime at five seconds and memory consumption at two hundred megabytes.\n"
            "Network restrictions drop all inbound and outbound socket connections to eliminate data exfiltration.\n"
            "Filesystem isolation restricts write operations strictly to the workspace jail boundary.\n"
            "CONF_SANDBOX_PAGE4: Defensive sandbox enforces process isolation, memory limits, and network jail."
        ),
        (
            "Testing Strategy and Verification Governance\n"
            "The testing framework validates accuracy, security guardrails, and deterministic behavior.\n"
            "Automated regression suites evaluate retrieval precision using Reciprocal Rank Fusion.\n"
            "Security vulnerability checks test prompt injection sanitization against adversarial inputs.\n"
            "Human-in-the-loop (HITL) approval gates require explicit authorization before applying code patches.\n"
            "CONF_TESTING_PAGE5: Security regression tests enforce HITL human approval for code patches."
        ),
    ]

    pdf_bytes = make_text_page_pdf(pages)
    output_path = OUTPUT_DIR / "normal_text.pdf"
    output_path.write_bytes(pdf_bytes)
    print(f"Generated {output_path} (5 pages)")


# =====================================================================
# 2. Scanned Text PDF (3 pages)
# =====================================================================
def generate_scanned_text_pdf():
    def draw_page1(draw, w, h):
        draw.rectangle([20, 20, w - 20, h - 20], outline="gray", width=2)
        draw.text(
            (60, 100),
            "SCANNED DOCUMENT -- Authentication uses JWT tokens.",
            fill="black",
        )
        draw.text(
            (60, 140),
            "Document ID: SCAN-AUTH-9081 | Classification: RESTRICTED",
            fill="darkgray",
        )
        draw.text(
            (60, 180),
            "AuthService validates tokens with HMAC-SHA256 signature verification.",
            fill="black",
        )

    def draw_page2(draw, w, h):
        draw.rectangle([20, 20, w - 20, h - 20], outline="gray", width=2)
        draw.text(
            (60, 100),
            "SCANNED DOCUMENT -- The sandbox blocks outbound network access.",
            fill="black",
        )
        draw.text(
            (60, 140),
            "Security Notice: Outbound and inbound sockets are dropped at kernel boundary.",
            fill="black",
        )

    def draw_page3(draw, w, h):
        draw.rectangle([20, 20, w - 20, h - 20], outline="gray", width=2)
        draw.text(
            (60, 100),
            "SCANNED DOCUMENT -- Human approval is required before applying patches.",
            fill="black",
        )
        draw.text(
            (60, 140),
            "Governance Rule: Automated agent must NEVER apply write operations to git without approval.",
            fill="black",
        )

    writer = PdfWriter()
    for fn in [draw_page1, draw_page2, draw_page3]:
        p_bytes = make_image_page(fn)
        r = PdfReader(BytesIO(p_bytes))
        writer.add_page(r.pages[0])

    buf = BytesIO()
    writer.write(buf)
    output_path = OUTPUT_DIR / "scanned_text.pdf"
    output_path.write_bytes(buf.getvalue())
    print(f"Generated {output_path} (3 pages)")


# =====================================================================
# 3. Visual Architecture PDF (3 pages)
# =====================================================================
def generate_visual_architecture_pdf():
    # Page 1: System Flow Diagram
    def draw_diag1(draw, w, h):
        draw.rectangle([40, 40, w - 40, h - 40], outline="black", width=2)
        # Boxes
        boxes = [
            ("User", 230, 80, 380, 130),
            ("API Gateway", 210, 180, 400, 230),
            ("Retrieval Router", 180, 280, 430, 330),
            ("Vector / BM25 / GraphRAG", 160, 380, 450, 430),
            ("LLM Agent", 220, 480, 390, 530),
        ]
        for name, x1, y1, x2, y2 in boxes:
            draw.rectangle([x1, y1, x2, y2], fill="lightgray", outline="black", width=2)
            draw.text((x1 + 15, y1 + 15), name, fill="black")

        # Down arrows
        arrows = [(305, 130, 305, 180), (305, 230, 305, 280), (305, 330, 305, 380), (305, 430, 305, 480)]
        for x1, y1, x2, y2 in arrows:
            draw.line([(x1, y1), (x2, y2)], fill="black", width=3)
            draw.polygon([(x2, y2), (x2 - 5, y2 - 10), (x2 + 5, y2 - 10)], fill="black")

    # Page 2: Dependency Diagram
    def draw_diag2(draw, w, h):
        draw.rectangle([40, 40, w - 40, h - 40], outline="black", width=2)
        draw.rectangle([100, 100, 250, 150], fill="lightblue", outline="black", width=2)
        draw.text((120, 120), "main.py", fill="black")

        draw.rectangle([100, 220, 250, 270], fill="lightblue", outline="black", width=2)
        draw.text((120, 240), "auth.py", fill="black")

        draw.rectangle([100, 340, 250, 390], fill="lightblue", outline="black", width=2)
        draw.text((120, 360), "database.py", fill="black")

        draw.rectangle([340, 220, 490, 270], fill="lightgreen", outline="black", width=2)
        draw.text((360, 240), "test_auth.py", fill="black")

        # Arrows: main -> auth, auth -> database, test_auth -> auth
        draw.line([(175, 150), (175, 220)], fill="black", width=3)
        draw.line([(175, 270), (175, 340)], fill="black", width=3)
        draw.line([(340, 245), (250, 245)], fill="black", width=3)

    # Page 3: Security Boundary Diagram
    def draw_diag3(draw, w, h):
        # Outer Sandbox Boundary
        draw.rectangle([60, 80, w - 60, h - 80], outline="red", width=3)
        draw.text((80, 95), "DEFENSIVE SANDBOX BOUNDARY", fill="red")

        draw.rectangle([100, 140, 500, 200], fill="lightyellow", outline="black", width=2)
        draw.text((120, 160), "Filesystem Jail: Strictly restricted to ./data/workspace", fill="black")

        draw.rectangle([100, 230, 500, 290], fill="lightyellow", outline="black", width=2)
        draw.text((120, 250), "Network Boundary: Outbound socket blocked", fill="black")

        draw.rectangle([100, 320, 500, 380], fill="lightyellow", outline="black", width=2)
        draw.text((120, 340), "Process Limits: 5s timeout | 200MB memory cap", fill="black")

        draw.rectangle([100, 410, 500, 470], fill="salmon", outline="black", width=2)
        draw.text((120, 430), "HITL Approval Gate: Human confirmation required", fill="black")

    labels = [
        "Figure 1: End-to-End System Architecture Diagram and Flow.",
        "Figure 2: Component Dependency Diagram showing auth and database modules.",
        "Figure 3: Sandbox Security Boundary and Approval Gate Diagram.",
    ]

    writer = PdfWriter()
    for fn, label in zip([draw_diag1, draw_diag2, draw_diag3], labels, strict=False):
        img_pdf = make_image_page(fn)
        txt_pdf = make_text_page_pdf([label])
        r_img = PdfReader(BytesIO(img_pdf))
        r_txt = PdfReader(BytesIO(txt_pdf))

        page = r_txt.pages[0]
        page.merge_page(r_img.pages[0])
        writer.add_page(page)

    buf = BytesIO()
    writer.write(buf)
    output_path = OUTPUT_DIR / "visual_architecture.pdf"
    output_path.write_bytes(buf.getvalue())
    print(f"Generated {output_path} (3 pages)")


# =====================================================================
# 4. Mixed Document PDF (4 pages)
# =====================================================================
def generate_mixed_document_pdf():
    writer = PdfWriter()

    # Page 1: Normal selectable text (> 100 chars, no images) -> TEXT_PAGE
    p1_text = (
        "Chapter 1: System Configuration and Operational Environment.\n"
        "SentinelForge requires standard POSIX environment parameters.\n"
        "All file operations must reside strictly within the configured jail root directory.\n"
        "Environment variables are loaded securely from the sanitized local configuration file.\n"
        "Arbitrary system execution is prevented by strict path validation and isolation policies."
    )
    r1 = PdfReader(BytesIO(make_text_page_pdf([p1_text])))
    writer.add_page(r1.pages[0])

    # Page 2: Image-rendered text (no selectable text) -> SCANNED_PAGE
    def draw_scanned_appendix(draw, w, h):
        draw.rectangle([30, 30, w - 30, h - 30], outline="gray", width=2)
        draw.text(
            (60, 100),
            "SCANNED APPENDIX: Verification logs from offline air-gapped run.",
            fill="black",
        )
        draw.text(
            (60, 140),
            "Recorded digest: 7f83b1657ff1fc53b92dc18148a1d65dfc2d4b1fa3d677284addd200126d9069",
            fill="darkgray",
        )

    p2_bytes = make_image_page(draw_scanned_appendix)
    r2 = PdfReader(BytesIO(p2_bytes))
    writer.add_page(r2.pages[0])

    # Page 3: Normal text (> 150 chars) + architecture diagram -> MIXED_PAGE
    p3_text = (
        "Section 3: Pipeline Processing Flow and Data Transformation Stages.\n"
        "The SentinelForge ingestion pipeline processes raw bytes, creates SHA-256 digests,\n"
        "segments sections by AST or page bounds, and writes synchronized records to the tri-store.\n"
        "The diagram below demonstrates how data flows between parser, indexer, and vector collections.\n"
        "Review the stages below before modifying ingestion parameters."
    )

    def draw_ingestion_diagram(draw, w, h):
        draw.rectangle([100, 300, 240, 360], fill="lightgray", outline="black", width=2)
        draw.text((120, 320), "Raw Content", fill="black")
        draw.rectangle([280, 300, 420, 360], fill="lightgray", outline="black", width=2)
        draw.text((300, 320), "Parser & Chunker", fill="black")
        draw.line([(240, 330), (280, 330)], fill="black", width=3)

    p3_img = make_image_page(draw_ingestion_diagram)
    r3_txt = PdfReader(BytesIO(make_text_page_pdf([p3_text])))
    r3_img = PdfReader(BytesIO(p3_img))
    p3_page = r3_txt.pages[0]
    p3_page.merge_page(r3_img.pages[0])
    writer.add_page(p3_page)

    # Page 4: Mostly visual diagram (short text with Figure keyword) -> VISUAL_HEAVY_PAGE
    p4_text = "Figure 4: Cache Topology and Storage Partition Layout."

    def draw_cache_diagram(draw, w, h):
        draw.rectangle([50, 100, w - 50, h - 100], outline="black", width=2)
        draw.rectangle([80, 140, 240, 220], fill="lightyellow", outline="black", width=2)
        draw.text((100, 170), "L1 Cache\nIn-Memory BM25", fill="black")
        draw.rectangle([280, 140, 440, 220], fill="lightcyan", outline="black", width=2)
        draw.text((300, 170), "L2 Cache\nChromaDB Store", fill="black")

    p4_img = make_image_page(draw_cache_diagram)
    r4_txt = PdfReader(BytesIO(make_text_page_pdf([p4_text])))
    r4_img = PdfReader(BytesIO(p4_img))
    p4_page = r4_txt.pages[0]
    p4_page.merge_page(r4_img.pages[0])
    writer.add_page(p4_page)

    buf = BytesIO()
    writer.write(buf)
    output_path = OUTPUT_DIR / "mixed_document.pdf"
    output_path.write_bytes(buf.getvalue())
    print(f"Generated {output_path} (4 pages)")


if __name__ == "__main__":
    generate_normal_text_pdf()
    generate_scanned_text_pdf()
    generate_visual_architecture_pdf()
    generate_mixed_document_pdf()
    print("All synthetic test PDFs generated successfully!")
