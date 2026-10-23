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
Anda adalah "Hermes", AI Customer Service & Print Automation Specialist di Percetakan Anugrah Indah.
Tugas Anda adalah melayani pelanggan via WhatsApp dengan gaya bicara yang SANGAT ALAMI, RAMAH, DAN LUWES LAYAKNYA SEORANG MANUSIA (bukan bot/robot template yang kaku).

Sifat & Gaya Komunikasi:
- Berbicaralah seperti Customer Service profesional dan ramah di dunia nyata (hangat, solutif, menyapa nama pelanggan jika ada).
- Gunakan Bahasa Indonesia percakapan yang santun dan akrab (gunakan sapaan seperti "Kak", "Halo Kak Saenab!", "Bisa banget Kak", "Siap kami bantu ya!").
- Selalu sisipkan emoji WhatsApp yang hangat & relevan (seperti 😊, 🖨️, 📄, ✨, 🙏, 🚀).
- JANGAN gunakan template kalimat yang terlalu kaku atau formal birokratis. Berikan variasi kalimat yang hidup dan luwes!
- Kami melayani cetak file dokumen format PDF maupun Microsoft Word (.doc dan .docx).

Kategori Tarif Percetakan (Hanya Ada 3 Kategori Warna, TIDAK ADA Kategori Hitam-Putih):
1. Berwarna < 50%: Rp 2.000 / halaman (termasuk dokumen teks biasa atau hitam-putih standar)
2. Berwarna >= 50%: Rp 2.500 / halaman
3. Full Warna (Block/Cover/Foto): Rp 3.000 / halaman
PENTING: Percetakan kami TIDAK memiliki tarif Hitam-Putih terpisah. Semua dokumen teks biasa masuk ke kategori Berwarna < 50% (Rp 2.000/halaman). Jangan pernah menyebutkan tarif Hitam-Putih atau Rp 500 kepada pelanggan.

Tugas & Klasifikasi Tindakan:
1. NEW_DOCUMENT_SUMMARY:
   Jika menerima dokumen baru (PDF / Word):
   - Sambut dengan hangat dan berikan ringkasan singkat isi dokumen (1-2 kalimat).
   - Sampaikan hasil deteksi: Jumlah halaman, rincian warna (Warna < 50%, Warna >= 50%, Full Warna), ukuran kertas, dan estimasi biaya cetak bawaan (1 rangkap).
   - Tanyakan dengan ramah apakah ingin langsung dicetak sekarang atau ingin mengubah pengaturan (jumlah rangkap / halaman tertentu).

2. CONFIRM_PRINT:
   Jika pelanggan menyetujui / mengonfirmasi cetak (contoh: "Cetak", "Oke mas", "Gas print", "Ya cetak", "Lanjut"):
   - Berikan respon antusias bahwa dokumen sedang dikirim langsung ke printer fisik.
   - Beritahu pelanggan bahwa mereka bisa mengambil hasil cetakan begitu selesai.

3. REVISE_PRINT_SETTINGS:
   Jika pelanggan ingin mengubah parameter cetak (jumlah rangkap, rentang halaman tertentu):
   - Ekstrak: `updated_copies` (integer), `updated_page_range` (misal: "1-5", "1,3,5", "all").
   - Konfirmasi pembaruan tersebut dengan ramah dan tanyakan apakah siap dicetak.

4. REVISE_CONTENT_ADMIN:
   Jika pelanggan meminta perbaikan isi teks, ketikan, layout, atau desain:
   - Jelaskan bahwa editing isi dokumen akan dibantu langsung oleh Admin kami.
   - Buat `revision_notes_for_admin` dan informasikan bahwa Admin akan segera menghubungi.

5. CHAT:
   Jika pelanggan menyapa, bertanya format (misal Word/PDF), bertanya harga, jam buka, atau konsultasi umum:
   - Jawab secara luwes, akrab, informatif, dan tawarkan bantuan untuk mengirim file mereka.

6. CANCEL_PRINT:
   Jika pelanggan membatalkan cetak: Jawab dengan sopan dan ramah.

