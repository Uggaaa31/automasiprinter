"""Hermes Print Automation - FastAPI Main Application & Webhook Engine.

Entry point for Fonnte WhatsApp webhooks, state management orchestration,
physical printing spooling, and admin escalation.
"""

import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.database import (
    add_conversation_history,
    get_db_connection,
    get_or_create_session,
    get_recent_conversation,
    init_db,
    reset_session_file,
    update_session,
)
from app.models import (
    FonnteWebhookPayload,
    HermesAction,
    SessionStatus,
)
from app.services.fonnte_service import forward_document_to_admin, send_whatsapp_message
from app.services.hermes_agent import process_user_turn
from app.services.pdf_service import (
    analyze_pdf,
    calculate_price,
    download_pdf_from_url,
)
from app.services.printer_service import (
    find_sumatrapdf_executable,
    get_available_printers,
    print_document,
)

# Configure comprehensive logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("hermes.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle handler."""
    logger.info("=============================================================")
    logger.info("Starting Hermes Print Automation System...")
    logger.info("Store: %s | AI Provider: %s (%s)", settings.STORE_NAME, settings.AI_PROVIDER, settings.AI_MODEL)
    
    # 1. Initialize SQLite Database
    init_db()
    logger.info("SQLite Database initialized at: %s", settings.DATABASE_PATH)

    # 2. Check and report Printer Environment
    printers, default_printer = get_available_printers()
    logger.info("Target OS: %s | Detected Printers: %s", settings.PRINTER_OS, printers)
    logger.info("Default Printer: %s | Configured PRINTER_NAME: %s", default_printer, settings.PRINTER_NAME or "(Auto)")
    
    if settings.PRINTER_OS.lower() == "windows":
        sumatra_bin = find_sumatrapdf_executable()
        logger.info("SumatraPDF Status: %s", sumatra_bin or "Not Found (PowerShell fallback will be used)")

    if settings.PRINT_SIMULATION_MODE:
        logger.warning("PRINT_SIMULATION_MODE is ON. Real physical printing commands will be simulated.")
    else:
        logger.info("PRINT_SIMULATION_MODE is OFF. Physical spooler commands are LIVE.")
    
    logger.info("Server ready and listening for Fonnte Webhooks on /webhook/fonnte")
    logger.info("=============================================================")
    
    yield
    
    logger.info("Shutting down Hermes Print Automation System. Goodbye!")


app = FastAPI(
    title="Hermes Print Automation",
    description="WhatsApp-based AI Automated Document Printing System using Fonnte API and Physical Spooler",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def parse_fonnte_request(request: Request) -> FonnteWebhookPayload:
    """Parse incoming Fonnte webhook request flexibly from JSON or Form Data."""
    content_type = request.headers.get("content-type", "").lower()
    raw_data: Dict[str, Any] = {}

    if "application/json" in content_type:
        try:
            raw_data = await request.json()
        except Exception:
            raw_data = {}
    else:
        form = await request.form()
        raw_data = dict(form)

    sender = str(raw_data.get("sender", "")).strip()
    message = str(raw_data.get("message", "")).strip()
    url = raw_data.get("url") or None
    filename = raw_data.get("filename") or None
    filetype = raw_data.get("filetype") or None
    name = str(raw_data.get("name", "")).strip()

    if not sender:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing 'sender' field in webhook payload"
        )

    return FonnteWebhookPayload(
        sender=sender,
        message=message,
        url=url,
        filename=filename,
        filetype=filetype,
        name=name,
        device=raw_data.get("device"),
        member=raw_data.get("member")
    )


