"""Hermes Print Automation - PDF Processing & Analysis Service.

Handles downloading PDFs, analyzing page count, paper dimensions, orientation,
color vs black & white classification per page using PyMuPDF and NumPy,
extracting text for LLM summarization, and calculating print costs.
"""

import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import pymupdf as fitz
import httpx
import numpy as np

from app.config import settings
from app.models import PDFAnalysisResult


# Standard Paper Dimensions in PostScript Points (1 pt = 1/72 inch)
# Tolerance window (+- 10 pt) accommodates margins & PDF generator variations
STANDARD_SIZES = [
    ("A4", 595.28, 841.89, "210 x 297 mm"),
    ("F4 / Folio", 595.28, 935.43, "215 x 330 mm"),
    ("Letter", 612.00, 792.00, "216 x 279 mm"),
    ("Legal", 612.00, 1008.00, "216 x 356 mm"),
    ("A3", 841.89, 1190.55, "297 x 420 mm"),
    ("A5", 419.53, 595.28, "148 x 210 mm"),
]


def detect_paper_size_and_dimensions(width: float, height: float) -> Tuple[str, str]:
    """Identify standardized paper size name and dimensions in millimeters."""
    # Normalize orientation so shorter side is w, longer is h
    w, h = min(width, height), max(width, height)
    
    w_mm = round(w * 0.352778)
    h_mm = round(h * 0.352778)
    dim_str = f"{w_mm} x {h_mm} mm"

    for name, sw, sh, standard_dim in STANDARD_SIZES:
        if abs(w - sw) <= 12 and abs(h - sh) <= 15:
            return name, standard_dim
            
    return f"Custom ({w_mm}x{h_mm} mm)", dim_str


def is_page_color(page: fitz.Page, dpi: int = 36) -> bool:
    """Accurately detect whether a page contains color content.
    
    Renders the page to a low-res RGB pixmap and measures channel divergence
    using NumPy. Filters out grayscale JPEG artifacts and antialiasing noise.
    """
    try:
        pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csRGB)
        samples = np.frombuffer(pix.samples, dtype=np.uint8).reshape((pix.height, pix.width, 3))
        
        r = samples[:, :, 0].astype(np.int32)
        g = samples[:, :, 1].astype(np.int32)
        b = samples[:, :, 2].astype(np.int32)

        # Difference between color channels
        rg_diff = np.abs(r - g)
        gb_diff = np.abs(g - b)
        rb_diff = np.abs(r - b)
        max_diff = np.maximum(rg_diff, np.maximum(gb_diff, rb_diff))

        # Threshold > 18 ignores slight compression artifacts; > 30 pixels confirms intentional color
        color_pixels = np.count_nonzero(max_diff > 18)
        return bool(color_pixels > 30)
    except Exception:
        # Fallback to black and white on error
        return False


def parse_page_range(range_str: str, max_pages: int) -> Set[int]:
    """Parse page range expression like '1-5', '1,3,5', or 'all' into a set of 1-indexed page numbers."""
    if not range_str or range_str.strip().lower() in ("all", "semua", "*"):
        return set(range(1, max_pages + 1))

    selected_pages: Set[int] = set()
    parts = re.split(r"[,;]+", range_str.strip())
    
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            sub = part.split("-", 1)
            try:
                start = max(1, int(sub[0].strip()))
                end = min(max_pages, int(sub[1].strip()))
                if start <= end:
                    selected_pages.update(range(start, end + 1))
            except ValueError:
                continue
        else:
            try:
                page_num = int(part)
                if 1 <= page_num <= max_pages:
                    selected_pages.add(page_num)
            except ValueError:
                continue

    return selected_pages if selected_pages else set(range(1, max_pages + 1))


def calculate_price(
    total_pages: int,
    color_pages_list: List[int],
    bw_pages_list: List[int],
    copies: int = 1,
    color_mode: str = "auto",
    page_range: str = "all",
    price_bw: Optional[int] = None,
    price_color: Optional[int] = None
) -> int:
    """Calculate the total printing cost based on settings and detected page colors."""
    price_bw = price_bw if price_bw is not None else settings.PRICE_PER_PAGE_BW
    price_color = price_color if price_color is not None else settings.PRICE_PER_PAGE_COLOR
    copies = max(1, copies)

    selected_pages = parse_page_range(page_range, total_pages)
    selected_count = len(selected_pages)

    if color_mode == "bw":
        return selected_count * price_bw * copies
    elif color_mode == "color":
        return selected_count * price_color * copies
    else:  # 'auto' mode: charge color price for color pages, bw price for bw pages
        color_set = set(color_pages_list)
        bw_set = set(bw_pages_list)
        
        target_color_count = len(selected_pages.intersection(color_set))
        target_bw_count = len(selected_pages.intersection(bw_set))

        subtotal = (target_color_count * price_color) + (target_bw_count * price_bw)
        return subtotal * copies


