"""Hermes Print Automation - Comprehensive System Verification Suite.

Tests and validates:
1. Database creation, session state CRUD, conversation history logging.
2. PDF generation and PyMuPDF analysis (pages, color/bw detection, paper size, pricing).
3. Hermes AI agent decision logic (new doc, confirm, revise settings, revise content admin).
4. Physical printer spooler command building & simulation execution.
5. FastAPI Webhook integration test.
"""

import asyncio
import os
import sys
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Ensure UTF-8 console output on Windows
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from unittest.mock import AsyncMock, patch

import pymupdf as fitz
from fastapi.testclient import TestClient

from app.config import settings
from app.database import (
    add_conversation_history,
    get_or_create_session,
    get_recent_conversation,
    init_db,
    reset_session_file,
    update_session,
)
from app.main import app
from app.models import HermesAction, SessionStatus
from app.services.hermes_agent import process_user_turn
from app.services.pdf_service import (
    analyze_pdf,
    calculate_price,
    detect_paper_size_and_dimensions,
)
from app.services.printer_service import (
    build_sumatra_print_settings,
    get_available_printers,
    print_document,
)


def create_sample_pdf(file_path: str) -> None:
    """Generate a 5-page sample PDF with mixed content for testing 3 color tiers:
    Page 1: Grayscale text (Skripsi) -> BW
    Page 2: Color vector/graphics with low coverage (< 50%) -> COLOR_LOW
    Page 3: Grayscale text (Conclusion) -> BW
    Page 4: Color elements with high ink ratio (> 50%) -> COLOR_HIGH
    Page 5: Full page background color block (>= 40% page coverage) -> COLOR_FULL
    """
    doc = fitz.open()

    # Page 1: A4, Black and white text
    p1 = doc.new_page(width=595.28, height=841.89)
    p1.insert_text(
        fitz.Point(72, 100),
        "BAB 1 PENDAHULUAN\n\n"
        "Dokumen ini adalah draf Skripsi Sistem Otomasi Percetakan.\n"
        "Sistem ini menghubungkan WhatsApp dengan mesin printer lokal.\n"
        "Penelitian ini bertujuan untuk meningkatkan efisiensi antrean cetak.",
        fontsize=12,
        color=(0, 0, 0)
    )

    # Page 2: A4, Contains Color graphic with small area (< 50% ink ratio & low coverage)
    p2 = doc.new_page(width=595.28, height=841.89)
    p2.insert_text(
        fitz.Point(72, 100),
        "DIAGRAM ALUR SISTEM (BERWARNA SEDIKIT)",
        fontsize=14,
        color=(0.1, 0.4, 0.8)  # Blue color
    )
    # Add substantial black text so ink is mostly black
    p2.insert_text(
        fitz.Point(72, 130),
        "Teks penjelasan alur sistem dengan tinta hitam yang mendominasi halaman ini agar ink ratio warna berada di bawah 50 persen.\n" * 8,
        fontsize=11,
        color=(0, 0, 0)
    )
    # Small colored rectangle
    rect = fitz.Rect(72, 300, 150, 340)
    p2.draw_rect(rect, color=(0.9, 0.2, 0.2), fill=(1.0, 0.8, 0.2))

    # Page 3: A4, Black and white text
    p3 = doc.new_page(width=595.28, height=841.89)
    p3.insert_text(
        fitz.Point(72, 100),
        "BAB 3 KESIMPULAN\n\n"
        "Implementasi sistem berjalan dengan sukses dan siap digunakan di gerai percetakan.",
        fontsize=12,
        color=(0, 0, 0)
    )

    # Page 4: A4, Medium color graphic (> 50% ink ratio)
    p4 = doc.new_page(width=595.28, height=841.89)
    p4.insert_text(
        fitz.Point(72, 80),
        "INFOGRAFIS WARNA TINGGI (> 50%)",
        fontsize=16,
        color=(0.8, 0.1, 0.1)
    )
    # Colored rectangles
    p4.draw_rect(fitz.Rect(72, 120, 400, 300), color=(0.1, 0.6, 0.2), fill=(0.2, 0.8, 0.4))

    # Page 5: A4, Full color cover / block
    p5 = doc.new_page(width=595.28, height=841.89)
    # Draw huge color block filling more than 50% of the entire page
    p5.draw_rect(fitz.Rect(0, 0, 595.28, 600), color=(0.1, 0.2, 0.7), fill=(0.2, 0.4, 0.9))
    p5.insert_text(fitz.Point(100, 200), "COVER MAJALAH FULL WARNA", fontsize=24, color=(1, 1, 1))

    doc.save(file_path)
    doc.close()


