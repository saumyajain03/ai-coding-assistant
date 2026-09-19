"""
Generate an Engineering Architecture Specification test document under data/manual_test.
Contains structural, thermal, and material specifications with engineering diagrams.
Used for semantic RAG evaluation where queries share zero lexical overlap with target answers.
"""

import sys
from io import BytesIO
from pathlib import Path

from PIL import ImageDraw, ImageFont
from pypdf import PdfReader, PdfWriter

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.generate_test_pdfs import make_image_page, make_text_page_pdf  # noqa: E402

OUTPUT_DIR = Path(__file__).resolve().parent / "pdf"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

try:
    DEFAULT_FONT = ImageFont.load_default(size=16)
    TITLE_FONT = ImageFont.load_default(size=18)
    HEADER_FONT = ImageFont.load_default(size=20)
except Exception:
    DEFAULT_FONT = ImageFont.load_default()
    TITLE_FONT = ImageFont.load_default()
    HEADER_FONT = ImageFont.load_default()


def generate_engineering_architecture_pdf() -> Path:
    writer = PdfWriter()

    # =========================================================================
    # Page 1: Structural Foundation & Geotechnical Anchorage (Text Page)
    # =========================================================================
    p1_text = (
        "ENGINEERING SPECIFICATION: INDUSTRIAL REINFORCEMENT & STRUCTURAL ANCHORAGE\n"
        "Document Ref: ENG-SPEC-2026-REV4 | Substructure Geotechnical Division\n"
        "\n"
        "1.0 DEEP SUBSTRUCTURE GEOTECHNICAL BASE\n"
        "1.1 Base Column Anchor Studs:\n"
        "Anchor bolts embedded into bedrock are fabricated from Austenitic Stainless Steel 316L\n"
        "with Molybdenum passivation. This metallurgical treatment prevents galvanic saline\n"
        "oxidation and pitting degradation in aggressive high-salinity underground aquifers.\n"
        "\n"
        "1.2 Seismic Tension Members:\n"
        "Lateral shear reinforcement across the basement slab is provided by Prestressed Carbon-Fiber\n"
        "Reinforced Polymer (CFRP) tendons. These high-modulus tendons resist severe bending moments\n"
        "and dynamic seismic shearing vibrations during major earthquake ground accelerations.\n"
        "\n"
        "1.3 Foundation Slab Matrix:\n"
        "Primary compressive bearing loads are sustained by Ultra-High-Performance Fiber-Reinforced\n"
        "Concrete (UHPFRC) Class 180, rated for compressive loads exceeding 180 MPa."
    )
    r1 = PdfReader(BytesIO(make_text_page_pdf([p1_text])))
    writer.add_page(r1.pages[0])

    # =========================================================================
    # Page 2: Thermal Barrier & Cryogenic Heat Exchanger Assembly (Visual Diagram)
    # The answer exists in the visual diagram labels and callouts!
    # =========================================================================
    def draw_thermal_diagram(draw: ImageDraw.ImageDraw, w: int, h: int):
        # Outer border
        draw.rectangle([20, 20, w - 20, h - 20], outline="black", width=2)
        draw.text((40, 40), "FIGURE 2.1: THERMAL BARRIER & EXHAUST DUCT SCHEMATIC", fill="black", font=HEADER_FONT)
        draw.text((40, 70), "Subsystem Blueprint: Cryogenic and Thermal Enclosure Materials", fill="dimgray", font=TITLE_FONT)

        # Flow Diagram Box 1: Cryogenic Delivery
        draw.rectangle([50, 120, 220, 200], fill="lightblue", outline="navy", width=2)
        draw.text((60, 135), "Cryogenic Coolant Line\nLiquid Nitrogen (-196 C)", fill="navy", font=DEFAULT_FONT)

        draw.line([(220, 160), (280, 160)], fill="black", width=3)
        draw.polygon([(280, 160), (265, 153), (265, 167)], fill="black")

        # Flow Diagram Box 2: Regenerative Pre-Chamber
        draw.rectangle([280, 120, 520, 200], fill="lightyellow", outline="goldenrod", width=2)
        draw.text((290, 135), "Regenerative Pre-Chamber\nThermal Mixing Zone", fill="black", font=DEFAULT_FONT)

        draw.line([(400, 200), (400, 260)], fill="black", width=3)
        draw.polygon([(400, 260), (393, 245), (407, 245)], fill="black")

        # Material Specification Callout 1: Aerogel Insulation Blanket
        draw.rectangle([50, 270, 540, 360], fill="aliceblue", outline="steelblue", width=2)
        draw.text(
            (65, 285),
            "MATERIAL CALLOUT A: Aerogel Silica Matrix Blanket (Density: 0.003 g/cm3)\n"
            "Primary function: Outer thermal envelope barrier preventing extreme heat loss\n"
            "and radiant dissipation to sensitive surrounding avionics enclosures.",
            fill="black",
            font=DEFAULT_FONT,
        )

        # Material Specification Callout 2: Inconel Superalloy
        draw.rectangle([50, 380, 540, 470], fill="mistyrose", outline="firebrick", width=2)
        draw.text(
            (65, 395),
            "MATERIAL CALLOUT B: Inconel 718 Nickel-Chromium Superalloy\n"
            "Primary function: Core structural combustor casing maintaining ductile yield strength\n"
            "under continuous 980 C high-temperature oxidative exposure and flame impingement.",
            fill="black",
            font=DEFAULT_FONT,
        )

        # Material Specification Callout 3: Hastelloy Impeller Shroud
        draw.rectangle([50, 490, 540, 580], fill="honeydew", outline="darkgreen", width=2)
        draw.text(
            (65, 505),
            "MATERIAL CALLOUT C: Hastelloy C-276 Impeller Shroud\n"
            "Primary function: Exhaust gas scrubber lining resisting severe chemical pitting,\n"
            "wet chlorine compounds, and concentrated nitric acid condensation.",
            fill="black",
            font=DEFAULT_FONT,
        )

        # Legend Box
        draw.rectangle([50, 610, 540, 720], fill="lightgray", outline="gray", width=1)
        draw.text(
            (65, 625),
            "ASSEMBLY NOTES & TOLERANCES:\n"
            "- All thermal barrier fasteners must be torque-calibrated to 45 Nm.\n"
            "- Maximum allowable radiant heat flux across blanket perimeter: < 12 W/m2.\n"
            "- Inspect weld seams with ultrasonic non-destructive testing (NDT).",
            fill="black",
            font=DEFAULT_FONT,
        )

    img_bytes = make_image_page(draw_thermal_diagram)
    txt_bytes = make_text_page_pdf(
        ["Figure 2.1: Thermal Barrier and Cryogenic Heat Exchanger Assembly Blueprint."]
    )
    r_img = PdfReader(BytesIO(img_bytes))
    r_txt = PdfReader(BytesIO(txt_bytes))
    page2 = r_txt.pages[0]
    page2.merge_page(r_img.pages[0])
    writer.add_page(page2)

    # =========================================================================
    # Page 3: Fluid Conduit & High-Pressure Piping System (Mixed Page)
    # =========================================================================
    p3_text = (
        "3.0 FLUID CONDUITS AND HIGH-PRESSURE PIPING MANIFOLD\n"
        "3.1 Hydraulic Duct Metallurgy:\n"
        "Conduits subject to rapid fluid surges are constructed from Titanium Grade 5 (Ti-6Al-4V) Ducts.\n"
        "This aerospace-grade alloy provides high strength-to-weight ratio while sustaining transient\n"
        "surge burst pressures exceeding 350 bar without plastic deformation.\n"
        "\n"
        "3.2 Interface Sealing Elements:\n"
        "Flange mating junctions are hermetically sealed using Perfluoroelastomer (FFKM) Kalrez O-Rings.\n"
        "These elastomeric barriers prevent fugitive emissions and catastrophic leakage of hazardous\n"
        "volatile hydrocarbons across temperatures ranging from -40 C to +320 C."
    )
    r3 = PdfReader(BytesIO(make_text_page_pdf([p3_text])))
    writer.add_page(r3.pages[0])

    out_file = OUTPUT_DIR / "engineering_architecture_spec.pdf"
    buf = BytesIO()
    writer.write(buf)
    out_file.write_bytes(buf.getvalue())
    print(f"Generated {out_file} ({len(out_file.read_bytes())} bytes, {len(writer.pages)} pages)")
    return out_file


if __name__ == "__main__":
    generate_engineering_architecture_pdf()