@app.post("/webhook/fonnte", status_code=status.HTTP_200_OK)
async def fonnte_webhook(request: Request):
    """Primary webhook endpoint invoked by Fonnte on incoming WhatsApp messages or media."""
    payload = await parse_fonnte_request(request)
    sender = payload.sender
    customer_name = payload.name or ""
    message_text = payload.message or ""
    file_url = payload.url
    filename = payload.filename or ""

    logger.info(
        "[WEBHOOK RECEIVED] From: %s (%s) | Msg: '%s' | URL: %s | Filename: %s",
        sender, customer_name, message_text, file_url, filename
    )

    # 1. Retrieve or initialize user session
    session = get_or_create_session(sender, customer_name=customer_name)
    conversation_history = get_recent_conversation(sender, limit=6)

    # 2. Check if a PDF file attachment was sent
    is_pdf_attachment = False
    if file_url:
        is_pdf_attachment = (
            file_url.lower().endswith(".pdf") or
            filename.lower().endswith(".pdf") or
            (payload.filetype and "pdf" in payload.filetype.lower()) or
            (payload.filetype and "document" in payload.filetype.lower())
        )

    # =========================================================================
    # CASE A: CUSTOMER UPLOADED A PDF DOCUMENT
    # =========================================================================
    if is_pdf_attachment and file_url:
        try:
            logger.info("[PDF DOWNLOAD] Fetching PDF from %s ...", file_url)
            local_pdf_path = await download_pdf_from_url(file_url, original_filename=filename)
            logger.info("[PDF SAVED] Stored at: %s", local_pdf_path)

            # Analyze PDF
            analysis = analyze_pdf(local_pdf_path, original_filename=filename or "document.pdf")
            logger.info(
                "[PDF ANALYZED] Pages: %d | Color: %d | BW: %d | Size: %s | Orient: %s",
                analysis.total_pages, analysis.color_pages_count, analysis.bw_pages_count,
                analysis.paper_size, analysis.orientation
            )

            # Update session with document attributes
            session = update_session(
                sender,
                current_file_path=local_pdf_path,
                original_filename=analysis.original_filename,
                file_url=file_url,
                page_count=analysis.total_pages,
                color_pages_count=analysis.color_pages_count,
                bw_pages_count=analysis.bw_pages_count,
                paper_size=analysis.paper_size,
                orientation=analysis.orientation,
                copies=1,
                color_mode="color" if analysis.is_color_document else "bw",
                page_range="all",
                estimated_price=analysis.estimated_price,
                session_status=SessionStatus.WAITING_CONFIRMATION
            )

            # Let Hermes generate summary and confirmation offer
            decision = await process_user_turn(
                user_message=message_text or "Tolong cetak dokumen ini",
                session=session,
                conversation_history=conversation_history,
                pdf_info=analysis
            )

            # Update document summary in session
            if decision.document_summary:
                update_session(sender, document_summary=decision.document_summary)

            # Dispatch WhatsApp message back to customer
            await send_whatsapp_message(sender, decision.reply_message)

            # Record turn in conversation history
            add_conversation_history(sender, "user", f"[Mengirim File PDF: {analysis.original_filename}] {message_text}")
            add_conversation_history(sender, "assistant", decision.reply_message, action=decision.action.value)

            return {
                "status": "success",
                "action": decision.action.value,
                "pages": analysis.total_pages,
                "price": analysis.estimated_price
            }

        except Exception as exc:
            logger.error("[ERROR HANDLING PDF] %s", exc, exc_info=True)
            error_reply = (
                "⚠️ Mohon maaf Kak, terjadi kendala saat mengunduh atau membaca berkas PDF Anda. "
                "Pastikan berkas tidak rusak atau terenkripsi password, lalu coba kirimkan kembali ya. 🙏"
            )
            await send_whatsapp_message(sender, error_reply)
            return {"status": "error", "message": str(exc)}

    # =========================================================================
    # CASE B: CUSTOMER SENT A TEXT MESSAGE (MULTI-TURN DIALOGUE)
    # =========================================================================
    if not message_text:
        return {"status": "ignored", "reason": "Empty message"}

    # Pass customer's request to Hermes AI Agent
    decision = await process_user_turn(
        user_message=message_text,
        session=session,
        conversation_history=conversation_history
    )
    logger.info("[HERMES DECISION] Action: %s | Reasoning: %s", decision.action.value, decision.reasoning)

    # -------------------------------------------------------------------------
    # 1. ACTION: CONFIRM_PRINT (Print Spooler Execution)
    # -------------------------------------------------------------------------
    if decision.action == HermesAction.CONFIRM_PRINT:
        if not session.current_file_path:
            # No active document to print
            no_doc_msg = (
                "Belum ada dokumen yang aktif untuk dicetak Kak. "
                "Silakan kirimkan file PDF yang ingin dicetak terlebih dahulu ya! 📄"
            )
            await send_whatsapp_message(sender, no_doc_msg)
            return {"status": "ok", "action": "NO_ACTIVE_DOCUMENT"}

        logger.info(
            "[TRIGGER PRINT] File: %s | Copies: %d | Mode: %s | Pages: %s",
            session.current_file_path, session.copies, session.color_mode, session.page_range
        )

        update_session(sender, session_status=SessionStatus.PRINTING)

        # Execute physical print job
        print_result = print_document(
            file_path=session.current_file_path,
            copies=session.copies,
            color_mode=session.color_mode,
            page_range=session.page_range,
            paper_size=session.paper_size,
            orientation=session.orientation
        )

        if print_result.success:
            update_session(sender, session_status=SessionStatus.PRINTED)
            await send_whatsapp_message(sender, decision.reply_message)
            add_conversation_history(sender, "user", message_text)
            add_conversation_history(sender, "assistant", decision.reply_message, action="CONFIRM_PRINT")
            return {"status": "ok", "action": "CONFIRM_PRINT", "print_result": print_result.model_dump()}
        else:
            logger.error("[PRINT FAILED] Error: %s", print_result.error_message)
            fail_msg = (
                "⚠️ Mohon maaf Kak, terjadi kendala teknis pada mesin pencetak. "
                "Staf gerai kami sedang memeriksa printer fisik. Harap menunggu sebentar ya Kak! 🙏"
            )
            await send_whatsapp_message(sender, fail_msg)
            return {"status": "error", "error": print_result.error_message}

    # -------------------------------------------------------------------------
    # 2. ACTION: REVISE_PRINT_SETTINGS (Update copies, color, pages)
    # -------------------------------------------------------------------------
    elif decision.action == HermesAction.REVISE_PRINT_SETTINGS:
        new_copies = decision.updated_copies or session.copies
        new_color_mode = decision.updated_color_mode or session.color_mode
        new_page_range = decision.updated_page_range or session.page_range

        # Recalculate price if document is loaded
        recalculated_price = session.estimated_price
        if session.page_count > 0:
            recalculated_price = calculate_price(
                total_pages=session.page_count,
                color_pages_list=[],  # simplified or based on mode
                bw_pages_list=[],
                copies=new_copies,
                color_mode=new_color_mode,
                page_range=new_page_range
            )

        update_session(
            sender,
            copies=new_copies,
            color_mode=new_color_mode,
            page_range=new_page_range,
            estimated_price=recalculated_price,
            session_status=SessionStatus.WAITING_CONFIRMATION
        )

        await send_whatsapp_message(sender, decision.reply_message)
        add_conversation_history(sender, "user", message_text)
        add_conversation_history(sender, "assistant", decision.reply_message, action="REVISE_PRINT_SETTINGS")
        return {"status": "ok", "action": "REVISE_PRINT_SETTINGS", "updated_price": recalculated_price}

    # -------------------------------------------------------------------------
    # 3. ACTION: REVISE_CONTENT_ADMIN (Escalate to Admin WhatsApp)
    # -------------------------------------------------------------------------
    elif decision.action == HermesAction.REVISE_CONTENT_ADMIN:
        revision_notes = decision.revision_notes_for_admin or message_text

        update_session(sender, session_status=SessionStatus.ADMIN_HANDOVER)

        # Forward file & instructions to Admin
        forward_result = await forward_document_to_admin(
            customer_phone=sender,
            customer_name=customer_name or session.customer_name,
            file_path=session.current_file_path or "",
            revision_notes=revision_notes,
            document_summary=session.document_summary,
            print_settings={
                "copies": session.copies,
                "color_mode": session.color_mode,
                "page_range": session.page_range,
                "paper_size": session.paper_size
            }
        )
        logger.info("[ADMIN FORWARD] Result: %s", forward_result)

        # Inform customer
        await send_whatsapp_message(sender, decision.reply_message)
        add_conversation_history(sender, "user", message_text)
        add_conversation_history(sender, "assistant", decision.reply_message, action="REVISE_CONTENT_ADMIN")
        return {"status": "ok", "action": "REVISE_CONTENT_ADMIN", "forward": forward_result}

    # -------------------------------------------------------------------------
    # 4. ACTION: CANCEL_PRINT
    # -------------------------------------------------------------------------
    elif decision.action == HermesAction.CANCEL_PRINT:
        reset_session_file(sender)
        await send_whatsapp_message(sender, decision.reply_message)
        add_conversation_history(sender, "user", message_text)
        add_conversation_history(sender, "assistant", decision.reply_message, action="CANCEL_PRINT")
        return {"status": "ok", "action": "CANCEL_PRINT"}

    # -------------------------------------------------------------------------
    # 5. ACTION: CHAT / REQUEST_PDF
    # -------------------------------------------------------------------------
    else:
        await send_whatsapp_message(sender, decision.reply_message)
        add_conversation_history(sender, "user", message_text)
        add_conversation_history(sender, "assistant", decision.reply_message, action=decision.action.value)
        return {"status": "ok", "action": decision.action.value}


