"""Hermes Print Automation - AI Agent "Hermes" Service.

Implements the conversational intelligence, multi-turn reasoning, and deterministic
structured outputs for print workflows using Google GenAI SDK and OpenAI.
Includes robust rule-based heuristic fallback if LLM credentials are not configured.
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional

from app.config import settings
from app.models import HermesAction, HermesDecision, PDFAnalysisResult, SessionData

logger = logging.getLogger("hermes.agent")

HERMES_SYSTEM_PROMPT = """
Anda adalah "Hermes", AI Customer Service & Print Automation Specialist yang bertugas melayani pelanggan percetakan secara otomatis via WhatsApp.
Sifat & Gaya Komunikasi Anda:
- Sangat sopan, ramah, profesional, dan solutif (Bahasa Indonesia yang baik dan santun).
- Menggunakan formatting WhatsApp standar (*tebal*, _miring_, `monospace`, bullet points, dan emoji relevan seperti 🖨️, 📄, ⚙️, ✨, 🙏).
- Jangan berbelit-belit, berikan informasi yang jelas dan to the point.

Tugas Utama Anda:
1. NEW_DOCUMENT_SUMMARY:
   Jika menerima dokumen PDF baru:
   - Berikan ringkasan singkat padat (1-3 kalimat) mengenai isi dokumen (misal: "Dokumen ini adalah draf proposal skripsi...", "File ini berupa CV/Resume...", atau "Dokumen pindaian/scan...").
   - Sampaikan hasil deteksi: Jumlah halaman, halaman berwarna vs hitam-putih, ukuran kertas, dan orientasi.
   - Sampaikan rincian pengaturan cetak bawaan (default: 1 rangkap, mode warna sesuai deteksi, seluruh halaman).
   - Cantumkan estimasi total biaya cetak.
   - Tanyakan dengan ramah apakah pelanggan ingin langsung mencetak dokumen tersebut, atau ingin mengubah pengaturan cetak, atau perlu perbaikan/revisi isi/desain dokumen.

2. CONFIRM_PRINT:
   Jika pelanggan menyetujui cetak (contoh: "Cetak sekarang", "Oke mas", "Gas print", "Ya tolong dicetak", "Siap", "Konfirmasi"):
   - Berikan pesan bahwa dokumen sedang diproses dan dikirim langsung ke mesin printer.
   - Beritahu pelanggan bahwa mereka dapat mengambil dokumen setelah proses selesai.

3. REVISE_PRINT_SETTINGS:
   Jika pelanggan ingin mengubah parameter cetak (jumlah rangkap, mode warna hitam-putih/warna, rentang halaman):
   - Ekstrak nilai baru: `updated_copies` (integer), `updated_color_mode` ("bw", "color", atau "auto"), `updated_page_range` (misal: "1-5", "1,3,5", "all").
   - Tampilkan pembaruan pengaturan tersebut dan tanyakan konfirmasi akhir untuk mencetak.

4. REVISE_CONTENT_ADMIN:
   Jika pelanggan meminta perubahan/editing isi teks, kesalahan ketik, tata letak/layout, atau desain dokumen:
   - Sistem ini mencetak secara otomatis, sehingga jika ada permintaan edit isi dokumen, tugas HARUS dialihkan ke Admin manusia.
   - Buat `revision_notes_for_admin` yang merangkum apa saja yang diminta pelanggan untuk diperbaiki.
   - Berikan pesan sopan kepada pelanggan bahwa permintaan revisi isi/desain dokumen telah diteruskan ke nomor WhatsApp Admin, dan Admin kami akan segera menghubungi untuk proses editing serta cetak manual.

5. CHAT:
   Jika pelanggan sekadar menyapa, bertanya harga, jam buka percetakan, atau konsultasi umum:
   - Jawab dengan ramah dan informatif.

6. CANCEL_PRINT:
   Jika pelanggan membatalkan proses cetak:
   - Konfirmasi pembatalan dengan sopan dan siap membantu jika ada dokumen lain.

7. REQUEST_PDF:
   Jika pelanggan ingin mencetak tetapi belum melampirkan file PDF:
   - Minta pelanggan dengan santun untuk mengirimkan file dokumen dalam format PDF.
