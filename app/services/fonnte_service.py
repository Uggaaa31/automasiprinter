"""Hermes Print Automation - Fonnte WhatsApp Gateway Service.

Handles sending text notifications, dispatching interactive print confirmations,
and forwarding escalated revision requests with attachments to Admin WhatsApp.
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

import httpx

from app.config import settings

logger = logging.getLogger("hermes.fonnte")


async def send_whatsapp_message(
    target: str,
    message: str,
    file_url: Optional[str] = None,
    filename: Optional[str] = None
) -> Dict[str, Any]:
    """Send a WhatsApp text or media message via local Baileys gateway or Fonnte API."""
    # Normalize Indonesian phone number format
    clean_target = target.strip().replace("+", "").replace("-", "").replace(" ", "")

    # 1. If configured for Baileys (local zero-cost gateway), send via Baileys REST API
    if settings.WHATSAPP_GATEWAY.lower() == "baileys":
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    f"{settings.BAILEYS_API_URL.rstrip('/')}/send",
                    json={"target": clean_target, "message": message}
                )
                if response.status_code == 200:
                    response_json = response.json()
                    logger.info("[BAILEYS] Send result for %s: %s", clean_target, response_json)
                    return response_json
                else:
                    logger.warning("[BAILEYS] Local gateway returned %d: %s. Falling back to Fonnte...", response.status_code, response.text)
        except Exception as exc:
            logger.warning("[BAILEYS] Local gateway request failed (%s). Falling back to Fonnte...", exc)

    # 2. Fallback to Fonnte API
    if not settings.FONNTE_API_TOKEN:
        logger.warning(
            "[FONNTE] FONNTE_API_TOKEN is empty! Message to %s was not sent over network: %s",
            target, message[:100]
        )
        return {"status": False, "reason": "No active WhatsApp gateway available", "target": target}

    headers = {
        "Authorization": settings.FONNTE_API_TOKEN
    }

    payload = {
        "target": clean_target,
        "message": message,
        "countryCode": "62",
    }
    if file_url:
        payload["url"] = file_url
    if filename:
        payload["filename"] = filename

    api_url = f"{settings.FONNTE_API_URL.rstrip('/')}/send"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(api_url, data=payload, headers=headers)
            response_json = response.json()
            logger.info("[FONNTE] Send result for %s: %s", clean_target, response_json)
            return response_json
    except httpx.HTTPError as exc:
        logger.error("[FONNTE] HTTP error occurred when sending message to %s: %s", clean_target, exc)
        return {"status": False, "error": str(exc)}
    except Exception as exc:
        logger.error("[FONNTE] Unexpected error when sending message to %s: %s", clean_target, exc)
        return {"status": False, "error": str(exc)}


async def send_local_file_to_whatsapp(
    target: str,
    file_path: str,
    caption: str = ""
) -> Dict[str, Any]:
    """Upload and forward a local file via Fonnte multipart form."""
    if not settings.FONNTE_API_TOKEN:
        logger.warning("[FONNTE] FONNTE_API_TOKEN empty, skipping file upload for %s", target)
        return {"status": False, "reason": "FONNTE_API_TOKEN not configured"}

    path = Path(file_path)
    if not path.is_file():
        logger.error("[FONNTE] Local file does not exist: %s", file_path)
        return {"status": False, "reason": f"File not found: {file_path}"}

    headers = {
        "Authorization": settings.FONNTE_API_TOKEN
    }
    clean_target = target.strip().replace("+", "").replace("-", "").replace(" ", "")
    api_url = f"{settings.FONNTE_API_URL.rstrip('/')}/send"

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            with open(path, "rb") as f:
                files = {
                    "file": (path.name, f, "application/pdf")
                }
                data = {
                    "target": clean_target,
                    "message": caption or f"Dokumen: {path.name}",
                    "countryCode": "62",
                }
                response = await client.post(api_url, data=data, files=files, headers=headers)
                result = response.json()
                logger.info("[FONNTE] File upload result to %s: %s", clean_target, result)
                return result
    except Exception as exc:
        logger.error("[FONNTE] Error uploading file %s to %s: %s", file_path, clean_target, exc)
        return {"status": False, "error": str(exc)}


async def forward_document_to_admin(
    customer_phone: str,
    customer_name: str,
    file_path: str,
    revision_notes: str,
    document_summary: str,
    print_settings: Dict[str, Any]
) -> Dict[str, Any]:
    """Forward an escalated customer revision request and document to the Admin WhatsApp."""
    admin_number = settings.ADMIN_WHATSAPP_NUMBER
    if not admin_number:
        logger.error("[FONNTE] ADMIN_WHATSAPP_NUMBER is not configured in .env! Cannot forward.")
        return {"status": False, "reason": "ADMIN_WHATSAPP_NUMBER not configured"}

    filename = os.path.basename(file_path) if file_path else "Dokumen.pdf"
    copies = print_settings.get("copies", 1)
    color_mode = print_settings.get("color_mode", "auto").upper()
    page_range = print_settings.get("page_range", "semua")
    paper_size = print_settings.get("paper_size", "A4")

    # 1. Compose detailed notification message
    admin_message = (
        "🚨 *[ESKALASI REVISI DESAIN / ISI DOKUMEN]* 🚨\n\n"
        "Halo Admin, pelanggan mengajukan permintaan perbaikan/revisi dokumen yang membutuhkan "
        "penanganan atau editing manual sebelum dicetak:\n\n"
        f"👤 *Data Pelanggan:*\n"
        f"• Nama: {customer_name or 'Pelanggan'}\n"
        f"• WhatsApp: https://wa.me/{customer_phone.replace('+', '')}\n\n"
        f"📄 *Informasi Dokumen:*\n"
        f"• Nama File: `{filename}`\n"
        f"• Ringkasan Dokumen: {document_summary or '-'}\n\n"
        f"⚙️ *Preferensi Cetak Terakhir:*\n"
        f"• Rangkap: {copies}x\n"
        f"• Mode: {color_mode}\n"
        f"• Halaman: {page_range}\n"
        f"• Kertas: {paper_size}\n\n"
        f"📌 *Catatan Revisi dari Pelanggan:*\n"
        f"\"{revision_notes}\"\n\n"
        f"📁 *Arsip Lokal PC:*\n"
        f"`{file_path}`\n\n"
        "Silakan hubungi nomor pelanggan di atas untuk koordinasi editing dan konfirmasi cetak manual. 🙏"
    )

    # 2. Dispatch text notification
    msg_result = await send_whatsapp_message(admin_number, admin_message)

    # 3. Dispatch document file if accessible
    file_result = None
    if file_path and os.path.exists(file_path):
        caption = f"📄 File revisi dari {customer_name or customer_phone} ({filename})"
        file_result = await send_local_file_to_whatsapp(admin_number, file_path, caption=caption)

    return {
        "status": True,
        "message_result": msg_result,
        "file_result": file_result
    }
