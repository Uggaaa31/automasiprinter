"""Hermes Print Automation - WhatsApp Gateway Service.

Handles sending outbound messages and notifications to customers and admins
via the local Baileys WhatsApp Gateway (port 3001).
"""

import logging
from typing import Any, Dict, Optional
import httpx
from app.config import settings

logger = logging.getLogger("hermes.whatsapp")


async def send_whatsapp_message(
    target: str,
    message: str,
    file_url: Optional[str] = None,
    filename: Optional[str] = None
) -> Dict[str, Any]:
    """Send an outbound WhatsApp message via local Baileys gateway."""
    clean_target = target.strip().replace("+", "").replace("-", "").replace(" ", "")

    api_url = f"{settings.BAILEYS_API_URL.rstrip('/')}/send"
    payload = {
        "target": clean_target,
        "message": message
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(api_url, json=payload)
            if response.status_code == 200:
                res_data = response.json()
                logger.info("[WA-GATEWAY] Outbound message sent to %s: %s", clean_target, res_data)
                return res_data
            else:
                logger.warning(
                    "[WA-GATEWAY] Local gateway returned HTTP %d: %s",
                    response.status_code, response.text
                )
                return {"status": False, "error": response.text}
    except Exception as exc:
        logger.error(
            "[WA-GATEWAY] Failed to connect to WhatsApp Gateway at %s: %s",
            api_url, exc
        )
        return {"status": False, "error": str(exc)}


async def forward_revision_to_admin(
    customer_phone: str,
    customer_name: str,
    original_filename: str,
    revision_notes: str,
    local_file_path: Optional[str] = None
) -> Dict[str, Any]:
    """Escalate a customer's document revision or design request to Admin WhatsApp."""
    if not settings.ADMIN_WHATSAPP_NUMBER:
        logger.warning("[WA-GATEWAY] ADMIN_WHATSAPP_NUMBER is not set, skipping escalation.")
        return {"status": False, "reason": "ADMIN_WHATSAPP_NUMBER not configured"}

    admin_msg = (
        f"🚨 *PERMINTAAN EDIT / REVISI DOKUMEN* 🚨\n\n"
        f"👤 *Pelanggan:* {customer_name or 'Pelanggan'} (`{customer_phone}`)\n"
        f"📄 *File:* `{original_filename}`\n"
        f"📝 *Catatan Revisi dari Pelanggan:*\n\"{revision_notes}\"\n\n"
        f"⚠️ Mohon admin segera menghubungi pelanggan untuk koordinasi proses edit & cetak manual."
    )

    return await send_whatsapp_message(settings.ADMIN_WHATSAPP_NUMBER, admin_msg)
