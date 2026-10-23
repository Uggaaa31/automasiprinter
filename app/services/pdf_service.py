"""Hermes Print Automation - PDF Processing & Analysis Service.

Handles downloading PDFs, analyzing page count, paper dimensions, orientation,
color vs black & white classification per page using PyMuPDF and NumPy,
extracting text for LLM summarization, and calculating print costs.
"""

import os
import re
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import pymupdf as fitz
import httpx
import numpy as np

from app.config import settings
from app.models import PDFAnalysisResult


def convert_word_to_pdf(file_path: str) -> str:
    """Convert a Microsoft Word (.docx or .doc) file to PDF using Microsoft Word COM on Windows."""
    abs_src = str(Path(file_path).resolve())
    if not os.path.exists(abs_src):
        raise FileNotFoundError(f"Word file not found: {abs_src}")

    target_pdf = str(Path(abs_src).with_suffix(".pdf"))

    ps_script = f"""
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $doc = $word.Documents.Open('{abs_src}')
    $doc.SaveAs('{target_pdf}', 17)
    $doc.Close()
    $word.Quit()
    """
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            check=True,
            timeout=45,
            capture_output=True,
            text=True
        )
        if os.path.exists(target_pdf) and os.path.getsize(target_pdf) > 0:
            return target_pdf
    except Exception as exc:
        raise RuntimeError(f"Gagal mengonversi Word ke PDF: {exc}")

    raise RuntimeError("File PDF hasil konversi Word tidak ditemukan.")


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


def classify_page_color(page: fitz.Page, dpi: int = 36) -> Tuple[str, float]:
    """Accurately classify page into 3 color tiers based on pixel color ratio and ink coverage.
    (Catatan: Tidak ada kategori Hitam-Putih; halaman teks standar / minim warna masuk ke tier Warna < 50%).
    
    Returns:
        (category, coverage_pct)
        - 'COLOR_LOW': Warna < 50% (Rp 2.000)
        - 'COLOR_HIGH': Warna >= 50% (Rp 2.500)
        - 'COLOR_FULL': Full warna (blok warna tebal, poster, foto penuh) (Rp 3.000)
    """
    try:
        pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csRGB)
        samples = np.frombuffer(pix.samples, dtype=np.uint8).reshape((pix.height, pix.width, 3))
        total_pixels = pix.height * pix.width

        r = samples[:, :, 0].astype(np.int32)
        g = samples[:, :, 1].astype(np.int32)
        b = samples[:, :, 2].astype(np.int32)

        # Difference between color channels (filters out grayscale/black/white)
        rg_diff = np.abs(r - g)
        gb_diff = np.abs(g - b)
        rb_diff = np.abs(r - b)
        max_diff = np.maximum(rg_diff, np.maximum(gb_diff, rb_diff))

        # Colored pixels
        color_mask = max_diff > 18
        color_pixels = np.count_nonzero(color_mask)

        # Non-white pixels (pixels with printed ink/content)
        ink_mask = (r < 240) | (g < 240) | (b < 240)
        ink_pixels = np.count_nonzero(ink_mask)

        # Halaman dengan sedikit / tanpa warna masuk ke kategori Warna < 50%
        if color_pixels <= 30 or ink_pixels == 0:
            return "COLOR_LOW", 0.0

        # Page-wide coverage (colored pixels vs total physical sheet area)
        page_coverage = color_pixels / total_pixels
        
        # Ink-based color ratio (colored content vs total printed ink area)
        ink_ratio = (color_pixels / ink_pixels) if ink_pixels > 0 else 0.0

        # 1. Full Warna: background berwarna pekat atau foto full halaman (>= 40% luas total atau >= 80% dari tinta dengan area luas)
        if page_coverage >= 0.40 or (ink_ratio >= 0.80 and page_coverage >= 0.25):
            return "COLOR_FULL", page_coverage * 100

        # 2. Warna >= 50%: warna dominan pada konten (>= 50% dari total tinta atau >= 18% luas halaman)
        elif ink_ratio >= 0.50 or page_coverage >= 0.18:
            return "COLOR_HIGH", max(page_coverage, ink_ratio) * 100

        # 3. Warna < 50%: warna ringan / teks biasa / di bawah 50%
        else:
            return "COLOR_LOW", max(page_coverage, ink_ratio) * 100

    except Exception:
        return "COLOR_LOW", 0.0


def is_page_color(page: fitz.Page, dpi: int = 36) -> bool:
    """Helper for backward compatibility (all prints use color categories)."""
    return True


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
    color_pages_list: Optional[List[int]] = None,
    bw_pages_list: Optional[List[int]] = None,
    color_low_pages: Optional[List[int]] = None,
    color_high_pages: Optional[List[int]] = None,
    color_full_pages: Optional[List[int]] = None,
    copies: int = 1,
    color_mode: str = "auto",
    page_range: str = "all",
    price_low: Optional[int] = None,
    price_high: Optional[int] = None,
    price_full: Optional[int] = None,
    price_bw: Optional[int] = None
) -> int:
    """Calculate the total printing cost based strictly on the 3-tier color pricing:
    1. Warna < 50%: Rp 2.000
    2. Warna >= 50%: Rp 2.500
    3. Full Warna: Rp 3.000
    (Catatan: Tidak ada tarif Hitam-Putih; halaman teks standar / non-warna dihitung tarif tier Warna < 50%).
    """
    price_low = price_low if price_low is not None else settings.PRICE_COLOR_LOW
    price_high = price_high if price_high is not None else settings.PRICE_COLOR_HIGH
    price_full = price_full if price_full is not None else settings.PRICE_COLOR_FULL
    copies = max(1, copies)

    selected_pages = parse_page_range(page_range, total_pages)

    low_set = set(color_low_pages or [])
    high_set = set(color_high_pages or [])
    full_set = set(color_full_pages or [])
    bw_set = set(bw_pages_list or [])

    # If color tier breakdown is not provided, fallback to color_pages_list as low tier
    if not (low_set or high_set or full_set):
        color_set = set(color_pages_list or selected_pages)
        low_set = color_set

    count_low = len(selected_pages.intersection(low_set))
    count_high = len(selected_pages.intersection(high_set))
    count_full = len(selected_pages.intersection(full_set))
    count_bw = len(selected_pages.intersection(bw_set))

    # Semua halaman di bawah 50% (termasuk halaman teks/minim warna) dihitung tarif tier Warna < 50%
    subtotal = ((count_low + count_bw) * price_low) + (count_high * price_high) + (count_full * price_full)

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
    color_low_pages: List[int] = []
    color_high_pages: List[int] = []
    color_full_pages: List[int] = []
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

        # Color analysis with 3-tier categorization (<50%, >=50%, full)
        color_cat, _ = classify_page_color(page)
        color_pages.append(page_num)
        if color_cat == "COLOR_FULL":
            color_full_pages.append(page_num)
        elif color_cat == "COLOR_HIGH":
            color_high_pages.append(page_num)
        else:
            color_low_pages.append(page_num)

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
        color_low_pages=color_low_pages,
        color_high_pages=color_high_pages,
        color_full_pages=color_full_pages,
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
        color_low_pages=color_low_pages,
        color_high_pages=color_high_pages,
        color_full_pages=color_full_pages,
        color_low_count=len(color_low_pages),
        color_high_count=len(color_high_pages),
        color_full_count=len(color_full_pages),
        paper_size=aggregated_size,
        dimensions_mm=aggregated_dim,
        orientation=aggregated_orientation,
        text_excerpt=combined_text[:5000],
        is_color_document=is_color,
        estimated_price=default_price
    )