7. REQUEST_PDF:
   Jika pelanggan ingin mencetak tapi belum mengirim file: Ajak pelanggan untuk mengirimkan dokumen PDF atau Word mereka ke chat ini.
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

        color_breakdown: List[str] = []
        if pdf_info.color_low_count > 0:
            color_breakdown.append(f"{pdf_info.color_low_count} hal Berwarna < 50% (Rp {settings.PRICE_COLOR_LOW:,})")
        if pdf_info.color_high_count > 0:
            color_breakdown.append(f"{pdf_info.color_high_count} hal Berwarna ≥ 50% (Rp {settings.PRICE_COLOR_HIGH:,})")
        if pdf_info.color_full_count > 0:
            color_breakdown.append(f"{pdf_info.color_full_count} hal Full Warna (Rp {settings.PRICE_COLOR_FULL:,})")

        color_desc = ", ".join(color_breakdown) if color_breakdown else f"{pdf_info.total_pages} hal Berwarna < 50%"

        reply = (
            f"👋 Halo *{session.customer_name or 'Kak'}*, saya *Hermes* dari *{settings.STORE_NAME}*! 🖨️✨\n\n"
            f"📄 *Analisis Dokumen:*\n"
            f"• File: `{pdf_info.original_filename}`\n"
            f"• Ringkasan: {summary_text}\n"
            f"• Total Halaman: *{pdf_info.total_pages} halaman*\n"
            f"  └ Rincian: _{color_desc}_\n"
            f"• Kertas & Orientasi: *{pdf_info.paper_size}* ({pdf_info.orientation})\n\n"
            f"⚙️ *Rekomendasi Pengaturan Cetak:*\n"
            f"• Jumlah: *1 Rangkap*\n"
            f"• Mode: *Warna*\n"
            f"• Halaman: *Semua (1-{pdf_info.total_pages})*\n"
            f"💰 *Estimasi Biaya:* *Rp {pdf_info.estimated_price:,}*\n\n"
            f"❓ *Bagaimana Kak?*\n"
            f"• Balas *'Cetak'* untuk langsung mencetak dokumen ini.\n"
            f"• Atau sebutkan jika ingin ubah rangkap/halaman (misal: _'Cetak 2 rangkap'_ atau _'Hanya halaman 1 sampai 5'_).\n"
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

    customer_display = f"Kak {session.customer_name}" if session.customer_name else "Kak"

    # 6. Confirm Print
    confirm_keywords = [
        "cetak", "print", "oke", "ok", "gas", "siap", "lanjut", "ya",
        "setuju", "silakan", "printkan", "proses", "gaskeun"
    ]
    if any(k in msg for k in confirm_keywords):
        return HermesDecision(
            action=HermesAction.CONFIRM_PRINT,
            reply_message=(
                f"🚀 *Siap {customer_display}! Dokumen Anda sedang kami cetak.* 🖨️💨\n\n"
                f"📄 File: `{session.original_filename}`\n"
                f"• Jumlah: *{session.copies} Rangkap*\n"
                f"• Mode: *{session.color_mode.upper()}*\n"
                f"• Halaman: *{session.page_range}*\n\n"
                "Dokumen sudah dikirim ke printer fisik kami di gerai. "
                "Silakan diambil begitu selesai ya Kak. Terima kasih banyak sudah mencetak di toko kami! 🙏✨"
            ),
            reasoning="Rule-based heuristic: Customer confirmed printing."
        )

    # 7. Word / Format Inquiries
    if any(k in msg for k in ["word", "doc", "docx"]):
        return HermesDecision(
            action=HermesAction.CHAT,
            reply_message=(
                f"Bisa banget dong {customer_display}! 😊 Di *{settings.STORE_NAME}*, kami melayani cetak file *Microsoft Word* (`.doc` dan `.docx`) maupun *PDF* lho.\n\n"
                "Silakan langsung kirimkan dokumen Word Anda ke chat WhatsApp ini ya Kak, sistem kami akan langsung membaca dan menghitung biayanya! 📄🖨️✨"
            ),
            reasoning="Rule-based heuristic: Customer inquired about Word format."
        )

    # 8. General Chat
    return HermesDecision(
        action=HermesAction.CHAT,
        reply_message=(
            f"Halo {customer_display}! Senang bisa menyapa Anda di *{settings.STORE_NAME}*. 😊🖨️\n\n"
            f"Kami melayani jasa print dokumen cepat untuk format *PDF* maupun *Word* (`.docx`/`.doc`).\n\n"
            f"Tarif Cetak Dokumen:\n"
            f"• Berwarna < 50% (termasuk teks biasa): *Rp {settings.PRICE_COLOR_LOW:,}/halaman*\n"
            f"• Berwarna ≥ 50%: *Rp {settings.PRICE_COLOR_HIGH:,}/halaman*\n"
            f"• Full Warna: *Rp {settings.PRICE_COLOR_FULL:,}/halaman*\n\n"
            "Ada file yang ingin dicetak sekarang? Cukup kirimkan dokumen Anda ke chat ini ya! 📄✨"
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
    """Execute structured decision generation via OpenAI SDK with robust JSON parsing and fast fallback."""
    if not settings.OPENAI_API_KEY:
        return None

    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL,
            timeout=12.0,
            max_retries=1
        )

        full_prompt = (
            prompt +
            "\n\nPENTING: Kembalikan respons HANYA dalam JSON valid tunggal dengan struktur:\n"
            "{\n"
            '  "action": "NEW_DOCUMENT_SUMMARY" | "CONFIRM_PRINT" | "REVISE_PRINT_SETTINGS" | "REVISE_CONTENT_ADMIN" | "CHAT" | "CANCEL_PRINT" | "REQUEST_PDF",\n'
            '  "reply_message": "Tulis balasan WhatsApp yang ramah, sopan, luwes, dan natural seperti manusia melayani pelanggan secara langsung, lengkap dengan emoji yang relevan.",\n'
            '  "document_summary": "Ringkasan isi dokumen (jika ada dokumen)",\n'
            '  "updated_copies": 1,\n'
            '  "updated_color_mode": "color",\n'
            '  "updated_page_range": "all",\n'
            '  "revision_notes_for_admin": null,\n'
            '  "reasoning": "Alasan singkat tindakan"\n'
            "}"
        )

        response = await client.chat.completions.create(
            model=settings.AI_MODEL,
            messages=[
                {"role": "system", "content": HERMES_SYSTEM_PROMPT},
                {"role": "user", "content": full_prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
        )
        content = response.choices[0].message.content
        if content:
            content_clean = content.strip()
            if content_clean.startswith("```"):
                content_clean = re.sub(r"^```(?:json)?\s*", "", content_clean)
                content_clean = re.sub(r"\s*```$", "", content_clean)
            data = json.loads(content_clean)
            if isinstance(data, dict):
                # 1. Normalize action if model returns dictionary or variant string
                raw_action = data.get("action")
                if isinstance(raw_action, dict):
                    act_type = str(raw_action.get("type") or raw_action.get("action") or raw_action.get("name") or "").upper()
                    if any(k in act_type for k in ("PRINT", "CONFIRM")):
                        data["action"] = HermesAction.CONFIRM_PRINT.value
                    elif any(k in act_type for k in ("REVISE", "SETTING")):
                        data["action"] = HermesAction.REVISE_PRINT_SETTINGS.value
                    elif any(k in act_type for k in ("ADMIN", "EDIT")):
                        data["action"] = HermesAction.REVISE_CONTENT_ADMIN.value
                    elif any(k in act_type for k in ("CANCEL", "BATAL")):
                        data["action"] = HermesAction.CANCEL_PRINT.value
                    elif any(k in act_type for k in ("SUMMARY", "DOCUMENT", "DOC")):
                        data["action"] = HermesAction.NEW_DOCUMENT_SUMMARY.value
                    else:
                        data["action"] = HermesAction.CHAT.value

                    # Extract nested settings if present inside action dict
                    if "copies" in raw_action and not data.get("updated_copies"):
                        data["updated_copies"] = raw_action["copies"]
                    if "page_range" in raw_action and not data.get("updated_page_range"):
                        data["updated_page_range"] = raw_action["page_range"]
                elif isinstance(raw_action, str):
                    act_str = raw_action.upper().strip()
                    if act_str in [a.value for a in HermesAction]:
                        data["action"] = act_str
                    elif any(k in act_str for k in ("PRINT_DOCUMENT", "PRINT", "CONFIRM", "YES_PRINT")):
                        data["action"] = HermesAction.CONFIRM_PRINT.value
                    elif any(k in act_str for k in ("SETTING", "REVISE_SETTINGS")):
                        data["action"] = HermesAction.REVISE_PRINT_SETTINGS.value
                    elif any(k in act_str for k in ("ADMIN", "EDIT")):
                        data["action"] = HermesAction.REVISE_CONTENT_ADMIN.value
                    elif any(k in act_str for k in ("CANCEL", "BATAL")):
                        data["action"] = HermesAction.CANCEL_PRINT.value
                    elif any(k in act_str for k in ("SUMMARY", "NEW_DOC")):
                        data["action"] = HermesAction.NEW_DOCUMENT_SUMMARY.value
                    elif any(k in act_str for k in ("REQUEST", "NEED_PDF")):
                        data["action"] = HermesAction.REQUEST_PDF.value
                    else:
                        data["action"] = HermesAction.CHAT.value
                else:
                    data["action"] = HermesAction.CHAT.value

                # 2. Normalize reply_message if keyed differently
                if not data.get("reply_message"):
                    # Check if action dict had a message
                    if isinstance(raw_action, dict):
                        for k in ("message", "reply", "text", "response"):
                            if raw_action.get(k) and isinstance(raw_action[k], str):
                                data["reply_message"] = raw_action[k]
                                break

                    # Check other top-level keys
                    if not data.get("reply_message"):
                        for k in ("response", "message", "reply", "text", "content"):
                            if data.get(k) and isinstance(data[k], str) and len(data[k]) > 3:
                                data["reply_message"] = data[k]
                                break

                    # Last fallback for reply_message
                    if not data.get("reply_message"):
                        for k, v in data.items():
                            if k not in ("action", "reasoning", "reason", "updated_copies", "updated_color_mode", "updated_page_range") and isinstance(v, str) and len(v) > 5:
                                data["reply_message"] = v
                                break

                # Ensure reply_message is at least a string
                if not data.get("reply_message"):
                    data["reply_message"] = "Siap Kak, pesan Anda telah kami terima! Ada yang bisa kami bantu lagi? 😊"

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
            f"- Halaman Warna < 50% ({pdf_info.color_low_count}): {pdf_info.color_low_pages}\n"
            f"- Halaman Warna >= 50% ({pdf_info.color_high_count}): {pdf_info.color_high_pages}\n"
            f"- Halaman Full Warna ({pdf_info.color_full_count}): {pdf_info.color_full_pages}\n"
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
            f"- Pengaturan Saat Ini: {session.copies} Rangkap, Halaman: {session.page_range}\n"
            f"- Estimasi Biaya: Rp {session.estimated_price}"
        )

    prompt = (
        f"KONDISI PERCAKAPAN SAAT INI:\n"
        f"• Nama Toko Percetakan: {settings.STORE_NAME}\n"
        f"• Kategori Tarif Cetak (HANYA ADA 3 KATEGORI, TIDAK ADA KATEGORI HITAM-PUTIH):\n"
        f"  1. Berwarna < 50%: Rp {settings.PRICE_COLOR_LOW}/lembar\n"
        f"  2. Berwarna >= 50%: Rp {settings.PRICE_COLOR_HIGH}/lembar\n"
        f"  3. Full Warna: Rp {settings.PRICE_COLOR_FULL}/lembar\n"
        f"  (PENTING: Jangan pernah sebutkan tarif Hitam-Putih atau Rp 500. Dokumen biasa/teks masuk ke Berwarna < 50%).\n"
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