async def download_pdf_from_url(url: str, original_filename: Optional[str] = None) -> str:
    """Download a PDF file from a given URL to the local storage directory."""
    storage_dir = settings.storage_dir_path
    
    # Generate a clean, collision-safe filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    clean_name = re.sub(r"[^\w\-.]", "_", original_filename or "document.pdf")
    if not clean_name.lower().endswith(".pdf"):
        clean_name += ".pdf"
    
    unique_filename = f"{timestamp}_{uuid.uuid4().hex[:6]}_{clean_name}"
    local_path = storage_dir / unique_filename

    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()
        local_path.write_bytes(response.content)

    return str(local_path.resolve())


def analyze_pdf(file_path: str, original_filename: Optional[str] = None) -> PDFAnalysisResult:
    """Perform comprehensive structural, dimensional, color, and textual analysis of a PDF."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"PDF file does not exist at path: {file_path}")

    filename = original_filename or os.path.basename(file_path)
    doc = fitz.open(file_path)
    total_pages = len(doc)
    
    if total_pages == 0:
        raise ValueError("PDF document has 0 pages.")

    color_pages: List[int] = []
    bw_pages: List[int] = []
    orientations: Set[str] = set()
    paper_sizes: Set[str] = set()
    dimensions_set: Set[str] = set()
    
    extracted_text_pieces: List[str] = []

    for idx, page in enumerate(doc):
        page_num = idx + 1
        rect = page.rect
        w, h = rect.width, rect.height

        # Orientation detection
        if w > h:
            orientations.add("Lanskap")
        else:
            orientations.add("Potret")

        # Size detection
        size_name, dim_str = detect_paper_size_and_dimensions(w, h)
        paper_sizes.add(size_name)
        dimensions_set.add(dim_str)

        # Color analysis
        if is_page_color(page):
            color_pages.append(page_num)
        else:
            bw_pages.append(page_num)

        # Text extraction sampling (first 3 pages, middle page, last page for rich context)
        if page_num <= 4 or page_num == total_pages or (page_num == (total_pages // 2)):
            page_text = page.get_text("text").strip()
            if page_text:
                extracted_text_pieces.append(f"--- [Halaman {page_num}] ---\n{page_text[:1500]}")

    doc.close()

    # Determine aggregated orientation
    if len(orientations) > 1:
        aggregated_orientation = "Campuran (Potret & Lanskap)"
    elif orientations:
        aggregated_orientation = list(orientations)[0]
    else:
        aggregated_orientation = "Potret"

    # Aggregated paper size
    aggregated_size = list(paper_sizes)[0] if len(paper_sizes) == 1 else f"Campuran ({', '.join(paper_sizes)})"
    aggregated_dim = list(dimensions_set)[0] if len(dimensions_set) == 1 else "Bervariasi"

    # Combined text excerpt
    combined_text = "\n\n".join(extracted_text_pieces)
    if not combined_text.strip():
        combined_text = "[Dokumen pindaian/scan atau gambar tanpa layer teks yang dapat diekstrak]"

    is_color = len(color_pages) > 0
    default_price = calculate_price(
        total_pages=total_pages,
        color_pages_list=color_pages,
        bw_pages_list=bw_pages,
        copies=1,
        color_mode="auto",
        page_range="all"
    )

    return PDFAnalysisResult(
        file_path=file_path,
        original_filename=filename,
        total_pages=total_pages,
        color_pages_count=len(color_pages),
        bw_pages_count=len(bw_pages),
        color_pages_list=color_pages,
        bw_pages_list=bw_pages,
        paper_size=aggregated_size,
        dimensions_mm=aggregated_dim,
        orientation=aggregated_orientation,
        text_excerpt=combined_text[:5000],
        is_color_document=is_color,
        estimated_price=default_price
    )