"""


def _build_rule_based_decision(
    user_message: str,
    session: SessionData,
    pdf_info: Optional[PDFAnalysisResult] = None
) -> HermesDecision:
    """Deterministic heuristic fallback when LLM API keys are not available."""
    msg = user_message.lower().strip()
    has_active_doc = bool(session.current_file_path or pdf_info)

    # 1. New document upload
    if pdf_info:
        summary_text = (
            f"Dokumen `{pdf_info.original_filename}` telah kami terima dan periksa."
        )
        if "skripsi" in pdf_info.original_filename.lower() or "skripsi" in pdf_info.text_excerpt.lower():
            summary_text = "Dokumen ini merupakan berkas akademik / skripsi."
        elif "cv" in pdf_info.original_filename.lower() or "resume" in pdf_info.text_excerpt.lower():
            summary_text = "Dokumen ini merupakan berkas CV / Curriculum Vitae."
        elif "laporan" in pdf_info.original_filename.lower() or "laporan" in pdf_info.text_excerpt.lower():
            summary_text = "Dokumen ini merupakan berkas laporan resmi."

        color_desc = (
            f"{pdf_info.color_pages_count} halaman berwarna, {pdf_info.bw_pages_count} hitam-putih"
            if pdf_info.is_color_document
            else "Semua halaman Hitam-Putih (Grayscale)"
        )

        reply = (
            f"👋 Halo *{session.customer_name or 'Kak'}*, saya *Hermes* dari *{settings.STORE_NAME}*! 🖨️✨\n\n"
            f"📄 *Analisis Dokumen:*\n"
            f"• File: `{pdf_info.original_filename}`\n"
            f"• Ringkasan: {summary_text}\n"
            f"• Total Halaman: *{pdf_info.total_pages} halaman* ({color_desc})\n"
            f"• Kertas & Orientasi: *{pdf_info.paper_size}* ({pdf_info.orientation})\n\n"
            f"⚙️ *Rekomendasi Pengaturan Cetak:*\n"
            f"• Jumlah: *1 Rangkap*\n"
            f"• Mode: *{'Warna Otomatis' if pdf_info.is_color_document else 'Hitam-Putih'}*\n"
            f"• Halaman: *Semua (1-{pdf_info.total_pages})*\n"
            f"💰 *Estimasi Biaya:* *Rp {pdf_info.estimated_price:,}*\n\n"
            f"❓ *Bagaimana Kak?*\n"
            f"• Balas *'Cetak'* untuk langsung mencetak dokumen ini.\n"
            f"• Atau sebutkan jika ingin ubah rangkap/warna/halaman (misal: _'Cetak 2 rangkap hitam putih'_).\n"
            f"• Jika butuh edit isi/desain dokumen, silakan tulis revisinya agar dibantu oleh Admin kami. 🙏"
        )
        return HermesDecision(
            action=HermesAction.NEW_DOCUMENT_SUMMARY,
            reply_message=reply,
            document_summary=summary_text,
            reasoning="Rule-based heuristic: New PDF document uploaded."
        )

    # 2. Cancel
    if any(k in msg for k in ["batal", "cancel", "gak jadi", "nggak jadi", "tidak jadi"]):
        return HermesDecision(
            action=HermesAction.CANCEL_PRINT,
            reply_message=(
                "Baik Kak, pesanan cetak dokumen Anda telah *dibatalkan*. 👍\n"
                "Jika nanti butuh mencetak dokumen lainnya, cukup kirimkan file PDF ke sini ya. Terima kasih! 🙏"
            ),
            reasoning="Rule-based heuristic: User requested cancellation."
        )

    # 3. Request PDF if user asks to print without active file
    if not has_active_doc:
        return HermesDecision(
            action=HermesAction.REQUEST_PDF,
            reply_message=(
                f"👋 Halo Kak! Saya *Hermes* dari *{settings.STORE_NAME}* 🖨️✨\n\n"
                "Silakan kirimkan file dokumen Anda dalam format *PDF* ke chat WhatsApp ini. "
                "Sistem kami akan otomatis membaca dokumen, menghitung halaman, dan mencetaknya langsung! 📄🚀"
            ),
            reasoning="Rule-based heuristic: No active document found."
        )

    # 4. Content / Design Revision (Escalate to Admin)
    content_revision_keywords = [
        "edit", "revisi", "ubah isi", "ganti judul", "salah ketik", "typo",
        "format ulang", "rapikan", "desain", "admin", "tolong perbaiki"
    ]
    if any(k in msg for k in content_revision_keywords):
        return HermesDecision(
            action=HermesAction.REVISE_CONTENT_ADMIN,
            reply_message=(
                "📌 *Permintaan Revisi Isi / Desain Diteruskan ke Admin* 👨‍💼\n\n"
                "Karena dokumen Anda memerlukan perbaikan/editing isi sebelum dicetak, "
                "file dan catatan Anda telah kami teruskan langsung ke nomor WhatsApp Admin kami.\n\n"
                "Admin kami akan segera menghubungi Anda untuk koordinasi editing dan proses cetak manual. "
                "Mohon ditunggu sebentar ya Kak, terima kasih atas kesabarannya! 🙏✨"
            ),
            revision_notes_for_admin=user_message,
            reasoning="Rule-based heuristic: Customer requested text/design editing."
        )

    # 5. Revise Print Settings (copies, color, pages)
    setting_change = False
    updated_copies = None
    updated_color_mode = None
    updated_page_range = None

    # Detect copies (e.g., "2 rangkap", "3 copy", "5 lembar", "cetak 2x")
    copy_match = re.search(r"(\d+)\s*(rangkap|copy|kopi|lembar|eks|x)", msg)
    if copy_match:
        updated_copies = int(copy_match.group(1))
        setting_change = True

    # Detect color mode
    if any(k in msg for k in ["hitam putih", "hitam-putih", "bw", "monochrome", "grayscale"]):
        updated_color_mode = "bw"
        setting_change = True
    elif any(k in msg for k in ["warna", "full color", "colour"]):
        updated_color_mode = "color"
        setting_change = True

    # Detect page range (e.g., "halaman 1 sampai 5", "hal 1-10", "halaman 1,3,5")
    page_range_match = re.search(r"(?:halaman|hal)\s*([0-9\-,;\s]+)", msg)
    if page_range_match:
        updated_page_range = page_range_match.group(1).strip()
        setting_change = True

    if setting_change:
        copies_text = f"{updated_copies} Rangkap" if updated_copies else f"{session.copies} Rangkap"
        color_text = (
            "Hitam-Putih" if (updated_color_mode == "bw" or (not updated_color_mode and session.color_mode == "bw"))
            else "Warna"
        )
        range_text = updated_page_range or session.page_range

        reply = (
            "⚙️ *Pengaturan Cetak Telah Diperbarui:* 🔄\n\n"
            f"📄 Dokumen: `{session.original_filename}`\n"
            f"• Jumlah: *{copies_text}*\n"
            f"• Mode: *{color_text}*\n"
            f"• Halaman: *{range_text}*\n\n"
            "Ketik *'Cetak'* jika sudah sesuai untuk langsung memproses ke printer! 🖨️"
        )
        return HermesDecision(
            action=HermesAction.REVISE_PRINT_SETTINGS,
            reply_message=reply,
            updated_copies=updated_copies,
            updated_color_mode=updated_color_mode,
            updated_page_range=updated_page_range,
            reasoning="Rule-based heuristic: Print settings revised."
        )

    # 6. Confirm Print
    confirm_keywords = [
        "cetak", "print", "oke", "ok", "gas", "siap", "lanjut", "ya",
        "setuju", "silakan", "printkan", "proses", "gaskeun"
    ]
    if any(k in msg for k in confirm_keywords):
        return HermesDecision(
            action=HermesAction.CONFIRM_PRINT,
            reply_message=(
                f"🚀 *Siap Kak! Dokumen Anda sedang dicetak otomatis.* 🖨️💨\n\n"
                f"📄 File: `{session.original_filename}`\n"
                f"• Jumlah: *{session.copies} Rangkap*\n"
                f"• Mode: *{session.color_mode.upper()}*\n"
                f"• Halaman: *{session.page_range}*\n\n"
                "Dokumen sedang dikeluarkan oleh printer fisik kami di gerai. "
                "Silakan diambil begitu selesai ya Kak. Terima kasih banyak telah menggunakan layanan kami! 🙏✨"
            ),
            reasoning="Rule-based heuristic: Customer confirmed printing."
        )

    # 7. General Chat
    return HermesDecision(
        action=HermesAction.CHAT,
        reply_message=(
            f"Halo Kak! Kami siap membantu mencetak dokumen Anda di *{settings.STORE_NAME}*. 🖨️\n"
            f"• Tarif Hitam-Putih: Rp {settings.PRICE_PER_PAGE_BW:,}/halaman\n"
            f"• Tarif Warna: Rp {settings.PRICE_PER_PAGE_COLOR:,}/halaman\n\n"
            "Ada file yang ingin dicetak sekarang? Cukup kirimkan dokumen PDF-nya ke sini ya! 📄"
        ),
        reasoning="Rule-based heuristic: General chat."
    )


async def call_gemini_structured(prompt: str) -> Optional[HermesDecision]:
    """Execute structured decision generation via Google GenAI SDK (google-genai)."""
    if not settings.GEMINI_API_KEY:
        return None

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        response = client.models.generate_content(
            model=settings.AI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=HermesDecision,
                system_instruction=HERMES_SYSTEM_PROMPT,
                temperature=0.2,
            )
        )
        if response and response.text:
            data = json.loads(response.text)
            return HermesDecision(**data)
    except Exception as exc:
        logger.warning("[HERMES] google-genai call failed: %s. Falling back to alternative...", exc)
        return None


async def call_openai_structured(prompt: str) -> Optional[HermesDecision]:
    """Execute structured decision generation via OpenAI SDK."""
    if not settings.OPENAI_API_KEY:
        return None

    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL
        )
        response = await client.chat.completions.create(
            model=settings.AI_MODEL,
            messages=[
                {"role": "system", "content": HERMES_SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        content = response.choices[0].message.content
        if content:
            content_clean = content.strip()
            if content_clean.startswith("```"):
                content_clean = re.sub(r"^```(?:json)?\s*", "", content_clean)
                content_clean = re.sub(r"\s*```$", "", content_clean)
            data = json.loads(content_clean)
            if isinstance(data, dict):
                if not any(k in data for k in ("reply_message", "response", "message", "reply", "text")):
                    for k, v in data.items():
                        if k not in ("action", "reasoning", "reason") and isinstance(v, str) and len(v) > 5:
                            data["reply_message"] = v
                            break
            return HermesDecision(**data)
    except Exception as exc:
        logger.warning("[HERMES] OpenAI/Proxy call failed: %s", exc)
        return None


async def process_user_turn(
    user_message: str,
    session: SessionData,
    conversation_history: List[Dict[str, str]],
    pdf_info: Optional[PDFAnalysisResult] = None
) -> HermesDecision:
    """Analyze incoming user input and generate a deterministic HermesDecision."""
    # Build prompt context
    history_lines = []
    for turn in conversation_history[-6:]:
        history_lines.append(f"{turn['role'].upper()}: {turn['message']}")
    history_context = "\n".join(history_lines) if history_lines else "Tidak ada riwayat percakapan sebelumnya."

    doc_info_text = "Tidak ada dokumen aktif saat ini."
    if pdf_info:
        doc_info_text = (
            f"DOKUMEN BARU DIUNGGAH:\n"
            f"- Nama File: {pdf_info.original_filename}\n"
            f"- Total Halaman: {pdf_info.total_pages}\n"
            f"- Halaman Berwarna ({pdf_info.color_pages_count}): {pdf_info.color_pages_list}\n"
            f"- Halaman Hitam-Putih ({pdf_info.bw_pages_count}): {pdf_info.bw_pages_list}\n"
            f"- Ukuran Kertas: {pdf_info.paper_size}\n"
            f"- Orientasi: {pdf_info.orientation}\n"
            f"- Estimasi Biaya Bawaan: Rp {pdf_info.estimated_price}\n"
            f"- Cuplikan Isi Teks Dokumen:\n{pdf_info.text_excerpt}"
        )
    elif session.current_file_path:
        doc_info_text = (
            f"DOKUMEN AKTIF SAAT INI:\n"
            f"- File: {session.original_filename}\n"
            f"- Ringkasan Sebelumnya: {session.document_summary}\n"
            f"- Pengaturan Saat Ini: {session.copies} Rangkap, Mode: {session.color_mode}, Halaman: {session.page_range}\n"
            f"- Estimasi Biaya: Rp {session.estimated_price}"
        )

    prompt = (
        f"KONDISI PERCAKAPAN SAAT INI:\n"
        f"• Nama Toko Percetakan: {settings.STORE_NAME}\n"
        f"• Tarif BW: Rp {settings.PRICE_PER_PAGE_BW}/lembar, Tarif Warna: Rp {settings.PRICE_PER_PAGE_COLOR}/lembar\n"
        f"• Nama Pelanggan: {session.customer_name or 'Pelanggan'}\n"
        f"• Status Sesi: {session.session_status.value}\n\n"
        f"INFORMASI DOKUMEN:\n{doc_info_text}\n\n"
        f"RIWAYAT PERCAKAPAN:\n{history_context}\n\n"
        f"PESAN TERBARU PELANGGAN:\n\"{user_message}\"\n\n"
        f"Tentukan tindakan (HermesAction) dan hasilkan JSON terstruktur sesuai skema HermesDecision."
    )

    decision: Optional[HermesDecision] = None

    # Route based purely on AI_PROVIDER in .env
    provider = settings.AI_PROVIDER.lower().strip()
    if provider == "gemini":
        decision = await call_gemini_structured(prompt)
    else:
        # Any other provider (e.g. deepseek, openai, 9router, ollama, local proxy)
        # connects using OPENAI_BASE_URL, OPENAI_API_KEY, and AI_MODEL from .env
        decision = await call_openai_structured(prompt)

    # Fallback to robust deterministic rule-based engine if LLM didn't return or isn't configured
    if not decision:
        logger.info("[HERMES] Using deterministic rule-based logic for turn decision.")
        decision = _build_rule_based_decision(user_message, session, pdf_info)

    # If a new PDF was uploaded, always present document summary & confirmation first
    if pdf_info and decision:
        decision.action = HermesAction.NEW_DOCUMENT_SUMMARY

    return decision
