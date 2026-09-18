"""
Lightweight Deterministic PDF Page Classifier
Classifies PDF pages into TEXT_PAGE, SCANNED_PAGE, MIXED_PAGE, VISUAL_HEAVY_PAGE,
or EMPTY_OR_UNREADABLE_PAGE using inexpensive structural heuristics (text density,
word count, embedded image count, and image area ratio) without requiring heavy ML inference.
"""

from typing import Any

from src.config import get_settings
from src.rag.canonical_page import PageType


def classify_pdf_page(
    page_text: str,
    page_images: list[Any],
    page_width: float = 612.0,
    page_height: float = 792.0,
    has_diagram_drawings: bool = False,
    warnings: list[str] | None = None,
) -> tuple[PageType, dict[str, Any]]:
    """
    Classifies a PDF page based on structural signals.

    Returns:
        (PageType, metrics_dict)
    """
    settings = get_settings()
    clean_text = page_text.strip()
    char_count = len(clean_text)
    word_count = len(clean_text.split())
    image_count = len(page_images)

    # Calculate total approximate image area ratio
    page_area = max(1.0, page_width * page_height)
    total_img_area = 0.0

    for img in page_images:
        # In pypdf, img is a File object; if PIL image or dimensions are available:
        width = getattr(img, "width", None)
        height = getattr(img, "height", None)
        if width and height:
            total_img_area += float(width * height)
        else:
            # Fallback: estimate standard image chunk area (e.g. 20% of page per image)
            total_img_area += page_area * 0.25

    image_area_ratio = min(1.0, total_img_area / page_area) if page_area > 0 else 0.0

    metrics: dict[str, Any] = {
        "char_count": char_count,
        "word_count": word_count,
        "image_count": image_count,
        "image_area_ratio": round(image_area_ratio, 4),
        "has_diagram_drawings": has_diagram_drawings,
    }

    # 1. EMPTY / UNREADABLE
    if char_count < 15 and image_count == 0 and not has_diagram_drawings:
        return PageType.EMPTY_OR_UNREADABLE_PAGE, metrics

    # 2. SCANNED PAGE (No/minimal selectable text, but substantial image layer)
    if char_count < settings.PDF_SCANNED_MAX_CHARS and (image_count >= 1 or image_area_ratio >= settings.PDF_VISUAL_AREA_RATIO_MIN):
        return PageType.SCANNED_PAGE, metrics

    # 3. VISUAL HEAVY PAGE (Diagrams, charts, flowcharts, architectural drawings)
    visual_keywords = ("diagram", "flowchart", "architecture", "figure", "table", "overview", "chart")
    has_visual_label = any(kw in clean_text.lower() for kw in visual_keywords)

    if (image_count >= settings.PDF_VISUAL_MIN_IMAGES and image_area_ratio >= 0.35) or (
        has_diagram_drawings and image_count >= 1
    ) or (
        image_count >= 1 and has_visual_label and char_count < settings.PDF_PAGE_TEXT_MIN_CHARS * 3
    ):
        return PageType.VISUAL_HEAVY_PAGE, metrics

    # 4. MIXED PAGE (Substantial text AND embedded images)
    if char_count >= settings.PDF_PAGE_TEXT_MIN_CHARS and image_count >= 1:
        return PageType.MIXED_PAGE, metrics

    # 5. TEXT PAGE (Standard text document page)
    return PageType.TEXT_PAGE, metrics
