# 🖨️ Hermes Print Automation

> **Production-Ready WhatsApp-Based Document Print Automation System**  
> Sistem otomatisasi percetakan dokumen berbasis WhatsApp yang dikendalikan oleh AI Agent **"Hermes"**. Terintegrasi penuh dengan **WhatsApp Gateway Lokal (Baileys Node.js - 100% Mandiri & Gratis)**, **PyMuPDF**, **Konverter Dokumen Word (.docx/.doc)**, dan **Spooler Printer Fisik** (SumatraPDF di Windows).

---

## 📑 Daftar Isi
1. [Arsitektur & Alur Kerja Sistem](#-arsitektur--alur-kerja-sistem)
2. [Fitur Unggulan](#-fitur-unggulan)
3. [Format Dokumen yang Didukung](#-format-dokumen-yang-didukung)
4. [Struktur Direktori Proyek](#-struktur-direktori-proyek)
5. [Konfigurasi Environment (.env)](#-konfigurasi-environment-env)
6. [Panduan Instalasi & Menjalankan Sistem](#-panduan-instalasi--menjalankan-sistem)
7. [Menghubungkan WhatsApp Toko (Baileys)](#-menghubungkan-whatsapp-toko-baileys)
8. [Panduan Printer Fisik (EPSON / SumatraPDF)](#-panduan-printer-fisik-epson--sumatrapdf)
9. [Verifikasi Sistem Otomatis](#-verifikasi-sistem-otomatis)
10. [Dokumentasi API Endpoints](#-dokumentasi-api-endpoints)

---

## 🏛️ Arsitektur & Alur Kerja Sistem

Sistem ini berjalan langsung pada PC lokal kasir/operator yang terhubung kabel USB ke mesin pencetak fisik (contoh: **EPSON L5290**, L3110, Canon G2010, HP LaserJet).

```text
 ┌──────────────────────────────────────────────┐
 │             Pelanggan (WhatsApp)             │ 
 └──────────────────────┬───────────────────────┘
                        │ 1. Kirim Pesan Teks / Berkas PDF / Word (.docx/.doc)
                        ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │           Hermes WhatsApp Gateway Lokal (Baileys Node.js)             │
 │  • Berjalan lokal di port 3001 (Outbound REST API + WhatsApp Socket)   │
 │  • 100% Gratis, tanpa kuota, tanpa batasan ukuran lampiran             │
 │  • Mendukung nomor standar (@s.whatsapp.net) & WhatsApp LID (@lid)    │
 │  • Otomatis mengunduh berkas ke storage/documents/                     │
 └──────────────────────┬─────────────────────────────────────────────────┘
                        │ 2. Forward Webhook (POST http://127.0.0.1:8000/webhook/wa)
                        ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │                      FastAPI Application Engine                        │
 │                                                                        │
 │  [pdf_service.py]                                                      │
 │  ├── Auto-Convert Word: .docx / .doc ──> PDF (Microsoft Word COM)      │
 │  └── Analisis PyMuPDF & NumPy:                                         │
 │      • Hitung total halaman, orientasi (Potret/Lanskap), ukuran kertas │
 │      • Deteksi cakupan warna piksel (3 Tier Warna)                     │
 │      • Hitung estimasi total biaya cetak secara presisi                │
 │                                                                        │
 │  [database.py]                                                         │
 │  └── SQLite State Management (Multi-turn memory riwayat chat per nomor)│
 │                                                                        │
 │  [hermes_agent.py] (AI Agent "Hermes")                                 │
 │  └── LLM Structured Decision (Kenari/beam-1-0:free / Gemini / DeepSeek)│
 │      • Respon luwes, ramah, dan manusiawi (human-like CS) + emoji      │
 │      • NEW_DOCUMENT_SUMMARY ──> Ringkas isi & rincian biaya         │
 │      • CONFIRM_PRINT        ──> Eksekusi perintah cetak langsung       │
 │      • REVISE_PRINT_SETTINGS──> Ubah rangkap atau rentang halaman      │
 │      • REVISE_CONTENT_ADMIN ──> Teruskan permintaan revisi ke Admin    │
 │      • CHAT                 ──> Konsultasi tarif, format, info toko    │
 └──────────────────────┬───────────────────────────────────┬─────────────┘
                        │                                   │
                (Jika Disetujui)                  (Jika Minta Edit Konten)
                        │                                   │
                        ▼                                   ▼
 ┌──────────────────────────────────────┐  ┌──────────────────────────────┐
 │         printer_service.py           │  │     whatsapp_service.py      │
 │  Eksekusi Spooler Silent Printing    │  │  Kirim Pesan Notifikasi &    │
 │  SumatraPDF CLI (-print-to EPSON)    │  │  Rangkuman Revisi ke WA Admin│
 └──────────────────────┬───────────────┘  └──────────────┬───────────────┘
                        │                                 │
                        ▼                                 ▼
 ┌──────────────────────────────────────┐  ┌──────────────────────────────┐
 │     Mesin Printer Fisik (EPSON)      │  │      WhatsApp HP Admin       │
 └──────────────────────────────────────┘  └──────────────────────────────┘
```

---

## 🌟 Fitur Unggulan

1. **WhatsApp Gateway Mandiri & Lokal (Baileys):**
   - Tanpa langganan bulanan pihak ketiga (bebas biaya Fonnte/Waba).
   - Bebas limitasi lampiran: pelanggan dapat mengirim file berukuran besar secara langsung di chat.
   - Berjalan murni di jaringan lokal (tanpa perlu tunnel Cloudflare/Ngrok).
   - Mendukung resolusi nomor privasi WhatsApp multi-device (`@lid`).
2. **Dukungan Format Lengkap (PDF & Word):**
   - Mendukung berkas **PDF**, **Microsoft Word (.docx)**, dan **.doc**.
   - Dokumen Word otomatis dikonversi ke PDF dalam hitungan detik tanpa merusak tata letak.
3. **Skema Tarif 3 Tier Warna Presisi:**
   - **TIDAK ADA Kategori Hitam-Putih** (seluruh dokumen teks biasa masuk kategori Berwarna < 50%).
   - **Tier 1 (Berwarna < 50%):** Rp 2.000 / halaman.
   - **Tier 2 (Berwarna ≥ 50%):** Rp 2.500 / halaman.
   - **Tier 3 (Full Warna / Blok / Cover / Foto):** Rp 3.000 / halaman.
4. **AI Agent "Hermes" yang Luwes & Human-Like:**
   - Menjawab layaknya staf Customer Service profesional di dunia nyata (hangat, menyapa nama pelanggan, menggunakan emoji WhatsApp yang tepat).
   - Memiliki sistem normalisasi JSON cerdas yang kebal dari kesalahan format model.
   - Dilengkapi *fallback* deterministik ramah jika koneksi internet/AI sedang lambat.
5. **Cetak Fisik Senyap (*Silent Printing*):**
   - Otomatis mencetak ke printer target via CLI SumatraPDF tanpa memunculkan dialog pop-up.
6. **Eskalasi Revisi Desain / Isi ke Admin:**
   - Jika pelanggan meminta perbaikan isi teks/layout, bot otomatis merangkum revisi dan meneruskannya ke nomor WhatsApp Admin.

---

## 📄 Format Dokumen yang Didukung

| Format | Ekstensi | Mekanisme Pemrosesan |
| :--- | :--- | :--- |
| **PDF Document** | `.pdf` | Dianalisis langsung via PyMuPDF untuk deteksi halaman, dimensi kertas, dan rasio warna. |
| **Microsoft Word** | `.docx`, `.doc` | Dikonversi otomatis menjadi PDF via Microsoft Word Automation (PowerShell COM), lalu dianalisis dan dicetak. |

---

## 📁 Struktur Direktori Proyek

```text
hermes-print-automation/
├── app/
│   ├── config.py               # Konfigurasi Pydantic Settings & environment variables
│   ├── database.py             # SQLite WAL session, transaksi & conversation history
│   ├── main.py                 # Server FastAPI & Webhook endpoint (/webhook/wa)
│   ├── models.py               # Schema data Pydantic (HermesDecision, PDFAnalysis, dsb.)
│   └── services/
│       ├── hermes_agent.py     # AI Turn Decision engine, human-like prompt & schema normalizer
│       ├── pdf_service.py      # PyMuPDF color analysis & Word-to-PDF converter
│       ├── printer_service.py  # SumatraPDF CLI physical printer spooler
│       └── whatsapp_service.py # Pengiriman pesan WhatsApp outbound ke Baileys Gateway
├── wa-gateway/                 # WhatsApp Gateway Service (Node.js & Baileys)
│   ├── index.js                # Koneksi WebSocket WA, QR generator, media downloader, & REST API
│   └── package.json            # Dependensi Baileys, Express, Axios, & Pino
├── storage/                    # Penyimpanan lokal
│   ├── documents/              # Berkas PDF & Word yang diterima dari pelanggan
│   ├── hermes.db               # Database SQLite lokal
│   └── wa_session/             # Kredensial login WhatsApp (multi-device)
├── start_hermes.bat            # Script 1-klik untuk menjalankan Server FastAPI + WhatsApp Gateway
├── start_wa_gateway.bat        # Script untuk menjalankan WhatsApp Gateway secara mandiri
├── setup_pc_baru.bat           # Skrip otomatisasi instalasi depedensi di PC baru
├── test_system.py              # Suite pengujian otomatis (Database, PDF, AI, Spooler, Webhook)
└── .env                        # File konfigurasi aktif toko
```

---

## ⚙️ Konfigurasi Environment (`.env`)

Salin template berikut ke dalam file `.env` di direktori utama:

```env
# ==============================================================================
# HERMES PRINT AUTOMATION - ENVIRONMENT CONFIGURATION
# ==============================================================================

# --- LOCAL WHATSAPP GATEWAY (BAILEYS) ---
BAILEYS_API_URL=http://127.0.0.1:3001

# Nomor WhatsApp Admin untuk eskalasi revisi desain/isi dokumen (format internasional, e.g. 6282313935096)
ADMIN_WHATSAPP_NUMBER=6282313935096

# --- AI AGENT "HERMES" CONFIGURATION ---
# Pilihan provider AI: "deepseek", "openai", atau "gemini"
AI_PROVIDER=deepseek

# Konfigurasi OpenAI-compatible Proxy (9Router / OpenRouter / Ollama)
OPENAI_BASE_URL=http://localhost:20128/v1
OPENAI_API_KEY=sk-e1fd973b2845063d-kowko3-f1cf8099
AI_MODEL=Kenari/beam-1-0:free

# Google Gemini API Key (Opsional jika ingin menggunakan AI_PROVIDER=gemini)
GEMINI_API_KEY=

# --- PRINT HARDWARE & SPOOLER CONFIGURATION ---
PRINTER_OS=windows

# Nama Printer Fisik di Windows (kosongkan "" untuk menggunakan default printer OS)
PRINTER_NAME=

# Path executable SumatraPDF di Windows
SUMATRAPDF_PATH=C:\Users\lenov\AppData\Local\SumatraPDF\SumatraPDF.exe

# Mode Simulasi Cetak (true = uji coba tanpa mencetak kertas fisik, false = cetak langsung ke printer)
PRINT_SIMULATION_MODE=false

# --- PRICING RULES (IDR) ---
# 3 Kategori tarif warna (tidak ada kategori hitam-putih)
PRICE_COLOR_LOW=2000
PRICE_COLOR_HIGH=2500
PRICE_COLOR_FULL=3000

# Profil Nama Percetakan
STORE_NAME=Percetakan Anugrah Indah

# --- STORAGE & DATABASE ---
STORAGE_DIR=storage/temp_pdfs
DATABASE_PATH=storage/hermes.db

# --- SERVER NETWORK CONFIGURATION ---
HOST=0.0.0.0
PORT=8000
```

### Penjelasan Variabel Penting:

| Kategori | Variabel | Penjelasan |
| :--- | :--- | :--- |
| **Gateway** | `BAILEYS_API_URL` | Port REST API lokal tempat Baileys Gateway mendengarkan (`http://127.0.0.1:3001`). |
| **Admin** | `ADMIN_WHATSAPP_NUMBER` | Nomor HP Admin tujuan forward saat ada pelanggan yang ingin revisi isi/layout dokumen. |
| **AI LLM** | `AI_PROVIDER` | `deepseek` (atau `openai`) untuk proxy lokal 9Router, atau `gemini` untuk Google AI Studio. |
| | `AI_MODEL` | Disarankan `Kenari/beam-1-0:free` (respon cepat ~1.5s, tidak terkena rate-limit free pool). |
| | `GEMINI_API_KEY` | Jika menggunakan `AI_PROVIDER=gemini`, isi dengan API key dari [Google AI Studio](https://aistudio.google.com/). |
| **Printer** | `PRINT_SIMULATION_MODE` | Ubah ke `false` saat printer fisik EPSON siap mencetak. Set `true` saat uji coba logika. |
| | `PRINTER_NAME` | Nama printer Windows. Jika dikosongkan, sistem otomatis memilih default printer Windows. |
| **Tarif** | `PRICE_COLOR_LOW` | Tarif lembar Berwarna < 50% (termasuk teks biasa/hitam-putih standar). |
| | `PRICE_COLOR_HIGH` | Tarif lembar Berwarna ≥ 50%. |
| | `PRICE_COLOR_FULL` | Tarif lembar Full Warna (cover tebal / foto / poster). |

---

## 🚀 Panduan Instalasi & Menjalankan Sistem

### 1. Prasyarat Sistem
* **OS:** Windows 10 / 11 (64-bit).
* **Python:** 3.10 atau lebih baru (dengan pip).
* **Node.js:** Versi 18+ (dengan npm).
* **Microsoft Word:** Terpasang di PC (untuk konversi otomatis `.docx` ke PDF).
* **SumatraPDF:** Terpasang di PC (untuk cetak dokumen senyap ke printer).

### 2. Instalasi Dependensi (Sekali Saja)
Jalankan file batch otomatisasi:
```cmd
setup_pc_baru.bat
```
Atau instal manual:
```bash
# Dependensi Python
pip install -r requirements.txt

# Dependensi WhatsApp Gateway Node.js
cd wa-gateway
npm install
cd ..
```

### 3. Menjalankan Sistem
Cukup klik ganda file:
```cmd
start_hermes.bat
```
Script ini akan:
1. Membuka jendela WhatsApp Gateway lokal di port 3001.
2. Membuka jendela Server Hermes FastAPI di `http://localhost:8000`.

---

## 📱 Menghubungkan WhatsApp Toko (Baileys)

1. Saat pertama kali `start_hermes.bat` dijalankan, jendela WhatsApp Gateway akan memunculkan **QR Code**.
2. Buka aplikasi WhatsApp di HP Toko -> **Perangkat Tertaut** -> **Tautkan Perangkat**.
3. Arahkan kamera HP ke QR Code di layar monitor.
4. Begitu tersambung, sesi login akan disimpan secara permanen di folder `storage/wa_session/`.
5. Untuk hari-hari berikutnya, sistem akan langsung terhubung otomatis tanpa perlu scan QR lagi.

---

## 🖨️ Panduan Printer Fisik (EPSON / SumatraPDF)

1. Hubungkan kabel USB printer (misal **EPSON L5290 Series**) ke PC dan pastikan driver printer terpasang di Windows.
2. Pastikan file `SumatraPDF.exe` tersedia di direktori yang tertera pada `SUMATRAPDF_PATH`.
3. Buka [.env](file:///d:/Automasi%20Print/hermes-print-automation/.env) dan pastikan:
   ```env
   PRINT_SIMULATION_MODE=false
   ```
4. Kertas dan tinta printer sudah terisi. Setiap kali pelanggan mengetik *"Cetak"*, dokumen akan langsung keluar secara otomatis dari printer fisik!

---

## 🧪 Verifikasi Sistem Otomatis

Anda dapat menguji seluruh alur sistem (Database, deteksi 3 tier warna PDF, penalaran AI Agent, spooler printer, dan endpoint webhook) dalam satu perintah:

```bash
python test_system.py
```

Jika seluruh komponen siap, Anda akan melihat pesan:
```text
================================================================
🎉 ALL TESTS PASSED! THE SYSTEM IS 100% PRODUCTION READY.
================================================================
```

---

## 📡 Dokumentasi API Endpoints

### 1. `POST /webhook/wa`
Endpoint utama yang dipanggil oleh WhatsApp Gateway setiap kali ada pesan teks atau dokumen baru yang masuk.
* **Payload:**
  ```json
  {
    "sender": "6282270878729",
    "name": "Saenab",
    "message": "Cetak sekarang ya",
    "local_file_path": "D:\\Automasi Print\\hermes-print-automation\\storage\\documents\\dokumen.pdf",
    "filename": "dokumen.pdf",
    "source": "baileys"
  }
  ```
* **Response (HTTP 200):**
  ```json
  {
    "status": "ok",
    "action": "CONFIRM_PRINT"
  }
  ```

### 2. `GET /health`
Mengecek status operasional sistem secara real-time.
* **Response (HTTP 200):**
  ```json
  {
    "status": "healthy",
    "store": "Percetakan Anugrah Indah",
    "printer": {
      "default_printer": "EPSON L5290 Series (Copy 1)",
      "simulation_mode": false
    },
    "ai": {
      "provider": "deepseek",
      "model": "Kenari/beam-1-0:free"
    }
  }
  ```

### 3. `GET /printers`
Menampilkan daftar seluruh printer fisik dan virtual yang terdeteksi di sistem operasi Windows.

---

## 🔒 Kebijakan Git & Repositori

> **Catatan Pengembang:**
> Seluruh commit pada repositori ini dikelola secara lokal. **Jangan menjalankan `git push` secara otomatis**; push ke remote repository akan dilakukan sendiri oleh pemilik proyek.
