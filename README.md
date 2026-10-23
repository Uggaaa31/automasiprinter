# 🖨️ Hermes Print Automation

> **Production-Ready WhatsApp-Based Document Print Automation System**  
> Dikendalikan oleh AI Agent **"Hermes"** dengan integrasi **Fonnte API**, **PyMuPDF**, dan **Spooler Cetak Fisik** (SumatraPDF di Windows / CUPS `lp` di Linux).

---

## 📑 Daftar Isi
1. [Arsitektur & Alur Kerja Sistem](#-arsitektur--alur-kerja-sistem)
2. [Fitur Unggulan](#-fitur-unggulan)
3. [Struktur Direktori](#-struktur-direktori)
4. [Persyaratan Sistem](#-persyaratan-sistem)
5. [Panduan Instalasi & Setup Cepat](#-panduan-instalasi--setup-cepat)
6. [Konfigurasi Environment (.env)](#-konfigurasi-environment-env)
7. [Panduan Printer Fisik & SumatraPDF](#-panduan-printer-fisik--sumatrapdf)
8. [Menghubungkan Webhook Fonnte via Tunnel](#-menghubungkan-webhook-fonnte-via-tunnel)
9. [Menjalankan Sistem & Verifikasi](#-menjalankan-sistem--verifikasi)
10. [Dokumentasi API Endpoints](#-dokumentasi-api-endpoints)

---

## 🏛️ Arsitektur & Alur Kerja Sistem

Sistem ini berjalan langsung pada PC lokal yang terhubung kabel USB ke mesin pencetak fisik (misal: Epson L3110, Canon G2010, HP LaserJet).

```text
 ┌──────────────────────┐
 │   Pelanggan (WA)     │ 
 └──────────┬───────────┘
            │ 1. Kirim File PDF via WhatsApp
            ▼
 ┌──────────────────────┐
 │ Fonnte WA Gateway    │
 └──────────┬───────────┘
            │ 2. Webhook POST (/webhook/fonnte)
            ▼
 ┌──────────────────────────────────────────────────────────────┐
 │                  FastAPI Application (Local PC)              │
 │                                                              │
 │  [pdf_service.py]                                            │
 │  ├── Unduh PDF ke storage/temp_pdfs/                         │
 │  └── Analisis PyMuPDF & NumPy:                               │
 │      • Halaman total, orientasi (Potret/Lanskap), ukuran     │
 │      • Deteksi akurat halaman Warna vs Hitam-Putih           │
 │      • Ekstraksi teks & hitung estimasi biaya cetak          │
 │                                                              │
 │  [database.py]                                               │
 │  └── SQLite State Management (Multi-turn per nomor WA)       │
 │                                                              │
 │  [hermes_agent.py] (AI Agent "Hermes")                       │
 │  └── LLM Structured Output (Google GenAI / OpenAI)          │
 │      • NEW_DOCUMENT_SUMMARY ──> Ringkas isi & tawarkan cetak │
 │      • CONFIRM_PRINT        ──> Setujui & cetak otomatis     │
 │      • REVISE_PRINT_SETTINGS──> Perbarui rangkap/warna/hal   │
 │      • REVISE_CONTENT_ADMIN ──> Alihkan ke WA Admin          │
 └──────────┬────────────────────────────────────┬──────────────┘
            │                                    │
    (Jika Disetujui)                   (Jika Minta Edit Desain/Isi)
            │                                    │
            ▼                                    ▼
 ┌──────────────────────┐               ┌──────────────────────┐
 │  printer_service.py  │               │   fonnte_service.py  │
 │  (SumatraPDF CLI)    │               │ (Forward PDF & Catatan)│
 └──────────┬───────────┘               └──────────┬───────────┘
            │ Eksekusi CLI Spooler                 │ Notifikasi & File
            ▼                                      ▼
 ┌──────────────────────┐               ┌──────────────────────┐
 │ Mesin Printer Fisik  │               │ WhatsApp Admin Gerai │
 │   (Kabel USB Lokal)  │               │ (Editing Manual)     │
 └──────────────────────┘               └──────────────────────┘
```

---

## 🌟 Fitur Unggulan

1. **AI Agent "Hermes" yang Ramah & Solutif:**
   - Berbicara dalam Bahasa Indonesia yang santun, informatif, dan terstruktur dengan format WhatsApp (emojis & formatting).
   - Menggunakan **Structured Outputs (JSON Schema)** untuk klasifikasi maksud (*intent*) deterministik tanpa halusinasi.
2. **Mesin Analisis PDF Cerdas (PyMuPDF + NumPy):**
   - Mendeteksi ukuran kertas standar (A4, F4/Folio, Letter, Legal, A3).
   - Mendeteksi orientasi halaman (Potret / Lanskap).
   - **Chroma Divergence Pixel Analysis:** Membedakan halaman berwarna vs hitam-putih secara presisi tinggi tanpa tertipu oleh artefak kompresi JPEG.
   - Menghitung kalkulasi harga cetak otomatis secara real-time.
3. **Eksekusi Cetak Langsung (Hardware Spooling):**
   - Menggunakan **SumatraPDF CLI** di Windows (`-print-to`, `-print-settings`) dan **CUPS `lp`** di Linux.
   - Mendukung pengaturan jumlah rangkap (*copies*), mode warna (*monochrome* / *color*), dan pemilihan halaman (*page range*).
   - Dilengkapi **`PRINT_SIMULATION_MODE`** untuk kemudahan testing tanpa harus menghabiskan kertas atau menghubungkan printer fisik.
4. **Eskalasi Cerdas ke Admin (Revisi Dokumen):**
   - Jika pelanggan meminta revisi tata letak, salah ketik (*typo*), atau desain dokumen, sistem otomatis meneruskan berkas PDF beserta catatan instruksi pelanggan ke WhatsApp Admin gerai.
5. **State Management & Riwayat Multi-Turn:**
   - Didukung database SQLite lokal dengan mode **WAL (Write-Ahead Logging)** untuk menyimpan riwayat sesi percakapan per nomor pelanggan.

---

## 📂 Struktur Direktori

```text
hermes-print-automation/
├── .env.example                # Template konfigurasi environment variables
├── requirements.txt            # Dependensi Python
├── README.md                   # Dokumentasi lengkap sistem
├── test_system.py              # Suite pengujian otomatis menyeluruh
├── storage/
│   ├── hermes.db               # Database SQLite sesi dan percakapan (otomatis dibuat)
│   └── temp_pdfs/              # Penyimpanan lokal berkas PDF pelanggan
└── app/
    ├── __init__.py             # Inisialisasi package
    ├── main.py                 # FastAPI app & Webhook receiver (/webhook/fonnte)
    ├── config.py               # Pydantic Settings & validasi environment
    ├── database.py             # SQLite WAL connection & CRUD session management
    ├── models.py               # Pydantic schemas (Webhook, PDF, Hermes, Printer)
    └── services/
        ├── __init__.py
        ├── fonnte_service.py   # Gateway kirim pesan & forward dokumen ke Admin
        ├── pdf_service.py      # Download, inspeksi PyMuPDF, deteksi warna, & pricing
        ├── hermes_agent.py     # Prompt Hermes & LLM Structured Output decision
        └── printer_service.py  # Eksekutor cetak fisik via SumatraPDF CLI / CUPS lp
```

---

## 💻 Persyaratan Sistem

- **Sistem Operasi:** Windows 10/11 (Direkomendasikan untuk SumatraPDF) atau Linux (CUPS).
- **Python:** Versi 3.10 atau lebih baru.
- **Hardware:** PC/Laptop yang terhubung langsung ke mesin printer via kabel USB.
- **Akun WhatsApp Gateway:** Token perangkat dari [Fonnte](https://md.fonnte.com/).
- **AI API Key:** Google Gemini API Key dari [Google AI Studio](https://aistudio.google.com/) (Gratis) atau OpenAI API Key.

---

## 🚀 Panduan Instalasi & Setup Cepat

### Cara 1: Setup Otomatis 1-Klik untuk PC Baru (Windows)
Jika Anda memindahkan proyek ini ke PC kasir/gerai baru yang belum memiliki apa pun:
1. Cukup klik **2x** file:
   👉 **`setup_pc_baru.bat`**
2. Script akan secara otomatis:
   - Mendeteksi apakah Python sudah ada. Jika belum ada, script akan **otomatis mengunduh dan memasang Python 3.12 resmi secara silent** beserta penambahan ke System PATH.
   - Memasang `SumatraPDF` secara silent.
   - Membuat `venv` dan menginstall seluruh library di `requirements.txt`.
   - Menyiapkan file `.env`.
3. Setelah selesai, cukup klik **2x** file:
   👉 **`start_hermes.bat`** untuk langsung menjalankan server!

---

### Cara 2: Setup Manual via Terminal
```bash
cd "d:\Automasi Print\hermes-print-automation"
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```
Buka file `.env` menggunakan teks editor dan lengkapi variabel-variabel utamanya.

---

## ⚙️ Konfigurasi Environment (`.env`)

File `.env` adalah pusat pengaturan seluruh sistem Hermes Print Automation. Berikut adalah panduan lengkap step-by-step untuk setiap variabel yang digunakan:

### 📑 Tabel Rangkuman Variabel

| Variabel | Kategori | Deskripsi | Contoh Nilai |
| :--- | :--- | :--- | :--- |
| `FONNTE_API_TOKEN` | WhatsApp | Token perangkat Fonnte untuk bot WA | `akgprim4YPTrHXkSPv2u` |
| `FONNTE_API_URL` | WhatsApp | URL API resmi Fonnte | `https://api.fonnte.com` |
| `ADMIN_WHATSAPP_NUMBER`| WhatsApp | Nomor WA Admin untuk menerima revisi desain | `6282313935096` |
| `AI_PROVIDER` | AI Agent | Provider AI (`deepseek`, `gemini`, atau `openai`) | `deepseek` |
| `OPENAI_BASE_URL` | AI Agent | Base URL API (untuk 9Router, Ollama, OpenAI) | `http://localhost:20128/v1` |
| `OPENAI_API_KEY` | AI Agent | API Key OpenAI atau Proxy 9Router | `sk-e1fd...` |
| `AI_MODEL` | AI Agent | Nama model AI yang digunakan | `Kenari/deepseek-v4-1-flash:free` |
| `GEMINI_API_KEY` | AI Agent | API Key Google Gemini (jika AI_PROVIDER=gemini) | `AIzaSy...` |
| `PRINTER_OS` | Hardware | Sistem Operasi PC host (`windows` / `linux`) | `windows` |
| `PRINTER_NAME` | Hardware | Nama printer di OS (kosongkan untuk default) | `EPSON L3110 Series` |
| `SUMATRAPDF_PATH` | Hardware | Lokasi file SumatraPDF.exe | `C:\Users\lenov\AppData\Local\SumatraPDF\SumatraPDF.exe` |
| `PRICE_COLOR_LOW` | Bisnis | Tarif cetak per lembar Berwarna < 50% (IDR) | `2000` |
| `PRICE_COLOR_HIGH`| Bisnis | Tarif cetak per lembar Berwarna >= 50% (IDR) | `2500` |
| `PRICE_COLOR_FULL`| Bisnis | Tarif cetak per lembar Full Warna (IDR) | `3000` |
| `STORE_NAME` | Bisnis | Nama Toko / Usaha Percetakan Anda | `Percetakan Anugrah Indah` |
| `STORAGE_DIR` | Sistem | Folder penyimpanan sementara PDF | `storage/temp_pdfs` |
| `DATABASE_PATH` | Sistem | Lokasi file database SQLite | `storage/hermes.db` |
| `HOST` & `PORT` | Jaringan | IP bind host & port server | `0.0.0.0` & `8000` |

---

### 📝 Panduan Step-by-Step Menyiapkan Masing-Masing Variabel

#### 1. Setup WhatsApp Gateway (Fonnte)
- **`FONNTE_API_TOKEN`**:
  1. Buka dan login ke dashboard [Fonnte](https://md.fonnte.com/).
  2. Buka menu **Device** di sidebar kiri.
  3. Hubungkan nomor WhatsApp bot percetakan Anda via Scan QR Code.
  4. Salin string **Token** yang tampil pada kartu device Anda dan tempel di sini.
- **`FONNTE_API_URL`**:
  - Biarkan `https://api.fonnte.com` (nilai standar resmi).
- **`ADMIN_WHATSAPP_NUMBER`**:
  - Masukkan nomor WhatsApp pribadi Admin/Pemilik toko gerai (format internasional diawali `62` tanpa tanda `+` atau spasi, contoh: `6282313935096`).
  - *Fungsi:* Saat pelanggan meminta revisi tata letak, salah ketik, atau desain dokumen, sistem otomatis meneruskan file PDF dan catatan instruksi pelanggan ke nomor ini.

#### 2. Setup AI Agent "Hermes" (Pilih Salah Satu Opsi)

##### Opsi A: Menggunakan 9Router Proxy Lokal (DeepSeek Free) — *Aktif Sekarang*
Jika Anda menggunakan **9Router Proxy** di PC lokal (`localhost:20128`):
```ini
AI_PROVIDER=deepseek
OPENAI_BASE_URL=http://localhost:20128/v1
OPENAI_API_KEY=sk-e1fd973b2845063d-0m0405-d27d08e9
AI_MODEL=Kenari/deepseek-v4-1-flash:free
```
*(API Key didapatkan dari menu **Endpoint & Key** pada dashboard 9Router).*

##### Opsi B: Menggunakan Google Gemini API (100% Gratis & Cepat)
1. Buka [Google AI Studio](https://aistudio.google.com/) dan login dengan akun Gmail.
2. Klik tombol **Get API key** $\rightarrow$ **Create API key**.
3. Salin API key yang diawali `AIzaSy...`.
4. Isi di `.env`:
```ini
AI_PROVIDER=gemini
GEMINI_API_KEY=AIzaSy...kunci_anda_disini
AI_MODEL=gemini-2.5-flash
```

##### Opsi C: Menggunakan OpenAI Langsung (GPT-4o Mini)
```ini
AI_PROVIDER=openai
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_API_KEY=sk-proj-...kunci_anda_disini
AI_MODEL=gpt-4o-mini
```

#### 3. Setup Hardware Printer & Spooler
- **`PRINTER_OS`**:
  - Isi `windows` (untuk PC Windows) atau `linux` (untuk Linux).
- **`PRINTER_NAME`**:
  - Kosongkan (`""`) agar sistem otomatis mendeteksi dan menggunakan **Default Printer** Windows.
  - Atau isi nama spesifik sesuai yang tertera di Windows (*Settings -> Bluetooth & devices -> Printers & scanners*), misalnya `EPSON L3110 Series`.
- **`SUMATRAPDF_PATH`**:
  - Lokasi file `SumatraPDF.exe`. File ini otomatis dipasang oleh script `setup_pc_baru.bat` ke:  
    `C:\Users\<NamaUser>\AppData\Local\SumatraPDF\SumatraPDF.exe`
- **`PRINT_SIMULATION_MODE`**:
  - `True`: Mode aman untuk testing (sistem mencatat log perintah cetak tanpa membuang kertas/tinta printer).
  - `False`: Ubah ke `False` saat kabel USB printer fisik sudah terhubung dan Anda ingin dokumen dicetak riil secara fisik.

#### 4. Setup Tarif Cetak & Profil Bisnis
Sistem menggunakan 3 kategori tarif cetak warna (tidak ada kategori hitam-putih terpisah; semua dokumen teks biasa dihitung masuk ke kategori Berwarna < 50%):
- **`PRICE_COLOR_LOW`**:
  - Tarif cetak per halaman Berwarna kurang dari 50% / low coverage / teks standar (default: `2000`).
- **`PRICE_COLOR_HIGH`**:
  - Tarif cetak per halaman Berwarna lebih dari 50% / high coverage (default: `2500`).
- **`PRICE_COLOR_FULL`**:
  - Tarif cetak per halaman Full Warna / Block / Cover / Foto (default: `3000`).
- **`STORE_NAME`**:
  - Nama usaha/percetakan Anda yang digunakan oleh AI Hermes saat menyapa pelanggan di WhatsApp (contoh: `Percetakan Anugrah Indah`).


---

## 🖨️ Panduan Printer Fisik & SumatraPDF

### Mengapa SumatraPDF?
Windows tidak memiliki antarmuka command-line bawaan yang mendukung passing parameter spesifik (seperti jumlah rangkap, duplex, atau pemilihan halaman) ke driver printer tanpa memunculkan dialog GUI. **SumatraPDF** adalah standar industri untuk automasi pencetakan PDF di Windows karena sangat ringan, berlisensi bebas, dan mendukung CLI lengkap.

### Cara Memasang SumatraPDF di Windows:
1. Unduh file **SumatraPDF Portable (64-bit)** atau **Installer** dari situs resminya:  
   👉 [https://www.sumatrapdfreader.org/download-free-pdf-viewer](https://www.sumatrapdfreader.org/download-free-pdf-viewer)
2. Letakkan file `SumatraPDF.exe` di salah satu lokasi berikut:
   - Di dalam folder proyek: `hermes-print-automation/bin/SumatraPDF.exe`
   - Atau install di `C:\Program Files\SumatraPDF\SumatraPDF.exe`
   - Atau masukkan foldernya ke dalam **System PATH**.
3. Jika diletakkan di lokasi khusus, sesuaikan path pada `.env`:
   ```ini
   SUMATRAPDF_PATH=C:\Program Files\SumatraPDF\SumatraPDF.exe
   ```

> 💡 **Fallback Cerdas:** Jika SumatraPDF belum terpasang, sistem secara otomatis beralih ke perintah PowerShell `Start-Process -Verb PrintTo` sehingga pencetakan tetap dapat berjalan.

---

## 🌐 Menghubungkan Webhook Fonnte via Tunnel (Publik HTTPS)

Agar Fonnte di cloud dapat mengirimkan pesan WhatsApp ke server FastAPI di PC lokal toko Anda (`localhost:8000`), sistem memerlukan tunnel publik HTTPS.

### 🌟 Cara Otomatis (Cloudflare Tunnel - Gratis & Tanpa Akun):
File `setup_pc_baru.bat` sudah otomatis mendownload `cloudflared.exe`. Anda cukup:
1. Klik 2x file **`start_hermes.bat`** (otomatis membuka Server Hermes + Cloudflare Tunnel).
   * Atau klik 2x **`start_tunnel.bat`** untuk membuka tunnel tersendiri.
2. Di jendela tunnel, akan muncul URL publik resmi Cloudflare, contoh:  
   `https://random-subdomain.trycloudflare.com`
3. Salin URL tersebut dan tambahkan `/webhook/fonnte` di belakangnya:
   ```text
   https://random-subdomain.trycloudflare.com/webhook/fonnte
   ```

### ⚡ Cara Alternatif 1: Bawaan Windows (OpenSSH - Tanpa Install Apapun)
Cukup jalankan `start_tunnel.bat` atau via CMD:
```bash
ssh -o StrictHostKeyChecking=no -R 80:127.0.0.1:8000 nokey@localhost.run
```

### ⚡ Cara Alternatif 2: Ngrok
Jika Anda sudah memasang Ngrok:
```bash
ngrok http 8000
```

### Konfigurasi di Dashboard Fonnte:
1. Masuk ke [https://md.fonnte.com/](https://md.fonnte.com/).
2. Buka menu **Device Settings** -> **Webhook**.
3. Masukkan Webhook URL yang Anda dapatkan dari tunnel di atas, contoh:
   ```text
   https://random-subdomain.trycloudflare.com/webhook/fonnte
   ```
4. Simpan pengaturan. Sekarang setiap pesan WhatsApp pelanggan yang masuk akan langsung direspon oleh Hermes!

---

## 🧪 Menjalankan Sistem & Verifikasi

### 1. Jalankan Unit & Integration Test
Proyek ini dilengkapi dengan suite pengujian otomatis yang menguji seluruh modul tanpa memerlukan sambungan printer fisik:
```bash
python test_system.py
```
Hasil uji mencakup:
- Inisialisasi tabel database SQLite & state CRUD.
- Pembuatan dan analisis PDF dengan PyMuPDF (halaman warna vs BW).
- Ekstraksi parameter dan penalaran LLM Hermes.
- Pembentukan perintah CLI printer spooler.
- Endpoint FastAPI Webhook.

### 2. Jalankan Server Production / Development
Jalankan server menggunakan Uvicorn:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
Akses dokumentasi Swagger UI interaktif di browser Anda:
👉 `http://localhost:8000/docs`

---

## 📡 Dokumentasi API Endpoints

### 1. `POST /webhook/fonnte`
Endpoint penerima callback webhook dari Fonnte.
- **Content-Type:** `application/json` atau `application/x-www-form-urlencoded`.
- **Payload Utama:**
  ```json
  {
    "sender": "6281234567890",
    "message": "Tolong cetak 2 rangkap hitam putih ya",
    "url": "https://example.com/skripsi.pdf",
    "filename": "skripsi_final.pdf",
    "name": "Budi Santoso"
  }
  ```

### 2. `GET /health`
Memeriksa status operasional server, database SQLite, printer default yang terdeteksi di Windows, status SumatraPDF, dan kredensial AI.

### 3. `GET /printers`
Menampilkan daftar printer fisik dan virtual yang terdaftar di sistem operasi PC lokal.

### 4. `GET /session/{phone_number}`
Inspeksi data sesi aktif dan riwayat pesan pelanggan tertentu (untuk keperluan monitoring / debug).

---

## 🛡️ Lisensi & Kredit
Dibangun dengan standar rekayasa perangkat lunak tingkat produksi untuk automasi percetakan modern.  
© 2026 **Hermes Print Automation**.
