import makeWASocket, {
    DisconnectReason,
    useMultiFileAuthState,
    fetchLatestBaileysVersion,
    downloadMediaMessage
} from "@whiskeysockets/baileys";
import pino from "pino";
import qrcode from "qrcode-terminal";
import express from "express";
import axios from "axios";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Configuration
const PORT = process.env.WA_GATEWAY_PORT || 3001;
const FASTAPI_WEBHOOK_URL = process.env.FASTAPI_WEBHOOK_URL || "http://127.0.0.1:8000/webhook/wa";
const SESSION_DIR = path.resolve(__dirname, "../storage/wa_session");
const DOCUMENTS_DIR = path.resolve(__dirname, "../storage/documents");

// Ensure directories exist
if (!fs.existsSync(SESSION_DIR)) fs.mkdirSync(SESSION_DIR, { recursive: true });
if (!fs.existsSync(DOCUMENTS_DIR)) fs.mkdirSync(DOCUMENTS_DIR, { recursive: true });

let sock = null;
let isConnected = false;
const jidMap = new Map();

// Express server for outgoing messages from FastAPI
const app = express();
app.use(express.json());

app.get("/status", (req, res) => {
    res.json({
        status: isConnected ? "connected" : "disconnected",
        user: sock?.user || null
    });
});

app.post("/send", async (req, res) => {
    const { target, message } = req.body;
    if (!target || !message) {
        return res.status(400).json({ status: false, error: "Missing 'target' or 'message'" });
    }

    if (!isConnected || !sock) {
        return res.status(503).json({ status: false, error: "WhatsApp Gateway is not connected yet" });
    }

    try {
        let jid = null;
        if (target.includes("@")) {
            jid = target;
        } else {
            const cleanNumber = target.toString().replace(/[^0-9]/g, "");
            if (jidMap.has(cleanNumber)) {
                jid = jidMap.get(cleanNumber);
            } else if (cleanNumber.length > 13) {
                // WhatsApp LID (Linked Identity) is typically 15 digits
                jid = `${cleanNumber}@lid`;
            } else {
                jid = `${cleanNumber}@s.whatsapp.net`;
            }
        }

        console.log(`[WA-GATEWAY] Mengirim pesan ke JID: ${jid}`);
        const sent = await sock.sendMessage(jid, { text: message });
        return res.json({ status: true, message: "sent", id: sent.key.id, jid });
    } catch (err) {
        console.error("[WA-GATEWAY] Error sending message to", target, err.message);
        return res.status(500).json({ status: false, error: err.message });
    }
});

