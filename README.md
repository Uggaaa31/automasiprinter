# 🖨️ Hermes Print Automation

> **Production-Ready WhatsApp-Based Document Print Automation System**  
> Dikendalikan oleh AI Agent **"Hermes"** dengan integrasi **Baileys WhatsApp Gateway Lokal (100% Gratis & Mandiri)**, **PyMuPDF**, dan **Spooler Cetak Fisik** (SumatraPDF di Windows / CUPS `lp` di Linux).

---

## 📑 Daftar Isi
1. [Arsitektur & Alur Kerja Sistem](#-arsitektur--alur-kerja-sistem)
2. [Fitur Unggulan](#-fitur-unggulan)
3. [Struktur Direktori](#-struktur-direktori)
4. [Persyaratan Sistem](#-persyaratan-sistem)
5. [Panduan Instalasi & Setup Cepat](#-panduan-instalasi--setup-cepat)
6. [Konfigurasi Environment (.env)](#-konfigurasi-environment-env)
7. [Panduan Printer Fisik & SumatraPDF](#-panduan-printer-fisik--sumatrapdf)
8. [Menghubungkan WhatsApp Toko (Baileys)](#-menghubungkan-whatsapp-toko-baileys)
9. [Menjalankan Sistem & Verifikasi](#-menjalankan-sistem--verifikasi)
10. [Dokumentasi API Endpoints](#-dokumentasi-api-endpoints)

---

## 🏛️ Arsitektur & Alur Kerja Sistem

Sistem ini berjalan langsung pada PC lokal yang terhubung kabel USB ke mesin pencetak fisik (misal: Epson L5290, L3110, Canon G2010, HP LaserJet).

```text
 ┌──────────────────────┐
 │   Pelanggan (WA)     │ 
 └──────────┬───────────┘
            │ 1. Kirim Pesan Teks / File PDF langsung di Chat
            ▼
 ┌──────────────────────────────────────────────────────────────┐
 │       Hermes WhatsApp Gateway Lokal (Baileys Node.js)        │
 │  • Berjalan di PC lokal (port 3001)                          │
 │  • 100% Gratis, tanpa langganan, tanpa batasan file PDF      │
 │  • Otomatis download file PDF ke storage/documents/          │
 └──────────┬───────────────────────────────────────────────────┘
            │ 2. Forward Event ke FastAPI (POST /webhook/wa)
            ▼
 ┌──────────────────────────────────────────────────────────────┐
 │                  FastAPI Application (Local PC)              │
 │                                                              │
 │  [pdf_service.py]                                            │
 │  ├── Analisis PyMuPDF & NumPy:                               │
 │  │   • Halaman total, orientasi (Potret/Lanskap), ukuran     │
 │  │   • Klasifikasi 3 Tier Warna (Warna < 50%, >= 50%, Full)  │
 │  │   • Ekstraksi teks & hitung estimasi biaya cetak          │
 │                                                              │
 │  [database.py]                                               │
 │  └── SQLite State Management (Multi-turn per nomor WA)       │
 │                                                              │
 │  [hermes_agent.py] (AI Agent "Hermes")                       │
 │  └── LLM Structured Output (DeepSeek / Gemini / OpenAI)      │
 │      • NEW_DOCUMENT_SUMMARY ──> Ringkas isi & rincian biaya  │
 │      • CONFIRM_PRINT        ──> Setujui & cetak otomatis     │
 │      • REVISE_PRINT_SETTINGS──> Perbarui rangkap/halaman     │
 │      • REVISE_CONTENT_ADMIN ──> Alihkan ke WA Admin          │
 └──────────┬────────────────────────────────────┬──────────────┘
            │                                    │
    (Jika Disetujui)                   (Jika Minta Edit Desain/Isi)
            │                                    │
            ▼                                    ▼
 ┌──────────────────────┐               ┌──────────────────────┐
 │  printer_service.py  │               │  whatsapp_service.py │
 │  (SumatraPDF CLI)    │               │ (Forward ke Admin)   │
 └──────────┬───────────┘               └──────────┬───────────┘
            │ Eksekusi CLI Spooler                 │ Notifikasi WhatsApp
            ▼                                      ▼
 ┌──────────────────────┐               ┌──────────────────────┐
 │ Printer Fisik (EPSON)│               │  WhatsApp Admin HP   │
 └──────────────────────┘               └──────────────────────┘
```

---

## 🌟 Fitur Unggulan

* **Gateway WhatsApp Mandiri (Baileys):** 
  - Tidak memerlukan layanan pihak ketiga berbayar.
  - Pelanggan dapat mengirim file PDF ukuran apa pun langsung di ruang chat WhatsApp.
  - Berjalan lokal tanpa perlu tunnel publik (bebas Cloudflare/Ngrok/localhost.run).
* **3 Kategori Tarif Warna (Tanpa Kategori Hitam-Putih):**
  - Kategori 1: Berwarna < 50% (termasuk halaman teks biasa) = **Rp 2.000 / halaman**.
  - Kategori 2: Berwarna ≥ 50% = **Rp 2.500 / halaman**.
  - Kategori 3: Full Warna (poster/foto/blok warna tebal) = **Rp 3.000 / halaman**.
* **Eksekusi Cetak Fisik Senyap (*Silent Printing*):**
  - Mengirim berkas cetak langsung ke printer fisik melalui CLI SumatraPDF (`-print-to` dan `-print-settings`).
* **Multi-Turn AI Conversation Memory:**
  - Database SQLite lokal melacak sesi tiap pelanggan: status pesanan, jumlah rangkap, halaman terpilih, dan estimasi biaya.
* **Eskalasi Revisi Konten / Desain ke Admin:**
  - Jika pelanggan meminta revisi ketik/desain, berkas dan catatan revisi diteruskan ke nomor WhatsApp Admin.

---

## 📁 Struktur Direktori

```text
hermes-print-automation/
├── app/
│   ├── config.py               # Pydantic Settings & environment variables
│   ├── database.py             # SQLite WAL session & conversation history
│   ├── main.py                 # FastAPI app & Webhook receiver (/webhook/wa)
│   ├── models.py               # Pydantic schema models
│   └── services/
│       ├── hermes_agent.py     # AI Turn Decision engine & rules
│       ├── pdf_service.py      # PyMuPDF color & page classifier
│       ├── printer_service.py  # SumatraPDF CLI physical printer spooler
│       └── whatsapp_service.py # Outbound WhatsApp gateway client
├── wa-gateway/                 # Baileys WhatsApp Gateway (Node.js)
│   ├── index.js                # WebSocket WhatsApp connection & REST API
│   └── package.json            # Baileys & Express dependencies
├── storage/                    # SQLite database & customer documents
├── start_hermes.bat            # Script 1-klik jalankan Server + WhatsApp Gateway
├── start_wa_gateway.bat        # Script jalankan WhatsApp Gateway mandiri
├── setup_pc_baru.bat           # Installer otomatis untuk PC baru
├── test_system.py              # Suite verifikasi sistem otomatis
└── .env                        # Konfigurasi aktif toko
```

---

## ⚙️ Konfigurasi Environment (`.env`)

| Variabel | Deskripsi | Nilai Contoh |
| :--- | :--- | :--- |
| `BAILEYS_API_URL` | URL REST API WhatsApp Gateway lokal | `http://127.0.0.1:3001` |
| `ADMIN_WHATSAPP_NUMBER`| Nomor WA Admin untuk eskalasi revisi desain | `6282313935096` |
| `AI_PROVIDER` | Provider AI (`deepseek`, `gemini`, atau `openai`) | `deepseek` |
| `OPENAI_BASE_URL` | Base URL Proxy AI (9Router, Ollama, OpenAI) | `http://localhost:20128/v1` |
| `OPENAI_API_KEY` | API Key OpenAI atau Proxy 9Router | `sk-e1fd...` |
| `AI_MODEL` | Nama model AI yang digunakan | `Kenari/deepseek-v4-1-flash:free` |
| `PRINTER_OS` | Sistem Operasi PC host (`windows` / `linux`) | `windows` |
| `PRINTER_NAME` | Nama printer fisik di Windows (kosongkan = default) | `EPSON L5290 Series (Copy 1)` |
| `SUMATRAPDF_PATH` | Lokasi file `SumatraPDF.exe` | `C:\Users\lenov\AppData\Local\SumatraPDF\SumatraPDF.exe` |
| `PRINT_SIMULATION_MODE` | Mode simulasi cetak (`true` = uji coba, `false` = cetak fisik) | `false` |
| `PRICE_COLOR_LOW` | Tarif cetak Berwarna < 50% per halaman (IDR) | `2000` |
| `PRICE_COLOR_HIGH`| Tarif cetak Berwarna ≥ 50% per halaman (IDR) | `2500` |
| `PRICE_COLOR_FULL`| Tarif cetak Full Warna per halaman (IDR) | `3000` |
| `STORE_NAME` | Nama Toko / Usaha Percetakan Anda | `Percetakan Anugrah Indah` |

---

## 📱 Menghubungkan WhatsApp Toko (Baileys)

1. Jalankan **`start_hermes.bat`** (atau **`start_wa_gateway.bat`**).
2. Di jendela terminal gateway, akan muncul gambar **QR Code**.
3. Buka WhatsApp di HP Toko -> **Perangkat Tertaut (Linked Devices)** -> **Tautkan Perangkat** -> Scan QR.
4. Sesi login akan tersimpan permanen di `storage/wa_session/`. Selanjutnya sistem akan tersambung otomatis tanpa scan ulang.

---

## 🧪 Verifikasi Sistem

Jalankan pengujian end-to-end tanpa memerlukan printer fisik:
```bash
python test_system.py
```

---

## 📡 API Endpoints

### 1. `POST /webhook/wa`
Endpoint penerima pesan & file PDF dari WhatsApp Gateway Baileys.
- **Payload Utama:**
  ```json
  {
    "sender": "6281341185188",
    "name": "Uggaaa",
    "message": "Tolong cetak ya",
    "local_file_path": "D:\\Automasi Print\\hermes-print-automation\\storage\\documents\\dokumen.pdf",
    "filename": "dokumen.pdf",
    "source": "baileys"
  }
  ```

### 2. `GET /health`
Mengecek status kesehatan server, ketersediaan database, dan daftar printer fisik yang terdeteksi di Windows.