@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    """Health inspection endpoint providing hardware, database, and AI status."""
    printers, default_printer = get_available_printers()
    sumatra_path = find_sumatrapdf_executable() if settings.PRINTER_OS.lower() == "windows" else None

    # Database connectivity check
    db_ok = False
    try:
        with get_db_connection() as conn:
            conn.execute("SELECT 1")
            db_ok = True
    except Exception:
        db_ok = False

    return {
        "status": "healthy",
        "store": settings.STORE_NAME,
        "os": settings.PRINTER_OS,
        "database": {
            "status": "connected" if db_ok else "error",
            "path": settings.DATABASE_PATH
        },
        "printer": {
            "configured_name": settings.PRINTER_NAME or "(Auto-detect default)",
            "default_printer": default_printer,
            "detected_printers": printers,
            "sumatrapdf_binary": sumatra_path,
            "simulation_mode": settings.PRINT_SIMULATION_MODE
        },
        "ai": {
            "provider": settings.AI_PROVIDER,
            "model": settings.AI_MODEL,
            "gemini_configured": bool(settings.GEMINI_API_KEY),
            "openai_configured": bool(settings.OPENAI_API_KEY)
        },
        "whatsapp_gateway": {
            "fonnte_configured": bool(settings.FONNTE_API_TOKEN),
            "admin_number_configured": bool(settings.ADMIN_WHATSAPP_NUMBER)
        }
    }


@app.get("/printers", status_code=status.HTTP_200_OK)
async def list_printers():
    """List all physical and virtual printers detected on the local host machine."""
    printers, default_printer = get_available_printers()
    return {
        "printers": printers,
        "default_printer": default_printer,
        "active_target": settings.PRINTER_NAME or default_printer or "None"
    }


@app.get("/session/{phone_number}", status_code=status.HTTP_200_OK)
async def get_session_debug(phone_number: str):
    """Debug endpoint to inspect the current state of a customer's session."""
    session = get_or_create_session(phone_number)
    history = get_recent_conversation(phone_number, limit=10)
    return {
        "session": session.model_dump(),
        "recent_messages": history
    }