async function connectToWhatsApp() {
    const { state, saveCreds } = await useMultiFileAuthState(SESSION_DIR);
    const { version } = await fetchLatestBaileysVersion();

    sock = makeWASocket({
        version,
        logger: pino({ level: "silent" }),
        printQRInTerminal: false,
        auth: state,
        defaultQueryTimeoutMs: 60000,
        syncFullHistory: false
    });

    sock.ev.on("creds.update", saveCreds);

    sock.ev.on("connection.update", (update) => {
        const { connection, lastDisconnect, qr } = update;

        if (qr) {
            console.log("\n========================================================");
            console.log("     HERMES WHATSAPP GATEWAY - SILAKAN SCAN QR INI      ");
            console.log("========================================================");
            console.log("Buka WhatsApp di HP Toko -> Perangkat Tertaut -> Tautkan:");
            qrcode.generate(qr, { small: true });
            console.log("========================================================\n");
        }

        if (connection === "close") {
            isConnected = false;
            const shouldReconnect = (lastDisconnect?.error)?.output?.statusCode !== DisconnectReason.loggedOut;
            console.log("[WA-GATEWAY] Koneksi terputus. Status:", lastDisconnect?.error?.message);
            if (shouldReconnect) {
                console.log("[WA-GATEWAY] Menghubungkan ulang dalam 3 detik...");
                setTimeout(connectToWhatsApp, 3000);
            } else {
                console.log("[WA-GATEWAY] Sesi logout. Silakan hapus folder storage/wa_session dan scan ulang.");
            }
        } else if (connection === "open") {
            isConnected = true;
            console.log("\n========================================================");
            console.log(`[WA-GATEWAY] SUKSES TERSAMBUNG! Nomor: ${sock.user?.id.split(':')[0]}`);
            console.log(`[WA-GATEWAY] Siap menerima pesan & file PDF langsung dari WhatsApp.`);
            console.log("========================================================\n");
        }
    });

    // Handle incoming messages
    sock.ev.on("messages.upsert", async ({ messages, type }) => {
        if (type !== "notify") return;

        for (const m of messages) {
            if (!m.message || m.key.fromMe) continue;
            if (m.key.remoteJid === "status@broadcast") continue;
            // Ignore group chats
            if (m.key.remoteJid.endsWith("@g.us")) continue;

            const remoteJid = m.key.remoteJid;
            let senderNumber = remoteJid.split("@")[0].replace(/[^0-9]/g, "");

            // Attempt to resolve real Phone Number if remoteJid is @lid
            if (remoteJid.endsWith("@lid") && sock.signalRepository?.lidMapping?.getPNForLID) {
                try {
                    const pnJid = await sock.signalRepository.lidMapping.getPNForLID(remoteJid);
                    if (pnJid) {
                        const cleanPn = pnJid.split("@")[0].replace(/[^0-9]/g, "");
                        console.log(`[WA-GATEWAY] Resolved LID ${senderNumber} -> Nomor Telepon: ${cleanPn}`);
                        jidMap.set(cleanPn, remoteJid);
                        senderNumber = cleanPn;
                    }
                } catch (e) {}
            }
            jidMap.set(senderNumber, remoteJid);
            jidMap.set(remoteJid, remoteJid);

            const customerName = m.pushName || "";
            const msgObj = m.message;

            let textMessage = "";
            let localFilePath = null;
            let originalFilename = "";

            // Check if document / PDF
            let docMsg = msgObj.documentMessage;
            if (!docMsg && msgObj.documentWithCaptionMessage) {
                docMsg = msgObj.documentWithCaptionMessage.message?.documentMessage;
            }

            if (docMsg) {
                originalFilename = docMsg.fileName || "document.pdf";
                textMessage = docMsg.caption || "";
                console.log(`[WA-GATEWAY] File diterima dari ${senderNumber} (${customerName}): ${originalFilename}`);

                try {
                    console.log(`[WA-GATEWAY] Mengunduh lampiran ${originalFilename}...`);
                    const buffer = await downloadMediaMessage(
                        m,
                        "buffer",
                        {},
                        {
                            logger: pino({ level: "silent" }),
                            reuploadRequest: sock.updateMediaMessage
                        }
                    );

                    const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
                    const cleanName = originalFilename.replace(/[^\w.-]/g, "_");
                    const targetFile = path.resolve(DOCUMENTS_DIR, `${timestamp}_${cleanName}`);
                    await fs.promises.writeFile(targetFile, buffer);

                    localFilePath = targetFile;
                    console.log(`[WA-GATEWAY] File berhasil disimpan ke: ${targetFile}`);
                } catch (dlErr) {
                    console.error("[WA-GATEWAY] Gagal mengunduh file media:", dlErr.message);
                }
            } else if (msgObj.conversation) {
                textMessage = msgObj.conversation;
            } else if (msgObj.extendedTextMessage?.text) {
                textMessage = msgObj.extendedTextMessage.text;
            } else if (msgObj.imageMessage) {
                textMessage = msgObj.imageMessage.caption || "[Gambar diterima]";
            }

            if (!textMessage && !localFilePath) continue;

            console.log(`[WA-GATEWAY] Meneruskan ke Hermes FastAPI: Dari=${senderNumber}, Pesan='${textMessage}', File=${originalFilename || 'None'}`);

            // Forward to FastAPI
            try {
                await axios.post(FASTAPI_WEBHOOK_URL, {
                    sender: senderNumber,
                    name: customerName,
                    message: textMessage,
                    local_file_path: localFilePath,
                    filename: originalFilename,
                    source: "baileys"
                }, { timeout: 15000 });
            } catch (postErr) {
                console.error("[WA-GATEWAY] Gagal meneruskan ke FastAPI Webhook:", postErr.message);
            }
        }
    });
}

// Start Express REST API and Baileys
app.listen(PORT, "127.0.0.1", () => {
    console.log(`[WA-GATEWAY] Outbound REST API aktif di http://127.0.0.1:${PORT}`);
    connectToWhatsApp();
});
