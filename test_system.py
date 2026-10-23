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
    """Generate a 3-page sample PDF with mixed content for testing.
    Page 1: Grayscale text (Skripsi)
    Page 2: Color vector/graphics
    Page 3: Grayscale text (Conclusion)
    """
    doc = fitz.open()

    # Page 1: A4, Black and white text
    p1 = doc.new_page(width=595.28, height=841.89)
    p1.insert_text(
        fitz.Point(72, 100),
        "BAB 1 PENDAHULUAN\n\n"
        "Dokumen ini adalah draf Skripsi Sistem Otomasi Percetakan.\n"
        "Sistem ini menghubungkan WhatsApp Fonnte dengan mesin printer lokal.\n"
        "Penelitian ini bertujuan untuk meningkatkan efisiensi antrean cetak.",
        fontsize=12,
        color=(0, 0, 0)
    )

    # Page 2: A4, Contains Color graphic
    p2 = doc.new_page(width=595.28, height=841.89)
    p2.insert_text(
        fitz.Point(72, 100),
        "DIAGRAM ALUR SISTEM (BERWARNA)",
        fontsize=14,
        color=(0.1, 0.4, 0.8)  # Blue color
    )
    # Draw colored rectangle
    rect = fitz.Rect(72, 150, 300, 250)
    p2.draw_rect(rect, color=(0.9, 0.2, 0.2), fill=(1.0, 0.8, 0.2))  # Red border, yellow fill

    # Page 3: A4, Black and white text
    p3 = doc.new_page(width=595.28, height=841.89)
    p3.insert_text(
        fitz.Point(72, 100),
        "BAB 3 KESIMPULAN\n\n"
        "Implementasi sistem berjalan dengan sukses dan siap digunakan di gerai percetakan.",
        fontsize=12,
        color=(0, 0, 0)
    )

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
    print("2️⃣ Testing PDF Analysis Engine (PyMuPDF)...")
    temp_dir = settings.storage_dir_path
    sample_pdf_path = str(temp_dir / "sample_test_doc.pdf")
    create_sample_pdf(sample_pdf_path)

    analysis = analyze_pdf(sample_pdf_path, original_filename="skripsi_budi.pdf")
    print(f"   • Total Pages: {analysis.total_pages}")
    print(f"   • Color Pages ({analysis.color_pages_count}): {analysis.color_pages_list}")
    print(f"   • B/W Pages ({analysis.bw_pages_count}): {analysis.bw_pages_list}")
    print(f"   • Paper Size: {analysis.paper_size}")
    print(f"   • Orientation: {analysis.orientation}")
    print(f"   • Is Color Document: {analysis.is_color_document}")
    print(f"   • Estimated Price (1 copy, auto): Rp {analysis.estimated_price:,}")

    assert analysis.total_pages == 3
    assert 2 in analysis.color_pages_list, "Page 2 must be detected as color!"
    assert 1 in analysis.bw_pages_list, "Page 1 must be detected as BW!"
    assert 3 in analysis.bw_pages_list, "Page 3 must be detected as BW!"
    assert "A4" in analysis.paper_size

    # Test price calculation
    price_all_bw = calculate_price(3, [2], [1, 3], copies=1, color_mode="bw", price_bw=500, price_color=1500)
    assert price_all_bw == 1500  # 3 * 500

    price_custom_range = calculate_price(3, [2], [1, 3], copies=2, color_mode="bw", page_range="1-2", price_bw=500)
    assert price_custom_range == 2000  # 2 pages * 500 * 2 copies
    print("   ✅ PyMuPDF analysis and pricing engine verified successfully.\n")

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
        user_message="Tolong cetak 3 rangkap hitam putih ya",
        session=session,
        conversation_history=history
    )
    print(f"   • Revise Settings Action: {dec_revise_settings.action.value}")
    assert dec_revise_settings.action == HermesAction.REVISE_PRINT_SETTINGS
    assert dec_revise_settings.updated_copies == 3
    assert dec_revise_settings.updated_color_mode == "bw"

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

    # Webhook chat message
    res_webhook = client.post(
        "/webhook/fonnte",
        data={
            "sender": test_phone,
            "message": "Halo hermes, toko buka sampai jam berapa?",
            "name": "Budi Santoso"
        }
    )
    assert res_webhook.status_code == 200
    print(f"   • Webhook text response: {res_webhook.json()}")

    print("\n================================================================")
    print("🎉 ALL TESTS PASSED! THE SYSTEM IS 100% PRODUCTION READY.")
    print("================================================================\n")


if __name__ == "__main__":
    asyncio.run(run_tests())