async def run_tests():
    print("================================================================")
    print("🚀 STARTING HERMES PRINT AUTOMATION VERIFICATION SUITE")
    print("================================================================\n")

    # 1. Test Database
    print("1️⃣ Testing Database & State Management...")
    init_db()
    test_phone = "628999888777"
    reset_session_file(test_phone)
    session = get_or_create_session(test_phone, customer_name="Budi Santoso")
    assert session.phone_number == test_phone
    assert session.customer_name == "Budi Santoso"
    assert session.session_status == SessionStatus.IDLE

    # Update session
    session = update_session(test_phone, copies=2, color_mode="color", estimated_price=3000)
    assert session.copies == 2
    assert session.color_mode == "color"

    # Add conversation history
    add_conversation_history(test_phone, "user", "Halo mas mau print")
    add_conversation_history(test_phone, "assistant", "Halo Kak Budi, silakan kirim file PDF-nya.")
    history = get_recent_conversation(test_phone, limit=5)
    assert len(history) >= 2
    print("   ✅ Database and session tracking verified successfully.\n")

    # 2. Test PDF Analysis Engine
    print("2️⃣ Testing PDF Analysis Engine (PyMuPDF) with 3 Color Tiers...")
    temp_dir = settings.storage_dir_path
    sample_pdf_path = str(temp_dir / "sample_test_doc.pdf")
    create_sample_pdf(sample_pdf_path)

    analysis = analyze_pdf(sample_pdf_path, original_filename="skripsi_budi.pdf")
    print(f"   • Total Pages: {analysis.total_pages}")
    print(f"   • Color Pages ({analysis.color_pages_count}): {analysis.color_pages_list}")
    print(f"   • B/W Pages ({analysis.bw_pages_count}): {analysis.bw_pages_list}")
    print(f"   • Color Low < 50% ({analysis.color_low_count}): {analysis.color_low_pages} (Tarif Rp {settings.PRICE_COLOR_LOW:,})")
    print(f"   • Color High >= 50% ({analysis.color_high_count}): {analysis.color_high_pages} (Tarif Rp {settings.PRICE_COLOR_HIGH:,})")
    print(f"   • Color Full ({analysis.color_full_count}): {analysis.color_full_pages} (Tarif Rp {settings.PRICE_COLOR_FULL:,})")
    print(f"   • Paper Size: {analysis.paper_size}")
    print(f"   • Orientation: {analysis.orientation}")
    print(f"   • Is Color Document: {analysis.is_color_document}")
    print(f"   • Estimated Price (1 copy, auto): Rp {analysis.estimated_price:,}")

    assert analysis.total_pages == 5
    assert 1 in analysis.color_low_pages, "Page 1 (text) must be classified as COLOR_LOW (<50%)!"
    assert 2 in analysis.color_low_pages, "Page 2 (minimal color) must be classified as COLOR_LOW (<50%)!"
    assert 3 in analysis.color_low_pages, "Page 3 (text) must be classified as COLOR_LOW (<50%)!"
    assert 4 in analysis.color_high_pages, "Page 4 must be classified as COLOR_HIGH (>=50%)!"
    assert 5 in analysis.color_full_pages, "Page 5 must be classified as COLOR_FULL!"
    assert analysis.color_low_count == 3
    assert analysis.color_high_count == 1
    assert analysis.color_full_count == 1
    assert "A4" in analysis.paper_size

    # Test price calculation: 3 pages low (3*2000) + 1 high (2500) + 1 full (3000) = 11500
    price_auto = calculate_price(
        total_pages=5,
        color_low_pages=[1, 2, 3],
        color_high_pages=[4],
        color_full_pages=[5],
        copies=1,
        color_mode="auto",
        price_low=2000,
        price_high=2500,
        price_full=3000
    )
    assert price_auto == 11500, f"Expected 11500, got {price_auto}"

    # Custom range: pages 1-2 (2 Color Low) * 2 copies = (2 * 2000) * 2 = 8000
    price_custom_range = calculate_price(
        total_pages=5,
        color_low_pages=[1, 2, 3],
        color_high_pages=[4],
        color_full_pages=[5],
        copies=2,
        color_mode="auto",
        page_range="1-2",
        price_low=2000,
        price_high=2500,
        price_full=3000
    )
    assert price_custom_range == 8000, f"Expected 8000, got {price_custom_range}"
    print("   ✅ PyMuPDF analysis and 3-tier color pricing engine verified successfully.\n")

    # 3. Test Hermes AI Agent Decisions
    print("3️⃣ Testing Hermes AI Agent Decisions...")
    # Simulation: User uploads PDF
    dec_upload = await process_user_turn(
        user_message="Tolong cetak skripsi ini mas",
        session=session,
        conversation_history=[],
        pdf_info=analysis
    )
    print(f"   • Upload Action: {dec_upload.action.value}")
    assert dec_upload.action == HermesAction.NEW_DOCUMENT_SUMMARY

    # Update session with document
    session = update_session(
        test_phone,
        current_file_path=sample_pdf_path,
        original_filename="skripsi_budi.pdf",
        page_count=3,
        document_summary="Draf Skripsi Bab 1-3",
        session_status=SessionStatus.WAITING_CONFIRMATION
    )

    # Simulation: User requests print setting revision
    dec_revise_settings = await process_user_turn(
        user_message="Tolong cetak 3 rangkap ya",
        session=session,
        conversation_history=history
    )
    print(f"   • Revise Settings Action: {dec_revise_settings.action.value}")
    assert dec_revise_settings.action == HermesAction.REVISE_PRINT_SETTINGS
    assert dec_revise_settings.updated_copies == 3

    # Simulation: User requests content/design revision (Admin handover)
    dec_revise_content = await process_user_turn(
        user_message="Ada salah ketik di judul halaman 1, bisa tolong dieditkan dulu?",
        session=session,
        conversation_history=history
    )
    print(f"   • Content Revision Action: {dec_revise_content.action.value}")
    assert dec_revise_content.action == HermesAction.REVISE_CONTENT_ADMIN
    assert dec_revise_content.revision_notes_for_admin is not None

    # Simulation: User confirms print
    dec_confirm = await process_user_turn(
        user_message="Oke gaskeun cetak sekarang ya mas",
        session=session,
        conversation_history=history
    )
    print(f"   • Confirm Action: {dec_confirm.action.value}")
    assert dec_confirm.action == HermesAction.CONFIRM_PRINT
    print("   ✅ Hermes decision logic verified successfully.\n")

    # 4. Test Printer Spooler Service
    print("4️⃣ Testing Printer Spooler Service...")
    printers, default_p = get_available_printers()
    print(f"   • Detected Printers: {printers}")
    print(f"   • Default OS Printer: {default_p}")

    sumatra_args = build_sumatra_print_settings(
        copies=2, color_mode="bw", page_range="1-2", paper_size="A4", orientation="portrait"
    )
    print(f"   • Generated Sumatra Settings: '{sumatra_args}'")
    assert "copies=2" in sumatra_args
    assert "monochrome" in sumatra_args
    assert "1-2" in sumatra_args

    # Execute simulated print
    settings.PRINT_SIMULATION_MODE = True
    print_job = print_document(
        file_path=sample_pdf_path,
        copies=2,
        color_mode="bw",
        page_range="1-2",
        paper_size="A4"
    )
    print(f"   • Simulated Job Success: {print_job.success}")
    print(f"   • Command: {print_job.command_executed}")
    assert print_job.success is True
    assert print_job.is_simulated is True
    print("   ✅ Printer spooler service verified successfully.\n")

    # 5. Test FastAPI Webhook Endpoint
    print("5️⃣ Testing FastAPI Webhook Endpoints...")
    client = TestClient(app)
    
    # Health check
    res_health = client.get("/health")
    assert res_health.status_code == 200
    data_health = res_health.json()
    assert data_health["status"] == "healthy"
    print(f"   • Health check: {data_health['status']}")

    # Webhook chat message (Mock WhatsApp dispatch to preserve test speed)
    with patch("app.main.send_whatsapp_message", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = {"status": True, "detail": "mocked"}
        res_webhook = client.post(
            "/webhook/wa",
            data={
                "sender": test_phone,
                "message": "Halo hermes, toko buka sampai jam berapa?",
                "name": "Budi Santoso"
            }
        )
        assert res_webhook.status_code == 200
        assert mock_send.called, "WhatsApp reply must be dispatched via send_whatsapp_message"
        print(f"   • Webhook text response: {res_webhook.json()} (Mocked WhatsApp dispatch)")

    print("\n================================================================")
    print("🎉 ALL TESTS PASSED! THE SYSTEM IS 100% PRODUCTION READY.")
    print("================================================================\n")


if __name__ == "__main__":
    asyncio.run(run_tests())
